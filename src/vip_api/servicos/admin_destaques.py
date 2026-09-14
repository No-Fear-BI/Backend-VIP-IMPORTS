"""Destaques da home no painel (tarefa 58).

As duas rotas SUBSTITUEM o conjunto — "definir", como o resto do painel: quem
está na lista vira destaque com a ordem da posição, quem não está deixa de ser.
Mandar a lista inteira é o que permite reordenar e remover na mesma chamada,
sem a tela ter que calcular diferenças.

TETO. `LIMITE_DESTAQUES` de produtos é o MESMO número que a home renderiza
(servicos/home.py): marcar 30 produtos como destaque quando a home mostra 12
faria o cliente marcar, não ver na home e procurar o erro na tela errada — o
mesmo problema do produto oculto marcado como destaque, que esta rota recusa
explicitamente. Nas categorias o teto é menor: a faixa de categorias da home é
uma fileira de cartões, e passar de 8 vira rolagem horizontal e peso numa
página que tem orçamento de quatro consultas.
"""

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from vip_api.erros.codigos import DADOS_INVALIDOS
from vip_api.erros.excecoes import AppError
from vip_api.modelos.catalogo import Categoria, Produto
from vip_api.servicos.home import LIMITE_DESTAQUES

LIMITE_CATEGORIAS_DESTAQUE = 8


def _campo_invalido(mensagem: str, detalhes: dict | None = None) -> AppError:
    return AppError(
        codigo=DADOS_INVALIDOS,
        mensagem=mensagem,
        status_code=400,
        campos={"ids": mensagem},
        detalhes=detalhes,
    )


def _conferir_lista(ids: list[int], teto: int, rotulo: str) -> list[int]:
    unicos = list(dict.fromkeys(ids))
    if len(unicos) != len(ids):
        raise _campo_invalido("Há id repetido na lista.")
    if len(unicos) > teto:
        raise _campo_invalido(
            f"A home mostra no máximo {teto} {rotulo} em destaque; "
            f"a lista tem {len(unicos)}."
        )
    return unicos


def _aplicar(sessao: Session, modelo, ids: list[int]) -> None:
    """Zera todo mundo e numera 1..N quem ficou. Duas instruções, sem laço por
    linha na primeira: é a mesma ideia do `_renumerar` das imagens."""
    agora = datetime.now(timezone.utc)
    sessao.execute(
        update(modelo)
        .where(modelo.destaque.is_(True))
        .values(destaque=False, destaque_ordem=None, atualizado_em=agora)
    )
    for posicao, identificador in enumerate(ids, start=1):
        sessao.execute(
            update(modelo)
            .where(modelo.id == identificador)
            .values(destaque=True, destaque_ordem=posicao, atualizado_em=agora)
        )
    sessao.commit()


def definir_produtos_destaque(sessao: Session, ids: list[int]) -> list[int]:
    """Devolve os ids na ordem gravada."""
    pedidos = _conferir_lista(ids, LIMITE_DESTAQUES, "produtos")

    if pedidos:
        encontrados = {
            linha.id: linha.status
            for linha in sessao.execute(
                select(Produto.id, Produto.status).where(Produto.id.in_(pedidos))
            )
        }
        faltando = [i for i in pedidos if i not in encontrados]
        if faltando:
            raise _campo_invalido(
                f"Estes produtos não existem: {faltando}.",
                detalhes={"naoEncontrados": faltando},
            )

        # Produto oculto some da home inteira. Aceitar a marcação aqui seria
        # deixar o cliente marcar e não ver nada, sem mensagem nenhuma.
        ocultos = [i for i in pedidos if encontrados[i] == "oculto"]
        if ocultos:
            raise _campo_invalido(
                f"Produto oculto não aparece na home e não pode ser destaque: {ocultos}.",
                detalhes={"ocultos": ocultos},
            )

    _aplicar(sessao, Produto, pedidos)
    return pedidos


def definir_categorias_destaque(sessao: Session, ids: list[int]) -> list[int]:
    pedidos = _conferir_lista(ids, LIMITE_CATEGORIAS_DESTAQUE, "categorias")

    if pedidos:
        encontradas = {
            linha.id: linha.ativa
            for linha in sessao.execute(
                select(Categoria.id, Categoria.ativa).where(Categoria.id.in_(pedidos))
            )
        }
        faltando = [i for i in pedidos if i not in encontradas]
        if faltando:
            raise _campo_invalido(
                f"Estas categorias não existem: {faltando}.",
                detalhes={"naoEncontrados": faltando},
            )

        # Mesma regra do produto oculto: categoria inativa não aparece na home.
        inativas = [i for i in pedidos if not encontradas[i]]
        if inativas:
            raise _campo_invalido(
                f"Categoria inativa não aparece na home e não pode ser destaque: {inativas}.",
                detalhes={"inativas": inativas},
            )

    _aplicar(sessao, Categoria, pedidos)
    return pedidos
