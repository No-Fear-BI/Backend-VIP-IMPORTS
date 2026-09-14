"""Constantes das identidades de teste.

Arquivo à parte do conftest de propósito: importar o conftest de dentro de um
teste faz o Python carregá-lo uma segunda vez, com outro nome de módulo, e
todo o efeito colateral dele (criar o banco de teste, calcular o hash argon2)
acontece de novo.
"""

EMAIL_ADMIN = "admin@teste.local"
SENHA_ADMIN = "senha-de-teste-1"
EMAIL_CLIENTE = "cliente@teste.local"

# IP de mentira do TestClient: o padrão do Starlette é a string "testclient",
# que não cabe na coluna `inet` de tentativas_acesso e derrubaria toda rota
# com limite por IP.
CLIENTE_DE_ORIGEM = ("127.0.0.1", 50000)
