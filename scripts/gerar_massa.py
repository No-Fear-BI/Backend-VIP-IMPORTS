"""Gera massa de teste para desenvolvimento: 18 marcas, categorias por
coleção e 11.569 produtos com imagens e variações — o tamanho do catálogo real.

Fora do pacote da aplicação de propósito — isto nunca vai para produção.

Reexecutável: usa o `codigo` do produto e o `slug` de marca/categoria como
chave natural e pula o que já existe, então rodar duas vezes não duplica nada.

    python scripts/gerar_massa.py            # cria o que faltar
    python scripts/gerar_massa.py --limpar   # apaga a massa antes de recriar

A distribuição é TORTA de propósito, porque distribuição uniforme esconde
justamente os casos lentos:
- três marcas com milhares de produtos e várias com dezenas;
- metade do catálogo em bolsas, e a coleção feminina com o dobro da masculina;
- nomes que repetem os termos comuns ("bolsa", "preta", "couro"), que é o que
  faz a busca por substring casar com milhares de linhas;
- 12% sem imagem, 20% sem descrição, parte esgotada e parte oculta;
- mais da metade com o MESMO `criado_em`, o instante da carga, como a
  importação da Fatia 5 vai deixar.
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

TOTAL_PRODUTOS = 11_569
SEMENTE = 20260910  # massa reproduzível: mesma semente, mesmo catálogo

# (nome, prefixo do código, QUANTOS produtos). Contagem exata, não peso: três
# marcas com milhares, uma faixa do meio com centenas e a cauda com dezenas.
# A soma tem que dar TOTAL_PRODUTOS, e _gerar_produtos confere.
MARCAS = [
    ("Chanel", "CHN", 3_400),
    ("Louis Vuitton", "LVT", 2_800),
    ("Gucci", "GUC", 1_945),
    ("Prada", "PRD", 900),
    ("Dior", "DIO", 650),
    ("Balenciaga", "BLC", 480),
    ("Saint Laurent", "SLT", 360),
    ("Versace", "VRS", 240),
    ("Fendi", "FND", 180),
    ("Bottega Veneta", "BTV", 150),
    ("Burberry", "BBR", 120),
    ("Hermès", "HRM", 90),
    ("Valentino", "VLT", 70),
    ("Givenchy", "GVC", 60),
    ("Céline", "CLN", 45),
    ("Off-White", "OFW", 35),
    ("Loewe", "LOE", 25),
    ("Goyard", "GOY", 19),
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

# Peso de cada coleção e de cada categoria (pelo slug). Bolsa é metade do
# catálogo de uma loja de grife, e é o filtro que mais vai pesar.
PESO_COLECAO = {"feminino": 2, "masculino": 1}
PESO_CATEGORIA = {
    "bolsas": 50, "sapatos": 14, "acessorios": 14, "oculos": 6,
    "vestidos": 8, "blusas": 8, "camisas": 8, "casacos": 8,
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
# Preta em mais de um terço dos nomes: é a cor que o catálogo real repete.
PESO_COR = [36, 10, 8, 6, 6, 5, 4, 4, 6, 5, 4, 6]
# Termos que voltam de novo e de novo em nome de produto de grife.
TERMOS_COMUNS = ["Couro", "Clássica", "Matelassê", "Monograma", "Pequena", "Média", "Grande"]
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
    for nome, _prefixo, _quantidade in MARCAS:
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
    assert sum(quantidade for *_, quantidade in MARCAS) == TOTAL_PRODUTOS
    aleatorio = random.Random(SEMENTE)
    codigos_existentes = set(sessao.scalars(select(Produto.codigo)))

    marcas_por_slug = {_slug(nome): (nome, prefixo, quantidade) for nome, prefixo, quantidade in MARCAS}

    slug_da_colecao = {c.id: c.slug for c in sessao.scalars(select(Colecao))}
    categorias_por_colecao: dict[int, list[Categoria]] = {}
    for (colecao_id, _slug_cat), categoria in categorias.items():
        categorias_por_colecao.setdefault(colecao_id, []).append(categoria)
    ids_colecao = sorted(categorias_por_colecao)
    pesos_colecao = [PESO_COLECAO.get(slug_da_colecao[i], 1) for i in ids_colecao]

    sequencia_por_marca: dict[str, int] = {}
    for codigo in codigos_existentes:
        prefixo, _, numero = codigo.partition("-")
        if numero.isdigit():
            sequencia_por_marca[prefixo] = max(
                sequencia_por_marca.get(prefixo, 0), int(numero)
            )

    # Uma entrada por produto que falta, já na quantidade exata de cada marca,
    # e embaralhada: a ordem de inserção não pode agrupar a marca inteira.
    fila: list[str] = []
    for slug_marca, (_nome, prefixo, quantidade) in marcas_por_slug.items():
        fila.extend([slug_marca] * max(0, quantidade - sequencia_por_marca.get(prefixo, 0)))
    aleatorio.shuffle(fila)

    agora = datetime.now(timezone.utc)
    # O instante da carga: a importação grava milhares de linhas com o mesmo
    # criado_em, e é o caso em que a paginação só se sustenta pelo desempate
    # por id.
    instante_da_carga = agora - timedelta(days=3)
    criados = 0
    lote: list[Produto] = []

    for slug_marca in fila:
        nome_marca, prefixo, _quantidade = marcas_por_slug[slug_marca]
        marca = marcas[slug_marca]

        colecao_id = aleatorio.choices(ids_colecao, weights=pesos_colecao, k=1)[0]
        opcoes = categorias_por_colecao[colecao_id]
        categoria = aleatorio.choices(
            opcoes, weights=[PESO_CATEGORIA.get(c.slug, 5) for c in opcoes], k=1
        )[0]

        sequencia_por_marca[prefixo] = sequencia_por_marca.get(prefixo, 0) + 1
        codigo = f"{prefixo}-{sequencia_por_marca[prefixo]:04d}"
        if codigo in codigos_existentes:
            continue
        codigos_existentes.add(codigo)

        tipo = categoria.nome.rstrip("s")
        cor = aleatorio.choices(CORES, weights=PESO_COR, k=1)[0]
        modelo = aleatorio.choice(MODELOS)
        termo = aleatorio.choice(TERMOS_COMUNS)
        # Três formatos, para "bolsa preta" sair colado em parte dos nomes e
        # separado em outra — é assim que o cadastro real fica.
        formato = aleatorio.random()
        if formato < 0.4:
            nome = f"{tipo} {cor} {termo} {nome_marca}"
        elif formato < 0.8:
            nome = f"{tipo} {modelo} {cor} {nome_marca}"
        else:
            nome = f"{tipo} {termo} {modelo} {cor} {nome_marca}"

        sorteio = aleatorio.random()
        if sorteio < 0.08:
            status = "oculto"
        elif sorteio < 0.23:
            status = "esgotado"
        else:
            status = "normal"

        if aleatorio.random() < 0.55:
            criado_em = instante_da_carga
        elif aleatorio.random() < 0.4:
            criado_em = agora - timedelta(days=aleatorio.randint(0, 24) * 30)
        else:
            criado_em = agora - timedelta(days=aleatorio.randint(0, 730))

        produto = Produto(
            codigo=codigo,
            nome=nome,
            # 20% sem descrição: a extração nem sempre traz texto.
            descricao=(
                None
                if aleatorio.random() < 0.20
                else f"{nome}. Peça importada, disponível para atendimento."
            ),
            status=status,
            destaque=aleatorio.random() < 0.02,
            marca_id=marca.id,
            categoria_id=categoria.id,
            colecao_id=colecao_id,
            criado_em=criado_em,
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
            for cor_variacao in aleatorio.sample(CORES, aleatorio.randint(1, 3)):
                produto.variacoes.append(
                    ProdutoVariacao(tipo="cor", valor=cor_variacao, disponivel=True)
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


def _resumo(sessao: Session) -> None:
    total = sessao.scalar(select(func.count()).select_from(Produto))
    visiveis = sessao.scalar(
        select(func.count()).select_from(Produto).where(Produto.status != "oculto")
    )
    sem_imagem = sessao.scalar(
        select(func.count()).select_from(Produto).where(~Produto.imagens.any())
    )
    sem_descricao = sessao.scalar(
        select(func.count()).select_from(Produto).where(Produto.descricao.is_(None))
    )
    mesmo_instante = sessao.scalar(
        select(func.count())
        .select_from(Produto)
        .group_by(Produto.criado_em)
        .order_by(func.count().desc())
        .limit(1)
    )
    print(
        f"\ntotal no banco: {total} produtos ({visiveis} visíveis, {sem_imagem} sem imagem, "
        f"{sem_descricao} sem descrição, {mesmo_instante} no mesmo criado_em)"
    )
    for rotulo, termo in (("'bolsa'", "%bolsa%"), ("'preta'", "%preta%"), ("'bolsa preta'", "%bolsa preta%")):
        casam = sessao.scalar(
            select(func.count()).select_from(Produto).where(Produto.nome_ordenacao.like(termo))
        )
        print(f"  nomes com {rotulo}: {casam}")
    for nome, quantidade in sessao.execute(
        select(Marca.nome, func.count(Produto.id))
        .join(Produto, Produto.marca_id == Marca.id)
        .group_by(Marca.nome)
        .order_by(func.count(Produto.id).desc())
    ):
        print(f"  {nome:<16} {quantidade:>5}")


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
        _resumo(sessao)

    # ANALYZE: sem estatísticas atualizadas o planejador escolhe plano ruim e
    # a medição mede a coisa errada.
    with engine.connect() as conexao:
        conexao.exec_driver_sql("ANALYZE produtos, marcas, categorias, produto_imagens, produto_variacoes")
    print("ANALYZE concluído")


if __name__ == "__main__":
    main()
