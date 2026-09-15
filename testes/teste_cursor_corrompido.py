"""Cursor adulterado é 400 CURSOR_INVALIDO, nunca 500.

Achado da varredura de vazamento (tarefa 78): base64 e JSON válidos com
`"id": "abc"` passavam pela decodificação e estouravam no `int()` do serviço.
Não vazava nada, mas o visitante recebia "não foi possível concluir a
operação" por um link mal copiado.
"""

import pytest

from testes.teste_vazamento_erros import CURSORES_CORROMPIDOS

QUEBRADOS = {nome: valor for nome, valor in CURSORES_CORROMPIDOS.items() if nome != "cursor com id gigante"}


@pytest.mark.parametrize("nome", sorted(QUEBRADOS))
def teste_catalogo_recusa_cursor_corrompido(sem_sessao, nome):
    resposta = sem_sessao.get("/api/v1/produtos", params={"cursor": QUEBRADOS[nome]})

    assert resposta.status_code == 400
    assert resposta.json()["erro"]["codigo"] == "CURSOR_INVALIDO"


@pytest.mark.parametrize("nome", sorted(QUEBRADOS))
def teste_historico_de_selecoes_recusa_cursor_corrompido(cliente_logado, nome):
    resposta = cliente_logado.get("/api/v1/selecoes", params={"cursor": QUEBRADOS[nome]})

    assert resposta.status_code == 400
    assert resposta.json()["erro"]["codigo"] == "CURSOR_INVALIDO"
