"""Fila interna de aprovação dos produtos importados dos fornecedores.

Aprovar um álbum (POST, status='approved') cria — ou, se o mesmo álbum já
tiver sido aprovado antes, ATUALIZA — um PRODUTO DE VERDADE no catálogo,
navegável na loja, pela mesma mecânica de scripts/importar_catalogo.py
(marca/categoria por slug, imagem baixada e convertida pra WebP, variações):
ver vip_api.servicos.importacao_catalogo.importar_produto, reaproveitada
aqui em vez de duplicada. Antes desta função existir, aprovar só gravava
nesta tabela de revisão (DecisaoRevisao) — uma fila paralela que nenhuma
tela pública lia.

`supplier` e `sourceUrl` são o fornecedor e o link do álbum no Yupoo — dado
interno, só de rastreabilidade (nunca serializado em rota pública, igual ao
resto do catálogo real: ver docs/modelagem-banco.md 4.4). NUNCA viram marca:
marca e coleção não vêm do Yupoo (não tem essa informação), então é o admin
quem escolhe as duas na hora de aprovar.

Este roteador inteiro só existe montado dentro de admin_painel.roteador, que
já exige sessão de admin no grupo (`Depends(exigir_admin)`) — não precisa (e
não deve) repetir a dependência rota a rota aqui.
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from time import monotonic
from typing import Literal
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.configuracao import configuracao
from vip_api.erros.excecoes import AppError
from vip_api.esquemas.admin_produto import PRECO_MAXIMO_CENTAVOS
from vip_api.modelos.catalogo import Produto
from vip_api.modelos.revisao import DecisaoRevisao
from vip_api.servicos.produto_destinos import definir_destinos, validar_destinos, validar_publicos
from vip_api.texto import gerar_slug, normalizar
from vip_api.servicos.imagens_processamento import abrir_imagem
from vip_api.servicos.importacao_catalogo import importar_produto
from vip_api.servicos import atualizacao_fila

roteador = APIRouter(prefix='/revisao', tags=['admin'])
_arquivo = Path(__file__).resolve().parents[3] / 'data' / 'pending-products.json'
TAMANHO_MAXIMO_FOTO = 15 * 1024 * 1024  # 15 MB — mesmo teto de scripts/importar_catalogo.py
MAXIMO_FOTOS_POR_PRODUTO = 20
_AGENTE = 'Mozilla/5.0 (compatible; VIPImportsCatalog/1.0)'
# O álbum do Yupoo não muda enquanto o cliente escolhe as fotos: guardar a lista por alguns minutos
# evita abrir a página do fornecedor a cada cartão aberto.
_VALIDADE_ALBUM = 300
_albuns: dict[str, tuple[float, list[str]]] = {}

@lru_cache(maxsize=1)
def _ler_catalogo(versao):
    dados = json.loads(_arquivo.read_text(encoding='utf-8-sig'))
    return dados, {p['id']: p for p in dados}

def _catalogo():
    estado = _arquivo.stat()
    return _ler_catalogo((estado.st_mtime_ns, estado.st_size))
_singular = {'Jaquetas':'Jaqueta','Jaquetas de inverno':'Jaqueta de inverno','Moletons':'Moletom','Coletes':'Colete','Suéteres':'Suéter','Conjuntos':'Conjunto','Ternos':'Terno','Jeans':'Calça jeans','Bermudas':'Bermuda','Camisetas':'Camiseta','Camisas':'Camisa','Casacos':'Casaco','Bolsas':'Bolsa'}
def traduzir(p):
    n=p['name']; d=[]
    for termos, rotulo in ((('hoodie','hooded'),'com capuz'),(('leather',),'de couro'),(('down jacket',),'acolchoada'),(('denim','jeans'),'jeans'),(('knit','sweater'),'de malha')):
        if any(t in n.lower() for t in termos): d.append(rotulo)
    cor=next((x for termos,x in ((('black',),'preta'),(('white',),'branca'),(('blue',),'azul'),(('green',),'verde'),(('red',),'vermelha'),(('brown',),'marrom')) if any(t in n.lower() for t in termos)),None)
    detalhes=([f'Cor: {cor}'] if cor else [])+[f"Referência: {p['id'].split('-',1)[1]}"]
    return {'translatedName':n if p['category']=='A classificar' else ' '.join([_singular.get(p['category'],p['category']),*list(dict.fromkeys(d))[:2]]),'translatedDetails':' • '.join(detalhes)}

def _exigir_origem_yupoo(url: str, source: str) -> None:
    u, s = urlparse(url), urlparse(source)
    if u.scheme != 'https' or u.hostname != 'photo.yupoo.com' or s.scheme != 'https' or not (s.hostname or '').endswith('.x.yupoo.com'):
        raise AppError('ORIGEM_NAO_PERMITIDA', 'Origem não permitida.', 403)

def _fotos_do_album(source: str) -> list[str]:
    """URLs das fotos originais do álbum, na ordem do Yupoo. O álbum só abre com `uid=1` na URL
    (sem ele o Yupoo responde 404) e cada foto vem em `data-origin-src`."""
    s = urlparse(source)
    if s.scheme != 'https' or not (s.hostname or '').endswith('.x.yupoo.com'):
        raise AppError('ORIGEM_NAO_PERMITIDA', 'Origem não permitida.', 403)
    guardado = _albuns.get(source)
    if guardado and monotonic() - guardado[0] < _VALIDADE_ALBUM:
        return guardado[1]
    try:
        with urlopen(Request(f'https://{s.hostname}{s.path}?uid=1', headers={'User-Agent': _AGENTE}), timeout=15) as remoto:
            pagina = remoto.read(5 * 1024 * 1024).decode('utf-8', 'ignore')
    except Exception as exc:
        raise AppError('ALBUM_INDISPONIVEL', 'Não foi possível abrir o álbum no fornecedor.', 502) from exc
    fotos = []
    for url in re.findall(r'data-origin-src="([^"]+)"', pagina):
        url = f'https:{url}' if url.startswith('//') else url
        if url.startswith('https://photo.yupoo.com/') and url not in fotos:
            fotos.append(url)
    if len(_albuns) >= 200:
        _albuns.clear()
    _albuns[source] = (monotonic(), fotos)
    return fotos

def _baixar_foto_yupoo(url: str, source: str):
    """Baixa a foto do álbum — precisa do mesmo `Referer` que /revisao/imagem
    usa (hotlink protection do Yupoo), senão a origem recusa a requisição."""
    _exigir_origem_yupoo(url, source)
    try:
        with urlopen(Request(url, headers={'Referer': source, 'User-Agent': _AGENTE}), timeout=15) as remoto:
            dados = remoto.read(TAMANHO_MAXIMO_FOTO + 1)
    except AppError:
        raise
    except Exception as exc:
        raise AppError('IMAGEM_INDISPONIVEL', 'Imagem indisponível.', 502) from exc
    if len(dados) > TAMANHO_MAXIMO_FOTO:
        raise AppError('IMAGEM_INDISPONIVEL', 'Imagem indisponível.', 502)
    try:
        return abrir_imagem(dados)
    except ValueError as exc:
        raise AppError('IMAGEM_INDISPONIVEL', 'Imagem indisponível.', 502) from exc

def _baixar_fotos(urls: list[str], source: str):
    """Baixa todas antes de tocar no produto: se uma falhar, a aprovação inteira falha sem criar nada."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(lambda url: _baixar_foto_yupoo(url, source), urls))

