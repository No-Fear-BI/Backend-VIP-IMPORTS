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
from vip_api.rotas.admin_painel import roteador as roteador_admin_painel
from vip_api.rotas.admin_sessao import roteador as roteador_admin_sessao
from vip_api.rotas.carrinho import roteador as roteador_carrinho
from vip_api.rotas.clientes import roteador as roteador_clientes
from vip_api.rotas.favoritos import roteador as roteador_favoritos
from vip_api.rotas.home import roteador as roteador_home
from vip_api.rotas.navegacao import roteador as roteador_navegacao
from vip_api.rotas.produtos import roteador as roteador_produtos
from vip_api.rotas.produtos_aprovados import roteador as roteador_produtos_aprovados
from vip_api.rotas.selecoes import roteador as roteador_selecoes
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
roteador_v1.include_router(roteador_produtos_aprovados)
roteador_v1.include_router(roteador_navegacao)
roteador_v1.include_router(roteador_home)
roteador_v1.include_router(roteador_clientes)
roteador_v1.include_router(roteador_favoritos)
roteador_v1.include_router(roteador_carrinho)
roteador_v1.include_router(roteador_selecoes)
# Login e logout ficam FORA do roteador protegido: exigir sessão de admin
# para abrir a sessão de admin trancaria o painel para quem tem a senha
# certa. São as duas únicas rotas /admin sem proteção, e a exceção está
# declarada em testes/teste_protecao_admin.py.
roteador_v1.include_router(roteador_admin_sessao)
# Tudo o mais do painel entra por aqui, já protegido pelo grupo.
roteador_v1.include_router(roteador_admin_painel)

app.include_router(roteador_v1)
