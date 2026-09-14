"""Verificação das rotas do painel, contra a massa grande.

Os testes de testes/teste_admin_produtos.py já cobrem estas regras e rodam em
segundos; este roteiro existe para ver o antes e o depois em cima do catálogo
real de desenvolvimento, com 5.000 produtos e clientes de verdade.

    python scripts/verificar_admin_produtos.py <passo>

Passos: codigo, exclusao, duplicar, lote, imagens, variacoes, status, filtro,
        marcas, categorias, banners, home, tudo
"""

import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# 127.0.0.1 e não "localhost": pelo nome, o urllib tenta ::1 primeiro e cada
# requisição carrega ~2 s de espera antes de cair no IPv4.
BASE = "http://127.0.0.1:8000/api/v1"


class Painel:
    """Sessão de admin. A senha vem do ambiente para não ficar no código."""

    def __init__(self) -> None:
        self.cookie = ""
        corpo, cabecalhos, status = self._pedir(
            "POST",
            "/admin/sessao",
            {
                "email": os.environ.get("ADMIN_EMAIL", "painel@nofear.com.br"),
                "senha": os.environ["ADMIN_SENHA"],
            },
        )
        if status != 200:
            raise SystemExit(f"login do painel falhou: HTTP {status} {corpo}")
        for chave, valor in cabecalhos:
            if chave.lower() == "set-cookie":
                self.cookie = valor.split(";")[0]

    def _pedir(self, metodo, caminho, corpo=None):
        dados = json.dumps(corpo).encode() if corpo is not None else None
        req = urllib.request.Request(f"{BASE}{caminho}", data=dados, method=metodo)
        req.add_header("Content-Type", "application/json")
        if self.cookie:
            req.add_header("Cookie", self.cookie)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                bruto = r.read().decode("utf-8")
                return (json.loads(bruto) if bruto else None), list(r.headers.items()), r.status
        except urllib.error.HTTPError as e:
            bruto = e.read().decode("utf-8")
            return (json.loads(bruto) if bruto else None), list(e.headers.items()), e.code

    def get(self, caminho):
        return self._pedir("GET", caminho)[0::2]

    def post(self, caminho, corpo=None):
        return self._pedir("POST", caminho, corpo if corpo is not None else {})[0::2]

    def patch(self, caminho, corpo):
        return self._pedir("PATCH", caminho, corpo)[0::2]

    def delete(self, caminho):
        return self._pedir("DELETE", caminho)[0::2]


class Cliente(Painel):
    """Sessão de CLIENTE, para os passos que precisam de carrinho e favoritos.
    Herda só o transporte HTTP do Painel — a identificação é outra."""

    def __init__(self, email: str):
        self.cookie = ""
        corpo, cabecalhos, status = self._pedir(
            "POST", "/clientes/identificar", {"email": email}
        )
        if status != 200:
            raise SystemExit(f"identificação do cliente falhou: HTTP {status} {corpo}")
        for chave, valor in cabecalhos:
            if chave.lower() == "set-cookie":
                self.cookie = valor.split(";")[0]
        self.id = corpo["id"]

    def carrinho(self):
        return self.get("/carrinho")[0]


def _sessao_do_banco():
    from vip_api.banco import SessaoLocal

    return SessaoLocal()


def _marca_e_categoria(sessao):
    from sqlalchemy import select

    from vip_api.modelos.catalogo import Categoria, Marca

    marca = sessao.execute(
        select(Marca.id, Marca.nome).where(Marca.slug == "chanel")
    ).first()
    categoria = sessao.execute(
        select(Categoria.id, Categoria.nome).order_by(Categoria.id).limit(1)
    ).first()
    return marca, categoria


# ======================================================================
# codigo — geração e colisão
# ======================================================================


def passo_codigo() -> None:
    painel = Painel()
    with _sessao_do_banco() as sessao:
        marca, categoria = _marca_e_categoria(sessao)

    print(f"  marca {marca.nome} (id {marca.id}), categoria {categoria.nome} (id {categoria.id})")

    corpo, status = painel.post(
        "/admin/produtos",
        {"nome": "Bolsa de Verificação", "marcaId": marca.id, "categoriaId": categoria.id},
    )
    print("\n  POST /admin/produtos sem código:")
    print(f"    HTTP {status}  codigo gerado: {corpo.get('codigo')}")
    gerado = corpo["codigo"]
    criado_id = corpo["id"]

    repetido, status = painel.post(
        "/admin/produtos",
        {
            "codigo": gerado,
            "nome": "Outra Bolsa",
            "marcaId": marca.id,
            "categoriaId": categoria.id,
        },
    )
    print(f"\n  POST /admin/produtos com o MESMO código ({gerado}):")
    print(f"    HTTP {status} {json.dumps(repetido, ensure_ascii=False)}")

    outro, status = painel.post(
        "/admin/produtos",
        {"nome": "Terceira Bolsa", "marcaId": marca.id, "categoriaId": categoria.id},
    )
    print(f"\n  POST /admin/produtos sem código de novo: {outro.get('codigo')} (HTTP {status})")

    for identificador in (criado_id, outro["id"]):
        painel.delete(f"/admin/produtos/{identificador}")
    print("\n  (os produtos criados neste passo foram excluídos)")


