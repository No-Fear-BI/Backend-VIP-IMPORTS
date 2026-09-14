"""Verificação do acesso ao painel: login, sessão própria e limite (tarefas 52 e 53).

Cada passo imprime o que mandou e o que recebeu, para a saída se sustentar
sozinha sem quem lê ter que confiar no código.

    python scripts/verificar_fatia4.py <passo>

Passos: login, respostas, eu, convivencia, troca, limite, expiracao, tudo
"""

import json
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# 127.0.0.1 e não "localhost": com o nome, o urllib tenta ::1 primeiro, o
# servidor local só escuta em IPv4 e cada requisição carrega ~2 s de espera
# antes de cair no IPv4 — ruído que engoliria a medição de tempo do passo
# `respostas`.
BASE = "http://127.0.0.1:8000/api/v1"
RAIZ = os.path.join(os.path.dirname(__file__), "..")

ADMIN_EMAIL = "painel@nofear.com.br"
ADMIN_SENHA = "senha-do-painel-1"
SUPORTE_EMAIL = "suporte@nofear.com.br"
SUPORTE_SENHA = "senha-do-suporte-1"
INATIVO_EMAIL = "desligado@nofear.com.br"
INATIVO_SENHA = "senha-do-desligado-1"
CLIENTE_EMAIL = "verificacao.fatia4@nofear.test"


class Navegador:
    """Um pote de cookies, como o do navegador: guarda o do cliente e o do
    admin lado a lado, e manda os dois em toda requisição."""

    def __init__(self) -> None:
        self.cookies: dict[str, str] = {}

    def pedir(self, metodo: str, caminho: str, corpo=None, cookies=None):
        dados = json.dumps(corpo).encode() if corpo is not None else None
        req = urllib.request.Request(f"{BASE}{caminho}", data=dados, method=metodo)
        req.add_header("Content-Type", "application/json")

        enviar = self.cookies if cookies is None else cookies
        if enviar:
            req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in enviar.items()))

        inicio = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                bruto, cabecalhos, status = r.read().decode("utf-8"), list(r.headers.items()), r.status
        except urllib.error.HTTPError as e:
            bruto, cabecalhos, status = e.read().decode("utf-8"), list(e.headers.items()), e.code
        segundos = time.perf_counter() - inicio

        for chave, valor in cabecalhos:
            if chave.lower() == "set-cookie":
                nome, _, resto = valor.partition("=")
                conteudo = resto.split(";")[0]
                if conteudo and "max-age=0" not in valor.lower():
                    self.cookies[nome] = conteudo
                else:
                    self.cookies.pop(nome, None)

        return status, (json.loads(bruto) if bruto else None), cabecalhos, segundos

    def set_cookie(self, cabecalhos) -> str | None:
        for chave, valor in cabecalhos:
            if chave.lower() == "set-cookie":
                return valor
        return None


def zerar_tentativas(escopo: str | None = None) -> None:
    """Limpa o contador de tentativas por IP.

    O limite é de 5 logins de admin por minuto (passo `limite`), e um passo de
    verificação faz mais que isso. Zerar entre os passos é coisa do teste, não
    do sistema — por isso aparece impresso.
    """
    from sqlalchemy import delete

    from vip_api.banco import SessaoLocal
    from vip_api.modelos.acesso_tentativas import TentativaAcesso

    with SessaoLocal() as sessao:
        instrucao = delete(TentativaAcesso)
        if escopo:
            instrucao = instrucao.where(TentativaAcesso.escopo == escopo)
        sessao.execute(instrucao)
        sessao.commit()


def entrar_como_admin(navegador: Navegador, email=ADMIN_EMAIL, senha=ADMIN_SENHA):
    return navegador.pedir("POST", "/admin/sessao", {"email": email, "senha": senha})


