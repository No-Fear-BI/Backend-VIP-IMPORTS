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
- **`POST /carrinho/migrar` — formato novo, não estava no contrato v1.0.** É como o carrinho do `localStorage` (visitante não identificado) entra na conta logo após a identificação. Corpo:

  ```json
  { "itens": [ { "produtoId": 812, "variacaoId": 55 }, { "produtoId": 930 } ] }
  ```

  A resposta traz `itens` (o carrinho final da conta) e `ignorados` — os que não puderam migrar, cada um com `produtoId`, `variacaoId`, `motivo` (`PRODUTO_INDISPONIVEL` ou `PRODUTO_NAO_ENCONTRADO`) e `mensagem` pronta para exibir. Mostre esses ignorados ("2 itens não estão mais disponíveis") em vez de sumir com eles em silêncio. Produto já na conta com a mesma variação não duplica; com variação diferente vira um segundo item.
- **O carrinho NÃO tem quantidade.** O mesmo produto com variações diferentes são dois itens; o mesmo produto com a mesma variação é um item só. Adicionar duas vezes o mesmo par não é erro, é sem efeito.
- **O item do carrinho tem `itemId` além de `id`.** `id` é o produto (para link e imagem); `itemId` é a linha do carrinho, e é ele que vai em `PATCH /carrinho/:itemId` e `DELETE /carrinho/:itemId`.
- **`POST /selecoes` NÃO esvazia o carrinho.** Se a pessoa abrir o link do WhatsApp e fechar sem mandar a mensagem, esvaziar teria destruído a seleção dela. Se a tela quiser oferecer "limpar seleção", é um botão que chama `DELETE /carrinho/:itemId` item a item — o backend não faz isso sozinho.
- **`linkWhatsapp` vem pronto do backend.** Não monte o link no frontend e não guarde o número da loja lá: ele vive só na configuração do servidor. O texto já vai percent-encoded; basta abrir a URL.
- **Códigos de erro novos:** `CARRINHO_VAZIO` (400, `POST /selecoes` sem itens), `ITEM_NAO_ENCONTRADO` (404, item do carrinho inexistente **ou de outro cliente** — a API não distingue os dois casos de propósito) e `VARIACAO_INVALIDA` (400, variação que não pertence ao produto).
