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
- **Criação devolve 201; o resto devolve 200. Nenhuma rota devolve 204.**
  Respondem **201** com o recurso criado: `POST /selecoes`, `POST /admin/produtos`, `POST /admin/produtos/:id/duplicar`, `POST /admin/produtos/:id/imagens`, `POST /admin/marcas`, `POST /admin/categorias` e `POST /admin/banners`. Todo o resto — inclusive `POST /clientes/identificar`, `POST /favoritos`, `POST /carrinho`, `POST /carrinho/migrar` e `POST /admin/sessao` — responde **200**: são rotas que abrem sessão ou registram uma ação, não que criam um recurso novo para a tela navegar até ele.
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

  `POST /carrinho/migrar` — **a rota está no contrato v1.0** (seção 03, `migrarCarrinhoAnonimo`); o que não estava definido era o FORMATO DO CORPO da requisição. É como o carrinho do `localStorage` (visitante não identificado) entra na conta logo após a identificação:

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
- **`POST /api/v1/admin/produtos/:id/imagens/upload`** — upload de arquivo (revisão upload de imagem). `multipart/form-data`: campo `arquivo` (o arquivo) e `alt` opcional (texto, até 200 caracteres). **Não acrescenta a imagem à galeria sozinho** — processa (decodifica de verdade com Pillow, não confia em extensão/Content-Type; redimensiona pro tamanho grande do catálogo; converte pra WebP), grava em disco e responde **201** com `{ "url": "...", "alt": "..." }` — a MESMA forma de um item de `imagens` do endpoint acima. A tela chama esse endpoint pra obter a URL e depois manda o `POST /imagens` de sempre com ela, como faria com uma URL digitada à mão; as duas etapas ficam separadas de propósito, pra não duplicar a regra de limite/ordem/capa numa segunda rota. 400 `DADOS_INVALIDOS` (campo `arquivo`) se o arquivo não abrir como imagem ou passar do tamanho máximo (15 MB); 404 se o produto não existe.
- **`PATCH /api/v1/admin/produtos/:id/imagens/ordem`** — recebe a lista COMPLETA de ids na ordem desejada: `{ "ids": [12, 10, 11] }`. Lista parcial ou com imagem de outro produto é **400** — reordenar metade deixaria a outra metade com ordem duplicada. Responde com a galeria na ordem nova.
- **`DELETE /api/v1/admin/imagens/:id`** — apaga uma imagem (sem o produto na URL, como o contrato define) e responde com as imagens que sobraram.
- **A ordem é sempre 1..N contígua, e a imagem de ordem 1 é a CAPA** — a que aparece na grade do site. Apagar a capa promove a seguinte automaticamente; apagar do meio fecha o buraco. Como as três rotas devolvem a galeria já acertada, a tela não precisa recalcular nada nem recarregar o produto.
- **`PATCH /api/v1/admin/produtos/:id/variacoes`** — **SUBSTITUI o conjunto inteiro**. O que não vier na lista sai; lista vazia remove todas.

  ```json
  { "variacoes": [ { "tipo": "tamanho", "valor": "M" }, { "tipo": "cor", "valor": "Preto", "disponivel": false } ] }
  ```

  Só os tipos `tamanho` e `cor`. Valor repetido **dentro do mesmo tipo** é 400 (o mesmo valor em tipos diferentes é aceito: tamanho "Único" e cor "Único" são coisas distintas). `disponivel` é opcional e vale `true`.

  **Mande SEMPRE a grade inteira, carregada do produto.** Se a tela mandar só o tamanho que acabou de ser criado, todos os outros tamanhos e cores do produto somem — e junto com eles a escolha de quem já tinha aquela variação no carrinho, que fica com o campo vazio. Não existe "acrescentar uma variação": existe salvar a grade.

  **O que permanece mantém o `id`**: uma variação com o mesmo tipo e o mesmo valor não é recriada, é reaproveitada — é isso que preserva a escolha de quem já tinha aquele tamanho no carrinho. Mande sempre a grade completa, inclusive o que não mudou.

  Quando uma variação sai, os itens de carrinho que a usavam perdem aquela escolha; se o cliente ficar com dois itens iguais do mesmo produto, eles viram um só. Nada disso devolve erro — é a API acertando o carrinho, e a tela do cliente vê o resultado no próximo `GET /carrinho`.

