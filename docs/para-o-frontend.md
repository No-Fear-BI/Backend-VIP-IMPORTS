# Para o frontend

O backend agora é FastAPI (Python), tudo sob o prefixo `/api/v1`, como o contrato já previa.

`packages/tipos` deixa de ser mantido à mão: a API expõe seu próprio OpenAPI em `/api/v1/openapi.json`, e os tipos TypeScript são **gerados automaticamente** a partir dele. Dev 2 roda, na raiz do frontend:

```
npx openapi-typescript http://localhost:8000/api/v1/openapi.json -o packages/tipos/api.ts
```

Formato de resposta, envelope de erro (`erro.codigo`/`erro.mensagem`/`erro.campos`), envelope de paginação (`dados`/`paginacao`) e os nomes de campo do contrato v1.0 continuam iguais. As poucas diferenças estão listadas abaixo.

## Mudanças desde o contrato v1.0

- **Código de erro novo: `DADOS_INVALIDOS`.** É o `erro.codigo` de qualquer falha de validação de corpo ou query (o contrato só previa códigos de domínio). O detalhe por campo vem em `erro.campos`, como sempre.
- **Código de erro novo: `COLECAO_NAO_ENCONTRADA`.** `GET /colecoes/:slug/categorias` com slug inexistente devolve 404 com esse código. Antes cairia em `CATEGORIA_NAO_ENCONTRADA`, que faria a tela mostrar a mensagem errada.
- **O identificador de rastreio do erro 500 vai no cabeçalho `X-Rastreio`, não em `erro.campos`.** `campos` é só de validação — cada chave dele é renderizada como erro embaixo de um input, e "rastreio" viraria um erro de campo que não existe na tela. Ao reportar um 500, mande o valor de `X-Rastreio`: ele acha a exceção no log.
- **`GET /produtos/:codigo` não devolve `capa`.** É redundante com `imagens`, que vem completo e ordenado no detalhe. `destaque` continua presente, como a interface `Produto` da seção 07 declara.
- **`POST /clientes/identificar` responde sempre 200**, inclusive quando a conta é criada naquele momento. A rota existe para abrir sessão, não para criar registro — não ramifique por status: conta nova e conta existente levam à mesma tela.
- **Nenhuma rota devolve 204.** `POST /clientes/sair`, `POST /favoritos` e `DELETE /favoritos/:produtoId` respondem **200 com `{"ok": true}`**, seguindo a tabela da seção 1.4 do contrato, que lista 200 para atualização e exclusão bem-sucedidas. Assim `api/cliente.ts` pode desempacotar JSON em toda resposta de sucesso, sem tratar o caso sem corpo. `POST /favoritos` também não devolve 201: favoritar duas vezes não cria nada, e a resposta é a mesma nos dois casos.
- **O item do carrinho tem DUAS variações: `variacaoTamanhoId` e `variacaoCorId`.** Não existe mais `variacaoId`. A página do produto tem seletor de tamanho **e** de cor, e os dois entram no mesmo item — é o que faz a seleção sair como "(Chanel, M / Preto)". Cada um é opcional: produto só com tamanho, só com cor ou sem variação nenhuma manda só o que tiver. O banco recusa tamanho no campo de cor e vice-versa, então não inverta os dois campos.

  `POST /carrinho` — adiciona um item:

  ```json
  { "produtoId": 812, "variacaoTamanhoId": 315, "variacaoCorId": 318 }
  ```

  `PATCH /carrinho/:itemId` — **troca o par inteiro**, não um campo só. O tipo que não vier no corpo fica nulo, então mande sempre os dois seletores, mesmo quando só um mudou:

  ```json
  { "variacaoTamanhoId": 315, "variacaoCorId": 318 }
  ```

  Se a troca cair em cima de um item que já existe (mesmo produto, mesmo par), os dois viram um: o item alterado some e fica o que já estava lá. O `itemId` que some é o do PATCH — recarregue a lista com o `GET /carrinho` da resposta seguinte em vez de guardar o id.

  `POST /carrinho/migrar` — **formato novo, não estava no contrato v1.0.** É como o carrinho do `localStorage` (visitante não identificado) entra na conta logo após a identificação:

  ```json
  {
    "itens": [
      { "produtoId": 812, "variacaoTamanhoId": 315, "variacaoCorId": 318 },
      { "produtoId": 812, "variacaoTamanhoId": 315 },
      { "produtoId": 930 }
    ]
  }
  ```

  A resposta traz `itens` (o carrinho final da conta) e `ignorados` — os que não puderam migrar, cada um com `produtoId`, `variacaoTamanhoId`, `variacaoCorId`, `motivo` (`PRODUTO_INDISPONIVEL`, `PRODUTO_NAO_ENCONTRADO` ou `VARIACAO_INVALIDA`) e `mensagem` pronta para exibir. Mostre esses ignorados ("2 itens não estão mais disponíveis") em vez de sumir com eles em silêncio. Produto já na conta com o **mesmo par** não duplica; com par diferente vira um segundo item.
