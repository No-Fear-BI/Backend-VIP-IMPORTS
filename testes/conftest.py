"""Infraestrutura dos testes: banco próprio, transação por teste e identidades.

BANCO SEPARADO, NÃO NEGOCIÁVEL. O teste apaga, cria e reverte linhas o tempo
todo; apontar isso para o banco onde alguém está trabalhando é perder a massa
de desenvolvimento no meio de uma tarde. A URL de teste é a de
desenvolvimento com o sufixo `_teste` no nome do banco (ou `DATABASE_URL_TESTE`
no ambiente, se você quiser outra), e este arquivo se recusa a rodar se o nome
do banco não terminar em `_teste`.

A troca da URL acontece ANTES de qualquer import de `vip_api`: o engine nasce
no import de `vip_api.banco`, a partir de `configuracao.DATABASE_URL`. Importar
o pacote antes da troca ligaria os testes no banco errado — por isso os imports
deste arquivo estão fora de ordem, com `# noqa: E402`.
"""

import os
from urllib.parse import urlsplit, urlunsplit

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

SUFIXO_TESTE = "_teste"


def _url_de_teste() -> str:
    escolhida = os.environ.get("DATABASE_URL_TESTE")
    if not escolhida:
        partes = urlsplit(_url_de_desenvolvimento())
        escolhida = urlunsplit(partes._replace(path=partes.path.rstrip("/") + SUFIXO_TESTE))

    nome = urlsplit(escolhida).path.lstrip("/")
    if not nome.endswith(SUFIXO_TESTE):
        raise RuntimeError(
            f"O banco de teste é {nome!r} e não termina em {SUFIXO_TESTE!r}. "
            "Recusando rodar: o teste reverte e apaga linhas, e essa URL pode "
            "ser a do banco de desenvolvimento."
        )
    return escolhida


def _url_de_desenvolvimento() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    # Mesmo .env que a aplicação lê. Sem depender do pydantic-settings aqui,
    # que só pode ser importado depois da URL trocada.
    # `with`: o arquivo aberto e esquecido vira ResourceWarning, e aviso aqui
    # é erro (filterwarnings do pyproject.toml).
    with open(".env", encoding="utf-8") as arquivo:
        for linha in arquivo:
            if linha.startswith("DATABASE_URL="):
                return linha.split("=", 1)[1].strip()
    raise RuntimeError("DATABASE_URL não está no ambiente nem no .env.")


def _criar_banco_se_faltar(url: str) -> None:
    partes = urlsplit(url)
    nome = partes.path.lstrip("/")
    # Conecta no banco administrativo `postgres` para poder criar o outro:
    # CREATE DATABASE não roda de dentro do banco que está sendo criado, nem
    # dentro de transação — daí o AUTOCOMMIT.
    servidor = create_engine(
        urlunsplit(partes._replace(path="/postgres")), isolation_level="AUTOCOMMIT"
    )
    with servidor.connect() as conexao:
        existe = conexao.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": nome})
        if not existe:
            conexao.execute(text(f'CREATE DATABASE "{nome}"'))
    servidor.dispose()


URL_TESTE = _url_de_teste()
_criar_banco_se_faltar(URL_TESTE)
os.environ["DATABASE_URL"] = URL_TESTE

from contextlib import contextmanager  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402

from vip_api.banco import engine, obter_sessao  # noqa: E402
from vip_api.modelos.acesso import AcessoConfig  # noqa: E402
from vip_api.modelos.admin import Administrador  # noqa: E402
from vip_api.modelos.cliente import Cliente  # noqa: E402
from vip_api.principal import app  # noqa: E402
from vip_api.seguranca.senhas import gerar_hash  # noqa: E402
from vip_api.servicos.admin import criar_sessao_admin  # noqa: E402
from vip_api.servicos.cliente import criar_sessao_cliente  # noqa: E402

from testes.identidades import (  # noqa: E402
    CLIENTE_DE_ORIGEM,
    EMAIL_ADMIN,
    EMAIL_CLIENTE,
    SENHA_ADMIN,
)

# Um argon2 por SESSÃO de teste, não um por teste: o hash é sempre da mesma
# senha, e cada verificação custa ~50 ms. O caminho de verdade do login
# (autenticar_administrador) é exercido em teste_sessao_admin.py.
HASH_SENHA_ADMIN = gerar_hash(SENHA_ADMIN)


