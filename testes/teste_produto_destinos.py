"""Categorias (principal + temas) e público do produto: revisão, edição, contagens e remoção.

Desde a 0015 o produto tem uma categoria principal, até 4 adicionais e, separado disso, o
público (`publicos`: feminino, masculino ou os dois = unissex).
"""
import pytest
from sqlalchemy import select, func

from testes.fabrica import criar_categoria, criar_marca, criar_produto
from vip_api.modelos.catalogo import Categoria, Produto
from testes.teste_admin_revisao import fila_de_teste, ALBUM_TESTE

ROTA = '/api/v1/admin/produtos'


@pytest.fixture
def destinos(sessao):
    pecas = criar_categoria(sessao, 'feminino', 'Peças', 'pecas-personalizadas')
    tema = criar_categoria(sessao, 'feminino', 'Coleção de verão', 'colecao-de-verao')
    marca = criar_marca(sessao, 'Marca Destinos', 'marca-destinos')
    produto = criar_produto(sessao, 'DEST-001', 'Peça compartilhada', marca, pecas)
    sessao.commit()
    return produto, pecas, tema


def teste_editar_duas_categorias_sem_duplicar(admin_logado, destinos):
    produto, pecas, tema = destinos
    resposta = admin_logado.patch(f'{ROTA}/{produto.id}', json={'categoriasIds': [pecas.id, tema.id]})
    assert resposta.status_code == 200
    assert resposta.json()['categoriasIds'] == [pecas.id, tema.id]
    for categoria in (pecas, tema):
        publico = admin_logado.get('/api/v1/produtos', params={'categoria': categoria.slug}).json()
        assert [p['id'] for p in publico['dados']] == [produto.id]
        painel = admin_logado.get(ROTA, params={'categoriaId': categoria.id}).json()
        assert [p['id'] for p in painel['dados']] == [produto.id]
    categorias = admin_logado.get('/api/v1/colecoes/feminino/categorias').json()
    assert {c['id']: c['totalProdutos'] for c in categorias} == {pecas.id: 1, tema.id: 1}
    assert admin_logado.get('/api/v1/produtos').json()['paginacao']['total'] == 1
    assert admin_logado.delete(f'/api/v1/admin/categorias/{tema.id}').status_code == 409


def teste_unissex_aparece_nos_dois_publicos(admin_logado, destinos):
    produto, pecas, _ = destinos
    assert admin_logado.get('/api/v1/produtos?colecao=masculino').json()['paginacao']['total'] == 0
    resposta = admin_logado.patch(f'{ROTA}/{produto.id}', json={'publicos': ['feminino', 'masculino']})
    assert resposta.status_code == 200
    assert resposta.json()['publicos'] == ['feminino', 'masculino']
    assert resposta.json()['colecao']['nome'] == 'Unissex'
    for slug in ('feminino', 'masculino'):
        pagina = admin_logado.get(f'/api/v1/produtos?colecao={slug}&categoria={pecas.slug}').json()
        assert [p['id'] for p in pagina['dados']] == [produto.id]
    # O painel filtra pelos ids fixos 1 (feminino) e 2 (masculino).
    assert admin_logado.get(ROTA, params={'colecaoId': 2}).json()['paginacao']['total'] == 1


def teste_trocar_o_publico_e_preservar_edicao_parcial(admin_logado, destinos):
    produto, pecas, tema = destinos
    admin_logado.patch(f'{ROTA}/{produto.id}', json={'categoriasIds': [pecas.id, tema.id]})
    resposta = admin_logado.patch(f'{ROTA}/{produto.id}', json={'nome': 'Novo nome'})
    assert resposta.json()['categoriasIds'] == [pecas.id, tema.id]
    resposta = admin_logado.patch(f'{ROTA}/{produto.id}', json={'publicos': ['masculino']})
    assert resposta.json()['publicos'] == ['masculino']
    assert resposta.json()['categoriasIds'] == [pecas.id, tema.id]
    assert admin_logado.get('/api/v1/produtos?colecao=feminino').json()['paginacao']['total'] == 0
    assert admin_logado.get('/api/v1/produtos?colecao=masculino').json()['paginacao']['total'] == 1