def preparar_administradores() -> None:
    """Garante as contas do roteiro: duas ativas e uma desativada.

    A conta inativa é criada pelo mesmo comando de linha das outras e
    desativada direto no banco — não existe rota nem script para desativar, e
    inventar um só para o teste seria código que ninguém mais usa.
    """
    from sqlalchemy import update

    from vip_api.banco import SessaoLocal
    from vip_api.modelos.admin import Administrador
    from vip_api.servicos.admin import buscar_por_email, criar_administrador

    with SessaoLocal() as sessao:
        for email, nome, senha in (
            (ADMIN_EMAIL, "Equipe VIP Imports", ADMIN_SENHA),
            (SUPORTE_EMAIL, "Suporte No Fear", SUPORTE_SENHA),
            (INATIVO_EMAIL, "Conta Desligada", INATIVO_SENHA),
        ):
            if buscar_por_email(sessao, email) is None:
                criar_administrador(sessao, email, nome, senha)
        sessao.execute(
            update(Administrador)
            .where(Administrador.email == INATIVO_EMAIL)
            .values(ativo=False)
        )
        sessao.commit()


# ======================================================================
# login — 200, cookie e os atributos do cookie
# ======================================================================


def passo_login() -> None:
    zerar_tentativas()
    navegador = Navegador()
    status, corpo, cabecalhos, _ = entrar_como_admin(navegador)

    print(f"  POST /admin/sessao  {{\"email\": \"{ADMIN_EMAIL}\", \"senha\": \"...\"}}")
    print(f"    HTTP {status}")
    print(f"    corpo: {json.dumps(corpo, ensure_ascii=False)}")

    bruto = navegador.set_cookie(cabecalhos)
    print(f"\n    Set-Cookie: {bruto}")

    minusculo = (bruto or "").lower()
    from vip_api.dependencias.sessao_admin import NOME_COOKIE as COOKIE_ADMIN
    from vip_api.dependencias.sessao_cliente import NOME_COOKIE as COOKIE_CLIENTE

    conferencias = [
        ("HttpOnly presente", "httponly" in minusculo),
        ("SameSite=Lax", "samesite=lax" in minusculo),
        ("Secure AUSENTE (desenvolvimento)", "secure" not in minusculo),
        ("Path=/", "path=/" in minusculo),
        (f"nome do cookie é {COOKIE_ADMIN}", minusculo.startswith(f"{COOKIE_ADMIN}=")),
        (
            f"diferente do cookie de cliente ({COOKIE_CLIENTE})",
            COOKIE_ADMIN != COOKIE_CLIENTE,
        ),
        ("Max-Age de 12 horas (43200s)", "max-age=43200" in minusculo),
    ]
    print()
    for rotulo, ok in conferencias:
        print(f"    [{'OK' if ok else 'FALHOU'}] {rotulo}")


# ======================================================================
# respostas — os três fracassos são indistinguíveis
# ======================================================================


