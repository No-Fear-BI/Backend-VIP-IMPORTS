"""Favoritos do cliente da sessão."""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.dependencias.sessao_cliente import ClienteAutenticado, cliente_autenticado
from vip_api.esquemas.cliente import FavoritoEntrada
from vip_api.esquemas.produto import ProdutoItem
from vip_api.servicos.favoritos import adicionar_favorito, listar_favoritos, remover_favorito

roteador = APIRouter(tags=["favoritos"])


@roteador.get("/favoritos", response_model=list[ProdutoItem])
def listar(
    atual: ClienteAutenticado = Depends(cliente_autenticado),
    sessao: Session = Depends(obter_sessao),
) -> list[ProdutoItem]:
    return listar_favoritos(sessao, atual.cliente.id)


# 200 com corpo em vez de 204: a seção 1.4 do contrato lista 200 para
# atualização e exclusão bem-sucedidas, e o cliente HTTP do frontend desempacota
# JSON em toda resposta — 204 não tem corpo e quebraria esse caminho.
# Favoritar não devolve 201 porque favoritar duas vezes não cria nada: a
# resposta é a mesma nos dois casos, e o frontend não deve ramificar por status.


@roteador.post("/favoritos")
def adicionar(
    corpo: FavoritoEntrada,
    atual: ClienteAutenticado = Depends(cliente_autenticado),
    sessao: Session = Depends(obter_sessao),
) -> dict[str, bool]:
    adicionar_favorito(sessao, atual.cliente.id, corpo.produto_id)
    return {"ok": True}


@roteador.delete("/favoritos/{produtoId}")
def remover(
    produto_id: int = Path(alias="produtoId"),
    atual: ClienteAutenticado = Depends(cliente_autenticado),
    sessao: Session = Depends(obter_sessao),
) -> dict[str, bool]:
    remover_favorito(sessao, atual.cliente.id, produto_id)
    return {"ok": True}
