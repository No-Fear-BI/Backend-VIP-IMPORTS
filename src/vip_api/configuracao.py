"""Configuração da aplicação, lida do ambiente. Instância única em `configuracao`,
importada por todo o resto do pacote — nunca instancie `Configuracao()` de novo."""

from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Senha do .env.example. Quem copiar o arquivo no VPS e esquecer de trocar
# fica com um banco de produção de senha pública.
SENHA_DE_EXEMPLO = "vip_imports"


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
    # Número da loja no WhatsApp, formato internacional só com dígitos.
    # O link de /selecoes é montado com ele: o número não é escrito no
    # código nem no frontend, para trocar em um lugar só.
    WHATSAPP_LOJA: str = ""

    # Upload de imagem pelo painel (produtos e banners) — disco local, servido
    # pela própria API via StaticFiles (ver principal.py). Diretório relativo
    # ao processo (dentro do container, `./dados/imagens`, montado como volume
    # no docker-compose.yml para sobreviver a um `docker compose down`/rebuild).
    IMAGENS_DIR: str = "./dados/imagens"
    # Em desenvolvimento aponta pro próprio host http (sem TLS local). Em
    # produção PRECISA ser https — mesma regra "só https" de toda URL de
    # imagem do contrato (ImagemEntrada, BannerCriar...): servir por http
    # atrás de uma página https é conteúdo misto, o navegador bloqueia e a
    # imagem some sem aviso. Ver `_exigir_imagens_https_em_producao` abaixo.
    IMAGENS_URL_BASE: str = "http://localhost:8000/midia"

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

    @model_validator(mode="after")
    def _recusar_senha_de_exemplo(self) -> Self:
        # Compara a SENHA extraída da URL, não a URL inteira: usuário e nome
        # do banco também se chamam "vip_imports", e um `in` daria falso
        # positivo mesmo com a senha já trocada.
        try:
            senha = urlsplit(self.DATABASE_URL).password
        except ValueError:
            senha = None

        if self.AMBIENTE == "producao" and senha == SENHA_DE_EXEMPLO:
            raise RuntimeError(
                "DATABASE_URL ainda usa a senha de exemplo "
                f"({SENHA_DE_EXEMPLO!r}) com AMBIENTE=producao. Troque a senha "
                "do usuário do PostgreSQL e atualize DATABASE_URL no .env — "
                "o formato é postgresql+psycopg://usuario:SENHA@host:5432/banco. "
                "Um banco de produção com senha de exemplo é pior do que um "
                "que não sobe."
            )
        return self

    @model_validator(mode="after")
    def _exigir_whatsapp_em_producao(self) -> Self:
        if self.AMBIENTE == "producao" and not self.WHATSAPP_LOJA.isdigit():
            raise RuntimeError(
                "WHATSAPP_LOJA precisa ser o número da loja em formato "
                "internacional, só dígitos (ex.: 5541984975960). Sem ele o "
                "link de cada seleção enviada aponta para lugar nenhum."
            )
        return self

    @model_validator(mode="after")
    def _exigir_imagens_https_em_producao(self) -> Self:
        # Em desenvolvimento a API roda http puro (sem Nginx na frente), e
        # IMAGENS_URL_BASE aponta pra ela mesma — por isso só http é aceito
        # aqui. Em produção a API já fica atrás do Nginx (PROXIES_CONFIAVEIS
        # acima), que é quem teria o certificado; subir com IMAGENS_URL_BASE
        # http produziria imagem que todo navegador bloqueia como conteúdo
        # misto numa página https, e ninguém percebe até abrir o site.
        if self.AMBIENTE == "producao" and not self.IMAGENS_URL_BASE.lower().startswith("https://"):
            raise RuntimeError(
                "IMAGENS_URL_BASE precisa começar com https:// com "
                "AMBIENTE=producao (ex.: https://vipimports.com.br/midia, "
                "servido pelo Nginx à frente da API). Sem isso a imagem "
                "enviada pelo painel não aparece: o navegador bloqueia http "
                "dentro de uma página https."
            )
        return self


configuracao = Configuracao()
