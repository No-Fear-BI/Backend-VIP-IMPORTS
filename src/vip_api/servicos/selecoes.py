"""Envio da seleção por WhatsApp e histórico do cliente.

Não usa API do WhatsApp e não tem custo: a resposta traz um link `wa.me` que
o navegador abre com o texto já preenchido.
"""

from datetime import datetime
from urllib.parse import quote

from sqlalchemy import and_, func, select, tuple_
from sqlalchemy.orm import Session, aliased

from vip_api.configuracao import configuracao
from vip_api.erros.codigos import CARRINHO_VAZIO, CURSOR_INVALIDO
from vip_api.erros.excecoes import AppError
from vip_api.esquemas.base import (
    Pagina,
    Paginacao,
    codificar_cursor,
    decodificar_cursor,
    exigir_formato_do_cursor,
)
from vip_api.esquemas.selecao import SelecaoItemSaida, SelecaoResumo, SelecaoSaida
from vip_api.modelos.catalogo import Categoria, Colecao, Marca, Produto, ProdutoImagem, ProdutoVariacao
from vip_api.modelos.cliente import Carrinho, CarrinhoItem, Cliente
from vip_api.modelos.selecao import Selecao, SelecaoItem

SAUDACAO = "Olá! Tenho interesse nestes itens:"
ASSINATURA = "Enviado pelo site."
POR_PAGINA_PADRAO = 20
POR_PAGINA_MAXIMO = 50

_Tamanho = aliased(ProdutoVariacao, name="v_tamanho")
_Cor = aliased(ProdutoVariacao, name="v_cor")


def rotulo_variacao(tamanho: str | None, cor: str | None) -> str | None:
    """Compõe o rótulo exibível das variações do item.

    Com as duas sai "M / Preto"; com uma só, "M" ou "Preto"; sem nenhuma, nada
    — é o formato "(Chanel, M / Preto)" que o contrato mostra.
    """
    escolhas = [valor for valor in (tamanho, cor) if valor]
    return " / ".join(escolhas) if escolhas else None


def _linha_da_mensagem(codigo: str, nome: str, marca: str, variacao: str | None) -> str:
    detalhe = f"{marca}, {variacao}" if variacao else marca
    return f"• {codigo} — {nome} ({detalhe})"


def montar_mensagem(itens: list[SelecaoItemSaida]) -> str:
    linhas = [
        _linha_da_mensagem(i.codigo, i.nome, i.marca, i.variacao) for i in itens
    ]
    return f"{SAUDACAO}\n\n" + "\n".join(linhas) + f"\n\n{ASSINATURA}"


def montar_link(mensagem: str) -> str:
    """O BACKEND monta o link, não o frontend: assim o número da loja e o
    formato da mensagem ficam em um lugar só.

    `safe=""` encoda tudo — quebra de linha, acento e o marcador "•". Sem isso
    o texto chega truncado ou corrompido no WhatsApp.
    """
    return f"https://wa.me/{configuracao.WHATSAPP_LOJA}?text={quote(mensagem, safe='')}"


def _itens_do_carrinho_para_congelar(sessao: Session, cliente_id: int):
    return sessao.execute(
        select(
            Produto.id.label("produto_id"),
            Produto.codigo,
            Produto.nome,
            Marca.nome.label("marca_nome"),
            Categoria.nome.label("categoria_nome"),
            Colecao.nome.label("colecao_nome"),
            ProdutoImagem.url.label("imagem_url"),
            _Tamanho.valor.label("variacao_tamanho"),
            _Cor.valor.label("variacao_cor"),
        )
        # select_from explícito: a lista de colunas começa em Produto, mas o
        # caminho das junções parte de CarrinhoItem. Sem isso o SQLAlchemy não
        # sabe qual é o lado esquerdo do JOIN.
        .select_from(CarrinhoItem)
        .join(Carrinho, Carrinho.id == CarrinhoItem.carrinho_id)
        .join(Produto, Produto.id == CarrinhoItem.produto_id)
        .join(Marca, Marca.id == Produto.marca_id)
        .join(Categoria, Categoria.id == Produto.categoria_id)
        .join(Colecao, Colecao.id == Produto.colecao_id)
        .outerjoin(
            ProdutoImagem,
            and_(ProdutoImagem.produto_id == Produto.id, ProdutoImagem.capa.is_(True)),
        )
        .outerjoin(_Tamanho, _Tamanho.id == CarrinhoItem.variacao_tamanho_id)
        .outerjoin(_Cor, _Cor.id == CarrinhoItem.variacao_cor_id)
        .where(Carrinho.cliente_id == cliente_id, Produto.status != "oculto")
        .order_by(CarrinhoItem.criado_em.asc(), CarrinhoItem.id.asc())
    ).all()


