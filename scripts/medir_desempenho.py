"""Tarefa 77: todas as medições de desempenho, comparadas com limiares fixos.

Feito para rodar no dia seguinte à carga dos 11.569 produtos reais e responder
em um minuto se está bom. Sai com código 1 se algum limiar estourar.

    python scripts/medir_desempenho.py
    python scripts/medir_desempenho.py --salvar antes.json
    python scripts/medir_desempenho.py --comparar antes.json

Como mede: sobe a aplicação de verdade (uvicorn) numa thread DESTE processo,
numa porta livre de 127.0.0.1, e faz as requisições por HTTP. Por estar no
mesmo processo, o evento do SQLAlchemy enxerga cada consulta que o servidor
dispara, com o tempo de cada uma. Precisa do mesmo DATABASE_URL da aplicação.
No servidor: `docker compose exec api python scripts/medir_desempenho.py`.

Cada rota recebe requisições de aquecimento (conexões do pool, cache do
planejador) e depois é medida N vezes. O tempo é o da requisição inteira, visto
pelo cliente HTTP. As rotas do painel pagam uma consulta de sessão do admin
(`admin_sessoes`): ela ENTRA na contagem, e aparece separada numa coluna.

O script abre uma sessão de admin pelo serviço (não pelo login, para não gastar
argon2 nem o limite de tentativas) e a revoga no fim.
"""

import argparse
import json
import math
import os
import socket
import statistics
import sys
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import uvicorn  # noqa: E402
from sqlalchemy import event, func, select  # noqa: E402

from vip_api.banco import SessaoLocal, engine  # noqa: E402
from vip_api.modelos.admin import Administrador  # noqa: E402
from vip_api.modelos.catalogo import Categoria, Marca, Produto  # noqa: E402
from vip_api.principal import app  # noqa: E402
from vip_api.servicos.admin import criar_sessao_admin, encerrar_sessao_admin  # noqa: E402

# ======================================================================
# LIMIARES
# ======================================================================

# Referência do plano (tarefa 77): nenhuma consulta principal acima de meio
# segundo. Vale LITERALMENTE para cada instrução SQL, em qualquer rota.
MAIOR_CONSULTA_MS = 500

# Rotas públicas: p95 da requisição inteira até 300 ms. A tarefa 83 dá 3 s
# para os primeiros produtos aparecerem num celular em 4G, e quase todo esse
# tempo é rede e imagem. Um backend acima de 10% disso vira o gargalo que o
# visitante percebe. Com 5 mil produtos a medição local dá ~25 ms de p95, então
# há folga de dez vezes para o servidor de produção e para o catálogo maior.
P95_PUBLICO_MS = 300

# Busca por termo comum ("bolsa", "preta"): é a consulta mais cara do catálogo,
# LIKE de substring sobre o índice trigram, e o termo comum casa com milhares
# de linhas. Ganha o teto do plano, e não o das outras rotas públicas: quem
# digita na busca espera um pouco mais do que quem abre a home.
P95_BUSCA_MS = 500

# Painel: p95 até 500 ms, o teto do plano. É ferramenta interna, de duas
# contas, usada sentado no computador. Meio segundo ainda é "respondeu".
P95_PAINEL_MS = 500

# Quantas consultas cada requisição pode fazer. O número é fixo por desenho
# (JOIN, não consulta por item) e é o medido hoje. Se crescer com o volume de
# dados, é N+1, e N+1 com 11 mil produtos é o que derruba a rota.
# A travessia usa o limite por página: 2 na primeira (COUNT + página) e 1 nas
# seguintes, porque o total viaja dentro do cursor. Os tetos de cada rota
# estão em `_alvos`, ao lado da medição.

AQUECIMENTO = 3
RODADAS = 20


@dataclass
class Medicao:
    nome: str
    caminho: str
    parametros: dict = field(default_factory=dict)
    painel: bool = False
    p95_ms: int = P95_PUBLICO_MS
    consultas_max: int = 0


@dataclass
class Resultado:
    nome: str
    alvo: str
    consultas: int
    sessao_admin: int
    p50_ms: float
    p95_ms: float
    maior_consulta_ms: float
    # Soma do tempo das consultas de uma requisição (mediana). Separa "o banco
    # ficou lento" de "o Python em volta ficou lento" quando o p50 sobe.
    sql_p50_ms: float
    descricao: str
    limite_p95_ms: int
    limite_consultas: int
    estouros: list[str]