- **Na resposta, `variacao` deu lugar a `variacaoTamanho` e `variacaoCor`.** Cada um é o objeto de sempre (`id`, `tipo`, `valor`, `disponivel`) ou `null` — separados, e não numa lista, para o seletor de cor ler `variacaoCor` direto, sem procurar por `tipo` dentro de um array.
- **O carrinho NÃO tem quantidade.** O mesmo produto com pares de variação diferentes são itens diferentes; o mesmo produto com o mesmo par é um item só. Adicionar duas vezes o mesmo par não é erro, é sem efeito — inclusive "produto sem variação nenhuma", que também não entra duas vezes.
- **O item do carrinho tem `itemId` além de `id`.** `id` é o produto (para link e imagem); `itemId` é a linha do carrinho, e é ele que vai em `PATCH /carrinho/:itemId` e `DELETE /carrinho/:itemId`.
- **`POST /selecoes` NÃO esvazia o carrinho.** Se a pessoa abrir o link do WhatsApp e fechar sem mandar a mensagem, esvaziar teria destruído a seleção dela. Se a tela quiser oferecer "limpar seleção", é um botão que chama `DELETE /carrinho/:itemId` item a item — o backend não faz isso sozinho.
- **Em `POST /selecoes` e `GET /selecoes`, `variacao` é um rótulo pronto para exibir.** Vem composto das duas variações congeladas no envio: `"M / Preto"` com as duas, `"M"` ou `"Preto"` com uma só, `null` sem nenhuma. É o mesmo texto que aparece na mensagem do WhatsApp — não monte esse rótulo na tela.
- **`linkWhatsapp` vem pronto do backend.** Não monte o link no frontend e não guarde o número da loja lá: ele vive só na configuração do servidor. O texto já vai percent-encoded; basta abrir a URL.
- **Códigos de erro novos:** `CARRINHO_VAZIO` (400, `POST /selecoes` sem itens), `ITEM_NAO_ENCONTRADO` (404, item do carrinho inexistente **ou de outro cliente** — a API não distingue os dois casos de propósito), `CREDENCIAIS_INVALIDAS` (401, login do painel recusado — e-mail, senha ou conta desativada, sem distinguir qual) e `VARIACAO_INVALIDA` (400, variação que não pertence ao produto **ou que não é do tipo do campo** — cor mandada em `variacaoTamanhoId`, por exemplo; `erro.campos` diz qual dos dois campos recusou).

## Painel administrativo — acesso (fatia 4)

