"""Esquemas do controle de entrada da loja (seção 05 do contrato)."""

from datetime import datetime
from typing import Literal

from vip_api.esquemas.base import EsquemaEntrada, EsquemaResposta

# Só os dois modos que têm rota. `senha_compartilhada` (modo 2) existe no
# enum do banco, mas POST /acesso/senha não foi construída: aceitar o modo
# aqui ligaria um portão sem porta. O Pydantic recusa com 400.
ModoAceito = Literal["aberto", "aprovacao"]
Decisao = Literal["aprovado", "recusado"]


class EstadoAcesso(EsquemaResposta):
    """GET /acesso/estado — diz ao frontend se pode navegar e qual tela mostrar.

    `situacao` é null sem sessão de cliente. `solicitacaoPendente` separa o
    "pendente que ainda não pediu" do "pedido enviado, aguardando".
    `mensagemBloqueio` vem sempre (null se o painel não escreveu nenhuma)."""

    modo: str
    pode_navegar: bool
    identificado: bool
    situacao: str | None = None
    solicitacao_pendente: bool
    mensagem_bloqueio: str | None = None


class SolicitarAcessoEntrada(EsquemaEntrada):
    # Opcionais: o cliente já existe (POST /clientes/identificar). O que vier
    # aqui atualiza o cadastro e fica congelado na solicitação.
    nome: str | None = None
    telefone: str | None = None


class SolicitacaoFila(EsquemaResposta):
    """Item de GET /admin/acesso/fila. E-mail, nome e telefone são a cópia
    congelada no pedido, não o cadastro atual."""

    id: int
    cliente_id: int
    email: str
    nome: str | None = None
    telefone: str | None = None
    criado_em: datetime


class DecidirAcessoEntrada(EsquemaEntrada):
    situacao: Decisao
    motivo: str | None = None


class DecisaoAcesso(EsquemaResposta):
    """Resposta de PATCH /admin/acesso/{clienteId}. `decididoEm` é null quando
    nada mudou (o cliente já estava na situação pedida, sem pedido aberto)."""

    cliente_id: int
    email: str
    situacao: str
    motivo: str | None = None
    decidido_em: datetime | None = None


class ConfiguracaoAcessoEntrada(EsquemaEntrada):
    """PATCH parcial: só o que vier no corpo muda."""

    modo: ModoAceito | None = None
    mensagem_bloqueio: str | None = None


class ConfiguracaoAcesso(EsquemaResposta):
    modo: str
    mensagem_bloqueio: str | None = None
    atualizado_em: datetime