class Decisao(BaseModel):
    productId: str
    status: str
    translatedName: str | None = None
    # Só fazem sentido (e só são exigidos) quando status == 'approved': o
    # Yupoo não manda marca nem coleção — o admin escolhe as duas ao aprovar.
    # NUNCA vem de `supplier`/`p['category']` sozinho, ver docstring do módulo.
    marca: str | None = None
    colecao: str | None = None
    categoriasIds: list[int] | None = Field(None, min_length=1, max_length=5)
    # Feminino, masculino ou os dois (unissex). Sem isto vale `colecao`.
    publicos: list[str] | None = None
    # Entra na página Novidades (por 14 dias) ao aprovar. Padrão: sim.
    emNovidades: bool = True
    # Preço de consulta interna do dono, em centavos de real. Opcional: sem ele a aprovação segue normal.
    precoCentavos: int | None = Field(None, ge=0, le=PRECO_MAXIMO_CENTAVOS, strict=True)
    quantidadeDisponivel: int | None = Field(None, ge=0, le=2147483647, strict=True)
    statusProduto: Literal['normal', 'esgotado'] = 'normal'
    # Fotos do álbum que entram no produto, na ordem final: a primeira é a capa. Sem isto entra só a
    # foto de capa do álbum, como antes.
    fotos: list[str] | None = Field(None, min_length=1, max_length=MAXIMO_FOTOS_POR_PRODUTO)

