"""Upload de imagem ao vivo pelo painel (produtos e banners).

Diferente de `scripts/importar_catalogo.py` (que baixa de uma URL do
fornecedor), aqui os bytes vêm de quem está logado no painel — mas o painel
roda no navegador ou no celular de quem quer que tenha a senha, então o
arquivo em si não é mais confiável que um upload público: confere o tipo
REAL decodificando com Pillow (nunca só a extensão ou o Content-Type que o
cliente manda, que é o próprio remetente quem escreve), recusa acima de
TAMANHO_MAXIMO_ARQUIVO, e qualquer coisa que não seja imagem válida vira
DADOS_INVALIDOS — nunca um 500 nem um arquivo estranho parando no disco.

Este serviço NÃO grava produto_imagens nem banners: devolve só (url, alt), a
mesma forma que o campo de URL manual já aceita. A tela decide o que fazer
com essa URL — no produto, chama o `POST /produtos/:id/imagens` de sempre
(admin_imagens.adicionar_imagens), que já resolve limite/ordem/capa; no
banner, só preenche o campo do formulário até o `POST`/`PATCH /banners` de
sempre. Duplicar aquela lógica aqui seria dois lugares para as mesmas regras
divergirem.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from sqlalchemy.orm import Session

from vip_api.configuracao import configuracao
from vip_api.erros.codigos import DADOS_INVALIDOS, PRODUTO_NAO_ENCONTRADO
from vip_api.erros.excecoes import AppError
from vip_api.modelos.catalogo import Produto
from vip_api.servicos.imagens_processamento import (
    LADO_GRANDE,
    TAMANHO_MAXIMO_ARQUIVO,
    abrir_imagem,
    para_webp,
    redimensionado,
)


def _arquivo_invalido(mensagem: str) -> AppError:
    return AppError(
        codigo=DADOS_INVALIDOS, mensagem=mensagem, status_code=400, campos={"arquivo": mensagem}
    )


def _processar_e_salvar(dados: bytes, pasta_relativa: str) -> str:
    """Valida, redimensiona pro tamanho grande (mesma regra da importação em
    lote), grava em `IMAGENS_DIR/<pasta_relativa>/` com nome opaco (evita
    colisão e evita expor o nome original do arquivo do remetente na URL
    pública) e devolve a URL final servida por `StaticFiles`."""
    if not dados:
        raise _arquivo_invalido("Envie um arquivo.")
    if len(dados) > TAMANHO_MAXIMO_ARQUIVO:
        raise _arquivo_invalido(
            f"Arquivo muito grande — o máximo é {TAMANHO_MAXIMO_ARQUIVO // (1024 * 1024)} MB."
        )

    try:
        imagem = abrir_imagem(dados)
    except ValueError as erro:
        raise _arquivo_invalido("O arquivo enviado não é uma imagem que dá para abrir.") from erro

    conteudo = para_webp(redimensionado(imagem, LADO_GRANDE))

    pasta = Path(configuracao.IMAGENS_DIR) / pasta_relativa
    pasta.mkdir(parents=True, exist_ok=True)
    nome_arquivo = f"{secrets.token_hex(16)}.webp"
    (pasta / nome_arquivo).write_bytes(conteudo)

    return f"{configuracao.IMAGENS_URL_BASE.rstrip('/')}/{pasta_relativa}/{nome_arquivo}"


def upload_imagem_produto(
    sessao: Session, produto_id: int, dados: bytes, alt: str | None
) -> tuple[str, str | None]:
    if sessao.get(Produto, produto_id) is None:
        raise AppError(
            codigo=PRODUTO_NAO_ENCONTRADO, mensagem="Produto não encontrado.", status_code=404
        )
    url = _processar_e_salvar(dados, f"produtos/{produto_id}")
    return url, alt


def upload_imagem_banner(dados: bytes, alt: str | None) -> tuple[str, str | None]:
    url = _processar_e_salvar(dados, "banners")
    return url, alt
