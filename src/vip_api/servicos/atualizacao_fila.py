"""Atualização da fila de revisão a partir do Yupoo (botão "Atualizar produtos").

Roda `scripts/sync-yupoo.mjs` — o mesmo script que se roda à mão — com a lista de
`data/fornecedores-adicionais.json` mais os fornecedores embutidos (`--padrao`). O script
junta os álbuns pelo id (`fornecedor-idDoÁlbum`), então reexecutar não duplica nada, e a
fila já esconde o que foi aprovado ou reprovado (as decisões ficam no PostgreSQL).

A coleta leva vários minutos, por isso roda numa thread e a tela consulta o andamento.
O estado mora em ARQUIVOS (`data/`), não em memória: sobrevive a reinício, vale para mais
de um processo e a trava (`sync-yupoo.lock`, criada com O_EXCL) impede duas coletas juntas.
"""

import json
import os
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
DADOS = RAIZ / "data"
TRAVA = DADOS / "sync-yupoo.lock"
ESTADO = DADOS / "sync-yupoo-estado.json"
RELATORIO = DADOS / "sync-yupoo-report.json"

# Tempo máximo de uma coleta inteira.
LIMITE_SEGUNDOS = 2 * 60 * 60
# Enquanto a coleta roda, a thread "bate" na trava (mtime) a cada BATIDA segundos. Trava sem batida há
# mais de VALIDADE_TRAVA é de uma coleta morta (a API reiniciou no meio): sem isso o botão ficaria
# preso em "Atualizando…" por horas depois de qualquer reinício.
BATIDA = 20
VALIDADE_TRAVA = 120
_fio: threading.Thread | None = None


def _comando() -> list[str]:
    return ["node", str(RAIZ / "scripts" / "sync-yupoo.mjs"), str(DADOS / "fornecedores-adicionais.json"), "--padrao"]


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gravar_estado(**campos) -> None:
    # Um temporário por thread: duas gravações juntas no mesmo nome se atropelariam no `replace`.
    temporario = ESTADO.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    temporario.write_text(json.dumps(campos, ensure_ascii=False), encoding="utf-8")
    for tentativa in range(10):
        try:
            os.replace(temporario, ESTADO)
            return
        except PermissionError:  # Windows: o arquivo está aberto numa leitura do `estado()`
            if tentativa == 9:
                raise
            time.sleep(0.05)


def _ler_json(caminho: Path) -> dict:
    try:
        return json.loads(caminho.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def _trava_viva() -> bool:
    try:
        return time.time() - TRAVA.stat().st_mtime <= VALIDADE_TRAVA
    except OSError:
        return False


def _tomar_trava() -> bool:
    for _ in range(2):
        try:
            os.close(os.open(TRAVA, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return True
        except FileExistsError:
            if _trava_viva():
                return False
            TRAVA.unlink(missing_ok=True)  # trava velha: o processo que a criou morreu
    return False


def estado() -> dict:
    """`estado`: ocioso | rodando | concluido | falhou — mais os números da última coleta."""
    salvo = _ler_json(ESTADO)
    if _trava_viva():
        return {"estado": "rodando", "iniciadoEm": salvo.get("iniciadoEm")}
    if salvo.get("estado") == "rodando":  # sem trava: a coleta morreu sem registrar o fim
        return {"estado": "falhou", "iniciadoEm": salvo.get("iniciadoEm"), "erro": "A coleta foi interrompida. Tente de novo."}
    if salvo:
        return salvo
    relatorio = _ler_json(RELATORIO)
    return {"estado": "ocioso", "concluidoEm": relatorio.get("concluidoEm")}


def _cauda(texto: str) -> str:
    linhas = [linha for linha in (texto or "").strip().splitlines() if linha.strip()]
    return " | ".join(linhas[-3:])[:500] or "O script terminou com erro, sem mensagem."


def _executar(inicio: str) -> None:
    try:
        # Saída num arquivo temporário (e não num pipe): ninguém precisa ler enquanto roda, então um
        # script falante não trava no buffer.
        with tempfile.TemporaryFile() as saida:
            processo = subprocess.Popen(_comando(), cwd=RAIZ, stdout=saida, stderr=subprocess.STDOUT)
            comeco = time.monotonic()
            while True:
                try:
                    codigo = processo.wait(timeout=BATIDA)
                    break
                except subprocess.TimeoutExpired:
                    if time.monotonic() - comeco > LIMITE_SEGUNDOS:
                        processo.kill()
                        raise RuntimeError("A coleta passou do tempo limite e foi cancelada.")
                    os.utime(TRAVA)  # batida: "ainda estou vivo"
            saida.seek(0)
            texto = saida.read().decode("utf-8", errors="replace")
        if codigo != 0:
            raise RuntimeError(_cauda(texto))
        relatorio = _ler_json(RELATORIO)
        _gravar_estado(
            estado="concluido", iniciadoEm=inicio, concluidoEm=_agora(),
            adicionados=relatorio.get("adicionados"), coletados=relatorio.get("coletados"), total=relatorio.get("total"),
        )
    except Exception as erro:  # a thread nunca pode morrer calada: a tela precisa ver o motivo
        _gravar_estado(estado="falhou", iniciadoEm=inicio, concluidoEm=_agora(), erro=str(erro)[:500] or "Falha ao atualizar.")
    finally:
        TRAVA.unlink(missing_ok=True)


def iniciar() -> dict:
    """Começa a coleta, se não houver uma em andamento (nesse caso só devolve o andamento)."""
    global _fio
    if not _tomar_trava():
        return estado()
    inicio = _agora()
    _gravar_estado(estado="rodando", iniciadoEm=inicio)  # só `iniciar` grava "rodando": um escritor por vez
    _fio = threading.Thread(target=_executar, args=(inicio,), name="atualizar-fila-yupoo", daemon=True)
    _fio.start()
    return estado()
