"""Controle de entrada da loja — seção 05 do contrato, modo 3 (aprovação).

Duas fontes, cada uma com um papel (docs/modelagem-banco.md, 4.17 e 4.18):

- `clientes.acesso_status` é o que o portão lê a cada requisição. Uma coluna
  na linha que a sessão já traz, sem JOIN com a fila.
- `acesso_solicitacoes` é o histórico auditável: quem pediu, com que dados,
  quem decidiu e quando. Toda decisão grava as duas coisas na mesma transação.

`acesso_config` é linha única (id = 1), semeada em 'aberto' pela revisão 0013.
Linha ausente é tratada como 'aberto': falhar fechado aqui trancaria a loja
inteira por causa de um banco mal semeado, e trancar a loja é decisão do
painel, nunca de um acidente.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vip_api.erros.codigos import ACESSO_RECUSADO, CLIENTE_NAO_ENCONTRADO, DADOS_INVALIDOS
from vip_api.erros.excecoes import AppError
from vip_api.esquemas.acesso import (
    ConfiguracaoAcesso,
    ConfiguracaoAcessoEntrada,
    DecisaoAcesso,
    EstadoAcesso,
    SolicitacaoFila,
)
from vip_api.esquemas.base import Pagina, Paginacao
from vip_api.modelos.acesso import AcessoConfig, AcessoSolicitacao
from vip_api.modelos.cliente import Cliente

MODO_ABERTO = "aberto"
MODO_APROVACAO = "aprovacao"
ID_CONFIG = 1

POR_PAGINA_PADRAO = 20
POR_PAGINA_MAXIMO = 100

MENSAGEM_PADRAO_PENDENTE = "Seu acesso à loja está aguardando liberação da equipe."
MENSAGEM_PADRAO_RECUSADO = "Seu acesso à loja não foi liberado."


def obter_config(sessao: Session) -> AcessoConfig | None:
    return sessao.get(AcessoConfig, ID_CONFIG)


def modo_atual(sessao: Session) -> str:
    config = obter_config(sessao)
    return config.modo if config is not None else MODO_ABERTO


def exige_aprovacao(config: AcessoConfig | None) -> bool:
    return config is not None and config.modo == MODO_APROVACAO


def _solicitacao_pendente(sessao: Session, cliente_id: int) -> AcessoSolicitacao | None:
    return sessao.scalar(
        select(AcessoSolicitacao).where(
            AcessoSolicitacao.cliente_id == cliente_id,
            AcessoSolicitacao.situacao == "pendente",
        )
    )


def montar_estado(sessao: Session, cliente: Cliente | None) -> EstadoAcesso:
    config = obter_config(sessao)
    situacao = cliente.acesso_status if cliente is not None else None
    return EstadoAcesso(
        modo=config.modo if config is not None else MODO_ABERTO,
        pode_navegar=not exige_aprovacao(config) or situacao == "aprovado",
        identificado=cliente is not None,
        situacao=situacao,
        solicitacao_pendente=(
            cliente is not None and _solicitacao_pendente(sessao, cliente.id) is not None
        ),
        mensagem_bloqueio=config.mensagem_bloqueio if config is not None else None,
    )


def solicitar_acesso(sessao: Session, cliente: Cliente) -> EstadoAcesso:
    """Abre o pedido de liberação. IDEMPOTENTE: pedir de novo devolve o mesmo
    estado, nunca uma segunda linha e nunca 500.

    Não cria nada quando não há o que pedir — loja fora do modo aprovação, ou
    cliente já aprovado. Cliente RECUSADO não reabre pedido sozinho: o índice
    permite várias recusadas no histórico, mas deixar o recusado pedir de novo
    a cada clique enche a fila da equipe. Quem reabre é o painel.
    """
    config = obter_config(sessao)
    if not exige_aprovacao(config) or cliente.acesso_status == "aprovado":
        return montar_estado(sessao, cliente)

    if cliente.acesso_status == "recusado":
        raise AppError(
            codigo=ACESSO_RECUSADO,
            mensagem=config.mensagem_bloqueio or MENSAGEM_PADRAO_RECUSADO,
            status_code=403,
            detalhes={"situacao": "recusado"},
        )

    if _solicitacao_pendente(sessao, cliente.id) is None:
        # Dois pedidos simultâneos passam os dois pela checagem acima; o
        # índice único parcial (uma pendente por cliente) recusa o segundo.
        # O SAVEPOINT isola essa recusa: o INSERT perdedor é desfeito, a
        # transação segue viva e a resposta é a mesma do vencedor.
        try:
            with sessao.begin_nested():
                sessao.add(
                    AcessoSolicitacao(
                        cliente_id=cliente.id,
                        email=cliente.email,
                        nome=cliente.nome,
                        telefone=cliente.telefone,
                    )
                )
        except IntegrityError:
            pass
        sessao.commit()

    return montar_estado(sessao, cliente)


def listar_fila(
    sessao: Session, pagina: int = 1, por_pagina: int = POR_PAGINA_PADRAO
) -> Pagina[SolicitacaoFila]:
    """Só as pendentes, o pedido mais antigo primeiro — é uma fila."""
    por_pagina = max(1, min(por_pagina, POR_PAGINA_MAXIMO))
    pagina = max(1, pagina)
    pendentes = select(AcessoSolicitacao).where(AcessoSolicitacao.situacao == "pendente")

    total = sessao.scalar(select(func.count()).select_from(pendentes.subquery())) or 0
    linhas = sessao.scalars(
        pendentes.order_by(AcessoSolicitacao.criado_em, AcessoSolicitacao.id)
        .limit(por_pagina)
        .offset((pagina - 1) * por_pagina)
    ).all()

    return Pagina[SolicitacaoFila](
        dados=[SolicitacaoFila.model_validate(linha) for linha in linhas],
        paginacao=Paginacao(total=total, por_pagina=por_pagina, pagina=pagina),
    )


def decidir_acesso(
    sessao: Session,
    cliente_id: int,
    situacao: str,
    motivo: str | None,
    admin_id: int,
) -> DecisaoAcesso:
    """Aprova, recusa ou revoga (contrato, seção 05).

    Com pedido pendente, a decisão fecha o pedido. Sem pedido pendente — o
    aprovado que perde o acesso, o recusado que a equipe resolve liberar —
    grava uma linha JÁ decidida, para a mudança ficar no histórico igual às
    outras. O CHECK da tabela exige `decidido_em` fora de 'pendente'; as duas
    trilhas preenchem.

    O cliente é travado (FOR UPDATE) antes de ler a fila: duas decisões
    simultâneas para a mesma pessoa viram uma depois da outra, e a coluna em
    `clientes` termina igual à última linha do histórico.
    """
    cliente = sessao.scalar(select(Cliente).where(Cliente.id == cliente_id).with_for_update())
    if cliente is None:
        raise AppError(
            codigo=CLIENTE_NAO_ENCONTRADO,
            mensagem="Cliente não encontrado.",
            status_code=404,
        )

    motivo = (motivo or "").strip() or None
    agora = datetime.now(timezone.utc)
    pendente = _solicitacao_pendente(sessao, cliente.id)

    if pendente is None and cliente.acesso_status == situacao:
        # Nada a decidir: clique repetido no painel não enche o histórico.
        return DecisaoAcesso(cliente_id=cliente.id, email=cliente.email, situacao=situacao)

    if pendente is None:
        pendente = AcessoSolicitacao(
            cliente_id=cliente.id,
            email=cliente.email,
            nome=cliente.nome,
            telefone=cliente.telefone,
        )
        sessao.add(pendente)

    pendente.situacao = situacao
    pendente.motivo = motivo
    pendente.decidido_por_admin_id = admin_id
    pendente.decidido_em = agora
    cliente.acesso_status = situacao
    cliente.atualizado_em = agora
    sessao.commit()

    return DecisaoAcesso(
        cliente_id=cliente.id,
        email=cliente.email,
        situacao=situacao,
        motivo=motivo,
        decidido_em=agora,
    )


def definir_configuracao(
    sessao: Session, dados: ConfiguracaoAcessoEntrada, admin_id: int
) -> ConfiguracaoAcesso:
    """PATCH parcial do modo e da mensagem de bloqueio."""
    informados = dados.model_fields_set
    if "modo" in informados and dados.modo is None:
        raise AppError(
            codigo=DADOS_INVALIDOS,
            mensagem="Há campos inválidos no envio.",
            status_code=400,
            campos={"modo": "Escolha o modo de acesso."},
        )

    config = sessao.get(AcessoConfig, ID_CONFIG, with_for_update=True)
    if config is None:
        config = AcessoConfig(id=ID_CONFIG, modo=MODO_ABERTO)
        sessao.add(config)

    if "modo" in informados:
        config.modo = dados.modo
    if "mensagem_bloqueio" in informados:
        config.mensagem_bloqueio = (dados.mensagem_bloqueio or "").strip() or None
    config.atualizado_por_admin_id = admin_id
    config.atualizado_em = datetime.now(timezone.utc)
    sessao.commit()
    sessao.refresh(config)

    return ConfiguracaoAcesso.model_validate(config)
