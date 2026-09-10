# Limitações conhecidas

Registro por escrito das limitações aceitas do sistema, com a decisão que as
originou e a mitigação aplicada. Tarefa 42 do plano de execução.

## Identificação do cliente sem senha

A área do cliente da VIP Imports identifica o visitante apenas pelo e-mail:
quem informa um endereço entra na conta correspondente, sem senha e sem
confirmação. Isso significa que **qualquer pessoa que saiba (ou adivinhe) o
e-mail de um cliente entra na conta dele** e passa a ver os produtos
favoritados, o histórico de seleções enviadas e o telefone cadastrado. Não é
uma falha de implementação: é a consequência direta do modelo sem senha, que
**foi escolhido pelo cliente**, não pela No Fear. A decisão está registrada em
dois documentos: no item 2.2 da proposta comercial ("Identificação por e-mail,
sem senha: a conta é reconhecida pelo endereço informado") e na seção 03 do
contrato de API ("Decisão do cliente: sem senha"). A justificativa apresentada
foi reduzir o atrito de quem só quer montar uma lista e mandar pelo WhatsApp —
pedir cadastro com senha afasta parte dos visitantes antes do primeiro
contato. A No Fear apontou a exposição decorrente e aplicou a mitigação
possível dentro desse modelo: um limite de identificações por endereço IP por
minuto, que impede a varredura automatizada de e-mails em série. Ela reduz o
abuso em escala, mas **não protege contra alguém que conheça o e-mail de um
cliente específico** e queira ver os dados daquela pessoa. Nenhum dado de
pagamento existe no sistema, e nenhuma rota pública devolve o telefone de
terceiros — o telefone só aparece para o próprio cliente autenticado e no
painel administrativo. Se o cliente decidir fechar essa exposição, o caminho é
confirmação por e-mail (um código enviado ao endereço informado antes de abrir
a sessão); o backend já está dividido para receber isso sem reescrita, entre
identificar o cliente e abrir a sessão.

## Detalhes técnicos da mitigação

- Limite de **10 identificações por IP por minuto**; acima disso a API responde
  `429` com o código `EXCESSO_TENTATIVAS`.
- A contagem fica no **banco**, não em memória do processo: em produção o
  uvicorn roda com vários workers, e um contador em memória só enxergaria as
  tentativas que caíssem no mesmo worker.
- Atrás do Nginx, o IP real vem de `X-Forwarded-For`, mas o cabeçalho **só é
  lido quando a conexão vem de um proxy listado em `PROXIES_CONFIAVEIS`**. Sem
  isso, qualquer visitante forjaria um IP diferente a cada tentativa e o limite
  não valeria nada; e sem tratar o cabeçalho, todos os visitantes chegariam com
  o IP do proxy e o primeiro que estourasse o limite trancaria o site inteiro.
