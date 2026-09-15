"""Confere a API implementada contra o contrato de API v1.0.

AVISO QUE VALE PARA A TABELA INTEIRA: **o contrato v1.0 não está neste
repositório**. A coluna "contrato" abaixo é uma RECONSTRUÇÃO, montada a partir
do que o próprio repositório registra sobre ele — docs/modelagem-banco.md, que
cita endpoint por endpoint ao justificar cada coluna e cada índice,
docs/para-o-frontend.md e os comentários de código que citam seção por seção.
Onde a reconstrução é incerta, a linha diz.

Isso é, em si, o primeiro achado desta auditoria: a fonte da verdade da API não
está versionada junto com o código. Ver docs/pendencias.md.

    python scripts/auditoria_contrato.py
"""

import os
import pathlib
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vip_api.principal import app  # noqa: E402

PREFIXO = "/api/v1"

# (método, caminho sem prefixo, grupo, situação esperada)
# situação: "implementar" = o contrato pede e a Fatia 0-4 devia entregar;
#           "congelada"   = seção 05, parada por decisão do cliente.
CONTRATO = [
    # --- catálogo público (seção 02) ---
    ("GET", "/produtos", "catálogo", "implementar"),
    ("GET", "/produtos/{codigo}", "catálogo", "implementar"),
    ("GET", "/produtos/{codigo}/relacionados", "catálogo", "implementar"),
    ("GET", "/marcas", "catálogo", "implementar"),
    ("GET", "/colecoes", "catálogo", "implementar"),
    ("GET", "/colecoes/{slug}/categorias", "catálogo", "implementar"),
    ("GET", "/home", "catálogo", "implementar"),
    # --- área do cliente (seção 03) ---
    ("POST", "/clientes/identificar", "cliente", "implementar"),
    ("GET", "/clientes/eu", "cliente", "implementar"),
    ("PATCH", "/clientes/eu", "cliente", "implementar"),
    ("POST", "/clientes/sair", "cliente", "implementar"),
    ("GET", "/favoritos", "cliente", "implementar"),
    ("POST", "/favoritos", "cliente", "implementar"),
    ("DELETE", "/favoritos/{produtoId}", "cliente", "implementar"),
    ("GET", "/carrinho", "cliente", "implementar"),
    ("POST", "/carrinho", "cliente", "implementar"),
    ("PATCH", "/carrinho/{itemId}", "cliente", "implementar"),
    ("DELETE", "/carrinho/{itemId}", "cliente", "implementar"),
    ("POST", "/selecoes", "cliente", "implementar"),
    ("GET", "/selecoes", "cliente", "implementar"),
    # --- painel: sessão (seção 04) ---
    ("POST", "/admin/sessao", "painel", "implementar"),
    ("DELETE", "/admin/sessao", "painel", "implementar"),
    # --- painel: produtos (seção 4.2) ---
    ("GET", "/admin/produtos", "painel", "implementar"),
    ("GET", "/admin/produtos/{produtoId}", "painel", "implementar"),
    ("POST", "/admin/produtos", "painel", "implementar"),
    ("PATCH", "/admin/produtos/{produtoId}", "painel", "implementar"),
    ("DELETE", "/admin/produtos/{produtoId}", "painel", "implementar"),
    ("POST", "/admin/produtos/{produtoId}/duplicar", "painel", "implementar"),
    ("PATCH", "/admin/produtos/lote", "painel", "implementar"),
    ("POST", "/admin/produtos/{produtoId}/imagens", "painel", "implementar"),
    ("PATCH", "/admin/produtos/{produtoId}/imagens/ordem", "painel", "implementar"),
    ("DELETE", "/admin/imagens/{imagemId}", "painel", "implementar"),
    ("PATCH", "/admin/produtos/{produtoId}/variacoes", "painel", "implementar"),
    # --- painel: catálogo de apoio (seção 06) ---
    ("GET", "/admin/marcas", "painel", "implementar"),
    ("POST", "/admin/marcas", "painel", "implementar"),
    ("PATCH", "/admin/marcas/{marcaId}", "painel", "implementar"),
    ("DELETE", "/admin/marcas/{marcaId}", "painel", "implementar"),
    ("GET", "/admin/categorias", "painel", "implementar"),
    ("POST", "/admin/categorias", "painel", "implementar"),
    ("PATCH", "/admin/categorias/{categoriaId}", "painel", "implementar"),
    ("DELETE", "/admin/categorias/{categoriaId}", "painel", "implementar"),
    ("GET", "/admin/banners", "painel", "implementar"),
    ("POST", "/admin/banners", "painel", "implementar"),
    ("PATCH", "/admin/banners/{bannerId}", "painel", "implementar"),
    ("DELETE", "/admin/banners/{bannerId}", "painel", "implementar"),
    ("PATCH", "/admin/destaques/produtos", "painel", "implementar"),
    ("PATCH", "/admin/destaques/categorias", "painel", "implementar"),
    # --- painel: consultas (seção 4.4) ---
    ("GET", "/admin/resumo", "painel", "implementar"),
    ("GET", "/admin/selecoes", "painel", "implementar"),
    ("GET", "/admin/selecoes/{selecaoId}", "painel", "implementar"),
    ("GET", "/admin/clientes", "painel", "implementar"),
    # --- controle de acesso (seção 05) — CONGELADAS por decisão do cliente ---
    # Os caminhos exatos não dá para afirmar sem o documento; o que importa
    # aqui é que NENHUMA rota deste tema exista na aplicação, e isso é
    # conferido por padrão logo abaixo, não por nome.
    ("GET", "/admin/acesso", "acesso (05)", "congelada"),
    ("PATCH", "/admin/acesso", "acesso (05)", "congelada"),
    ("POST", "/acesso/senha", "acesso (05)", "congelada"),
    ("GET", "/admin/solicitacoes", "acesso (05)", "congelada"),
    ("PATCH", "/admin/solicitacoes/{id}", "acesso (05)", "congelada"),
]

