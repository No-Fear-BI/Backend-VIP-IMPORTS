"""Carrinho do cliente.

NÃO existe quantidade. O contrato não tem esse campo em lugar nenhum: isto é
catálogo de seleção, não loja com estoque. O mesmo produto com variações
diferentes são dois itens; o mesmo produto com a mesma variação é um item só —
regra que o UNIQUE (carrinho_id, produto_id, variacao_id) NULLS NOT DISTINCT
já sustenta no banco.

(A coluna `quantidade` existe na tabela desde a migração 0001, com default 1.
Nenhuma rota lê ou escreve nela. Está documentado no relatório da Fatia 3 como
coluna a remover quando houver outra migração de catálogo.)
"""

from dataclasses import dataclass

from sqlalchemy import and_, delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from vip_api.erros.codigos import (
    ITEM_NAO_ENCONTRADO,
    PRODUTO_NAO_ENCONTRADO,
    VARIACAO_INVALIDA,
)
from vip_api.erros.excecoes import AppError
from vip_api.esquemas.carrinho import CarrinhoItemSaida, ItemIgnorado
from vip_api.esquemas.produto import Capa, Referencia, VariacaoDetalhe
from vip_api.modelos.catalogo import (
    Categoria,
    Colecao,
    Marca,
    Produto,
    ProdutoImagem,
    ProdutoVariacao,
)
from vip_api.modelos.cliente import Carrinho, CarrinhoItem

MOTIVO_PRODUTO_INDISPONIVEL = "PRODUTO_INDISPONIVEL"


def obter_ou_criar_carrinho(sessao: Session, cliente_id: int) -> Carrinho:
    """Um carrinho por cliente — o índice único parcial uq_carrinhos_cliente_ativo
    garante isso no banco, então não existe o caso de "qual dos dois é o bom"."""
    carrinho = sessao.scalar(select(Carrinho).where(Carrinho.cliente_id == cliente_id))
    if carrinho is None:
        carrinho = Carrinho(cliente_id=cliente_id)
        sessao.add(carrinho)
        sessao.commit()
        sessao.refresh(carrinho)
    return carrinho


def _consulta_de_itens(carrinho_id: int):
    """Item do carrinho = produto no formato da listagem + variação escolhida.

    Tudo numa consulta só: marca, categoria, coleção, capa e variação entram
    por JOIN, não por uma consulta por item.
    """
    return (
        select(
            CarrinhoItem.id.label("item_id"),
            CarrinhoItem.criado_em.label("adicionado_em"),
            Produto.id,
            Produto.codigo,
            Produto.nome,
            Produto.status,
            Produto.destaque,
            Marca.nome.label("marca_nome"),
            Marca.slug.label("marca_slug"),
            Categoria.nome.label("categoria_nome"),
            Categoria.slug.label("categoria_slug"),
            Colecao.nome.label("colecao_nome"),
            Colecao.slug.label("colecao_slug"),
            ProdutoImagem.url.label("capa_url"),
            ProdutoImagem.alt.label("capa_alt"),
            ProdutoVariacao.id.label("variacao_id"),
            ProdutoVariacao.tipo.label("variacao_tipo"),
            ProdutoVariacao.valor.label("variacao_valor"),
            ProdutoVariacao.disponivel.label("variacao_disponivel"),
        )
        .join(Produto, Produto.id == CarrinhoItem.produto_id)
        .join(Marca, Marca.id == Produto.marca_id)
        .join(Categoria, Categoria.id == Produto.categoria_id)
        .join(Colecao, Colecao.id == Produto.colecao_id)
        .outerjoin(
            ProdutoImagem,
            and_(ProdutoImagem.produto_id == Produto.id, ProdutoImagem.capa.is_(True)),
        )
        .outerjoin(ProdutoVariacao, ProdutoVariacao.id == CarrinhoItem.variacao_id)
        .where(
            CarrinhoItem.carrinho_id == carrinho_id,
            # Produto oculto some do carrinho, mas a LINHA continua no banco:
            # se o admin voltar a exibir, o item reaparece. Mesma regra dos
            # favoritos.
            Produto.status != "oculto",
        )
        .order_by(CarrinhoItem.criado_em.asc(), CarrinhoItem.id.asc())
    )


