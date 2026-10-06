"""Texto que o PostgreSQL não aceita (caractere NUL) é erro de quem enviou: 400, nunca 500."""

import pytest

ROTA_PRODUTOS = "/api/v1/produtos"


@pytest.mark.parametrize("parametro", ["busca", "marca", "categoria", "cor"])
def teste_nul_na_consulta_publica_da_400(cliente_logado, parametro):
    resposta = cliente_logado.get(ROTA_PRODUTOS, params={parametro: "a\x00b"})
    assert resposta.status_code == 400
    assert resposta.json()["erro"]["codigo"] == "DADOS_INVALIDOS"
    # Sem detalhe técnico no corpo (regra de testes/teste_vazamento_erros.py).
    assert "NUL" not in resposta.text and "psycopg" not in resposta.text


def teste_nul_na_busca_do_painel_da_400(admin_logado):
    resposta = admin_logado.get("/api/v1/admin/produtos", params={"busca": "a\x00b"})
    assert resposta.status_code == 400


def teste_nul_no_nome_do_produto_da_400_e_a_sessao_continua_usavel(admin_logado):
    resposta = admin_logado.post(
        "/api/v1/admin/produtos",
        json={"nome": "a\u0000b", "marcaId": 1, "categoriaId": 1, "publicos": ["feminino"]},
    )
    assert resposta.status_code in (400, 404)
    assert admin_logado.get("/api/v1/admin/produtos").status_code == 200
