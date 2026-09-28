"""Identidade e sessão do cliente.

`identificar_cliente` e `criar_sessao_cliente` são duas funções separadas de
propósito, em camadas diferentes: a primeira resolve QUEM é, a segunda abre a
sessão. É esse corte que permite plugar verificação por e-mail na v2 sem
reescrever nada — a verificação entra ENTRE as duas, e nem uma nem outra muda.

Nada aqui é compartilhado com a sessão de administrador além do utilitário de
token (seguranca/tokens.py), que não sabe de quem é o token.
"""

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from vip_api.erros.codigos import DADOS_INVALIDOS
from vip_api.erros.excecoes import AppError
from vip_api.modelos.cliente import Cliente, ClienteSessao
from vip_api.servicos.acesso import MODO_APROVACAO, modo_atual
from vip_api.seguranca.tokens import gerar_token, hash_do_token

DURACAO_SESSAO = timedelta(days=90)
# Renovação deslizante, mas não a cada requisição: só quando já se passaram
# 10 dias dos 90. Estender a sessão em toda visualização de página
# transformaria cada leitura do catálogo numa escrita no banco.
RENOVAR_QUANDO_FALTAR = timedelta(days=80)
# Mesma lógica para ultimo_acesso_em: uma atualização por dia por cliente
# basta para o painel, e evita um UPDATE por página vista.
INTERVALO_ULTIMO_ACESSO = timedelta(days=1)

_FORMATO_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalizar_email(email: str) -> str:
    return (email or "").strip().lower()


def identificar_cliente(sessao: Session, email: str) -> Cliente:
    """Normaliza, valida e devolve o cliente — criando na hora se não existir.

    Sem senha: decisão do cliente da No Fear, registrada em contrato. A
    consequência está em docs/limitacoes-conhecidas.md.
    """
    normalizado = normalizar_email(email)
    if not _FORMATO_EMAIL.match(normalizado) or len(normalizado) > 254:
        raise AppError(
            codigo=DADOS_INVALIDOS,
            mensagem="Há campos inválidos no envio.",
            status_code=400,
            campos={"email": "Informe um e-mail válido."},
        )

    # A coluna é citext: a busca já ignora caixa. A normalização aqui é para
    # não gravar "  Jose@X.com " com espaço e maiúscula no cadastro novo.
    cliente = sessao.scalar(select(Cliente).where(Cliente.email == normalizado))
    if cliente is None:
        cliente = Cliente(email=normalizado)
        # Com a loja no modo aprovação (seção 05), quem chega agora nasce
        # PENDENTE — senão o default 'aprovado' da coluna deixaria qualquer
        # e-mail novo passar pelo portão. Só na criação: quem já está
        # cadastrado nunca é trancado por o modo ter sido ligado depois.
        if modo_atual(sessao) == MODO_APROVACAO:
            cliente.acesso_status = "pendente"
        sessao.add(cliente)
        sessao.commit()
        sessao.refresh(cliente)

    return cliente


def criar_sessao_cliente(
    sessao: Session, cliente: Cliente, ip: str | None = None, user_agent: str | None = None
) -> str:
    """Abre a sessão e devolve o token EM TEXTO — o único momento em que ele
    existe fora do cookie. No banco vai só o hash."""
    token = gerar_token()
    agora = datetime.now(timezone.utc)

    sessao.add(
        ClienteSessao(
            cliente_id=cliente.id,
            token_hash=hash_do_token(token),
            criado_em=agora,
            expira_em=agora + DURACAO_SESSAO,
            ip=ip,
            user_agent=user_agent,
        )
    )
    sessao.commit()
    return token


def buscar_sessao_valida(sessao: Session, token: str) -> tuple[Cliente, ClienteSessao] | None:
    """Resolve o token do cookie em (cliente, sessão). None se inválido,
    expirado ou revogado — a rota traduz isso em 401."""
    if not token:
        return None

    agora = datetime.now(timezone.utc)
    linha = sessao.execute(
        select(Cliente, ClienteSessao)
        .join(ClienteSessao, ClienteSessao.cliente_id == Cliente.id)
        .where(
            ClienteSessao.token_hash == hash_do_token(token),
            ClienteSessao.revogado_em.is_(None),
            ClienteSessao.expira_em > agora,
        )
    ).first()

    if linha is None:
        return None
    return linha[0], linha[1]


def renovar_se_necessario(sessao: Session, cliente: Cliente, sessao_cliente: ClienteSessao) -> None:
    """Estende a sessão e marca o último acesso, mas só quando vale a escrita."""
    agora = datetime.now(timezone.utc)
    escreveu = False

    if sessao_cliente.expira_em - agora < RENOVAR_QUANDO_FALTAR:
        sessao.execute(
            update(ClienteSessao)
            .where(ClienteSessao.id == sessao_cliente.id)
            .values(expira_em=agora + DURACAO_SESSAO)
        )
        escreveu = True

    ultimo = cliente.ultimo_acesso_em
    if ultimo is None or agora - ultimo >= INTERVALO_ULTIMO_ACESSO:
        sessao.execute(
            update(Cliente).where(Cliente.id == cliente.id).values(ultimo_acesso_em=agora)
        )
        escreveu = True

    if escreveu:
        sessao.commit()


def encerrar_sessao_cliente(sessao: Session, token: str) -> None:
    """Revoga no BANCO. Limpar só o cookie deixaria o token válido para quem
    o tivesse copiado."""
    if not token:
        return
    sessao.execute(
        update(ClienteSessao)
        .where(
            ClienteSessao.token_hash == hash_do_token(token),
            ClienteSessao.revogado_em.is_(None),
        )
        .values(revogado_em=datetime.now(timezone.utc))
    )
    sessao.commit()


def atualizar_cliente(
    sessao: Session, cliente: Cliente, nome: str | None, telefone: str | None
) -> Cliente:
    """Edita nome e telefone. E-mail não entra: é a identidade da conta."""
    valores = {}
    if nome is not None:
        valores["nome"] = nome.strip() or None
    if telefone is not None:
        somente_digitos = re.sub(r"\D", "", telefone)
        valores["telefone"] = somente_digitos or None

    if valores:
        valores["atualizado_em"] = datetime.now(timezone.utc)
        sessao.execute(update(Cliente).where(Cliente.id == cliente.id).values(**valores))
        sessao.commit()
        sessao.refresh(cliente)

    return cliente
