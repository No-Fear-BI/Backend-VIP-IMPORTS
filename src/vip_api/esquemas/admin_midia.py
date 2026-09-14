"""Esquemas das imagens e das variações do produto no painel (tarefa 56)."""

from typing import Literal

from pydantic import Field, field_validator

from vip_api.esquemas.base import EsquemaEntrada

# Teto por produto. A grade do site mostra uma capa e a página do produto
# mostra a galeria; passar disso é peso de carregamento para o visitante, não
# informação. Se um dia precisar subir, é constante aqui e nada mais.
LIMITE_IMAGENS = 10


class ImagemEntrada(EsquemaEntrada):
    url: str = Field(min_length=1, max_length=2000)
    alt: str | None = Field(None, max_length=200)

    @field_validator("url")
    @classmethod
    def _somente_https(cls, valor: str) -> str:
        # Só https: imagem por http numa página https é bloqueada pelo
        # navegador como conteúdo misto, e o produto aparece sem foto sem
        # ninguém entender por quê.
        limpo = valor.strip()
        if not limpo.lower().startswith("https://"):
            raise ValueError("A URL da imagem precisa começar com https://.")
        return limpo


class ImagensEntrada(EsquemaEntrada):
    imagens: list[ImagemEntrada] = Field(min_length=1, max_length=LIMITE_IMAGENS)


class OrdemEntrada(EsquemaEntrada):
    """A lista COMPLETA de ids na ordem desejada. Lista parcial é recusada:
    reordenar metade deixaria a outra metade com ordem duplicada."""

    ids: list[int] = Field(min_length=1)


class VariacaoEntrada(EsquemaEntrada):
    tipo: Literal["tamanho", "cor"]
    valor: str = Field(min_length=1, max_length=60)
    disponivel: bool = True


class VariacoesEntrada(EsquemaEntrada):
    """Lista vazia é válida: é assim que o painel remove todas as variações de
    um produto que passou a ser tamanho único."""

    variacoes: list[VariacaoEntrada]
