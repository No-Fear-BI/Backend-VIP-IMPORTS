"""Gera massa de teste para desenvolvimento: 18 marcas, categorias por
coleção e 5.000 produtos com imagens e variações.

Fora do pacote da aplicação de propósito — isto nunca vai para produção.

Reexecutável: usa o `codigo` do produto e o `slug` de marca/categoria como
chave natural e pula o que já existe, então rodar duas vezes não duplica nada.

    python scripts/gerar_massa.py            # cria o que faltar
    python scripts/gerar_massa.py --limpar   # apaga a massa antes de recriar

A distribuição imita catálogo real: umas poucas marcas concentram centenas de
produtos, a maioria tem dezenas. Parte esgotada, parte oculta, parte sem
imagem nenhuma — testar filtro com 50 registros bem-comportados não prova nada.
"""

import argparse
import os
import random
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from vip_api.banco import SessaoLocal, engine  # noqa: E402
from vip_api.configuracao import configuracao  # noqa: E402
from vip_api.modelos.catalogo import (  # noqa: E402
    Banner,
    Categoria,
    Colecao,
    Marca,
    Produto,
    ProdutoImagem,
    ProdutoVariacao,
)

TOTAL_PRODUTOS = 5_000
SEMENTE = 20260910  # massa reproduzível: mesma semente, mesmo catálogo

# (nome, prefixo do código, peso na distribuição). O peso é o que cria o
# catálogo desbalanceado de verdade: Chanel com centenas, Goyard com poucas.
MARCAS = [
    ("Chanel", "CHN", 40),
    ("Louis Vuitton", "LVT", 38),
    ("Gucci", "GUC", 32),
    ("Prada", "PRD", 28),
    ("Hermès", "HRM", 10),
    ("Dior", "DIO", 24),
    ("Balenciaga", "BLC", 18),
    ("Saint Laurent", "SLT", 16),
    ("Bottega Veneta", "BTV", 12),
    ("Versace", "VRS", 14),
    ("Fendi", "FND", 12),
    ("Burberry", "BBR", 10),
    ("Valentino", "VLT", 8),
    ("Givenchy", "GVC", 7),
    ("Céline", "CLN", 6),
    ("Loewe", "LOE", 4),
    ("Goyard", "GOY", 3),
    ("Off-White", "OFW", 5),
]

CATEGORIAS = {
    "feminino": [
        ("Bolsas", "bolsas"),
        ("Vestidos", "vestidos"),
        ("Sapatos", "sapatos"),
        ("Acessórios", "acessorios"),
        ("Blusas", "blusas"),
        ("Óculos", "oculos"),
    ],
    "masculino": [
        ("Bolsas", "bolsas"),
        ("Camisas", "camisas"),
        ("Sapatos", "sapatos"),
        ("Acessórios", "acessorios"),
        ("Casacos", "casacos"),
        ("Óculos", "oculos"),
    ],
}

MODELOS = [
    "Clássica", "Acolchoada", "Monograma", "Matelassê", "Slim", "Oversized",
    "Vintage", "Couro Legítimo", "Camurça", "Bordada", "Tweed", "Canvas",
    "Mini", "Maxi", "Tote", "Crossbody", "Plissada", "Estruturada",
]
CORES = [
    "Preta", "Bege", "Caramelo", "Off-White", "Vermelha", "Azul Marinho",
    "Verde Oliva", "Rosé", "Cinza", "Dourada", "Prata", "Marrom",
]
TAMANHOS = ["PP", "P", "M", "G", "GG", "36", "37", "38", "39", "40", "42", "44"]


def _exigir_desenvolvimento() -> None:
    if configuracao.AMBIENTE != "desenvolvimento":
        sys.exit(
            f"Recusando rodar com AMBIENTE={configuracao.AMBIENTE!r}. "
            "Este script só roda em desenvolvimento — ele escreve milhares de "
            "linhas de mentira no catálogo."
        )


def _limpar(sessao: Session) -> None:
    # Imagens e variações somem por cascata da FK ao apagar o produto.
    sessao.execute(delete(Banner))
    sessao.execute(delete(Produto))
    sessao.execute(delete(Categoria))
    sessao.execute(delete(Marca))
    sessao.commit()
    print("massa anterior apagada")


def _garantir_marcas(sessao: Session) -> dict[str, Marca]:
    existentes = {m.slug: m for m in sessao.scalars(select(Marca))}
    criadas = 0
    for nome, _prefixo, _peso in MARCAS:
        slug = _slug(nome)
        if slug in existentes:
            continue
        # Objeto ORM, não INSERT em massa: é o que dispara o listener que
        # preenche `nome_busca`.
        marca = Marca(nome=nome, slug=slug, ordem=criadas)
        sessao.add(marca)
        existentes[slug] = marca
        criadas += 1
    sessao.commit()
    print(f"marcas: {criadas} criadas, {len(existentes)} no total")
    return existentes