# ======================================================================
# Coleta
# ======================================================================

_CONTROLE = ("SAVEPOINT", "RELEASE", "ROLLBACK", "BEGIN", "COMMIT")
_trava = threading.Lock()
_consultas: list[tuple[str, float]] = []


@event.listens_for(engine, "before_cursor_execute")
def _antes(conexao, cursor, instrucao, parametros, contexto, muitos):
    conexao.info.setdefault("_inicios", []).append(time.perf_counter())


@event.listens_for(engine, "after_cursor_execute")
def _depois(conexao, cursor, instrucao, parametros, contexto, muitos):
    decorrido = (time.perf_counter() - conexao.info["_inicios"].pop()) * 1000
    limpa = " ".join(instrucao.split())
    if not limpa.upper().startswith(_CONTROLE):
        with _trava:
            _consultas.append((limpa, decorrido))


def _limpar_coleta() -> None:
    with _trava:
        _consultas.clear()


def _coletadas() -> list[tuple[str, float]]:
    # O fechamento da sessão do banco pode terminar logo depois da resposta.
    time.sleep(0.02)
    with _trava:
        return list(_consultas)


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _subir_servidor(porta: int) -> None:
    servidor = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="warning", access_log=False)
    )
    threading.Thread(target=servidor.run, daemon=True).start()
    for _ in range(200):
        if servidor.started:
            return
        time.sleep(0.05)
    sys.exit("o servidor de medição não subiu")


def _get(base: str, caminho: str, parametros: dict, cookie: str | None):
    url = f"{base}/api/v1{caminho}"
    if parametros:
        url += "?" + urllib.parse.urlencode(parametros)
    requisicao = urllib.request.Request(url)
    if cookie:
        requisicao.add_header("Cookie", cookie)
    inicio = time.perf_counter()
    with urllib.request.urlopen(requisicao, timeout=60) as resposta:
        corpo = json.loads(resposta.read().decode("utf-8"))
        status = resposta.status
    return status, corpo, (time.perf_counter() - inicio) * 1000


def _p95(valores: list[float]) -> float:
    ordenados = sorted(valores)
    return ordenados[max(0, math.ceil(len(ordenados) * 0.95) - 1)]


def _descrever(corpo) -> str:
    if isinstance(corpo, dict) and "paginacao" in corpo:
        return f"{len(corpo['dados'])} de {corpo['paginacao']['total']}"
    if isinstance(corpo, dict) and "totalProdutos" in corpo:
        return f"{corpo['totalProdutos']} produtos, {len(corpo['porMarca'])} marcas"
    if isinstance(corpo, dict) and "destaques" in corpo:
        return f"{len(corpo['banners'])} banners, {len(corpo['destaques'])} destaques, {len(corpo['marcas'])} marcas"
    if isinstance(corpo, list):
        return f"{len(corpo)} itens"
    if isinstance(corpo, dict) and "codigo" in corpo:
        return f"{len(corpo.get('imagens', []))} imagens, {len(corpo.get('variacoes', []))} variações"
    return ""


def medir(base: str, m: Medicao, cookie: str | None, rodadas: int) -> Resultado:
    for _ in range(AQUECIMENTO):
        _get(base, m.caminho, m.parametros, cookie if m.painel else None)

    tempos, contagens, de_sessao, maiores, somas = [], [], [], [], []
    corpo = None
    for _ in range(rodadas):
        _limpar_coleta()
        status, corpo, ms = _get(base, m.caminho, m.parametros, cookie if m.painel else None)
        feitas = _coletadas()
        if status != 200:
            sys.exit(f"{m.nome}: HTTP {status}")
        tempos.append(ms)
        contagens.append(len(feitas))
        de_sessao.append(sum(1 for sql, _ in feitas if "admin_sessoes" in sql))
        maiores.append(max((t for _, t in feitas), default=0.0))
        somas.append(sum(t for _, t in feitas))

    r = Resultado(
        nome=m.nome,
        alvo=m.caminho + ("?" + urllib.parse.urlencode(m.parametros) if m.parametros else ""),
        consultas=max(contagens),
        sessao_admin=max(de_sessao),
        p50_ms=statistics.median(tempos),
        p95_ms=_p95(tempos),
        maior_consulta_ms=max(maiores),
        sql_p50_ms=statistics.median(somas),
        descricao=_descrever(corpo),
        limite_p95_ms=m.p95_ms,
        limite_consultas=m.consultas_max,
        estouros=[],
    )
    if r.p95_ms > m.p95_ms:
        r.estouros.append(f"p95 {r.p95_ms:.0f} ms > {m.p95_ms} ms")
    if r.maior_consulta_ms > MAIOR_CONSULTA_MS:
        r.estouros.append(f"consulta de {r.maior_consulta_ms:.0f} ms > {MAIOR_CONSULTA_MS} ms")
    if r.consultas > m.consultas_max:
        r.estouros.append(f"{r.consultas} consultas > {m.consultas_max}")
    return r