## Cores: vocabulário no painel e filtro na vitrine (revisão 0007, 21/09/2026)

Estas rotas e parâmetros são posteriores ao contrato v1.0: estão em `docs/contrato-api-v1-adendo.json`, não no `contrato-api-v1.json` (que é a transcrição do PDF do cliente).

Cor deixou de ser texto solto dentro da variação e virou **tabela**. O que muda para o frontend:

- **`GET /api/v1/cores`** (público, sem sessão) — a paleta para montar o filtro. Só as cores **ativas**. Cada uma traz `id`, `nome`, `slug` e `totalProdutos` (contando só produto visível, como em `GET /marcas`). Cor recém-criada aparece com `totalProdutos: 0` — não some da lista por não ter produto ainda.
- **`GET /api/v1/produtos?cor=preto`** — o filtro da vitrine, **por slug**, e aceita vários separados por vírgula (`?cor=preto,bege`), com **OU** entre eles: traz quem tem preto OU bege, não quem tem os dois. Slug que não existe (ou cor inativa) devolve lista vazia com `total: 0`, e não erro — é filtro que não casa nada, igual a `?marca=`. Combina com todos os outros filtros.
- **`GET` / `POST /api/v1/admin/cores`, `PATCH` / `DELETE /api/v1/admin/cores/:id`** — o CRUD da paleta, irmão do de marcas. A listagem traz `totalProdutos` por cor (contando os ocultos, é o painel) — mostre esse número ANTES do botão de excluir. Campos: `nome` (obrigatório, até 60), `slug` (opcional, gerado do nome), `ordem` e `ativa`.

  **O slug nasce do nome e não muda sozinho**, pela mesma razão da marca: `?cor=preto` é link compartilhável. Para trocar, mande `slug` no corpo. Slug gerado que colide ganha sufixo (`bege-2`); slug informado que colide é **409 `SLUG_EM_USO`**.

  **Excluir cor em uso é 409 `COR_EM_USO`**, com a contagem em `erro.detalhes.totalProdutos`.

- **Renomear a cor reescreve o texto exibido em todas as variações que a usam.** É o que faz a correção valer para a loja inteira sem reabrir produto por produto. Há um caso que a API recusa: se algum produto já tiver OUTRA variação de cor com o nome novo, a troca colidiria na unicidade `(produto, tipo, valor)` — a resposta é **409 `COR_EM_CONFLITO`**, com `erro.detalhes.codigoProduto` dizendo qual produto trava. Mostre esse código e peça o ajuste na grade daquele produto; a API não apaga variação por conta própria, porque a que sumiria pode estar no carrinho de um cliente.

- **`PATCH /admin/produtos/:id/variacoes` ganhou `corId` na variação de cor**, e ele é **opcional**:

  ```json
  { "variacoes": [ { "tipo": "cor", "valor": "Preto", "corId": 3 }, { "tipo": "tamanho", "valor": "M" } ] }
  ```

  Mandando `corId`, **o nome exibido passa a ser o nome da cor no vocabulário** — o `valor` enviado é ignorado. É o caminho do painel, onde a cor é escolhida numa lista. Sem `corId`, a cor é resolvida pelo **slug do texto**: "Preto", "preto" e "PRETO" caem todos na mesma cor, e se nenhuma casar, **a cor é criada ali**. Isso mantém funcionando o importador de planilha, que não tem id nenhum — mas na tela prefira o seletor, porque pelo caminho de texto um erro de digitação vira cor nova na paleta. `corId` em variação de `tipo: "tamanho"` é **400**; `corId` inexistente é **404 `COR_NAO_ENCONTRADA`**.

