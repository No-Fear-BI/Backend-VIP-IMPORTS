"""Login do painel e `GET /admin/eu` — os três desfechos da porta.

A varredura (teste_protecao_admin.py) cobre TODA rota /admin de uma vez; este
arquivo cobre o caminho de verdade do login, com senha e argon2, que a
varredura pula por ser a exceção declarada.
"""

from testes.identidades import EMAIL_ADMIN, SENHA_ADMIN


def teste_login_com_senha_certa_abre_sessao(sem_sessao, administrador):
    resposta = sem_sessao.post(
        "/api/v1/admin/sessao", json={"email": EMAIL_ADMIN, "senha": SENHA_ADMIN}
    )

    assert resposta.status_code == 200
    assert resposta.json()["email"] == EMAIL_ADMIN
    assert "vip_sessao_admin" in resposta.cookies

    bruto = resposta.headers["set-cookie"].lower()
    assert "httponly" in bruto
    assert "samesite=lax" in bruto
    # `secure` só em produção: fixo, o desenvolvimento local em HTTP pararia
    # de receber o cookie.
    assert "secure" not in bruto


def teste_login_com_senha_errada_recusa(sem_sessao, administrador):
    resposta = sem_sessao.post(
        "/api/v1/admin/sessao", json={"email": EMAIL_ADMIN, "senha": "senha-errada-1"}
    )

    assert resposta.status_code == 401
    assert resposta.json()["erro"]["codigo"] == "CREDENCIAIS_INVALIDAS"
    assert "vip_sessao_admin" not in resposta.cookies


def teste_email_inexistente_responde_igual_a_senha_errada(sem_sessao, administrador):
    """Mesmo corpo e mesmo status: distinguir os dois diria quais e-mails são
    de administrador."""
    inexistente = sem_sessao.post(
        "/api/v1/admin/sessao", json={"email": "ninguem@teste.local", "senha": "x-1234567"}
    )
    senha_errada = sem_sessao.post(
        "/api/v1/admin/sessao", json={"email": EMAIL_ADMIN, "senha": "senha-errada-1"}
    )

    assert inexistente.status_code == senha_errada.status_code == 401
    assert inexistente.json() == senha_errada.json()


def teste_eu_sem_sessao_responde_401(sem_sessao):
    resposta = sem_sessao.get("/api/v1/admin/eu")

    assert resposta.status_code == 401
    assert resposta.json()["erro"]["codigo"] == "NAO_IDENTIFICADO"


def teste_eu_com_sessao_de_cliente_responde_403(cliente_logado):
    """Cliente identificado NÃO é administrador. 403 e não 401 porque mandar
    essa pessoa para a tela de login do painel a faria tentar uma senha que
    ela não tem."""
    resposta = cliente_logado.get("/api/v1/admin/eu")

    assert resposta.status_code == 403
    assert resposta.json()["erro"]["codigo"] == "SEM_PERMISSAO"


def teste_eu_com_sessao_de_admin_responde_o_administrador(admin_logado, administrador):
    resposta = admin_logado.get("/api/v1/admin/eu")

    assert resposta.status_code == 200
    assert resposta.json()["id"] == administrador.id
    assert resposta.json()["email"] == EMAIL_ADMIN


def teste_sair_revoga_a_sessao_no_banco(admin_logado):
    assert admin_logado.get("/api/v1/admin/eu").status_code == 200

    resposta = admin_logado.delete("/api/v1/admin/sessao")
    assert resposta.status_code == 200

    # O cookie sumiu do navegador; o teste devolve o token à mão para provar
    # que a revogação foi no BANCO, e não só no cookie.
    assert admin_logado.get("/api/v1/admin/eu").status_code == 401
