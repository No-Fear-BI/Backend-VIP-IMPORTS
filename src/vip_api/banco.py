# DECISÃO: SQLAlchemy SÍNCRONO em todo o projeto — sem async_sessionmaker, sem
# create_async_engine. Nada no domínio (catálogo de leitura, sem alta
# concorrência de escrita) justifica a complexidade extra de sessão
# assíncrona; mantenha essa escolha em qualquer código futuro.
"""Engine, fábrica de sessão e a dependência que os endpoints usam com Depends."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from vip_api.configuracao import configuracao

engine = create_engine(configuracao.DATABASE_URL, pool_pre_ping=True)

SessaoLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def obter_sessao() -> Generator[Session, None, None]:
    """Uma sessão por requisição — `Depends(obter_sessao)` nos endpoints."""
    sessao = SessaoLocal()
    try:
        yield sessao
    finally:
        sessao.close()
