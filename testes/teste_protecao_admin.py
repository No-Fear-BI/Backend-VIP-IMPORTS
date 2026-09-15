"""Varredura: NENHUMA rota /admin fica aberta.

Este teste não tem lista de rotas escrita à mão — ele lê o próprio roteador do
FastAPI (`app.routes`), pega tudo sob /api/v1/admin e confere as três portas
em cada método de cada rota. É o que faz o CRUD de amanhã nascer coberto: quem
acrescentar rota sem pendurar no roteador protegido vê este teste ficar
vermelho, com o nome da rota na mensagem.

A lista de exceções abaixo é a única forma de uma rota /admin ficar sem
proteção. Ela é curta de propósito e mora aqui, no teste, para que acrescentar
uma linha nela apareça no diff do PR e alguém pergunte por quê.
"""

import re

import pytest

from testes.rotas_registradas import eh_do_painel, rotas_registradas
from vip_api.principal import app

PREFIXO = "/api/v1/admin"

# As DUAS rotas de sessão. Exigir sessão de admin para ABRIR a sessão de admin
# tranca o painel para todo mundo, inclusive para quem tem a senha certa; e o
# logout precisa funcionar com a sessão já expirada, senão o cookie morto fica
# no navegador sem jeito de sair.
EXCECOES = {
    ("POST", f"{PREFIXO}/sessao"),
    ("DELETE", f"{PREFIXO}/sessao"),
}

NEGADO = (401, 403)


def rotas_do_painel(aplicacao=app) -> list[tuple[str, str]]:
    """Tudo sob o prefixo do painel, lido do roteador (testes/rotas_registradas.py)."""
    return [
        (metodo, caminho)
        for metodo, caminho, _rota in rotas_registradas(aplicacao)
        if eh_do_painel(caminho, PREFIXO)
    ]


def protegidas() -> list[tuple[str, str]]:
    return [rota for rota in rotas_do_painel() if rota not in EXCECOES]


def _com_valores(caminho: str) -> str:
    """Troca `{produtoId}` por um valor qualquer. O teste não quer saber se o
    id existe — 404 também é sinal de que passou da porta."""
    return re.sub(r"\{[^}]+\}", "1", caminho)


def _chamar(http, metodo: str, caminho: str):
    # Corpo vazio nos métodos que aceitam corpo: a validação devolveria 422, e
    # 422 já prova que a requisição passou pela autenticação — as dependências
    # do roteador rodam antes da validação do corpo.
    extras = {"json": {}} if metodo in {"POST", "PUT", "PATCH"} else {}
    return http.request(metodo, _com_valores(caminho), **extras)


def teste_existe_rota_de_painel_para_varrer():
    """Guarda contra o teste virar verde por não achar rota nenhuma — se o
    prefixo mudar, é aqui que aparece."""
    assert protegidas(), f"nenhuma rota encontrada sob {PREFIXO}"


def teste_excecoes_declaradas_existem_de_verdade():
    """Exceção que não corresponde a rota nenhuma é lixo acumulando: some da
    aplicação, fica na lista, e um dia cobre uma rota nova de mesmo nome."""
    inexistentes = EXCECOES - set(rotas_do_painel())
    assert not inexistentes, f"exceções declaradas que não existem mais: {sorted(inexistentes)}"


def teste_a_varredura_enxerga_rota_nova():
    """Prova que o coletor acha uma rota acrescentada fora do roteador
    protegido — é a parte do teste que pode quebrar em silêncio se o FastAPI
    mudar a forma de guardar os roteadores incluídos, e aí a varredura passaria
    a não varrer nada.

    Aplicação descartável: a de verdade não ganha rota de mentira nem por um
    teste.
    """
    from fastapi import APIRouter, FastAPI

    solto = APIRouter()

    @solto.get("/admin/rota_desprotegida")
    def _rota_de_mentira() -> dict:
        return {}

    versionado = APIRouter(prefix="/api/v1")
    versionado.include_router(solto)
    descartavel = FastAPI()
    descartavel.include_router(versionado)

    assert ("GET", f"{PREFIXO}/rota_desprotegida") in rotas_do_painel(descartavel)


@pytest.mark.parametrize("metodo,caminho", protegidas(), ids=lambda valor: valor)
def teste_rota_do_painel_exige_admin(metodo, caminho, sem_sessao, cliente_logado, admin_logado):
    sem_cookie = _chamar(sem_sessao, metodo, caminho)
    com_cliente = _chamar(cliente_logado, metodo, caminho)
    com_admin = _chamar(admin_logado, metodo, caminho)

    assert sem_cookie.status_code == 401, (
        f"{metodo} {caminho} respondeu {sem_cookie.status_code} sem cookie nenhum, "
        "e devia responder 401 — a rota está FORA do roteador protegido"
    )
    assert com_cliente.status_code == 403, (
        f"{metodo} {caminho} respondeu {com_cliente.status_code} com cookie de CLIENTE, "
        "e devia responder 403 — sessão de cliente não abre o painel"
    )
    assert com_admin.status_code not in NEGADO, (
        f"{metodo} {caminho} respondeu {com_admin.status_code} com cookie de ADMIN, "
        "e não devia barrar quem tem sessão válida"
    )


def teste_tabela_da_varredura(sem_sessao, cliente_logado, admin_logado, capsys):
    """Imprime a tabela completa. Rode com `pytest -s` para vê-la."""
    linhas = []
    for metodo, caminho in rotas_do_painel():
        marca = " (exceção)" if (metodo, caminho) in EXCECOES else ""
        linhas.append(
            (
                f"{metodo}{marca}",
                caminho,
                _chamar(sem_sessao, metodo, caminho).status_code,
                _chamar(cliente_logado, metodo, caminho).status_code,
                _chamar(admin_logado, metodo, caminho).status_code,
            )
        )

    with capsys.disabled():
        print(f"\n  {'MÉTODO':<20} {'ROTA':<52} {'sem cookie':>10} {'cliente':>8} {'admin':>7}")
        print(f"  {'-' * 20} {'-' * 52} {'-' * 10} {'-' * 8} {'-' * 7}")
        for metodo, caminho, sem, cli, adm in linhas:
            print(f"  {metodo:<20} {caminho:<52} {sem:>10} {cli:>8} {adm:>7}")
        print(f"\n  {len(linhas)} entradas, {len(EXCECOES)} exceções declaradas")

    assert linhas
