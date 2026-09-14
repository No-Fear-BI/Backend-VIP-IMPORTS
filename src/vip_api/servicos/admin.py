"""Identidade e sessão do ADMINISTRADOR.

Espelha servicos/cliente.py de propósito, sem compartilhar nada com ele além
de seguranca/tokens.py, que não sabe de quem é o token. Outra tabela, outro
prazo, outra dependência. As trinta linhas parecidas aqui embaixo são mais
baratas que um `criar_sessao(tipo=...)` em que alguém troca o argumento e um
visitante entra no painel.

Duas diferenças de comportamento em relação ao cliente, ambas deliberadas:

- 12 horas SEM renovação deslizante. A sessão do cliente dura 90 dias e se
  estende com o uso porque o custo de deslogar quem só quer montar uma lista é
  perder a venda. O painel é ferramenta de trabalho protegida por senha, e
  expõe o CRUD inteiro do catálogo: login novo por dia é o preço certo.
- Senha, com argon2 — e com o mesmo tempo de resposta para e-mail que não
  existe, senha errada e conta inativa.
"""

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from vip_api.erros.codigos import CREDENCIAIS_INVALIDAS, DADOS_INVALIDOS
from vip_api.erros.excecoes import AppError
from vip_api.modelos.admin import AdminSessao, Administrador
from vip_api.seguranca.senhas import (
    conferir_senha,
    gastar_tempo_de_verificacao,
    gerar_hash,
)
from vip_api.seguranca.tokens import gerar_token, hash_do_token

DURACAO_SESSAO = timedelta(hours=12)
TAMANHO_MINIMO_SENHA = 10

_FORMATO_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalizar_email(email: str) -> str:
    return (email or "").strip().lower()


def autenticar_administrador(sessao: Session, email: str, senha: str) -> Administrador:
    """Confere e-mail e senha, ou levanta 401 — sempre o MESMO 401.

    E-mail que não existe, senha errada e conta inativa devolvem o mesmo
    código, a mesma mensagem e gastam o mesmo tempo: nos dois casos em que não
    há hash real para conferir, o argon2 roda contra um hash descartável. A
    diferença de tempo entre "conferiu" e "nem tentou" é de duas ordens de
    grandeza — sem esse cuidado, quem cronometra a resposta descobre quais
    e-mails são de administrador.
    """
    normalizado = normalizar_email(email)
    administrador = sessao.scalar(
        select(Administrador).where(Administrador.email == normalizado)
    )

    if administrador is None or not administrador.ativo:
        gastar_tempo_de_verificacao(senha)
        raise _credenciais_invalidas()

    if not conferir_senha(senha, administrador.senha_hash):
        raise _credenciais_invalidas()

    return administrador


def _credenciais_invalidas() -> AppError:
    return AppError(
        codigo=CREDENCIAIS_INVALIDAS,
        mensagem="E-mail ou senha inválidos.",
        status_code=401,
    )


def criar_sessao_admin(
    sessao: Session,
    administrador: Administrador,
    ip: str | None = None,
    user_agent: str | None = None,
) -> str:
    """Abre a sessão e devolve o token EM TEXTO — no banco vai só o hash."""
    token = gerar_token()
    agora = datetime.now(timezone.utc)

    sessao.add(
        AdminSessao(
            administrador_id=administrador.id,
            token_hash=hash_do_token(token),
            criado_em=agora,
            expira_em=agora + DURACAO_SESSAO,
            ip=ip,
            user_agent=user_agent,
        )
    )
    sessao.execute(
        update(Administrador)
        .where(Administrador.id == administrador.id)
        .values(ultimo_login_em=agora)
    )
    sessao.commit()
    return token


