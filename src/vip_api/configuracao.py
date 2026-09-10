"""Configuração da aplicação, lida do ambiente. Instância única em `configuracao`,
importada por todo o resto do pacote — nunca instancie `Configuracao()` de novo."""

from typing import Annotated, Literal, Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Configuracao(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Sem padrão: carrega credencial do banco, nunca fica embutida no código.
    DATABASE_URL: str

    AMBIENTE: Literal["desenvolvimento", "producao"] = "desenvolvimento"
    # NoDecode: sem isso, pydantic-settings tenta ler o valor do .env como
    # JSON (por ser uma lista) e explode antes do nosso validador rodar.
    # Com NoDecode a string crua "http://a,http://b" chega ao validador abaixo.
    ORIGENS_PERMITIDAS: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    NIVEL_LOG: str = "INFO"
    # IPs ou faixas CIDR do Nginx à frente da API. Vazio em desenvolvimento:
    # sem proxy configurado, X-Forwarded-For é ignorado por completo, que é o
    # comportamento seguro (o cabeçalho é escrito pelo cliente).
    PROXIES_CONFIAVEIS: Annotated[list[str], NoDecode] = []

    @field_validator("ORIGENS_PERMITIDAS", "PROXIES_CONFIAVEIS", mode="before")
    @classmethod
    def _dividir_lista(cls, valor: object) -> object:
        # No .env é mais prático escrever "http://a,http://b" do que uma lista
        # JSON de verdade.
        if isinstance(valor, str):
            return [origem.strip() for origem in valor.split(",") if origem.strip()]
        return valor

    @model_validator(mode="after")
    def _exigir_proxies_em_producao(self) -> Self:
        # Em produção a API fica atrás do Nginx. Com a lista vazia, o
        # X-Forwarded-For é descartado e TODO visitante chega com o IP do
        # proxy — aí a décima primeira identificação do dia, de qualquer
        # pessoa, tranca o site inteiro com 429. O sintoma parece queda, não
        # configuração, então é melhor não subir do que subir assim.
        if self.AMBIENTE == "producao" and not self.PROXIES_CONFIAVEIS:
            raise RuntimeError(
                "PROXIES_CONFIAVEIS está vazia com AMBIENTE=producao. "
                "Informe o IP ou a faixa CIDR do Nginx à frente da API "
                '(ex.: PROXIES_CONFIAVEIS="172.16.0.0/12"). Sem isso, o limite '
                "de identificações por IP contaria todos os visitantes como um só."
            )
        return self


configuracao = Configuracao()
