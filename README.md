# Backend VIP Imports

Backend da loja virtual VIP Imports (No Fear): catálogo, identificação de cliente por e-mail e painel administrativo. Este repositório está na Fatia 0 — só existem o desenho do banco (`docs/modelagem-banco.md`) e as migrações Alembic que o implementam. Não há rota, modelo ou serviço ainda.

Para subir o banco, copie `.env.example` para `.env` (os valores padrão já funcionam para desenvolvimento local) e rode `docker compose up -d banco`. Isso sobe um PostgreSQL 16 na porta `5432` com os dados persistidos no volume nomeado `banco_dados` — derrubar o container com `docker compose down` não apaga nada, os dados sobrevivem até alguém remover o volume explicitamente. Confirme que subiu com `docker compose ps`; o serviço fica saudável quando o `healthcheck` (`pg_isready`) passa, geralmente em poucos segundos.

Para rodar as migrações, crie um ambiente virtual Python 3.12+ e instale as dependências com `pip install -e .`, exporte `DATABASE_URL` (o mesmo valor do `.env`, ou `set -a; source .env; set +a` no bash) e rode `alembic upgrade head` a partir da raiz do projeto. Isso cria o esquema inteiro — tabelas, tipos enumerados, índices — e semeia as duas coleções fixas (Feminino e Masculino). Para reverter tudo, `alembic downgrade base`; para ver o histórico, `alembic history`.

Para derrubar o ambiente, `docker compose down` para o container mantendo os dados, ou `docker compose down -v` para apagar também o volume e começar do zero na próxima subida. Não existe `Dockerfile` da aplicação ainda — isso entra numa tarefa posterior, junto com as rotas e os modelos SQLAlchemy.

## Testes

```
pip install -e ".[dev]"
pytest
```

O `pytest` roda contra um banco PRÓPRIO — a `DATABASE_URL` do `.env` com o
sufixo `_teste` no nome do banco (ou `DATABASE_URL_TESTE`, se você preferir
outro). Ele é criado sozinho na primeira execução, recebe as migrações do
Alembic e nunca é o banco de desenvolvimento: `testes/conftest.py` se recusa a
rodar se o nome não terminar em `_teste`. Cada teste roda dentro de uma
transação revertida no fim, então nada fica para trás entre um teste e outro.

`pytest -s` mostra a tabela da varredura de proteção do painel (rota, método e
os códigos sem cookie, com cookie de cliente e com cookie de admin).

Critério de `scripts/`: fica só o que roda à mão contra a massa grande do banco de desenvolvimento ou opera o ambiente (massa, travessia, contagem de consultas, EXPLAIN, auditoria do contrato, comandos de admin); roteiro de verificação que virou teste sai.
