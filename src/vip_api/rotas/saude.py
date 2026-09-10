"""GET /api/v1/health — prova que o caminho inteiro funciona, do código ao
navegador. De propósito SEM checagem de banco, versão ou uptime: isso é
monitoramento (Dev 4 decide o formato), e misturar as duas coisas faz a rota
cair por um motivo que não é "o processo está de pé"."""

from fastapi import APIRouter

roteador = APIRouter(tags=["saude"])


@roteador.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}
