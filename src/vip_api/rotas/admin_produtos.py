"""Rotas de produto do painel (tarefa 55).

Este roteador NÃO tem proteção própria: ele é incluído dentro do roteador
protegido de rotas/admin_painel.py, e herda de lá o `Depends(exigir_admin)` do
grupo. Nenhuma rota daqui vai para a lista de exceções da varredura.
"""

from fastapi import APIRouter, Depends, File, Form, Path, Query, UploadFile
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.esquemas.admin_produto import (
    LoteEntrada,
    LoteSaida,
    ProdutoAdminDetalhe,
    ProdutoAdminItem,
    ProdutoCriar,
    ProdutoEditar,
    StatusProduto,
    VariacaoAdmin,
)
from vip_api.esquemas.admin_midia import (
    ImagemUploadSaida,
    ImagensEntrada,
    OrdemEntrada,
    VariacoesEntrada,
)
from vip_api.esquemas.base import Pagina
from vip_api.esquemas.produto import ImagemDetalhe
from vip_api.servicos.admin_imagens import adicionar_imagens, reordenar_imagens
from vip_api.servicos.admin_produtos import (
    POR_PAGINA_MAXIMO,
    POR_PAGINA_PADRAO,
    FiltrosAdmin,
    alterar_em_lote,
    criar_produto,
    duplicar_produto,
    editar_produto,
    excluir_produto,
    listar_produtos,
    obter_produto,
)
from vip_api.servicos.admin_upload import upload_imagem_produto
from vip_api.servicos.admin_variacoes import definir_variacoes
from vip_api.servicos.imagens_processamento import TAMANHO_MAXIMO_ARQUIVO

roteador = APIRouter(prefix="/produtos", tags=["admin"])


@roteador.get("", response_model=Pagina[ProdutoAdminItem])
def listar(
    sessao: Session = Depends(obter_sessao),
    busca: str | None = Query(None, description="Nome ou código, parcial."),
    marca_id: int | None = Query(None, alias="marcaId"),
    categoria_id: int | None = Query(None, alias="categoriaId"),
    colecao_id: int | None = Query(None, alias="colecaoId"),
    cor_id: int | None = Query(
        None, alias="corId", description="Produtos que têm esta cor na grade de variações."
    ),
    status: StatusProduto | None = Query(
        None, description="Ausente traz TUDO, inclusive os ocultos."
    ),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(
        POR_PAGINA_PADRAO, alias="porPagina", description=f"Máximo {POR_PAGINA_MAXIMO}."
    ),
) -> Pagina[ProdutoAdminItem]:
    return listar_produtos(
        sessao,
        FiltrosAdmin(
            busca=busca,
            marca_id=marca_id,
            categoria_id=categoria_id,
            colecao_id=colecao_id,
            cor_id=cor_id,
            status=status,
            pagina=pagina,
            por_pagina=por_pagina,
        ),
    )


@roteador.post("", response_model=ProdutoAdminDetalhe, status_code=201)
def criar(
    corpo: ProdutoCriar, sessao: Session = Depends(obter_sessao)
) -> ProdutoAdminDetalhe:
    return criar_produto(sessao, corpo)


# ANTES de /{produtoId}: "lote" casaria com o parâmetro de caminho e a
# requisição morreria num 422 de "isto não é um inteiro" em vez de chegar aqui.
@roteador.patch("/lote", response_model=LoteSaida)
def alterar_lote(corpo: LoteEntrada, sessao: Session = Depends(obter_sessao)) -> LoteSaida:
    alterados = alterar_em_lote(
        sessao,
        ids=corpo.ids,
        status=corpo.status,
        destaque=corpo.destaque,
        marca_id=corpo.marca_id,
        categoria_id=corpo.categoria_id,
    )
    return LoteSaida(alterados=alterados)


@roteador.get("/{produtoId}", response_model=ProdutoAdminDetalhe)
def detalhe(
    produto_id: int = Path(alias="produtoId"), sessao: Session = Depends(obter_sessao)
) -> ProdutoAdminDetalhe:
    return obter_produto(sessao, produto_id)


@roteador.patch("/{produtoId}", response_model=ProdutoAdminDetalhe)
def editar(
    corpo: ProdutoEditar,
    produto_id: int = Path(alias="produtoId"),
    sessao: Session = Depends(obter_sessao),
) -> ProdutoAdminDetalhe:
    return editar_produto(sessao, produto_id, corpo)


@roteador.delete("/{produtoId}")
def excluir(
    produto_id: int = Path(alias="produtoId"), sessao: Session = Depends(obter_sessao)
) -> dict[str, bool]:
    excluir_produto(sessao, produto_id)
    return {"ok": True}


@roteador.post("/{produtoId}/duplicar", response_model=ProdutoAdminDetalhe, status_code=201)
def duplicar(
    produto_id: int = Path(alias="produtoId"), sessao: Session = Depends(obter_sessao)
) -> ProdutoAdminDetalhe:
    return duplicar_produto(sessao, produto_id)


@roteador.post("/{produtoId}/imagens", response_model=list[ImagemDetalhe], status_code=201)
def imagens_acrescentar(
    corpo: ImagensEntrada,
    produto_id: int = Path(alias="produtoId"),
    sessao: Session = Depends(obter_sessao),
) -> list[ImagemDetalhe]:
    """Devolve a galeria inteira, já renumerada — a tela não precisa recarregar
    o produto para saber a ordem e a capa que ficaram."""
    return adicionar_imagens(sessao, produto_id, corpo.imagens)


@roteador.post("/{produtoId}/imagens/upload", response_model=ImagemUploadSaida, status_code=201)
def imagens_upload(
    arquivo: UploadFile = File(...),
    alt: str | None = Form(None, max_length=200),
    produto_id: int = Path(alias="produtoId"),
    sessao: Session = Depends(obter_sessao),
) -> ImagemUploadSaida:
    """Processa o arquivo e grava em disco — NÃO acrescenta à galeria
    sozinho. Devolve `{url, alt}` para a tela chamar `POST /imagens` (o de
    sempre, por URL) com o resultado, exatamente como faria com uma URL
    digitada à mão."""
    dados = arquivo.file.read(TAMANHO_MAXIMO_ARQUIVO + 1)
    url, alt_final = upload_imagem_produto(sessao, produto_id, dados, alt)
    return ImagemUploadSaida(url=url, alt=alt_final)


@roteador.patch("/{produtoId}/imagens/ordem", response_model=list[ImagemDetalhe])
def imagens_reordenar(
    corpo: OrdemEntrada,
    produto_id: int = Path(alias="produtoId"),
    sessao: Session = Depends(obter_sessao),
) -> list[ImagemDetalhe]:
    return reordenar_imagens(sessao, produto_id, corpo.ids)


@roteador.patch("/{produtoId}/variacoes", response_model=list[VariacaoAdmin])
def variacoes_definir(
    corpo: VariacoesEntrada,
    produto_id: int = Path(alias="produtoId"),
    sessao: Session = Depends(obter_sessao),
) -> list[VariacaoAdmin]:
    """SUBSTITUI o conjunto: o que não vier na lista sai."""
    return definir_variacoes(sessao, produto_id, corpo.variacoes)
