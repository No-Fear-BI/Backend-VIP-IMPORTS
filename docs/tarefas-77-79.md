# Tarefas 77, 78 e 79: fechamento do backend

Estado em 15/09/2026, branch `feat/publicacao-backend`. As três tarefas de backend da Fatia 6 estão entregues até onde dá sem o catálogo real. A 77 fica com o roteiro pronto e com uma medição contra massa sintética. O que falta está em `pendencias.md`.

**Suíte:** 257 testes (251 passam, 6 pulados com o motivo no relatório). Nenhum aviso: aviso novo agora é erro.

## Tarefa 78: nada técnico vaza na resposta de erro

`testes/teste_vazamento_erros.py` não tem lista de rotas. Ele lê o roteador e, em cada uma das 56 rotas, força os erros que dá para provocar de fora:

- sem sessão;
- id inexistente, e id grande demais para o `integer` do banco;
- tipo errado no caminho e na query;
- corpo que não é JSON, corpo que não é objeto, e tipo errado em todos os campos;
- cinco cursores corrompidos.

O corpo inteiro de cada resposta com status >= 400 é conferido contra:

- os nomes de tabela lidos de `Base.metadata`;
- `Traceback`, `File "`, `.py`, `sqlalchemy`, `psycopg` e `asyncpg`;
- o caminho do projeto no disco.

- **Resultado:** 50 rotas conferidas sem vazamento. As outras 6 não têm erro provocável de fora (`/health`, `/home`, `/marcas`, `/colecoes`, `POST /clientes/sair` e `DELETE /admin/sessao`) e aparecem como puladas, com o nome.
- **Nomes de tabela que são palavras comuns** (`produtos`, `marcas`, `clientes`) só contam na forma em que um vazamento aparece: depois de FROM, JOIN, INTO ou `relation`; entre aspas; qualificados (`produtos.id`); ou dentro de um identificador. Sem essa regra, "Adicione produtos antes de enviar", que é a mensagem certa, reprovaria. Nomes com sublinhado contam em qualquer lugar.
- **Prova:** com o manipulador de 500 sabotado para devolver `str(exc)`, o teste reprovou 15 rotas, com a tabela e o trecho SQL de cada uma. Depois de desfazer, voltou a passar.
- **Achados:**
  - Cursor com JSON válido e tipo errado (`"id": "abc"`) dava 500 no catálogo e no histórico de seleções. Corrigido (`exigir_formato_do_cursor`) e coberto por `teste_cursor_corrompido.py`.
  - Id maior que o `integer` do banco dá 500 genérico, sem vazar nada. Ficou como pendência, porque corrigir muda o status que o frontend recebe.

## Tarefa 79: proteção do painel

A varredura (`teste_protecao_admin.py`) cobre tudo sob `/api/v1/admin`. O buraco era uma rota de escrita pendurada fora desse prefixo. `teste_escrita_fora_do_painel.py` exige que todo POST, PATCH, PUT e DELETE fora do painel esteja declarado, com o motivo:

| Método | Rota | Por que é pública |
|---|---|---|
| POST | `/api/v1/clientes/identificar` | identificação por e-mail, sem senha (tarefa 40) |
| PATCH | `/api/v1/clientes/eu` | o cliente edita o próprio nome e telefone (seção 03) |
| POST | `/api/v1/clientes/sair` | encerra a própria sessão |
| POST, DELETE | `/api/v1/favoritos`, `/api/v1/favoritos/{produtoId}` | favoritos do próprio cliente |
| POST, PATCH, DELETE | `/api/v1/carrinho`, `/api/v1/carrinho/{itemId}` | carrinho do próprio cliente |
| POST | `/api/v1/carrinho/migrar` | carrinho anônimo para a conta (tarefa 47) |
| POST | `/api/v1/selecoes` | envio da seleção para o WhatsApp (tarefa 44) |

Para provar, pendurei um `PATCH /api/v1/produtos/{codigo}/preco` no roteador público: o teste reprovou nomeando a rota. Depois de desfazer, voltou a passar.

**Varredura completa** (sem cookie, com cookie de cliente, com cookie de admin):

