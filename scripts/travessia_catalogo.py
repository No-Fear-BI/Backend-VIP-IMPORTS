"""Percorre o catálogo inteiro de ponta a ponta seguindo `proximoCursor` e
prova que a paginação não repete nem pula item.

É o teste que importa da tarefa 17: se ele passa nas duas ordenações, o
cursor está certo. Compara o conjunto de ids visitados com a lista de
produtos visíveis lida direto do banco — se der diferença, diz qual.

    python scripts/travessia_catalogo.py [--por-pagina 24] [--base URL]
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy import select  # noqa: E402

from vip_api.banco import SessaoLocal  # noqa: E402
from vip_api.modelos.catalogo import Produto  # noqa: E402


def _buscar(base: str, parametros: dict) -> dict:
    url = f"{base}/api/v1/produtos?{urllib.parse.urlencode(parametros)}"
    with urllib.request.urlopen(url, timeout=60) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


def travessia(base: str, ordem: str, por_pagina: int) -> tuple[list[int], int, int, float]:
    """Devolve (ids na ordem visitada, total informado, páginas, segundos)."""
    ids: list[int] = []
    cursor = None
    paginas = 0
    total_informado = None
    inicio = time.perf_counter()

    while True:
        parametros = {"ordem": ordem, "porPagina": por_pagina}
        if cursor:
            parametros["cursor"] = cursor

        pagina = _buscar(base, parametros)
        paginas += 1

        if total_informado is None:
            total_informado = pagina["paginacao"]["total"]
        elif pagina["paginacao"]["total"] != total_informado:
            print(
                f"  ! total mudou no meio da paginação: {total_informado} -> "
                f"{pagina['paginacao']['total']}"
            )

        ids.extend(item["id"] for item in pagina["dados"])

        cursor = pagina["paginacao"].get("proximoCursor")
        if not cursor:
            break
        if paginas > 5_000:
            print("  ! passou de 5.000 páginas — abortando, provável laço infinito")
            break

    return ids, total_informado or 0, paginas, time.perf_counter() - inicio


def main() -> None:
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument("--por-pagina", type=int, default=24)
    analisador.add_argument("--base", default="http://localhost:8000")
    argumentos = analisador.parse_args()

    with SessaoLocal() as sessao:
        visiveis = set(
            sessao.scalars(select(Produto.id).where(Produto.status != "oculto"))
        )
        ocultos = set(sessao.scalars(select(Produto.id).where(Produto.status == "oculto")))

    print(f"banco: {len(visiveis)} produtos visíveis, {len(ocultos)} ocultos\n")

    falhou = False
    for ordem in ("recentes", "nome"):
        ids, total_informado, paginas, segundos = travessia(
            argumentos.base, ordem, argumentos.por_pagina
        )
        unicos = set(ids)
        repetidos = len(ids) - len(unicos)
        faltando = visiveis - unicos
        sobrando = unicos - visiveis
        ocultos_vazados = unicos & ocultos

        print(f"ordem={ordem}")
        print(f"  páginas percorridas ....... {paginas} (em {segundos:.2f}s)")
        print(f"  ids visitados ............. {len(ids)}")
        print(f"  ids únicos ................ {len(unicos)}")
        print(f"  total informado pela API .. {total_informado}")
        print(f"  produtos visíveis no banco  {len(visiveis)}")
        print(f"  repetidos ................. {repetidos}")
        print(f"  faltando .................. {len(faltando)}")
        print(f"  sobrando .................. {len(sobrando)}")
        print(f"  OCULTOS que vazaram ....... {len(ocultos_vazados)}")

        ok = (
            repetidos == 0
            and not faltando
            and not sobrando
            and not ocultos_vazados
            and total_informado == len(visiveis)
        )
        print(f"  => {'OK' if ok else 'FALHOU'}\n")
        if not ok:
            falhou = True
            if faltando:
                print(f"     faltando (até 10): {sorted(faltando)[:10]}")
            if sobrando:
                print(f"     sobrando (até 10): {sorted(sobrando)[:10]}")
            if ocultos_vazados:
                print(f"     ocultos (até 10): {sorted(ocultos_vazados)[:10]}")

    sys.exit(1 if falhou else 0)


if __name__ == "__main__":
    main()