- **O painel tem sessão PRÓPRIA, cookie próprio e prazo próprio.** O cookie é `vip_sessao_admin`, sem nenhuma relação com o `vip_sessao_cliente` da loja: os dois convivem no mesmo navegador, e estar logado em um não muda nada no outro. Nenhum token de cliente abre o painel.
- **`POST /api/v1/admin/sessao`** — login. Corpo:

  ```json
  { "email": "painel@nofear.com.br", "senha": "..." }
  ```

  200 devolve o administrador (`id`, `nome`, `email`, `ultimoLoginEm`, `criadoEm`) e grava o cookie. **`ultimoLoginEm` é campo novo, não previsto no contrato v1.0**: é o instante DESTE login, gravado quando a sessão abre — não o login anterior. `GET /admin/eu` devolve o mesmo valor enquanto a sessão durar, então ele serve para a tela mostrar "sessão iniciada em ...". É nulo só para conta que nunca entrou, o que nenhuma destas duas respostas alcança. Falha devolve **401 com `CREDENCIAIS_INVALIDAS`** — e é sempre a MESMA resposta para e-mail que não existe, senha errada e conta desativada. Não tente distinguir os três na tela: o backend não distingue de propósito, inclusive no tempo de resposta. Mostre uma mensagem só: "E-mail ou senha inválidos."
- **`DELETE /api/v1/admin/sessao`** — sair. Responde `200 {"ok": true}`, revoga a sessão no banco e limpa o cookie. Funciona mesmo com a sessão já expirada.
- **`GET /api/v1/admin/eu` — rota NOVA, não existe no contrato v1.0.** É a rota que o painel chama ao abrir para saber se a sessão ainda vale. 200 com o administrador; **401** (`NAO_IDENTIFICADO`) quando não há sessão de admin — mande para a tela de login; **403** (`SEM_PERMISSAO`) quando quem bate está logado como CLIENTE — aí não adianta mandar para o login do painel, essa conta não tem senha de admin.
- **A sessão do painel dura 12 horas e NÃO renova com o uso.** Ao contrário da sessão do cliente, que se estende sozinha, aqui o relógio corre desde o login: passadas as 12 horas, qualquer chamada volta 401 e é login de novo. Trate 401 em qualquer rota do painel como "sessão acabou", não como erro da tela.
- **Código de erro novo: `CREDENCIAIS_INVALIDAS`** (401). Só o login do painel devolve. Um código só para os três casos — e-mail que não existe, senha errada e conta desativada — porque códigos diferentes diriam quais e-mails são de administrador.
- **Limite de 5 logins por minuto por IP**, com **429** e `EXCESSO_TENTATIVAS` — contagem separada da identificação do cliente, então estourar um não bloqueia o outro.
- **Não existe rota de cadastro nem de troca de senha de administrador.** As contas são criadas e têm a senha trocada por comando de linha no servidor (`scripts/criar_admin.py` e `scripts/trocar_senha_admin.py`). Trocar a senha derruba as sessões abertas daquele administrador na hora.

## Painel administrativo — produtos (tarefa 55)

Todas estas rotas exigem a sessão de admin: sem cookie é **401**, com cookie de cliente é **403**. Nenhuma delas é exceção — a única parte do painel que responde sem sessão é `POST`/`DELETE /admin/sessao`.

- **`GET /api/v1/admin/produtos`** — a listagem do painel. **Traz os produtos OCULTOS junto**, ao contrário de `GET /produtos`: é daqui que o admin reexibe o que escondeu. Filtros: `busca` (nome ou código, parcial), `marcaId`, `categoriaId`, `colecaoId`, `status` (`normal`, `esgotado` ou `oculto` — ausente traz tudo).

  **A paginação aqui é por página, não por cursor**: `?pagina=1&porPagina=50` (máximo 100). O envelope é o mesmo `{dados, paginacao}` de sempre, só que `paginacao` traz `pagina` em vez de `proximoCursor`:

  ```json
  { "dados": [ ... ], "paginacao": { "total": 5000, "porPagina": 50, "pagina": 1 } }
  ```

  Cada item traz `id`, `codigo`, `nome`, `status`, `destaque`, `marca`, `categoria`, `colecao`, `capa`, `criadoEm` e `atualizadoEm`.
