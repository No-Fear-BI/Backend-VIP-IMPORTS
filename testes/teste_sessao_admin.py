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
    assert "path=/" in bruto
    # 12 horas, o mesmo prazo gravado em admin_sessoes.expira_em.
    assert "max-age=43200" in bruto
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


def teste_conta_inativa_responde_igual_e_o_argon2_roda_nos_tres_casos(
    sem_sessao, sessao, administrador, monkeypatch
):
    """Os três fracassos são indistinguíveis também no TEMPO.

    Cronometrar não serve de teste — o ruído da máquina é maior que qualquer
    limiar honesto. O que dá para provar é a causa: nos três casos a senha
    passa por uma verificação argon2, real ou contra o hash descartável.
    """
    from vip_api.modelos.admin import Administrador
    from vip_api.seguranca import senhas
    from vip_api.servicos import admin

    sessao.add(
        Administrador(
            nome="Desligado",
            email="desligado@teste.local",
            senha_hash=administrador.senha_hash,
            ativo=False,
        )
    )
    sessao.commit()

    verificacoes = []
    original = senhas.conferir_senha

    def contar(senha, hash_guardado):
        verificacoes.append(hash_guardado)
        return original(senha, hash_guardado)

    # Os dois nomes: o serviço importou a função, e o gasto de tempo chama a
    # do próprio módulo.
    monkeypatch.setattr(senhas, "conferir_senha", contar)
    monkeypatch.setattr(admin, "conferir_senha", contar)

    casos = [
        ("ninguem@teste.local", "qualquer-senha-1"),
        (EMAIL_ADMIN, "senha-errada-1"),
        ("desligado@teste.local", SENHA_ADMIN),
    ]
    respostas = []
    for email, senha in casos:
        antes = len(verificacoes)
        resposta = sem_sessao.post("/api/v1/admin/sessao", json={"email": email, "senha": senha})
        respostas.append((resposta.status_code, resposta.json()))
        assert len(verificacoes) == antes + 1, f"sem argon2 para {email}"

    assert respostas[0] == respostas[1] == respostas[2]
    assert respostas[0][0] == 401


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
