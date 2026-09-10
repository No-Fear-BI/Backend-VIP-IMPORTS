FROM python:3.12-slim

WORKDIR /app

# libpq5: biblioteca cliente do PostgreSQL que o psycopg[binary] usa em
# tempo de execução (o wheel binário já traz o essencial, mas a lib do
# sistema evita surpresa de imagem para imagem).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic.ini ./
COPY migracoes ./migracoes

RUN pip install --no-cache-dir -e .

EXPOSE 8000

# CMD "de produção" — sem --reload. O serviço "api" do docker-compose.yml
# sobrescreve este comando em desenvolvimento para ligar a recarga automática.
CMD ["uvicorn", "vip_api.principal:app", "--host", "0.0.0.0", "--port", "8000"]