def travessia(base: str, ordem: str, visiveis: set[int]) -> Resultado:
    """Percorre o catálogo inteiro pelo cursor e confere contra o banco."""
    ids, tempos, contagens, maiores, somas = [], [], [], [], []
    cursor, total = None, None
    while True:
        parametros = {"ordem": ordem, "porPagina": 24}
        if cursor:
            parametros["cursor"] = cursor
        _limpar_coleta()
        _, pagina, ms = _get(base, "/produtos", parametros, None)
        feitas = _coletadas()
        tempos.append(ms)
        # A primeira página conta o total (2 consultas); as demais, 1.
        contagens.append(len(feitas) - (1 if cursor is None else 0))
        maiores.append(max((t for _, t in feitas), default=0.0))
        somas.append(sum(t for _, t in feitas))
        total = pagina["paginacao"]["total"] if total is None else total
        ids.extend(item["id"] for item in pagina["dados"])
        cursor = pagina["paginacao"].get("proximoCursor")
        if not cursor or len(tempos) > 10_000:
            break

    unicos = set(ids)
    problemas = []
    if len(ids) != len(unicos):
        problemas.append(f"{len(ids) - len(unicos)} repetidos")
    if unicos != visiveis:
        problemas.append(f"{len(visiveis - unicos)} faltando, {len(unicos - visiveis)} sobrando")
    if total != len(visiveis):
        problemas.append(f"total informado {total} ≠ {len(visiveis)} no banco")

    r = Resultado(
        nome=f"travessia ordem={ordem}",
        alvo=f"/produtos?ordem={ordem}&porPagina=24, {len(tempos)} páginas",
        consultas=max(contagens),
        sessao_admin=0,
        p50_ms=statistics.median(tempos),
        p95_ms=_p95(tempos),
        maior_consulta_ms=max(maiores),
        sql_p50_ms=statistics.median(somas),
        descricao=f"{len(unicos)} ids, {sum(tempos) / 1000:.1f} s no total"
        + (": " + "; ".join(problemas) if problemas else ", sem repetido nem faltando"),
        limite_p95_ms=P95_PUBLICO_MS,
        limite_consultas=1,
        estouros=list(problemas),
    )
    if r.p95_ms > P95_PUBLICO_MS:
        r.estouros.append(f"p95 por página {r.p95_ms:.0f} ms > {P95_PUBLICO_MS} ms")
    if r.maior_consulta_ms > MAIOR_CONSULTA_MS:
        r.estouros.append(f"consulta de {r.maior_consulta_ms:.0f} ms > {MAIOR_CONSULTA_MS} ms")
    if r.consultas > 1:
        r.estouros.append(f"{r.consultas} consultas por página > 1")
    return r


# ======================================================================
# O que medir
# ======================================================================


# Desde a 0015 a categoria não tem coleção: o roteiro mede o público feminino.
COLECAO_DO_ROTEIRO = "feminino"


