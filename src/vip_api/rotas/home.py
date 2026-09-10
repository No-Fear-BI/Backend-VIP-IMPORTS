"""GET /api/v1/home — a página inicial inteira numa resposta só."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.esquemas.home import Home
from vip_api.servicos.home import montar_home

roteador = APIRouter(tags=["home"])


@roteador.get("/home", response_model=Home)
def home(sessao: Session = Depends(obter_sessao)) -> Home:
    return montar_home(sessao)
