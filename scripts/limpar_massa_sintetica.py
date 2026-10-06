"""Limpa a massa sintética de `gerar_massa.py` do banco de desenvolvimento:
produtos primeiro, depois marca/categoria que ficarem órfãs — nessa ordem
obrigatória, porque a FK de `produtos` para `marcas`/`categorias` é RESTRICT
(docs/modelagem-banco.md): apagar marca/categoria com produto pendurado dá
erro de integridade antes mesmo de qualquer trava deste script agir.

NÃO RODAR sem ler isto primeiro: é destrutivo. Use --simular tantas vezes
quanto quiser antes — ele executa a limpeza inteira DENTRO de uma transação e
dá ROLLBACK no final, então o "seria apagado" é o resultado real do banco, não
uma estimativa em Python.

Sequência (uma transação só; qualquer recusa aborta TUDO, nada fica pela
metade):

  1. `DELETE FROM produtos WHERE origem_url = 'gerar_massa'` — o carimbo que
     só `gerar_massa.py` escreve (ver o cabeçalho de lá). Cascata cuida do
     resto sozinha: `produto_imagens`, `produto_variacoes`, `carrinho_itens`
     e `favoritos` são ON DELETE CASCADE.
  2. Marca sem NENHUM produto (sintético ou real — depois do passo 1, "sem
     produto" só pode significar isso) E cujo slug não está na taxonomia
     real (`scripts/semear_taxonomia_real.py`, mesma fonte da semeadura) é
     apagada.
  3. Categoria na mesma condição, por (coleção, slug).

Trava (o pedido explícito): antes de detonar qualquer coisa, confere que TODO
produto com `origem_url = 'gerar_massa'` tem `codigo_origem` NULO —
`gerar_massa.py` nunca preenche essa coluna, `importar_catalogo.py` sempre
preenche (é a chave de dedup dele). Um produto carimbado 'gerar_massa' COM
`codigo_origem` preenchido não é massa sintética — é sinal de dado carimbado
errado — e a validação recusa rodar em vez de apagar um produto real por
engano. Depois do passo 1, a mesma lógica vale de novo para marca/categoria:
se uma candidata a remoção ainda tiver produto pendurado, só pode ser um
produto que SOBREVIVEU ao passo 1 (logo, `origem_url` diferente de
'gerar_massa') — a trava recusa a limpeza inteira nesse caso, em vez de
pular só aquela marca ou deixar a RESTRICT do banco estourar um erro feio.

    python scripts/limpar_massa_sintetica.py --simular   # mostra o plano, não apaga nada
    python scripts/limpar_massa_sintetica.py             # apaga de verdade

Não é reexecutável no sentido de "rodar de novo não faz nada" — depois da
primeira vez bem-sucedida não sobra massa sintética para apagar, então uma
segunda execução só confirma "0 produtos, 0 marcas, 0 categorias" e sai
limpo, sem erro.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from semear_taxonomia_real import (  # noqa: E402
    CATEGORIAS_REAIS,
    CSV_PADRAO,
    _ler_csv,
    _marcas_do_csv,
)
from vip_api.banco import SessaoLocal  # noqa: E402
from vip_api.configuracao import configuracao  # noqa: E402
from vip_api.modelos.catalogo import Categoria, Marca, Produto  # noqa: E402
from vip_api.texto import gerar_slug  # noqa: E402

CARIMBO_MASSA_SINTETICA = "gerar_massa"


def _exigir_desenvolvimento() -> None:
    if configuracao.AMBIENTE != "desenvolvimento":
        sys.exit(
            f"Recusando rodar com AMBIENTE={configuracao.AMBIENTE!r}. Este "
            "script apaga dado em massa — só roda em desenvolvimento."
        )


def _slugs_marcas_reais() -> set[str]:
    linhas = _ler_csv(CSV_PADRAO)
    return {gerar_slug(nome) for nome in _marcas_do_csv(linhas)}


def _slugs_categorias_reais() -> set[str]:
    """{slug_categoria} — o slug é único na tabela desde a 0015."""
    return {gerar_slug(nome) for nome, _publico in CATEGORIAS_REAIS}


def _checar_carimbo(sessao: Session) -> None:
    """A trava de antes de mexer em qualquer coisa: produto carimbado
    'gerar_massa' tem que parecer mesmo sintético."""
    suspeitos = sessao.execute(
        select(Produto.id, Produto.codigo, Produto.codigo_origem)
        .where(
            Produto.origem_url == CARIMBO_MASSA_SINTETICA,
            Produto.codigo_origem.is_not(None),
        )
        .limit(20)
    ).all()
    if suspeitos:
        exemplos = "\n".join(
            f"    id={p.id} codigo={p.codigo!r} codigo_origem={p.codigo_origem!r}"
            for p in suspeitos
        )
        sys.exit(
            f"RECUSANDO RODAR: {len(suspeitos)} produto(s) com "
            f"origem_url={CARIMBO_MASSA_SINTETICA!r} têm codigo_origem preenchido — "
            "gerar_massa.py NUNCA preenche essa coluna, então isso não é massa "
            "sintética. Carimbo errado em produto real; investigue antes de "
            "rodar este script.\n"
            f"{exemplos}"
        )


def _remover_produtos_sinteticos(sessao: Session) -> int:
    total = sessao.scalar(
        select(func.count())
        .select_from(Produto)
        .where(Produto.origem_url == CARIMBO_MASSA_SINTETICA)
    )
    sessao.execute(delete(Produto).where(Produto.origem_url == CARIMBO_MASSA_SINTETICA))
    return total or 0


def _remover_marcas_orfas(sessao: Session, slugs_reais: set[str]) -> list[str]:
    candidatas = sessao.execute(
        select(Marca.id, Marca.nome, Marca.slug)
        .outerjoin(Produto, Produto.marca_id == Marca.id)
        .group_by(Marca.id)
        .having(func.count(Produto.id) == 0)
    ).all()

    removidas = []
    for marca in candidatas:
        if marca.slug in slugs_reais:
            continue  # órfã, mas É a taxonomia real recém-semeada — fica.

        # A trava, de novo: a HAVING já garante zero produto, mas confere
        # direto na tabela antes de apagar, sem confiar só na agregação.
        total = sessao.scalar(
            select(func.count()).select_from(Produto).where(Produto.marca_id == marca.id)
        )
        if total:
            sys.exit(
                f"RECUSANDO RODAR: marca {marca.nome!r} (slug {marca.slug!r}) "
                f"tinha {total} produto(s) no instante da exclusão — só pode ser "
                f"produto com origem_url diferente de {CARIMBO_MASSA_SINTETICA!r} "
                "(o passo 1 já apagou todo o resto). Abortando antes de apagar "
                "qualquer coisa."
            )

        sessao.execute(delete(Marca).where(Marca.id == marca.id))
        removidas.append(f"{marca.nome!r} (slug {marca.slug!r})")
    return removidas


def _remover_categorias_orfas(
    sessao: Session, slugs_reais: set[str]
) -> list[str]:
    candidatas = sessao.execute(
        select(Categoria.id, Categoria.nome, Categoria.slug)
        .outerjoin(Produto, Produto.categoria_id == Categoria.id)
        .group_by(Categoria.id)
        .having(func.count(Produto.id) == 0)
    ).all()

    removidas = []
    for cat in candidatas:
        if cat.slug in slugs_reais:
            continue

        total = sessao.scalar(
            select(func.count()).select_from(Produto).where(Produto.categoria_id == cat.id)
        )
        if total:
            sys.exit(
                f"RECUSANDO RODAR: categoria {cat.nome!r} "
                f"tinha {total} produto(s) no instante da exclusão — só pode ser "
                f"produto com origem_url diferente de {CARIMBO_MASSA_SINTETICA!r}. "
                "Abortando antes de apagar qualquer coisa."
            )

        sessao.execute(delete(Categoria).where(Categoria.id == cat.id))
        removidas.append(f"{cat.nome!r} (slug {cat.slug!r})")
    return removidas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--simular",
        action="store_true",
        help="Roda a limpeza inteira numa transação e dá ROLLBACK no final — nada é gravado.",
    )
    args = parser.parse_args()

    _exigir_desenvolvimento()
    slugs_marcas_reais = _slugs_marcas_reais()
    pares_categorias_reais = _slugs_categorias_reais()

    with SessaoLocal() as sessao:
        _checar_carimbo(sessao)

        total_produtos = _remover_produtos_sinteticos(sessao)
        marcas_removidas = _remover_marcas_orfas(sessao, slugs_marcas_reais)
        categorias_removidas = _remover_categorias_orfas(sessao, pares_categorias_reais)

        if args.simular:
            sessao.rollback()
        else:
            sessao.commit()

    prefixo = "[simulação, nada foi gravado] " if args.simular else ""
    print(f"{prefixo}{total_produtos} produto(s) com origem_url={CARIMBO_MASSA_SINTETICA!r} removido(s).")
    print(f"\n{prefixo}{len(marcas_removidas)} marca(s) órfã(s) removida(s):")
    for linha in marcas_removidas:
        print(f"  - {linha}")
    print(f"\n{prefixo}{len(categorias_removidas)} categoria(s) órfã(s) removida(s):")
    for linha in categorias_removidas:
        print(f"  - {linha}")


if __name__ == "__main__":
    main()