def _alvos(sessao) -> tuple[list[Medicao], set[int]]:
    """Os parâmetros saem do próprio banco: a maior e a menor marca, um produto
    da maior marca numa categoria cheia, a última página do painel. Assim o
    roteiro serve para qualquer catálogo, inclusive o real."""
    por_marca = sessao.execute(
        select(Marca.id, Marca.slug, func.count(Produto.id).label("n"))
        .join(Produto, Produto.marca_id == Marca.id)
        .group_by(Marca.id)
        .order_by(func.count(Produto.id).desc())
    ).all()
    maior, menor = por_marca[0], por_marca[-1]

    categoria = sessao.execute(
        select(Categoria.id, Categoria.slug)
        .join(Produto, Produto.categoria_id == Categoria.id)
        .group_by(Categoria.id)
        .order_by(func.count(Produto.id).desc())
        .limit(1)
    ).one()

    codigo = sessao.scalar(
        select(Produto.codigo)
        .where(
            Produto.marca_id == maior.id,
            Produto.categoria_id == categoria.id,
            Produto.status != "oculto",
        )
        .order_by(Produto.id)
        .limit(1)
    )
    total = sessao.scalar(select(func.count()).select_from(Produto))
    visiveis = set(sessao.scalars(select(Produto.id).where(Produto.status != "oculto")))

    publico = [
        Medicao("produtos: 1ª página", "/produtos", consultas_max=2),
        Medicao("produtos: maior marca", "/produtos", {"marca": maior.slug}, consultas_max=3),
        Medicao("produtos: menor marca, por nome", "/produtos", {"marca": menor.slug, "ordem": "nome"}, consultas_max=3),
        Medicao(
            "produtos: categoria mais cheia",
            "/produtos",
            {"colecao": COLECAO_DO_ROTEIRO, "categoria": categoria.slug},
            consultas_max=4,
        ),
        Medicao("produtos: busca 'bolsa'", "/produtos", {"busca": "bolsa"}, p95_ms=P95_BUSCA_MS, consultas_max=4),
        Medicao("produtos: busca 'preta'", "/produtos", {"busca": "preta"}, p95_ms=P95_BUSCA_MS, consultas_max=4),
        Medicao("produtos: busca por código", "/produtos", {"busca": codigo}, consultas_max=1),
        Medicao("produto: detalhe", f"/produtos/{codigo}", consultas_max=3),
        Medicao("produto: relacionados", f"/produtos/{codigo}/relacionados", consultas_max=2),
        Medicao("marcas", "/marcas", consultas_max=1),
        Medicao("categorias da coleção", f"/colecoes/{COLECAO_DO_ROTEIRO}/categorias", consultas_max=2),
        Medicao("home", "/home", consultas_max=4),
    ]
    painel = [
        Medicao("painel: produtos 1ª página", "/admin/produtos", painel=True, p95_ms=P95_PAINEL_MS, consultas_max=3),
        Medicao(
            "painel: produtos busca 'bolsa'",
            "/admin/produtos",
            {"busca": "bolsa"},
            painel=True,
            p95_ms=P95_PAINEL_MS,
            consultas_max=3,
        ),
        Medicao(
            "painel: produtos da maior marca",
            "/admin/produtos",
            {"marcaId": maior.id},
            painel=True,
            p95_ms=P95_PAINEL_MS,
            consultas_max=3,
        ),
        Medicao(
            "painel: produtos última página",
            "/admin/produtos",
            {"pagina": max(1, math.ceil(total / 50))},
            painel=True,
            p95_ms=P95_PAINEL_MS,
            consultas_max=3,
        ),
        Medicao("painel: resumo", "/admin/resumo", painel=True, p95_ms=P95_PAINEL_MS, consultas_max=4),
        Medicao("painel: clientes", "/admin/clientes", painel=True, p95_ms=P95_PAINEL_MS, consultas_max=3),
    ]
    return publico + painel, visiveis


# ======================================================================
# Relatório
# ======================================================================


