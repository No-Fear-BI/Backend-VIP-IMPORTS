"""Controle de entrada, lado do painel (seção 05): fila, decisão e mensagem.

Incluído no roteador protegido de admin_painel.py, sem proteção própria. E
NUNCA atrás do portão da loja: é daqui que a equipe libera quem está na fila.
"""

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.dependencias.sessao_admin import AdminAutenticado, admin_autenticado
from vip_api.esquemas.acesso import (
    ConfiguracaoAcesso,
    ConfiguracaoAcessoEntrada,
    DecidirAcessoEntrada,
    DecisaoAcesso,
    SolicitacaoFila,
)
from vip_api.esquemas.base import Pagina
from vip_api.servicos.acesso import (
    POR_PAGINA_MAXIMO,
    POR_PAGINA_PADRAO,
    decidir_acesso,
    definir_configuracao,
    listar_fila,
)

roteador_acesso = APIRouter(prefix="/acesso", tags=["admin"])
roteador_configuracao = APIRouter(prefix="/configuracao", tags=["admin"])


@roteador_acesso.get("/fila", response_model=Pagina[SolicitacaoFila])
def fila(
    sessao: Session = Depends(obter_sessao),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(
        POR_PAGINA_PADRAO, alias="porPagina", description=f"Máximo {POR_PAGINA_MAXIMO}."
    ),
) -> Pagina[SolicitacaoFila]:
    return listar_fila(sessao, pagina, por_pagina)


@roteador_acesso.patch("/{clienteId}", response_model=DecisaoAcesso)
def decidir(
    corpo: DecidirAcessoEntrada,
    cliente_id: int = Path(alias="clienteId"),
    atual: AdminAutenticado = Depends(admin_autenticado),
    sessao: Session = Depends(obter_sessao),
) -> DecisaoAcesso:
    """Aprova, recusa ou revoga. Por CLIENTE, não por solicitação: há no
    máximo um pedido pendente por cliente, e revogar não tem pedido nenhum."""
    return decidir_acesso(
        sessao, cliente_id, corpo.situacao, corpo.motivo, atual.administrador.id
    )


@roteador_configuracao.patch("/acesso", response_model=ConfiguracaoAcesso)
def configurar(
    corpo: ConfiguracaoAcessoEntrada,
    atual: AdminAutenticado = Depends(admin_autenticado),
    sessao: Session = Depends(obter_sessao),
) -> ConfiguracaoAcesso:
    """Não liga nem desliga o portão: a loja é sempre fechada. Na prática só
    grava a mensagem de bloqueio. `modo: "aprovacao"` é aceito e não muda nada;
    'aberto' e 'senha_compartilhada' são recusados com 400."""
    return definir_configuracao(sessao, corpo, atual.administrador.id)
