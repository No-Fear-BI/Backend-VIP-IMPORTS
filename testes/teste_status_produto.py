"""Status do produto ponta a ponta (tarefa 59).

Os três status já existiam no schema e o PATCH já os editava. O que faltava era
provar o COMPORTAMENTO em cada ponto de saída:

- `esgotado` continua na vitrine, marcado — o cliente pode perguntar sobre
  reposição, e produto que some não gera pergunta nenhuma;
- `oculto` some de tudo que é público, SEM apagar registro: favorito e item de
  carrinho continuam no banco e voltam a aparecer se o admin reexibir;
- no painel, os três aparecem.
"""

import pytest
from sqlalchemy import func, select

from testes.fabrica import criar_categoria, criar_marca, criar_produto
from vip_api.modelos.catalogo import Produto
from vip_api.modelos.cliente import CarrinhoItem, Favorito

ADMIN = "/api/v1/admin/produtos"


@pytest.fixture
def vitrine(sessao):
    """Dois produtos da mesma marca e categoria: o alvo, que vai mudar de
    status, e um vizinho, que serve de origem para `/relacionados` e mantém a
    marca com produto visível."""
    marca = criar_marca(sessao, "Chanel", "chanel")
    categoria = criar_categoria(sessao, "feminino", "Bolsas", "bolsas")
    alvo = criar_produto(
        sessao,
        "CHN-9000",
        "Bolsa Alvo",
        marca,
        categoria,
        variacoes=[("tamanho", "M"), ("cor", "Preto")],
    )
    alvo.destaque = True
    alvo.destaque_ordem = 1
    vizinho = criar_produto(sessao, "CHN-9001", "Bolsa Vizinha", marca, categoria)
    sessao.commit()
    return alvo, vizinho


def pontos_de_saida(http_publico, http_cliente, alvo, vizinho) -> dict:
    """Cada ponto por onde o produto pode vazar para o visitante."""
    listagem = http_publico.get("/api/v1/produtos", params={"porPagina": 50}).json()
    marcas = http_publico.get("/api/v1/marcas").json()
    categorias = http_publico.get("/api/v1/colecoes/feminino/categorias").json()
    home = http_publico.get("/api/v1/home").json()
    relacionados = http_publico.get(f"/api/v1/produtos/{vizinho.codigo}/relacionados").json()

    return {
        "GET /produtos": sum(1 for item in listagem["dados"] if item["id"] == alvo.id),
        "GET /produtos (total)": listagem["paginacao"]["total"],
        "GET /produtos/:codigo": http_publico.get(f"/api/v1/produtos/{alvo.codigo}").status_code,
        "GET /produtos/:codigo/relacionados": sum(
            1 for item in relacionados if item["id"] == alvo.id
        ),
        "GET /home (destaques)": sum(
            1 for item in home["destaques"] if item["id"] == alvo.id
        ),
        "GET /marcas (totalProdutos)": [m for m in marcas if m["slug"] == "chanel"][0][
            "totalProdutos"
        ],
        "GET /colecoes/feminino/categorias": [c for c in categorias if c["slug"] == "bolsas"][
            0
        ]["totalProdutos"],
        "GET /favoritos": sum(
            1 for item in http_cliente.get("/api/v1/favoritos").json() if item["id"] == alvo.id
        ),
        "GET /carrinho": sum(
            1 for item in http_cliente.get("/api/v1/carrinho").json() if item["id"] == alvo.id
        ),
    }


