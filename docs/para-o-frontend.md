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
- **`POST /api/v1/admin/produtos/:id/duplicar`** — responde **201** com a cópia: mesmas imagens (na mesma ordem) e variações, código novo, nome com `(cópia)` no fim. **A cópia nasce `oculto` e sem destaque** — é rascunho até alguém terminar de editar, e uma gêmea publicada na hora apareceria na vitrine.
- **`PATCH /api/v1/admin/produtos/lote`** — altera vários de uma vez. Aceita **exatamente quatro campos**, e qualquer outro é **400**: `status`, `destaque`, `marcaId`, `categoriaId`. Máximo de 100 ids por chamada.

  ```json
  { "ids": [12, 34, 56], "status": "oculto" }
  ```

  Responde `{"alterados": 3}`. **É tudo ou nada**: se algum id não existir mais, nada é alterado e a resposta é **404** com a lista dos ids problemáticos em `erro.detalhes.naoEncontrados` — use essa lista para marcar as linhas na tela e recarregar a listagem.

  ```json
  { "erro": { "codigo": "PRODUTO_NAO_ENCONTRADO", "mensagem": "...", "campos": { "ids": "..." }, "detalhes": { "naoEncontrados": [99] } } }
  ```

- **`erro.detalhes` é campo novo do envelope de erro**, e opcional: some quando não há nada a processar. `campos` continua sendo o texto que vai embaixo de cada input; `detalhes` é o que a tela precisa ler como dado, não exibir como frase.
