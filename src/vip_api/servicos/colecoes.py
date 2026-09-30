"""Feminino e Masculino: o público do produto (migração 0015).

Deixaram de ser tabela. Cada produto tem `feminino` e `masculino`; os dois marcados
significam unissex. `/feminino` e `/masculino` seguem filtrando, agora por esses campos, e
`GET /colecoes` devolve as duas constantes abaixo (ids 1 e 2, os mesmos de antes, para nenhum
link ou cliente da API quebrar).
"""

from sqlalchemy import and_, case

from vip_api.modelos.catalogo import Produto

COLECOES = (
    {"id": 1, "nome": "Feminina", "slug": "feminino"},
    {"id": 2, "nome": "Masculina", "slug": "masculino"},
)
NOME_UNISSEX = "Unissex"

SLUGS = tuple(c["slug"] for c in COLECOES)


def colecao_por_slug(slug: str | None) -> dict | None:
    return next((c for c in COLECOES if c["slug"] == slug), None)


def colecao_por_id(colecao_id: int | None) -> dict | None:
    return next((c for c in COLECOES if c["id"] == colecao_id), None)


def coluna_do_publico(slug: str, tabela=Produto):
    """A coluna booleana do público: `Produto.feminino` ou `Produto.masculino`."""
    return tabela.feminino if slug == "feminino" else tabela.masculino


def filtro_do_publico(slug: str, tabela=Produto):
    return coluna_do_publico(slug, tabela).is_(True)


def nome_da_colecao(feminino, masculino):
    """Expressão SQL do nome exibido: Unissex quando as duas estão marcadas."""
    return case(
        (and_(feminino.is_(True), masculino.is_(True)), NOME_UNISSEX),
        (feminino.is_(True), "Feminina"),
        else_="Masculina",
    )


def slug_da_colecao(feminino):
    """Expressão SQL do slug de URL: o do Feminino quando marcado, senão o do Masculino.
    Serve de 'coleção principal' onde a API ainda devolve uma só (`colecao` do produto)."""
    return case((feminino.is_(True), "feminino"), else_="masculino")


def publicos(feminino: bool, masculino: bool) -> list[str]:
    return [slug for slug, marcado in (("feminino", feminino), ("masculino", masculino)) if marcado]


def nome_do_publico(feminino: bool, masculino: bool) -> str:
    if feminino and masculino:
        return NOME_UNISSEX
    return "Feminina" if feminino else "Masculina"


def slug_do_publico(feminino: bool) -> str:
    return "feminino" if feminino else "masculino"


def flags_dos_publicos(slugs: list[str]) -> tuple[bool, bool]:
    return "feminino" in slugs, "masculino" in slugs