# Rotas implementadas que NÃO vêm do contrato v1.0, com a justificativa e onde
# ela está registrada.
FORA_DO_CONTRATO = {
    ("GET", "/health"): "infraestrutura (docker healthcheck); não é rota de produto",
    ("GET", "/admin/eu"): "tarefa 53; registrada em docs/para-o-frontend.md",
    ("POST", "/carrinho/migrar"): "tarefa 50; registrada em docs/para-o-frontend.md",
    (
        "PATCH",
        "/admin/banners/ordem",
    ): "tarefa 57 (ordem contígua exige rota); registrada em docs/para-o-frontend.md",
}

# Nenhuma rota pode casar com estes padrões: é o tema congelado da seção 05.
PADROES_CONGELADOS = (
    re.compile(r"/acesso"),
    re.compile(r"/solicitac"),
    re.compile(r"/aprovac"),
    re.compile(r"senha[-_]?compartilhada"),
)


def _texto_do_repositorio() -> str:
    """Tudo que o repositório escreve sobre a API, num texto só: é onde se
    procura a evidência de que uma rota veio mesmo do contrato."""
    raiz = pathlib.Path(__file__).resolve().parent.parent
    partes = []
    for caminho in list((raiz / "docs").glob("*.md")) + list(
        (raiz / "src").rglob("*.py")
    ):
        partes.append(caminho.read_text(encoding="utf-8"))
    return "\n".join(partes)


REPOSITORIO = _texto_do_repositorio()


def tem_evidencia(metodo: str, caminho: str) -> bool:
    """A rota aparece escrita em doc ou comentário do projeto?

    `{produtoId}` e `:id` são a mesma coisa para esta busca — o que interessa é
    se alguém já escreveu aquela rota em algum lugar, não como nomeou o
    parâmetro.
    """
    partes = [re.escape(pedaco) for pedaco in re.split(r"\{[^}]+\}", caminho)]
    corpo = "[^ `)]+".join(partes)
    padrao = re.compile(rf"{metodo}\s+`?(/api/v1)?{corpo}", re.IGNORECASE)
    return bool(padrao.search(REPOSITORIO))