- **A leitura do painel devolve o `corId` de cada variação**, em `GET /admin/produtos/:id` (`variacoes`) e na resposta do próprio `PATCH …/variacoes`. Em tamanho ele vem `null`. É daqui que a tela tira o id para reenviar a grade: como o PATCH substitui o conjunto inteiro, as cores que o produto já tem voltam também, e **precisam voltar com `corId`**. Pelo texto não serve: renomear "Preto" para "Preto Ônix" mantém o slug `preto` e reescreve o texto da variação, então no próximo salvamento o texto "Preto Ônix" (slug `preto-onix`) não casa com nada e cria uma cor duplicada, sem erro. A leitura pública (`GET /produtos/:codigo`) não traz `corId`.

- **`GET /admin/produtos?corId=`** — a busca de produtos por cor no painel. Aqui é **id**, não slug (o painel já tem a lista em mãos e usa id em todos os outros filtros), e traz os ocultos junto, como o resto da rota.

- **Códigos de erro novos:** `COR_NAO_ENCONTRADA` (404), `COR_EM_USO` (409, exclusão) e `COR_EM_CONFLITO` (409, renomeação).

- **Nada mudou na leitura pública do produto.** `variacaoCor` continua `{id, tipo, valor, disponivel}`, e o carrinho segue com `variacaoCorId` apontando para a **variação**, não para a cor. Nenhuma tela existente precisa mudar por causa desta revisão.

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

- **`POST /api/v1/admin/banners/upload`** — upload de arquivo (revisão upload de imagem), mesmo formato e mesmas regras do upload de imagem de produto acima: `multipart/form-data` (`arquivo` + `alt` opcional), processa e grava em disco, responde **201** com `{ "url": "...", "alt": "..." }`. Não existe banner ainda nesta etapa — a tela usa a URL devolvida para preencher `imagemUrl` ou `imagemUrlMobile` do formulário e segue para o `POST`/`PATCH /banners` de sempre.

## Painel administrativo — destaques e consultas (tarefas 58 e 60)

- **`PATCH /api/v1/admin/destaques/produtos`** e **`PATCH /api/v1/admin/destaques/categorias`** — recebem a lista COMPLETA de ids na ordem em que devem aparecer na home: `{ "ids": [812, 44, 930] }`. **Substituem o conjunto**: quem está na lista vira destaque com a ordem da posição, quem não está deixa de ser. Lista vazia tira todos. Respondem com os ids na ordem gravada.

  **Mande SEMPRE a lista inteira, carregada da tela.** Estas rotas substituem o conjunto: se a tela mandar um id só, a home do cliente esvazia — os outros onze destaques somem na mesma chamada, sem erro nenhum, porque "não veio na lista" é exatamente como se tira do destaque. O fluxo certo é ler a ordem atual, mexer nela e devolver inteira.

  **Produto `oculto` é recusado com 400**, e os ids problemáticos vêm em `erro.detalhes.ocultos` — marque-os na tela em vez de mostrar um erro genérico: o produto oculto some da home inteira, então aceitar a marcação seria deixar o cliente marcar e não ver nada. Categoria inativa é recusada pelo mesmo motivo, com `erro.detalhes.inativas`.

  **Teto: 12 produtos e 8 categorias.** O dos produtos é exatamente o que a home renderiza — marcar mais do que ela mostra é marcar o que ninguém vai ver.