@pytest.mark.parametrize('caso', ['vazio', 'nulo', 'repetido', 'demais', 'inexistente', 'inativa', 'conflito'])
def teste_recusar_categorias_invalidas(admin_logado, sessao, destinos, caso):
    produto, pecas, tema = destinos
    extras = [criar_categoria(sessao, 'feminino', f'Extra {n}', f'extra-{n}') for n in range(5)]
    if caso == 'inativa':
        tema.ativa = False
    sessao.commit()
    ids = {'vazio': [], 'nulo': None, 'repetido': [pecas.id, pecas.id],
           'demais': [pecas.id] + [c.id for c in extras], 'inexistente': [99999999],
           'inativa': [pecas.id, tema.id], 'conflito': [tema.id]}[caso]
    corpo = {'categoriasIds': ids}
    if caso == 'conflito':
        corpo['categoriaId'] = pecas.id
    resposta = admin_logado.patch(f'{ROTA}/{produto.id}', json=corpo)
    assert resposta.status_code == 400
    assert admin_logado.get(f'{ROTA}/{produto.id}').json()['categoriasIds'] == [pecas.id]


@pytest.mark.parametrize('publicos', [[], ['unissex'], ['feminino', 'feminino', 'masculino']])
def teste_recusar_publico_invalido(admin_logado, destinos, publicos):
    produto, _, _ = destinos
    resposta = admin_logado.patch(f'{ROTA}/{produto.id}', json={'publicos': publicos})
    assert resposta.status_code == 400
    assert admin_logado.get(f'{ROTA}/{produto.id}').json()['publicos'] == ['feminino']


def teste_criar_produto_exige_publico(admin_logado, destinos):
    produto, pecas, _ = destinos
    corpo = {'nome': 'Sem público', 'marcaId': produto.marca_id, 'categoriaId': pecas.id}

    sem_publico = admin_logado.post(ROTA, json=corpo)
    com_publico = admin_logado.post(ROTA, json={**corpo, 'publicos': ['masculino']})

    assert sem_publico.status_code == 400
    assert 'publicos' in sem_publico.json()['erro']['campos']
    assert com_publico.status_code == 201
    assert com_publico.json()['publicos'] == ['masculino']


def teste_duplicacao_preserva_destinos_e_oculta(admin_logado, destinos):
    produto, pecas, tema = destinos
    admin_logado.patch(f'{ROTA}/{produto.id}', json={'categoriasIds': [pecas.id, tema.id], 'publicos': ['feminino', 'masculino']})
    copia = admin_logado.post(f'{ROTA}/{produto.id}/duplicar').json()
    assert copia['categoriasIds'] == [pecas.id, tema.id]
    assert copia['publicos'] == ['feminino', 'masculino']
    assert copia['status'] == 'oculto'
    assert admin_logado.get('/api/v1/produtos').json()['paginacao']['total'] == 1


def teste_revisao_usa_categorias_e_publicos_escolhidos_sem_criar_outras(admin_logado, sessao, destinos, fila_de_teste):
    _, pecas, tema = destinos
    total_categorias = sessao.scalar(select(func.count()).select_from(Categoria))
    corpo = {'productId': ALBUM_TESTE['id'], 'status': 'approved', 'marca': 'Marca Destinos',
             'categoriasIds': [pecas.id, tema.id], 'publicos': ['feminino', 'masculino']}
    assert admin_logado.post('/api/v1/admin/revisao', json=corpo).status_code == 200
    produto = sessao.scalar(select(Produto).where(Produto.codigo_origem == ALBUM_TESTE['id']))
    detalhe = admin_logado.get(f'{ROTA}/{produto.id}').json()
    assert detalhe['categoriasIds'] == [pecas.id, tema.id]
    assert detalhe['publicos'] == ['feminino', 'masculino']
    assert sessao.scalar(select(func.count()).select_from(Categoria)) == total_categorias
    corpo['categoriasIds'] = [tema.id]
    corpo['publicos'] = ['masculino']
    assert admin_logado.post('/api/v1/admin/revisao', json=corpo).status_code == 200
    assert sessao.scalar(select(func.count()).select_from(Produto).where(Produto.codigo_origem == ALBUM_TESTE['id'])) == 1
    detalhe = admin_logado.get(f'{ROTA}/{produto.id}').json()
    assert detalhe['categoriasIds'] == [tema.id]
    assert detalhe['publicos'] == ['masculino']
