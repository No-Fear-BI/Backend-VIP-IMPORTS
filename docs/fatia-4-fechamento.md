# Fatia 4: fechamento do painel

Estado em 15/09/2026, branch `feat/painel-fechamento`. O painel implementa todas as rotas do contrato, conforme a reconstrução usada na auditoria. Nada ficou pela metade no código. O que falta depende de documento ou de decisão de outra pessoa (ver "Pendências").

## Rotas

- **55 rotas** na API, contando catálogo, cliente e painel: 51 do contrato e 4 fora dele.
- **33 rotas no painel** (`/api/v1/admin/...`): 31 do contrato, mais `GET /admin/eu` e `PATCH /admin/banners/ordem`.
- 31 dessas 33 exigem sessão de admin. As 2 exceções declaradas são login e logout (`POST` e `DELETE /admin/sessao`). A varredura de `testes/teste_protecao_admin.py` lê as rotas do próprio roteador, então rota nova já nasce coberta.

## Testes

- **187 testes, todos passando**, em cerca de 17 s contra o banco `_teste`.
- 162 deles estão nos arquivos do painel: `teste_admin_*`, `teste_protecao_admin`, `teste_sessao_admin` e `teste_acesso_painel`.
- 15 entraram neste fechamento. Cobrem o que só os roteiros de verificação provavam:
  - atributos do cookie do admin;
  - conta inativa recebendo a mesma resposta das outras falhas, com argon2 nos três casos;
  - convivência dos cookies de cliente e de admin;
  - troca de senha derrubando a sessão;
  - limite de login com baldes separados;
  - expiração da sessão em 12 h;
  - FK composta e unicidade do par de variações do carrinho.

## Auditoria do contrato

Saída de `scripts/auditoria_contrato.py`. Atenção: **o contrato v1.0 não está no repositório**. A auditoria compara a API com uma reconstrução feita a partir do que os docs e o código citam.

- **Do contrato:** as 51 rotas a implementar estão implementadas e nenhuma falta.
- **Seção 05 (acesso):** 5 rotas não existem, e é o certo. A seção foi congelada por decisão do cliente, e a auditoria confere que nenhuma rota do tema existe.
- **Além do contrato:** 4 rotas.
  - `GET /admin/eu` (tarefa 53): o painel usa para saber se a sessão vale.
  - `PATCH /admin/banners/ordem` (tarefa 57): a ordem contígua dos banners precisa de rota própria.
  - `POST /carrinho/migrar` (tarefa 50): leva o carrinho anônimo para a conta.
  - `GET /health`: healthcheck do Docker, não é rota de produto.
  - As três primeiras estão em `para-o-frontend.md`.
- **Incerteza:** 5 rotas da reconstrução não têm evidência escrita (`GET` e `PATCH` de marcas e de categorias, e `GET /admin/banners`). A reconstrução chega a 51 rotas e o contrato fala em 52 endpoints. Só dá para fechar essa conta com o documento em mãos.

## Medição na massa grande

Banco de desenvolvimento com 4.997 produtos (4.636 visíveis e 361 ocultos), 47 clientes e 22 seleções. Aplicação real (uvicorn) servindo por HTTP em 127.0.0.1. Cada rota teve 3 requisições de aquecimento e depois 20 medidas. Controle de transação não conta como consulta.

**A consulta de sessão do admin está incluída na contagem** das rotas do painel. É uma por requisição, em `admin_sessoes` com join em `administradores`, e aparece na coluna ao lado.

| Medição | Parâmetros | Consultas | Delas, sessão do admin | Tempo (mediana / p95) | Resultado |
|---|---|---|---|---|---|
| Travessia, `ordem=recentes` | `porPagina=24`, 194 páginas | 195 (2 na 1ª página, 1 por página com cursor) | — | 3,54 s no total | 4.636 ids, 0 repetidos, 0 faltando, 0 ocultos: OK |
| Travessia, `ordem=nome` | `porPagina=24`, 194 páginas | 195 (2 na 1ª página, 1 por página com cursor) | — | 2,53 s no total | 4.636 ids, 0 repetidos, 0 faltando, 0 ocultos: OK |
| `GET /produtos` | 1ª página, 24 itens | 2 | — | 10,7 / 26,7 ms | 24 de 4.636 |
| `GET /home` | — | 4 | — | 13,9 / 25,9 ms | 3 banners, 2 destaques, 6 categorias, 18 marcas |
| `GET /admin/produtos` | 1ª página, 50 itens | 3 | 1 | 16,0 / 18,3 ms | 50 de 4.997 |
| `GET /admin/resumo` | — | 4 | 1 | 13,1 / 27,8 ms | 4.997 produtos, 18 marcas |
| `GET /admin/selecoes` | 1ª página, 20 seleções | 4 | 1 | 17,1 / 40,7 ms | 20 de 22, 377 itens |
| `GET /admin/clientes` | 1ª página, 20 clientes | 3 | 1 | 9,3 / 26,1 ms | 20 de 47 |

A contagem de cada rota foi a mesma nas 20 requisições e não acompanha o volume da página. `GET /admin/selecoes`, por exemplo, traz 377 itens em 4 consultas. As 390 consultas das duas travessias batem com 2 + 193 por ordem.

## O que ficou fora, e por quê

- **Seção 05 do contrato** (acesso compartilhado e solicitações): congelada pelo cliente.
- **Cadastro e troca de senha de administrador pela API:** a proposta (item 2.4) não contratou. Isso é feito por `scripts/criar_admin.py` e `scripts/trocar_senha_admin.py`, e a troca derruba as sessões abertas.
- **Upload de imagem:** nesta fase as imagens entram por URL (seção 4.2). A rota fica a mesma quando houver hospedagem de arquivo.
- **CRUD de coleções:** são duas fixas, e o contrato não tem rota para elas.
- **Cronometragem do login:** não há teste automatizado de tempo, porque o ruído da máquina é maior que qualquer limiar honesto. O teste prova a causa: o argon2 roda nos três casos de falha.

## Pendências conhecidas

Detalhe, motivo e quem decide estão em `docs/pendencias.md`.

1. O contrato v1.0 não está versionado no repositório. É daí que vem a incerteza da auditoria.
2. Três rotas de produto fora do contrato esperam uma revisão v1.1.
3. A seção 05 segue congelada, e a decisão é do cliente.
4. A abertura do `README.md` ainda descreve a Fatia 0.
5. A suíte emite cerca de 230 avisos de dependência (pydantic 2.13 com FastAPI 0.115).

## Scripts que ficaram em `scripts/`

`gerar_massa.py`, `travessia_catalogo.py`, `contar_consultas.py`, `explicar_consulta.py`, `auditoria_contrato.py`, `criar_admin.py` e `trocar_senha_admin.py`, mais `_entrada_admin.py`, que é a leitura de terminal compartilhada pelos dois comandos de admin. Os roteiros `verificar_fatia3.py`, `verificar_fatia4.py` e `verificar_admin_produtos.py` saíram, porque o que provavam agora está na suíte.
