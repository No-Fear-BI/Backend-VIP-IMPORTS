"""Tarefa 79: a varredura do painel não cobre rota de escrita FORA do painel.

`teste_protecao_admin.py` garante que tudo sob /api/v1/admin exige sessão de
admin. Ele não diz nada sobre um `DELETE /api/v1/produtos/{id}` pendurado no
roteador público: essa rota nunca passaria pela varredura, e o catálogo
ficaria editável por qualquer visitante.

Este teste lê o roteador e exige que TODO POST, PATCH, PUT e DELETE fora do
painel esteja na lista abaixo. Rota de escrita nova fora de /admin quebra o
teste, e a única saída é acrescentar uma linha aqui — que aparece no diff do
PR com a justificativa ao lado.
"""

from fastapi import APIRouter, FastAPI

from testes.rotas_registradas import eh_do_painel, rotas_registradas

METODOS_DE_ESCRITA = {"POST", "PATCH", "PUT", "DELETE"}

# Rotas públicas de escrita: todas agem sobre a PRÓPRIA conta de quem chama
# (ou abrem essa conta), nunca sobre o catálogo ou sobre outro cliente.
ESCRITA_PUBLICA = {
    ("POST", "/api/v1/clientes/identificar"): "identificação por e-mail, sem senha (tarefa 40)",
    ("PATCH", "/api/v1/clientes/eu"): "o cliente edita o próprio nome e telefone (seção 03)",
    ("POST", "/api/v1/clientes/sair"): "encerra a própria sessão",
    ("POST", "/api/v1/favoritos"): "favoritos do próprio cliente (tarefa 43)",
    ("DELETE", "/api/v1/favoritos/{produtoId}"): "favoritos do próprio cliente (tarefa 43)",
    ("POST", "/api/v1/carrinho"): "carrinho do próprio cliente (tarefa 43)",
    ("PATCH", "/api/v1/carrinho/{itemId}"): "troca de variação no próprio carrinho (tarefa 46)",
    ("DELETE", "/api/v1/carrinho/{itemId}"): "remoção do próprio carrinho (tarefa 43)",
    ("POST", "/api/v1/carrinho/migrar"): "carrinho anônimo para a conta (tarefa 47)",
    ("POST", "/api/v1/selecoes"): "envio da seleção para o WhatsApp (tarefa 44)",
    ("POST", "/api/v1/acesso/solicitar"): "o cliente pede a liberação da própria conta (seção 05, modo aprovação)",
}


def escrita_fora_do_painel(aplicacao=None) -> list[tuple[str, str]]:
    argumentos = () if aplicacao is None else (aplicacao,)
    return [
        (metodo, caminho)
        for metodo, caminho, _rota in rotas_registradas(*argumentos)
        if metodo in METODOS_DE_ESCRITA and not eh_do_painel(caminho)
    ]


def teste_toda_escrita_fora_do_painel_esta_declarada(capsys):
    encontradas = escrita_fora_do_painel()

    with capsys.disabled():
        print(f"\n  rotas de escrita fora de /api/v1/admin: {len(encontradas)}")
        for metodo, caminho in encontradas:
            motivo = ESCRITA_PUBLICA.get((metodo, caminho), "!!! NÃO DECLARADA !!!")
            print(f"    {metodo:<7} {caminho:<34} {motivo}")

    nao_declaradas = [rota for rota in encontradas if rota not in ESCRITA_PUBLICA]
    assert not nao_declaradas, (
        "rota de escrita fora do painel sem declaração em ESCRITA_PUBLICA: "
        + ", ".join(f"{m} {c}" for m, c in nao_declaradas)
        + " — ou ela vai para o roteador protegido do painel, ou entra na lista com a justificativa"
    )


def teste_declaracoes_correspondem_a_rotas_que_existem():
    """Declaração sem rota é lixo que um dia cobre uma rota nova de mesmo nome."""
    sobrando = set(ESCRITA_PUBLICA) - set(escrita_fora_do_painel())
    assert not sobrando, f"declaradas em ESCRITA_PUBLICA mas inexistentes: {sorted(sobrando)}"


def teste_a_varredura_enxerga_escrita_nova_fora_do_painel():
    """Prova que o coletor acha uma escrita acrescentada fora do painel — e que
    `/api/v1/administracao` não passa por painel só por começar com as mesmas
    letras. Aplicação descartável: a real não ganha rota de mentira."""
    solto = APIRouter()

    @solto.delete("/produtos/{codigo}")
    def _apagar_produto_de_mentira(codigo: str) -> dict:
        return {}

    @solto.post("/administracao/importar")
    def _importar_de_mentira() -> dict:
        return {}

    versionado = APIRouter(prefix="/api/v1")
    versionado.include_router(solto)
    descartavel = FastAPI()
    descartavel.include_router(versionado)

    achadas = escrita_fora_do_painel(descartavel)
    assert ("DELETE", "/api/v1/produtos/{codigo}") in achadas
    assert ("POST", "/api/v1/administracao/importar") in achadas