def teste_oculto_some_de_todo_ponto_publico_e_volta(
    sem_sessao, cliente_logado, admin_logado, sessao, vitrine
):
    alvo, vizinho = vitrine
    cliente_logado.post("/api/v1/favoritos", json={"produtoId": alvo.id})
    cliente_logado.post("/api/v1/carrinho", json={"produtoId": alvo.id})

    antes = pontos_de_saida(sem_sessao, cliente_logado, alvo, vizinho)
    assert antes == {
        "GET /produtos": 1,
        "GET /produtos (total)": 2,
        "GET /produtos/:codigo": 200,
        "GET /produtos/:codigo/relacionados": 1,
        "GET /home (destaques)": 1,
        "GET /marcas (totalProdutos)": 2,
        "GET /colecoes/feminino/categorias": 2,
        "GET /favoritos": 1,
        "GET /carrinho": 1,
    }

    assert admin_logado.patch(f"{ADMIN}/{alvo.id}", json={"status": "oculto"}).status_code == 200

    depois = pontos_de_saida(sem_sessao, cliente_logado, alvo, vizinho)
    assert depois == {
        "GET /produtos": 0,
        "GET /produtos (total)": 1,
        # Oculto responde 404, igual a inexistente: não é "aparece se você
        # souber a URL".
        "GET /produtos/:codigo": 404,
        "GET /produtos/:codigo/relacionados": 0,
        "GET /home (destaques)": 0,
        "GET /marcas (totalProdutos)": 1,
        "GET /colecoes/feminino/categorias": 1,
        "GET /favoritos": 0,
        "GET /carrinho": 0,
    }

    # NADA foi apagado: as linhas continuam no banco.
    sessao.expire_all()
    assert sessao.scalar(
        select(func.count()).select_from(Favorito).where(Favorito.produto_id == alvo.id)
    ) == 1
    assert sessao.scalar(
        select(func.count()).select_from(CarrinhoItem).where(CarrinhoItem.produto_id == alvo.id)
    ) == 1

    assert admin_logado.patch(f"{ADMIN}/{alvo.id}", json={"status": "normal"}).status_code == 200
    assert pontos_de_saida(sem_sessao, cliente_logado, alvo, vizinho) == antes


def teste_esgotado_continua_na_vitrine_marcado(sem_sessao, admin_logado, vitrine):
    """Esgotado é vitrine: o cliente vê, pergunta sobre reposição, e o
    atendimento responde. Sumir com ele mataria a pergunta."""
    alvo, vizinho = vitrine

    admin_logado.patch(f"{ADMIN}/{alvo.id}", json={"status": "esgotado"})

    listagem = sem_sessao.get("/api/v1/produtos", params={"porPagina": 50}).json()
    (item,) = [i for i in listagem["dados"] if i["id"] == alvo.id]
    detalhe = sem_sessao.get(f"/api/v1/produtos/{alvo.codigo}")

    assert item["status"] == "esgotado"
    assert detalhe.status_code == 200
    assert detalhe.json()["status"] == "esgotado"
    assert listagem["paginacao"]["total"] == 2
    # Continua contando nas listas de navegação.
    marcas = sem_sessao.get("/api/v1/marcas").json()
    assert [m for m in marcas if m["slug"] == "chanel"][0]["totalProdutos"] == 2


def teste_no_painel_os_tres_status_aparecem(admin_logado, sessao, vitrine):
    alvo, _ = vitrine

    for status in ("normal", "esgotado", "oculto"):
        admin_logado.patch(f"{ADMIN}/{alvo.id}", json={"status": status})
        listagem = admin_logado.get(ADMIN, params={"porPagina": 100}).json()
        (item,) = [i for i in listagem["dados"] if i["id"] == alvo.id]
        assert item["status"] == status
        assert listagem["paginacao"]["total"] == 2


def teste_oculto_nao_entra_no_carrinho_nem_nos_favoritos(
    cliente_logado, admin_logado, vitrine
):
    """O produto some das rotas de escrita também: quem tiver a página aberta e
    clicar em favoritar depois da ocultação recebe 404, não um favorito
    fantasma."""
    alvo, _ = vitrine
    admin_logado.patch(f"{ADMIN}/{alvo.id}", json={"status": "oculto"})

    assert cliente_logado.post("/api/v1/favoritos", json={"produtoId": alvo.id}).status_code == 404
    assert cliente_logado.post("/api/v1/carrinho", json={"produtoId": alvo.id}).status_code == 404
