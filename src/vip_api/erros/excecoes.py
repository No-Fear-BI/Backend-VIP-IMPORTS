"""Exceção de domínio. Todo erro esperado (não achou, sem permissão, conflito)
é um AppError — o manipulador central (manipuladores.py) traduz pro formato
único de erro da API. Nunca deixe uma exceção de biblioteca (SQLAlchemy,
psycopg) vazar até o cliente: capture e relance como AppError.

Mapeamento de status HTTP, contrato seção 1.4 — quem levanta o AppError
escolhe o status_code observando esta tabela:
    400 dados inválidos (campos preenchido)   401 não identificado
    403 sem permissão                         404 não encontrado
    409 conflito                              429 excesso de requisições
(500 é só o manipulador de exceção não tratada — nunca se levanta um AppError com 500 de propósito.)
"""

from __future__ import annotations


class AppError(Exception):
    def __init__(
        self,
        codigo: str,
        mensagem: str,
        status_code: int = 400,
        campos: dict[str, str] | None = None,
    ) -> None:
        self.codigo = codigo
        self.mensagem = mensagem
        self.status_code = status_code
        self.campos = campos
        super().__init__(mensagem)
