"""Confere a API implementada contra o contrato versionado em docs/contrato-api-v1.json.

O contrato mora num arquivo, não aqui dentro: mudança no contrato é commit, e a
auditoria compara a aplicação com algo que ela não escreveu.

O arquivo diz de onde veio (`origem`). O estado normal é `"documento"` — o
arquivo extraído do PDF do contrato (`docs/contrato-api-v1.pdf`), endpoint por
endpoint, com o nome do handler que o contrato previa. Enquanto for
`"reconstrucao"` (uma transcrição feita sem o documento em mãos, montada a
partir do que o próprio repositório cita), a auditoria avisa em toda execução
e não conclui nada — ver o campo `observacao` do arquivo.

O contrato foi escrito para um backend em Node; o handler real é Python, e o
projeto usa nome curto dentro do módulo (`listar`, `criar`, `editar`) em vez de
repetir o recurso inteiro no nome (`listarProdutosAdmin`). Por isso o nome do
handler REAL quase sempre difere do nome PREVISTO — a auditoria mostra os
dois lado a lado, mas a divergência de nome é só informação, nunca falha.

    python scripts/auditoria_contrato.py

Código de saída:
    0  tudo confere contra um contrato com origem "documento";
    1  falha concreta: rota do contrato faltando, rota congelada existindo,
       ou rota implementada fora do contrato sem justificativa registrada;
    2  nada falhou, mas a conferência não vale como prova: o arquivo ainda é
       uma reconstrução, ou (quando o arquivo traz essa contagem) o número de
       entradas não bate com o que ele mesmo declara vir do documento.
"""

import json
import os
import pathlib
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fastapi.routing import APIRoute  # noqa: E402

from vip_api.principal import app  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent
ARQUIVO_CONTRATO = RAIZ / "docs" / "contrato-api-v1.json"

# O prefixo é o mesmo da aplicação inteira (vip_api/principal.py); o arquivo
# do contrato não precisa repeti-lo.
PREFIXO = "/api/v1"

# Desvios da IMPLEMENTAÇÃO em relação ao contrato: rotas que existem sem estar
# nele. Não pertencem ao arquivo do contrato, que descreve o documento — são
# decisão do projeto, registradas aqui com a justificativa.
FORA_DO_CONTRATO = {
    ("GET", "/health"): "infraestrutura (docker healthcheck); não é rota de produto",
    ("GET", "/admin/eu"): "tarefa 53; registrada em docs/para-o-frontend.md",
    ("PATCH", "/admin/banners/ordem"): "tarefa 57 (ordem contígua exige rota); registrada em docs/para-o-frontend.md",
    # Vocabulário de cores (revisão 0007): pedido do cliente em 21/09/2026,
    # posterior ao contrato v1.0. Registradas em docs/para-o-frontend.md.
    ("GET", "/cores"): "revisão 0007 (paleta do filtro ?cor=); registrada em docs/para-o-frontend.md",
    ("GET", "/admin/cores"): "revisão 0007 (CRUD da paleta); registrada em docs/para-o-frontend.md",
    ("POST", "/admin/cores"): "revisão 0007 (CRUD da paleta); registrada em docs/para-o-frontend.md",
    ("PATCH", "/admin/cores/{corId}"): "revisão 0007 (CRUD da paleta); registrada em docs/para-o-frontend.md",
    ("DELETE", "/admin/cores/{corId}"): "revisão 0007 (CRUD da paleta); registrada em docs/para-o-frontend.md",
}

# Nenhuma rota implementada pode casar com estes padrões: é o VOCABULÁRIO do
# tema congelado da seção 05 (acesso compartilhado e fila de aprovação), não
# só os seis caminhos exatos do contrato — pega também uma implementação
# equivalente pendurada num caminho diferente.
PADROES_CONGELADOS = (
    re.compile(r"/acesso"),
    re.compile(r"/solicit"),
    re.compile(r"/aprovac"),
    re.compile(r"/fila"),
    re.compile(r"/configuracao"),
)


def carregar_contrato() -> dict:
    return json.loads(ARQUIVO_CONTRATO.read_text(encoding="utf-8"))


