"""Conta as consultas SQL que um serviço dispara, por evento do SQLAlchemy.

Não é estimativa nem leitura de log: engancha em `before_cursor_execute` e
conta cada ida ao banco, mostrando o SQL de cada uma.

    python scripts/contar_consultas.py home
    python scripts/contar_consultas.py detalhe CHN-0042
    python scripts/contar_consultas.py relacionados CHN-0042
    python scripts/contar_consultas.py marcas
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy import event, text  # noqa: E402

from vip_api.banco import SessaoLocal, engine  # noqa: E402
from vip_api.servicos import catalogo, home, navegacao  # noqa: E402

consultas: list[str] = []


@event.listens_for(engine, "before_cursor_execute")
def _registrar(conexao, cursor, instrucao, parametros, contexto, muitos):
    consultas.append(" ".join(instrucao.split()))


def _resumir(sql: str, tamanho: int = 118) -> str:
    sql = re.sub(r"\s+", " ", sql)
    return sql if len(sql) <= tamanho else sql[:tamanho] + "…"


def main() -> None:
    alvo = sys.argv[1] if len(sys.argv) > 1 else "home"
    argumento = sys.argv[2] if len(sys.argv) > 2 else None

    with SessaoLocal() as sessao:
        # Aquece: a primeira conexão do pool dispara consultas do próprio
        # driver (SET, ping) que não são do serviço e sujariam a contagem.
        sessao.execute(text("SELECT 1"))
        consultas.clear()

        inicio = time.perf_counter()
        if alvo == "home":
            resultado = home.montar_home(sessao)
            descricao = (
                f"{len(resultado.banners)} banners, {len(resultado.destaques)} destaques, "
                f"{len(resultado.categorias_destaque)} categorias em destaque, "
                f"{len(resultado.marcas)} marcas"
            )
        elif alvo == "detalhe":
            resultado = catalogo.obter_produto(sessao, argumento)
            descricao = f"{len(resultado.imagens)} imagens, {len(resultado.variacoes)} variações"
        elif alvo == "relacionados":
            resultado = catalogo.listar_relacionados(sessao, argumento)
            descricao = f"{len(resultado)} relacionados"
        elif alvo == "marcas":
            resultado = navegacao.listar_marcas(sessao)
            descricao = f"{len(resultado)} marcas"
        else:
            sys.exit(f"alvo desconhecido: {alvo}")
        decorrido = (time.perf_counter() - inicio) * 1000

    print(f"alvo: {alvo}{' ' + argumento if argumento else ''}  ->  {descricao}")
    print(f"consultas ao banco: {len(consultas)}  (montagem em {decorrido:.1f} ms)\n")
    for indice, sql in enumerate(consultas, start=1):
        print(f"  {indice}. {_resumir(sql)}")


if __name__ == "__main__":
    main()
