# Backend VIP Imports

Backend da loja virtual VIP Imports (No Fear): catálogo, identificação de cliente por e-mail e painel administrativo. Este repositório está na Fatia 0 — só existem o desenho do banco (`docs/modelagem-banco.md`) e as migrações Alembic que o implementam. Não há rota, modelo ou serviço ainda.

Para subir o banco, copie `.env.example` para `.env` (os valores padrão já funcionam para desenvolvimento local) e rode `docker compose up -d banco`. Isso sobe um PostgreSQL 16 na porta `5432` com os dados persistidos no volume nomeado `banco_dados` — derrubar o container com `docker compose down` não apaga nada, os dados sobrevivem até alguém remover o volume explicitamente. Confirme que subiu com `docker compose ps`; o serviço fica saudável quando o `healthcheck` (`pg_isready`) passa, geralmente em poucos segundos.

Para rodar as migrações, crie um ambiente virtual Python 3.12+ e instale as dependências com `pip install -e .`, exporte `DATABASE_URL` (o mesmo valor do `.env`, ou `set -a; source .env; set +a` no bash) e rode `alembic upgrade head` a partir da raiz do projeto. Isso cria o esquema inteiro — tabelas, tipos enumerados, índices — e semeia as duas coleções fixas (Feminino e Masculino). Para reverter tudo, `alembic downgrade base`; para ver o histórico, `alembic history`.

Para derrubar o ambiente, `docker compose down` para o container mantendo os dados, ou `docker compose down -v` para apagar também o volume e começar do zero na próxima subida. Não existe `Dockerfile` da aplicação ainda — isso entra numa tarefa posterior, junto com as rotas e os modelos SQLAlchemy.
