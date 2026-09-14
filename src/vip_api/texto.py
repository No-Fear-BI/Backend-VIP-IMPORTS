"""Normalização de texto para ordenação, busca e slug.

Esta é a rotina que preenche `produtos.nome_ordenacao` e `marcas.nome_busca`
(via listener, ver modelos/catalogo.py) E que normaliza o termo de `?busca=`
antes de comparar. Se as duas pontas divergirem, a busca simplesmente para de
achar — por isso existe uma função só, e não duas parecidas.

O banco não faz essa normalização: `unaccent()` do PostgreSQL não é IMMUTABLE
e não pode sustentar coluna gerada nem índice confiável
(docs/modelagem-banco.md, seção 5.1).
"""

import unicodedata


def normalizar(texto: str) -> str:
    """`"Bolsa Clássica"` -> `"bolsa classica"`: minúsculas, sem acento."""
    decomposto = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return sem_acento.lower().strip()


def gerar_slug(texto: str) -> str:
    """`"Louis Vuitton"` -> `"louis-vuitton"`.

    Mesma normalização da busca (minúsculas, sem acento) mais a troca do que
    não é letra nem número por hífen. É a URL pública da marca e da categoria,
    então sai daqui uma vez, na criação, e não muda sozinha depois — trocar
    slug quebra link compartilhado e o que o buscador já indexou.
    """
    base = normalizar(texto)
    palavras = "".join(c if c.isalnum() else " " for c in base).split()
    return "-".join(palavras)
