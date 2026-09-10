"""Ponto de entrada da aplicação. `uvicorn vip_api.principal:app`."""

import logging

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from vip_api.configuracao import configuracao
from vip_api.erros.excecoes import AppError
from vip_api.erros.manipuladores import (
    tratar_app_error,
    tratar_erro_validacao,
    tratar_excecao_nao_tratada,
)
from vip_api.rotas.clientes import roteador as roteador_clientes
from vip_api.rotas.favoritos import roteador as roteador_favoritos
from vip_api.rotas.home import roteador as roteador_home
from vip_api.rotas.navegacao import roteador as roteador_navegacao
from vip_api.rotas.produtos import roteador as roteador_produtos
from vip_api.rotas.saude import roteador as roteador_saude

logging.basicConfig(level=configuracao.NIVEL_LOG)

app = FastAPI(
    title="API VIP Imports",
    version="1.0.0",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=configuracao.ORIGENS_PERMITIDAS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ordem não importa aqui: Starlette escolhe o manipulador mais específico da
# MRO da exceção levantada, não o primeiro registrado.
app.add_exception_handler(AppError, tratar_app_error)
app.add_exception_handler(RequestValidationError, tratar_erro_validacao)
app.add_exception_handler(Exception, tratar_excecao_nao_tratada)

# Todo roteador futuro (produtos, clientes, admin...) entra registrado aqui,
# não direto em `app` — é o que garante o prefixo /api/v1 em tudo.
roteador_v1 = APIRouter(prefix="/api/v1")
roteador_v1.include_router(roteador_saude)
roteador_v1.include_router(roteador_produtos)
roteador_v1.include_router(roteador_navegacao)
roteador_v1.include_router(roteador_home)
roteador_v1.include_router(roteador_clientes)
roteador_v1.include_router(roteador_favoritos)

app.include_router(roteador_v1)
