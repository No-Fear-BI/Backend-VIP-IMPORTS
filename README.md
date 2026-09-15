# Backend VIP Imports

Backend da loja virtual VIP Imports (No Fear), em FastAPI, SQLAlchemy e PostgreSQL. As Fatias 0 a 4 estão prontas:

- catálogo público com filtros, busca e paginação por cursor;
- home numa rota só;
- identificação do cliente por e-mail, sem senha (ver `docs/limitacoes-conhecidas.md`);
- favoritos, carrinho e envio da seleção para o WhatsApp;
- painel administrativo com login próprio (argon2), CRUD do catálogo, destaques e consultas.

São 55 rotas sob `/api/v1`, com a documentação interativa em `/api/v1/docs`.

Onde está cada coisa:

- `src/vip_api/`: a aplicação (`rotas/`, `servicos/`, `esquemas/`, `modelos/`).
- `migracoes/`: o esquema do banco.
- `testes/`: a suíte.
- `scripts/`: comandos de operação e medição.
- `docs/`: o desenho do banco (`modelagem-banco.md`), o que o frontend precisa saber (`para-o-frontend.md`), o contrato versionado (`contrato-api-v1.json`), os relatórios de fechamento e as pendências (`pendencias.md`).

Para subir o banco, copie `.env.example` para `.env` (os valores padrão já funcionam para desenvolvimento local) e rode `docker compose up -d banco`. Isso sobe um PostgreSQL 16 na porta `5432` com os dados persistidos no volume nomeado `banco_dados` — derrubar o container com `docker compose down` não apaga nada, os dados sobrevivem até alguém remover o volume explicitamente. Confirme que subiu com `docker compose ps`; o serviço fica saudável quando o `healthcheck` (`pg_isready`) passa, geralmente em poucos segundos.

Para rodar as migrações, crie um ambiente virtual Python 3.12+ e instale as dependências com `pip install -e .`, exporte `DATABASE_URL` (o mesmo valor do `.env`, ou `set -a; source .env; set +a` no bash) e rode `alembic upgrade head` a partir da raiz do projeto. Isso cria o esquema inteiro — tabelas, tipos enumerados, índices — e semeia as duas coleções fixas (Feminino e Masculino). Para reverter tudo, `alembic downgrade base`; para ver o histórico, `alembic history`.

Para derrubar o ambiente, `docker compose down` para o container mantendo os dados, ou `docker compose down -v` para apagar também o volume e começar do zero na próxima subida. Para subir a API junto, `docker compose up -d`: o serviço `api` usa o `Dockerfile` da raiz e responde na porta `8000`.

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
os códigos sem cookie, com cookie de cliente e com cookie de admin) e a lista
das rotas de escrita fora do painel.

**Aviso novo é erro.** Os avisos conhecidos das dependências estão listados um
a um em `filterwarnings`, no `pyproject.toml`, com o motivo. Qualquer outro
derruba o teste que o emitiu. Se aparecer um, corrija a causa. Só acrescente
à lista o que for comprovadamente da dependência, e escreva o motivo.

Critério de `scripts/`: fica só o que roda à mão contra a massa grande do banco de desenvolvimento ou opera o ambiente (massa, travessia, contagem de consultas, EXPLAIN, medição de desempenho, auditoria do contrato, comandos de admin, limpeza de sessões); roteiro de verificação que virou teste sai.

## Contrato da API

O contrato v1.0 está em `docs/contrato-api-v1.json`, e mudança no contrato é
commit nesse arquivo. `python scripts/auditoria_contrato.py` confere a API
contra ele:

- sai com código 1 quando falta rota, quando existe rota congelada ou quando
  aparece rota nova sem justificativa;
- sai com código 2 quando nada falhou, mas o arquivo ainda é uma reconstrução
  e não o documento (ver `docs/pendencias.md`).

## Medição de desempenho

```
python scripts/medir_desempenho.py --salvar antes.json
python scripts/medir_desempenho.py --comparar antes.json
```

O script mede as rotas principais e percorre o catálogo inteiro nas duas
ordenações. Depois compara tempo, consultas e maior consulta com os limiares
escritos no próprio arquivo. Sai com código 1 se algum estourar. No servidor,
no dia seguinte à carga: `docker compose exec api python scripts/medir_desempenho.py`.

## Limpeza de sessões

Cada identificação de cliente abre uma sessão de 90 dias, e a tabela cresce
sozinha com o site no ar. `scripts/limpar_sessoes.py` apaga as sessões
expiradas ou revogadas das duas tabelas (`cliente_sessoes` e `admin_sessoes`)
e imprime quantas saíram. A carência padrão é de 30 dias, para o histórico
recente de login do painel continuar consultável. `--simular` só conta, sem
apagar nada. Não existe rota para isso.

Para agendar no servidor, uma vez por dia fora do horário de movimento, use o
crontab do usuário que roda o Docker (`crontab -e`):

```
# limpeza de sessões da VIP Imports — todo dia às 04:10
10 4 * * * cd /caminho/do/Backend-VIP-IMPORTS && docker compose exec -T api python scripts/limpar_sessoes.py >> /var/log/vip-imports/limpar-sessoes.log 2>&1
```

O `-T` é obrigatório no cron, porque sem terminal o `docker compose exec` recusa
alocar um. O diretório do log precisa existir. Para conferir se rodou, olhe o
fim do log: cada execução deixa a data e a tabela do relatório.
