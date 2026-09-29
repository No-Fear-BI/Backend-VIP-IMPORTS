"""O PORTÃO da loja: controle de entrada da seção 05, modo aprovação.

Dependência de GRUPO, igual à proteção do painel (rotas/admin_painel.py): vai
em `include_router(..., dependencies=[...])` no vip_api/principal.py, uma vez
por roteador de catálogo, e toda rota que nascer num desses roteadores já nasce
atrás do portão.

Ficam FORA, de propósito, e isso é conferido por varredura em
testes/teste_acesso_loja.py:
- /acesso/* — é por ali que o barrado descobre por que foi barrado e pede
  liberação. Portão na porta do portão tranca todo mundo.
- /clientes/* — identificar é o primeiro passo do pedido; eu/sair mexem só na
  própria conta e não mostram catálogo.
- /health — o healthcheck do Docker não tem sessão de cliente.
- TODO o /admin/* — a equipe não tem sessão de cliente; se o portão pegasse o
  painel, o administrador não conseguiria nem liberar a fila.

O portão custa uma leitura por chave primária de uma linha só (acesso_config)
por requisição. A loja é sempre fechada; sem a linha, também conta como fechado.
"""

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.dependencias.sessao_cliente import NOME_COOKIE
from vip_api.erros.codigos import ACESSO_PENDENTE, ACESSO_RECUSADO, NAO_IDENTIFICADO
from vip_api.erros.excecoes import AppError
from vip_api.servicos.acesso import (
    MENSAGEM_PADRAO_PENDENTE,
    MENSAGEM_PADRAO_RECUSADO,
    cliente_liberado,
    exige_aprovacao,
    obter_config,
)
from vip_api.servicos.cliente import buscar_sessao_valida


def exigir_acesso_liberado(requisicao: Request, sessao: Session = Depends(obter_sessao)) -> None:
    """401 sem sessão de cliente (o frontend manda identificar); 403 com
    sessão, mas sem aprovação — ACESSO_PENDENTE ou ACESSO_RECUSADO, com a
    mensagem de bloqueio do painel em `erro.mensagem`.

    Não renova sessão nem marca último acesso: isso é da `cliente_autenticado`,
    que as rotas de conta (favoritos, carrinho, seleções) continuam chamando.
    """
    config = obter_config(sessao)
    if not exige_aprovacao(config):
        return

    encontrado = buscar_sessao_valida(sessao, requisicao.cookies.get(NOME_COOKIE, ""))
    if encontrado is None:
        raise AppError(
            codigo=NAO_IDENTIFICADO,
            mensagem="Identifique-se para ver a loja.",
            status_code=401,
        )

    cliente, _sessao_cliente = encontrado
    if cliente_liberado(cliente):
        return

    recusado = cliente.acesso_status == "recusado"
    raise AppError(
        codigo=ACESSO_RECUSADO if recusado else ACESSO_PENDENTE,
        mensagem=config.mensagem_bloqueio
        or (MENSAGEM_PADRAO_RECUSADO if recusado else MENSAGEM_PADRAO_PENDENTE),
        status_code=403,
        detalhes={"situacao": cliente.acesso_status},
    )
