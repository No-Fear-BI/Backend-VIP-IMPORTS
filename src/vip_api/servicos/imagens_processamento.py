"""Processamento de imagem compartilhado entre `scripts/importar_catalogo.py`
(carga em lote, baixa de URL do fornecedor) e o upload ao vivo do painel
(tarefa de upload de arquivo). As duas pontas de entrada são diferentes —
uma baixa de URL, a outra recebe bytes de um `UploadFile` — mas a partir do
momento em que os bytes crus chegam, a regra é a MESMA: decodifica, encolhe
(nunca amplia) e grava em WebP com a mesma qualidade. Ter isso num lugar só
evita a foto do painel sair com compressão ou limite de tamanho diferente
da foto importada em lote.
"""

from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError

# Lado maior da versão "grande" — é a que fica em produto_imagens.url e
# banners.imagem_url (contrato só tem uma URL por imagem hoje). Mesmo valor
# usado pela importação em lote, para as duas fontes renderem no mesmo
# tamanho na loja.
LADO_GRANDE = 1200
QUALIDADE_WEBP = 82
# Acima disso é cliente/fornecedor mandando arquivo errado (RAW, vídeo
# renomeado, foto de 50MP sem compressão) — rejeita antes de gastar CPU
# decodificando. Mesmo teto usado pela importação em lote.
TAMANHO_MAXIMO_ARQUIVO = 15 * 1024 * 1024  # 15 MB


def abrir_imagem(dados: bytes) -> Image.Image:
    """Decodifica bytes crus e devolve em RGB. Lança `ValueError` — nunca
    deixa `UnidentifiedImageError` do Pillow vazar — quando os bytes não são
    uma imagem que o Pillow consegue abrir: é o jeito de saber que o arquivo
    é falso ou corrompido, não só olhar a extensão/Content-Type, que quem
    manda o arquivo controla e pode mentir.
    """
    try:
        imagem = Image.open(io.BytesIO(dados))
        imagem.load()  # decodifica agora — arquivo corrompido ou HTML disfarçado de imagem estoura aqui
    except UnidentifiedImageError as erro:
        raise ValueError("Não é uma imagem que dá para abrir.") from erro
    return imagem.convert("RGB")


def redimensionado(imagem: Image.Image, lado_maior: int) -> Image.Image:
    """Encolhe para que o lado maior fique em `lado_maior`, mantendo a
    proporção. Nunca amplia uma imagem menor — subir a resolução de uma foto
    pequena só produz um arquivo maior, borrado, sem ganhar nitidez nenhuma.
    """
    largura, altura = imagem.size
    fator = lado_maior / max(largura, altura)
    if fator >= 1:
        return imagem.copy()
    novo_tamanho = (round(largura * fator), round(altura * fator))
    return imagem.resize(novo_tamanho, Image.LANCZOS)


def para_webp(imagem: Image.Image) -> bytes:
    buffer = io.BytesIO()
    imagem.save(buffer, format="WEBP", quality=QUALIDADE_WEBP, method=6)
    return buffer.getvalue()
