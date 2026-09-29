"""Códigos de erro da API — string estável, é contrato com o frontend
(seção 1.3). Nunca renomeie um já publicado; se um código deixar de fazer
sentido, deprecie e crie outro."""

PRODUTO_NAO_ENCONTRADO = "PRODUTO_NAO_ENCONTRADO"
CLIENTE_NAO_ENCONTRADO = "CLIENTE_NAO_ENCONTRADO"
SELECAO_NAO_ENCONTRADA = "SELECAO_NAO_ENCONTRADA"
MARCA_NAO_ENCONTRADA = "MARCA_NAO_ENCONTRADA"
CATEGORIA_NAO_ENCONTRADA = "CATEGORIA_NAO_ENCONTRADA"
# Coleção tem código próprio: usar CATEGORIA_NAO_ENCONTRADA para uma coleção
# inexistente faria o frontend mostrar a mensagem errada ao visitante.
COLECAO_NAO_ENCONTRADA = "COLECAO_NAO_ENCONTRADA"
ITEM_NAO_ENCONTRADO = "ITEM_NAO_ENCONTRADO"
VARIACAO_INVALIDA = "VARIACAO_INVALIDA"
CARRINHO_VAZIO = "CARRINHO_VAZIO"
CURSOR_INVALIDO = "CURSOR_INVALIDO"
PARAMETRO_OBRIGATORIO = "PARAMETRO_OBRIGATORIO"
NAO_IDENTIFICADO = "NAO_IDENTIFICADO"
SEM_PERMISSAO = "SEM_PERMISSAO"
# Login do painel. Um código só para e-mail inexistente, senha errada e
# conta inativa: códigos diferentes diriam quais e-mails são de
# administrador, que é a mesma informação que o tempo de resposta entrega.
CREDENCIAIS_INVALIDAS = "CREDENCIAIS_INVALIDAS"
CODIGO_EM_USO = "CODIGO_EM_USO"
# Slug de marca ou de categoria já usado. Separado de CODIGO_EM_USO, que é
# do código do produto: são campos diferentes em telas diferentes, e o
# frontend marca o input pelo código do erro.
SLUG_EM_USO = "SLUG_EM_USO"
MARCA_COM_PRODUTOS = "MARCA_COM_PRODUTOS"
CATEGORIA_COM_PRODUTOS = "CATEGORIA_COM_PRODUTOS"
COR_NAO_ENCONTRADA = "COR_NAO_ENCONTRADA"
COR_EM_USO = "COR_EM_USO"
# Renomear cor reescreve o `valor` das variações que apontam para ela. Se um
# produto já tiver outra variação com o nome novo, a UNIQUE (produto, tipo,
# valor) recusa — e a tela precisa saber que foi colisão de nome, não falha
# genérica, para sugerir juntar as duas cores em vez de tentar de novo.
COR_EM_CONFLITO = "COR_EM_CONFLITO"
# Controle de entrada da loja (seção 05, modo aprovação). Dois códigos, não
# um: a tela do visitante é diferente — "seu pedido está em análise" contra
# "seu acesso não foi liberado". Sem sessão continua NAO_IDENTIFICADO (401).
ACESSO_PENDENTE = "ACESSO_PENDENTE"
ACESSO_RECUSADO = "ACESSO_RECUSADO"
# Recusado que estourou o limite de recusas seguidas e ainda está na espera
# para pedir de novo (servicos/acesso.py). `detalhes.bloqueadoAte` traz a data.
ACESSO_EM_ESPERA = "ACESSO_EM_ESPERA"
EXCESSO_TENTATIVAS = "EXCESSO_TENTATIVAS"
ERRO_INTERNO = "ERRO_INTERNO"

# Não veio da lista da tarefa 1 — é o código genérico que o manipulador de
# RequestValidationError usa quando o Pydantic recusa o corpo/query da
# requisição. O detalhe por campo vai em "campos"; este é só o rótulo geral.
DADOS_INVALIDOS = "DADOS_INVALIDOS"
