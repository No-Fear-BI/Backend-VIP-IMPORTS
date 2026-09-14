"""Hash de senha de administrador — argon2id.

POR QUE ARGON2 AQUI E SHA-256 NO TOKEN (seguranca/tokens.py), e por que os
dois não viram um só:

Senha é escolhida por gente. Tem entropia baixa, aparece em lista de senhas
vazadas e é testável em lote — o hash precisa ser CARO de propósito, para que
cada tentativa custe caro também. Argon2id gasta memória e tempo por desenho,
e é conferido uma vez por login, algumas vezes ao dia.

Token de sessão é o contrário: 32 bytes aleatórios, que não se adivinha em
nenhuma escala de tempo, conferido a CADA requisição autenticada. Ali o hash
precisa ser barato, e SHA-256 é a escolha certa.

Unificar os dois só tem dois desfechos: ou a senha passa a usar o hash barato
e fica fraca, ou toda chamada autenticada do painel passa a custar os ~50 ms
do argon2.

O hash do argon2 já carrega sal e parâmetros dentro da própria string — não
existe coluna de sal, e trocar os parâmetros no futuro não invalida os hashes
antigos, que continuam conferindo com os parâmetros com que foram criados.
"""

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# Parâmetros padrão da biblioteca (argon2id, 64 MiB, 3 passagens): ~50 ms por
# verificação nesta máquina. Mexer neles é decisão de operação, não de código
# — se mudar, os hashes já gravados continuam válidos.
_hasher = PasswordHasher()

# Hash de uma senha aleatória que ninguém conhece e que não abre nada. Existe
# para o login gastar o MESMO tempo quando o e-mail não existe: sem isso, a
# resposta rápida denuncia "este e-mail não está cadastrado" e a lenta
# confirma que está. Gerado uma vez, no carregamento do módulo.
HASH_DESCARTAVEL = _hasher.hash(secrets.token_urlsafe(32))


def gerar_hash(senha: str) -> str:
    return _hasher.hash(senha)


def conferir_senha(senha: str, hash_guardado: str) -> bool:
    """False em vez de exceção para senha errada — e também para hash
    corrompido ou em formato desconhecido, que não deve virar erro 500 na cara
    de quem está tentando entrar."""
    try:
        return _hasher.verify(hash_guardado, senha)
    except (VerificationError, InvalidHashError):
        return False


def gastar_tempo_de_verificacao(senha: str) -> None:
    """Confere a senha contra o hash descartável e joga o resultado fora.

    Chamada quando o e-mail não existe ou a conta está inativa, para o custo
    do argon2 aparecer nos três casos. Sem ela, medir o tempo de resposta
    entrega quais e-mails são de administrador de verdade.
    """
    conferir_senha(senha, HASH_DESCARTAVEL)