```
  MÉTODO               ROTA                                                 sem cookie  cliente   admin
  GET                  /api/v1/admin/banners                                       401      403     200
  POST                 /api/v1/admin/banners                                       401      403     400
  PATCH                /api/v1/admin/banners/ordem                                 401      403     400
  DELETE               /api/v1/admin/banners/{bannerId}                            401      403     404
  PATCH                /api/v1/admin/banners/{bannerId}                            401      403     404
  GET                  /api/v1/admin/categorias                                    401      403     200
  POST                 /api/v1/admin/categorias                                    401      403     400
  DELETE               /api/v1/admin/categorias/{categoriaId}                      401      403     404
  PATCH                /api/v1/admin/categorias/{categoriaId}                      401      403     404
  GET                  /api/v1/admin/clientes                                      401      403     200
  PATCH                /api/v1/admin/destaques/categorias                          401      403     200
  PATCH                /api/v1/admin/destaques/produtos                            401      403     200
  GET                  /api/v1/admin/eu                                            401      403     200
  DELETE               /api/v1/admin/imagens/{imagemId}                            401      403     404
  GET                  /api/v1/admin/marcas                                        401      403     200
  POST                 /api/v1/admin/marcas                                        401      403     400
  DELETE               /api/v1/admin/marcas/{marcaId}                              401      403     404
  PATCH                /api/v1/admin/marcas/{marcaId}                              401      403     404
  GET                  /api/v1/admin/produtos                                      401      403     200
  POST                 /api/v1/admin/produtos                                      401      403     400
  PATCH                /api/v1/admin/produtos/lote                                 401      403     400
  DELETE               /api/v1/admin/produtos/{produtoId}                          401      403     404
  GET                  /api/v1/admin/produtos/{produtoId}                          401      403     404
  PATCH                /api/v1/admin/produtos/{produtoId}                          401      403     404
  POST                 /api/v1/admin/produtos/{produtoId}/duplicar                 401      403     404
  POST                 /api/v1/admin/produtos/{produtoId}/imagens                  401      403     400
  PATCH                /api/v1/admin/produtos/{produtoId}/imagens/ordem            401      403     400
  PATCH                /api/v1/admin/produtos/{produtoId}/variacoes                401      403     400
  GET                  /api/v1/admin/resumo                                        401      403     200
  GET                  /api/v1/admin/selecoes                                      401      403     200
  GET                  /api/v1/admin/selecoes/{selecaoId}                          401      403     404
  DELETE (exceção)     /api/v1/admin/sessao                                        200      200     200
  POST (exceção)       /api/v1/admin/sessao                                        400      400     400

  33 entradas, 2 exceções declaradas
```

As 31 rotas protegidas recusam sem cookie (401) e com cookie de cliente (403). O 400 e o 404 com cookie de admin são a validação e o id inexistente: a requisição passou da porta. As duas exceções são login e logout.

## Tarefa 77: desempenho com o volume do catálogo real

Os 11.569 produtos reais só chegam com a carga da Fatia 5. Hoje foram feitas duas coisas.

**Massa torta.** O `gerar_massa.py` agora gera 11.569 produtos:

- Chanel com 3.400, Louis Vuitton com 2.800 e Gucci com 1.945, e a cauda descendo até Goyard com 19;
- metade em bolsas;
- "bolsa" em 5.795 nomes e "preta" em 4.161;
- 1.386 sem imagem e 2.254 sem descrição;
- 6.332 com o mesmo `criado_em`, o instante da carga.

**Roteiro pronto.** `scripts/medir_desempenho.py` percorre o catálogo nas duas ordenações e mede 19 rotas. Sai com código 1 se algum limiar estourar. Limiares, com a justificativa no arquivo:

- nenhuma consulta SQL acima de 500 ms (a referência do plano);
- p95 de até 300 ms nas rotas públicas;
- p95 de até 500 ms na busca por termo comum e no painel;
- teto de consultas por requisição igual ao medido hoje, para detectar N+1.

**Medição.** A mesma máquina de desenvolvimento, lado a lado: 4.997 produtos uniformes (ANTES) contra 11.569 tortos (DEPOIS). Tempos em ms. SQL é a soma das consultas da requisição (mediana). As consultas do painel incluem a de sessão do admin.

| Medição | Consultas | p50 antes → depois | p95 antes → depois | SQL antes → depois |
|---|---|---|---|---|
| travessia `recentes` (por página) | 1 | 9,0 → 8,8 | 30,1 → 30,4 | 2,0 → 1,9 |
| travessia `nome` (por página) | 1 | 9,2 → 9,0 | 30,4 → 29,5 | 2,2 → 2,0 |
| produtos: 1ª página | 2 | 10,2 → 10,2 | 27,5 → 28,1 | 3,0 → 3,2 |
| produtos: maior marca | 3 | 11,1 → 11,1 | 26,9 → 27,3 | 3,4 → 3,4 |
| produtos: menor marca, por nome | 3 | 12,1 → 10,9 | 14,4 → 27,9 | 3,7 → 3,3 |
| produtos: categoria mais cheia | 4 | 11,6 → 11,5 | 24,1 → 28,2 | 4,0 → 4,1 |
| **produtos: busca 'bolsa'** | 4 | 13,3 → 16,0 | 14,5 → 32,4 | **4,9 → 7,0** |
| **produtos: busca 'preta'** | 4 | 14,6 → 15,0 | 32,7 → 16,5 | **4,8 → 6,3** |
| produtos: busca por código | 1 | 8,2 → 8,2 | 29,9 → 31,6 | 1,7 → 1,7 |
| produto: detalhe | 3 | 8,6 → 9,3 | 29,4 → 30,0 | 2,8 → 3,0 |
| produto: relacionados | 2 | 25,8 → 12,7 | 28,1 → 31,4 | 3,5 → 5,8 |
| marcas | 1 | 7,5 → 8,1 | 31,1 → 26,3 | 2,4 → 3,0 |
| categorias da coleção | 2 | 7,7 → 8,1 | 29,0 → 27,0 | 2,4 → 3,0 |
| **home** | 4 | 12,2 → 17,5 | 27,3 → 26,4 | **5,3 → 9,9** |
| painel: produtos 1ª página | 3 (1) | 15,1 → 16,8 | 31,5 → 37,9 | 6,0 → 7,6 |
| painel: produtos busca 'bolsa' | 3 (1) | 15,9 → 17,7 | 31,0 → 35,8 | 6,1 → 8,3 |
| painel: produtos da maior marca | 3 (1) | 14,8 → 16,1 | 24,6 → 32,4 | 5,6 → 6,7 |
| **painel: produtos última página** | 3 (1) | 16,9 → 19,2 | 23,4 → 36,1 | **7,3 → 10,7** |
| **painel: resumo** | 4 (1) | 11,7 → 14,9 | 27,0 → 39,0 | **5,0 → 7,6** |
| painel: seleções | 4 (1) | 17,6 → 17,4 | 36,6 → 41,0 | 4,0 → 3,8 |
| painel: clientes | 3 (1) | 9,5 → 9,5 | 27,0 → 28,3 | 2,6 → 2,7 |

