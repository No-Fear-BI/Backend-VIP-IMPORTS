"""Tarefa 78: nenhuma resposta de erro deixa escapar detalhe técnico.

O formato do erro existe desde a Fatia 0 (erros/manipuladores.py). Este teste
é a prova de que ele segura, e continua segurando quando alguém escrever a
rota número 56: ele não tem lista de rotas. Lê o roteador, e em CADA rota força
os erros que dá para forçar de fora:

- sem sessão nenhuma;
- id inexistente, e id grande demais para a coluna do banco;
- tipo errado nos parâmetros de caminho e de query;
- corpo que não é JSON, corpo que não é objeto e corpo com tipo errado em
  todos os campos;
- cursor corrompido, de quatro jeitos diferentes.

Toda resposta com status >= 400 tem o corpo INTEIRO conferido contra os
nomes de tabela (lidos de `Base.metadata`, não de uma lista), os marcadores de
traceback e de biblioteca de banco, e o caminho do projeto no disco.
"""

import base64
import json
import pathlib
import re
import types
import typing

import pytest
from fastapi.dependencies.utils import get_flat_dependant
from fastapi.testclient import TestClient

import vip_api.modelos  # noqa: F401  (registra todas as tabelas em Base.metadata)
from testes.identidades import CLIENTE_DE_ORIGEM
from testes.rotas_registradas import rotas_da_api
from vip_api.modelos.base import Base

RAIZ = pathlib.Path(__file__).resolve().parent.parent

TABELAS = sorted(Base.metadata.tables)
MARCADORES_TECNICOS = ["Traceback", 'File "', ".py", "sqlalchemy", "psycopg", "asyncpg"]
# O caminho do projeto do jeito que ele pode aparecer: com barra invertida,
# com barra normal e com a barra invertida escapada pelo JSON.
CAMINHOS_DO_PROJETO = sorted(
    {str(RAIZ), RAIZ.as_posix(), json.dumps(str(RAIZ))[1:-1]}, key=len, reverse=True
)


def _padrao_de_tabela(nome: str) -> re.Pattern:
    """Nome de tabela com sublinhado (`admin_sessoes`, `carrinho_itens`) não
    existe em português corrido: casa em qualquer lugar.

    Nome que é palavra comum (`produtos`, `marcas`, `clientes`) casa só na
    forma em que um vazamento aparece: depois de FROM/JOIN/INTO/UPDATE/TABLE,
    `relation` ou `tabela`; entre aspas; qualificado (`produtos.id`); ou
    dentro de identificador (`uq_produtos_codigo`). Sem essa distinção,
    "Adicione produtos antes de enviar" — a mensagem certa — reprovaria.
    """
    escapado = re.escape(nome)
    if "_" in nome:
        return re.compile(rf"(?<![A-Za-z0-9]){escapado}(?![A-Za-z0-9])", re.I)
    return re.compile(
        rf"(?:(?:from|join|into|update|table|relation|tabela)\s+[\"'`]?|[\"'`._]){escapado}(?![A-Za-z0-9])"
        rf"|(?<![A-Za-z0-9]){escapado}(?:[\"'`_]|\.[A-Za-z_])",
        re.I,
    )


PROCURADOS = (
    [(f"tabela {nome}", _padrao_de_tabela(nome)) for nome in TABELAS]
    + [(marcador, re.compile(re.escape(marcador), re.I)) for marcador in MARCADORES_TECNICOS]
    + [("caminho do projeto", re.compile(re.escape(caminho), re.I)) for caminho in CAMINHOS_DO_PROJETO]
)

ID_INEXISTENTE = 99_999_999
# Cabe num int do Python e do Pydantic, NÃO cabe no `integer` do PostgreSQL:
# é o jeito de fazer o erro nascer lá embaixo, no driver.
ID_FORA_DO_INTERVALO = 9_223_372_036_854_775_807


def _b64(texto: str) -> str:
    return base64.urlsafe_b64encode(texto.encode()).decode().rstrip("=")


