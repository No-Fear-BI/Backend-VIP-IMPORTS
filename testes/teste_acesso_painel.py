"""O que acontece com a sessão do painel DEPOIS do login.

Herdado dos passos `convivencia`, `troca`, `limite` e `expiracao` do antigo
roteiro de verificação da Fatia 4:

- os cookies de cliente e de admin convivem no mesmo navegador, e sair de um
  não derruba o outro;
- trocar a senha derruba a sessão aberta;
- o login do painel tem limite próprio por IP, num balde separado do da loja;
- a sessão vale 12 horas e não é aceita depois disso.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from testes.identidades import EMAIL_ADMIN, EMAIL_CLIENTE, SENHA_ADMIN
from vip_api.modelos.admin import AdminSessao
from vip_api.seguranca import limite
from vip_api.servicos.admin import criar_sessao_admin, trocar_senha

LOGIN = "/api/v1/admin/sessao"


def _entrar(http, senha=SENHA_ADMIN):
    return http.post(LOGIN, json={"email": EMAIL_ADMIN, "senha": senha})


@pytest.fixture
def janela_fixa(monkeypatch):
    """Congela a janela do limite num minuto só. Sem isso, o teste que
    atravessa a virada do minuto zera o contador no meio e fica vermelho por
    acaso."""
    fixa = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    monkeypatch.setattr(limite, "_inicio_do_minuto", lambda momento: fixa)


# ----------------------------------------------------------------------
# convivência
# ----------------------------------------------------------------------


def teste_sair_do_painel_nao_derruba_a_sessao_da_loja(cliente_logado, sessao, administrador):
    cliente_logado.cookies.set("vip_sessao_admin", criar_sessao_admin(sessao, administrador))
    assert cliente_logado.get("/api/v1/clientes/eu").status_code == 200
    assert cliente_logado.get("/api/v1/admin/eu").status_code == 200

    assert cliente_logado.delete(LOGIN).status_code == 200

    assert cliente_logado.get("/api/v1/clientes/eu").status_code == 200
    assert cliente_logado.get("/api/v1/admin/eu").status_code in (401, 403)


def teste_sair_da_loja_nao_derruba_a_sessao_do_painel(cliente_logado, sessao, administrador):
    cliente_logado.cookies.set("vip_sessao_admin", criar_sessao_admin(sessao, administrador))

    assert cliente_logado.post("/api/v1/clientes/sair").status_code == 200

    assert cliente_logado.get("/api/v1/admin/eu").status_code == 200


# ----------------------------------------------------------------------
# troca de senha
# ----------------------------------------------------------------------


def teste_trocar_a_senha_derruba_a_sessao_aberta(admin_logado, sem_sessao, sessao, administrador):
    assert admin_logado.get("/api/v1/admin/eu").status_code == 200
    nova = "senha-trocada-no-teste-1"

    derrubadas = trocar_senha(sessao, administrador, nova)

    assert derrubadas == 1
    assert admin_logado.get("/api/v1/admin/eu").status_code == 401
    assert _entrar(sem_sessao, nova).status_code == 200
    assert _entrar(sem_sessao, SENHA_ADMIN).status_code == 401


# ----------------------------------------------------------------------
# limite de tentativas
# ----------------------------------------------------------------------


def teste_login_do_painel_estoura_no_sexto_e_a_loja_segue_atendendo(
    sem_sessao, administrador, janela_fixa
):
    for _ in range(limite.LIMITE_LOGIN_ADMIN):
        assert _entrar(sem_sessao, "senha-errada-1").status_code == 401

    bloqueado = _entrar(sem_sessao, SENHA_ADMIN)
    assert bloqueado.status_code == 429
    assert bloqueado.json()["erro"]["codigo"] == "EXCESSO_TENTATIVAS"

    # Mesmo IP, outro balde.
    loja = sem_sessao.post("/api/v1/clientes/identificar", json={"email": EMAIL_CLIENTE})
    assert loja.status_code == 200


def teste_loja_bloqueada_nao_tranca_o_painel(sem_sessao, administrador, janela_fixa):
    for _ in range(limite.LIMITE_POR_MINUTO):
        resposta = sem_sessao.post("/api/v1/clientes/identificar", json={"email": EMAIL_CLIENTE})
        assert resposta.status_code == 200

    bloqueada = sem_sessao.post("/api/v1/clientes/identificar", json={"email": EMAIL_CLIENTE})
    assert bloqueada.status_code == 429

    assert _entrar(sem_sessao).status_code == 200


# ----------------------------------------------------------------------
# expiração
# ----------------------------------------------------------------------


def teste_sessao_dura_doze_horas(sem_sessao, sessao, administrador):
    assert _entrar(sem_sessao).status_code == 200

    criada, expira = sessao.execute(
        select(AdminSessao.criado_em, AdminSessao.expira_em).where(
            AdminSessao.administrador_id == administrador.id
        )
    ).one()

    assert expira - criada == timedelta(hours=12)


def teste_sessao_expirada_nao_entra(admin_logado, sessao, administrador):
    assert admin_logado.get("/api/v1/admin/eu").status_code == 200

    sessao.execute(
        update(AdminSessao)
        .where(AdminSessao.administrador_id == administrador.id)
        .values(expira_em=datetime.now(timezone.utc) - timedelta(minutes=1))
    )
    sessao.commit()

    resposta = admin_logado.get("/api/v1/admin/eu")
    assert resposta.status_code == 401
    assert resposta.json()["erro"]["codigo"] == "NAO_IDENTIFICADO"