def buscar_sessao_valida_admin(
    sessao: Session, token: str
) -> tuple[Administrador, AdminSessao] | None:
    """Resolve o token do cookie em (administrador, sessão). None quando o
    token não existe, expirou, foi revogado, a conta foi desativada ou a senha
    mudou depois que a sessão abriu."""
    if not token:
        return None

    agora = datetime.now(timezone.utc)
    linha = sessao.execute(
        select(Administrador, AdminSessao)
        .join(AdminSessao, AdminSessao.administrador_id == Administrador.id)
        .where(
            AdminSessao.token_hash == hash_do_token(token),
            AdminSessao.revogado_em.is_(None),
            AdminSessao.expira_em > agora,
            Administrador.ativo.is_(True),
            # Segunda trava da troca de senha: mesmo que uma revogação tenha
            # falhado, sessão aberta antes da troca não vale mais.
            AdminSessao.criado_em >= Administrador.senha_alterada_em,
        )
    ).first()

    if linha is None:
        return None
    return linha[0], linha[1]


def encerrar_sessao_admin(sessao: Session, token: str) -> None:
    """Revoga no BANCO. Limpar só o cookie deixaria o token válido para quem o
    tivesse copiado."""
    if not token:
        return
    sessao.execute(
        update(AdminSessao)
        .where(
            AdminSessao.token_hash == hash_do_token(token),
            AdminSessao.revogado_em.is_(None),
        )
        .values(revogado_em=datetime.now(timezone.utc))
    )
    sessao.commit()


def revogar_sessoes_do_administrador(sessao: Session, administrador_id: int) -> int:
    """Derruba TODAS as sessões abertas daquele administrador. Devolve quantas
    caíram, para o comando de linha dizer o que fez."""
    resultado = sessao.execute(
        update(AdminSessao)
        .where(
            AdminSessao.administrador_id == administrador_id,
            AdminSessao.revogado_em.is_(None),
        )
        .values(revogado_em=datetime.now(timezone.utc))
    )
    sessao.commit()
    return resultado.rowcount or 0


# ======================================================================
# Usados só pelos comandos de linha (scripts/criar_admin.py e
# scripts/trocar_senha_admin.py). NÃO existe rota para nenhum dos dois: a
# proposta (item 2.4) não contratou cadastro nem troca de senha pela API.
# ======================================================================


def validar_email(email: str) -> str:
    normalizado = normalizar_email(email)
    if not _FORMATO_EMAIL.match(normalizado) or len(normalizado) > 254:
        raise AppError(
            codigo=DADOS_INVALIDOS,
            mensagem="Informe um e-mail válido.",
            status_code=400,
            campos={"email": "Informe um e-mail válido."},
        )
    return normalizado


def validar_senha(senha: str) -> str:
    if len(senha) < TAMANHO_MINIMO_SENHA:
        raise AppError(
            codigo=DADOS_INVALIDOS,
            mensagem=f"A senha precisa ter ao menos {TAMANHO_MINIMO_SENHA} caracteres.",
            status_code=400,
            campos={"senha": "Senha curta demais."},
        )
    return senha


def buscar_por_email(sessao: Session, email: str) -> Administrador | None:
    return sessao.scalar(
        select(Administrador).where(Administrador.email == normalizar_email(email))
    )


def criar_administrador(
    sessao: Session, email: str, nome: str, senha: str
) -> Administrador:
    administrador = Administrador(
        email=validar_email(email), nome=nome.strip(), senha_hash=gerar_hash(validar_senha(senha))
    )
    sessao.add(administrador)
    sessao.commit()
    sessao.refresh(administrador)
    return administrador


def trocar_senha(sessao: Session, administrador: Administrador, senha: str) -> int:
    """Grava a senha nova, marca `senha_alterada_em` e derruba o que estiver
    aberto. As três coisas juntas: trocar a senha porque ela pode ter vazado e
    deixar a sessão de quem vazou aberta não resolve nada."""
    agora = datetime.now(timezone.utc)
    sessao.execute(
        update(Administrador)
        .where(Administrador.id == administrador.id)
        .values(
            senha_hash=gerar_hash(validar_senha(senha)),
            senha_alterada_em=agora,
            atualizado_em=agora,
        )
    )
    sessao.commit()
    return revogar_sessoes_do_administrador(sessao, administrador.id)
