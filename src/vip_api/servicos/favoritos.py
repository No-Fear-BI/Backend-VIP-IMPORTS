"""Favoritos do cliente."""

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from vip_api.erros.codigos import PRODUTO_NAO_ENCONTRADO
from vip_api.erros.excecoes import AppError
from vip_api.esquemas.produto import ProdutoItem
from vip_api.modelos.catalogo import Produto
from vip_api.modelos.cliente import Favorito
from vip_api.servicos.catalogo import (
    _colunas_do_produto,
    _envolver_com_juncoes,
    _montar_item,
)


def listar_favoritos(sessao: Session, cliente_id: int) -> list[ProdutoItem]:
    """Produto que virou `oculto` some daqui, mas a LINHA do favorito continua
    no banco: se o admin voltar a exibir o produto, o favorito reaparece
    sozinho. Apagar a linha seria uma decisão do admin virando perda de dado
    do cliente."""
    interna = (
        select(*_colunas_do_produto(), Favorito.criado_em.label("favoritado_em"))
        .join(Favorito, Favorito.produto_id == Produto.id)
        .where(Favorito.cliente_id == cliente_id, Produto.status != "oculto")
        .order_by(Favorito.criado_em.desc(), Produto.id.desc())
    )
    p = interna.subquery("p")
    # A capa vem no mesmo SELECT, como na listagem — nada de uma consulta por
    # favorito para buscar a imagem.
    linhas = sessao.execute(
        _envolver_com_juncoes(p).order_by(p.c.favoritado_em.desc(), p.c.id.desc())
    ).all()
    return [_montar_item(linha) for linha in linhas]


def adicionar_favorito(sessao: Session, cliente_id: int, produto_id: int) -> None:
    """Favoritar duas vezes não é erro, é sem efeito — daí o DO NOTHING."""
    existe = sessao.scalar(
        select(Produto.id).where(Produto.id == produto_id, Produto.status != "oculto")
    )
    if existe is None:
        raise AppError(
            codigo=PRODUTO_NAO_ENCONTRADO,
            mensagem="Produto não encontrado.",
            status_code=404,
        )

    sessao.execute(
        insert(Favorito)
        .values(cliente_id=cliente_id, produto_id=produto_id)
        .on_conflict_do_nothing(constraint="pk_favoritos")
    )
    sessao.commit()


def remover_favorito(sessao: Session, cliente_id: int, produto_id: int) -> None:
    sessao.execute(
        delete(Favorito).where(
            Favorito.cliente_id == cliente_id, Favorito.produto_id == produto_id
        )
    )
    sessao.commit()