- **`GET /api/v1/admin/produtos/:id`** — o produto para edição, **por id e não por código**: no painel o código é editável, e recarregar pelo código que acabou de mudar perde o produto no meio do formulário. Traz `imagens` (ordenadas) e `variacoes`, mais `marcaId`/`categoriaId`/`colecaoId` para os seletores do formulário.
- **`POST /api/v1/admin/produtos`** — cria; responde **201** com o produto.

  ```json
  { "nome": "Bolsa Clássica", "marcaId": 3, "categoriaId": 7, "status": "normal", "destaque": false }
  ```

  **`codigo` é opcional.** Sem ele, o backend gera no padrão da marca (`CHN-0042`): três letras da marca — as que a marca já usa nos códigos existentes — mais o próximo sequencial. Mandar um código já usado devolve **409 `CODIGO_EM_USO`**.
- **`PATCH /api/v1/admin/produtos/:id`** — edita. **Campo ausente não muda**; `null` em `descricao` apaga o valor. Trocar o código para um já existente devolve 409. Trocar `categoriaId` move a coleção junto.
- **`DELETE /api/v1/admin/produtos/:id`** — exclui. Some com as imagens, as variações, os favoritos e os itens de carrinho que apontavam para o produto. **As seleções já enviadas NÃO somem**: elas são histórico congelado e continuam mostrando código, nome, marca e variações como estavam no envio — só perdem o link para o produto.
- **`POST /api/v1/admin/produtos/:id/duplicar`** — responde **201** com a cópia: mesmas imagens (na mesma ordem) e variações, código novo, nome com `(cópia)` no fim. **A cópia nasce com status `oculto` e sem destaque, e isso é decisão de produto, não descuido**: duplicar é o primeiro passo de um cadastro que ainda vai ser editado, e uma gêmea publicada na hora apareceria na vitrine com o nome da original. Avise na tela — quem duplica e vai procurar a cópia no site não vai achar até mudar o status para `normal`.
- **`PATCH /api/v1/admin/produtos/lote`** — altera vários de uma vez. Aceita **exatamente quatro campos**, e qualquer outro é **400**: `status`, `destaque`, `marcaId`, `categoriaId`. Máximo de 100 ids por chamada.

  ```json
  { "ids": [12, 34, 56], "status": "oculto" }
  ```

  Responde `{"alterados": 3}`. **É tudo ou nada**: se algum id não existir mais, nada é alterado e a resposta é **404** com a lista dos ids problemáticos em `erro.detalhes.naoEncontrados` — use essa lista para marcar as linhas na tela e recarregar a listagem.

  ```json
  { "erro": { "codigo": "PRODUTO_NAO_ENCONTRADO", "mensagem": "...", "campos": { "ids": "..." }, "detalhes": { "naoEncontrados": [99] } } }
  ```

- **`erro.detalhes` é campo novo do envelope de erro**, e opcional: some quando não há nada a processar. `campos` continua sendo o texto que vai embaixo de cada input; `detalhes` é o que a tela precisa ler como dado, não exibir como frase.

## Painel administrativo — imagens e variações (tarefa 56)

Também sob sessão de admin: sem cookie 401, com cookie de cliente 403.

- **`POST /api/v1/admin/produtos/:id/imagens`** — acrescenta imagens **por URL**, não por upload (é o que a seção 4.2 define para esta fase; a rota continua a mesma quando passarmos a hospedar arquivo). Corpo:

  ```json
  { "imagens": [ { "url": "https://cdn.exemplo.com/a.jpg", "alt": "frente" }, { "url": "https://cdn.exemplo.com/b.jpg" } ] }
  ```

  **Só `https`** — imagem em `http` dentro de uma página `https` é bloqueada pelo navegador como conteúdo misto e o produto aparece sem foto. Máximo de **10 imagens por produto**. As novas entram **no fim** da ordem, então acrescentar foto nunca troca a capa. Responde **201** com a galeria inteira já renumerada.
