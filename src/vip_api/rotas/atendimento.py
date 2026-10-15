"""GET /api/v1/atendimento/widget — o que a loja precisa para mostrar o chat.

Atrás do portão de acesso, como o catálogo: só quem foi aprovado conversa com
o agente, porque o agente consulta o catálogo (decisão de 15/10/2026). Devolve
só dado público (o endereço do widget.js e a chave pública do canal, `wk_…`),
nunca a key.

Chat desligado (sem key, sem canal, Burnwood fora do ar) é resposta normal com
os dois campos nulos: a loja simplesmente não carrega o chat.
"""

from fastapi import APIRouter

from vip_api.esquemas.atendimento import WidgetAtendimento
from vip_api.servicos.burnwood import configuracao_do_widget

roteador = APIRouter(prefix="/atendimento", tags=["atendimento"])


@roteador.get("/widget", response_model=WidgetAtendimento)
def widget() -> WidgetAtendimento:
    dados = configuracao_do_widget()
    if dados is None:
        return WidgetAtendimento(widget_url=None, chave_canal=None)
    return WidgetAtendimento(**dados)
