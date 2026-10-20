## Atualização de 20/10/2026 — pedidos voltam, agora com status

Pedido do dono: a decisão de 05/10/2026 (abaixo) foi **revertida**. A migração 0021 cria `pedidos` (com `status`: em_andamento, finalizado, nao_finalizado) e `pedido_itens`, com o mesmo desenho congelado de `selecoes`/`selecao_itens`; `POST /selecoes` grava o pedido e o painel ganha `/admin/pedidos`. O histórico apagado pela 0019 não volta. Detalhes das rotas em `para-o-frontend.md`.

## Atualização de 05/10/2026 — pedidos sem histórico

Por solicitação do cliente, o histórico de pedidos foi removido. `POST /selecoes`
responde 200 com `itens`, `mensagemWhatsapp` e `linkWhatsapp`, gerados em memória.
Não cria id, data, registro de pedido nem cópia dos dados do cliente. O carrinho
em andamento é mantido. As rotas GET /selecoes e GET /admin/selecoes (lista e
detalhe) foram removidas, assim como selecoesNoMes e totalSelecoes dos relatórios.
A migração 0019 remove as tabelas selecoes e selecao_itens e seu conteúdo antigo.
O histórico da conversa fica no WhatsApp. Esta decisão substitui as referências
anteriores a histórico de seleções neste documento.