Todas as 21 medições ficaram dentro dos limiares, com folga de mais de 7 vezes no p95. Nenhuma contagem de consultas mudou com o volume, então não há N+1.

- **Onde não mudou nada:** a paginação por cursor e o detalhe. A travessia por página e a 1ª página ficaram iguais com mais que o dobro de produtos, que é o esperado de keyset sobre índice.
- **O que piorou.** São essas as consultas que vão doer depois da carga, porque crescem com o catálogo, e não com a página:
  - **COUNT da busca por termo comum.** Com "bolsa" em metade dos nomes, o bitmap do índice trigram visita 5.334 linhas. O EXPLAIN foi de 0,6 ms para 4,2 ms (quase 7 vezes), contra 2,3 vezes mais produtos. É a consulta mais sensível à distribuição, e a uniforme escondia isso.
  - **Contagem de produtos por marca, a cada `GET /home` e `GET /marcas`.** Varre todos os visíveis pelo índice. O EXPLAIN foi de 1,3 ms para 3,2 ms, linear. A home também passou de 2 para 12 destaques, o que soma no SQL dela.
  - **Última página do painel (OFFSET).** 7,3 ms para 10,7 ms de SQL, linear no deslocamento.
  - **Resumo do painel.** COUNTs sobre a tabela inteira, de 5,0 ms para 7,6 ms.
- **Ressalva:** os números são de um notebook com o PostgreSQL no Docker. O p95 de ~30 ms é ruído da máquina, repare que ele não acompanha o p50. O que vale é rodar o roteiro no servidor no dia seguinte à carga, com `--comparar` contra uma medição salva antes dela.

## Limpeza de sessões

`scripts/limpar_sessoes.py` apaga as sessões de cliente e de admin que estão expiradas ou revogadas há mais de 30 dias (ajustável com `--carencia-dias`, e `--simular` só conta). Imprime o antes, o depois e quantas saíram de cada tabela. Está coberto por `teste_limpar_sessoes.py`, e o agendamento por cron está no README. O `Dockerfile` passou a copiar `scripts/` para a imagem, para os comandos rodarem dentro do container.

## Pendências do fechamento anterior

- **Contrato: RESOLVIDA em 15/09/2026.** O documento v1.0 (`docs/contrato-api-v1.pdf`) apareceu. `docs/contrato-api-v1.json` deixou de ser a reconstrução e virou a extração direta dele: 58 entradas (52 a implementar, 6 congeladas), `"origem": "documento"` e o handler previsto em cada uma. A auditoria agora sai com **código 0**. A extração corrigiu dois enganos da reconstrução: `POST /carrinho/migrar` estava marcada como fora do contrato — sempre esteve nele (seção 03, `migrarCarrinhoAnonimo`), só o formato do corpo não estava definido; e os seis caminhos da seção 05 eram outros (`GET /acesso/estado`, `POST /acesso/senha`, `POST /acesso/solicitar`, `GET /admin/acesso/fila`, `PATCH /admin/acesso/{clienteId}`, `PATCH /admin/configuracao/acesso`). Com isso, rotas fora do contrato caem de 4 para 3: `GET /admin/eu`, `GET /health`, `PATCH /admin/banners/ordem`. O script passou a mostrar o nome do handler REAL ao lado do PREVISTO no contrato — divergem em quase todas as 52 rotas porque o contrato foi escrito para Node e o handler é Python (nome curto por módulo, não o nome do recurso inteiro); isso é informação, não falha.
- **Avisos:** os conhecidos estão listados por nome no `pyproject.toml`, e qualquer outro é erro. No primeiro dia a regra já pegou um aviso real: um `ResourceWarning` do `conftest.py`, que abria o `.env` sem fechar. Foi corrigido.
- **README:** a abertura agora descreve o estado atual.