# ======================================================================
# exclusao — carrinho some, seleção fica
# ======================================================================


def passo_exclusao() -> None:
    from sqlalchemy import func, select

    from vip_api.modelos.catalogo import Produto
    from vip_api.modelos.cliente import CarrinhoItem
    from vip_api.modelos.selecao import SelecaoItem

    painel = Painel()

    with _sessao_do_banco() as sessao:
        # Um produto que esteja nos dois lugares ao mesmo tempo: no carrinho
        # de alguém (dado vivo) e numa seleção já enviada (congelado).
        # Preferindo um cujo item congelado tenha variação: é o que mostra
        # que o texto inteiro sobrevive, não só o nome.
        com_variacao = select(SelecaoItem.produto_id).where(
            SelecaoItem.variacao_tamanho.is_not(None)
        )
        alvo = sessao.execute(
            select(Produto.id, Produto.codigo, Produto.nome)
            .where(
                Produto.id.in_(select(CarrinhoItem.produto_id)),
                Produto.id.in_(select(SelecaoItem.produto_id)),
            )
            .order_by(Produto.id.in_(com_variacao).desc(), Produto.id)
            .limit(1)
        ).first()

    if alvo is None:
        raise SystemExit(
            "nenhum produto está ao mesmo tempo num carrinho e numa seleção — "
            "rode scripts/verificar_fatia3.py congelamento antes."
        )

    def contar():
        with _sessao_do_banco() as sessao:
            return {
                "carrinho_itens": sessao.scalar(
                    select(func.count()).select_from(CarrinhoItem).where(
                        CarrinhoItem.produto_id == alvo.id
                    )
                ),
                "selecao_itens": sessao.scalar(
                    select(func.count()).select_from(SelecaoItem).where(
                        SelecaoItem.produto_id == alvo.id
                    )
                ),
                # A mesma tabela contada pelo CÓDIGO congelado: é o número que
                # mostra que as linhas continuam lá depois do SET NULL.
                "selecao_linhas": sessao.scalar(
                    select(func.count()).select_from(SelecaoItem).where(
                        SelecaoItem.produto_codigo == alvo.codigo
                    )
                ),
                "selecao_congelada": sessao.execute(
                    select(
                        SelecaoItem.produto_id,
                        SelecaoItem.produto_codigo,
                        SelecaoItem.produto_nome,
                        SelecaoItem.variacao_tamanho,
                        SelecaoItem.variacao_cor,
                    ).where(SelecaoItem.produto_codigo == alvo.codigo)
                ).first(),
            }

    antes = contar()
    print(f"  produto {alvo.codigo} — {alvo.nome} (id {alvo.id})")
    print("\n  ANTES")
    print(f"    carrinho_itens apontando para ele: {antes['carrinho_itens']}")
    print(f"    selecao_itens com produto_id = {alvo.id}: {antes['selecao_itens']}")
    print(f"    selecao_itens com o código congelado {alvo.codigo}: {antes['selecao_linhas']}")
    print(f"    uma linha congelada: {tuple(antes['selecao_congelada'])}")

    corpo, status = painel.delete(f"/admin/produtos/{alvo.id}")
    print(f"\n  DELETE /admin/produtos/{alvo.id}  ->  HTTP {status} {json.dumps(corpo)}")

    depois = contar()
    print("\n  DEPOIS")
    print(f"    carrinho_itens apontando para ele: {depois['carrinho_itens']}")
    print(f"    selecao_itens com produto_id = {alvo.id}: {depois['selecao_itens']}")
    print(f"    selecao_itens com o código congelado {alvo.codigo}: {depois['selecao_linhas']}")
    print(f"    uma linha congelada: {tuple(depois['selecao_congelada'])}")


# ======================================================================
# duplicar — original e cópia lado a lado
# ======================================================================