def _montar_item(linha) -> CarrinhoItemSaida:
    return CarrinhoItemSaida(
        item_id=linha.item_id,
        id=linha.id,
        codigo=linha.codigo,
        nome=linha.nome,
        status=linha.status,
        destaque=linha.destaque,
        marca=Referencia(nome=linha.marca_nome, slug=linha.marca_slug),
        categoria=Referencia(nome=linha.categoria_nome, slug=linha.categoria_slug),
        colecao=Referencia(nome=linha.colecao_nome, slug=linha.colecao_slug),
        capa=Capa(url=linha.capa_url, alt=linha.capa_alt) if linha.capa_url else None,
        variacao=(
            VariacaoDetalhe(
                id=linha.variacao_id,
                tipo=linha.variacao_tipo,
                valor=linha.variacao_valor,
                disponivel=linha.variacao_disponivel,
            )
            if linha.variacao_id
            else None
        ),
    )


def listar_itens(sessao: Session, cliente_id: int) -> list[CarrinhoItemSaida]:
    carrinho = obter_ou_criar_carrinho(sessao, cliente_id)
    linhas = sessao.execute(_consulta_de_itens(carrinho.id)).all()
    return [_montar_item(linha) for linha in linhas]


@dataclass(frozen=True)
class _Validacao:
    produto_id: int | None
    variacao_id: int | None
    motivo: str | None = None
    mensagem: str | None = None


def _validar(sessao: Session, produto_id: int, variacao_id: int | None) -> _Validacao:
    """Confere produto e variação sem levantar — quem chama decide se vira erro
    (POST) ou entra na lista de ignorados (migrar)."""
    visivel = sessao.scalar(
        select(Produto.id).where(Produto.id == produto_id, Produto.status != "oculto")
    )
    if visivel is None:
        existe = sessao.scalar(select(Produto.id).where(Produto.id == produto_id))
        return _Validacao(
            produto_id=produto_id,
            variacao_id=variacao_id,
            motivo=MOTIVO_PRODUTO_INDISPONIVEL if existe else PRODUTO_NAO_ENCONTRADO,
            mensagem=(
                "Este produto não está mais disponível."
                if existe
                else "Produto não encontrado."
            ),
        )

    if variacao_id is not None:
        # A variação tem que ser DO PRODUTO informado: sem esta checagem dá
        # para montar um item com o tamanho de outro produto.
        pertence = sessao.scalar(
            select(ProdutoVariacao.id).where(
                ProdutoVariacao.id == variacao_id,
                ProdutoVariacao.produto_id == produto_id,
            )
        )
        if pertence is None:
            return _Validacao(
                produto_id=produto_id,
                variacao_id=variacao_id,
                motivo=VARIACAO_INVALIDA,
                mensagem="A variação escolhida não pertence a este produto.",
            )

    return _Validacao(produto_id=produto_id, variacao_id=variacao_id)


def adicionar_item(
    sessao: Session, cliente_id: int, produto_id: int, variacao_id: int | None
) -> None:
    validacao = _validar(sessao, produto_id, variacao_id)
    if validacao.motivo == VARIACAO_INVALIDA:
        raise AppError(
            codigo=VARIACAO_INVALIDA,
            mensagem=validacao.mensagem,
            status_code=400,
            campos={"variacaoId": validacao.mensagem},
        )
    if validacao.motivo is not None:
        raise AppError(
            codigo=PRODUTO_NAO_ENCONTRADO, mensagem="Produto não encontrado.", status_code=404
        )

    carrinho = obter_ou_criar_carrinho(sessao, cliente_id)
    # Mesmo produto + mesma variação já no carrinho: não é erro, é sem efeito.
    sessao.execute(
        insert(CarrinhoItem)
        .values(carrinho_id=carrinho.id, produto_id=produto_id, variacao_id=variacao_id)
        .on_conflict_do_nothing(constraint="uq_carrinho_itens_carrinho_produto_variacao")
    )
    sessao.commit()


