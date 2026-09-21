"""Testes isolados da revisão, sem PostgreSQL: python scripts/testar_revisao.py."""
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ['DATABASE_URL'] = 'sqlite://'
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from vip_api.rotas import admin_revisao as revisao
from vip_api.modelos.revisao import DecisaoRevisao

class RevisaoTeste(unittest.TestCase):
    def setUp(self):
        self.original = revisao._arquivo
        self.pasta = tempfile.TemporaryDirectory()
        revisao._arquivo = Path(self.pasta.name) / 'catalogo.json'
        self.produtos = [dict(id=f'qwer888-{i}', name=f'Produto {i}', category='Camisas', supplier='qwer888', image='https://photo.yupoo.com/a/medium.jpg', sourceUrl=f'https://1234qwer888.x.yupoo.com/albums/{i}') for i in range(125)]
        self.gravar()
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        DecisaoRevisao.__table__.create(self.engine)
        self.app = FastAPI()
        self.app.include_router(revisao.roteador)
        def sessao():
            with Session(self.engine) as db:
                yield db
        self.app.dependency_overrides[revisao.obter_sessao] = sessao
        self.cliente = TestClient(self.app)

    def gravar(self):
        revisao._arquivo.write_text(json.dumps(self.produtos), encoding='utf8')

    def tearDown(self):
        revisao._arquivo = self.original
        revisao._ler_catalogo.cache_clear()
        self.cliente.close()
        self.engine.dispose()
        self.pasta.cleanup()

    def test_paginacao_filtros_limites(self):
        a = self.cliente.get('/revisao/pendentes').json()
        b = self.cliente.get('/revisao/pendentes?pagina=2').json()
        self.assertEqual(a['total'], 125)
        self.assertEqual(a['paginas'], 3)
        self.assertEqual(len(a['items']), 60)
        self.assertFalse({p['id'] for p in a['items']} & {p['id'] for p in b['items']})
        self.assertEqual(len(self.cliente.get('/revisao/pendentes?pagina=99').json()['items']), 5)
        self.assertEqual(self.cliente.get('/revisao/pendentes?busca=inexistente').json()['total'], 0)
        self.assertEqual(self.cliente.get('/revisao/pendentes?categoria=Bolsas').json()['total'], 0)
        self.assertEqual(self.cliente.get('/revisao/pendentes?pagina=0').status_code, 422)
        self.assertEqual(self.cliente.get('/revisao/pendentes?porPagina=101').status_code, 422)

    def test_decisao_reimportacao_e_reposicao(self):
        resposta = self.cliente.post('/revisao', json={'productId': 'qwer888-0', 'status': 'approved', 'translatedName': 'Camisa revisada'})
        self.assertEqual(resposta.status_code, 200)
        fila = self.cliente.get('/revisao/pendentes').json()
        self.assertEqual(fila['total'], 124)
        self.assertEqual(len(fila['items']), 60)
        self.assertNotIn('qwer888-0', [p['id'] for p in fila['items']])
        self.produtos.append(dict(self.produtos[0], id='qwer888-novo', name='Novo'))
        self.gravar()
        fila = self.cliente.get('/revisao/pendentes?busca=Novo').json()
        self.assertEqual(fila['total'], 1)
        self.assertEqual(self.cliente.get('/revisao/publicados').json()[0]['name'], 'Camisa revisada')
        self.assertEqual(self.cliente.post('/revisao', json={'productId': 'qwer888-novo', 'status': 'rejected'}).status_code, 200)
        self.assertEqual(self.cliente.get('/revisao/pendentes?busca=Novo').json()['total'], 0)

if __name__ == '__main__':
    unittest.main()