- **`PATCH /api/v1/admin/produtos/:id/imagens/ordem`** — recebe a lista COMPLETA de ids na ordem desejada: `{ "ids": [12, 10, 11] }`. Lista parcial ou com imagem de outro produto é **400** — reordenar metade deixaria a outra metade com ordem duplicada. Responde com a galeria na ordem nova.
- **`DELETE /api/v1/admin/imagens/:id`** — apaga uma imagem (sem o produto na URL, como o contrato define) e responde com as imagens que sobraram.
- **A ordem é sempre 1..N contígua, e a imagem de ordem 1 é a CAPA** — a que aparece na grade do site. Apagar a capa promove a seguinte automaticamente; apagar do meio fecha o buraco. Como as três rotas devolvem a galeria já acertada, a tela não precisa recalcular nada nem recarregar o produto.
- **`PATCH /api/v1/admin/produtos/:id/variacoes`** — **SUBSTITUI o conjunto inteiro**. O que não vier na lista sai; lista vazia remove todas.

  ```json
  { "variacoes": [ { "tipo": "tamanho", "valor": "M" }, { "tipo": "cor", "valor": "Preto", "disponivel": false } ] }
  ```

  Só os tipos `tamanho` e `cor`. Valor repetido **dentro do mesmo tipo** é 400 (o mesmo valor em tipos diferentes é aceito: tamanho "Único" e cor "Único" são coisas distintas). `disponivel` é opcional e vale `true`.

  **O que permanece mantém o `id`**: uma variação com o mesmo tipo e o mesmo valor não é recriada, é reaproveitada — é isso que preserva a escolha de quem já tinha aquele tamanho no carrinho. Mande sempre a grade completa, inclusive o que não mudou.

  Quando uma variação sai, os itens de carrinho que a usavam perdem aquela escolha; se o cliente ficar com dois itens iguais do mesmo produto, eles viram um só. Nada disso devolve erro — é a API acertando o carrinho, e a tela do cliente vê o resultado no próximo `GET /carrinho`.

## Painel administrativo — marcas, categorias e banners (tarefa 57)

- **`GET` / `POST /api/v1/admin/marcas`, `PATCH` / `DELETE /api/v1/admin/marcas/:id`.** A listagem traz `totalProdutos` por marca (contando os ocultos, é o painel) — mostre esse número na tela ANTES do botão de excluir.

  **O slug nasce do nome na criação e não muda sozinho depois.** Editar o nome de "chanel" para "Chanel" NÃO troca o slug: a URL `/marcas/chanel` já foi compartilhada e indexada. Para trocar o slug, mande o campo `slug` no corpo — aí é decisão consciente, e a tela deveria avisar que links antigos param de funcionar. Slug informado que já existe é **409 `SLUG_EM_USO`**; slug gerado que colide ganha sufixo (`prada-2`) em vez de erro.
- **`GET` / `POST /api/v1/admin/categorias`, `PATCH` / `DELETE /api/v1/admin/categorias/:id`.** Aceita `?colecaoId=` na listagem. Cada categoria traz `colecaoId`, `colecaoSlug` e `totalProdutos`.

  **O slug é único POR COLEÇÃO, não global**: "bolsas" existe em Feminino e em Masculino e são categorias diferentes. Repetir dentro da MESMA coleção é 409; na outra é normal. Por isso o link público precisa das duas coisas: `?colecao=feminino&categoria=bolsas`.

  **Trocar a coleção de uma categoria que já tem produtos é recusado com 409** (`CATEGORIA_COM_PRODUTOS`), e a mensagem diz o caminho: criar a categoria na coleção certa e mover os produtos com `PATCH /admin/produtos/lote`, que move a coleção junto. Categoria sem produto troca de coleção normalmente.
