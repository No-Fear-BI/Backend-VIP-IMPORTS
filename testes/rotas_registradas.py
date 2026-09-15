"""As rotas que a aplicação REALMENTE registra, lidas do roteador do FastAPI.

Compartilhado pelos testes que varrem a aplicação inteira (proteção do painel,
escrita fora do painel, vazamento em erro). Nenhum deles tem lista de rotas
escrita à mão: rota nova entra na varredura no dia em que é registrada.
"""

from fastapi.routing import APIRoute

from vip_api.principal import app

METODOS_DO_FRAMEWORK = {"HEAD", "OPTIONS"}


def _planas(roteador, herdado: str = ""):
    """Achata a árvore de roteadores em (caminho completo, rota).

    Algumas versões do FastAPI não copiam as rotas dos roteadores incluídos
    para dentro de `app.routes`: guardam um embrulho com o roteador original,
    e a árvore continua em pé. Daí a recursão.

    A conta do prefixo tem uma sutileza: o prefixo do roteador que DECLAROU a
    rota já está no `path` dela (`APIRouter(prefix="/admin")` + `@get("/eu")`
    dá `/admin/eu`). O que falta é o prefixo dos roteadores ACIMA — por isso a
    folha usa `herdado`, e só os filhos recebem `herdado + prefixo`.
    """
    meu = herdado + getattr(roteador, "prefix", "")
    for rota in getattr(roteador, "routes", ()):
        interno = getattr(rota, "original_router", None)
        if interno is not None:
            yield from _planas(interno, meu)
        elif getattr(rota, "methods", None):
            yield herdado + getattr(rota, "path", ""), rota


def rotas_registradas(aplicacao=app) -> list[tuple[str, str, object]]:
    """(método, caminho completo, rota), ordenado por caminho e método."""
    encontradas = []
    for caminho, rota in _planas(aplicacao.router):
        for metodo in sorted(rota.methods):
            if metodo not in METODOS_DO_FRAMEWORK:
                encontradas.append((metodo, caminho, rota))
    return sorted(encontradas, key=lambda item: (item[1], item[0]))


def rotas_da_api(aplicacao=app) -> list[tuple[str, str, APIRoute]]:
    """Só as rotas da API — ficam de fora as do próprio FastAPI (`/docs`,
    `/openapi.json`), que não são endpoints nossos."""
    return [item for item in rotas_registradas(aplicacao) if isinstance(item[2], APIRoute)]


def eh_do_painel(caminho: str, prefixo: str = "/api/v1/admin") -> bool:
    """Por SEGMENTO, não por começo de texto: `/api/v1/administracao` não é
    painel só porque começa com as mesmas letras."""
    return caminho == prefixo or caminho.startswith(prefixo + "/")