def passo_respostas() -> None:
    casos = [
        ("e-mail que NÃO existe", "ninguem@nofear.com.br", "qualquer-senha-1"),
        ("e-mail que existe, senha errada", ADMIN_EMAIL, "senha-errada-1"),
        ("administrador INATIVO, senha certa", INATIVO_EMAIL, INATIVO_SENHA),
    ]

    navegador = Navegador()
    zerar_tentativas()
    entrar_como_admin(navegador, casos[0][1], casos[0][2])  # aquecimento

    print("  resposta de cada caso")
    respostas = []
    for rotulo, email, senha in casos:
        zerar_tentativas()
        status, corpo, _, _ = navegador.pedir(
            "POST", "/admin/sessao", {"email": email, "senha": senha}
        )
        respostas.append((status, json.dumps(corpo, ensure_ascii=False, sort_keys=True)))
        print(f"    {rotulo:<38} HTTP {status} {respostas[-1][1]}")

    iguais = len(set(respostas)) == 1
    print(f"\n    [{'OK' if iguais else 'FALHOU'}] as três respostas são idênticas em status e corpo")

    print("\n  tempo de resposta (ms), 10 medições por caso")
    tempos: dict[str, list[float]] = {}
    for rodada in range(10):
        for rotulo, email, senha in casos:
            zerar_tentativas()
            _, _, _, segundos = navegador.pedir(
                "POST", "/admin/sessao", {"email": email, "senha": senha}
            )
            tempos.setdefault(rotulo, []).append(segundos * 1000)

    for rotulo, medicoes in tempos.items():
        amostras = " ".join(f"{m:5.0f}" for m in medicoes)
        print(f"    {rotulo:<38} {amostras}   mediana {statistics.median(medicoes):5.1f}")

    medianas = [statistics.median(m) for m in tempos.values()]
    entre_casos = max(medianas) - min(medianas)
    # A comparação que interessa não é "as medianas bateram", é se a diferença
    # ENTRE os casos se separa do ruído DENTRO de um caso. Se não se separa,
    # não há o que cronometrar.
    dentro_do_caso = max(max(m) - min(m) for m in tempos.values())
    print(f"\n    o argon2 custa ~{min(medianas):.0f} ms e roda nos três casos")
    print(f"    diferença entre as medianas dos casos .... {entre_casos:5.1f} ms")
    print(f"    variação DENTRO de um mesmo caso ......... {dentro_do_caso:5.1f} ms")
    print(
        "    => a diferença entre os casos não se separa do ruído da própria máquina"
        if entre_casos < dentro_do_caso
        else "    => ATENÇÃO: diferença entre casos maior que o ruído"
    )
    print("    (o contador de tentativas é zerado entre as medições — o limite é 5/min)")


# ======================================================================
# eu — 200 com cookie de admin, 403 com cookie de cliente, 401 sem nada
# ======================================================================


def passo_eu() -> None:
    zerar_tentativas()

    admin = Navegador()
    entrar_como_admin(admin)
    status, corpo, _, _ = admin.pedir("GET", "/admin/eu")
    print(f"  GET /admin/eu  com cookie de ADMIN     HTTP {status} {json.dumps(corpo, ensure_ascii=False)}")

    cliente = Navegador()
    cliente.pedir("POST", "/clientes/identificar", {"email": CLIENTE_EMAIL})
    status, corpo, _, _ = cliente.pedir("GET", "/admin/eu")
    print(f"  GET /admin/eu  com cookie de CLIENTE   HTTP {status} {json.dumps(corpo, ensure_ascii=False)}")

    anonimo = Navegador()
    status, corpo, _, _ = anonimo.pedir("GET", "/admin/eu")
    print(f"  GET /admin/eu  SEM cookie              HTTP {status} {json.dumps(corpo, ensure_ascii=False)}")


# ======================================================================
# convivencia — os dois cookies no mesmo navegador
# ======================================================================


def passo_convivencia() -> None:
    zerar_tentativas()
    navegador = Navegador()

    navegador.pedir("POST", "/clientes/identificar", {"email": CLIENTE_EMAIL})
    entrar_como_admin(navegador)
    print(f"  cookies guardados: {sorted(navegador.cookies)}")

    status, corpo, _, _ = navegador.pedir("GET", "/clientes/eu")
    print(f"\n  GET /clientes/eu  HTTP {status} {json.dumps(corpo, ensure_ascii=False)}")
    status, corpo, _, _ = navegador.pedir("GET", "/admin/eu")
    print(f"  GET /admin/eu     HTTP {status} {json.dumps(corpo, ensure_ascii=False)}")

    # Sair do painel não pode derrubar a sessão da loja, e vice-versa.
    navegador.pedir("DELETE", "/admin/sessao")
    print(f"\n  depois de DELETE /admin/sessao — cookies: {sorted(navegador.cookies)}")
    status, corpo, _, _ = navegador.pedir("GET", "/clientes/eu")
    print(f"  GET /clientes/eu  HTTP {status} {json.dumps(corpo, ensure_ascii=False)}")
    status, corpo, _, _ = navegador.pedir("GET", "/admin/eu")
    print(f"  GET /admin/eu     HTTP {status} {json.dumps(corpo, ensure_ascii=False)}")