def _item_do_cliente(sessao: Session, cliente_id: int, item_id: int) -> CarrinhoItem:
    """Carrega o item conferindo o dono. Item de outro cliente responde 404, o
    mesmo que item inexistente: confirmar que o id existe já entregaria
    informação de outra conta."""
    item = sessao.scalar(
        select(CarrinhoItem)
        .join(Carrinho, Carrinho.id == CarrinhoItem.carrinho_id)
        .where(CarrinhoItem.id == item_id, Carrinho.cliente_id == cliente_id)
    )
    if item is None:
        raise AppError(
            codigo=ITEM_NAO_ENCONTRADO,
            mensagem="Item do carrinho não encontrado.",
            status_code=404,
        )
    return item


def trocar_variacao(
    sessao: Session, cliente_id: int, item_id: int, variacao_id: int | None
) -> None:
    item = _item_do_cliente(sessao, cliente_id, item_id)

    validacao = _validar(sessao, item.produto_id, variacao_id)
    if validacao.motivo == VARIACAO_INVALIDA:
        raise AppError(
            codigo=VARIACAO_INVALIDA,
            mensagem=validacao.mensagem,
            status_code=400,
            campos={"variacaoId": validacao.mensagem},
        )

    ja_existe = sessao.scalar(
        select(CarrinhoItem.id).where(
            CarrinhoItem.carrinho_id == item.carrinho_id,
            CarrinhoItem.produto_id == item.produto_id,
            CarrinhoItem.variacao_id.is_(variacao_id)
            if variacao_id is None
            else CarrinhoItem.variacao_id == variacao_id,
            CarrinhoItem.id != item.id,
        )
    )
    if ja_existe is not None:
        # A troca colidiu com um item que já existia. Como "mesmo produto e
        # mesma variação é um item só", os dois viram um: some o que estava
        # sendo alterado e fica o que já estava lá.
        sessao.execute(delete(CarrinhoItem).where(CarrinhoItem.id == item.id))
    else:
        sessao.execute(
            update(CarrinhoItem)
            .where(CarrinhoItem.id == item.id)
            .values(variacao_id=variacao_id)
        )
    sessao.commit()


def remover_item(sessao: Session, cliente_id: int, item_id: int) -> None:
    item = _item_do_cliente(sessao, cliente_id, item_id)
    sessao.execute(delete(CarrinhoItem).where(CarrinhoItem.id == item.id))
    sessao.commit()


def migrar_itens(
    sessao: Session, cliente_id: int, itens: list[tuple[int, int | None]]
) -> tuple[list[CarrinhoItemSaida], list[ItemIgnorado]]:
    """Move o carrinho do visitante anônimo (localStorage) para a conta.

    Se o carrinho esvaziar na identificação, perde-se a venda — é o erro mais
    comum deste fluxo. Por isso item inválido não derruba a migração inteira:
    ele volta em `ignorados` com o motivo, para a tela poder dizer "2 itens não
    estão mais disponíveis" em vez de sumir com eles em silêncio.

    Tudo numa transação só: ou entra o que dá, ou não entra nada.
    """
    carrinho = obter_ou_criar_carrinho(sessao, cliente_id)
    ignorados: list[ItemIgnorado] = []

    for produto_id, variacao_id in itens:
        validacao = _validar(sessao, produto_id, variacao_id)
        if validacao.motivo is not None:
            ignorados.append(
                ItemIgnorado(
                    produto_id=produto_id,
                    variacao_id=variacao_id,
                    motivo=validacao.motivo,
                    mensagem=validacao.mensagem,
                )
            )
            continue

        # Regra 1: mesmo produto + mesma variação já na conta -> mantém o que
        # já estava, sem duplicar e sem erro.
        # Regra 2: mesmo produto + variação diferente -> o UNIQUE não casa,
        # entra como item novo, e os dois ficam.
        sessao.execute(
            insert(CarrinhoItem)
            .values(
                carrinho_id=carrinho.id, produto_id=produto_id, variacao_id=variacao_id
            )
            .on_conflict_do_nothing(
                constraint="uq_carrinho_itens_carrinho_produto_variacao"
            )
        )

    sessao.commit()

    linhas = sessao.execute(_consulta_de_itens(carrinho.id)).all()
    return [_montar_item(linha) for linha in linhas], ignorados
