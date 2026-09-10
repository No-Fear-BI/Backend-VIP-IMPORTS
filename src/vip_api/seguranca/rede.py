"""Descobre o IP real do visitante.

Em produção a aplicação fica atrás do Nginx. Sem tratar `X-Forwarded-For`,
TODO visitante chega com o IP do proxy — e o primeiro que estourar o limite
tranca o site inteiro para todo mundo.

Tratar o cabeçalho sem cuidado é o erro oposto: `X-Forwarded-For` é escrito
pelo cliente e pode ser forjado. Quem quiser furar o limite manda um IP
diferente a cada tentativa. Por isso o cabeçalho só é lido quando a conexão
veio de um proxy que está na configuração.
"""

import ipaddress

from fastapi import Request

from vip_api.configuracao import configuracao


def _e_confiavel(endereco: str) -> bool:
    try:
        ip = ipaddress.ip_address(endereco)
    except ValueError:
        return False
    for entrada in configuracao.PROXIES_CONFIAVEIS:
        try:
            if ip in ipaddress.ip_network(entrada, strict=False):
                return True
        except ValueError:
            continue
    return False


def ip_do_visitante(requisicao: Request) -> str:
    """IP de quem realmente fez a requisição.

    Se a conexão não veio de um proxy confiável, o cabeçalho é ignorado por
    completo — inclusive quando está presente.
    """
    imediato = requisicao.client.host if requisicao.client else ""

    if not imediato or not _e_confiavel(imediato):
        return imediato or "0.0.0.0"

    encaminhados = requisicao.headers.get("x-forwarded-for", "")
    if not encaminhados:
        return imediato

    # Da direita para a esquerda, descartando proxies confiáveis: o primeiro
    # endereço que NÃO é nosso proxy é o cliente. Pegar o primeiro da lista
    # (à esquerda) seria confiar no que o cliente escreveu.
    cadeia = [parte.strip() for parte in encaminhados.split(",") if parte.strip()]
    for endereco in reversed(cadeia):
        if not _e_confiavel(endereco):
            try:
                ipaddress.ip_address(endereco)
            except ValueError:
                return imediato
            return endereco

    return imediato