@roteador.get('/pendentes')
def pendentes(busca:str='', categoria:str='Todos', pagina:int=Query(1,ge=1), por_pagina:int=Query(60,alias='porPagina',ge=1,le=100), sessao:Session=Depends(obter_sessao)):
    dados, _ = _catalogo()
    decididos=set(sessao.scalars(select(DecisaoRevisao.product_id)).all()); fila=[p for p in dados if p['id'] not in decididos]
    termos = normalizar(busca).split()
    filtrados = []
    for p in fila:
        if categoria != 'Todos' and p['category'] != categoria:
            continue
        # O título do fornecedor pode conter apenas códigos/tamanhos. A categoria
        # e o nome traduzido permitem encontrar a peça pelo nome em português.
        texto = normalizar(' '.join((p['name'], p['category'], traduzir(p)['translatedName'])))
        if all(termo in texto for termo in termos):
            filtrados.append(p)
    paginas=max(1,(len(filtrados)+por_pagina-1)//por_pagina)
    pagina=min(pagina,paginas); inicio=(pagina-1)*por_pagina
    return {'items':[dict(p, **traduzir(p)) for p in filtrados[inicio:inicio+por_pagina]],'total':len(filtrados),'categories':sorted({p['category'] for p in fila}),'pagina':pagina,'paginas':paginas,'porPagina':por_pagina}

@roteador.post('/atualizar')
def atualizar_fila():
    """Puxa os álbuns novos do Yupoo para a fila (botão "Atualizar produtos"). Roda em segundo plano;
    se já houver uma coleta, só devolve o andamento. Não repete álbum: o script junta pelo id."""
    return atualizacao_fila.iniciar()

@roteador.get('/atualizacao')
def andamento_da_atualizacao():
    return atualizacao_fila.estado()

@roteador.get('/fotos')
def fotos(produto_id: str = Query(alias='produtoId')):
    _, por_id = _catalogo()
    p = por_id.get(produto_id)
    if not p:
        raise AppError('PRODUTO_NAO_ENCONTRADO', 'Produto não encontrado.', 404)
    urls = _fotos_do_album(p['sourceUrl']) or [p['image']]
    # `medium.jpg` ao lado do original é a versão leve, boa para a grade de escolha.
    return {'fotos': [{'url': u, 'miniatura': u.rsplit('/', 1)[0] + '/medium.jpg'} for u in urls]}

@roteador.post('')
def decidir(corpo: Decisao, sessao: Session = Depends(obter_sessao)):
    if corpo.status not in {'approved', 'rejected'}:
        raise AppError('DECISAO_INVALIDA', 'Decisão inválida.', 400)
    _, por_id = _catalogo()
    p = por_id.get(corpo.productId)
    if not p:
        raise AppError('PRODUTO_NAO_ENCONTRADO', 'Produto não encontrado.', 404)

    t = traduzir(p)
    nome = ((corpo.translatedName or '').strip() or t['translatedName'])[:180]

    if corpo.status == 'approved':
        marca = (corpo.marca or '').strip()
        colecao = (corpo.colecao or '').strip()
        campos = {}
        if not marca:
            campos['marca'] = 'Escolha a marca do produto.'
        destinos = validar_destinos(sessao, corpo.categoriasIds) if corpo.categoriasIds is not None else None
        if corpo.publicos is not None:
            flags = validar_publicos(corpo.publicos)
            colecao = 'feminino' if flags[0] else 'masculino'
        elif colecao in {'feminino', 'masculino'}:
            flags = (colecao == 'feminino', colecao == 'masculino')
        else:
            flags = None
            campos['colecao'] = 'Escolha feminino ou masculino.'
        if campos:
            raise AppError('DADOS_INVALIDOS', 'Confira os campos destacados.', 400, campos=campos)

        urls_fotos = list(dict.fromkeys(corpo.fotos or [p['image']]))
        imagens = _baixar_fotos(urls_fotos, p['sourceUrl'])
        try:
            produto, _ = importar_produto(
                sessao,
                codigo_origem=p['id'],
                nome=nome,
                descricao=None,
                nome_marca=marca[:80],
                nome_categoria=destinos[0].nome if destinos else _singular.get(p['category'], p['category'])[:80],
                valor_colecao=colecao,
                origem_url=p['sourceUrl'],
                tamanhos=[],
                cores=[],
                imagens=imagens,
                saida_dir=Path(configuracao.IMAGENS_DIR),
                url_base=configuracao.IMAGENS_URL_BASE,
                cache_marcas={},
                cache_colecoes={},
                cache_categorias={gerar_slug(destinos[0].nome): destinos[0]} if destinos else {},
                # `p['id']` é "<fornecedor>-<id do álbum>" — pasta_imagens
                # usa só o número: a pasta pública nunca carrega o nome do
                # fornecedor, mesmo indiretamente pela URL da foto.
                pasta_imagens=p['id'].rsplit('-', 1)[-1],
            )
            produto.feminino, produto.masculino = flags
            produto.em_novidades = corpo.emNovidades
            produto.preco_centavos = corpo.precoCentavos
            if 'quantidadeDisponivel' in corpo.model_fields_set:
                produto.quantidade_disponivel = corpo.quantidadeDisponivel
            produto.status = corpo.statusProduto
            if destinos:
                definir_destinos(sessao, produto, destinos)
        except ValueError as exc:
            raise AppError('DADOS_INVALIDOS', str(exc), 400) from exc

    existente = sessao.get(DecisaoRevisao, p['id'])
    capa = urls_fotos[0] if corpo.status == 'approved' else p['image']
    valores = dict(status=corpo.status, translated_name=nome, translated_details=t['translatedDetails'], original_name=p['name'], category=p['category'], supplier=p['supplier'], image=capa, source_url=p['sourceUrl'])
    if existente:
        for k, v in valores.items(): setattr(existente, k, v)
    else:
        sessao.add(DecisaoRevisao(product_id=p['id'], **valores))
    sessao.commit()
    return {'ok': True, 'product': dict(p, **t)}

@roteador.delete('')
def desfazer(produto_id:str=Query(alias='produtoId'),sessao:Session=Depends(obter_sessao)):
    item=sessao.get(DecisaoRevisao,produto_id)
    if item: sessao.delete(item); sessao.commit()
    return {'ok':True}
@roteador.get('/publicados')
def publicados(sessao:Session=Depends(obter_sessao)):
    aprovados=sessao.scalars(select(DecisaoRevisao).where(DecisaoRevisao.status=='approved')).all()
    produtos=dict(sessao.execute(select(Produto.codigo_origem,Produto.id).where(Produto.codigo_origem.in_([x.product_id for x in aprovados]))).all())
    # As fotos são salvas dentro da própria aprovação: aprovado com produto = 'concluido'; sem produto
    # é uma aprovação antiga, de quando aprovar só gravava a decisão ('legado', volta para a revisão).
    return [{'id':x.product_id,'name':x.translated_name,'category':x.category,'detail':x.translated_details,'image':x.image,'sourceUrl':x.source_url,'available':True,'produtoId':produtos.get(x.product_id),'imagensEstado':'concluido' if x.product_id in produtos else 'legado'} for x in aprovados]
@roteador.get('/imagem')
def imagem(url:str,source:str):
    u,s=urlparse(url),urlparse(source)
    if u.scheme!='https' or u.hostname!='photo.yupoo.com' or s.scheme!='https' or not (s.hostname or '').endswith('.x.yupoo.com'): raise AppError('ORIGEM_NAO_PERMITIDA','Origem não permitida.',403)
    try:
        remoto=urlopen(Request(url,headers={'Referer':source,'User-Agent':'Mozilla/5.0 (compatible; VIPImportsCatalog/1.0)'}),timeout=15)
        return Response(remoto.read(),media_type=remoto.headers.get_content_type(),headers={'Cache-Control':'public, max-age=86400, s-maxage=1209600, immutable','X-Content-Type-Options':'nosniff'})
    except Exception as exc: raise AppError('IMAGEM_INDISPONIVEL','Imagem indisponível.',502) from exc