- **`GET /api/v1/admin/resumo`** — os números da tela inicial: `totalProdutos`, `produtosEsgotados`, `produtosOcultos`, `porMarca` (lista com `marcaId`, `nome`, `slug` e `total`, incluindo marca com zero), `selecoesNoMes` e `totalClientes`.
- **`GET /api/v1/admin/selecoes`** — as seleções recebidas, mais recentes primeiro, com `?pagina=` e `?porPagina=` no envelope `{dados, paginacao}` de sempre. Cada seleção traz `criadoEm`, `totalItens`, o `cliente` (id, nome, e-mail e telefone, todos congelados no envio) e os `itens`.
- **`GET /api/v1/admin/selecoes/:id`** — o detalhe, com os mesmos itens.

  **Os itens são dado CONGELADO**: `codigo`, `nome`, `marca`, `categoria`, `colecao`, `imagemUrl` e `variacao` são cópias do que o cliente viu no envio, não um JOIN com o catálogo de hoje. Se o produto foi excluído depois, `produtoId` vem `null` e o resto continua igual — não esconda o item nem tente buscar o produto por esse id sem checar o nulo.
- **`GET /api/v1/admin/clientes`** — os clientes cadastrados, com `?busca=` (parte do e-mail ou do nome, ignorando caixa) e paginação. Cada um traz `totalSelecoes`, que é o número que diz quem vale a pena atender, mais `ultimoAcessoEm` e o **telefone** — aqui ele aparece porque é o painel, e é com ele que o atendimento responde.

## Importação completa do Yupoo e fila de revisão

Execute `node scripts/sync-yupoo.mjs` na raiz do backend. O script percorre a listagem global do fornecedor qwer888 até o total de páginas declarado, sem filtro de marcas. Confere o total de álbuns únicos antes de substituir o JSON, cria `data/pending-products.backup.json` e registra a contagem em `data/sync-yupoo-report.json`. Uma falha de rede ou contagem mantém a fila anterior. Reexecuções usam o ID do álbum e não duplicam produtos. Registros antigos e outros fornecedores são preservados. Produtos novos ficam em `A classificar`; categorias já atribuídas são mantidas. As decisões continuam no PostgreSQL.

`GET /api/v1/admin/revisao/pendentes` aceita `pagina` (mínimo 1) e `porPagina` (1–100, padrão 60), além de `busca` e `categoria`. Retorna `items`, `total`, `categories`, `pagina`, `paginas` e `porPagina`. O total considera o filtro e exclui produtos já decididos; páginas fora do intervalo são ajustadas para a última página. O backend recarrega o catálogo quando o arquivo muda. Depois de decidir um produto, o frontend atualiza a página para repor os itens disponíveis.

## Controle de entrada da loja — seção 05, modo aprovação (28/09/2026)

O cliente da No Fear decidiu ligar o modo 3 da seção 05: quem não foi aprovado pela equipe não vê o catálogo. Cinco das seis rotas saíram do congelamento. **`POST /acesso/senha` (modo 2, senha compartilhada) continua congelada e não existe.**

- **A loja é sempre fechada (decisão do cliente, 29/09/2026).** A revisão 0014 grava `acesso_config.modo = 'aprovacao'`, e não existe mais o modo aberto: ninguém liga ou desliga o portão, nem pelo painel. Linha ausente no banco também conta como fechado. Quem já estava cadastrado continua aprovado (o default de `clientes.acesso_status` é `'aprovado'`), então ninguém é trancado para fora.
- **O portão.** Com `modo = 'aprovacao'`, todas as rotas de catálogo e de conta passam por ele: `/home`, `/produtos`, `/produtos/:codigo`, `/produtos/:codigo/relacionados`, `/marcas`, `/cores`, `/colecoes`, `/colecoes/:slug/categorias`, `/favoritos`, `/carrinho` e `/selecoes`. A resposta de quem não passa:
  - **401 `NAO_IDENTIFICADO`**, sem sessão de cliente. É o mesmo 401 de sempre: mande para a identificação.
  - **403 `ACESSO_PENDENTE`**, identificado e aguardando liberação.
  - **403 `ACESSO_RECUSADO`**, identificado e recusado (ou com o acesso revogado).

  Nos dois 403, `erro.mensagem` traz a mensagem de bloqueio que o painel escreveu (ou um texto padrão, se não houver nenhuma), e `erro.detalhes.situacao` traz `pendente` ou `recusado`.
