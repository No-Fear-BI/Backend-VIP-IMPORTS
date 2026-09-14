"""Imagens do produto no painel (tarefa 56).

Por URL, não por upload: é o que a seção 4.2 do contrato define para esta
fase. A rota continua a mesma quando passarmos a hospedar arquivo — o que muda
é de onde a URL vem.

INVARIANTE que todas as operações preservam: a ordem é 1..N, contígua, e a
imagem de ordem 1 é a capa. A capa é o que aparece na grade do site, então
apagar a primeira imagem muda o que o visitante vê — e é melhor que isso
aconteça de forma previsível do que o produto ficar sem capa nenhuma.
"""

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from vip_api.erros.codigos import DADOS_INVALIDOS, PRODUTO_NAO_ENCONTRADO
from vip_api.erros.excecoes import AppError
from vip_api.esquemas.admin_midia import LIMITE_IMAGENS, ImagemEntrada
from vip_api.esquemas.produto import ImagemDetalhe
from vip_api.modelos.catalogo import Produto, ProdutoImagem


def _produto_ou_404(sessao: Session, produto_id: int) -> Produto:
    produto = sessao.get(Produto, produto_id)
    if produto is None:
        raise AppError(
            codigo=PRODUTO_NAO_ENCONTRADO, mensagem="Produto não encontrado.", status_code=404
        )
    return produto


def _campo_invalido(campo: str, mensagem: str) -> AppError:
    return AppError(
        codigo=DADOS_INVALIDOS,
        mensagem="Há campos inválidos no envio.",
        status_code=400,
        campos={campo: mensagem},
    )


def _imagens_do_produto(sessao: Session, produto_id: int) -> list[ProdutoImagem]:
    return list(
        sessao.scalars(
            select(ProdutoImagem)
            .where(ProdutoImagem.produto_id == produto_id)
            .order_by(ProdutoImagem.ordem.asc(), ProdutoImagem.id.asc())
        )
    )


def _renumerar(sessao: Session, produto_id: int, ids_na_ordem: list[int]) -> None:
    """Grava ordem 1..N e põe a capa na primeira.

    A capa sai de TODAS antes de entrar na nova: o índice único parcial
    `uq_produto_imagens_capa` não é adiável, então duas capas no mesmo produto,
    nem por um instante, o banco recusa. Já a unicidade de (produto, ordem) é
    DEFERRABLE, e é o que permite reescrever a numeração inteira aqui dentro
    sem inventar ordens temporárias negativas.
    """
    sessao.execute(
        update(ProdutoImagem)
        .where(ProdutoImagem.produto_id == produto_id, ProdutoImagem.capa.is_(True))
        .values(capa=False)
    )
    for posicao, imagem_id in enumerate(ids_na_ordem, start=1):
        sessao.execute(
            update(ProdutoImagem)
            .where(ProdutoImagem.id == imagem_id)
            .values(ordem=posicao, capa=posicao == 1)
        )


def _saida(imagens: list[ProdutoImagem]) -> list[ImagemDetalhe]:
    return [
        ImagemDetalhe(id=i.id, url=i.url, alt=i.alt, ordem=i.ordem) for i in imagens
    ]


def listar_imagens(sessao: Session, produto_id: int) -> list[ImagemDetalhe]:
    return _saida(_imagens_do_produto(sessao, produto_id))


def adicionar_imagens(
    sessao: Session, produto_id: int, novas: list[ImagemEntrada]
) -> list[ImagemDetalhe]:
    """As novas entram NO FIM da ordem existente — quem já tinha capa continua
    com ela, e acrescentar foto não troca o que o site mostra na grade."""
    _produto_ou_404(sessao, produto_id)
    atuais = _imagens_do_produto(sessao, produto_id)

    if len(atuais) + len(novas) > LIMITE_IMAGENS:
        raise _campo_invalido(
            "imagens",
            f"Este produto ficaria com {len(atuais) + len(novas)} imagens; "
            f"o máximo é {LIMITE_IMAGENS}.",
        )

    criadas = []
    for posicao, entrada in enumerate(novas, start=len(atuais) + 1):
        imagem = ProdutoImagem(
            produto_id=produto_id,
            url=entrada.url,
            alt=entrada.alt,
            ordem=posicao,
            capa=False,
        )
        sessao.add(imagem)
        criadas.append(imagem)
    sessao.flush()

    # Produto que estava sem imagem nenhuma ganha capa agora.
    _renumerar(sessao, produto_id, [i.id for i in atuais] + [i.id for i in criadas])
    sessao.commit()
    return listar_imagens(sessao, produto_id)


def reordenar_imagens(
    sessao: Session, produto_id: int, ids_na_ordem: list[int]
) -> list[ImagemDetalhe]:
    """A lista tem que conter EXATAMENTE as imagens do produto.

    Lista parcial reordenaria metade e deixaria a outra metade com a numeração
    antiga — ordem duplicada, capa ambígua, e o erro só apareceria na vitrine.
    """
    _produto_ou_404(sessao, produto_id)
    atuais = {imagem.id for imagem in _imagens_do_produto(sessao, produto_id)}
    pedidos = list(dict.fromkeys(ids_na_ordem))

    if len(pedidos) != len(ids_na_ordem):
        raise _campo_invalido("ids", "Há id repetido na lista.")
    if set(pedidos) != atuais:
        faltando = sorted(atuais - set(pedidos))
        sobrando = sorted(set(pedidos) - atuais)
        raise _campo_invalido(
            "ids",
            "A lista precisa trazer todas as imagens deste produto, e só elas. "
            f"Faltando: {faltando or '—'}. Fora do produto: {sobrando or '—'}.",
        )

    _renumerar(sessao, produto_id, pedidos)
    sessao.commit()
    return listar_imagens(sessao, produto_id)


def remover_imagem(sessao: Session, imagem_id: int) -> list[ImagemDetalhe]:
    """Apaga e renumera o que sobrou. Se a apagada era a capa, a próxima vira
    capa — o site nunca fica com produto sem capa tendo imagem."""
    imagem = sessao.get(ProdutoImagem, imagem_id)
    if imagem is None:
        raise AppError(
            codigo=PRODUTO_NAO_ENCONTRADO, mensagem="Imagem não encontrada.", status_code=404
        )

    produto_id = imagem.produto_id
    sessao.execute(delete(ProdutoImagem).where(ProdutoImagem.id == imagem_id))
    sessao.flush()

    restantes = _imagens_do_produto(sessao, produto_id)
    _renumerar(sessao, produto_id, [i.id for i in restantes])
    sessao.commit()
    return listar_imagens(sessao, produto_id)