def _slug(texto: str) -> str:
    import unicodedata

    base = unicodedata.normalize("NFKD", texto)
    base = "".join(c for c in base if not unicodedata.combining(c))
    return "".join(c if c.isalnum() else "-" for c in base.lower()).strip("-")


def _garantir_categorias(sessao: Session) -> dict[tuple[int, str], Categoria]:
    colecoes = {c.slug: c for c in sessao.scalars(select(Colecao))}
    if not colecoes:
        sys.exit("Nenhuma coleção no banco. Rode `alembic upgrade head` primeiro.")

    existentes = {(c.colecao_id, c.slug): c for c in sessao.scalars(select(Categoria))}
    criadas = 0
    for slug_colecao, categorias in CATEGORIAS.items():
        colecao = colecoes[slug_colecao]
        for ordem, (nome, slug) in enumerate(categorias):
            chave = (colecao.id, slug)
            if chave in existentes:
                continue
            categoria = Categoria(colecao_id=colecao.id, nome=nome, slug=slug, ordem=ordem)
            sessao.add(categoria)
            existentes[chave] = categoria
            criadas += 1
    sessao.commit()
    print(f"categorias: {criadas} criadas, {len(existentes)} no total")
    return existentes


def _gerar_produtos(sessao: Session, marcas: dict, categorias: dict) -> None:
    aleatorio = random.Random(SEMENTE)
    codigos_existentes = set(sessao.scalars(select(Produto.codigo)))

    marcas_por_slug = {_slug(nome): (nome, prefixo, peso) for nome, prefixo, peso in MARCAS}
    pesos = [marcas_por_slug[_slug(nome)][2] for nome, _p, _peso in MARCAS]
    slugs_marca = [_slug(nome) for nome, _p, _peso in MARCAS]

    categorias_por_colecao: dict[int, list[Categoria]] = {}
    for (colecao_id, _slug_cat), categoria in categorias.items():
        categorias_por_colecao.setdefault(colecao_id, []).append(categoria)

    sequencia_por_marca: dict[str, int] = {}
    for codigo in codigos_existentes:
        prefixo, _, numero = codigo.partition("-")
        if numero.isdigit():
            sequencia_por_marca[prefixo] = max(
                sequencia_por_marca.get(prefixo, 0), int(numero)
            )

    agora = datetime.now(timezone.utc)
    criados = 0
    lote: list[Produto] = []

    for _ in range(TOTAL_PRODUTOS - len(codigos_existentes)):
        slug_marca = aleatorio.choices(slugs_marca, weights=pesos, k=1)[0]
        nome_marca, prefixo, _peso = marcas_por_slug[slug_marca]
        marca = marcas[slug_marca]

        colecao_id = aleatorio.choice(list(categorias_por_colecao.keys()))
        categoria = aleatorio.choice(categorias_por_colecao[colecao_id])

        sequencia_por_marca[prefixo] = sequencia_por_marca.get(prefixo, 0) + 1
        codigo = f"{prefixo}-{sequencia_por_marca[prefixo]:04d}"
        if codigo in codigos_existentes:
            continue
        codigos_existentes.add(codigo)

        nome = (
            f"{categoria.nome.rstrip('s')} {aleatorio.choice(MODELOS)} "
            f"{aleatorio.choice(CORES)} {nome_marca}"
        )

        sorteio = aleatorio.random()
        if sorteio < 0.08:
            status = "oculto"
        elif sorteio < 0.23:
            status = "esgotado"
        else:
            status = "normal"

        # criado_em espalhado por 2 anos, mas com blocos no mesmo instante:
        # é assim que a carga real vai ficar, e é exatamente o caso que quebra
        # paginação sem desempate por id.
        recuo = timedelta(days=aleatorio.randint(0, 730))
        if aleatorio.random() < 0.4:
            recuo = timedelta(days=aleatorio.randint(0, 24) * 30)

        produto = Produto(
            codigo=codigo,
            nome=nome,
            descricao=f"{nome}. Peça importada, disponível para atendimento.",
            status=status,
            destaque=aleatorio.random() < 0.02,
            marca_id=marca.id,
            categoria_id=categoria.id,
            colecao_id=colecao_id,
            criado_em=agora - recuo,
        )
        if produto.destaque:
            produto.destaque_ordem = aleatorio.randint(1, 40)

        # ~12% dos produtos sem imagem nenhuma: `capa` nula é caso real, e a
        # tarefa 68 precisa conseguir contar esses.
        if aleatorio.random() > 0.12:
            quantidade_imagens = aleatorio.randint(1, 5)
            for ordem in range(1, quantidade_imagens + 1):
                produto.imagens.append(
                    ProdutoImagem(
                        url=f"https://cdn.exemplo.com/{codigo.lower()}-{ordem}.jpg",
                        alt=f"{nome} — foto {ordem}",
                        ordem=ordem,
                        capa=(ordem == 1),
                    )
                )

        if aleatorio.random() < 0.7:
            for tamanho in aleatorio.sample(TAMANHOS, aleatorio.randint(1, 4)):
                produto.variacoes.append(
                    ProdutoVariacao(
                        tipo="tamanho", valor=tamanho, disponivel=aleatorio.random() > 0.25
                    )
                )
        if aleatorio.random() < 0.4:
            for cor in aleatorio.sample(CORES, aleatorio.randint(1, 3)):
                produto.variacoes.append(
                    ProdutoVariacao(tipo="cor", valor=cor, disponivel=True)
                )

        lote.append(produto)
        criados += 1

        if len(lote) >= 500:
            sessao.add_all(lote)
            sessao.commit()
            lote = []
            print(f"  {criados} produtos...", flush=True)

    if lote:
        sessao.add_all(lote)
        sessao.commit()

    print(f"produtos: {criados} criados")