def criar_selecao(sessao: Session, cliente: Cliente) -> SelecaoSaida:
    linhas = _itens_do_carrinho_para_congelar(sessao, cliente.id)
    if not linhas:
        raise AppError(
            codigo=CARRINHO_VAZIO,
            mensagem="Sua seleção está vazia. Adicione produtos antes de enviar.",
            status_code=400,
        )

    selecao = Selecao(
        cliente_id=cliente.id,
        # Dados do cliente também congelados: se o cadastro sumir, o
        # atendimento ainda sabe com quem estava falando.
        cliente_nome=cliente.nome,
        cliente_email=cliente.email,
        cliente_telefone=cliente.telefone,
        total_itens=len(linhas),
    )
    sessao.add(selecao)
    sessao.flush()

    for ordem, linha in enumerate(linhas, start=1):
        # TEXTO copiado agora, não JOIN na leitura: se o produto for renomeado
        # ou excluído depois, o painel continua mostrando o que o cliente viu.
        # `produto_id` fica só como referência, nulável e sem cascata.
        sessao.add(
            SelecaoItem(
                selecao_id=selecao.id,
                produto_id=linha.produto_id,
                produto_codigo=linha.codigo,
                produto_nome=linha.nome,
                marca_nome=linha.marca_nome,
                categoria_nome=linha.categoria_nome,
                colecao_nome=linha.colecao_nome,
                imagem_url=linha.imagem_url,
                variacao_tamanho=linha.variacao_tamanho,
                variacao_cor=linha.variacao_cor,
                ordem=ordem,
            )
        )

    sessao.commit()
    sessao.refresh(selecao)

    itens = [
        SelecaoItemSaida(
            codigo=linha.codigo,
            nome=linha.nome,
            marca=linha.marca_nome,
            variacao=rotulo_variacao(linha.variacao_tamanho, linha.variacao_cor),
        )
        for linha in linhas
    ]
    mensagem = montar_mensagem(itens)

    # O carrinho NÃO é esvaziado aqui, de propósito: se a pessoa abrir o link
    # e fechar o WhatsApp sem mandar nada, esvaziar teria destruído a seleção
    # dela. Duas seleções parecidas no painel é ruído; carrinho perdido é
    # venda perdida.
    return SelecaoSaida(
        id=selecao.id,
        criado_em=selecao.criado_em,
        itens=itens,
        mensagem_whatsapp=mensagem,
        link_whatsapp=montar_link(mensagem),
    )


def listar_selecoes(
    sessao: Session, cliente_id: int, cursor: str | None, por_pagina: int
) -> Pagina[SelecaoResumo]:
    por_pagina = max(1, min(por_pagina, POR_PAGINA_MAXIMO))

    dados_cursor = None
    if cursor:
        dados_cursor = exigir_formato_do_cursor(
            decodificar_cursor(cursor), texto=("v",), inteiros=("id", "t")
        )
        if {"v", "id"} - dados_cursor.keys():
            raise AppError(
                codigo=CURSOR_INVALIDO,
                mensagem="O cursor de paginação informado é inválido.",
                status_code=400,
            )

    consulta = select(Selecao.id, Selecao.criado_em, Selecao.total_itens).where(
        Selecao.cliente_id == cliente_id
    )

    if dados_cursor is None:
        total = (
            sessao.scalar(
                select(func.count()).select_from(Selecao).where(Selecao.cliente_id == cliente_id)
            )
            or 0
        )
    else:
        total = int(dados_cursor.get("t", 0))
        try:
            marca_tempo = datetime.fromisoformat(str(dados_cursor["v"]))
        except ValueError as exc:
            raise AppError(
                codigo=CURSOR_INVALIDO,
                mensagem="O cursor de paginação informado é inválido.",
                status_code=400,
            ) from exc
        # Comparação de tupla, igual à do catálogo: é ela que impede item
        # repetido quando duas seleções têm o mesmo criado_em.
        consulta = consulta.where(
            tuple_(Selecao.criado_em, Selecao.id)
            < tuple_(marca_tempo, int(dados_cursor["id"]))
        )

    linhas = sessao.execute(
        consulta.order_by(Selecao.criado_em.desc(), Selecao.id.desc()).limit(por_pagina + 1)
    ).all()

    tem_proxima = len(linhas) > por_pagina
    linhas = linhas[:por_pagina]

    # Os itens de TODAS as seleções da página numa consulta só — o N+1 aqui
    # seria uma consulta por seleção listada.
    ids = [linha.id for linha in linhas]
    itens_por_selecao: dict[int, list[SelecaoItemSaida]] = {i: [] for i in ids}
    if ids:
        for item in sessao.execute(
            select(
                SelecaoItem.selecao_id,
                SelecaoItem.produto_codigo,
                SelecaoItem.produto_nome,
                SelecaoItem.marca_nome,
                SelecaoItem.variacao_tamanho,
                SelecaoItem.variacao_cor,
            )
            .where(SelecaoItem.selecao_id.in_(ids))
            .order_by(SelecaoItem.selecao_id, SelecaoItem.ordem, SelecaoItem.id)
        ).all():
            itens_por_selecao[item.selecao_id].append(
                SelecaoItemSaida(
                    codigo=item.produto_codigo,
                    nome=item.produto_nome,
                    marca=item.marca_nome,
                    variacao=rotulo_variacao(item.variacao_tamanho, item.variacao_cor),
                )
            )

    proximo_cursor = None
    if tem_proxima and linhas:
        ultima = linhas[-1]
        proximo_cursor = codificar_cursor(
            {"v": ultima.criado_em.isoformat(), "id": ultima.id, "t": total}
        )

    return Pagina[SelecaoResumo](
        dados=[
            SelecaoResumo(
                id=linha.id,
                criado_em=linha.criado_em,
                total_itens=linha.total_itens,
                itens=itens_por_selecao[linha.id],
            )
            for linha in linhas
        ],
        paginacao=Paginacao(
            total=total, por_pagina=por_pagina, proximo_cursor=proximo_cursor
        ),
    )
