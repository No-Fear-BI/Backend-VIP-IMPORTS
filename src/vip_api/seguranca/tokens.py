"""Geração e hash de token opaco.

Este é o ÚNICO ponto compartilhado entre a sessão de cliente e a de
administrador, e ele não sabe de quem é o token: não recebe tipo, não escolhe
tabela, não decide cookie. Tabela, cookie, expiração e dependência de
autenticação são escritos duas vezes, um para cada lado — trinta linhas
duplicadas custam menos que um `criar_sessao(tipo=...)` em que alguém passa o
argumento errado e um visitante entra no painel.
"""

import hashlib
import secrets

BYTES_DO_TOKEN = 32


def gerar_token() -> str:
    """32 bytes aleatórios em base64 URL-safe. É o valor que vai no cookie e
    que NUNCA é gravado no banco."""
    return secrets.token_urlsafe(BYTES_DO_TOKEN)


def hash_do_token(token: str) -> str:
    """SHA-256 hexadecimal — 64 caracteres, que é o tamanho da coluna.

    SHA-256 e não argon2, de propósito. Argon2 é caro por desenho, para tornar
    inviável testar bilhões de senhas humanas, que são curtas e adivinháveis.
    Um token de 32 bytes aleatórios não é adivinhável em nenhuma escala de
    tempo, e este hash é conferido a CADA requisição autenticada: argon2 aqui
    somaria mais de 100 ms a toda chamada, sem ganho de segurança nenhum.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def conferir_token(token: str, hash_guardado: str) -> bool:
    """Comparação em tempo constante — evita distinguir token quase certo de
    token errado pelo tempo de resposta."""
    return secrets.compare_digest(hash_do_token(token), hash_guardado)
