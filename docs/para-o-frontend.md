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