- **Ficam sempre fora do portão:** `/acesso/*`, `/clientes/*` (identificar, eu, sair), `/health` e **todo o `/admin/*`**. O painel nunca é barrado, porque é dali que a equipe libera a fila. Uma varredura em `testes/teste_acesso_loja.py` falha se alguma rota pública escapar do portão sem estar nessa lista, ou se o portão pegar o painel.
- **Cliente novo com o portão ligado nasce `pendente`.** `POST /clientes/identificar` continua respondendo sempre 200 e com o mesmo corpo. O que muda é que um e-mail que ainda não existia entra pendente. **Quem já estava cadastrado continua aprovado**: ligar o modo não tranca ninguém que já existe (o default da coluna é `'aprovado'`).
- **`GET /api/v1/acesso/estado`** nunca é barrado e nunca devolve 401. É a primeira chamada da loja ao abrir:

  ```json
  { "modo": "aprovacao", "podeNavegar": false, "identificado": true,
    "situacao": "pendente", "solicitacaoPendente": false,
    "mensagemBloqueio": "Loja exclusiva para clientes convidados.",
    "podeSolicitar": true, "bloqueadoAte": null }
  ```

  `podeNavegar` é o que decide a tela. Sem sessão, `identificado` vem `false` e `situacao` vem `null`. `solicitacaoPendente` separa quem ainda precisa pedir liberação de quem já pediu e está esperando. `podeSolicitar` é `false` só na espera das 3 recusas seguidas, e então `bloqueadoAte` (ISO 8601) traz a data em que ele volta a poder pedir; fora da espera, `podeSolicitar` é `true` e `bloqueadoAte` é `null`.
- **`POST /api/v1/acesso/solicitar`** pede a liberação. **Exige sessão de cliente** (401 sem ela), então o fluxo é identificar e depois solicitar. Corpo opcional `{ "nome": "...", "telefone": "..." }`: atualiza o cadastro e fica congelado no pedido. Responde **200** com o mesmo formato de `/acesso/estado`. **É idempotente**: pedir de novo devolve o mesmo estado e não cria um segundo pedido. Com o cliente já aprovado, não cria nada e só devolve o estado. **Cliente recusado pode pedir de novo** (o pedido o devolve a `pendente`), **com uma trava: 3 recusas seguidas (contadas desde a última aprovação; uma aprovação zera a contagem) deixam o cliente 3 dias sem poder pedir**, contados do `decididoEm` da recusa mais recente. Durante a espera, `POST /acesso/solicitar` responde **403 `ACESSO_EM_ESPERA`**, sem criar pedido, com a data de liberação em `erro.mensagem` ("a partir de dd/mm/aaaa às hh:mm", horário de Brasília) e em `erro.detalhes.bloqueadoAte` (ISO 8601). Recusar de novo depois da espera reinicia os 3 dias. As constantes ficam em `servicos/acesso.py` (`RECUSAS_PARA_ESPERA`, `DIAS_DE_ESPERA`).
- **`GET /api/v1/admin/acesso/fila`** lista os pedidos pendentes, do mais antigo para o mais novo, com `?pagina=` e `?porPagina=` no envelope `{dados, paginacao}`. Cada item traz `id`, `clienteId`, `email`, `nome`, `telefone` e `criadoEm`, copiados do cadastro no momento do pedido.
- **`PATCH /api/v1/admin/acesso/:clienteId`** aprova, recusa ou revoga. Corpo `{ "situacao": "aprovado" | "recusado", "motivo": "opcional, uso interno" }`. A decisão é **por cliente**, não por pedido:
  - com pedido pendente, a decisão fecha o pedido;
  - sem pedido pendente (aprovado que perde o acesso, recusado que a equipe resolve liberar), grava uma linha já decidida no histórico.

  Nos dois casos, `clientes.acesso_status` muda na mesma transação e o admin que decidiu fica registrado. Repetir a mesma decisão não cria linha nova, e a resposta vem com `decididoEm: null`. `situacao: "pendente"` é recusado com 400. Cliente inexistente devolve 404 `CLIENTE_NAO_ENCONTRADO`.