def passo_duplicar() -> None:
    from sqlalchemy import func, select

    from vip_api.modelos.catalogo import Produto, ProdutoImagem, ProdutoVariacao

    painel = Painel()

    with _sessao_do_banco() as sessao:
        # Um produto com imagens E variações, para a cópia ter o que copiar.
        alvo = sessao.execute(
            select(
                Produto.id,
                Produto.codigo,
                func.count(ProdutoImagem.id.distinct()).label("imagens"),
                func.count(ProdutoVariacao.id.distinct()).label("variacoes"),
            )
            .join(ProdutoImagem, ProdutoImagem.produto_id == Produto.id)
            .join(ProdutoVariacao, ProdutoVariacao.produto_id == Produto.id)
            .group_by(Produto.id)
            .having(func.count(ProdutoImagem.id.distinct()) >= 3)
            .having(func.count(ProdutoVariacao.id.distinct()) >= 3)
            .limit(1)
        ).first()

    original, _ = painel.get(f"/admin/produtos/{alvo.id}")
    copia, status = painel.post(f"/admin/produtos/{alvo.id}/duplicar")
    print(f"  POST /admin/produtos/{alvo.id}/duplicar  ->  HTTP {status}\n")

    cabecalho = f"  {'':<18} {'ORIGINAL':<40} {'CÓPIA':<40}"
    print(cabecalho)
    print(f"  {'-' * 18} {'-' * 40} {'-' * 40}")
    linhas = [
        ("id", original["id"], copia["id"]),
        ("codigo", original["codigo"], copia["codigo"]),
        ("nome", original["nome"][:38], copia["nome"][:38]),
        ("status", original["status"], copia["status"]),
        ("destaque", original["destaque"], copia["destaque"]),
        ("imagens", len(original["imagens"]), len(copia["imagens"])),
        ("variacoes", len(original["variacoes"]), len(copia["variacoes"])),
        (
            "ordem das imagens",
            [i["ordem"] for i in original["imagens"]],
            [i["ordem"] for i in copia["imagens"]],
        ),
    ]
    for rotulo, esquerda, direita in linhas:
        print(f"  {rotulo:<18} {str(esquerda):<40} {str(direita):<40}")

    iguais = [
        (i["url"], i["ordem"]) for i in original["imagens"]
    ] == [(i["url"], i["ordem"]) for i in copia["imagens"]]
    print(f"\n  imagens idênticas em url e ordem: {iguais}")

    painel.delete(f"/admin/produtos/{copia['id']}")
    print("  (a cópia foi excluída)")


# ======================================================================
# lote — id inexistente não altera nada
# ======================================================================


def passo_lote() -> None:
    from sqlalchemy import select

    from vip_api.modelos.catalogo import Produto

    painel = Painel()

    with _sessao_do_banco() as sessao:
        alvos = sessao.execute(
            select(Produto.id, Produto.codigo, Produto.status)
            .where(Produto.status == "normal")
            .order_by(Produto.id)
            .limit(3)
        ).all()

    ids = [linha.id for linha in alvos]
    inexistente = 99_999_999

    print("  ANTES")
    for linha in alvos:
        print(f"    id={linha.id:<6} {linha.codigo:<10} status={linha.status}")

    corpo, status = painel.patch(
        "/admin/produtos/lote",
        {"ids": ids[:2] + [inexistente] + ids[2:], "status": "oculto"},
    )
    print(f"\n  PATCH /admin/produtos/lote com o id {inexistente} no meio:")
    print(f"    HTTP {status} {json.dumps(corpo, ensure_ascii=False)}")

    with _sessao_do_banco() as sessao:
        depois = sessao.execute(
            select(Produto.id, Produto.codigo, Produto.status).where(Produto.id.in_(ids))
        ).all()
    print("\n  DEPOIS (nenhum mudou)")
    for linha in sorted(depois, key=lambda item: item.id):
        print(f"    id={linha.id:<6} {linha.codigo:<10} status={linha.status}")

    corpo, status = painel.patch("/admin/produtos/lote", {"ids": ids, "status": "esgotado"})
    print(f"\n  o mesmo lote SÓ com ids válidos: HTTP {status} {json.dumps(corpo)}")
    corpo, status = painel.patch("/admin/produtos/lote", {"ids": ids, "status": "normal"})
    print(f"  (revertido para 'normal': HTTP {status} {json.dumps(corpo)})")

    corpo, status = painel.patch(
        "/admin/produtos/lote", {"ids": ids, "nome": "Renomeando em lote"}
    )
    print(f"\n  PATCH /admin/produtos/lote com um campo fora da lista:")
    print(f"    HTTP {status} {json.dumps(corpo, ensure_ascii=False)}")


# ======================================================================
# imagens — ordem contígua e capa a cada operação
# ======================================================================


def _galeria(rotulo, imagens, capa_id=None):
    print(f"  {rotulo}")
    if not imagens:
        print("    (sem imagem)")
        return
    for imagem in imagens:
        marca = " <- CAPA" if capa_id == imagem["id"] else ""
        print(f"    ordem={imagem['ordem']}  id={imagem['id']:<6} {imagem['url']}{marca}")


def _capa_no_banco(produto_id):
    from sqlalchemy import select

    from vip_api.modelos.catalogo import ProdutoImagem

    with _sessao_do_banco() as sessao:
        return sessao.scalar(
            select(ProdutoImagem.id).where(
                ProdutoImagem.produto_id == produto_id, ProdutoImagem.capa.is_(True)
            )
        )


