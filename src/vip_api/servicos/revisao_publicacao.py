"""Publica a decisao e o produto na mesma transacao, sem duplicar reenvios."""
from hashlib import sha256
from urllib.parse import quote

from sqlalchemy import delete, select, text
from vip_api.erros.excecoes import AppError
from vip_api.modelos.catalogo import Categoria, Colecao, Marca, Produto, ProdutoImagem
from vip_api.modelos.produto_destinos import ProdutoCategoriaAdicional


def travar_revisao(sessao, origem_id):
    # A linha da decisao ainda nao existe na primeira aprovacao. O lock por origem
    # tambem serializa duas aprovacoes simultaneas antes do INSERT.
    chave = int.from_bytes(sha256(origem_id.encode()).digest()[:8], 'big', signed=True)
    sessao.execute(text('SELECT pg_advisory_xact_lock(:chave)'), {'chave': chave})


def publicar(sessao, origem, traducao, corpo, decisao):
    ids = corpo.categoriasIds if corpo.categoriasIds is not None else ([corpo.categoriaId] if corpo.categoriaId else [])
    categorias = [sessao.get(Categoria, id_categoria) for id_categoria in ids]
    marca = sessao.get(Marca, corpo.marcaId) if corpo.marcaId else None
    campos = {}
    colecoes = []
    for categoria in categorias:
        colecao = sessao.get(Colecao, categoria.colecao_id) if categoria else None
        if not categoria or not categoria.ativa or not colecao or not colecao.ativa:
            campos['categoriasIds'] = 'Escolha uma categoria ativa para cada coleção marcada.'
        elif colecao.id in colecoes:
            campos['categoriasIds'] = 'Escolha somente uma categoria por coleção.'
        else:
            colecoes.append(colecao.id)
    if not categorias or (corpo.categoriasIds is not None and corpo.categoriaId is not None):
        campos['categoriasIds'] = 'Informe as categorias das coleções escolhidas.'
    if not marca or not marca.ativa:
        campos['marcaId'] = 'Escolha uma marca ativa.'
    if campos:
        raise AppError('DADOS_INVALIDOS', 'Escolha uma categoria para cada coleção e uma marca ativa.', 400, campos)
    categoria = categorias[0]

    # Codigo estavel permite reaproveitar o produto ocultado ao desfazer a decisao.
    codigo = 'REV-' + sha256(origem['id'].encode()).hexdigest()[:24].upper()
    produto = sessao.get(Produto, decisao.produto_id) if decisao and decisao.produto_id else None
    if produto is None:
        produto = sessao.scalars(select(Produto).where(Produto.codigo_origem == origem['id'], Produto.origem_url == origem['sourceUrl'])).first()
    if produto is None:
        produto = sessao.scalar(select(Produto).where(Produto.codigo == codigo))
    nome = (corpo.translatedName or '').strip() or traducao['translatedName']
    if len(nome) > 180:
        raise AppError('DADOS_INVALIDOS', 'O nome deve ter até 180 caracteres.', 400, {'translatedName': 'Use até 180 caracteres.'})
    if produto is None:
        produto = Produto(codigo=codigo)
        sessao.add(produto)
    produto.nome = nome
    produto.descricao = traducao['translatedDetails']
    produto.codigo_origem = origem['id']
    produto.origem_url = origem['sourceUrl']
    produto.marca_id = marca.id
    produto.categoria_id = categoria.id
    produto.colecao_id = categoria.colecao_id
    produto.status = 'normal'
    sessao.flush()
    sessao.execute(delete(ProdutoCategoriaAdicional).where(ProdutoCategoriaAdicional.produto_id == produto.id))
    for adicional in categorias[1:]:
        sessao.add(ProdutoCategoriaAdicional(produto_id=produto.id, categoria_id=adicional.id))
    if not produto.imagens:
        url = '/api/v1/produtos-aprovados/imagem?url=' + quote(origem['image'], safe='') + '&source=' + quote(origem['sourceUrl'], safe='')
        sessao.add(ProdutoImagem(produto_id=produto.id, url=url, alt=nome, ordem=1, capa=True))
    return produto


def ocultar(sessao, decisao):
    if decisao and decisao.produto_id:
        produto = sessao.get(Produto, decisao.produto_id)
        if produto:
            produto.status = 'oculto'
