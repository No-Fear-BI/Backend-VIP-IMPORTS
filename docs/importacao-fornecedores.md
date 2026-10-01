# Importação dos fornecedores adicionais

Execute na raiz do backend:

```powershell
node scripts/sync-yupoo.mjs data/fornecedores-adicionais.json
```

O arquivo contém os 14 links únicos solicitados em 01/10/2026. Cada categoria,
coleção ou listagem é percorrida desde a primeira página, mesmo se o link
informado apontar para outra página. Os álbuns são identificados pelo fornecedor
e pelo ID do álbum: categorias sobrepostas e reexecuções não duplicam itens.

O importador suporta cartões `album__title` e `album3__title`, imagens em
`data-src` ou `src`, categorias de uma página e listagens que informam somente
o número de páginas. Quando existe total de álbuns, a coleta precisa corresponder
exatamente a ele; sem esse total, são verificadas todas as páginas e a unicidade
dos IDs. Falhas impedem a substituição da fila anterior.

Os itens anteriores e suas categorias são preservados. Novos itens entram como
`A classificar` na fila de revisão, sem publicação automática na loja. Decisões
de aprovação e rejeição continuam no PostgreSQL.

A fila fica em `data/pending-products.json`, com cópia anterior em
`data/pending-products.backup.json`. O resultado por origem e as contagens
ficam em `data/sync-yupoo-report.json`. A API detecta a atualização do arquivo
sem precisar reiniciar.
