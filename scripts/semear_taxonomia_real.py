"""Semeia no banco de desenvolvimento as marcas e categorias REAIS extraídas do
protótipo do cliente (base44), a partir de scripts/catalogo-base44-prototipo.csv —
ver o levantamento completo na conversa que gerou esse CSV.

MARCAS vêm do CSV (coluna `marca`): os 24 produtos de amostra do protótipo
cobrem as 23 marcas reais inteiras — conferido contra `GET
.../entities/Brand` do próprio protótipo, é a mesma lista.

CATEGORIAS **não** vêm do CSV: só 6 das 16 categorias reais do protótipo têm
produto de amostra (Bolsas, Carteiras, Casacos, Vestidos, Óculos, Camisetas),
então derivar categoria só dos produtos perderia as outras 10 (Calças, Blusas
e Camisas, Lenços, Bermudas, Camisas-masculino já existente...). Por isso
`CATEGORIAS_REAIS` abaixo é a taxonomia completa, lida direto de `GET
.../entities/Category` do protótipo (16 linhas, todas `status: true`) na
mesma sessão de levantamento que gerou o CSV — não é inventada.

O que este script FAZ:
  - para cada marca (do CSV) cujo slug (mesma normalização de
    vip_api.texto.gerar_slug) ainda não existe em `marcas`, cria a marca;
  - para cada par (categoria, coleção) de `CATEGORIAS_REAIS` cujo slug ainda
    não existe NAQUELA coleção — a unicidade de categoria é por coleção, não
    global (docs/modelagem-banco.md) — cria a categoria.

O que este script NÃO FAZ, de propósito:
  - não cria produto nenhum (isso é `importar_catalogo.py`, e o CSV do
    protótipo não teve os produtos importados ainda, só a taxonomia);
  - não apaga nada. As 18 marcas e 12 categorias sintéticas de
    `gerar_massa.py` continuam no banco — têm 11.569 produtos pendurados, e
    excluir marca/categoria com produto devolve 409 (RESTRICT). A limpeza
    delas é passo separado, de depois que a massa sintética sair.

Dedup por SLUG, não por nome escrito igual: "Céline" (sintética, com acento)
e "Celine" (real, sem acento) normalizam para o mesmo slug "celine" — são a
MESMA marca pro banco, e criar de novo colidiria e o serviço resolveria
gerando "celine-2", uma marca duplicada. Por isso a checagem de "já existe"
usa `gerar_slug`, nunca comparação de string crua.

Reexecutável: roda de novo e só cria o que ainda faltar.

    python scripts/semear_taxonomia_real.py             # cria o que faltar
    python scripts/semear_taxonomia_real.py --simular   # só mostra o plano
"""

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from vip_api.banco import SessaoLocal  # noqa: E402
from vip_api.configuracao import configuracao  # noqa: E402
from vip_api.esquemas.admin_catalogo import CategoriaCriar, MarcaCriar  # noqa: E402
from vip_api.modelos.catalogo import Categoria, Colecao, Marca  # noqa: E402
from vip_api.servicos.admin_categorias import criar_categoria  # noqa: E402
from vip_api.servicos.admin_marcas import criar_marca  # noqa: E402
from vip_api.texto import gerar_slug  # noqa: E402

CSV_PADRAO = os.path.join(
    os.path.dirname(__file__), "catalogo-base44-prototipo.csv"
)

# (nome, slug da coleção) — as 16 categorias reais do protótipo (GET
# .../entities/Category, status:true), na mesma ordem em que o protótipo
# devolve. Slug da categoria é derivado do nome por gerar_slug(), não escrito
# aqui — é a mesma regra que o painel usa ao criar.
CATEGORIAS_REAIS: list[tuple[str, str]] = [
    ("Bolsas", "feminino"),
    ("Bolsas", "masculino"),
    ("Carteiras", "feminino"),
    ("Carteiras", "masculino"),
    ("Casacos", "feminino"),
    ("Casacos", "masculino"),
    ("Vestidos", "feminino"),
    ("Camisetas", "masculino"),
    ("Calças", "feminino"),
    ("Calças", "masculino"),
    ("Blusas e Camisas", "feminino"),
    ("Bermudas", "masculino"),
    ("Óculos", "feminino"),
    ("Camisas", "masculino"),
    ("Lenços", "feminino"),
    ("Óculos", "masculino"),
]


def _exigir_desenvolvimento() -> None:
    if configuracao.AMBIENTE != "desenvolvimento":
        sys.exit(
            f"Recusando rodar com AMBIENTE={configuracao.AMBIENTE!r}. "
            "Este script é para semear o banco de DESENVOLVIMENTO com a "
            "taxonomia real levantada do protótipo, não para produção."
        )


