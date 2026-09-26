"""Um cadastro em duas coleções: revisão, edição, contagens e remoção."""
import pytest
from sqlalchemy import select, func

from testes.fabrica import criar_categoria, criar_marca, criar_produto
from vip_api.modelos.catalogo import Categoria, Produto
from testes.teste_admin_revisao import fila_de_teste, ALBUM_TESTE

ROTA = '/api/v1/admin/produtos'


@pytest.fixture
def destinos(sessao):
    feminino = criar_categoria(sessao, 'feminino', 'Peças', 'pecas-personalizadas')
    masculino = criar_categoria(sessao, 'masculino', 'Peças', 'pecas-personalizadas')
    marca = criar_marca(sessao, 'Marca Destinos', 'marca-destinos')
    produto = criar_produto(sessao, 'DEST-001', 'Peça compartilhada', marca, feminino)
    sessao.commit()
    return produto, feminino, masculino


def teste_editar_duas_colecoes_sem_duplicar(admin_logado, destinos):
    produto, feminino, masculino = destinos
    resposta = admin_logado.patch(f'{ROTA}/{produto.id}', json={'categoriasIds': [feminino.id, masculino.id]})
    assert resposta.status_code == 200
    assert resposta.json()['categoriasIds'] == [feminino.id, masculino.id]
    for slug, categoria in [('feminino', feminino), ('masculino', masculino)]:
        publico = admin_logado.get('/api/v1/produtos', params={'colecao': slug, 'categoria': categoria.slug}).json()
        assert [p['id'] for p in publico['dados']] == [produto.id]
        categorias = admin_logado.get(f'/api/v1/colecoes/{slug}/categorias').json()
        assert next(c for c in categorias if c['id'] == categoria.id)['totalProdutos'] == 1
        painel = admin_logado.get(ROTA, params={'colecaoId': categoria.colecao_id}).json()
        assert [p['id'] for p in painel['dados']] == [produto.id]
    assert admin_logado.get('/api/v1/produtos').json()['paginacao']['total'] == 1
    assert admin_logado.get(f'{ROTA}/{produto.id}').json()['categoriasIds'] == [feminino.id, masculino.id]
    assert admin_logado.delete(f'/api/v1/admin/categorias/{masculino.id}').status_code == 409


def teste_remover_colecao_e_preservar_edicao_parcial(admin_logado, destinos):
    produto, feminino, masculino = destinos
    admin_logado.patch(f'{ROTA}/{produto.id}', json={'categoriasIds': [feminino.id, masculino.id]})
    resposta = admin_logado.patch(f'{ROTA}/{produto.id}', json={'nome': 'Novo nome'})
    assert resposta.json()['categoriasIds'] == [feminino.id, masculino.id]
    resposta = admin_logado.patch(f'{ROTA}/{produto.id}', json={'categoriasIds': [masculino.id]})
    assert resposta.json()['categoriasIds'] == [masculino.id]
    assert admin_logado.get('/api/v1/produtos?colecao=feminino').json()['paginacao']['total'] == 0
    assert admin_logado.get('/api/v1/produtos?colecao=masculino').json()['paginacao']['total'] == 1


@pytest.mark.parametrize('caso', ['vazio', 'nulo', 'repetido', 'mesma_colecao', 'inexistente', 'inativa', 'conflito'])
def teste_recusar_destinos_invalidos(admin_logado, sessao, destinos, caso):
    produto, feminino, masculino = destinos
    outra = criar_categoria(sessao, 'feminino', 'Outra', 'outra')
    if caso == 'inativa':
        masculino.ativa = False
        sessao.commit()
    ids = {'vazio': [], 'nulo': None, 'repetido': [feminino.id, feminino.id],
           'mesma_colecao': [feminino.id, outra.id], 'inexistente': [99999999],
           'inativa': [feminino.id, masculino.id], 'conflito': [masculino.id]}[caso]
    corpo = {'categoriasIds': ids}
    if caso == 'conflito':
        corpo['categoriaId'] = feminino.id
    resposta = admin_logado.patch(f'{ROTA}/{produto.id}', json=corpo)
    assert resposta.status_code == 400
    assert admin_logado.get(f'{ROTA}/{produto.id}').json()['categoriasIds'] == [feminino.id]


def teste_duplicacao_preserva_destinos_e_oculta(admin_logado, destinos):
    produto, feminino, masculino = destinos
    admin_logado.patch(f'{ROTA}/{produto.id}', json={'categoriasIds': [feminino.id, masculino.id]})
    copia = admin_logado.post(f'{ROTA}/{produto.id}/duplicar').json()
    assert copia['categoriasIds'] == [feminino.id, masculino.id]
    assert copia['status'] == 'oculto'
    assert admin_logado.get('/api/v1/produtos').json()['paginacao']['total'] == 1


def teste_revisao_usa_categorias_escolhidas_sem_criar_outras(admin_logado, sessao, destinos, fila_de_teste):
    _, feminino, masculino = destinos
    total_categorias = sessao.scalar(select(func.count()).select_from(Categoria))
    corpo = {'productId': ALBUM_TESTE['id'], 'status': 'approved', 'marca': 'Marca Destinos',
             'categoriasIds': [feminino.id, masculino.id]}
    assert admin_logado.post('/api/v1/admin/revisao', json=corpo).status_code == 200
    produto = sessao.scalar(select(Produto).where(Produto.codigo_origem == ALBUM_TESTE['id']))
    assert admin_logado.get(f'{ROTA}/{produto.id}').json()['categoriasIds'] == [feminino.id, masculino.id]
    assert sessao.scalar(select(func.count()).select_from(Categoria)) == total_categorias
    corpo['categoriasIds'] = [masculino.id]
    assert admin_logado.post('/api/v1/admin/revisao', json=corpo).status_code == 200
    assert sessao.scalar(select(func.count()).select_from(Produto).where(Produto.codigo_origem == ALBUM_TESTE['id'])) == 1
    assert admin_logado.get(f'{ROTA}/{produto.id}').json()['categoriasIds'] == [masculino.id]