@pytest.fixture(scope="session", autouse=True)
def migracoes() -> None:
    """Sobe o esquema uma vez por sessão de teste, com o mesmo Alembic do
    projeto — nunca com `create_all`. Migração que só é exercida em produção
    é migração não testada."""
    import logging

    # O Alembic despeja INFO no meio da saída do pytest — no import dos
    # plugins e no env.py, que reconfigura o logging inteiro (fileConfig).
    # Silenciado só durante a subida do esquema, import incluído.
    logging.disable(logging.INFO)
    try:
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config("alembic.ini"), "head")
    finally:
        logging.disable(logging.NOTSET)


@pytest.fixture
def sessao():
    """Uma transação por teste, revertida no fim.

    `join_transaction_mode="create_savepoint"` é o que faz isso funcionar com
    código de produção que dá `commit()` — e todo serviço aqui dá. Cada commit
    vira liberação de SAVEPOINT dentro da transação externa, que no fim é
    desfeita inteira. Sem isso, ou os testes sujam o banco ou o código teria
    que ser reescrito para não commitar, o que seria testar outra coisa.
    """
    conexao = engine.connect()
    transacao = conexao.begin()
    Fabrica = sessionmaker(
        bind=conexao, autoflush=False, join_transaction_mode="create_savepoint"
    )
    sessao_de_teste = Fabrica()

    yield sessao_de_teste

    sessao_de_teste.close()
    transacao.rollback()
    conexao.close()


@pytest.fixture(autouse=True)
def loja_aberta_nos_testes(sessao) -> None:
    """A migração 0014 fecha a loja, e o esquema de teste sobe até o head.

    O modo 'aberto' existe SÓ nos testes: aqui a config é aberta dentro da
    transação do teste (revertida no fim, o banco de verdade não é tocado), para
    que os demais testes de catálogo não precisem se preocupar com o portão. Os
    testes do portão chamam `_ligar_aprovacao` quando precisam dele.
    """
    config = sessao.get(AcessoConfig, 1)
    if config is None:
        config = AcessoConfig(id=1)
        sessao.add(config)
    config.modo = "aberto"
    sessao.commit()


@pytest.fixture
def app_de_teste(sessao):
    """A aplicação de verdade, com a sessão trocada pela transacional."""
    app.dependency_overrides[obter_sessao] = lambda: sessao
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def sem_sessao(app_de_teste) -> TestClient:
    """Cliente HTTP sem cookie nenhum — o visitante anônimo."""
    with TestClient(app_de_teste, client=CLIENTE_DE_ORIGEM) as cliente:
        yield cliente


@pytest.fixture
def administrador(sessao) -> Administrador:
    admin = Administrador(
        nome="Admin de Teste", email=EMAIL_ADMIN, senha_hash=HASH_SENHA_ADMIN
    )
    sessao.add(admin)
    sessao.commit()
    sessao.refresh(admin)
    return admin


@pytest.fixture
def cliente(sessao) -> Cliente:
    pessoa = Cliente(email=EMAIL_CLIENTE, nome="Cliente de Teste")
    sessao.add(pessoa)
    sessao.commit()
    sessao.refresh(pessoa)
    return pessoa


@pytest.fixture
def admin_logado(app_de_teste, sessao, administrador) -> TestClient:
    """Cliente HTTP com o cookie de ADMIN válido.

    A sessão é aberta pelo serviço, não pelo `POST /admin/sessao`: passar pelo
    login em toda fixture gastaria um argon2 por teste e contaria no limite de
    5 tentativas por minuto por IP, que reprovaria testes por motivo nenhum.
    """
    token = criar_sessao_admin(sessao, administrador)
    with TestClient(app_de_teste, client=CLIENTE_DE_ORIGEM) as http:
        http.cookies.set("vip_sessao_admin", token)
        yield http


@pytest.fixture
def outro_cliente(sessao) -> Cliente:
    pessoa = Cliente(email="cliente2@teste.local", nome="Outro Cliente")
    sessao.add(pessoa)
    sessao.commit()
    sessao.refresh(pessoa)
    return pessoa


@pytest.fixture
def outro_cliente_logado(app_de_teste, sessao, outro_cliente) -> TestClient:
    """Segunda conta de cliente, para o que só aparece com DOIS carrinhos
    diferentes em jogo — como a remoção de variação que colide nos dois."""
    token = criar_sessao_cliente(sessao, outro_cliente)
    with TestClient(app_de_teste, client=CLIENTE_DE_ORIGEM) as http:
        http.cookies.set("vip_sessao_cliente", token)
        yield http


