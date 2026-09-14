"""Travessia do catálogo inteiro seguindo `proximoCursor`.

Versão rápida do scripts/travessia_catalogo.py, que continua existindo para
rodar à mão contra os 5.000 produtos. Aqui são 60 produtos em páginas de 7 —
nove páginas, o suficiente para a comparação de tupla do cursor ter que
funcionar de verdade em cada virada.

O que o teste prova, nas duas ordenações: nenhum produto repete, nenhum some,
nenhum oculto vaza, e o total informado bate com o que existe no banco.
"""

import pytest

POR_PAGINA = 7


def percorrer(http, ordem: str) -> tuple[list[int], int, int]:
    """Devolve (ids na ordem visitada, total informado, páginas)."""
    ids: list[int] = []
    cursor = None
    paginas = 0
    total = None

    while True:
        parametros = {"ordem": ordem, "porPagina": POR_PAGINA}
        if cursor:
            parametros["cursor"] = cursor

        resposta = http.get("/api/v1/produtos", params=parametros)
        assert resposta.status_code == 200
        pagina = resposta.json()
        paginas += 1

        if total is None:
            total = pagina["paginacao"]["total"]
        else:
            # O total é calculado uma vez e viaja no cursor: se mudar no meio,
            # a paginação está recontando a cada página.
            assert pagina["paginacao"]["total"] == total

        ids.extend(item["id"] for item in pagina["dados"])
        cursor = pagina["paginacao"].get("proximoCursor")
        if not cursor:
            break
        assert paginas < 100, "paginação não terminou — provável laço infinito"

    return ids, total, paginas


@pytest.mark.parametrize("ordem", ["recentes", "nome"])
def teste_travessia_nao_repete_nem_pula(sem_sessao, catalogo, ordem):
    ids, total, paginas = percorrer(sem_sessao, ordem)

    assert paginas > 1, "a massa precisa render várias páginas para o teste valer"
    assert len(ids) == len(set(ids)), "a paginação repetiu produto na virada de página"
    assert set(ids) == catalogo.ids_visiveis, "a paginação pulou ou inventou produto"
    assert total == len(catalogo.ids_visiveis)


@pytest.mark.parametrize("ordem", ["recentes", "nome"])
def teste_travessia_nao_vaza_produto_oculto(sem_sessao, catalogo, ordem):
    ids, _, _ = percorrer(sem_sessao, ordem)

    assert not set(ids) & catalogo.ids_ocultos


def teste_ordenacao_por_nome_sai_ordenada(sem_sessao, catalogo):
    """A ordem tem que ser a do banco (COLLATE "C", byte a byte), não a de
    criação — é o que prova que o cursor de `ordem=nome` compara pelo mesmo
    critério do índice."""
    ids, _, _ = percorrer(sem_sessao, "nome")
    por_id = {produto.id: produto.nome_ordenacao for produto in catalogo.visiveis}
    nomes = [por_id[identificador] for identificador in ids]

    assert nomes == sorted(nomes)


def teste_ordenacao_recentes_sai_do_mais_novo_para_o_mais_velho(sem_sessao, catalogo):
    ids, _, _ = percorrer(sem_sessao, "recentes")
    criados = {produto.id: produto.criado_em for produto in catalogo.visiveis}
    datas = [criados[identificador] for identificador in ids]

    assert datas == sorted(datas, reverse=True)
