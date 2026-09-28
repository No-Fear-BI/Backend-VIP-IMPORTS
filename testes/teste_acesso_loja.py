"""Controle de entrada da loja — seção 05 do contrato, modo 3 (aprovação).

O que não pode quebrar, em ordem de estrago:
1. O painel NUNCA fica atrás do portão — senão a equipe se tranca do lado de
   fora e não consegue nem desligar o portão.
2. O site nasce aberto: a linha de acesso_config existe, em 'aberto'.
3. Quem já estava cadastrado quando o portão foi ligado continua entrando.
4. Pedir liberação duas vezes não estoura (índice único de uma pendente).
"""

import re
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from vip_api.dependencias.acesso import exigir_acesso_liberado
from vip_api.modelos.acesso import AcessoConfig, AcessoSolicitacao
from vip_api.modelos.cliente import Cliente
from vip_api.servicos import acesso as servico_acesso
from vip_api.servicos.cliente import criar_sessao_cliente

from testes.identidades import CLIENTE_DE_ORIGEM
from testes.rotas_registradas import eh_do_painel, rotas_da_api

CODIGOS_DO_PORTAO = {"ACESSO_PENDENTE", "ACESSO_RECUSADO"}

# Rotas públicas que ficam FORA do portão, por prefixo de segmento. Toda outra
# rota fora de /admin tem que estar atrás dele — rota nova que escapar quebra
# a varredura abaixo, e a saída é pôr no roteador certo ou declarar aqui.
FORA_DO_PORTAO = {
    "/api/v1/health": "healthcheck do Docker, sem sessão",
    "/api/v1/acesso": "é por aqui que o barrado entende o motivo e pede liberação",
    "/api/v1/clientes": "identificar é o primeiro passo do pedido; eu/sair só mexem na própria conta",
}


def _fora_do_portao(caminho: str) -> bool:
    return any(caminho == p or caminho.startswith(p + "/") for p in FORA_DO_PORTAO)


def _tem_portao(dependant) -> bool:
    return any(
        dep.call is exigir_acesso_liberado or _tem_portao(dep) for dep in dependant.dependencies
    )


def _caminho_concreto(caminho: str) -> str:
    """Troca `{parametro}` por um valor qualquer: o portão responde antes da
    validação dos parâmetros, então o valor não importa."""
    return re.sub(r"\{[^}]+\}", "1", caminho)


def _codigo_do_erro(resposta) -> str | None:
    if not resposta.headers.get("content-type", "").startswith("application/json"):
        return None
    corpo = resposta.json()
    return corpo.get("erro", {}).get("codigo") if isinstance(corpo, dict) else None


def _ligar_aprovacao(sessao, mensagem: str | None = None) -> None:
    config = sessao.get(AcessoConfig, 1)
    config.modo = "aprovacao"
    config.mensagem_bloqueio = mensagem
    sessao.commit()


def _logar(app_de_teste, sessao, cliente: Cliente) -> TestClient:
    http = TestClient(app_de_teste, client=CLIENTE_DE_ORIGEM)
    http.cookies.set("vip_sessao_cliente", criar_sessao_cliente(sessao, cliente))
    return http


def _novo_cliente(sessao, email: str, status: str) -> Cliente:
    pessoa = Cliente(email=email, acesso_status=status)
    sessao.add(pessoa)
    sessao.commit()
    sessao.refresh(pessoa)
    return pessoa


def _pendentes(sessao, cliente_id: int) -> int:
    return sessao.scalar(
        select(func.count())
        .select_from(AcessoSolicitacao)
        .where(
            AcessoSolicitacao.cliente_id == cliente_id,
            AcessoSolicitacao.situacao == "pendente",
        )
    )


# --- semente e ponto de partida ------------------------------------------------


def teste_a_migracao_semeia_a_config_no_modo_aberto(sessao):
    config = sessao.get(AcessoConfig, 1)
    assert config is not None, "a revisão 0013 precisa semear a linha única de acesso_config"
    assert config.modo == "aberto"


