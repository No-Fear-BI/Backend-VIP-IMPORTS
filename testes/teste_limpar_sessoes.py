"""scripts/limpar_sessoes.py: sai só o que está morto há mais que a carência."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from scripts.limpar_sessoes import limpar
from vip_api.modelos.admin import AdminSessao
from vip_api.modelos.cliente import ClienteSessao

AGORA = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
DIA = timedelta(days=1)


def _sessao(modelo, dono: dict, token: str, expira: datetime, revogada: datetime | None = None):
    return modelo(
        **dono,
        token_hash=token.ljust(64, "0"),
        criado_em=AGORA - 100 * DIA,
        expira_em=expira,
        revogado_em=revogada,
    )


def _semear(sessao, cliente, administrador):
    for modelo, dono in (
        (ClienteSessao, {"cliente_id": cliente.id}),
        (AdminSessao, {"administrador_id": administrador.id}),
    ):
        prefixo = modelo.__tablename__[:1]
        sessao.add_all(
            [
                _sessao(modelo, dono, f"{prefixo}valida", AGORA + 10 * DIA),
                _sessao(modelo, dono, f"{prefixo}expirada-ha-40", AGORA - 40 * DIA),
                _sessao(modelo, dono, f"{prefixo}expirada-ontem", AGORA - DIA),
                _sessao(modelo, dono, f"{prefixo}revogada-ha-40", AGORA + 10 * DIA, AGORA - 40 * DIA),
                _sessao(modelo, dono, f"{prefixo}revogada-ontem", AGORA + 10 * DIA, AGORA - DIA),
            ]
        )
    sessao.commit()


def _restantes(sessao, modelo, prefixo):
    return sorted(
        t.rstrip("0")[1:]
        for t in sessao.scalars(select(modelo.token_hash).where(modelo.token_hash.like(f"{prefixo}%")))
    )


def teste_carencia_de_trinta_dias_guarda_o_historico_recente(sessao, cliente, administrador):
    _semear(sessao, cliente, administrador)

    relatorio = limpar(sessao, timedelta(days=30), simular=False, agora=AGORA)

    esperado = ["expirada-ontem", "revogada-ontem", "valida"]
    assert _restantes(sessao, ClienteSessao, "c") == esperado
    assert _restantes(sessao, AdminSessao, "a") == esperado
    assert [linha["removidas"] for linha in relatorio] == [2, 2]


def teste_sem_carencia_sobra_so_a_valida(sessao, cliente, administrador):
    _semear(sessao, cliente, administrador)

    limpar(sessao, timedelta(0), simular=False, agora=AGORA)

    assert _restantes(sessao, ClienteSessao, "c") == ["valida"]
    assert _restantes(sessao, AdminSessao, "a") == ["valida"]


def teste_simular_nao_apaga_nada(sessao, cliente, administrador):
    _semear(sessao, cliente, administrador)

    relatorio = limpar(sessao, timedelta(0), simular=True, agora=AGORA)

    assert [linha["removidas"] for linha in relatorio] == [4, 4]
    assert len(_restantes(sessao, ClienteSessao, "c")) == 5
    assert len(_restantes(sessao, AdminSessao, "a")) == 5