def implementadas() -> dict[tuple[str, str], dict]:
    esquema = app.openapi()
    achadas = {}
    for caminho, operacoes in esquema["paths"].items():
        for metodo, operacao in operacoes.items():
            if metodo.upper() not in ("GET", "POST", "PATCH", "PUT", "DELETE"):
                continue
            curto = caminho[len(PREFIXO) :] if caminho.startswith(PREFIXO) else caminho
            achadas[(metodo.upper(), curto)] = {
                "caminho": caminho,
                "status": sorted(operacao.get("responses", {})),
            }
    return achadas


def main() -> None:
    reais = implementadas()
    do_contrato = {(m, c) for m, c, _, _ in CONTRATO}

    print("=" * 100)
    print("CONTRATO v1.0 (reconstruído) × IMPLEMENTADO")
    print("=" * 100)
    print(f"\n{'MÉTODO':<7} {'ROTA':<46} {'GRUPO':<12} {'SITUAÇÃO':<12} RESULTADO")
    print(f"{'-' * 7} {'-' * 46} {'-' * 12} {'-' * 12} {'-' * 18}")

    contados = {"bate": 0, "congelada ok": 0, "faltando": 0}
    for metodo, caminho, grupo, situacao in CONTRATO:
        existe = (metodo, caminho) in reais
        if situacao == "congelada":
            resultado = "NÃO EXISTE (ok)" if not existe else "!!! EXISTE !!!"
            contados["congelada ok"] += 1 if not existe else 0
        else:
            resultado = "implementada" if existe else "FALTANDO"
            contados["bate" if existe else "faltando"] += 1
        evidencia = "doc/código" if tem_evidencia(metodo, caminho) else "só o enunciado"
        print(
            f"{metodo:<7} {caminho:<46} {grupo:<12} {situacao:<11} {resultado:<16} {evidencia}"
        )

    extras = sorted(set(reais) - do_contrato)
    print(f"\n{'MÉTODO':<7} {'ROTA':<46} FORA DO CONTRATO — JUSTIFICATIVA")
    print(f"{'-' * 7} {'-' * 46} {'-' * 60}")
    for metodo, caminho in extras:
        motivo = FORA_DO_CONTRATO.get((metodo, caminho), "!!! SEM JUSTIFICATIVA REGISTRADA !!!")
        print(f"{metodo:<7} {caminho:<46} {motivo}")

    print("\n--- seção 05 (congelada): nenhuma rota do tema pode existir ---")
    vazando = [
        f"{m} {c}"
        for (m, c) in reais
        if any(padrao.search(c) for padrao in PADROES_CONGELADOS)
    ]
    print(f"    rotas com /acesso, /solicitacoes, /aprovacao ou senha compartilhada: {vazando or 'nenhuma'}")

    print("\n--- contagem ---")
    print(f"    contrato reconstruído ....... {len(CONTRATO)} rotas "
          f"({sum(1 for *_, s in CONTRATO if s == 'implementar')} a implementar, "
          f"{sum(1 for *_, s in CONTRATO if s == 'congelada')} congeladas)")
    print(f"    implementadas ............... {len(reais)}")
    print(f"    do contrato, implementadas .. {contados['bate']}")
    print(f"    do contrato, faltando ....... {contados['faltando']}")
    print(f"    fora do contrato ............ {len(extras)}")

    sem_evidencia = [
        f"{m} {c}"
        for m, c, _, situacao in CONTRATO
        if situacao == "implementar" and not tem_evidencia(m, c)
    ]
    print()
    print(
        "    rotas da reconstrução SEM evidência escrita no repositório "
        f"({len(sem_evidencia)}):"
    )
    for rota in sem_evidencia:
        print(f"      {rota}")
    print("    (são as candidatas a não estarem no contrato de verdade: a")
    print("     reconstrução chega a 51 rotas de produto e o contrato fala em 52")
    print("     endpoints, e a diferença só fecha com o documento em mãos)")

if __name__ == "__main__":
    main()