CURSORES_CORROMPIDOS = {
    "cursor não-base64": "@@@não-é-cursor@@@",
    "cursor base64 sem JSON": _b64("isto não é json"),
    "cursor JSON que não é objeto": _b64("[1, 2, 3]"),
    "cursor com tipos errados": _b64(json.dumps({"o": "recentes", "v": "ontem", "id": "abc", "t": "muitos"})),
    "cursor com id gigante": _b64(
        json.dumps({"o": "recentes", "v": "2026-01-01T00:00:00+00:00", "id": ID_FORA_DO_INTERVALO, "t": 1})
    ),
}


def _tipo_base(anotacao):
    """`int | None` -> int; `list[str]` -> list; `Literal[...]` -> Literal."""
    origem = typing.get_origin(anotacao)
    if origem in (typing.Union, types.UnionType):
        argumentos = [a for a in typing.get_args(anotacao) if a is not type(None)]
        return _tipo_base(argumentos[0]) if argumentos else str
    if origem is typing.Literal:
        return typing.Literal
    return origem or anotacao


def _valor_inexistente(parametro) -> str:
    return str(ID_INEXISTENTE) if _tipo_base(parametro.type_) is int else "nao-existe-000"


def _montar_caminho(caminho: str, parametros_de_caminho, trocar: dict[str, str] | None = None) -> str:
    valores = {p.alias: _valor_inexistente(p) for p in parametros_de_caminho}
    valores.update(trocar or {})
    return re.sub(r"\{([^}]+)\}", lambda m: valores[m.group(1)], caminho)


def variantes(metodo: str, caminho: str, rota):
    """(nome da variante, argumentos de `TestClient.request`) para uma rota."""
    plano = get_flat_dependant(rota.dependant, skip_repeats=True)
    de_caminho = plano.path_params
    base = _montar_caminho(caminho, de_caminho)
    aceita_corpo = metodo in {"POST", "PUT", "PATCH"}
    corpo_vazio = {"json": {}} if aceita_corpo else {}

    yield "id inexistente" if de_caminho else "requisição simples", {"url": base, **corpo_vazio}

    inteiros = [p for p in de_caminho if _tipo_base(p.type_) is int]
    if inteiros:
        grandes = {p.alias: str(ID_FORA_DO_INTERVALO) for p in inteiros}
        yield "id fora do intervalo", {"url": _montar_caminho(caminho, de_caminho, grandes), **corpo_vazio}
        errados = {p.alias: "abc" for p in inteiros}
        yield "tipo errado no caminho", {"url": _montar_caminho(caminho, de_caminho, errados), **corpo_vazio}

    tipados = [p for p in plano.query_params if _tipo_base(p.type_) not in (str,)]
    if tipados:
        yield "tipo errado na query", {
            "url": base,
            "params": {p.alias: "abc" for p in tipados},
            **corpo_vazio,
        }

    if any(p.alias == "cursor" for p in plano.query_params):
        for nome, cursor in CURSORES_CORROMPIDOS.items():
            yield nome, {"url": base, "params": {"cursor": cursor}}

    if aceita_corpo:
        yield "corpo que não é JSON", {
            "url": base,
            "content": b'{"isto": nao e json',
            "headers": {"content-type": "application/json"},
        }
        yield "corpo que não é objeto", {"url": base, "json": [1, 2, 3]}
        campos = {}
        for parametro in plano.body_params:
            modelo = parametro.type_
            nomes = (
                [c.alias or n for n, c in modelo.model_fields.items()]
                if hasattr(modelo, "model_fields")
                else [parametro.alias]
            )
            campos.update({nome: {"tipo": ["errado", None]} for nome in nomes})
        if campos:
            yield "tipo errado em todo campo do corpo", {"url": base, "json": campos}


