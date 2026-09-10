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
CURSOR_INVALIDO = "CURSOR_INVALIDO"
PARAMETRO_OBRIGATORIO = "PARAMETRO_OBRIGATORIO"
NAO_IDENTIFICADO = "NAO_IDENTIFICADO"
SEM_PERMISSAO = "SEM_PERMISSAO"
CODIGO_EM_USO = "CODIGO_EM_USO"
MARCA_COM_PRODUTOS = "MARCA_COM_PRODUTOS"
CATEGORIA_COM_PRODUTOS = "CATEGORIA_COM_PRODUTOS"
EXCESSO_TENTATIVAS = "EXCESSO_TENTATIVAS"
ERRO_INTERNO = "ERRO_INTERNO"

# Não veio da lista da tarefa 1 — é o código genérico que o manipulador de
# RequestValidationError usa quando o Pydantic recusa o corpo/query da
# requisição. O detalhe por campo vai em "campos"; este é só o rótulo geral.
DADOS_INVALIDOS = "DADOS_INVALIDOS"