def passo_imagens() -> None:
    painel = Painel()
    with _sessao_do_banco() as sessao:
        marca, categoria = _marca_e_categoria(sessao)

    produto, _ = painel.post(
        "/admin/produtos",
        {"nome": "Bolsa da Galeria", "marcaId": marca.id, "categoriaId": categoria.id},
    )
    print(f"  produto {produto['codigo']} (id {produto['id']}), criado sem imagem\n")

    imagens, status = painel.post(
        f"/admin/produtos/{produto['id']}/imagens",
        {
            "imagens": [
                {"url": "https://cdn.test/frente.jpg", "alt": "frente"},
                {"url": "https://cdn.test/lado.jpg"},
                {"url": "https://cdn.test/interior.jpg"},
            ]
        },
    )
    print(f"  POST .../imagens com três URLs  ->  HTTP {status}")
    _galeria("depois de inserir:", imagens, _capa_no_banco(produto["id"]))

    invertida = [imagens[2]["id"], imagens[0]["id"], imagens[1]["id"]]
    reordenadas, status = painel.patch(
        f"/admin/produtos/{produto['id']}/imagens/ordem", {"ids": invertida}
    )
    print(f"\n  PATCH .../imagens/ordem {invertida}  ->  HTTP {status}")
    _galeria("depois de reordenar:", reordenadas, _capa_no_banco(produto["id"]))

    capa_atual = reordenadas[0]["id"]
    restantes, status = painel.delete(f"/admin/imagens/{capa_atual}")
    print(f"\n  DELETE /admin/imagens/{capa_atual} (a CAPA)  ->  HTTP {status}")
    _galeria("depois de apagar a capa:", restantes, _capa_no_banco(produto["id"]))

    print("\n  PATCH .../imagens/ordem com lista PARCIAL:")
    recusa, status = painel.patch(
        f"/admin/produtos/{produto['id']}/imagens/ordem", {"ids": [restantes[0]["id"]]}
    )
    print(f"    HTTP {status} {json.dumps(recusa, ensure_ascii=False)}")
    depois, _ = painel.get(f"/admin/produtos/{produto['id']}")
    _galeria("a galeria continua intacta:", depois["imagens"], _capa_no_banco(produto["id"]))

    painel.delete(f"/admin/produtos/{produto['id']}")
    print("\n  (o produto deste passo foi excluído)")


# ======================================================================
# variacoes — substituição com dois carrinhos em jogo
# ======================================================================


def passo_variacoes() -> None:
    from sqlalchemy import select

    from vip_api.modelos.catalogo import ProdutoVariacao
    from vip_api.modelos.cliente import Carrinho, CarrinhoItem

    painel = Painel()
    with _sessao_do_banco() as sessao:
        marca, categoria = _marca_e_categoria(sessao)

    produto, _ = painel.post(
        "/admin/produtos",
        {"nome": "Bolsa das Variações", "marcaId": marca.id, "categoriaId": categoria.id},
    )
    painel.patch(
        f"/admin/produtos/{produto['id']}/variacoes",
        {
            "variacoes": [
                {"tipo": "tamanho", "valor": "M"},
                {"tipo": "tamanho", "valor": "G"},
                {"tipo": "cor", "valor": "Preto"},
                {"tipo": "cor", "valor": "Bege"},
            ]
        },
    )

    def grade():
        with _sessao_do_banco() as sessao:
            return {
                f"{v.tipo}:{v.valor}": v.id
                for v in sessao.scalars(
                    select(ProdutoVariacao)
                    .where(ProdutoVariacao.produto_id == produto["id"])
                    .order_by(ProdutoVariacao.tipo, ProdutoVariacao.valor)
                )
            }

    ids = grade()
    print(f"  produto {produto['codigo']} (id {produto['id']})")
    print(f"  grade inicial: {json.dumps(ids, ensure_ascii=False)}\n")

    # Dois clientes, dois carrinhos, cada um com dois itens do mesmo produto.
    clientes = [
        Cliente("verificacao.var1@nofear.test"),
        Cliente("verificacao.var2@nofear.test"),
    ]
    for pessoa in clientes:
        for item in pessoa.carrinho():
            pessoa.delete(f"/carrinho/{item['itemId']}")
        pessoa.post(
            "/carrinho",
            {
                "produtoId": produto["id"],
                "variacaoTamanhoId": ids["tamanho:M"],
                "variacaoCorId": ids["cor:Bege"],
            },
        )
        pessoa.post(
            "/carrinho",
            {"produtoId": produto["id"], "variacaoTamanhoId": ids["tamanho:M"]},
        )

    def mostrar_carrinhos(rotulo):
        print(f"  {rotulo}")
        with _sessao_do_banco() as sessao:
            linhas = sessao.execute(
                select(
                    CarrinhoItem.id,
                    Carrinho.cliente_id,
                    CarrinhoItem.variacao_tamanho_id,
                    CarrinhoItem.variacao_cor_id,
                )
                .join(Carrinho, Carrinho.id == CarrinhoItem.carrinho_id)
                .where(CarrinhoItem.produto_id == produto["id"])
                .order_by(CarrinhoItem.id)
            ).all()
        for linha in linhas:
            print(
                f"    item={linha.id:<6} cliente={linha.cliente_id:<4} "
                f"tamanho={str(linha.variacao_tamanho_id):<7} cor={linha.variacao_cor_id}"
            )
        if not linhas:
            print("    (nenhum item)")

    mostrar_carrinhos("carrinhos ANTES (dois clientes, dois itens cada):")

    nova, status = painel.patch(
        f"/admin/produtos/{produto['id']}/variacoes",
        {"variacoes": [{"tipo": "tamanho", "valor": "M"}, {"tipo": "cor", "valor": "Vermelha"}]},
    )
    print(f"\n  PATCH .../variacoes deixando só tamanho M e cor Vermelha  ->  HTTP {status}")
    depois_ids = grade()
    for chave, identificador in sorted(depois_ids.items()):
        origem = "MESMO id" if ids.get(chave) == identificador else "id novo"
        print(f"    {chave:<16} id={identificador:<7} ({origem})")
    for chave in sorted(set(ids) - set(depois_ids)):
        print(f"    {chave:<16} REMOVIDA (era id={ids[chave]})")

    print()
    mostrar_carrinhos("carrinhos DEPOIS:")

    painel.delete(f"/admin/produtos/{produto['id']}")
    print("\n  (o produto deste passo foi excluído)")


