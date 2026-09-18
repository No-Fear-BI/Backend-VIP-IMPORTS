"""Fila interna de aprovação dos produtos importados dos fornecedores."""
import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from vip_api.banco import obter_sessao
from vip_api.erros.excecoes import AppError
from vip_api.modelos.revisao import DecisaoRevisao

roteador = APIRouter(prefix='/revisao', tags=['admin'])
_dados = json.loads((Path(__file__).resolve().parents[3] / 'data' / 'pending-products.json').read_text(encoding='utf-8'))
_por_id = {p['id']: p for p in _dados}
_singular = {'Jaquetas':'Jaqueta','Jaquetas de inverno':'Jaqueta de inverno','Moletons':'Moletom','Coletes':'Colete','Suéteres':'Suéter','Conjuntos':'Conjunto','Ternos':'Terno','Jeans':'Calça jeans','Bermudas':'Bermuda','Camisetas':'Camiseta','Camisas':'Camisa','Casacos':'Casaco','Bolsas':'Bolsa'}
def traduzir(p):
    n=p['name']; d=[]
    for termos, rotulo in ((('hoodie','hooded'),'com capuz'),(('leather',),'de couro'),(('down jacket',),'acolchoada'),(('denim','jeans'),'jeans'),(('knit','sweater'),'de malha')):
        if any(t in n.lower() for t in termos): d.append(rotulo)
    cor=next((x for termos,x in ((('black',),'preta'),(('white',),'branca'),(('blue',),'azul'),(('green',),'verde'),(('red',),'vermelha'),(('brown',),'marrom')) if any(t in n.lower() for t in termos)),None)
    detalhes=([f'Cor: {cor}'] if cor else [])+[f"Referência: {p['id'].split('-',1)[1]}"]
    return {'translatedName':' '.join([_singular.get(p['category'],p['category']),*list(dict.fromkeys(d))[:2]]),'translatedDetails':' • '.join(detalhes)}
class Decisao(BaseModel): productId:str; status:str; translatedName:str|None=None
@roteador.get('/pendentes')
def pendentes(busca:str='', categoria:str='Todos', sessao:Session=Depends(obter_sessao)):
    decididos=set(sessao.scalars(select(DecisaoRevisao.product_id)).all()); fila=[p for p in _dados if p['id'] not in decididos]
    filtrados=[p for p in fila if (categoria=='Todos' or p['category']==categoria) and busca.casefold() in p['name'].casefold()]
    return {'items':[dict(p, **traduzir(p)) for p in filtrados[:60]],'total':len(filtrados),'categories':sorted({p['category'] for p in fila})}
@roteador.post('')
def decidir(corpo:Decisao, sessao:Session=Depends(obter_sessao)):
    if corpo.status not in {'approved','rejected'}: raise AppError('DECISAO_INVALIDA','Decisão inválida.',400)
    p=_por_id.get(corpo.productId)
    if not p: raise AppError('PRODUTO_NAO_ENCONTRADO','Produto não encontrado.',404)
    t=traduzir(p); existente=sessao.get(DecisaoRevisao,p['id']); valores=dict(status=corpo.status,translated_name=(corpo.translatedName or '').strip() or t['translatedName'],translated_details=t['translatedDetails'],original_name=p['name'],category=p['category'],supplier=p['supplier'],image=p['image'],source_url=p['sourceUrl'])
    if existente:
        for k,v in valores.items(): setattr(existente,k,v)
    else: sessao.add(DecisaoRevisao(product_id=p['id'],**valores))
    sessao.commit(); return {'ok':True,'product':dict(p,**t)}
@roteador.delete('')
def desfazer(produto_id:str=Query(alias='produtoId'),sessao:Session=Depends(obter_sessao)):
    item=sessao.get(DecisaoRevisao,produto_id)
    if item: sessao.delete(item); sessao.commit()
    return {'ok':True}
@roteador.get('/publicados')
def publicados(sessao:Session=Depends(obter_sessao)):
    return [{'id':x.product_id,'name':x.translated_name,'category':x.category,'detail':x.translated_details,'image':x.image,'sourceUrl':x.source_url,'available':True} for x in sessao.scalars(select(DecisaoRevisao).where(DecisaoRevisao.status=='approved')).all()]
@roteador.get('/imagem')
def imagem(url:str,source:str):
    u,s=urlparse(url),urlparse(source)
    if u.scheme!='https' or u.hostname!='photo.yupoo.com' or s.scheme!='https' or not (s.hostname or '').endswith('.x.yupoo.com'): raise AppError('ORIGEM_NAO_PERMITIDA','Origem não permitida.',403)
    try:
        remoto=urlopen(Request(url,headers={'Referer':source,'User-Agent':'Mozilla/5.0 (compatible; VIPImportsCatalog/1.0)'}),timeout=15)
        return Response(remoto.read(),media_type=remoto.headers.get_content_type(),headers={'Cache-Control':'public, max-age=86400, s-maxage=1209600, immutable','X-Content-Type-Options':'nosniff'})
    except Exception as exc: raise AppError('IMAGEM_INDISPONIVEL','Imagem indisponível.',502) from exc