- **`PATCH /api/v1/admin/configuracao/acesso`** só grava a mensagem de bloqueio; **não liga nem desliga o portão**. É um PATCH parcial: `{ "mensagemBloqueio": "..." }`. `mensagemBloqueio: null` apaga a mensagem. `modo: "aprovacao"` é aceito e não muda nada; `"aberto"` e `senha_compartilhada` são recusados com 400. Responde com `modo`, `mensagemBloqueio` e `atualizadoEm`. **Não existe `GET` administrativo da configuração**: o painel lê o modo e a mensagem atuais em `GET /acesso/estado`, que é público. É a mesma exceção da tela de Destaques, que lê a home pública.
- **E-mails pré-aprovados (29/09/2026).** Os e-mails listados em `EMAILS_PRE_APROVADOS` (variável de ambiente, separados por vírgula) entram sempre na loja fechada. Quem se identifica com um deles nasce `aprovado` (ou vira `aprovado`, se já existia pendente ou recusado), e o painel não consegue barrá-lo: `podeNavegar` é `true` mesmo se a equipe recusar ou revogar. Para o frontend nada muda no contrato. **Limitação conhecida, decidida pelo cliente:** a identificação continua sem senha, então quem digitar um desses e-mails entra.
- **Códigos de erro novos:** `ACESSO_PENDENTE` (403) e `ACESSO_RECUSADO` (403).

## Novidades: janela de 14 dias (29/09/2026)

Regra decidida com o cliente: todo produto fica **no máximo 14 dias** na página Novidades. Depois disso ele sai de lá e continua aparecendo normalmente nas categorias dele, em `/todos`, na busca e nas páginas de marca e coleção. Nada é apagado nem alterado no produto: é só um recorte por data.

- **`GET /api/v1/produtos?novidades=true`** devolve só os produtos criados nos últimos 14 dias (`criado_em >= agora - 14 dias`), sem os ocultos, como toda a rota. A janela é **rolante**, calculada na hora da consulta: não há tarefa agendada nem coluna nova. A constante é `DIAS_NOVIDADE` em `servicos/catalogo.py`.
- **Aceita só `true` ou `false`.** Qualquer outro valor devolve o 400 de validação de sempre. Sem o parâmetro, ou com `false`, nada muda.
- **Combina com todos os outros filtros** (`colecao`, `categoria`, `marca`, `cor`, `busca`) e com `ordem`.
- **Paginação:** `total` e `proximoCursor` valem dentro do recorte. O cursor guarda o filtro: um cursor de `?novidades=true` usado numa consulta sem ele (ou o contrário) devolve 400 `CURSOR_INVALIDO`. Ao trocar o filtro, recomece da primeira página.
- **Produto novo:** para o produto criado no painel, o início da janela é a data de criação; para o que veio da revisão, é a data da aprovação (só ali ele entra na tabela `produtos`).
- **Saída manual (30/09/2026, migração 0017):** `produtos.em_novidades` (padrão `true`). `?novidades=true` exige a flag ligada **e** os 14 dias. O painel lê `emNovidades` em `GET /admin/produtos` e `/{id}`, aceita em `POST /admin/produtos` (padrão `true`) e `PATCH /admin/produtos/{id}`, e `POST /admin/revisao` aceita `emNovidades` (padrão `true`) ao aprovar.
- **`GET /home` não muda.** Os "destaques" da home são escolha manual da equipe (`destaque = true`, com ordem própria), não uma vitrine de novidades.

## Categoria escondida (`ativa: false`) (30/09/2026)

O painel passou a usar `ativa` em categorias (já existia no contrato). Regras, agora todas cobertas por `testes/teste_categoria_escondida.py`:

