"""EXPLAIN ANALYZE da consulta REAL de GET /produtos.

Monta o statement pelas mesmas funções que a rota usa (nada de SQL reescrito
à mão, que é como se prova o plano da consulta errada) e roda EXPLAIN ANALYZE.

    python scripts/explicar_consulta.py --marca chanel --categoria bolsas --colecao feminino
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy import text  # noqa: E402

from vip_api.banco import SessaoLocal  # noqa: E402
from vip_api.servicos import catalogo  # noqa: E402


def main() -> None:
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument("--colecao")
    analisador.add_argument("--categoria")
    analisador.add_argument("--marca")
    analisador.add_argument("--busca")
    analisador.add_argument("--ordem", default="recentes", choices=["recentes", "nome"])
    analisador.add_argument("--por-pagina", type=int, default=24)
    argumentos = analisador.parse_args()

    filtros = catalogo.FiltrosProduto(
        colecao=argumentos.colecao,
        categoria=argumentos.categoria,
        marca=argumentos.marca,
        busca=argumentos.busca,
        ordem=argumentos.ordem,
        por_pagina=argumentos.por_pagina,
    )

    with SessaoLocal() as sessao:
        ids = catalogo._resolver_ids(sessao, filtros)
        if ids is None:
            sys.exit("Algum slug informado não existe no banco.")

        stmt = catalogo._consulta_da_pagina(filtros, ids, None, argumentos.por_pagina + 1)

        sql = str(
            stmt.compile(
                sessao.get_bind(), compile_kwargs={"literal_binds": True}
            )
        ).replace("\n", " ")

        print("--- SQL ---")
        print(sql)
        print("\n--- EXPLAIN ANALYZE ---")
        for linha in sessao.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {sql}")):
            print(linha[0])


if __name__ == "__main__":
    main()
