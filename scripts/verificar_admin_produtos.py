"""Verificação das rotas de produto do painel, contra a massa grande.

Os testes de testes/teste_admin_produtos.py já cobrem estas regras e rodam em
segundos; este roteiro existe para ver o antes e o depois em cima do catálogo
real de desenvolvimento, com 5.000 produtos e clientes de verdade.

    python scripts/verificar_admin_produtos.py <passo>

Passos: codigo, exclusao, duplicar, lote, tudo
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


PASSOS = {
    "codigo": passo_codigo,
    "exclusao": passo_exclusao,
    "duplicar": passo_duplicar,
    "lote": passo_lote,
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