# ======================================================================
# troca — a senha nova derruba a sessão aberta
# ======================================================================


def passo_troca() -> None:
    zerar_tentativas()
    navegador = Navegador()
    entrar_como_admin(navegador, SUPORTE_EMAIL, SUPORTE_SENHA)
    status, corpo, _, _ = navegador.pedir("GET", "/admin/eu")
    print(f"  sessão aberta de {SUPORTE_EMAIL}: GET /admin/eu -> HTTP {status}")

    nova = "senha-trocada-no-teste-1"
    entrada = f"{SUPORTE_EMAIL}\n{nova}\n{nova}\n"
    print(f"\n  $ python scripts/trocar_senha_admin.py  (entrada: e-mail e a senha nova duas vezes)")
    resultado = subprocess.run(
        [sys.executable, os.path.join(RAIZ, "scripts", "trocar_senha_admin.py")],
        input=entrada,
        text=True,
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    for linha in (resultado.stdout or "").splitlines():
        print(f"    {linha}")
    if resultado.returncode != 0:
        print(f"    (código {resultado.returncode}) {resultado.stderr.strip()}")

    status, corpo, _, _ = navegador.pedir("GET", "/admin/eu")
    print(f"\n  GET /admin/eu com o cookie ANTIGO   HTTP {status} {json.dumps(corpo, ensure_ascii=False)}")

    status, _, _, _ = entrar_como_admin(navegador, SUPORTE_EMAIL, nova)
    print(f"  login com a senha NOVA              HTTP {status}")
    status, _, _, _ = entrar_como_admin(navegador, SUPORTE_EMAIL, SUPORTE_SENHA)
    print(f"  login com a senha ANTIGA            HTTP {status}")

    # Devolve a senha original para o passo poder rodar de novo.
    subprocess.run(
        [sys.executable, os.path.join(RAIZ, "scripts", "trocar_senha_admin.py")],
        input=f"{SUPORTE_EMAIL}\n{SUPORTE_SENHA}\n{SUPORTE_SENHA}\n",
        text=True,
        capture_output=True,
        encoding="utf-8",
    )


# ======================================================================
# limite — 429 no login, e os dois baldes separados
# ======================================================================


def passo_limite() -> None:
    from vip_api.seguranca.limite import (
        ESCOPO_LOGIN_ADMIN,
        LIMITE_LOGIN_ADMIN,
        LIMITE_POR_MINUTO,
    )

    zerar_tentativas()
    navegador = Navegador()

    print(f"  limite do painel: {LIMITE_LOGIN_ADMIN}/min · limite da loja: {LIMITE_POR_MINUTO}/min")
    print("\n  POST /admin/sessao com senha errada, em sequência:")
    for tentativa in range(1, LIMITE_LOGIN_ADMIN + 2):
        status, corpo, _, _ = navegador.pedir(
            "POST", "/admin/sessao", {"email": ADMIN_EMAIL, "senha": "senha-errada-1"}
        )
        codigo = (corpo or {}).get("erro", {}).get("codigo", "")
        print(f"    tentativa {tentativa}: HTTP {status} {codigo}")

    print("\n  com o painel bloqueado, a LOJA continua atendendo o mesmo IP:")
    status, corpo, _, _ = navegador.pedir(
        "POST", "/clientes/identificar", {"email": CLIENTE_EMAIL}
    )
    print(f"    POST /clientes/identificar  HTTP {status}")

    print("\n  agora o contrário — estourando o limite da LOJA")
    # Zera SÓ o balde do painel: o da loja continua contando de onde parou. É
    # o que torna a segunda metade uma prova, e não um recomeço.
    zerar_tentativas(ESCOPO_LOGIN_ADMIN)
    print("  (contador do painel zerado aqui; o da loja segue de onde parou)")
    for tentativa in range(1, LIMITE_POR_MINUTO + 2):
        status, corpo, _, _ = navegador.pedir(
            "POST", "/clientes/identificar", {"email": CLIENTE_EMAIL}
        )
        codigo = (corpo or {}).get("erro", {}).get("codigo", "")
        # Só as últimas: o começo da sequência é repetição de HTTP 200.
        if tentativa > LIMITE_POR_MINUTO - 3:
            print(f"    tentativa {tentativa}: HTTP {status} {codigo}".rstrip())

    print("\n  com a loja bloqueada, o PAINEL continua atendendo o mesmo IP:")
    status, corpo, _, _ = entrar_como_admin(navegador)
    print(f"    POST /admin/sessao  HTTP {status}")

    from vip_api.banco import SessaoLocal
    from vip_api.seguranca.limite import tentativas_na_janela

    with SessaoLocal() as sessao:
        loja = tentativas_na_janela(sessao, "127.0.0.1", "identificacao")
        painel = tentativas_na_janela(sessao, "127.0.0.1", "admin_login")
    print(f"\n    contagem na janela atual — identificacao={loja}  admin_login={painel}")
    zerar_tentativas()


# ======================================================================
# expiracao — 12 horas, sem renovação
# ======================================================================


def passo_expiracao() -> None:
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select, update

    from vip_api.banco import SessaoLocal
    from vip_api.modelos.admin import AdminSessao
    from vip_api.seguranca.tokens import hash_do_token

    zerar_tentativas()
    navegador = Navegador()
    entrar_como_admin(navegador)
    token = navegador.cookies["vip_sessao_admin"]

    status, _, _, _ = navegador.pedir("GET", "/admin/eu")
    print(f"  GET /admin/eu logo após o login          HTTP {status}")

    with SessaoLocal() as sessao:
        expira = sessao.scalar(
            select(AdminSessao.expira_em).where(
                AdminSessao.token_hash == hash_do_token(token)
            )
        )
        criado = sessao.scalar(
            select(AdminSessao.criado_em).where(
                AdminSessao.token_hash == hash_do_token(token)
            )
        )
    print(f"    criada em {criado:%Y-%m-%d %H:%M:%S%z}, expira em {expira:%Y-%m-%d %H:%M:%S%z} "
          f"({(expira - criado).total_seconds() / 3600:.0f} horas)")

    with SessaoLocal() as sessao:
        sessao.execute(
            update(AdminSessao)
            .where(AdminSessao.token_hash == hash_do_token(token))
            .values(expira_em=datetime.now(timezone.utc) - timedelta(minutes=1))
        )
        sessao.commit()
    print("\n  expira_em forçada para um minuto atrás, direto no banco")

    status, corpo, _, _ = navegador.pedir("GET", "/admin/eu")
    print(f"  GET /admin/eu com o MESMO cookie         HTTP {status} {json.dumps(corpo, ensure_ascii=False)}")


PASSOS = {
    "login": passo_login,
    "respostas": passo_respostas,
    "eu": passo_eu,
    "convivencia": passo_convivencia,
    "troca": passo_troca,
    "limite": passo_limite,
    "expiracao": passo_expiracao,
}


def main() -> None:
    escolhido = sys.argv[1] if len(sys.argv) > 1 else "tudo"
    if escolhido != "tudo" and escolhido not in PASSOS:
        print(f"passo desconhecido: {escolhido}")
        print(f"passos: {', '.join(PASSOS)}, tudo")
        sys.exit(2)

    preparar_administradores()
    for nome, funcao in PASSOS.items():
        if escolhido in ("tudo", nome):
            print(f"===== {nome} =====")
            funcao()
            print()


if __name__ == "__main__":
    main()
