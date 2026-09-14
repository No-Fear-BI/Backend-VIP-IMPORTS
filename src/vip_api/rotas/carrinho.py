"""Carrinho do cliente da sessão. Sem quantidade — ver servicos/carrinho.py."""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.dependencias.sessao_cliente import ClienteAutenticado, cliente_autenticado
from vip_api.esquemas.carrinho import (
    CarrinhoItemEntrada,
    CarrinhoItemSaida,
    MigracaoSaida,
    MigrarEntrada,
    TrocaVariacaoEntrada,
)
from vip_api.servicos.carrinho import (
    Par,
    adicionar_item,
    listar_itens,
    migrar_itens,
    remover_item,
    trocar_variacao,
)

roteador = APIRouter(tags=["carrinho"])


@roteador.get("/carrinho", response_model=list[CarrinhoItemSaida])
def listar(
    atual: ClienteAutenticado = Depends(cliente_autenticado),
    sessao: Session = Depends(obter_sessao),
) -> list[CarrinhoItemSaida]:
    return listar_itens(sessao, atual.cliente.id)


@roteador.post("/carrinho")
def adicionar(
    corpo: CarrinhoItemEntrada,
    atual: ClienteAutenticado = Depends(cliente_autenticado),
    sessao: Session = Depends(obter_sessao),
) -> dict:
    adicionar_item(
        sessao,
        atual.cliente.id,
        corpo.produto_id,
        Par(corpo.variacao_tamanho_id, corpo.variacao_cor_id),
    )
    return {"ok": True}


@roteador.patch("/carrinho/{itemId}")
def trocar(
    corpo: TrocaVariacaoEntrada,
    item_id: int = Path(alias="itemId"),
    atual: ClienteAutenticado = Depends(cliente_autenticado),
    sessao: Session = Depends(obter_sessao),
) -> dict:
    trocar_variacao(
        sessao,
        atual.cliente.id,
        item_id,
        Par(corpo.variacao_tamanho_id, corpo.variacao_cor_id),
    )
    return {"ok": True}


@roteador.delete("/carrinho/{itemId}")
def remover(
    item_id: int = Path(alias="itemId"),
    atual: ClienteAutenticado = Depends(cliente_autenticado),
    sessao: Session = Depends(obter_sessao),
) -> dict:
    remover_item(sessao, atual.cliente.id, item_id)
    return {"ok": True}


@roteador.post("/carrinho/migrar", response_model=MigracaoSaida)
def migrar(
    corpo: MigrarEntrada,
    atual: ClienteAutenticado = Depends(cliente_autenticado),
    sessao: Session = Depends(obter_sessao),
) -> MigracaoSaida:
    itens, ignorados = migrar_itens(
        sessao,
        atual.cliente.id,
        [(i.produto_id, Par(i.variacao_tamanho_id, i.variacao_cor_id)) for i in corpo.itens],
    )
    return MigracaoSaida(itens=itens, ignorados=ignorados)