def _ler_csv(caminho: str) -> list[dict[str, str]]:
    with open(caminho, encoding="utf-8", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


def _marcas_do_csv(linhas: list[dict[str, str]]) -> list[str]:
    """Nomes de marca, na primeira ordem em que aparecem no CSV, sem repetir."""
    vistos: dict[str, str] = {}
    for linha in linhas:
        nome = linha["marca"].strip()
        slug = gerar_slug(nome)
        vistos.setdefault(slug, nome)
    return list(vistos.values())


def _semear_marcas(
    sessao: Session, nomes: list[str], simular: bool
) -> tuple[list[str], list[str]]:
    existentes = {
        slug: nome
        for slug, nome in sessao.execute(select(Marca.slug, Marca.nome)).all()
    }
    proxima_ordem = (sessao.scalar(select(Marca.ordem).order_by(Marca.ordem.desc())) or 0) + 1

    criadas, ja_existiam = [], []
    for nome in nomes:
        slug = gerar_slug(nome)
        if slug in existentes:
            ja_existiam.append(f"{nome!r} -> já é {existentes[slug]!r} (slug {slug!r})")
            continue
        if simular:
            criadas.append(f"{nome!r} (slug {slug!r}, ordem {proxima_ordem})")
        else:
            criar_marca(sessao, MarcaCriar(nome=nome, ordem=proxima_ordem))
            criadas.append(f"{nome!r} (slug {slug!r})")
        existentes[slug] = nome
        proxima_ordem += 1
    return criadas, ja_existiam


def _semear_categorias(
    sessao: Session, pares: list[tuple[str, str]], simular: bool
) -> tuple[list[str], list[str]]:
    colecoes = {c.slug: c for c in sessao.scalars(select(Colecao))}
    existentes: dict[tuple[int, str], str] = {}
    for cat in sessao.scalars(select(Categoria)):
        existentes[(cat.colecao_id, cat.slug)] = cat.nome
    proxima_ordem = {
        colecao_id: (
            sessao.scalar(
                select(Categoria.ordem)
                .where(Categoria.colecao_id == colecao_id)
                .order_by(Categoria.ordem.desc())
            )
            or 0
        )
        + 1
        for colecao_id in (c.id for c in colecoes.values())
    }

    criadas, ja_existiam = [], []
    for nome, colecao_slug in pares:
        colecao = colecoes.get(colecao_slug)
        if colecao is None:
            sys.exit(
                f"Coleção {colecao_slug!r} não existe no banco (só feminino/"
                "masculino são semeadas pela migração 0001). Verifique o CSV."
            )
        slug = gerar_slug(nome)
        chave = (colecao.id, slug)
        if chave in existentes:
            ja_existiam.append(
                f"{nome!r}/{colecao_slug} -> já é {existentes[chave]!r} (slug {slug!r})"
            )
            continue
        ordem = proxima_ordem[colecao.id]
        if simular:
            criadas.append(f"{nome!r}/{colecao_slug} (slug {slug!r}, ordem {ordem})")
        else:
            criar_categoria(
                sessao,
                CategoriaCriar(
                    colecao_id=colecao.id, nome=nome, ordem=ordem
                ),
            )
            criadas.append(f"{nome!r}/{colecao_slug} (slug {slug!r})")
        existentes[chave] = nome
        proxima_ordem[colecao.id] = ordem + 1
    return criadas, ja_existiam


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv", default=CSV_PADRAO, help="Caminho do CSV (padrão: %(default)s)"
    )
    parser.add_argument(
        "--simular",
        action="store_true",
        help="Só mostra o que criaria, não grava nada.",
    )
    args = parser.parse_args()

    _exigir_desenvolvimento()
    linhas = _ler_csv(args.csv)
    marcas = _marcas_do_csv(linhas)

    with SessaoLocal() as sessao:
        marcas_criadas, marcas_existentes = _semear_marcas(sessao, marcas, args.simular)
        categorias_criadas, categorias_existentes = _semear_categorias(
            sessao, CATEGORIAS_REAIS, args.simular
        )
        if not args.simular:
            sessao.commit()

    prefixo = "[simulação] " if args.simular else ""
    print(f"{prefixo}Marcas — {len(marcas_criadas)} novas, {len(marcas_existentes)} já existiam (por slug):")
    for linha in marcas_criadas:
        print(f"  + {linha}")
    for linha in marcas_existentes:
        print(f"  = {linha}")

    print(
        f"\n{prefixo}Categorias — {len(categorias_criadas)} novas, "
        f"{len(categorias_existentes)} já existiam (por coleção+slug):"
    )
    for linha in categorias_criadas:
        print(f"  + {linha}")
    for linha in categorias_existentes:
        print(f"  = {linha}")


if __name__ == "__main__":
    main()