def teste_cliente_novo_nasce_aprovado_por_padrao(sessao):
    pessoa = Cliente(email="padrao@teste.local")
    sessao.add(pessoa)
    sessao.commit()
    sessao.refresh(pessoa)
    assert pessoa.acesso_status == "aprovado"


# --- modo aberto não barra nada ------------------------------------------------


def teste_modo_aberto_nao_barra_nenhuma_rota_publica(sem_sessao, app_de_teste, sessao):
    pendente = _novo_cliente(sessao, "pendente@teste.local", "pendente")
    recusado = _novo_cliente(sessao, "recusado@teste.local", "recusado")

    for http in (sem_sessao, _logar(app_de_teste, sessao, pendente), _logar(app_de_teste, sessao, recusado)):
        for metodo, caminho, _rota in rotas_da_api():
            # Sair revogaria a sessão no meio da varredura e o resto rodaria
            # como anônimo.
            if eh_do_painel(caminho) or caminho == "/api/v1/clientes/sair":
                continue
            resposta = http.request(metodo, _caminho_concreto(caminho))
            assert _codigo_do_erro(resposta) not in CODIGOS_DO_PORTAO, f"{metodo} {caminho} barrou no modo aberto"


def teste_modo_aberto_estado_diz_que_pode_navegar(sem_sessao):
    corpo = sem_sessao.get("/api/v1/acesso/estado").json()
    assert corpo["modo"] == "aberto"
    assert corpo["podeNavegar"] is True
    assert corpo["identificado"] is False
    assert corpo["situacao"] is None


def teste_modo_aberto_home_responde_sem_sessao(sem_sessao):
    assert sem_sessao.get("/api/v1/home").status_code == 200
    assert sem_sessao.get("/api/v1/produtos").status_code == 200


# --- modo aprovação -------------------------------------------------------------


def teste_aprovacao_barra_visitante_sem_sessao_com_401(sem_sessao, sessao):
    _ligar_aprovacao(sessao)
    resposta = sem_sessao.get("/api/v1/home")
    assert resposta.status_code == 401
    assert resposta.json()["erro"]["codigo"] == "NAO_IDENTIFICADO"


def teste_aprovacao_barra_cliente_pendente(app_de_teste, sessao):
    pendente = _novo_cliente(sessao, "pendente@teste.local", "pendente")
    _ligar_aprovacao(sessao, "Loja só para convidados.")
    http = _logar(app_de_teste, sessao, pendente)

    resposta = http.get("/api/v1/produtos")
    assert resposta.status_code == 403
    erro = resposta.json()["erro"]
    assert erro["codigo"] == "ACESSO_PENDENTE"
    assert erro["mensagem"] == "Loja só para convidados."
    assert erro["detalhes"] == {"situacao": "pendente"}


def teste_aprovacao_barra_cliente_recusado(app_de_teste, sessao):
    recusado = _novo_cliente(sessao, "recusado@teste.local", "recusado")
    _ligar_aprovacao(sessao)
    resposta = _logar(app_de_teste, sessao, recusado).get("/api/v1/home")
    assert resposta.status_code == 403
    assert resposta.json()["erro"]["codigo"] == "ACESSO_RECUSADO"


def teste_aprovacao_nao_barra_cliente_aprovado(cliente_logado, sessao, catalogo):
    _ligar_aprovacao(sessao)
    for caminho in ("/api/v1/home", "/api/v1/produtos", "/api/v1/marcas", "/api/v1/colecoes",
                    "/api/v1/favoritos", "/api/v1/carrinho", "/api/v1/selecoes"):
        resposta = cliente_logado.get(caminho)
        assert resposta.status_code == 200, f"{caminho}: {resposta.status_code} {resposta.text}"


def teste_quem_ja_estava_cadastrado_nao_e_trancado_ao_ligar_o_modo(admin_logado, cliente_logado, sessao, cliente):
    """O cliente existe ANTES do portão ser ligado — pelo painel, como na
    vida real. Continua aprovado e continua entrando."""
    resposta = admin_logado.patch("/api/v1/admin/configuracao/acesso", json={"modo": "aprovacao"})
    assert resposta.status_code == 200

    sessao.refresh(cliente)
    assert cliente.acesso_status == "aprovado"
    assert cliente_logado.get("/api/v1/home").status_code == 200
    assert cliente_logado.get("/api/v1/acesso/estado").json()["podeNavegar"] is True