def _garantir_banners(sessao: Session) -> None:
    """Carrossel de até 4 imagens, o que o escopo assinado prevê."""
    existentes = sessao.scalar(select(func.count()).select_from(Banner))
    if existentes:
        print(f"banners: 0 criados, {existentes} no total")
        return

    for ordem, (titulo, subtitulo) in enumerate(
        [
            ("Novidades da temporada", "Peças recém-chegadas"),
            ("Bolsas de grife", "Seleção da curadoria"),
            ("Masculino", "Camisas e casacos importados"),
            ("Acessórios", "Óculos, cintos e mais"),
        ],
        start=1,
    ):
        sessao.add(
            Banner(
                titulo=titulo,
                subtitulo=subtitulo,
                imagem_url=f"https://cdn.exemplo.com/banner-{ordem}.jpg",
                imagem_url_mobile=f"https://cdn.exemplo.com/banner-{ordem}-mobile.jpg",
                alt=titulo,
                link_url=f"https://exemplo.com/campanha-{ordem}",
                ordem=ordem,
                ativo=(ordem <= 3),  # um inativo, para provar o filtro
            )
        )
    sessao.commit()
    print("banners: 4 criados (3 ativos)")


def _marcar_categorias_destaque(sessao: Session) -> None:
    ja_marcadas = sessao.scalar(
        select(func.count()).select_from(Categoria).where(Categoria.destaque.is_(True))
    )
    if ja_marcadas:
        print(f"categorias em destaque: {ja_marcadas} já marcadas")
        return

    # Três de cada coleção, alternadas: a home precisa provar que devolve a
    # coleção de cada categoria, e isso não aparece se todas forem da mesma.
    por_colecao: dict[int, list[Categoria]] = {}
    for categoria in sessao.scalars(select(Categoria).order_by(Categoria.id)):
        por_colecao.setdefault(categoria.colecao_id, []).append(categoria)

    escolhidas = []
    for posicao in range(3):
        for colecao_id in sorted(por_colecao):
            if posicao < len(por_colecao[colecao_id]):
                escolhidas.append(por_colecao[colecao_id][posicao])

    for posicao, categoria in enumerate(escolhidas, start=1):
        categoria.destaque = True
        categoria.destaque_ordem = posicao
    sessao.commit()
    print(f"categorias em destaque: {len(escolhidas)} marcadas")


def main() -> None:
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument(
        "--limpar", action="store_true", help="apaga produtos, categorias e marcas antes"
    )
    argumentos = analisador.parse_args()

    _exigir_desenvolvimento()

    with SessaoLocal() as sessao:
        if argumentos.limpar:
            _limpar(sessao)

        marcas = _garantir_marcas(sessao)
        categorias = _garantir_categorias(sessao)
        _gerar_produtos(sessao, marcas, categorias)
        _garantir_banners(sessao)
        _marcar_categorias_destaque(sessao)

        total = sessao.scalar(select(func.count()).select_from(Produto))
        visiveis = sessao.scalar(
            select(func.count()).select_from(Produto).where(Produto.status != "oculto")
        )
        sem_imagem = sessao.scalar(
            select(func.count())
            .select_from(Produto)
            .where(~Produto.imagens.any())
        )
        print(f"\ntotal no banco: {total} produtos ({visiveis} visíveis, {sem_imagem} sem imagem)")

    # ANALYZE: sem estatísticas atualizadas o planejador escolhe plano ruim e
    # o EXPLAIN da verificação mede a coisa errada.
    with engine.connect() as conexao:
        conexao.exec_driver_sql("ANALYZE produtos, marcas, categorias, produto_imagens")
    print("ANALYZE concluído")


if __name__ == "__main__":
    main()
