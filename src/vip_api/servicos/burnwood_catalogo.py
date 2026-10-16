"""Consulta do catálogo pelo agente da Burnwood (GET /burnwood/catalogo).

O agente manda poucas palavras tiradas da pergunta do cliente ("air force
branco 42", "camiseta polo") e lê os campos da resposta para responder no chat.

Busca por PALAVRA, não pelo texto inteiro como a busca da loja: cada palavra
conta um ponto se casar com o nome, a marca, a categoria, um tamanho, uma cor
ou o código. Vem primeiro quem casa mais palavras. "air force branco 42" acha
o tênis mesmo que "branco" esteja na cor e "42" no tamanho.

Só leitura, e só o que a loja mostra ao cliente, MAIS o preço (decisão de
15/10/2026: o agente informa o preço no chat). Nada de custo, fornecedor,
link de origem ou dado de cliente.
"""

from sqlalchemy import case, func, literal, or_, select
from sqlalchemy.orm import Session

from vip_api.configuracao import configuracao
from vip_api.modelos.catalogo import Categoria, Marca, Produto, ProdutoVariacao
from vip_api.servicos.colecoes import nome_da_colecao
from vip_api.texto import gerar_slug, normalizar

LIMITE_PADRAO = 10
LIMITE_MAXIMO = 20
MAX_PALAVRAS = 8

# Palavras que aparecem na pergunta e não ajudam a achar produto.
_IGNORADAS = frozenset(
    "a o as os de da do das dos e em no na nos nas um uma uns umas com sem para por "
    "tem vocês voces tamanho numero número cor tam".split()
)


def palavras_da_busca(q: str) -> list[str]:
    """`"Tênis Air Force, branco 42"` -> `["tenis", "air", "force", "branco", "42"]`."""
    texto = "".join(c if c.isalnum() else " " for c in normalizar(q))
    palavras = [p for p in texto.split() if p not in _IGNORADAS and (len(p) > 1 or p.isdigit())]
    return list(dict.fromkeys(palavras))[:MAX_PALAVRAS]


def _casa(palavra: str):
    """Expressão SQL: a palavra aparece em algum lugar que o cliente reconhece."""
    termo = f"%{palavra}%"
    variacao = (
        select(ProdutoVariacao.id)
        .where(
            ProdutoVariacao.produto_id == Produto.id,
            func.lower(ProdutoVariacao.valor) == palavra,
        )
        .exists()
    )
    return or_(
        Produto.nome_ordenacao.like(termo),
        Marca.nome_busca.like(termo),
        Categoria.slug.like(f"%{gerar_slug(palavra)}%"),
        # Código "AF1-0042": cada parte conta ("af1", "0042"), mas "42" sozinho
        # não, senão todo tamanho 42 casaria metade dos códigos.
        func.lower(Produto.codigo) == palavra,
        func.lower(Produto.codigo).like(f"{palavra}-%"),
        func.lower(Produto.codigo).like(f"%-{palavra}"),
        variacao,
    )


def _valores(sessao: Session, ids: list[int], tipo: str) -> dict[int, list[str]]:
    """Tamanhos ou cores disponíveis de cada produto, na ordem da grade."""
    linhas = sessao.execute(
        select(ProdutoVariacao.produto_id, ProdutoVariacao.valor)
        .where(
            ProdutoVariacao.produto_id.in_(ids),
            ProdutoVariacao.tipo == tipo,
            ProdutoVariacao.disponivel.is_(True),
        )
        .order_by(ProdutoVariacao.ordem.asc(), ProdutoVariacao.id.asc())
    ).all()
    por_produto: dict[int, list[str]] = {}
    for produto_id, valor in linhas:
        por_produto.setdefault(produto_id, []).append(valor)
    return por_produto


def consultar(sessao: Session, q: str, limite: int) -> list[dict]:
    palavras = palavras_da_busca(q)
    if not palavras:
        return []

    # O código inteiro digitado ganha de qualquer combinação de palavras.
    codigo_exato = case((Produto.codigo == q.strip().upper(), 100), else_=0)
    pontos = codigo_exato + sum(case((_casa(p), 1), else_=0) for p in palavras)
    linhas = sessao.execute(
        select(
            Produto.id,
            Produto.codigo,
            Produto.nome,
            Produto.status,
            Produto.quantidade_disponivel,
            Produto.preco_centavos,
            Marca.nome.label("marca"),
            Categoria.nome.label("categoria"),
            nome_da_colecao(Produto.feminino, Produto.masculino).label("publico"),
            pontos.label("pontos"),
        )
        .join(Marca, Marca.id == Produto.marca_id)
        .join(Categoria, Categoria.id == Produto.categoria_id)
        # Oculto some da loja inteira, e daqui também.
        .where(Produto.status != "oculto", pontos > literal(0))
        .order_by(
            pontos.desc(),
            # Entre os empatados: o que dá para vender agora, depois o mais novo.
            case((Produto.status == "esgotado", 1), else_=0).asc(),
            Produto.criado_em.desc(),
            Produto.id.desc(),
        )
        .limit(limite)
    ).all()

    ids = [linha.id for linha in linhas]
    tamanhos = _valores(sessao, ids, "tamanho")
    cores = _valores(sessao, ids, "cor")
    loja = configuracao.url_da_loja

    return [
        {
            "sku": linha.codigo,
            "nome": linha.nome,
            "marca": linha.marca,
            "categoria": linha.categoria,
            "publico": linha.publico,
            # Em reais. null = sem preço cadastrado: o valor é confirmado pelo atendimento.
            "preco": None if linha.preco_centavos is None else linha.preco_centavos / 100,
            "disponivel": linha.status != "esgotado",
            # null = a equipe não informou a quantidade.
            "estoque": linha.quantidade_disponivel,
            "tamanhos": tamanhos.get(linha.id, []),
            "cores": cores.get(linha.id, []),
            "link": f"{loja}/produto/{linha.codigo}",
        }
        for linha in linhas
    ]