def _textos_do_corpo(resposta) -> list[str]:
    """O corpo cru e, se for JSON, cada chave e cada valor decodificados —
    `\\u00e9` e barras escapadas não escondem nada da busca."""
    textos = [resposta.text]
    try:
        dados = resposta.json()
    except ValueError:
        return textos

    def andar(no):
        if isinstance(no, dict):
            for chave, valor in no.items():
                yield str(chave)
                yield from andar(valor)
        elif isinstance(no, list):
            for item in no:
                yield from andar(item)
        elif no is not None:
            yield str(no)

    textos.append("\n".join(andar(dados)))
    return textos


def vazamentos(resposta) -> list[tuple[str, str]]:
    """Um achado por marcador: o mesmo trecho no corpo cru e no decodificado
    é um vazamento só."""
    achados = []
    for texto in _textos_do_corpo(resposta):
        for rotulo, padrao in PROCURADOS:
            encontrado = padrao.search(texto)
            if encontrado and rotulo not in {r for r, _ in achados}:
                inicio = max(0, encontrado.start() - 40)
                achados.append((rotulo, texto[inicio : encontrado.end() + 40]))
    return achados


@pytest.fixture
def navegadores(app_de_teste, sessao, administrador, cliente):
    """Um navegador com as DUAS sessões — para o erro nascer dentro da rota, e
    não na porta — e um anônimo, para os erros da porta.

    `raise_server_exceptions=False`: sem isso o TestClient relança a exceção
    em vez de devolver o 500 que o visitante veria, e o 500 é justamente a
    resposta mais perigosa de conferir.
    """
    from vip_api.servicos.admin import criar_sessao_admin
    from vip_api.servicos.cliente import criar_sessao_cliente

    logado = TestClient(app_de_teste, client=CLIENTE_DE_ORIGEM, raise_server_exceptions=False)
    anonimo = TestClient(app_de_teste, client=CLIENTE_DE_ORIGEM, raise_server_exceptions=False)
    with logado, anonimo:
        logado.cookies.set("vip_sessao_admin", criar_sessao_admin(sessao, administrador))
        logado.cookies.set("vip_sessao_cliente", criar_sessao_cliente(sessao, cliente))
        yield logado, anonimo


ROTAS = rotas_da_api()


def teste_ha_rotas_e_tabelas_para_conferir():
    """Guarda contra o teste ficar verde por não varrer nada."""
    assert len(ROTAS) > 40
    assert "produtos" in TABELAS and "admin_sessoes" in TABELAS


@pytest.mark.parametrize("metodo,caminho,rota", ROTAS, ids=[f"{m} {c}" for m, c, _ in ROTAS])
def teste_erro_nao_vaza_detalhe_tecnico(metodo, caminho, rota, navegadores, sessao):
    logado, anonimo = navegadores
    erros_vistos = 0
    achados = []

    tentativas = [("sem sessão", anonimo, {"url": _montar_caminho(caminho, get_flat_dependant(rota.dependant).path_params)})]
    tentativas += [(nome, logado, argumentos) for nome, argumentos in variantes(metodo, caminho, rota)]

    for nome, http, argumentos in tentativas:
        resposta = http.request(metodo, **argumentos)
        # Erro de banco no meio da requisição deixa a transação do teste
        # abortada; volta ao último SAVEPOINT para a próxima tentativa valer.
        sessao.rollback()
        if resposta.status_code < 400:
            continue
        erros_vistos += 1
        for rotulo, trecho in vazamentos(resposta):
            achados.append(f"  [{nome}] HTTP {resposta.status_code}: {rotulo} em …{trecho}…")

    assert not achados, f"{metodo} {caminho} vazou detalhe técnico:\n" + "\n".join(achados)
    if not erros_vistos:
        # Sem parâmetro, sem corpo e sem sessão exigida: não há erro que dê
        # para provocar de fora. Aparece como pulado, com o nome, para ninguém
        # ler o verde como conferido.
        pytest.skip(f"{metodo} {caminho}: nenhum erro provocável de fora")