# ======================================================================
# status — os pontos de saída, antes e depois
# ======================================================================


def passo_status() -> None:
    from sqlalchemy import func, select

    from vip_api.modelos.catalogo import Produto
    from vip_api.modelos.cliente import CarrinhoItem, Favorito

    from vip_api.modelos.catalogo import Categoria, Colecao, Marca

    painel = Painel()
    with _sessao_do_banco() as sessao:
        # Um produto em destaque, com marca e categoria conhecidas, para dar
        # para conferir a home e as contagens de navegação.
        # O alvo tem que estar VISÍVEL em todos os pontos medidos, senão a
        # linha de zeros não prova nada. Para os relacionados, isso exige um
        # par (marca, categoria) pequeno: a rota devolve 8, e num grupo de 600
        # o alvo nunca apareceria. O destaque é ligado logo abaixo, pela API.
        grupo_pequeno = (
            select(Produto.marca_id, Produto.categoria_id)
            .where(Produto.status != "oculto")
            .group_by(Produto.marca_id, Produto.categoria_id)
            .having(func.count() <= 8)
            .having(func.count() >= 2)
            .limit(1)
        ).subquery("g")
        alvo = sessao.execute(
            select(Produto.id, Produto.codigo, Produto.marca_id, Produto.categoria_id)
            .join(
                grupo_pequeno,
                (Produto.marca_id == grupo_pequeno.c.marca_id)
                & (Produto.categoria_id == grupo_pequeno.c.categoria_id),
            )
            .where(Produto.status == "normal")
            .order_by(Produto.id)
            .limit(1)
        ).first()
        marca_slug = sessao.scalar(
            select(Marca.slug).where(Marca.id == alvo.marca_id)
        )
        categoria = sessao.execute(
            select(Categoria.slug, Colecao.slug.label("colecao"))
            .join(Colecao, Colecao.id == Categoria.colecao_id)
            .where(Categoria.id == alvo.categoria_id)
        ).first()
        # Um vizinho de mesma marca e categoria: é pelos relacionados DELE que
        # se vê se o alvo vazou.
        vizinho = sessao.scalar(
            select(Produto.codigo)
            .where(
                Produto.marca_id == alvo.marca_id,
                Produto.categoria_id == alvo.categoria_id,
                Produto.status == "normal",
                Produto.id != alvo.id,
            )
            .limit(1)
        )

    # Destaque ligado com ordem 0: a home mostra os 12 primeiros por
    # destaque_ordem, e o alvo precisa estar entre eles. Devolvido ao estado
    # original no fim do passo.
    painel.patch(f"/admin/produtos/{alvo.id}", {"destaque": True, "destaqueOrdem": 0})

    pessoa = Cliente("verificacao.status@nofear.test")
    for item in pessoa.carrinho():
        pessoa.delete(f"/carrinho/{item['itemId']}")
    pessoa.post("/favoritos", {"produtoId": alvo.id})
    pessoa.post("/carrinho", {"produtoId": alvo.id})

    def medir():
        # Busca pelo código: a listagem tem 5 mil produtos e o alvo pode
        # não cair na primeira página. Pelo código, ou ele está na lista
        # pública ou não está.
        listagem, _ = pessoa.get(f"/produtos?busca={alvo.codigo}")
        detalhe, status_detalhe = pessoa.get(f"/produtos/{alvo.codigo}")
        relacionados, _ = pessoa.get(f"/produtos/{vizinho}/relacionados")
        home, _ = pessoa.get("/home")
        marcas, _ = pessoa.get("/marcas")
        categorias, _ = pessoa.get(f"/colecoes/{categoria.colecao}/categorias")
        favoritos, _ = pessoa.get("/favoritos")
        carrinho, _ = pessoa.get("/carrinho")
        with _sessao_do_banco() as sessao:
            favoritos_no_banco = sessao.scalar(
                select(func.count()).select_from(Favorito).where(Favorito.produto_id == alvo.id)
            )
            carrinho_no_banco = sessao.scalar(
                select(func.count())
                .select_from(CarrinhoItem)
                .where(CarrinhoItem.produto_id == alvo.id)
            )
        return {
            "GET /produtos?busca=<codigo>": sum(
                1 for i in listagem["dados"] if i["id"] == alvo.id
            ),
            "GET /produtos/:codigo": status_detalhe,
            "GET /relacionados do vizinho": sum(
                1 for i in relacionados if i["id"] == alvo.id
            ),
            "GET /home destaques (o alvo)": sum(
                1 for i in home["destaques"] if i["id"] == alvo.id
            ),
            f"GET /marcas totalProdutos ({marca_slug})": [
                m for m in marcas if m["slug"] == marca_slug
            ][0]["totalProdutos"],
            f"GET /colecoes/{categoria.colecao}/categorias ({categoria.slug})": [
                c for c in categorias if c["slug"] == categoria.slug
            ][0]["totalProdutos"],
            "GET /favoritos (o alvo)": sum(1 for i in favoritos if i["id"] == alvo.id),
            "GET /carrinho (o alvo)": sum(1 for i in carrinho if i["id"] == alvo.id),
            "linhas de favorito no banco": favoritos_no_banco,
            "linhas de carrinho no banco": carrinho_no_banco,
        }

    print(f"  produto {alvo.codigo} (id {alvo.id}), marca {marca_slug}, categoria {categoria.slug}\n")
    antes = medir()
    painel.patch(f"/admin/produtos/{alvo.id}", {"status": "oculto"})
    oculto = medir()
    painel.patch(f"/admin/produtos/{alvo.id}", {"status": "normal"})
    voltou = medir()

    largura = max(len(chave) for chave in antes)
    print(f"  {'PONTO DE SAÍDA':<{largura}}  {'normal':>8} {'oculto':>8} {'normal':>8}")
    print(f"  {'-' * largura}  {'-' * 8} {'-' * 8} {'-' * 8}")
    for chave in antes:
        print(f"  {chave:<{largura}}  {antes[chave]:>8} {oculto[chave]:>8} {voltou[chave]:>8}")

    print(f"\n  voltou ao estado inicial: {antes == voltou}")
    for item in pessoa.carrinho():
        pessoa.delete(f"/carrinho/{item['itemId']}")
    pessoa.delete(f"/favoritos/{alvo.id}")
    painel.patch(f"/admin/produtos/{alvo.id}", {"destaque": False})