- **Sai da vitrine:** `GET /colecoes/:slug/categorias` e os destaques de `GET /home` não devolvem a categoria. `PATCH /admin/destaques/categorias` continua recusando categoria inativa.
- **Link direto (mudou):** `GET /produtos?colecao=&categoria=<slug escondido>` agora responde como slug desconhecido (lista vazia), em vez de listar os produtos dela. Os produtos seguem em `/produtos` sem filtro, por coleção, busca, marca, novidades e nas outras categorias deles.
- **Produto que já está numa categoria escondida (mudou):** `PATCH /admin/produtos/:id` com `categoriasIds` só barra a categoria inativa quando ela é ADICIONADA; reenviar uma que o produto já tem passa (antes, adicionar o segundo destino a um produto cuja categoria principal estava escondida dava 400). `categoriaId` igual à atual também passa.
- **Produto novo (mudou):** `categoriaId` de categoria escondida agora dá 400 (`campos.categoriaId`) em `PATCH /admin/produtos/lote`, em `POST /admin/produtos` e em `PATCH /admin/produtos/:id` (quando é outra que a atual).

## Feminino e Masculino viram o público do produto; categorias sem coleção (migração 0015, 30/09/2026)

A tabela `colecoes` deixou de existir. Feminino e Masculino são o **público** de cada produto (`feminino`/`masculino`; as duas marcadas = unissex) e as categorias não pertencem mais a coleção.

- **Mantido:** `GET /colecoes` (constantes, ids 1 e 2, slugs `feminino`/`masculino`), `GET /colecoes/:slug/categorias`, `GET /produtos?colecao=` (filtra pelo público; unissex aparece nos dois) e o campo `colecao` (`{nome, slug}`) dos produtos: é o público principal, e o nome vira "Unissex" quando são os dois.
- **Mudou (público):** `GET /colecoes/:slug/categorias` só traz categorias ativas com pelo menos uma peça visível daquele público. `GET /produtos?categoria=` vale sozinho (o slug é único na tabela) e combina com `colecao` (as duas condições). `CategoriaDestaque` da home perdeu `colecao`.
- **Mudou (painel, categorias):** `CategoriaAdmin`, `CategoriaCriar` e `CategoriaEditar` não têm mais `colecaoId`/`colecaoSlug`; `GET /admin/categorias` não aceita `?colecaoId`. Slug repetido é 409 `SLUG_EM_USO` na tabela toda.
- **Mudou (painel, produtos):** `ProdutoCriar` exige `publicos` (`["feminino"]`, `["masculino"]` ou os dois; vazio ou valor fora disso é 400 com `campos.publicos`). `ProdutoEditar` aceita `publicos` e `categoriasIds` (1 a 5; a primeira é a principal). `ProdutoAdminDetalhe` devolve `publicos` no lugar de `colecaoId`. `GET /admin/produtos?colecaoId=` continua (1 = feminino, 2 = masculino). O lote (`categoriaId`) troca só a categoria; não mexe no público.
- **Revisão — fotos do álbum (01/10/2026):** `GET /admin/revisao/fotos?produtoId=` abre o álbum no Yupoo (com `uid=1`, sem o qual ele responde 404) e devolve `{fotos: [{url, miniatura}]}` na ordem do fornecedor (cache de 5 min). `POST /admin/revisao` aceita `fotos` (1–20 URLs `photo.yupoo.com`, na ordem final; **a primeira é a capa**); sem `fotos` entra só a capa do álbum. Todas são baixadas antes de criar o produto: se uma falhar, a aprovação inteira falha (502) sem criar nada. `GET /admin/revisao/publicados` devolve `produtoId` e `imagensEstado` (`concluido` se o produto existe, `legado` se a aprovação é antiga e não gerou produto).
- **Revisão (Yupoo):** `POST /admin/revisao` aceita `publicos` (ou `colecao`, como antes) e até 5 `categoriasIds`.
- **Dados:** a migração fundiu as categorias de mesmo slug (fica a de menor id) e marcou como unissex os produtos que estavam nas duas coleções. Ensaiada numa cópia do banco de dev.
- **Fechado depois (mesmo dia):** o `upgrade()` recria a FK `produtos.categoria_id -> categorias.id`; o `downgrade()` foi refeito e ensaiado (upgrade, downgrade, upgrade); os scripts de massa foram adaptados. O `alembic check` só aponta divergências antigas de `review_decisions`.

