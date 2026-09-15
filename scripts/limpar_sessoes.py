"""Apaga sessões mortas de cliente e de administrador, com relatório.

Morta é a sessão expirada ou revogada. Nenhuma das duas volta a valer: o
login confere `expira_em` e `revogado_em` a cada requisição. Só que as linhas
continuam na tabela, e a de clientes cresce sozinha com o site no ar: cada
identificação abre uma sessão de 90 dias, e cada "sair" revoga uma.

NÃO existe rota para isto, de propósito: é manutenção agendada no servidor,
não ação de usuário. Como agendar está no README.

    python scripts/limpar_sessoes.py                 # apaga, com 30 dias de carência
    python scripts/limpar_sessoes.py --simular       # só conta, não apaga nada
    python scripts/limpar_sessoes.py --carencia-dias 0

A carência existe por causa do painel. A sessão de admin guarda IP e
navegador de cada login, e isso é o que se consulta quando alguém pergunta
"quem entrou no painel semana passada?". Apagar a sessão revogada no mesmo
dia apagaria essa resposta. Com 30 dias a tabela continua pequena e o
histórico recente fica.
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy import delete, func, or_, select  # noqa: E402

from vip_api.banco import SessaoLocal  # noqa: E402
from vip_api.modelos.admin import AdminSessao  # noqa: E402
from vip_api.modelos.cliente import ClienteSessao  # noqa: E402

TABELAS = (("cliente_sessoes", ClienteSessao), ("admin_sessoes", AdminSessao))


def _contar(sessao, modelo, *condicoes) -> int:
    return sessao.scalar(select(func.count()).select_from(modelo).where(*condicoes)) or 0


def limpar(sessao, carencia: timedelta, simular: bool, agora: datetime | None = None) -> list[dict]:
    """Uma transação para as duas tabelas: ou sai tudo o que devia, ou nada."""
    agora = agora or datetime.now(timezone.utc)
    limite = agora - carencia
    relatorio = []

    for nome, modelo in TABELAS:
        expiradas = modelo.expira_em < limite
        revogadas = modelo.revogado_em < limite
        linha = {
            "tabela": nome,
            "antes": _contar(sessao, modelo),
            # Uma sessão pode estar expirada E revogada: conta nas duas
            # colunas, mas sai uma vez só.
            "expiradas": _contar(sessao, modelo, expiradas),
            "revogadas": _contar(sessao, modelo, revogadas),
            "validas": _contar(
                sessao, modelo, modelo.expira_em > agora, modelo.revogado_em.is_(None)
            ),
        }
        if simular:
            linha["removidas"] = _contar(sessao, modelo, or_(expiradas, revogadas))
        else:
            linha["removidas"] = sessao.execute(delete(modelo).where(or_(expiradas, revogadas))).rowcount
        linha["depois"] = linha["antes"] - linha["removidas"]
        relatorio.append(linha)

    if simular:
        sessao.rollback()
    else:
        sessao.commit()
    return relatorio


def main() -> None:
    analisador = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    analisador.add_argument("--carencia-dias", type=int, default=30, help="só apaga o que morreu há mais que isto (padrão: 30)")
    analisador.add_argument("--simular", action="store_true", help="conta o que sairia, sem apagar")
    argumentos = analisador.parse_args()
    if argumentos.carencia_dias < 0:
        analisador.error("--carencia-dias não pode ser negativo")

    inicio = datetime.now(timezone.utc)
    with SessaoLocal() as sessao:
        relatorio = limpar(sessao, timedelta(days=argumentos.carencia_dias), argumentos.simular, inicio)

    modo = "SIMULAÇÃO — nada foi apagado" if argumentos.simular else "limpeza executada"
    print(f"limpeza de sessões · {inicio:%Y-%m-%d %H:%M:%S} UTC · carência de {argumentos.carencia_dias} dia(s) · {modo}\n")
    print(f"  {'TABELA':<16} {'ANTES':>7} {'EXPIRADAS':>10} {'REVOGADAS':>10} {'REMOVIDAS':>10} {'DEPOIS':>7} {'VÁLIDAS':>8}")
    print(f"  {'-' * 16} {'-' * 7} {'-' * 10} {'-' * 10} {'-' * 10} {'-' * 7} {'-' * 8}")
    for linha in relatorio:
        print(
            f"  {linha['tabela']:<16} {linha['antes']:>7} {linha['expiradas']:>10} {linha['revogadas']:>10} "
            f"{linha['removidas']:>10} {linha['depois']:>7} {linha['validas']:>8}"
        )
    total = sum(linha["removidas"] for linha in relatorio)
    print(f"\n  total {'que sairia' if argumentos.simular else 'removido'}: {total} sessão(ões)")
    print("  (expirada e revogada ao mesmo tempo conta nas duas colunas e sai uma vez só)")


if __name__ == "__main__":
    main()
