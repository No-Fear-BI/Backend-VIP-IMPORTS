"""A aprovacao deve publicar no catalogo real, na colecao e na marca escolhidas."""
import pytest
from sqlalchemy import select, func
from vip_api.rotas import admin_revisao
from vip_api.modelos.catalogo import Produto, ProdutoImagem
from vip_api.modelos.revisao import DecisaoRevisao
from testes.fabrica import criar_categoria, criar_marca


@pytest.fixture
def origem(monkeypatch):
    item = dict(id='teste-revisao-42', name='Black shirt', category='Camisas', supplier='Fornecedor',
                image='https://photo.yupoo.com/teste/medium.jpg', sourceUrl='https://teste.x.yupoo.com/albums/42')
    monkeypatch.setattr(admin_revisao, '_catalogo', lambda: ([item], {item['id']: item}))
    return item


def aprovar(http, origem, categoria, marca):
    return http.post('/api/v1/admin/revisao', json={
        'productId': origem['id'], 'status': 'approved', 'translatedName': 'Camisa revisada',
        'categoriaId': categoria.id, 'marcaId': marca.id,
    })


def aprovar_duas_colecoes(http, origem, categorias, marca):
    return http.post('/api/v1/admin/revisao', json={
        'productId': origem['id'], 'status': 'approved', 'translatedName': 'Camisa revisada',
        'categoriasIds': [categoria.id for categoria in categorias], 'marcaId': marca.id,
    })


def teste_um_produto_nas_duas_colecoes_sem_duplicar_em_todos(admin_logado, sessao, origem):
    categorias = [
        criar_categoria(sessao, 'feminino', 'Camisas revisão', 'camisas-revisao'),
        criar_categoria(sessao, 'masculino', 'Camisas revisão', 'camisas-revisao'),
    ]
    marca = criar_marca(sessao, 'Marca Revisão', 'marca-revisao')
    sessao.flush()
    resposta = aprovar_duas_colecoes(admin_logado, origem, categorias, marca)
    assert resposta.status_code == 200, resposta.text
    produto_id = resposta.json()['produtoId']
    assert produto_id in [p['id'] for p in admin_logado.get('/api/v1/produtos?colecao=feminino').json()['dados']]
    assert produto_id in [p['id'] for p in admin_logado.get('/api/v1/produtos?colecao=masculino').json()['dados']]
    todos = admin_logado.get('/api/v1/produtos').json()['dados']
    assert [p['id'] for p in todos].count(produto_id) == 1


@pytest.mark.parametrize('colecao,outra', [('masculino', 'feminino'), ('feminino', 'masculino')])
def teste_aprovacao_publica_em_todos_colecao_marca_e_detalhe(admin_logado, sessao, origem, colecao, outra):
    categoria = criar_categoria(sessao, colecao, 'Camisas revisão', 'camisas-revisao')
    marca = criar_marca(sessao, 'Marca Revisão', 'marca-revisao')
    sessao.flush()
    resposta = aprovar(admin_logado, origem, categoria, marca)
    assert resposta.status_code == 200, resposta.text
    produto_id = resposta.json()['produtoId']
    for query in ('', f'?colecao={colecao}', '?marca=marca-revisao', f'?colecao={colecao}&categoria=camisas-revisao'):
        dados = admin_logado.get('/api/v1/produtos' + query).json()['dados']
        assert produto_id in [p['id'] for p in dados]
    assert produto_id not in [p['id'] for p in admin_logado.get('/api/v1/produtos?colecao=' + outra).json()['dados']]
    detalhe = admin_logado.get('/api/v1/produtos/' + resposta.json()['codigo'])
    assert detalhe.status_code == 200
    assert detalhe.json()['marca']['slug'] == marca.slug
    assert detalhe.json()['imagens'][0]['url'].startswith('/api/v1/produtos-aprovados/imagem?')
    assert admin_logado.get('/api/v1/admin/revisao/pendentes').json()['total'] == 0
    vitrine = admin_logado.get('/api/v1/produtos-aprovados').json()
    assert any(p['id'] == produto_id and p['codigo'] == resposta.json()['codigo'] for p in vitrine)


def teste_reenvio_e_desfazer_nao_duplicam_produto(admin_logado, sessao, origem):
    categoria = criar_categoria(sessao, 'masculino', 'Camisas revisão', 'camisas-revisao')
    marca = criar_marca(sessao, 'Marca Revisão', 'marca-revisao')
    resposta = aprovar(admin_logado, origem, categoria, marca).json()
    assert aprovar(admin_logado, origem, categoria, marca).json()['produtoId'] == resposta['produtoId']
    assert sessao.scalar(select(func.count()).select_from(ProdutoImagem).where(ProdutoImagem.produto_id == resposta['produtoId'])) == 1
    assert admin_logado.delete('/api/v1/admin/revisao', params={'produtoId': origem['id']}).status_code == 200
    assert admin_logado.get('/api/v1/produtos/' + resposta['codigo']).status_code == 404
    assert admin_logado.get('/api/v1/produtos-aprovados').json() == []
    assert admin_logado.get('/api/v1/admin/revisao/pendentes').json()['total'] == 1
    assert aprovar(admin_logado, origem, categoria, marca).json()['produtoId'] == resposta['produtoId']
    assert sessao.scalar(select(func.count()).select_from(Produto).where(Produto.codigo_origem == origem['id'])) == 1
    assert admin_logado.post('/api/v1/admin/revisao', json={'productId': origem['id'], 'status': 'rejected'}).status_code == 200
    assert admin_logado.get('/api/v1/produtos/' + resposta['codigo']).status_code == 404


def teste_recusa_aprovacao_sem_destino_ou_com_destino_inativo(admin_logado, sessao, origem):
    corpo = {'productId': origem['id'], 'status': 'approved'}
    assert admin_logado.post('/api/v1/admin/revisao', json=corpo).status_code == 400
    assert sessao.get(DecisaoRevisao, origem['id']) is None
    categoria = criar_categoria(sessao, 'feminino', 'Camisas revisão', 'camisas-revisao')
    marca = criar_marca(sessao, 'Marca Revisão', 'marca-revisao')
    marca.ativa = False
    sessao.flush()
    assert aprovar(admin_logado, origem, categoria, marca).status_code == 400
    marca.ativa = True
    categoria.ativa = False
    sessao.flush()
    assert aprovar(admin_logado, origem, categoria, marca).status_code == 400
    assert sessao.get(DecisaoRevisao, origem['id']) is None
    assert sessao.scalar(select(func.count()).select_from(Produto).where(Produto.codigo_origem == origem['id'])) == 0


def teste_visitante_nao_pode_aprovar(sem_sessao, origem):
    assert sem_sessao.post('/api/v1/admin/revisao', json={'productId': origem['id'], 'status': 'approved'}).status_code == 401


def teste_excluir_produto_nao_republica_como_aprovacao_antiga(admin_logado, sessao, origem):
    categoria = criar_categoria(sessao, 'masculino', 'Camisas revisão', 'camisas-revisao')
    marca = criar_marca(sessao, 'Marca Revisão', 'marca-revisao')
    resposta = aprovar(admin_logado, origem, categoria, marca).json()
    assert admin_logado.delete('/api/v1/admin/produtos/' + str(resposta['produtoId'])).status_code == 200
    assert admin_logado.get('/api/v1/produtos-aprovados').json() == []