## Cards da home: categoria no lugar de Feminina/Masculina (migração 0016, 30/09/2026)

- **`GET /home`** ganhou `cardsColecao`: lista de `{ lado: "esquerda" | "direita", id, nome, slug, imagemUrl }`, uma por lado ocupado (esquerda = no lugar do card Feminina, direita = Masculina). `imagemUrl` é a imagem do card ou, se não houver, a da categoria. Só entram categorias ativas. Vem na mesma consulta das categorias em destaque (orçamento de 4 consultas mantido).
- **Painel:** `CategoriaAdmin`, `CategoriaCriar` e `CategoriaEditar` têm `cardHome` (`"esquerda"`, `"direita"` ou `null`) e `cardHomeImagemUrl` (https). Marcar um lado tira a categoria que o ocupava (e apaga a imagem do card dela); `cardHome: null` tira a categoria do card e apaga a imagem do card. Lado fora de esquerda/direita e imagem sem `https://` são 400.
- **Banco:** `categorias.card_home`, `categorias.card_home_imagem_url`, `ck_categorias_card_home` e o índice único parcial `uq_categorias_card_home` (um por lado).

## Link de origem do produto (02/10/2026)

`produtos.origem_url` já existia e a revisão já o preenchia ao aprovar (com o link do álbum). Agora o painel o enxerga: `GET /admin/produtos/{id}` devolve `origemUrl` (ou `null`), `POST /admin/produtos` e `PATCH /admin/produtos/{id}` aceitam `origemUrl`. Só http/https sem espaço (senão 400 em `campos.origemUrl`); no PATCH, `""` ou `null` apaga e a ausência do campo não mexe. O backend só guarda o texto, nunca abre o link. Sem migração. A listagem (`GET /admin/produtos`) também traz `origemUrl` em cada linha (o painel mostra "Ver origem" ao lado das ações). Duplicar produto não copia o link.

## Atualizar produtos da Yupoo pela Revisão (02/10/2026)

Dois endpoints do painel (sessão de admin) para o botão **Atualizar produtos**:

- `POST /admin/revisao/atualizar` — começa a coleta e responde na hora com o andamento. Roda `scripts/sync-yupoo.mjs data/fornecedores-adicionais.json --padrao` (os fornecedores do arquivo **mais** os embutidos, como o qwer888, que não está no arquivo). Se já houver uma coleta rodando (inclusive em outro processo), não começa outra: devolve o andamento da que está em curso.
- `GET /admin/revisao/atualizacao` — andamento: `estado` (`ocioso` | `rodando` | `concluido` | `falhou`), `iniciadoEm`, `concluidoEm`; em `concluido`, `adicionados` (álbuns novos na fila), `coletados` e `total`; em `falhou`, `erro` (texto para mostrar). A tela consulta de poucos em poucos segundos enquanto `rodando`; a coleta leva vários minutos.

**Sem repetidos:** o script junta os álbuns pelo id (`fornecedor-idDoÁlbum`), então reexecutar não duplica, e `GET /admin/revisao/pendentes` já esconde o que foi aprovado ou reprovado (decisões no PostgreSQL). Quem vem do arquivo e já estava na fila mantém a categoria e a marca sugerida.

O estado fica em `data/sync-yupoo-estado.json` e a trava em `data/sync-yupoo.lock` (os dois fora do git). Uma falha de rede preserva a fila anterior. **Infra:** a imagem da API agora tem Node (`Dockerfile`) e `./data` não é mais somente leitura no compose; em produção é preciso reconstruir a imagem e deixar `data/` gravável.