# ======================================================================
# filtro — o total da paginação bate com a contagem real
# ======================================================================


def passo_filtro() -> None:
    from sqlalchemy import func, select

    from vip_api.modelos.catalogo import Marca, Produto

    painel = Painel()
    with _sessao_do_banco() as sessao:
        marca = sessao.execute(
            select(Marca.id, Marca.nome, Marca.slug).where(Marca.slug == "chanel")
        ).first()
        reais = {
            filtro: sessao.scalar(
                select(func.count()).select_from(Produto).where(*condicoes)
            )
            for filtro, condicoes in {
                "sem filtro": (),
                f"marcaId={marca.id}": (Produto.marca_id == marca.id,),
                "status=oculto": (Produto.status == "oculto",),
                f"marcaId={marca.id} + status=oculto": (
                    Produto.marca_id == marca.id,
                    Produto.status == "oculto",
                ),
                "busca=matelasse": (Produto.nome_ordenacao.like("%matelasse%"),),
            }.items()
        }

    consultas = {
        "sem filtro": "",
        f"marcaId={marca.id}": f"&marcaId={marca.id}",
        "status=oculto": "&status=oculto",
        f"marcaId={marca.id} + status=oculto": f"&marcaId={marca.id}&status=oculto",
        "busca=matelasse": "&busca=matelasse",
    }

    print(f"  marca {marca.nome} (id {marca.id})\n")
    print(f"  {'FILTRO':<38} {'total da API':>13} {'contagem real':>14} {'bate':>6}")
    print(f"  {'-' * 38} {'-' * 13} {'-' * 14} {'-' * 6}")
    for rotulo, sufixo in consultas.items():
        corpo, _ = painel.get(f"/admin/produtos?porPagina=1{sufixo}")
        total = corpo["paginacao"]["total"]
        print(f"  {rotulo:<38} {total:>13} {reais[rotulo]:>14} {str(total == reais[rotulo]):>6}")


# ======================================================================
# marcas — slug na criação, slug intacto na edição
# ======================================================================


