"""Variações do produto no painel (tarefa 56) — e a única porta para apagá-las.

A ARMADILHA, que já custou um 500 em produção de desenvolvimento:

`carrinho_itens` referencia `produto_variacoes` com `ON DELETE SET NULL` em
cada uma das duas colunas de variação, e a unicidade do item é
(carrinho, produto, tamanho, cor) com NULLS NOT DISTINCT. Apagar uma variação
zera a coluna correspondente nos itens que apontavam para ela — e o item que
vira (nulo, nulo) colide com outro item do mesmo produto no mesmo carrinho que
já estivesse sem variação. O banco recusa, e quem só queria apagar um tamanho
recebe 500.

`remover_variacoes` resolve a colisão ANTES de apagar, com a mesma regra que a
troca de variação do carrinho já aplica: mesmo produto e mesmo par é um item
só, e quem some é o item que estava sendo mexido, não o que já estava lá.

Toda exclusão de variação passa por aqui, nas três portas que existem hoje:
excluir o produto (servicos/admin_produtos.py), tirar UMA variação da lista no
`PATCH /variacoes`, e trocar o conjunto inteiro nessa mesma rota — a pior das
três, porque apaga várias de uma vez e pode colidir com itens de carrinhos de
clientes diferentes na mesma transação. Não existe `delete(ProdutoVariacao)`
solto em lugar nenhum do projeto, e é de propósito: o próximo caller que
escrevesse o seu reintroduziria o 500.
"""

from sqlalchemy import delete, or_, select, tuple_, update
from sqlalchemy.orm import Session

from vip_api.erros.codigos import DADOS_INVALIDOS, PRODUTO_NAO_ENCONTRADO
from vip_api.erros.excecoes import AppError
from vip_api.esquemas.admin_midia import VariacaoEntrada
from vip_api.esquemas.produto import VariacaoDetalhe
from vip_api.modelos.catalogo import Produto, ProdutoVariacao
from vip_api.modelos.cliente import CarrinhoItem

LIMITE_VARIACOES = 40


def remover_variacoes(sessao: Session, ids: list[int]) -> int:
    """Apaga as variações depois de acertar os carrinhos que apontavam para
    elas. Devolve quantas foram apagadas. NÃO faz commit: quem chama decide o
    limite da transação."""
    ids = list(dict.fromkeys(ids))
    if not ids:
        return 0

    afetados = sessao.scalars(
        select(CarrinhoItem)
        .where(
            or_(
                CarrinhoItem.variacao_tamanho_id.in_(ids),
                CarrinhoItem.variacao_cor_id.in_(ids),
            )
        )
        # Ordem de id só para o desempate entre DOIS itens afetados que caem
        # no mesmo par: fica o de id menor. Contra um item que já ocupava o
        # par, quem some é sempre o afetado — é a regra que `trocar_variacao`
        # aplica quando o cliente troca a variação e cai num item existente.
        .order_by(CarrinhoItem.id.asc())
    ).all()

    if afetados:
        chaves = {(item.carrinho_id, item.produto_id) for item in afetados}
        atingidos = {item.id for item in afetados}
        # Os pares já ocupados por itens que NÃO vão mudar: são eles que
        # decidem se o item afetado pode virar (nulo, nulo) ou tem que sumir.
        ocupados = {
            (outro.carrinho_id, outro.produto_id, outro.variacao_tamanho_id, outro.variacao_cor_id)
            for outro in sessao.scalars(
                select(CarrinhoItem).where(
                    tuple_(CarrinhoItem.carrinho_id, CarrinhoItem.produto_id).in_(chaves),
                    CarrinhoItem.id.not_in(atingidos),
                )
            )
        }

        for item in afetados:
            tamanho = None if item.variacao_tamanho_id in ids else item.variacao_tamanho_id
            cor = None if item.variacao_cor_id in ids else item.variacao_cor_id
            novo = (item.carrinho_id, item.produto_id, tamanho, cor)

            if novo in ocupados:
                # Fundir: o cliente já tem esse mesmo par no carrinho.
                sessao.execute(delete(CarrinhoItem).where(CarrinhoItem.id == item.id))
            else:
                # Fazer o SET NULL na mão, ANTES do DELETE da variação: o do
                # banco aconteceria depois, sem ninguém para resolver a
                # colisão.
                sessao.execute(
                    update(CarrinhoItem)
                    .where(CarrinhoItem.id == item.id)
                    .values(variacao_tamanho_id=tamanho, variacao_cor_id=cor)
                )
                ocupados.add(novo)

    resultado = sessao.execute(delete(ProdutoVariacao).where(ProdutoVariacao.id.in_(ids)))
    return resultado.rowcount or 0


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


def listar_variacoes(sessao: Session, produto_id: int) -> list[VariacaoDetalhe]:
    linhas = sessao.scalars(
        select(ProdutoVariacao)
        .where(ProdutoVariacao.produto_id == produto_id)
        .order_by(ProdutoVariacao.tipo.asc(), ProdutoVariacao.ordem.asc(), ProdutoVariacao.id.asc())
    ).all()
    return [
        VariacaoDetalhe(id=v.id, tipo=v.tipo, valor=v.valor, disponivel=v.disponivel)
        for v in linhas
    ]


def definir_variacoes(
    sessao: Session, produto_id: int, desejadas: list[VariacaoEntrada]
) -> list[VariacaoDetalhe]:
    """SUBSTITUI o conjunto inteiro — "definir", como diz a seção 06 do
    contrato, não "acrescentar".

    O que permanece MANTÉM O ID. Uma variação com o mesmo tipo e o mesmo valor
    não é recriada, é reaproveitada: recriar tudo a cada salvamento trocaria os
    ids, o `ON DELETE SET NULL` zeraria a escolha de quem já tinha aquele
    tamanho no carrinho, e o cliente descobriria o esvaziamento na hora de
    enviar a seleção.
    """
    _produto_ou_404(sessao, produto_id)

    if len(desejadas) > LIMITE_VARIACOES:
        raise _campo_invalido(
            "variacoes", f"No máximo {LIMITE_VARIACOES} variações por produto."
        )

    vistas: set[tuple[str, str]] = set()
    for pedida in desejadas:
        chave = (pedida.tipo, pedida.valor.strip())
        if chave in vistas:
            raise _campo_invalido(
                "variacoes", f"'{pedida.valor.strip()}' aparece duas vezes em {pedida.tipo}."
            )
        vistas.add(chave)

    atuais = {
        (variacao.tipo, variacao.valor): variacao
        for variacao in sessao.scalars(
            select(ProdutoVariacao).where(ProdutoVariacao.produto_id == produto_id)
        )
    }

    mantidos: set[int] = set()
    novas: list[ProdutoVariacao] = []
    for ordem, pedida in enumerate(desejadas):
        valor = pedida.valor.strip()
        existente = atuais.get((pedida.tipo, valor))
        if existente is not None:
            existente.disponivel = pedida.disponivel
            existente.ordem = ordem
            mantidos.add(existente.id)
        else:
            novas.append(
                ProdutoVariacao(
                    produto_id=produto_id,
                    tipo=pedida.tipo,
                    valor=valor,
                    disponivel=pedida.disponivel,
                    ordem=ordem,
                )
            )

    # Apagar ANTES de inserir: uma variação nova pode ocupar o mesmo (tipo,
    # valor) de uma que está saindo — sem esta ordem, o UNIQUE recusaria.
    remover_variacoes(sessao, [v.id for v in atuais.values() if v.id not in mantidos])
    for nova in novas:
        sessao.add(nova)

    sessao.commit()
    return listar_variacoes(sessao, produto_id)