def imprimir(resultados: list[Resultado], contexto: dict, anterior: dict | None) -> None:
    print(
        f"\nbanco: {contexto['produtos']} produtos ({contexto['visiveis']} visíveis), "
        f"{contexto['marcas']} marcas, maior com {contexto['maior_marca']}, menor com {contexto['menor_marca']}"
    )
    if anterior:
        a = anterior["contexto"]
        print(f"antes: {a['produtos']} produtos ({a['visiveis']} visíveis), maior marca com {a['maior_marca']}")
    print(
        f"limiares: consulta ≤ {MAIOR_CONSULTA_MS} ms · p95 público ≤ {P95_PUBLICO_MS} ms · "
        f"busca ≤ {P95_BUSCA_MS} ms · painel ≤ {P95_PAINEL_MS} ms · consultas ≤ teto por rota"
    )
    print("consultas: total por requisição, com a sessão do admin INCLUÍDA; entre parênteses, quantas são dela\n")

    print("tempos em ms · SQL = soma das consultas da requisição (mediana) · MAIOR = a consulta mais lenta vista")
    if anterior:
        print("ANTES = a medição comparada; a variação é do p50, que oscila menos que o p95 numa máquina de desenvolvimento")
    print()

    antes = {r["nome"]: r for r in (anterior or {}).get("resultados", [])}
    cab = f"{'MEDIÇÃO':<36} {'CONSULTAS':>9} {'p50':>6} {'p95':>6} {'SQL':>5} {'MAIOR':>6}"
    if anterior:
        cab += f" │ {'p50':>6} {'p95':>6} {'SQL':>5} {'VAR p50':>7}"
    cab += f" │ {'LIMITE':>6}  RESULTADO"
    print(cab)
    print("-" * (len(cab) + 20))
    for r in resultados:
        consultas = f"{r.consultas} ({r.sessao_admin})" if r.sessao_admin else str(r.consultas)
        linha = (
            f"{r.nome:<36} {consultas:>9} {r.p50_ms:>6.1f} {r.p95_ms:>6.1f} "
            f"{r.sql_p50_ms:>5.1f} {r.maior_consulta_ms:>6.1f}"
        )
        if anterior:
            a = antes.get(r.nome)
            if a:
                variacao = f"{r.p50_ms / a['p50_ms']:.1f}×" if a["p50_ms"] else "—"
                linha += f" │ {a['p50_ms']:>6.1f} {a['p95_ms']:>6.1f} {a.get('sql_p50_ms', 0):>5.1f} {variacao:>7}"
            else:
                linha += f" │ {'—':>6} {'—':>6} {'—':>5} {'—':>7}"
        linha += f" │ {r.limite_p95_ms:>6}  " + ("ESTOUROU: " + "; ".join(r.estouros) if r.estouros else "ok")
        print(linha)
        print(f"{'':<36}   {r.descricao}")


def main() -> int:
    analisador = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    analisador.add_argument("--rodadas", type=int, default=RODADAS)
    analisador.add_argument("--salvar", help="grava os resultados em JSON, para comparar depois")
    analisador.add_argument("--comparar", help="JSON de uma medição anterior, para pôr lado a lado")
    analisador.add_argument("--email-admin", default=None, help="admin usado nas rotas do painel (padrão: o primeiro ativo)")
    argumentos = analisador.parse_args()

    porta = _porta_livre()
    base = f"http://127.0.0.1:{porta}"
    _subir_servidor(porta)

    with SessaoLocal() as sessao:
        consulta_admin = select(Administrador).where(Administrador.ativo.is_(True))
        if argumentos.email_admin:
            consulta_admin = consulta_admin.where(Administrador.email == argumentos.email_admin)
        administrador = sessao.scalars(consulta_admin.order_by(Administrador.id).limit(1)).first()
        if administrador is None:
            sys.exit("nenhum administrador ativo para medir o painel (scripts/criar_admin.py)")
        medicoes, visiveis = _alvos(sessao)
        contagem_marcas = sessao.execute(
            select(func.count(Produto.id)).group_by(Produto.marca_id).order_by(func.count(Produto.id).desc())
        ).scalars().all()
        contexto = {
            "produtos": sessao.scalar(select(func.count()).select_from(Produto)),
            "visiveis": len(visiveis),
            "marcas": len(contagem_marcas),
            "maior_marca": contagem_marcas[0],
            "menor_marca": contagem_marcas[-1],
        }
        token = criar_sessao_admin(sessao, administrador, ip="127.0.0.1", user_agent="scripts/medir_desempenho.py")

    cookie = f"vip_sessao_admin={token}"
    resultados = []
    try:
        for ordem in ("recentes", "nome"):
            resultados.append(travessia(base, ordem, visiveis))
        for medicao in medicoes:
            resultados.append(medir(base, medicao, cookie, argumentos.rodadas))
    finally:
        with SessaoLocal() as sessao:
            encerrar_sessao_admin(sessao, token)

    anterior = None
    if argumentos.comparar:
        with open(argumentos.comparar, encoding="utf-8") as arquivo:
            anterior = json.load(arquivo)
    imprimir(resultados, contexto, anterior)

    if argumentos.salvar:
        with open(argumentos.salvar, "w", encoding="utf-8") as arquivo:
            json.dump({"contexto": contexto, "resultados": [asdict(r) for r in resultados]}, arquivo, ensure_ascii=False, indent=2)

    estouros = [r for r in resultados if r.estouros]
    print(f"\n{len(resultados) - len(estouros)} de {len(resultados)} medições dentro dos limiares.")
    if estouros:
        print("ESTOURARAM: " + ", ".join(r.nome for r in estouros))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