def passo_marcas() -> None:
    from sqlalchemy import func, select

    from vip_api.modelos.catalogo import Marca, Produto

    painel = Painel()

    criada, status = painel.post("/admin/marcas", {"nome": "Maison Margiela"})
    print(f"  POST /admin/marcas {{'nome': 'Maison Margiela'}}  ->  HTTP {status}")
    print(f"    slug gerado: {criada['slug']!r}")

    editada, status = painel.patch(
        f"/admin/marcas/{criada['id']}", {"nome": "MAISON MARGIELA Paris"}
    )
    print(f"\n  PATCH só com o nome  ->  HTTP {status}")
    print(f"    nome:  {editada['nome']!r}")
    print(f"    slug:  {editada['slug']!r}  (intacto)")

    com_slug, status = painel.patch(
        f"/admin/marcas/{criada['id']}", {"slug": "Maison Margiela Paris"}
    )
    print(f"\n  PATCH mandando slug  ->  HTTP {status}")
    print(f"    slug:  {com_slug['slug']!r}  (normalizado)")

    painel.delete(f"/admin/marcas/{criada['id']}")

    # --- 409 com a contagem, conferida contra o banco --------------------
    with _sessao_do_banco() as sessao:
        alvo = sessao.execute(
            select(Marca.id, Marca.nome, func.count(Produto.id).label("total"))
            .join(Produto, Produto.marca_id == Marca.id)
            .group_by(Marca.id)
            .order_by(func.count(Produto.id).desc())
            .limit(1)
        ).first()

    corpo, status = painel.delete(f"/admin/marcas/{alvo.id}")
    print(f"\n  DELETE /admin/marcas/{alvo.id} ({alvo.nome}, com produtos)  ->  HTTP {status}")
    print(f"    {json.dumps(corpo, ensure_ascii=False)}")
    print(f"    contagem real no banco: {alvo.total}")

    vazia, _ = painel.post("/admin/marcas", {"nome": "Marca de Verificação"})
    corpo, status = painel.delete(f"/admin/marcas/{vazia['id']}")
    print(f"\n  DELETE de uma marca SEM produtos  ->  HTTP {status} {json.dumps(corpo)}")


# ======================================================================
# categorias — slug por coleção e a troca de coleção
# ======================================================================


def passo_categorias() -> None:
    from sqlalchemy import func, select

    from vip_api.modelos.catalogo import Categoria, Colecao, Produto

    painel = Painel()
    with _sessao_do_banco() as sessao:
        colecoes = {c.slug: c.id for c in sessao.scalars(select(Colecao))}

    feminino, status_f = painel.post(
        "/admin/categorias", {"nome": "Echarpes", "colecaoId": colecoes["feminino"]}
    )
    masculino, status_m = painel.post(
        "/admin/categorias", {"nome": "Echarpes", "colecaoId": colecoes["masculino"]}
    )
    print("  POST /admin/categorias 'Echarpes' nas duas coleções:")
    print(f"    feminino:  HTTP {status_f}  id={feminino['id']} slug={feminino['slug']!r}")
    print(f"    masculino: HTTP {status_m}  id={masculino['id']} slug={masculino['slug']!r}")

    repetida, status = painel.post(
        "/admin/categorias",
        {"nome": "Echarpes", "colecaoId": colecoes["feminino"], "slug": "echarpes"},
    )
    print(f"\n  POST repetindo 'echarpes' na MESMA coleção  ->  HTTP {status}")
    print(f"    {json.dumps(repetida, ensure_ascii=False)}")

    for identificador in (feminino["id"], masculino["id"]):
        painel.delete(f"/admin/categorias/{identificador}")

    # --- troca de coleção com produtos ----------------------------------
    with _sessao_do_banco() as sessao:
        alvo = sessao.execute(
            select(
                Categoria.id,
                Categoria.nome,
                Categoria.slug,
                Categoria.colecao_id,
                func.count(Produto.id).label("total"),
            )
            .join(Produto, Produto.categoria_id == Categoria.id)
            .group_by(Categoria.id)
            .order_by(func.count(Produto.id).desc())
            .limit(1)
        ).first()
        colecao_atual = sessao.scalar(select(Colecao.slug).where(Colecao.id == alvo.colecao_id))

    destino = [nome for nome in colecoes if nome != colecao_atual][0]
    print(
        f"\n  categoria {alvo.nome!r} (id {alvo.id}, slug {alvo.slug!r}), "
        f"coleção {colecao_atual}, {alvo.total} produtos"
    )

    def estado():
        with _sessao_do_banco() as sessao:
            categoria = sessao.execute(
                select(Categoria.colecao_id, Colecao.slug)
                .join(Colecao, Colecao.id == Categoria.colecao_id)
                .where(Categoria.id == alvo.id)
            ).first()
            produtos = sessao.execute(
                select(Produto.colecao_id, func.count())
                .where(Produto.categoria_id == alvo.id)
                .group_by(Produto.colecao_id)
            ).all()
        return categoria.slug, {linha[0]: linha[1] for linha in produtos}

    antes = estado()
    print(f"    ANTES  — coleção da categoria: {antes[0]}, produtos por coleção: {antes[1]}")

    corpo, status = painel.patch(
        f"/admin/categorias/{alvo.id}", {"colecaoId": colecoes[destino]}
    )
    print(f"\n  PATCH mudando a coleção para {destino}  ->  HTTP {status}")
    print(f"    {json.dumps(corpo, ensure_ascii=False)}")

    depois = estado()
    print(f"\n    DEPOIS — coleção da categoria: {depois[0]}, produtos por coleção: {depois[1]}")
    print(f"    nada mudou: {antes == depois}")

    corpo, status = painel.delete(f"/admin/categorias/{alvo.id}")
    print(f"\n  DELETE da mesma categoria  ->  HTTP {status}")
    print(f"    {json.dumps(corpo, ensure_ascii=False)}")


