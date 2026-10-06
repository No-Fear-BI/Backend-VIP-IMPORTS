"""O WhatsApp recebe a mensagem sem criar histórico no sistema."""
from sqlalchemy import inspect, select
from vip_api.modelos.catalogo import ProdutoVariacao

def teste_envio_sem_historico(cliente_logado, sessao, produto_com_variacoes, contar_consultas):
    produto = produto_com_variacoes
    variacoes = {v.tipo: v.id for v in sessao.scalars(select(ProdutoVariacao).where(ProdutoVariacao.produto_id == produto.id))}
    assert cliente_logado.post('/api/v1/carrinho', json={'produtoId': produto.id, 'variacaoTamanhoId': variacoes['tamanho'], 'variacaoCorId': variacoes['cor']}).status_code == 200
    with contar_consultas() as consultas:
        resposta = cliente_logado.post('/api/v1/selecoes')
        repetida = cliente_logado.post('/api/v1/selecoes')
    assert resposta.status_code == repetida.status_code == 200
    corpo = resposta.json()
    assert corpo == repetida.json()
    assert set(corpo) == {'itens', 'mensagemWhatsapp', 'linkWhatsapp'}
    assert '(Chanel, M / Preto)' in corpo['mensagemWhatsapp']
    from urllib.parse import parse_qs, urlsplit
    assert parse_qs(urlsplit(corpo['linkWhatsapp']).query)['text'] == [corpo['mensagemWhatsapp']]
    assert not any(q.lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE ')) for q in consultas)
    assert len(cliente_logado.get('/api/v1/carrinho').json()) == 1
    tabelas = inspect(sessao.connection()).get_table_names()
    assert 'selecoes' not in tabelas and 'selecao_itens' not in tabelas

def teste_rotas_historico_removidas(cliente_logado, admin_logado):
    assert cliente_logado.get('/api/v1/selecoes').status_code == 405
    assert admin_logado.get('/api/v1/admin/selecoes').status_code == 404
    assert admin_logado.get('/api/v1/admin/selecoes/1').status_code == 404

def teste_envio_vazio(cliente_logado):
    resposta = cliente_logado.post('/api/v1/selecoes')
    assert resposta.status_code == 400
    assert resposta.json()['erro']['codigo'] == 'CARRINHO_VAZIO'
