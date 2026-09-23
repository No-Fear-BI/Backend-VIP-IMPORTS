"""Leitura pública exclusiva da fila de fornecedores já aprovada."""
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload, selectinload
from vip_api.banco import obter_sessao
from vip_api.modelos.revisao import DecisaoRevisao
from vip_api.modelos.catalogo import Produto

roteador = APIRouter(prefix='/produtos-aprovados', tags=['produtos'])
@roteador.get('')
def listar(sessao: Session = Depends(obter_sessao)):
    vinculados = sessao.scalars(
        select(Produto).join(DecisaoRevisao, DecisaoRevisao.produto_id == Produto.id)
        .where(DecisaoRevisao.status == 'approved', Produto.status != 'oculto')
        .options(joinedload(Produto.marca), joinedload(Produto.categoria), joinedload(Produto.colecao), selectinload(Produto.imagens))
        .order_by(Produto.criado_em.desc(), Produto.id.desc())
    ).all()
    itens = []
    for produto in vinculados:
        capa = next((foto for foto in produto.imagens if foto.capa), None)
        itens.append({
            'id': produto.id, 'codigo': produto.codigo, 'nome': produto.nome,
            'status': produto.status, 'destaque': produto.destaque,
            'marca': {'nome': produto.marca.nome, 'slug': produto.marca.slug},
            'categoria': {'nome': produto.categoria.nome, 'slug': produto.categoria.slug},
            'colecao': {'nome': produto.colecao.nome, 'slug': produto.colecao.slug},
            'capa': {'url': capa.url, 'alt': capa.alt} if capa else None,
        })
    # Preserva a vitrine dos itens aprovados antes da classificacao existir.
    return itens + [{'id': x.product_id, 'codigo': x.product_id, 'nome': x.translated_name,
             'status': 'normal', 'marca': {'nome': x.supplier},
             'categoria': {'nome': x.category}, 'capa': {'url': f'/api/v1/produtos-aprovados/imagem?url={quote(x.image, safe="")}&source={quote(x.source_url, safe="")}', 'alt': x.translated_name},
             'origemUrl': x.source_url, 'detalhe': x.translated_details}
            for x in sessao.scalars(select(DecisaoRevisao).where(DecisaoRevisao.status == 'approved', DecisaoRevisao.produto_id.is_(None), DecisaoRevisao.publicado_no_catalogo.is_(False))).all()]

@roteador.get('/imagem')
def imagem(url: str, source: str):
    imagem_url, origem = urlparse(url), urlparse(source)
    if imagem_url.scheme != 'https' or imagem_url.hostname != 'photo.yupoo.com' or origem.scheme != 'https' or not (origem.hostname or '').endswith('.x.yupoo.com'):
        return Response('Origem não permitida', status_code=403)
    try:
        remoto = urlopen(Request(url, headers={'Referer': source, 'User-Agent': 'Mozilla/5.0 (compatible; VIPImportsCatalog/1.0)'}), timeout=15)
        return Response(remoto.read(), media_type=remoto.headers.get_content_type(), headers={'Cache-Control': 'public, max-age=86400', 'X-Content-Type-Options': 'nosniff'})
    except Exception:
        return Response('Imagem indisponível', status_code=502)