# ======================================================================
# banners — teto de quatro ativos, ordem e a home
# ======================================================================


def passo_banners() -> None:
    from sqlalchemy import delete as sql_delete

    from vip_api.modelos.catalogo import Banner

    painel = Painel()
    with _sessao_do_banco() as sessao:
        # A massa de desenvolvimento já tem banners; o passo começa do zero
        # para as contagens ficarem legíveis.
        sessao.execute(sql_delete(Banner))
        sessao.commit()

    criados = []
    for numero in range(1, 6):
        corpo, status = painel.post(
            "/admin/banners",
            {
                "imagemUrl": f"https://cdn.test/verificacao{numero}.jpg",
                "titulo": f"Banner {numero}",
            },
        )
        criados.append(corpo)
    print(f"  cinco banners criados (inativos): ordens {[b['ordem'] for b in criados]}")

    print("\n  ativando um a um:")
    for numero, banner in enumerate(criados, start=1):
        corpo, status = painel.patch(f"/admin/banners/{banner['id']}", {"ativo": True})
        if status == 200:
            print(f"    {numero}º  HTTP {status}  ativo={corpo['ativo']}")
        else:
            print(f"    {numero}º  HTTP {status}  {json.dumps(corpo, ensure_ascii=False)}")

    invertida = [b["id"] for b in reversed(criados)]
    reordenados, status = painel.patch("/admin/banners/ordem", {"ids": invertida})
    print(f"\n  PATCH /admin/banners/ordem invertendo  ->  HTTP {status}")
    for banner in reordenados:
        print(f"    ordem={banner['ordem']}  id={banner['id']:<5} {banner['titulo']:<10} ativo={banner['ativo']}")

    restantes, status = painel.delete(f"/admin/banners/{reordenados[1]['id']}")
    print(f"\n  DELETE do segundo da lista  ->  HTTP {status}")
    for banner in restantes:
        print(f"    ordem={banner['ordem']}  id={banner['id']:<5} {banner['titulo']:<10} ativo={banner['ativo']}")


# ======================================================================
# home — o carrossel público depois de tudo
# ======================================================================


def passo_home() -> None:
    painel = Painel()
    banners, _ = painel.get("/admin/banners")
    home, status = painel.get("/home")

    print(f"  GET /home  ->  HTTP {status}\n")
    print(f"  {'ID':<6} {'ORDEM':<6} {'ATIVO':<6} TÍTULO")
    print(f"  {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 20}")
    for banner in banners:
        print(f"  {banner['id']:<6} {banner['ordem']:<6} {str(banner['ativo']):<6} {banner['titulo']}")

    print(f"\n  banners que a home devolve: {[b['id'] for b in home['banners']]}")
    esperado = [b["id"] for b in banners if b["ativo"]]
    print(f"  ativos do painel, na ordem:  {esperado}")
    print(f"  conferem: {[b['id'] for b in home['banners']] == esperado}")


PASSOS = {
    "codigo": passo_codigo,
    "exclusao": passo_exclusao,
    "duplicar": passo_duplicar,
    "lote": passo_lote,
    "imagens": passo_imagens,
    "variacoes": passo_variacoes,
    "status": passo_status,
    "filtro": passo_filtro,
    "marcas": passo_marcas,
    "categorias": passo_categorias,
    "banners": passo_banners,
    "home": passo_home,
}


def main() -> None:
    escolhido = sys.argv[1] if len(sys.argv) > 1 else "tudo"
    if escolhido != "tudo" and escolhido not in PASSOS:
        print(f"passo desconhecido: {escolhido}")
        print(f"passos: {', '.join(PASSOS)}, tudo")
        sys.exit(2)

    for nome, funcao in PASSOS.items():
        if escolhido in ("tudo", nome):
            print(f"===== {nome} =====")
            funcao()
            print()


if __name__ == "__main__":
    main()