- **Excluir marca ou categoria com produtos é 409**, com a contagem na mensagem ("Não é possível excluir: 643 produtos usam esta marca.") e o número em `erro.detalhes.totalProdutos`. Sem produtos, exclui normalmente — o 409 não é um "não" permanente.
- **Não existe CRUD de coleções.** São duas, fixas (Feminina e Masculina), e o contrato não tem rota para elas. Use `GET /colecoes` para preencher o seletor.
- **`GET` / `POST /api/v1/admin/banners`, `PATCH` / `DELETE /api/v1/admin/banners/:id`, `PATCH /api/v1/admin/banners/ordem`.** Campos: `imagemUrl` (https, obrigatória), `imagemUrlMobile`, `titulo`, `subtitulo`, `alt`, `linkUrl`, `ordem` e `ativo`.

  **No máximo 4 banners ATIVOS** — é o carrossel contratado (proposta, item 2.1). A quinta ativação devolve **400** dizendo o limite, seja no `POST` com `ativo: true`, seja no `PATCH`. Banner **inativo não tem teto**: é rascunho e pode existir aos montes. Reenviar `ativo: true` num banner que já está ativo não conta como nova ativação, então a tela pode mandar o formulário inteiro sem medo.

  A ordem é 1..N contígua, como nas imagens do produto: `PATCH /admin/banners/ordem` recebe a lista COMPLETA de ids e o `DELETE` renumera o que sobrou. `GET /home` devolve só os ativos, nessa ordem.

## Painel administrativo — destaques e consultas (tarefas 58 e 60)

- **`PATCH /api/v1/admin/destaques/produtos`** e **`PATCH /api/v1/admin/destaques/categorias`** — recebem a lista COMPLETA de ids na ordem em que devem aparecer na home: `{ "ids": [812, 44, 930] }`. **Substituem o conjunto**: quem está na lista vira destaque com a ordem da posição, quem não está deixa de ser. Lista vazia tira todos. Respondem com os ids na ordem gravada.

  **Produto `oculto` é recusado com 400**, e os ids problemáticos vêm em `erro.detalhes.ocultos` — marque-os na tela em vez de mostrar um erro genérico: o produto oculto some da home inteira, então aceitar a marcação seria deixar o cliente marcar e não ver nada. Categoria inativa é recusada pelo mesmo motivo, com `erro.detalhes.inativas`.

  **Teto: 12 produtos e 8 categorias.** O dos produtos é exatamente o que a home renderiza — marcar mais do que ela mostra é marcar o que ninguém vai ver.
- **`GET /api/v1/admin/resumo`** — os números da tela inicial: `totalProdutos`, `produtosEsgotados`, `produtosOcultos`, `porMarca` (lista com `marcaId`, `nome`, `slug` e `total`, incluindo marca com zero), `selecoesNoMes` e `totalClientes`.
- **`GET /api/v1/admin/selecoes`** — as seleções recebidas, mais recentes primeiro, com `?pagina=` e `?porPagina=` no envelope `{dados, paginacao}` de sempre. Cada seleção traz `criadoEm`, `totalItens`, o `cliente` (id, nome, e-mail e telefone, todos congelados no envio) e os `itens`.
- **`GET /api/v1/admin/selecoes/:id`** — o detalhe, com os mesmos itens.

  **Os itens são dado CONGELADO**: `codigo`, `nome`, `marca`, `categoria`, `colecao`, `imagemUrl` e `variacao` são cópias do que o cliente viu no envio, não um JOIN com o catálogo de hoje. Se o produto foi excluído depois, `produtoId` vem `null` e o resto continua igual — não esconda o item nem tente buscar o produto por esse id sem checar o nulo.
- **`GET /api/v1/admin/clientes`** — os clientes cadastrados, com `?busca=` (parte do e-mail ou do nome, ignorando caixa) e paginação. Cada um traz `totalSelecoes`, que é o número que diz quem vale a pena atender, mais `ultimoAcessoEm` e o **telefone** — aqui ele aparece porque é o painel, e é com ele que o atendimento responde.