# Onde se procura evidência independente de cada entrada: os documentos que
# descrevem a API e o código. Ficam de fora o próprio arquivo do contrato e os
# relatórios que CITAM a auditoria (pendências, fechamentos) — senão a
# evidência de uma rota duvidosa passa a ser o relatório que a apontou.
#
# Com o documento em mãos isto deixa de ser a prova de que a rota é do
# contrato (o arquivo já é essa prova) — vira uma conferência à parte: toda
# rota do contrato também está DOCUMENTADA em algum lugar do próprio código
# ou dos outros docs, não só citada no JSON.
FONTES_DE_EVIDENCIA = ("modelagem-banco.md", "para-o-frontend.md", "limitacoes-conhecidas.md")


def _texto_do_repositorio() -> str:
    partes = [(RAIZ / "docs" / nome).read_text(encoding="utf-8") for nome in FONTES_DE_EVIDENCIA]
    partes += [caminho.read_text(encoding="utf-8") for caminho in (RAIZ / "src").rglob("*.py")]
    return "\n".join(partes)


def tem_evidencia(repositorio: str, metodo: str, rota: str) -> bool:
    """`{produtoId}` e `:id` são a mesma coisa para esta busca."""
    partes = [re.escape(pedaco) for pedaco in re.split(r"\{[^}]+\}", rota)]
    corpo = "[^ `)]+".join(partes)
    return bool(re.search(rf"{metodo}\s+`?(/api/v1)?{corpo}", repositorio, re.IGNORECASE))


def implementadas(prefixo: str) -> dict[tuple[str, str], str]:
    """(método, rota sem prefixo) -> nome da função que atende a rota.

    Lido do roteador e conferido contra o OpenAPI: rota que o FastAPI registra
    mas esconde do esquema (include_in_schema=False) também conta."""
    achadas = {}
    for rota in app.routes:
        if not isinstance(rota, APIRoute):
            continue
        curto = rota.path[len(prefixo):] if rota.path.startswith(prefixo) else rota.path
        for metodo in rota.methods - {"HEAD", "OPTIONS"}:
            achadas[(metodo, curto)] = rota.endpoint.__name__

    no_openapi = {
        (metodo.upper(), caminho[len(prefixo):] if caminho.startswith(prefixo) else caminho)
        for caminho, operacoes in app.openapi()["paths"].items()
        for metodo in operacoes
    }
    for chave in sorted(set(achadas) - no_openapi):
        print(f"  ! {chave[0]} {chave[1]} existe no roteador mas não aparece no OpenAPI")
    return achadas


