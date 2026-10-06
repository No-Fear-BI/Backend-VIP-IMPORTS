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
    Marca,
    Produto,
    ProdutoImagem,
    ProdutoVariacao,
)
from vip_api.servicos.admin_variacoes import obter_ou_criar_cor
from vip_api.servicos.colecoes import nome_do_publico

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
    """Categoria por slug (único na tabela desde a 0015). `colecao_slug` não vai para o
    banco: fica só no objeto como o público PADRÃO dos produtos criados com ela, para os
    testes que ainda contam "a categoria do Feminino"."""
    categoria = sessao.scalar(select(Categoria).where(Categoria.slug == slug))
    if categoria is None:
        categoria = Categoria(nome=nome, slug=slug)
        sessao.add(categoria)
        sessao.flush()
    categoria._publico_padrao = colecao_slug
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
    publicos: list[str] | None = None,
) -> Produto:
    publicos = publicos or [getattr(categoria, "_publico_padrao", "feminino")]
    produto = Produto(
        codigo=codigo,
        nome=nome,
        status=status,
        marca_id=marca.id,
        categoria_id=categoria.id,
        feminino="feminino" in publicos,
        masculino="masculino" in publicos,
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
