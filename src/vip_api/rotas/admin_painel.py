"""O roteador PROTEGIDO do painel (tarefa 54).

Toda rota administrativa entra aqui. A proteção está no GRUPO, uma vez, e não
rota a rota: com `dependencies=[Depends(exigir_admin)]` no `APIRouter`, quem
acrescentar o CRUD de produto amanhã não tem como esquecer de proteger — a
rota nasce protegida por estar neste arquivo. Decorar rota a rota é o desenho
em que um `@roteador.delete` sem `Depends` deixa o catálogo aberto para
qualquer pessoa apagar, e ninguém percebe até perceber.

A ÚNICA exceção é o par de rotas de sessão (`POST` e `DELETE /admin/sessao`),
que mora em rotas/admin_sessao.py: exigir sessão de admin para ABRIR a sessão
de admin tranca o painel para todo mundo, inclusive para quem tem a senha
certa. A exceção está declarada também no teste de varredura
(testes/teste_protecao_admin.py), que falha se alguém acrescentar outra.
"""

from fastapi import APIRouter, Depends

from vip_api.dependencias.sessao_admin import (
    AdminAutenticado,
    admin_autenticado,
    exigir_admin,
)
from vip_api.esquemas.admin import AdminEu
from vip_api.rotas.admin_acesso import roteador_acesso, roteador_configuracao
from vip_api.rotas.admin_catalogo import (
    roteador_banners,
    roteador_categorias,
    roteador_cores,
    roteador_marcas,
)
from vip_api.rotas.admin_imagens import roteador as roteador_imagens
from vip_api.rotas.admin_relatorios import (
    roteador_clientes,
    roteador_destaques,
    roteador_resumo,
    roteador_selecoes,
)
from vip_api.rotas.admin_produtos import roteador as roteador_produtos
from vip_api.rotas.admin_revisao import roteador as roteador_revisao

roteador = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(exigir_admin)])

# As rotas de produto entram por aqui, e é a inclusão neste roteador — e só
# ela — que as protege. Roteador novo do painel se pendura na mesma linha.
roteador.include_router(roteador_produtos)
roteador.include_router(roteador_imagens)
roteador.include_router(roteador_marcas)
roteador.include_router(roteador_cores)
roteador.include_router(roteador_categorias)
roteador.include_router(roteador_banners)
roteador.include_router(roteador_destaques)
roteador.include_router(roteador_resumo)
roteador.include_router(roteador_selecoes)
roteador.include_router(roteador_clientes)
roteador.include_router(roteador_revisao)
# Controle de entrada da loja (seção 05). Aqui, no grupo protegido — e só
# aqui: o portão da loja (dependencias/acesso.py) nunca pega o painel.
roteador.include_router(roteador_acesso)
roteador.include_router(roteador_configuracao)


@roteador.get("/eu", response_model=AdminEu)
def eu(atual: AdminAutenticado = Depends(admin_autenticado)) -> AdminEu:
    """O painel chama esta rota ao abrir para saber se a sessão ainda vale.

    `admin_autenticado` aparece de novo aqui, no parâmetro, só para trazer o
    administrador — o FastAPI reaproveita o que a dependência do grupo já
    resolveu nesta requisição.
    """
    return AdminEu.model_validate(atual.administrador)
