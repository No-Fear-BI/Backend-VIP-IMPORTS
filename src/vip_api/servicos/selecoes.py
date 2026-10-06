"""Gera a mensagem do WhatsApp em memória, sem registrar pedidos."""

from urllib.parse import quote

from sqlalchemy import and_, select
from sqlalchemy.orm import Session, aliased

from vip_api.configuracao import configuracao
from vip_api.erros.codigos import CARRINHO_VAZIO
from vip_api.erros.excecoes import AppError
from vip_api.esquemas.selecao import SelecaoItemSaida, SelecaoSaida
from vip_api.modelos.catalogo import Categoria, Marca, Produto, ProdutoImagem, ProdutoVariacao
from vip_api.modelos.cliente import Carrinho, CarrinhoItem, Cliente
from vip_api.servicos.colecoes import nome_da_colecao

SAUDACAO = "Olá! Tenho interesse nestes itens:"
ASSINATURA = "Enviado pelo site."

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


def _itens_do_carrinho(sessao: Session, cliente_id: int):
    return sessao.execute(
        select(
            Produto.id.label("produto_id"),
            Produto.codigo,
            Produto.nome,
            Marca.nome.label("marca_nome"),
            Categoria.nome.label("categoria_nome"),
            nome_da_colecao(Produto.feminino, Produto.masculino).label("colecao_nome"),
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
    linhas = _itens_do_carrinho(sessao, cliente.id)
    if not linhas:
        raise AppError(
            codigo=CARRINHO_VAZIO,
            mensagem="Sua seleção está vazia. Adicione produtos antes de enviar.",
            status_code=400,
        )

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

    return SelecaoSaida(
        itens=itens,
        mensagem_whatsapp=mensagem,
        link_whatsapp=montar_link(mensagem),
    )
