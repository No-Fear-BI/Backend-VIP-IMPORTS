# Pendências

Dívida conhecida e aceita por enquanto. Uma linha por item: o que é, por que ficou e quem decide. Limitações que são decisão de produto, e não dívida, ficam em `limitacoes-conhecidas.md`.

| Pendência | Motivo | Quem decide |
|---|---|---|
| O contrato de API v1.0 não está versionado no repositório. | `scripts/auditoria_contrato.py` compara a API com uma reconstrução do contrato. Cinco rotas do painel (`GET /admin/marcas`, `PATCH /admin/marcas/{id}`, `GET /admin/categorias`, `PATCH /admin/categorias/{id}`, `GET /admin/banners`) não têm evidência escrita, e a conta não fecha: 51 rotas reconstruídas contra 52 endpoints citados. | No Fear, que guarda o documento: colocar o contrato em `docs/`. |
| Três rotas de produto existem fora do contrato v1.0: `GET /admin/eu`, `PATCH /admin/banners/ordem` e `POST /carrinho/migrar`. | Estão registradas em `para-o-frontend.md`, mas a fonte da verdade continua sem elas. `GET /health` também fica fora, mas é infraestrutura e não entra no contrato. | No Fear com o frontend, numa revisão v1.1 do contrato. |
| Seção 05 do contrato (acesso compartilhado e solicitações): cinco rotas não implementadas. | Congelada por decisão do cliente. A auditoria confere que nenhuma rota do tema existe. | Cliente (VIP Imports). |
| A abertura do `README.md` descreve a Fatia 0: diz que não há rota e que não existe `Dockerfile`. | O texto ficou para trás nas Fatias 1 a 4 e engana quem chega ao projeto agora. | Backend: reescrever a abertura. |
| A suíte emite cerca de 230 avisos: `UnsupportedFieldAttributeWarning` do pydantic 2.13 com o FastAPI 0.115, gerado nos campos com alias camelCase, mais um `DeprecationWarning` do TestClient. | Não quebram nada, mas escondem um aviso novo que importe. O `pyproject.toml` limita o FastAPI a `<0.116` e deixa o pydantic solto até `<3.0`. | Backend: subir o teto do FastAPI ou fixar o pydantic. |
