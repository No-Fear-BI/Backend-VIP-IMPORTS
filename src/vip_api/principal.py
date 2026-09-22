"""Ponto de entrada da aplicação. `uvicorn vip_api.principal:app`."""

import logging
import mimetypes
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

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

# Imagem enviada pelo painel (produtos e banners) — disco local servido pela
# própria API. O caminho do mount é o PATH de IMAGENS_URL_BASE, não um
# "/midia" fixo repetido aqui: mudar a variável de ambiente já move os dois
# juntos, em vez de precisar lembrar de editar aqui também.
#
# `.webp` nem sempre está no /etc/mime.types da imagem base (python:3.12-slim
# não tem), e sem isso o StaticFiles serve toda foto processada como
# text/plain — o navegador ainda costuma renderizar por sniffing, mas é
# errado e alguns contextos (CORS, download forçado) dependem do cabeçalho
# certo. Registrar aqui, antes do mount, garante o tipo certo não importa o
# que o sistema operacional da imagem já tenha.
mimetypes.add_type("image/webp", ".webp")
Path(configuracao.IMAGENS_DIR).mkdir(parents=True, exist_ok=True)
app.mount(
    urlsplit(configuracao.IMAGENS_URL_BASE).path or "/midia",
    StaticFiles(directory=configuracao.IMAGENS_DIR),
    name="midia",
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