def teste_identificar_no_modo_aprovacao_cria_cliente_novo_pendente(sem_sessao, sessao):
    _ligar_aprovacao(sessao)
    assert sem_sessao.post("/api/v1/clientes/identificar", json={"email": "novo@teste.local"}).status_code == 200

    novo = sessao.scalar(select(Cliente).where(Cliente.email == "novo@teste.local"))
    assert novo.acesso_status == "pendente"
    # O cookie que o identificar acabou de gravar já está no cliente HTTP.
    assert sem_sessao.get("/api/v1/home").json()["erro"]["codigo"] == "ACESSO_PENDENTE"


def teste_identificar_no_modo_aprovacao_nao_rebaixa_quem_ja_existe(sem_sessao, sessao, cliente):
    _ligar_aprovacao(sessao)
    assert sem_sessao.post("/api/v1/clientes/identificar", json={"email": cliente.email}).status_code == 200
    sessao.refresh(cliente)
    assert cliente.acesso_status == "aprovado"


def teste_identificar_no_modo_aberto_cria_cliente_aprovado(sem_sessao, sessao):
    sem_sessao.post("/api/v1/clientes/identificar", json={"email": "aberto@teste.local"})
    novo = sessao.scalar(select(Cliente).where(Cliente.email == "aberto@teste.local"))
    assert novo.acesso_status == "aprovado"


# --- o que fica fora do portão ---------------------------------------------------


def teste_toda_rota_publica_fora_das_excecoes_esta_atras_do_portao(capsys):
    """Varredura estrutural: nenhuma rota pública escapa sem declaração, e
    nenhuma rota do painel ou das exceções carrega o portão."""
    sem_portao, portao_indevido = [], []
    for metodo, caminho, rota in rotas_da_api():
        protegida = _tem_portao(rota.dependant)
        deve_ficar_fora = eh_do_painel(caminho) or _fora_do_portao(caminho)
        if deve_ficar_fora and protegida:
            portao_indevido.append(f"{metodo} {caminho}")
        elif not deve_ficar_fora and not protegida:
            sem_portao.append(f"{metodo} {caminho}")

    assert not portao_indevido, f"portão da loja em rota que precisa ficar fora: {portao_indevido}"
    assert not sem_portao, (
        f"rota pública fora do portão sem declaração em FORA_DO_PORTAO: {sem_portao}"
    )


def teste_a_varredura_enxerga_o_portao():
    """Prova que o coletor não está devolvendo 'tudo sem portão' por engano."""
    atras = [c for _m, c, r in rotas_da_api() if _tem_portao(r.dependant)]
    assert "/api/v1/home" in atras
    assert "/api/v1/produtos" in atras
    assert "/api/v1/carrinho" in atras


def teste_aprovacao_barra_de_verdade_toda_rota_atras_do_portao(app_de_teste, sessao):
    """A mesma varredura, pelo comportamento: cliente pendente leva 403 do
    portão em TODA rota pública fora das exceções."""
    pendente = _novo_cliente(sessao, "pendente@teste.local", "pendente")
    _ligar_aprovacao(sessao)
    http = _logar(app_de_teste, sessao, pendente)

    for metodo, caminho, _rota in rotas_da_api():
        if eh_do_painel(caminho) or _fora_do_portao(caminho):
            continue
        resposta = http.request(metodo, _caminho_concreto(caminho))
        assert resposta.status_code == 403, f"{metodo} {caminho} passou pelo portão"
        assert resposta.json()["erro"]["codigo"] == "ACESSO_PENDENTE"


@pytest.mark.parametrize(
    "metodo,caminho",
    [
        ("GET", "/api/v1/health"),
        ("GET", "/api/v1/acesso/estado"),
        ("GET", "/api/v1/clientes/eu"),
        ("PATCH", "/api/v1/clientes/eu"),
    ],
)
def teste_aprovacao_nao_barra_as_excecoes(app_de_teste, sessao, metodo, caminho):
    pendente = _novo_cliente(sessao, "pendente@teste.local", "pendente")
    _ligar_aprovacao(sessao)
    resposta = _logar(app_de_teste, sessao, pendente).request(metodo, caminho, json={})
    assert resposta.status_code == 200, resposta.text


