FROM python:3.12-slim

WORKDIR /app

# libpq5: biblioteca cliente do PostgreSQL que o psycopg[binary] usa em
# tempo de execução (o wheel binário já traz o essencial, mas a lib do
# sistema evita surpresa de imagem para imagem).
# nodejs: o botão "Atualizar produtos" da Revisão roda scripts/sync-yupoo.mjs
# (servicos/atualizacao_fila.py); precisa de fetch nativo, que o Node 18+ tem.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY data ./data
COPY alembic.ini ./
COPY migracoes ./migracoes
# Os comandos de operação rodam DENTRO do container no servidor: criar e trocar
# senha de admin, limpar sessões, medir desempenho depois da carga.
COPY scripts ./scripts

RUN pip install --no-cache-dir -e .

EXPOSE 8000

# CMD "de produção" — sem --reload. O serviço "api" do docker-compose.yml
# sobrescreve este comando em desenvolvimento para ligar a recarga automática.
CMD ["uvicorn", "vip_api.principal:app", "--host", "0.0.0.0", "--port", "8000"]
