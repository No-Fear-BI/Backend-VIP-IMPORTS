"""Verificação do carrinho, da migração do carrinho anônimo e do envio da seleção.

Escrita na Fatia 3 e refeita na revisão 0005, quando o item do carrinho passou
a guardar um PAR de variações (tamanho e cor) em vez de uma só.

Cada passo imprime o estado antes e depois, para a saída se sustentar sozinha
sem quem lê ter que confiar no código.

    python scripts/verificar_fatia3.py <passo>

Passos: restricao, par, unicidade, migracao, congelamento, tudo
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

BASE = "http://localhost:8000/api/v1"


class Cliente:
    """Uma sessão de cliente com seu cookie próprio."""

    def __init__(self, email: str):
        self.email = email
        self.cookie = ""
        corpo, cabecalhos, _ = self._pedir(
            "POST", "/clientes/identificar", {"email": email}, cookie=""
        )
        for chave, valor in cabecalhos:
            if chave.lower() == "set-cookie":
                self.cookie = valor.split(";")[0]
        self.id = corpo["id"]

    def _pedir(self, metodo, caminho, corpo=None, cookie=None):
        dados = json.dumps(corpo).encode() if corpo is not None else None
        req = urllib.request.Request(f"{BASE}{caminho}", data=dados, method=metodo)
        req.add_header("Content-Type", "application/json")
        biscoito = self.cookie if cookie is None else cookie
        if biscoito:
            req.add_header("Cookie", biscoito)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                bruto = r.read().decode("utf-8")
                return (json.loads(bruto) if bruto else None), list(r.headers.items()), r.status
        except urllib.error.HTTPError as e:
            bruto = e.read().decode("utf-8")
            return (json.loads(bruto) if bruto else None), list(e.headers.items()), e.code

    def get(self, caminho):
        return self._pedir("GET", caminho)

    def post(self, caminho, corpo=None):
        return self._pedir("POST", caminho, corpo if corpo is not None else {})

    def patch(self, caminho, corpo):
        return self._pedir("PATCH", caminho, corpo)

    def delete(self, caminho):
        return self._pedir("DELETE", caminho)

    def carrinho(self):
        return self.get("/carrinho")[0]


def etiqueta_do_par(item):
    tamanho = item.get("variacaoTamanho")
    cor = item.get("variacaoCor")
    partes = []
    if tamanho:
        partes.append(f"tamanho={tamanho['valor']}")
    if cor:
        partes.append(f"cor={cor['valor']}")
    return " ".join(partes) if partes else "sem variação"


def mostrar_carrinho(rotulo, itens):
    print(f"  {rotulo}")
    if not itens:
        print("    (vazio)")
        return
    for i in itens:
        print(
            f"    itemId={i['itemId']:<5} {i['codigo']:<10} "
            f"{etiqueta_do_par(i):<28} {i['nome'][:40]}"
        )


def limpar_carrinho(c: Cliente):
    for item in c.carrinho():
        c.delete(f"/carrinho/{item['itemId']}")


# ======================================================================
# Massa de teste — produtos reais do catálogo, escolhidos pelo banco
# ======================================================================


def massa():
    """Um produto Chanel com tamanho M e cor Preta, um produto oculto e um id
    que não existe. Tudo lido do catálogo real: nada é criado para o teste."""
    from sqlalchemy import select

    from vip_api.banco import SessaoLocal
    from vip_api.modelos.catalogo import Marca, Produto, ProdutoVariacao

    with SessaoLocal() as sessao:
        tamanho = select(ProdutoVariacao.id).where(
            ProdutoVariacao.produto_id == Produto.id,
            ProdutoVariacao.tipo == "tamanho",
            ProdutoVariacao.valor == "M",
        )
        cor = select(ProdutoVariacao.id).where(
            ProdutoVariacao.produto_id == Produto.id,
            ProdutoVariacao.tipo == "cor",
            ProdutoVariacao.valor == "Preta",
        )
        produto = sessao.execute(
            select(Produto.id, Produto.codigo, Produto.nome, Marca.nome.label("marca"))
            .join(Marca, Marca.id == Produto.marca_id)
            .where(
                Produto.status != "oculto",
                Marca.nome == "Chanel",
                tamanho.exists(),
                cor.exists(),
            )
            .order_by(Produto.id)
            .limit(1)
        ).one()
        variacoes = sessao.execute(
            select(ProdutoVariacao.id, ProdutoVariacao.tipo, ProdutoVariacao.valor).where(
                ProdutoVariacao.produto_id == produto.id,
                ProdutoVariacao.valor.in_(("M", "Preta")),
            )
        ).all()
        oculto = sessao.scalar(
            select(Produto.id).where(Produto.status == "oculto").order_by(Produto.id).limit(1)
        )

    dados = {
        "produto_id": produto.id,
        "codigo": produto.codigo,
        "nome": produto.nome,
        "marca": produto.marca,
        "oculto_id": oculto,
        "inexistente_id": 99_999_999,
    }
    for linha in variacoes:
        dados["tamanho_id" if linha.tipo == "tamanho" else "cor_id"] = linha.id
    return dados


def um_carrinho_qualquer(sessao):
    from sqlalchemy import select

    from vip_api.modelos.cliente import Carrinho

    return sessao.scalar(select(Carrinho.id).order_by(Carrinho.id).limit(1))


# ======================================================================
# restricao — a CHECK e a FK composta, no SQL, sem passar pela API
# ======================================================================


def passo_restricao():
    from sqlalchemy import text

    from vip_api.banco import SessaoLocal

    d = massa()
    print(
        f"produto {d['codigo']} ({d['marca']}) — tamanho M = id {d['tamanho_id']}, "
        f"cor Preta = id {d['cor_id']}\n"
    )

    with SessaoLocal() as sessao:
        carrinho_id = um_carrinho_qualquer(sessao)

    base = "INSERT INTO carrinho_itens (carrinho_id, produto_id, {colunas}) VALUES ({valores})"
    tentativas = [
        (
            "cor gravada na coluna de tamanho (tipo vem do DEFAULT 'tamanho')",
            base.format(
                colunas="variacao_tamanho_id",
                valores=f"{carrinho_id}, {d['produto_id']}, {d['cor_id']}",
            ),
        ),
        (
            "cor gravada na coluna de tamanho, declarando o tipo 'cor'",
            base.format(
                colunas="variacao_tamanho_id, variacao_tamanho_tipo",
                valores=f"{carrinho_id}, {d['produto_id']}, {d['cor_id']}, 'cor'",
            ),
        ),
        (
            "tamanho gravado na coluna de cor",
            base.format(
                colunas="variacao_cor_id",
                valores=f"{carrinho_id}, {d['produto_id']}, {d['tamanho_id']}",
            ),
        ),
        (
            "tamanho na coluna de tamanho e cor na de cor (o caso que TEM que passar)",
            base.format(
                colunas="variacao_tamanho_id, variacao_cor_id",
                valores=f"{carrinho_id}, {d['produto_id']}, {d['tamanho_id']}, {d['cor_id']}",
            ),
        ),
    ]

    for rotulo, sql in tentativas:
        print(f"  {rotulo}")
        with SessaoLocal() as sessao:
            try:
                sessao.execute(text(sql))
                print("    => ACEITOU")
            except Exception as erro:
                original = getattr(erro, "orig", erro)
                linhas = [l for l in str(original).strip().splitlines() if l.strip()]
                print(f"    => RECUSOU: {linhas[0]}")
                for linha in linhas[1:]:
                    if linha.startswith(("DETAIL", "DETALHE")):
                        print(f"       {linha}")
            finally:
                # Nada deste passo fica no banco.
                sessao.rollback()
        print()

    # A mesma inversão chegando pela API: o serviço recusa antes do banco, para
    # o frontend receber VARIACAO_INVALIDA no campo certo em vez de um 500.
    c = Cliente("verificacao.restricao@nofear.test")
    corpo_invertido = {
        "produtoId": d["produto_id"],
        "variacaoTamanhoId": d["cor_id"],
        "variacaoCorId": d["tamanho_id"],
    }
    corpo, _, status = c.post("/carrinho", corpo_invertido)
    print(f"  POST /carrinho {json.dumps(corpo_invertido)}")
    print(f"    => HTTP {status} {json.dumps(corpo, ensure_ascii=False)}")


# ======================================================================
# par — item com as duas variações, com uma só, com nenhuma
# ======================================================================


def passo_par():
    d = massa()
    c = Cliente("verificacao.par@nofear.test")
    limpar_carrinho(c)

    print(f"produto {d['codigo']} — {d['nome']} ({d['marca']})\n")

    envios = [
        ("tamanho M + cor Preta", {"variacaoTamanhoId": d["tamanho_id"], "variacaoCorId": d["cor_id"]}),
        ("só tamanho M", {"variacaoTamanhoId": d["tamanho_id"]}),
        ("nenhuma variação", {}),
    ]
    for rotulo, extra in envios:
        corpo, _, status = c.post("/carrinho", {"produtoId": d["produto_id"], **extra})
        print(f"  POST /carrinho  {rotulo:<28} HTTP {status} {json.dumps(corpo)}")

    print()
    mostrar_carrinho("GET /carrinho", c.carrinho())

    corpo, _, _ = c.post("/selecoes")
    print("\n  POST /selecoes — mensagem do WhatsApp:")
    for linha in corpo["mensagemWhatsapp"].splitlines():
        print(f"    {linha}")
    print(f"\n  rótulo de cada item: {[i['variacao'] for i in corpo['itens']]}")

    limpar_carrinho(c)


# ======================================================================
# unicidade — NULLS NOT DISTINCT sobre o PAR
# ======================================================================


def passo_unicidade():
    d = massa()
    c = Cliente("verificacao.unicidade@nofear.test")
    limpar_carrinho(c)

    envios = [
        ("tamanho M + cor Preta", {"variacaoTamanhoId": d["tamanho_id"], "variacaoCorId": d["cor_id"]}),
        ("tamanho M + cor Preta (de novo)", {"variacaoTamanhoId": d["tamanho_id"], "variacaoCorId": d["cor_id"]}),
        ("só tamanho M", {"variacaoTamanhoId": d["tamanho_id"]}),
        ("só cor Preta", {"variacaoCorId": d["cor_id"]}),
        ("nenhuma variação", {}),
        ("nenhuma variação (de novo)", {}),
    ]
    for rotulo, extra in envios:
        _, _, status = c.post("/carrinho", {"produtoId": d["produto_id"], **extra})
        print(f"  POST {rotulo:<35} HTTP {status}  -> {len(c.carrinho())} item(ns)")

    print()
    mostrar_carrinho("GET /carrinho — mesmo produto, todas as combinações", c.carrinho())

    # PATCH troca o PAR inteiro. Aqui ele leva o item "só cor Preta" para o par
    # completo, que já existe: os dois viram um.
    so_cor = next(i for i in c.carrinho() if not i["variacaoTamanho"] and i["variacaoCor"])
    corpo = {"variacaoTamanhoId": d["tamanho_id"], "variacaoCorId": d["cor_id"]}
    _, _, status = c.patch(f"/carrinho/{so_cor['itemId']}", corpo)
    print()
    print(f"  PATCH /carrinho/{so_cor['itemId']} {json.dumps(corpo)} -> HTTP {status}")
    mostrar_carrinho("GET /carrinho — depois da troca que colidiu", c.carrinho())

    limpar_carrinho(c)


# ======================================================================
# migracao — as três regras de colisão do carrinho anônimo
# ======================================================================


def passo_migracao():
    d = massa()
    c = Cliente("verificacao.migracao@nofear.test")
    limpar_carrinho(c)

    c.post(
        "/carrinho",
        {"produtoId": d["produto_id"], "variacaoTamanhoId": d["tamanho_id"], "variacaoCorId": d["cor_id"]},
    )
    mostrar_carrinho("carrinho da CONTA antes de migrar", c.carrinho())

    corpo_migracao = {
        "itens": [
            # Regra 1: mesmo produto, mesmo par -> não duplica.
            {"produtoId": d["produto_id"], "variacaoTamanhoId": d["tamanho_id"], "variacaoCorId": d["cor_id"]},
            # Regra 2: mesmo produto, par diferente -> item novo.
            {"produtoId": d["produto_id"], "variacaoTamanhoId": d["tamanho_id"]},
            {"produtoId": d["produto_id"], "variacaoCorId": d["cor_id"]},
            # Regra 3: produto oculto e produto inexistente -> ignorados.
            {"produtoId": d["oculto_id"]},
            {"produtoId": d["inexistente_id"], "variacaoCorId": d["cor_id"]},
        ]
    }
    print("\n  POST /carrinho/migrar — corpo do visitante anônimo:")
    for item in corpo_migracao["itens"]:
        print(f"    {json.dumps(item)}")

    corpo, _, status = c.post("/carrinho/migrar", corpo_migracao)
    print(f"\n  HTTP {status}")
    mostrar_carrinho("itens da resposta (carrinho final da conta)", corpo["itens"])
    print("  ignorados")
    for i in corpo["ignorados"]:
        print(f"    produtoId={i['produtoId']:<10} motivo={i['motivo']:<22} {i['mensagem']}")

    limpar_carrinho(c)


# ======================================================================
# congelamento — a seleção enviada não segue o catálogo
# ======================================================================


def passo_congelamento():
    from sqlalchemy import select, update

    from vip_api.banco import SessaoLocal
    from vip_api.modelos.catalogo import Produto

    d = massa()
    c = Cliente("verificacao.congelamento@nofear.test")
    limpar_carrinho(c)
    c.post(
        "/carrinho",
        {"produtoId": d["produto_id"], "variacaoTamanhoId": d["tamanho_id"], "variacaoCorId": d["cor_id"]},
    )

    corpo, _, _ = c.post("/selecoes")
    selecao_id = corpo["id"]
    print(f"  seleção {selecao_id} enviada:")
    for i in corpo["itens"]:
        print(f"    {i['codigo']} — {i['nome']} ({i['marca']}, {i['variacao']})")

    novo_nome = "PRODUTO RENOMEADO DEPOIS DO ENVIO"
    with SessaoLocal() as sessao:
        sessao.execute(update(Produto).where(Produto.id == d["produto_id"]).values(nome=novo_nome))
        sessao.commit()
    print(f"\n  catálogo alterado: produto {d['produto_id']} renomeado para {novo_nome!r}")

    historico, _, _ = c.get("/selecoes")
    enviada = next(s for s in historico["dados"] if s["id"] == selecao_id)
    print("\n  GET /selecoes — o que o histórico mostra:")
    for i in enviada["itens"]:
        print(f"    {i['codigo']} — {i['nome']} ({i['marca']}, {i['variacao']})")

    with SessaoLocal() as sessao:
        sessao.execute(
            update(Produto).where(Produto.id == d["produto_id"]).values(nome=d["nome"])
        )
        sessao.commit()
        atual = sessao.scalar(select(Produto.nome).where(Produto.id == d["produto_id"]))
    print(f"\n  catálogo restaurado: {atual!r}")

    congelado = all(i["nome"] != novo_nome for i in enviada["itens"])
    rotulo_intacto = all(i["variacao"] == "M / Preta" for i in enviada["itens"])
    print(
        f"  => {'OK' if congelado and rotulo_intacto else 'FALHOU'} — "
        "nome e par de variações congelados no envio"
    )

    limpar_carrinho(c)


PASSOS = {
    "restricao": passo_restricao,
    "par": passo_par,
    "unicidade": passo_unicidade,
    "migracao": passo_migracao,
    "congelamento": passo_congelamento,
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