def teste_painel_nunca_e_barrado_pelo_portao(admin_logado, app_de_teste, sessao):
    """Toda leitura do painel, com o portão ligado e — de propósito — um
    cookie de cliente PENDENTE junto do cookie de admin. Nenhuma pode
    responder com o código do portão."""
    pendente = _novo_cliente(sessao, "pendente@teste.local", "pendente")
    _ligar_aprovacao(sessao)
    admin_logado.cookies.set("vip_sessao_cliente", criar_sessao_cliente(sessao, pendente))

    for metodo, caminho, _rota in rotas_da_api():
        if not eh_do_painel(caminho) or metodo != "GET":
            continue
        resposta = admin_logado.get(_caminho_concreto(caminho))
        assert _codigo_do_erro(resposta) not in CODIGOS_DO_PORTAO, f"GET {caminho} barrado pelo portão"


def teste_admin_desliga_o_portao_com_ele_ligado(admin_logado, sem_sessao, sessao):
    _ligar_aprovacao(sessao)
    assert sem_sessao.get("/api/v1/home").status_code == 401

    resposta = admin_logado.patch("/api/v1/admin/configuracao/acesso", json={"modo": "aberto"})
    assert resposta.status_code == 200
    assert sem_sessao.get("/api/v1/home").status_code == 200


# --- POST /acesso/solicitar ------------------------------------------------------


def teste_solicitar_duas_vezes_nao_quebra_e_nao_duplica(app_de_teste, sessao):
    pendente = _novo_cliente(sessao, "pendente@teste.local", "pendente")
    _ligar_aprovacao(sessao)
    http = _logar(app_de_teste, sessao, pendente)

    primeira = http.post("/api/v1/acesso/solicitar", json={"nome": "Maria", "telefone": "(11) 99999-0000"})
    segunda = http.post("/api/v1/acesso/solicitar", json={})
    assert primeira.status_code == 200, primeira.text
    assert segunda.status_code == 200, segunda.text
    assert segunda.json()["solicitacaoPendente"] is True
    assert segunda.json()["podeNavegar"] is False
    assert _pendentes(sessao, pendente.id) == 1

    pedido = sessao.scalar(select(AcessoSolicitacao).where(AcessoSolicitacao.cliente_id == pendente.id))
    assert (pedido.email, pedido.nome, pedido.telefone) == ("pendente@teste.local", "Maria", "11999990000")


def teste_solicitar_em_corrida_cai_no_indice_e_nao_estoura(app_de_teste, sessao, monkeypatch):
    """Simula a corrida: a checagem prévia não vê o pedido que outra
    requisição acabou de gravar, e o INSERT bate no índice único parcial."""
    pendente = _novo_cliente(sessao, "pendente@teste.local", "pendente")
    _ligar_aprovacao(sessao)
    sessao.add(AcessoSolicitacao(cliente_id=pendente.id, email=pendente.email))
    sessao.commit()

    original = servico_acesso._solicitacao_pendente
    chamadas = {"n": 0}

    def cego_na_primeira(sessao_, cliente_id):
        chamadas["n"] += 1
        return None if chamadas["n"] == 1 else original(sessao_, cliente_id)

    monkeypatch.setattr(servico_acesso, "_solicitacao_pendente", cego_na_primeira)

    resposta = _logar(app_de_teste, sessao, pendente).post("/api/v1/acesso/solicitar", json={})
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["solicitacaoPendente"] is True
    assert _pendentes(sessao, pendente.id) == 1


def teste_solicitar_sem_sessao_e_401(sem_sessao, sessao):
    _ligar_aprovacao(sessao)
    resposta = sem_sessao.post("/api/v1/acesso/solicitar", json={})
    assert resposta.status_code == 401


