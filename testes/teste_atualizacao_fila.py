"""Botão "Atualizar produtos" da Revisão (vip_api.servicos.atualizacao_fila).

O que este arquivo prova: a coleta roda uma vez por vez (trava), o estado conta o resultado
(ou o erro) em vez de a tela ficar esperando, e a trava é sempre solta. O script de verdade
nunca roda aqui: `_comando` é trocado por um programa Python mínimo, então o teste não
depende do Node nem do Yupoo estar no ar. A deduplicação em si (`mesclar`, por id) tem teste
próprio em scripts/sync-yupoo.test.mjs.
"""

import json
import os
import sys
import time

import pytest

from vip_api.servicos import atualizacao_fila as fila

ROTA = "/api/v1/admin/revisao"


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    """Aponta o serviço para uma pasta de dados descartável."""
    monkeypatch.setattr(fila, "DADOS", tmp_path)
    monkeypatch.setattr(fila, "TRAVA", tmp_path / "sync-yupoo.lock")
    monkeypatch.setattr(fila, "ESTADO", tmp_path / "sync-yupoo-estado.json")
    monkeypatch.setattr(fila, "RELATORIO", tmp_path / "sync-yupoo-report.json")
    monkeypatch.setattr(fila, "RAIZ", tmp_path)
    monkeypatch.setattr(fila, "_fio", None)  # sem thread herdada de outro teste
    yield tmp_path
    if fila._fio:
        fila._fio.join(timeout=10)
    monkeypatch.setattr(fila, "_fio", None)


def _programa(monkeypatch, codigo: str):
    monkeypatch.setattr(fila, "_comando", lambda: [sys.executable, "-c", codigo])


def _esperar_fim():
    assert fila._fio is not None
    fila._fio.join(timeout=10)
    assert not fila._fio.is_alive()


ESCREVE_RELATORIO = (
    "import json; json.dump({'adicionados': 7, 'coletados': 120, 'total': 500}, open('sync-yupoo-report.json', 'w'))"
)


def teste_sem_coleta_anterior_o_estado_e_ocioso(pasta):
    assert fila.estado()["estado"] == "ocioso"


def teste_coleta_concluida_conta_o_que_entrou_e_solta_a_trava(pasta, monkeypatch):
    _programa(monkeypatch, ESCREVE_RELATORIO)

    inicial = fila.iniciar()
    _esperar_fim()
    final = fila.estado()

    assert inicial["estado"] == "rodando"
    assert final["estado"] == "concluido"
    assert (final["adicionados"], final["coletados"], final["total"]) == (7, 120, 500)
    assert not fila.TRAVA.exists()


def teste_falha_do_script_vira_estado_falhou_com_o_motivo(pasta, monkeypatch):
    _programa(monkeypatch, "import sys; print('Falha na página 3: HTTP 503', file=sys.stderr); sys.exit(1)")

    fila.iniciar()
    _esperar_fim()
    final = fila.estado()

    assert final["estado"] == "falhou"
    assert "HTTP 503" in final["erro"]
    assert not fila.TRAVA.exists()


def teste_programa_que_nao_existe_tambem_vira_falha(pasta, monkeypatch):
    monkeypatch.setattr(fila, "_comando", lambda: ["programa-que-nao-existe-xyz"])

    fila.iniciar()
    _esperar_fim()

    assert fila.estado()["estado"] == "falhou"
    assert not fila.TRAVA.exists()


def teste_com_coleta_em_andamento_nao_comeca_outra(pasta, monkeypatch):
    fila.TRAVA.write_text("")  # outra coleta (ou outro processo) está rodando
    chamadas = []
    monkeypatch.setattr(fila, "_comando", lambda: chamadas.append(1) or [sys.executable, "-c", "pass"])

    resposta = fila.iniciar()

    assert resposta["estado"] == "rodando"
    assert fila._fio is None
    assert chamadas == []
    assert fila.TRAVA.exists()  # não é nossa: não pode ser solta


def teste_trava_velha_de_processo_morto_e_descartada(pasta, monkeypatch):
    _programa(monkeypatch, ESCREVE_RELATORIO)
    fila.TRAVA.write_text("")
    velha = time.time() - fila.LIMITE_SEGUNDOS - 3600
    os.utime(fila.TRAVA, (velha, velha))

    fila.iniciar()
    _esperar_fim()

    assert fila.estado()["estado"] == "concluido"


def teste_estado_rodando_sem_trava_e_coleta_interrompida(pasta):
    fila.ESTADO.write_text(json.dumps({"estado": "rodando", "iniciadoEm": "2026-10-02T10:00:00+00:00"}))

    estado = fila.estado()

    assert estado["estado"] == "falhou"
    assert "interrompida" in estado["erro"]


def teste_rota_inicia_e_consulta_o_andamento(admin_logado, pasta, monkeypatch):
    _programa(monkeypatch, ESCREVE_RELATORIO)

    iniciou = admin_logado.post(f"{ROTA}/atualizar")
    _esperar_fim()
    consulta = admin_logado.get(f"{ROTA}/atualizacao")

    assert iniciou.status_code == 200
    assert iniciou.json()["estado"] == "rodando"
    assert consulta.json()["estado"] == "concluido"
    assert consulta.json()["adicionados"] == 7


def teste_rotas_exigem_sessao_de_admin(app_de_teste):
    from fastapi.testclient import TestClient

    with TestClient(app_de_teste) as anonimo:
        assert anonimo.post(f"{ROTA}/atualizar").status_code == 401
        assert anonimo.get(f"{ROTA}/atualizacao").status_code == 401