def main() -> int:
    contrato = carregar_contrato()
    entradas = contrato["endpoints"]
    reais = implementadas(PREFIXO)
    repositorio = _texto_do_repositorio()
    falhas: list[str] = []
    handlers_divergentes: list[str] = []

    print("=" * 120)
    print(f"CONTRATO v{contrato['versao']} ({ARQUIVO_CONTRATO.relative_to(RAIZ)}, origem: {contrato['origem']}) × IMPLEMENTADO")
    print("=" * 120)
    if fonte := contrato.get("fonte"):
        print(fonte)
    if contrato["origem"] != "documento":
        print("AVISO: o arquivo é uma RECONSTRUÇÃO, não o documento. Ver o campo 'observacao' do arquivo.")

    print(f"\n{'MÉTODO':<7} {'ROTA':<44} {'SEÇÃO':<6} {'SITUAÇÃO':<12} {'RESULTADO':<17} {'HANDLER (real)':<24} {'HANDLER (contrato)':<24} EVIDÊNCIA")
    print(f"{'-' * 7} {'-' * 44} {'-' * 6} {'-' * 12} {'-' * 17} {'-' * 24} {'-' * 24} {'-' * 14}")

    contagem = {"implementadas": 0, "faltando": 0, "congeladas_ok": 0, "sem_evidencia": []}
    for e in entradas:
        chave = (e["metodo"], e["rota"])
        handler_real = reais.get(chave)
        if e["situacao"] == "congelada":
            if handler_real:
                resultado = "!!! EXISTE !!!"
                falhas.append(f"congelada existe: {e['metodo']} {e['rota']}")
            else:
                resultado = "não existe (ok)"
                contagem["congeladas_ok"] += 1
        elif handler_real:
            resultado = "implementada"
            contagem["implementadas"] += 1
        else:
            resultado = "FALTANDO"
            contagem["faltando"] += 1
            falhas.append(f"faltando: {e['metodo']} {e['rota']}")

        # Divergência de NOME nunca é falha — é o esperado (contrato em Node,
        # handler em Python) — mas fica registrada como informação.
        if handler_real and handler_real != e["handler"]:
            handlers_divergentes.append(f"{e['metodo']} {e['rota']}: {handler_real} (contrato: {e['handler']})")

        evidencia = "doc/código" if tem_evidencia(repositorio, *chave) else "só o contrato"
        if evidencia == "só o contrato" and e["situacao"] == "implementar":
            contagem["sem_evidencia"].append(f"{e['metodo']} {e['rota']}")
        print(
            f"{e['metodo']:<7} {e['rota']:<44} {e['secao']:<6} {e['situacao']:<12} "
            f"{resultado:<17} {(handler_real or '—'):<24} {e['handler']:<24} {evidencia}"
        )

    notas = [(e["metodo"], e["rota"], e["nota"]) for e in entradas if e.get("nota")]
    if notas:
        print("\nnotas do contrato:")
        for metodo, rota, nota in notas:
            print(f"    {metodo} {rota}: {nota}")

    do_contrato = {(e["metodo"], e["rota"]) for e in entradas}
    extras = sorted(set(reais) - do_contrato)
    print(f"\n{'MÉTODO':<7} {'ROTA':<44} FORA DO CONTRATO — JUSTIFICATIVA")
    print(f"{'-' * 7} {'-' * 44} {'-' * 56}")
    for metodo, rota in extras:
        motivo = FORA_DO_CONTRATO.get((metodo, rota))
        if motivo is None:
            motivo = "!!! SEM JUSTIFICATIVA REGISTRADA !!!"
            falhas.append(f"fora do contrato sem justificativa: {metodo} {rota}")
        print(f"{metodo:<7} {rota:<44} {motivo}")

    print("\n--- seção 05 (congelada): nenhuma rota do tema pode existir ---")
    vazando = [f"{m} {c}" for (m, c) in reais if any(p.search(c) for p in PADROES_CONGELADOS)]
    falhas.extend(f"tema congelado exposto: {rota}" for rota in vazando)
    print(f"    rotas com /acesso, /solicit, /aprovac, /fila ou /configuracao: {vazando or 'nenhuma'}")

    a_implementar = sum(1 for e in entradas if e["situacao"] == "implementar")
    congeladas = len(entradas) - a_implementar
    declarado = contrato.get("endpoints_declarados_no_documento")
    print("\n--- contagem ---")
    print(f"    entradas no arquivo ......... {len(entradas)} ({a_implementar} a implementar, {congeladas} congeladas)")
    if declarado is not None:
        print(f"    declaradas no documento ..... {declarado}")
    print(f"    implementadas na aplicação .. {len(reais)}")
    print(f"    do contrato, implementadas .. {contagem['implementadas']}")
    print(f"    do contrato, faltando ....... {contagem['faltando']}")
    print(f"    congeladas ausentes (ok) .... {contagem['congeladas_ok']}")
    print(f"    fora do contrato ............ {len(extras)}")
    print(f"    handlers com nome IGUAL ao previsto ... {contagem['implementadas'] - len(handlers_divergentes)} de {contagem['implementadas']}")
    print(f"    handlers com nome DIFERENTE (Node → Python, esperado) . {len(handlers_divergentes)} de {contagem['implementadas']}")
    if contagem["sem_evidencia"]:
        print(f"\n    entradas do contrato sem evidência fora do próprio arquivo ({len(contagem['sem_evidencia'])}):")
        for rota in contagem["sem_evidencia"]:
            print(f"      {rota}")

    incertezas = []
    if contrato["origem"] != "documento":
        incertezas.append("o arquivo é uma reconstrução")
    if declarado is not None and declarado != len(entradas):
        incertezas.append(f"o arquivo tem {len(entradas)} entradas e ele mesmo declara {declarado}")

    print("\n--- resultado ---")
    if falhas:
        for falha in falhas:
            print(f"    FALHA: {falha}")
        return 1
    if incertezas:
        for incerteza in incertezas:
            print(f"    INCONCLUSIVO: {incerteza}")
        return 2
    print("    OK: a aplicação confere com o contrato")
    return 0


if __name__ == "__main__":
    sys.exit(main())
