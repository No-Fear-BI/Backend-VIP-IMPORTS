"""Fábrica de massa para os testes.

Pequena de propósito: dezenas de produtos, não milhares. O que os testes
precisam provar é comportamento — paginação que não repete nem pula, colisão
de item no carrinho, congelamento da seleção — e isso aparece com 60 produtos
e páginas de 7. A massa grande continua em scripts/gerar_massa.py, para rodar
à mão contra o banco de desenvolvimento.

Tudo por objeto ORM, nunca por INSERT em massa: `nome_ordenacao` e `nome_busca`
são preenchidos por listener do modelo, e carga em lote pelo Core não dispara
listener nenhum.
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from vip_api.modelos.catalogo import (
    Categoria,
    Colecao,
    Marca,
    Produto,
    ProdutoImagem,
    ProdutoVariacao,
)
from vip_api.servicos.admin_variacoes import obter_ou_criar_cor

# Nomes escolhidos para embaralhar as duas ordenações: em ordem alfabética a
# sequência não bate com a ordem de criação, então uma travessia por `nome`
# que na verdade esteja ordenando por id seria flagrada.
MODELOS = ["Zurique", "Amalfi", "Monaco", "Bordeaux", "Kyoto", "Veneza", "Oslo", "Palermo"]
CORES = ["Preta", "Bege", "Vermelha", "Off-White"]
TAMANHOS = ["PP", "P", "M", "G"]


@dataclass
class Catalogo:
    marcas: list[Marca] = field(default_factory=list)
    categorias: list[Categoria] = field(default_factory=list)
    visiveis: list[Produto] = field(default_factory=list)
    ocultos: list[Produto] = field(default_factory=list)

    @property
    def ids_visiveis(self) -> set[int]:
        return {produto.id for produto in self.visiveis}

    @property
    def ids_ocultos(self) -> set[int]:
        return {produto.id for produto in self.ocultos}


# As duas funções abaixo reaproveitam o que já existe em vez de estourar no
# UNIQUE: marca e categoria são identificadas pelo slug, e um teste que peça as
# duas fixtures (catálogo grande + produto avulso) criaria a mesma "Chanel"
# duas vezes.
def criar_marca(sessao: Session, nome: str, slug: str, ordem: int = 0) -> Marca:
    marca = sessao.scalar(select(Marca).where(Marca.slug == slug))
    if marca is None:
        marca = Marca(nome=nome, slug=slug, ordem=ordem)
        sessao.add(marca)
        sessao.flush()
    return marca


def criar_categoria(sessao: Session, colecao_slug: str, nome: str, slug: str) -> Categoria:
    colecao = sessao.scalar(select(Colecao).where(Colecao.slug == colecao_slug))
    categoria = sessao.scalar(
        select(Categoria).where(Categoria.colecao_id == colecao.id, Categoria.slug == slug)
    )
    if categoria is None:
        categoria = Categoria(colecao_id=colecao.id, nome=nome, slug=slug)
        sessao.add(categoria)
        sessao.flush()
    return categoria


def criar_produto(
    sessao: Session,
    codigo: str,
    nome: str,
    marca: Marca,
    categoria: Categoria,
    status: str = "normal",
    com_imagem: bool = True,
    variacoes: list[tuple[str, str]] | None = None,
) -> Produto:
    produto = Produto(
        codigo=codigo,
        nome=nome,
        status=status,
        marca_id=marca.id,
        categoria_id=categoria.id,
        # Duplicado do da categoria de propósito (FK composta garante que não
        # dessincroniza) — é o que faz o filtro ?colecao= dispensar JOIN.
        colecao_id=categoria.colecao_id,
    )
    sessao.add(produto)
    sessao.flush()

    if com_imagem:
        sessao.add(
            ProdutoImagem(
                produto_id=produto.id, url=f"https://exemplo.test/{codigo}.jpg", capa=True, ordem=1
            )
        )
    for tipo, valor in variacoes or []:
        # Cor passa pelo vocabulário: a ck_produto_variacoes_cor_id (revisão
        # 0007) recusa variação de cor sem cor_id.
        cor = obter_ou_criar_cor(sessao, valor) if tipo == "cor" else None
        sessao.add(
            ProdutoVariacao(
                produto_id=produto.id,
                tipo=tipo,
                valor=cor.nome if cor else valor,
                cor_id=cor.id if cor else None,
            )
        )
    sessao.flush()
    return produto


def montar_catalogo(sessao: Session, visiveis: int = 60, ocultos: int = 6) -> Catalogo:
    catalogo = Catalogo()

    catalogo.marcas = [
        criar_marca(sessao, "Chanel", "chanel", 1),
        criar_marca(sessao, "Gucci", "gucci", 2),
    ]
    catalogo.categorias = [
        criar_categoria(sessao, "feminino", "Bolsas", "bolsas"),
        criar_categoria(sessao, "masculino", "Sapatos", "sapatos"),
    ]

    total = visiveis + ocultos
    for indice in range(total):
        marca = catalogo.marcas[indice % len(catalogo.marcas)]
        categoria = catalogo.categorias[indice % len(catalogo.categorias)]
        modelo = MODELOS[indice % len(MODELOS)]
        oculto = indice >= visiveis
        produto = criar_produto(
            sessao,
            codigo=f"TST-{indice:04d}",
            # O índice no fim do nome garante nome único; o modelo na frente
            # garante que a ordem alfabética não seja a ordem de criação.
            nome=f"{modelo} {marca.nome} {indice:04d}",
            marca=marca,
            categoria=categoria,
            status="oculto" if oculto else ("esgotado" if indice % 11 == 0 else "normal"),
            com_imagem=indice % 5 != 0,
            variacoes=[
                ("tamanho", TAMANHOS[indice % len(TAMANHOS)]),
                ("cor", CORES[indice % len(CORES)]),
            ],
        )
        (catalogo.ocultos if oculto else catalogo.visiveis).append(produto)

    sessao.commit()
    return catalogo


def criar_selecao(
    sessao: Session,
    cliente,
    produtos: list[Produto],
    variacao: tuple[str | None, str | None] = (None, None),
):
    """Seleção ENVIADA, com os itens já congelados — do jeito que
    `criar_selecao` do serviço grava, mas sem passar pelo carrinho.

    Os testes do painel precisam de dezenas de seleções; montar cada uma
    clicando no carrinho pela API custaria centenas de requisições para provar
    coisa nenhuma sobre o carrinho.
    """
    from vip_api.modelos.selecao import Selecao, SelecaoItem

    selecao = Selecao(
        cliente_id=cliente.id,
        cliente_nome=cliente.nome,
        cliente_email=cliente.email,
        cliente_telefone=cliente.telefone,
        total_itens=len(produtos),
    )
    sessao.add(selecao)
    sessao.flush()

    for ordem, produto in enumerate(produtos, start=1):
        categoria = sessao.get(Categoria, produto.categoria_id)
        marca = sessao.get(Marca, produto.marca_id)
        colecao = sessao.get(Colecao, produto.colecao_id)
        sessao.add(
            SelecaoItem(
                selecao_id=selecao.id,
                produto_id=produto.id,
                produto_codigo=produto.codigo,
                produto_nome=produto.nome,
                marca_nome=marca.nome,
                categoria_nome=categoria.nome,
                colecao_nome=colecao.nome,
                imagem_url=f"https://exemplo.test/{produto.codigo}.jpg",
                variacao_tamanho=variacao[0],
                variacao_cor=variacao[1],
                ordem=ordem,
            )
        )
    sessao.flush()
    return selecao
