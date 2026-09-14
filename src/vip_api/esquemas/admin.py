"""Esquemas do acesso ao painel."""

from datetime import datetime

from vip_api.esquemas.base import EsquemaEntrada, EsquemaResposta


class LoginEntrada(EsquemaEntrada):
    # `str` puro nos dois: formato de e-mail e tamanho de senha não são
    # validados aqui de propósito. Recusar "e-mail inválido" antes de conferir
    # a senha devolveria uma resposta diferente da de credencial errada, e a
    # diferença já diz se o endereço existe no formato que o painel aceita.
    email: str
    senha: str


class AdminEu(EsquemaResposta):
    """Resposta de `POST /admin/sessao` e de `GET /admin/eu`. Sem `senhaHash`,
    óbvio, e sem `ativo`: administrador inativo não chega a ter sessão."""

    id: int
    nome: str
    email: str
    ultimo_login_em: datetime | None = None
    criado_em: datetime
