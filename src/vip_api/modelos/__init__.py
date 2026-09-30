"""Modelos SQLAlchemy — espelho das migrações já aplicadas.

Importar este pacote registra TODAS as tabelas em `Base.metadata`. O
`migracoes/env.py` depende disso para o `alembic check` enxergar o schema
inteiro; se um modelo novo não for importado aqui, ele some da comparação.
"""

from vip_api.modelos.acesso import AcessoConfig, AcessoSolicitacao
from vip_api.modelos.acesso_tentativas import TentativaAcesso
from vip_api.modelos.admin import Administrador, AdminSessao
from vip_api.modelos.revisao import DecisaoRevisao
from vip_api.modelos.produto_destinos import ProdutoCategoriaAdicional
from vip_api.modelos.base import Base
from vip_api.modelos.catalogo import (
    Banner,
    Categoria,
    Marca,
    Produto,
    ProdutoImagem,
    ProdutoVariacao,
)
from vip_api.modelos.cliente import Carrinho, CarrinhoItem, Cliente, ClienteSessao, Favorito
from vip_api.modelos.selecao import Selecao, SelecaoItem

__all__ = [
    "AcessoConfig",
    "AcessoSolicitacao",
    "AdminSessao",
    "Administrador",
    "Banner",
    "Base",
    "Carrinho",
    "CarrinhoItem",
    "Categoria",
    "Cliente",
    "ClienteSessao",
    "Favorito",
    "Marca",
    "Produto",
    "ProdutoImagem",
    "ProdutoVariacao",
    "Selecao",
    "SelecaoItem",
    "TentativaAcesso",
]