def teste_solicitar_aprovado_ou_modo_aberto_nao_cria_nada(cliente_logado, app_de_teste, sessao, cliente):
    pendente = _novo_cliente(sessao, "pendente@teste.local", "pendente")
    # modo aberto: nada a pedir
    assert _logar(app_de_teste, sessao, pendente).post("/api/v1/acesso/solicitar", json={}).status_code == 200
    assert _pendentes(sessao, pendente.id) == 0

    _ligar_aprovacao(sessao)
    # já aprovado: nada a pedir
    assert cliente_logado.post("/api/v1/acesso/solicitar", json={}).json()["podeNavegar"] is True
    assert _pendentes(sessao, cliente.id) == 0


def teste_recusado_nao_reabre_pedido_sozinho(app_de_teste, sessao):
    recusado = _novo_cliente(sessao, "recusado@teste.local", "recusado")
    _ligar_aprovacao(sessao)
    resposta = _logar(app_de_teste, sessao, recusado).post("/api/v1/acesso/solicitar", json={})
    assert resposta.status_code == 403
    assert resposta.json()["erro"]["codigo"] == "ACESSO_RECUSADO"
    assert _pendentes(sessao, recusado.id) == 0


def teste_estado_de_quem_pediu(app_de_teste, sessao):
    pendente = _novo_cliente(sessao, "pendente@teste.local", "pendente")
    _ligar_aprovacao(sessao, "Aguarde a liberação.")
    http = _logar(app_de_teste, sessao, pendente)

    antes = http.get("/api/v1/acesso/estado").json()
    assert antes == {
        "modo": "aprovacao",
        "podeNavegar": False,
        "identificado": True,
        "situacao": "pendente",
        "solicitacaoPendente": False,
        "mensagemBloqueio": "Aguarde a liberação.",
    }
    http.post("/api/v1/acesso/solicitar", json={})
    assert http.get("/api/v1/acesso/estado").json()["solicitacaoPendente"] is True


# --- painel: fila, decisão, configuração --------------------------------------------


def teste_fila_lista_so_pendentes_do_mais_antigo(admin_logado, sessao):
    a = _novo_cliente(sessao, "a@teste.local", "pendente")
    b = _novo_cliente(sessao, "b@teste.local", "pendente")
    c = _novo_cliente(sessao, "c@teste.local", "recusado")
    for pessoa in (a, b):
        sessao.add(AcessoSolicitacao(cliente_id=pessoa.id, email=pessoa.email))
        sessao.commit()

    sessao.add(AcessoSolicitacao(cliente_id=c.id, email=c.email, situacao="recusado",
                                 decidido_em=datetime.now(timezone.utc)))
    sessao.commit()

    corpo = admin_logado.get("/api/v1/admin/acesso/fila").json()
    assert [item["email"] for item in corpo["dados"]] == ["a@teste.local", "b@teste.local"]
    assert corpo["paginacao"]["total"] == 2
    assert corpo["paginacao"]["pagina"] == 1
    assert set(corpo["dados"][0]) == {"id", "clienteId", "email", "nome", "telefone", "criadoEm"}


def teste_aprovar_fecha_o_pedido_e_libera_o_cliente(admin_logado, app_de_teste, sessao, administrador):
    pendente = _novo_cliente(sessao, "pendente@teste.local", "pendente")
    _ligar_aprovacao(sessao)
    http = _logar(app_de_teste, sessao, pendente)
    http.post("/api/v1/acesso/solicitar", json={})

    resposta = admin_logado.patch(f"/api/v1/admin/acesso/{pendente.id}", json={"situacao": "aprovado"})
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["decididoEm"] is not None

    pedido = sessao.scalar(select(AcessoSolicitacao).where(AcessoSolicitacao.cliente_id == pendente.id))
    sessao.refresh(pedido)
    sessao.refresh(pendente)
    assert pedido.situacao == "aprovado"
    assert pedido.decidido_por_admin_id == administrador.id
    assert pedido.decidido_em is not None
    assert pendente.acesso_status == "aprovado"
    assert http.get("/api/v1/home").status_code == 200
    assert admin_logado.get("/api/v1/admin/acesso/fila").json()["dados"] == []