@pytest.fixture
def cliente_logado(app_de_teste, sessao, cliente) -> TestClient:
    """Cliente HTTP com o cookie da ÁREA DO CLIENTE — o outro sistema de
    sessão, o que não pode abrir nada do painel."""
    token = criar_sessao_cliente(sessao, cliente)
    with TestClient(app_de_teste, client=CLIENTE_DE_ORIGEM) as http:
        http.cookies.set("vip_sessao_cliente", token)
        yield http


@pytest.fixture
def catalogo(sessao):
    """Catálogo pequeno: 60 produtos visíveis e 6 ocultos, com marca,
    categoria, capa e variações. Some no fim do teste junto com a transação."""
    from testes.fabrica import montar_catalogo

    return montar_catalogo(sessao)


@pytest.fixture
def produto_com_variacoes(sessao):
    """Um produto só, com um tamanho e uma cor — o caso do par do carrinho."""
    from testes.fabrica import criar_categoria, criar_marca, criar_produto

    marca = criar_marca(sessao, "Chanel", "chanel")
    categoria = criar_categoria(sessao, "feminino", "Bolsas", "bolsas")
    produto = criar_produto(
        sessao,
        codigo="TST-PAR",
        nome="Bolsa Clássica Chanel",
        marca=marca,
        categoria=categoria,
        variacoes=[("tamanho", "M"), ("cor", "Preto")],
    )
    sessao.commit()
    return produto


# Controle de transação do SQLAlchemy, não consulta de ninguém: não conta no
# orçamento das rotas.
_CONTROLE = ("SAVEPOINT", "RELEASE", "ROLLBACK", "BEGIN", "COMMIT")

# A consulta que resolve o cookie de admin em sessão. É UMA, igual em toda rota
# do painel, e não pertence ao orçamento de nenhuma delas — contá-la faria o
# teto da rota mudar se um dia a autenticação mudar de forma. Mesma coisa para
# o portão da loja (seção 05): uma leitura por chave primária de acesso_config
# em toda rota de catálogo, antes da rota começar.
_AUTENTICACAO = ("admin_sessoes", "acesso_config")


@pytest.fixture
def contar_consultas():
    """Conta as consultas SQL de um trecho, por evento do SQLAlchemy.

    É o mesmo mecanismo de scripts/contar_consultas.py, que roda à mão contra
    a massa grande — aqui ele vira asserção: rota com orçamento de consultas
    só continua dentro do orçamento se alguém conferir a cada alteração.
    """

    @contextmanager
    def _contar():
        consultas: list[str] = []

        def registrar(conexao, cursor, instrucao, parametros, contexto, muitos):
            limpa = " ".join(instrucao.split())
            if limpa.upper().startswith(_CONTROLE) or any(t in limpa for t in _AUTENTICACAO):
                return
            consultas.append(limpa)

        event.listen(engine, "before_cursor_execute", registrar)
        try:
            yield consultas
        finally:
            event.remove(engine, "before_cursor_execute", registrar)

    return _contar


@pytest.fixture(autouse=True)
def _coleta_do_yupoo_inofensiva(tmp_path, monkeypatch):
    """Nenhum teste pode disparar a coleta REAL do Yupoo.

    `POST /admin/revisao/atualizar` roda `node scripts/sync-yupoo.mjs`; as varreduras de rota
    (teste_protecao_admin, teste_vazamento_erros) chamam todas as rotas com um admin válido e
    iniciariam a coleta de verdade, deixando trava e estado em data/. Aqui o serviço aponta para
    uma pasta descartável e o comando vira um programa que não faz nada.
    """
    import sys

    from vip_api.servicos import atualizacao_fila

    monkeypatch.setattr(atualizacao_fila, "DADOS", tmp_path)
    monkeypatch.setattr(atualizacao_fila, "TRAVA", tmp_path / "sync-yupoo.lock")
    monkeypatch.setattr(atualizacao_fila, "ESTADO", tmp_path / "sync-yupoo-estado.json")
    monkeypatch.setattr(atualizacao_fila, "RELATORIO", tmp_path / "sync-yupoo-report.json")
    monkeypatch.setattr(atualizacao_fila, "_comando", lambda: [sys.executable, "-c", "pass"])
    monkeypatch.setattr(atualizacao_fila, "_fio", None)
    yield
    if atualizacao_fila._fio:
        atualizacao_fila._fio.join(timeout=10)
