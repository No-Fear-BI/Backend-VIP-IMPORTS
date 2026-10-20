"""Registro do pedido quando o cliente envia a seleção ao WhatsApp."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from vip_api.modelos.cliente import Cliente
from vip_api.modelos.pedido import Pedido, PedidoItem


def _assinatura(itens) -> list[tuple[int, str, str]]:
    """O que identifica uma seleção: quais peças, em quais tamanho e cor.

    Vale para as linhas do carrinho e para os itens de um pedido gravado, que
    têm os mesmos três campos. A ordem não conta.
    """
    return sorted((i.produto_id or 0, i.variacao_tamanho or "", i.variacao_cor or "") for i in itens)


def registrar_pedido(sessao: Session, cliente: Cliente, linhas) -> Pedido:
    """Grava a seleção como pedido `em_andamento`, com cópia em texto das peças e do cliente.

    `linhas` são as linhas do carrinho já resolvidas (servicos/selecoes.py). Se
    o cliente já tem um pedido em andamento IGUAL a esta seleção, devolve esse em
    vez de criar outro: quem abre o link do WhatsApp duas vezes não vira dois
    pedidos na tela da equipe. Seleção diferente, ou pedido anterior já
    finalizado/não finalizado, cria um pedido novo.
    """
    anterior = sessao.scalar(
        select(Pedido)
        .where(Pedido.cliente_id == cliente.id, Pedido.status == "em_andamento")
        .order_by(Pedido.criado_em.desc(), Pedido.id.desc())
        .limit(1)
    )
    if anterior is not None and _assinatura(anterior.itens) == _assinatura(linhas):
        return anterior

    pedido = Pedido(
        cliente_id=cliente.id,
        # Dados do cliente também congelados: se o cadastro sumir, a equipe
        # ainda sabe com quem estava falando.
        cliente_nome=cliente.nome,
        cliente_email=cliente.email,
        cliente_telefone=cliente.telefone,
        total_itens=len(linhas),
    )
    # TEXTO copiado agora, não JOIN na leitura: se o produto for renomeado ou
    # excluído depois, o painel continua mostrando o que o cliente viu.
    # `produto_id` fica só como referência, nulável e sem cascata.
    pedido.itens = [
        PedidoItem(
            produto_id=linha.produto_id,
            produto_codigo=linha.codigo,
            produto_nome=linha.nome,
            marca_nome=linha.marca_nome,
            categoria_nome=linha.categoria_nome,
            colecao_nome=linha.colecao_nome,
            imagem_url=linha.imagem_url,
            variacao_tamanho=linha.variacao_tamanho,
            variacao_cor=linha.variacao_cor,
            ordem=ordem,
        )
        for ordem, linha in enumerate(linhas, start=1)
    ]
    sessao.add(pedido)
    sessao.commit()
    return pedido