def teste_recusar_com_motivo(admin_logado, sessao):
    pendente = _novo_cliente(sessao, "pendente@teste.local", "pendente")
    sessao.add(AcessoSolicitacao(cliente_id=pendente.id, email=pendente.email))
    sessao.commit()

    resposta = admin_logado.patch(
        f"/api/v1/admin/acesso/{pendente.id}", json={"situacao": "recusado", "motivo": " sem vínculo "}
    )
    assert resposta.status_code == 200
    assert resposta.json()["motivo"] == "sem vínculo"
    sessao.refresh(pendente)
    assert pendente.acesso_status == "recusado"


def teste_revogar_aprovado_sem_pedido_grava_historico(admin_logado, cliente_logado, sessao, cliente, administrador):
    _ligar_aprovacao(sessao)
    resposta = admin_logado.patch(f"/api/v1/admin/acesso/{cliente.id}", json={"situacao": "recusado"})
    assert resposta.status_code == 200

    linhas = sessao.scalars(select(AcessoSolicitacao).where(AcessoSolicitacao.cliente_id == cliente.id)).all()
    assert len(linhas) == 1
    assert linhas[0].situacao == "recusado"
    assert linhas[0].decidido_em is not None
    assert linhas[0].decidido_por_admin_id == administrador.id
    assert cliente_logado.get("/api/v1/home").json()["erro"]["codigo"] == "ACESSO_RECUSADO"

    # Clique repetido: nada muda, nenhuma linha nova.
    de_novo = admin_logado.patch(f"/api/v1/admin/acesso/{cliente.id}", json={"situacao": "recusado"})
    assert de_novo.status_code == 200
    assert de_novo.json()["decididoEm"] is None
    assert len(sessao.scalars(select(AcessoSolicitacao).where(AcessoSolicitacao.cliente_id == cliente.id)).all()) == 1


def teste_decidir_cliente_inexistente_e_404(admin_logado):
    resposta = admin_logado.patch("/api/v1/admin/acesso/999999", json={"situacao": "aprovado"})
    assert resposta.status_code == 404
    assert resposta.json()["erro"]["codigo"] == "CLIENTE_NAO_ENCONTRADO"


def teste_decidir_pendente_nao_e_decisao(admin_logado, cliente):
    resposta = admin_logado.patch(f"/api/v1/admin/acesso/{cliente.id}", json={"situacao": "pendente"})
    assert resposta.status_code == 400


def teste_configuracao_grava_quem_mudou_e_a_mensagem(admin_logado, sessao, administrador):
    resposta = admin_logado.patch(
        "/api/v1/admin/configuracao/acesso",
        json={"modo": "aprovacao", "mensagemBloqueio": "  Loja fechada para convidados.  "},
    )
    assert resposta.status_code == 200
    assert resposta.json()["modo"] == "aprovacao"
    assert resposta.json()["mensagemBloqueio"] == "Loja fechada para convidados."

    # PATCH parcial: só a mensagem, o modo fica.
    so_mensagem = admin_logado.patch("/api/v1/admin/configuracao/acesso", json={"mensagemBloqueio": None})
    assert so_mensagem.json() == {**so_mensagem.json(), "modo": "aprovacao", "mensagemBloqueio": None}

    config = sessao.get(AcessoConfig, 1)
    sessao.refresh(config)
    assert config.atualizado_por_admin_id == administrador.id


@pytest.mark.parametrize("corpo", [{"modo": "senha_compartilhada"}, {"modo": None}, {"modo": "fechado"}])
def teste_configuracao_recusa_modo_sem_rota_ou_invalido(admin_logado, sessao, corpo):
    resposta = admin_logado.patch("/api/v1/admin/configuracao/acesso", json=corpo)
    assert resposta.status_code == 400
    assert sessao.get(AcessoConfig, 1).modo == "aberto"


def teste_cliente_nao_mexe_na_configuracao(cliente_logado):
    resposta = cliente_logado.patch("/api/v1/admin/configuracao/acesso", json={"modo": "aberto"})
    assert resposta.status_code == 403
    assert resposta.json()["erro"]["codigo"] == "SEM_PERMISSAO"
