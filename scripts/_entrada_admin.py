"""Leitura de e-mail, nome e senha no terminal, compartilhada pelos dois
comandos de administrador.

A senha não é ecoada. `getpass` resolve isso quando existe terminal de
verdade; quando a entrada vem de um cano (`echo ... | python`, `docker exec`
sem `-t`, um script de provisionamento), o getpass do Windows lê do CONSOLE e
não do cano, e o comando trava esperando uma tecla que ninguém vai digitar.
Por isso a leitura confere `isatty()` primeiro: com terminal, getpass; sem
terminal, a entrada padrão mesmo — que é de onde os dados estão vindo.
"""

import getpass
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _tem_terminal() -> bool:
    try:
        return sys.stdin.isatty()
    except ValueError:
        return False


def ler_texto(rotulo: str) -> str:
    if _tem_terminal():
        return input(rotulo).strip()
    print(rotulo, end="", flush=True)
    linha = sys.stdin.readline()
    if not linha:
        print()
        raise SystemExit("Entrada encerrada antes da resposta.")
    valor = linha.strip()
    print(valor)
    return valor


def ler_senha(rotulo: str) -> str:
    if _tem_terminal():
        return getpass.getpass(rotulo)
    print(rotulo, end="", flush=True)
    linha = sys.stdin.readline()
    if not linha:
        print()
        raise SystemExit("Entrada encerrada antes da senha.")
    # Sem eco, como no terminal: o que aparece é o tamanho, não a senha.
    senha = linha.rstrip("\r\n")
    print("*" * len(senha))
    return senha


def ler_senha_confirmada() -> str:
    senha = ler_senha("Senha: ")
    if senha != ler_senha("Repita a senha: "):
        raise SystemExit("As senhas não conferem. Nada foi gravado.")
    return senha
