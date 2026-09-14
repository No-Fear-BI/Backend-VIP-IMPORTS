"""Limite de tentativas por IP, contado no banco (tarefa 42).

Sem senha, quem digitar o e-mail de outra pessoa entra na conta dela. Isso não
se elimina sem senha — o que dá para reduzir é o abuso automatizado, varrendo
e-mails em série. É o que este módulo faz, e é a mitigação registrada em
docs/limitacoes-conhecidas.md.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from vip_api.erros.codigos import EXCESSO_TENTATIVAS
from vip_api.erros.excecoes import AppError
from vip_api.modelos.acesso_tentativas import TentativaAcesso

ESCOPO_IDENTIFICACAO = "identificacao"
# Balde separado do da identificação do cliente (revisão 0006): mesma
# tabela, contagens que não se somam. Sem isso, um visitante teimoso na
# loja trancaria o login do painel.
ESCOPO_LOGIN_ADMIN = "admin_login"
LIMITE_POR_MINUTO = 10
# Mais apertado que o do cliente: são duas contas, e ninguém erra a
# própria senha cinco vezes no mesmo minuto sem ser um script.
LIMITE_LOGIN_ADMIN = 5
# Uma linha por IP por minuto acumula para sempre se ninguém limpar. A limpeza
# roda por amostragem (1 em cada 100 tentativas) em vez de num cron separado —
# é uma tabela pequena e o custo diluído é menor que manter uma rotina à parte.
JANELAS_GUARDADAS = timedelta(hours=2)


def _inicio_do_minuto(momento: datetime) -> datetime:
    return momento.replace(second=0, microsecond=0)


def registrar_tentativa(
    sessao: Session,
    ip: str,
    escopo: str = ESCOPO_IDENTIFICACAO,
    limite: int = LIMITE_POR_MINUTO,
) -> None:
    """Conta mais uma tentativa e estoura 429 se passar do limite na janela.

    O UPSERT devolve o contador já incrementado na mesma ida ao banco: ler e
    depois escrever abriria espaço para duas requisições simultâneas lerem o
    mesmo valor e passarem juntas.
    """
    agora = datetime.now(timezone.utc)
    janela = _inicio_do_minuto(agora)

    instrucao = (
        insert(TentativaAcesso)
        .values(escopo=escopo, ip=ip, janela=janela, tentativas=1)
        .on_conflict_do_update(
            constraint="uq_tentativas_acesso_escopo_ip_janela",
            set_={"tentativas": TentativaAcesso.__table__.c.tentativas + 1},
        )
        .returning(TentativaAcesso.tentativas)
    )
    total = sessao.scalar(instrucao)
    sessao.commit()

    if total and total % 100 == 0:
        _limpar_janelas_velhas(sessao, agora)

    if total and total > limite:
        raise AppError(
            codigo=EXCESSO_TENTATIVAS,
            mensagem="Muitas tentativas seguidas. Aguarde um minuto e tente de novo.",
            status_code=429,
        )


def _limpar_janelas_velhas(sessao: Session, agora: datetime) -> None:
    sessao.execute(
        delete(TentativaAcesso).where(TentativaAcesso.janela < agora - JANELAS_GUARDADAS)
    )
    sessao.commit()


def tentativas_na_janela(
    sessao: Session, ip: str, escopo: str = ESCOPO_IDENTIFICACAO
) -> int:
    """Só para diagnóstico e teste — o caminho normal usa registrar_tentativa."""
    return (
        sessao.scalar(
            select(func.coalesce(func.sum(TentativaAcesso.tentativas), 0)).where(
                TentativaAcesso.escopo == escopo,
                TentativaAcesso.ip == ip,
                TentativaAcesso.janela == _inicio_do_minuto(datetime.now(timezone.utc)),
            )
        )
        or 0
    )
