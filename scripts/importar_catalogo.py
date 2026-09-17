"""Importa peças reais de um CSV para o catálogo — primeira versão da carga
da Fatia 5 (docs/pendencias.md). Começa pequeno de propósito: a ideia é rodar
com as 40-60 peças que o cliente mandar numa planilha, não com o catálogo
inteiro de uma vez. Ver scripts/exemplo_catalogo.csv para o formato exato.

NÃO apaga a massa sintética de scripts/gerar_massa.py. As peças reais entram
ao lado dela — a limpeza da massa é decisão separada, de outro dia.

Colunas do CSV (cabeçalho obrigatório, nessa ordem ou não — é por nome; o
nome da coluna é comparado sem diferenciar maiúscula/acento/espaço nas
pontas, então "Coleção", "COLECAO" e " colecao " são todas aceitas como
`colecao` — planilha exportada do Excel no Brasil costuma vir assim):
    codigo_origem, nome, marca, categoria, colecao, descricao,
    tamanhos, cores, foto_1, foto_2, foto_3, origem_url

O arquivo é lido como UTF-8 e, se isso falhar, como CP1252 (Windows-1252) —
é a codificação que o Excel no Brasil grava por padrão ao "Salvar como CSV",
não UTF-8, e é o formato mais provável do arquivo que o cliente for mandar.

  - codigo_origem: identificador da peça NA PLANILHA DO FORNECEDOR. É a chave
    de deduplicação (produtos.codigo_origem) — reimportar o MESMO arquivo em
    execuções diferentes não duplica nada, e mudar uma linha e rodar de novo
    ATUALIZA a peça existente em vez de criar outra. Obrigatório.
    Repetir o mesmo codigo_origem DENTRO do mesmo arquivo é erro (a segunda
    ocorrência falha, apontando em qual linha o código já tinha aparecido)
    — não silenciosamente "a segunda sobrescreve a primeira", que é perda de
    dado sem aviso nenhum: das duas linhas do fornecedor, uma delas está
    errada, e o script não adivinha qual.
  - nome: até 180 caracteres.
  - marca, categoria: se já existirem no catálogo (comparando por slug, sem
    diferenciar maiúscula/acento/espaço), a peça entra nelas. Se não
    existirem, SÃO CRIADAS — é o que a tarefa pediu. `colecao` é diferente:
    só existem duas (feminino/masculino) e este script NUNCA cria uma
    terceira; escreva exatamente "feminino" ou "masculino".
  - descricao: opcional.
  - cores: opcional. Vários valores na MESMA célula, separados por ";"
    (ex.: "Preta;Azul Marinho"). Cada um vira uma produto_variacoes com
    disponivel=true — o admin ajusta disponibilidade depois pelo painel,
    isto aqui só cadastra o que existe.
  - tamanhos: opcional, mesma ideia de `cores`, mas aceita ";", ",", "/" e a
    palavra "e" como separador dentro da MESMA célula — "38;39;40",
    "38, 39 e 40" e "38/39/40" viram a mesma lista ["38", "39", "40"]. Sem
    isso, um fornecedor que escreve "38, 39 e 40" numa linha e "38/39/40"
    noutra faz duas peças iguais nascerem com seletor de tamanho diferente
    (pior ainda: o cliente final veria uma opção literal "39 e 40", porque
    a célula inteira virava um único valor). Espaço sobrando em cada item e
    item repetido dentro da célula são descartados.
  - foto_1, foto_2, foto_3: URL da foto no site do fornecedor, na ordem em
    que devem aparecer (foto_1 = capa). Até 3; pode faltar qualquer uma.
    Cada URL preenchida é BAIXADA aqui, nunca gravada direto no banco — ver
    "Imagens" abaixo.
  - origem_url: opcional. O link do anúncio, da página ou da planilha de
    onde a peça e as fotos vieram — grava direto em produtos.origem_url
    (docs/modelagem-banco.md, 4.4: "dado de rastreabilidade, não de
    negócio"). Não é usado para nada além de auditoria; ninguém no site
    exibe este link.

O que o script NÃO faz, de propósito, porque o CSV proposto não cobre e o
schema tem valor sensato sem isso (docs/modelagem-banco.md, seção 4.4):
  - não mexe em status/destaque (toda peça nova entra 'normal', destaque
    fica para o painel depois).

Imagens (item 3 do pedido)
---------------------------
O banco NUNCA aponta para a URL do fornecedor — link de terceiro quebra sem
avisar e não dá para otimizar. Para cada foto_N preenchida:
  1. baixa;
  2. gera uma versão de até 1200px no lado maior e uma miniatura de até
     400px, as duas em WebP;
  3. salva as duas em CATALOGO_IMAGENS_DIR/<slug do codigo_origem>/, como
     `<ordem>.webp` e `<ordem>-miniatura.webp`;
  4. grava em produto_imagens.url o endereço FINAL que essa imagem vai ter
     quando publicada — CATALOGO_IMAGENS_URL_BASE + o mesmo caminho.

`produto_imagens` (docs/modelagem-banco.md, 4.5) só tem UMA coluna de URL por
imagem, então é a versão de 1200px que fica registrada no banco — é a que
`FotoProduto` do frontend usa hoje. A miniatura de 400px é gerada e salva do
mesmo jeito, mas SEM lugar no schema/contrato ainda (pendência registrada em
docs/pendencias.md): fica pronta em disco, como
`<ordem>-miniatura.webp` ao lado de `<ordem>.webp`, à espera de uma coluna
(ex.: `produto_imagens.miniatura_url`) ou de outro uso futuro. Vale confirmar
com o time se é isso mesmo antes de depender dela em algo.

Quando essa coluna existir: o backfill NÃO reprocessa imagem nenhuma — os
arquivos já estão no disco, com nome previsível (`<ordem>-miniatura.webp`
no mesmo `CATALOGO_IMAGENS_DIR/<slug do codigo_origem>/` de sempre). É só um
UPDATE ligando `produto_imagens.miniatura_url` a
`CATALOGO_IMAGENS_URL_BASE` + o mesmo caminho, trocando `.webp` por
`-miniatura.webp` no fim da URL grande já gravada — não precisa baixar foto
de fornecedor de novo, nem rodar este script de novo.

CATALOGO_IMAGENS_DIR e CATALOGO_IMAGENS_URL_BASE são variáveis de ambiente
(não vão para o .env da aplicação — são só deste script) porque ainda não
foi decidido onde essas imagens vão ficar hospedadas. Só são exigidas
quando alguma linha do CSV tem foto.

Uso
---
    python scripts/importar_catalogo.py caminho/catalogo.csv
    python scripts/importar_catalogo.py caminho/catalogo.csv --delimitador ";"
    python scripts/importar_catalogo.py caminho/catalogo.csv --simular

    CATALOGO_IMAGENS_DIR=./imagens-catalogo \\
    CATALOGO_IMAGENS_URL_BASE=https://cdn.vipimports.com.br/catalogo \\
    python scripts/importar_catalogo.py scripts/exemplo_catalogo.csv

No servidor, dentro do container (build precisa incluir scripts/ e o Pillow
do pyproject.toml — rebuilde a imagem antes):
    docker compose exec api python scripts/importar_catalogo.py /caminho/no/container/catalogo.csv

--simular faz tudo — lê o CSV, baixa e processa foto, resolve marca/
categoria — menos gravar no banco: desfaz a transação inteira no final. É
o jeito de validar um arquivo novo do fornecedor sem risco.

Segurança de execução (item 4 do pedido)
------------------------------------------
Cada LINHA do CSV é uma transação própria (SAVEPOINT): se a linha 37 falhar
(marca vazia, foto que não baixa, nome maior que o campo), as linhas 1-36 já
gravadas continuam gravadas, e a 37 não deixa rastro nenhum — nem produto
pela metade, nem imagem órfã apontando para um produto que não existe. O
script sempre termina e imprime quantas peças criou, quantas atualizou e a
lista de linhas que falharam com o motivo. Código de saída 1 se alguma linha
falhou (para um pipeline de CI/ops perceber), 0 se todas as linhas passaram.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PIL import Image, UnidentifiedImageError  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from vip_api.banco import SessaoLocal  # noqa: E402
from vip_api.modelos.catalogo import (  # noqa: E402
    Categoria,
    Colecao,
    Marca,
    Produto,
    ProdutoImagem,
    ProdutoVariacao,
)
from vip_api.texto import gerar_slug, normalizar  # noqa: E402

# Reaproveita a mecânica de código (tarefa 71) já usada pelo painel, em vez de
# reinventar: mesmo prefixo por marca (o que a marca já usa, se já tem peça
# no catálogo — sintética inclusive), mesma retentativa em SAVEPOINT na
# colisão de sequencial. Só o commit final é diferente: aqui quem decide
# quando confirmar é o laço de importação (uma linha = uma transação inteira,
# produto + imagens + variações juntos), não esta função sozinha.
from vip_api.servicos.admin_produtos import (  # noqa: E402
    TENTATIVAS_DE_CODIGO,
    _e_colisao_de_codigo,
    _prefixo_da_marca,
    _proximo_sequencial,
)

COLUNAS_OBRIGATORIAS = [
    "codigo_origem",
    "nome",
    "marca",
    "categoria",
    "colecao",
    "descricao",
    "tamanhos",
    "cores",
    "foto_1",
    "foto_2",
    "foto_3",
    "origem_url",
]
COLUNAS_FOTO = ["foto_1", "foto_2", "foto_3"]
SEPARADOR_LISTA = ";"  # dentro de cores — tamanhos tem separador próprio, ver _dividir_tamanhos

LADO_GRANDE = 1200
LADO_MINIATURA = 400
QUALIDADE_WEBP = 82
TAMANHO_MAXIMO_FOTO = 15 * 1024 * 1024  # 15 MB: acima disso é fornecedor mandando coisa errada


# ======================================================================
# Relatório
# ======================================================================


@dataclass
class Relatorio:
    criados: int = 0
    atualizados: int = 0
    falhas: list[tuple[int, str, str]] = field(default_factory=list)  # (linha, codigo_origem, motivo)

    def imprimir(self, *, simulado: bool) -> None:
        titulo = "SIMULAÇÃO (nada foi gravado)" if simulado else "Importação"
        print(f"\n{titulo} — resumo")
        print(f"  criados:     {self.criados}")
        print(f"  atualizados: {self.atualizados}")
        print(f"  falharam:    {len(self.falhas)}")
        if self.falhas:
            print("\nLinhas que falharam:")
            for linha, codigo_origem, motivo in self.falhas:
                origem = codigo_origem or "(sem codigo_origem)"
                print(f"  linha {linha} [{origem}]: {motivo}")


# ======================================================================
# CSV
# ======================================================================


def _ler_texto(caminho: Path) -> str:
    """UTF-8 primeiro; se o arquivo não decodificar como UTF-8, tenta CP1252
    (Windows-1252). É o que o Excel no Brasil grava por padrão ao "Salvar
    como CSV" — não UTF-8 — e é o formato mais provável do arquivo que o
    cliente mandar. CP1252 nunca levanta erro de decodificação (todo byte
    0x00-0xFF mapeia para algum caractere), então só cai aqui quando o UTF-8
    já falhou."""
    dados = caminho.read_bytes()
    try:
        return dados.decode("utf-8-sig")
    except UnicodeDecodeError:
        return dados.decode("cp1252")


def _normalizar_nome_coluna(nome: str) -> str:
    """Minúsculas, sem acento, sem espaço nas pontas — "Coleção", "COLECAO"
    e " colecao " todas viram "colecao". Mesma normalização usada em marca/
    categoria (vip_api.texto.normalizar), para o cabeçalho ter a mesma
    tolerância que o resto do script já tem com texto do fornecedor."""
    return normalizar(nome)


def _ler_linhas(caminho: Path, delimitador: str) -> list[dict[str, str]]:
    texto = _ler_texto(caminho)
    leitor = csv.DictReader(io.StringIO(texto), delimiter=delimitador)
    cabecalho_bruto = leitor.fieldnames or []
    coluna_por_normalizado = {_normalizar_nome_coluna(c): c for c in cabecalho_bruto}

    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in coluna_por_normalizado]
    if faltando:
        sys.exit(
            f"Cabeçalho do CSV não tem a(s) coluna(s) {faltando}. "
            f"Esperado: {COLUNAS_OBRIGATORIAS}. "
            "Se a planilha foi salva com ';' pelo Excel em pt-BR, use --delimitador ';'."
        )

    # Troca só o nome das colunas OBRIGATÓRIAS pela grafia canônica (é o que
    # _campo()/_lista() procuram); coluna extra do fornecedor fica como está,
    # sem uso mesmo.
    canonico_por_coluna_bruta = {
        coluna_por_normalizado[c]: c for c in COLUNAS_OBRIGATORIAS
    }
    leitor.fieldnames = [
        canonico_por_coluna_bruta.get(c, c) for c in cabecalho_bruto
    ]
    return [linha for linha in leitor]


def _campo(linha: dict[str, str], nome: str) -> str:
    return (linha.get(nome) or "").strip()


def _lista(linha: dict[str, str], nome: str) -> list[str]:
    bruto = _campo(linha, nome)
    if not bruto:
        return []
    return [item.strip() for item in bruto.split(SEPARADOR_LISTA) if item.strip()]


# "38;39;40", "38, 39 e 40" e "38 / 39 / 40" viram a mesma lista — ";", ",",
# "/" e a palavra "e" (isolada, com espaço nos dois lados) são todos
# separadores válidos dentro da mesma célula de tamanhos.
_SEPARADOR_TAMANHOS = re.compile(r"\s*[,;/]\s*|\s+e\s+", re.IGNORECASE)


def _dividir_tamanhos(bruto: str) -> list[str]:
    """Só para `tamanhos` (não `cores`, que continua só com ';' — não foi
    pedido). Tira espaço sobrando de cada item e item repetido dentro da
    MESMA célula, mantendo a ordem em que apareceram."""
    itens: list[str] = []
    for pedaco in _SEPARADOR_TAMANHOS.split(bruto):
        item = pedaco.strip()
        if item and item not in itens:
            itens.append(item)
    return itens


def _validar_tamanho(valor: str, maximo: int, campo: str) -> str:
    if len(valor) > maximo:
        raise ValueError(f"{campo} tem {len(valor)} caracteres; o máximo é {maximo}.")
    return valor


# ======================================================================
# Marca / categoria / coleção — obter ou criar
# ======================================================================


def _obter_ou_criar_marca(sessao: Session, nome_csv: str, cache: dict[str, Marca]) -> Marca:
    nome_csv = _validar_tamanho(nome_csv, 80, "marca")
    slug = gerar_slug(nome_csv)
    if not slug:
        raise ValueError(f"marca {nome_csv!r} não vira um slug válido.")
    if slug in cache:
        return cache[slug]

    existente = sessao.scalar(select(Marca).where(Marca.slug == slug))
    if existente:
        cache[slug] = existente
        return existente

    nova = Marca(nome=nome_csv, slug=slug)
    sessao.add(nova)
    sessao.flush()  # precisa do id antes de qualquer produto referenciar marca_id
    cache[slug] = nova
    return nova


def _obter_colecao(sessao: Session, valor_csv: str, cache: dict[str, Colecao]) -> Colecao:
    slug = gerar_slug(valor_csv)
    if slug in cache:
        return cache[slug]

    colecao = sessao.scalar(select(Colecao).where(Colecao.slug == slug))
    if not colecao:
        raise ValueError(
            f"colecao {valor_csv!r} não existe. Só 'feminino' e 'masculino' — "
            "este script não cria coleção nova (são só duas, fixas)."
        )
    cache[slug] = colecao
    return colecao


def _obter_ou_criar_categoria(
    sessao: Session, colecao: Colecao, nome_csv: str, cache: dict[tuple[int, str], Categoria]
) -> Categoria:
    nome_csv = _validar_tamanho(nome_csv, 80, "categoria")
    slug = gerar_slug(nome_csv)
    if not slug:
        raise ValueError(f"categoria {nome_csv!r} não vira um slug válido.")
    chave = (colecao.id, slug)
    if chave in cache:
        return cache[chave]

    existente = sessao.scalar(
        select(Categoria).where(Categoria.colecao_id == colecao.id, Categoria.slug == slug)
    )
    if existente:
        cache[chave] = existente
        return existente

    nova = Categoria(colecao_id=colecao.id, nome=nome_csv, slug=slug)
    sessao.add(nova)
    sessao.flush()
    cache[chave] = nova
    return nova


# ======================================================================
# Código do produto (reaproveita admin_produtos, tarefa 71 — ver comentário
# de import no topo do arquivo)
# ======================================================================


def _atribuir_codigo(sessao: Session, produto: Produto, prefixo: str) -> None:
    sequencial = _proximo_sequencial(sessao, prefixo)
    for tentativa in range(TENTATIVAS_DE_CODIGO):
        produto.codigo = f"{prefixo}-{sequencial + tentativa:04d}"
        try:
            with sessao.begin_nested():
                sessao.add(produto)
                sessao.flush()
        except IntegrityError as erro:
            if not _e_colisao_de_codigo(erro):
                raise
            continue
        return
    raise RuntimeError(
        f"não consegui gerar código para o prefixo {prefixo!r} depois de "
        f"{TENTATIVAS_DE_CODIGO} tentativas — muita coisa disputando o mesmo prefixo."
    )


# ======================================================================
# Imagens: baixar, redimensionar, salvar em WebP
# ======================================================================


def _baixar_imagem(url: str) -> Image.Image:
    requisicao = urllib.request.Request(url, headers={"User-Agent": "vip-imports-importador/1.0"})
    try:
        with urllib.request.urlopen(requisicao, timeout=20) as resposta:  # noqa: S310 — URL vem do CSV do fornecedor, não de input do usuário final
            dados = resposta.read(TAMANHO_MAXIMO_FOTO + 1)
    except Exception as erro:  # feixe amplo de propósito: qualquer falha de rede vira falha de LINHA, não crash do script
        raise ValueError(f"não consegui baixar {url}: {erro}") from erro

    if len(dados) > TAMANHO_MAXIMO_FOTO:
        raise ValueError(f"{url} passa de {TAMANHO_MAXIMO_FOTO // (1024 * 1024)} MB.")

    try:
        imagem = Image.open(io.BytesIO(dados))
        imagem.load()  # decodifica agora — é aqui que um arquivo corrompido ou HTML de erro disfarçado de imagem estoura
    except UnidentifiedImageError as erro:
        raise ValueError(f"{url} não é uma imagem que dá para abrir.") from erro
    return imagem.convert("RGB")


def _redimensionado(imagem: Image.Image, lado_maior: int) -> Image.Image:
    largura, altura = imagem.size
    fator = lado_maior / max(largura, altura)
    if fator >= 1:
        return imagem.copy()  # não estica foto pequena, só encolhe
    novo_tamanho = (round(largura * fator), round(altura * fator))
    return imagem.resize(novo_tamanho, Image.LANCZOS)


def _processar_fotos(
    urls_origem: list[str], codigo_origem: str, nome_produto: str, saida_dir: Path, url_base: str
) -> list[tuple[str, str]]:
    """Baixa cada URL, salva grande (1200px) e miniatura (400px) em WebP, e
    devolve [(url_final, alt), ...] na mesma ordem — url_final é o que entra
    em produto_imagens.url."""
    pasta_slug = gerar_slug(codigo_origem) or "produto"
    pasta = saida_dir / pasta_slug
    resultado: list[tuple[str, str]] = []

    for ordem, url_origem in enumerate(urls_origem, start=1):
        imagem = _baixar_imagem(url_origem)
        grande = _redimensionado(imagem, LADO_GRANDE)
        miniatura = _redimensionado(imagem, LADO_MINIATURA)

        pasta.mkdir(parents=True, exist_ok=True)
        caminho_grande = pasta / f"{ordem}.webp"
        caminho_miniatura = pasta / f"{ordem}-miniatura.webp"
        grande.save(caminho_grande, format="WEBP", quality=QUALIDADE_WEBP, method=6)
        miniatura.save(caminho_miniatura, format="WEBP", quality=QUALIDADE_WEBP, method=6)

        url_final = f"{url_base.rstrip('/')}/{pasta_slug}/{ordem}.webp"
        alt = _validar_tamanho(f"{nome_produto} — foto {ordem}", 200, "alt da imagem")
        resultado.append((url_final, alt))

    return resultado


# ======================================================================
# Uma linha do CSV -> um produto
# ======================================================================


def _importar_linha(
    sessao: Session,
    linha: dict[str, str],
    *,
    indice: int,
    saida_dir: Path | None,
    url_base: str | None,
    cache_marcas: dict[str, Marca],
    cache_colecoes: dict[str, Colecao],
    cache_categorias: dict[tuple[int, str], Categoria],
    codigos_vistos: dict[str, int],
) -> bool:
    """Devolve True se criou, False se atualizou. Levanta exceção se a linha
    for inválida — quem chama decide o que fazer (ver laço principal)."""
    codigo_origem = _campo(linha, "codigo_origem")
    if not codigo_origem:
        raise ValueError("codigo_origem vazio — é a chave de deduplicação, não dá pra importar sem.")
    codigo_origem = _validar_tamanho(codigo_origem, 80, "codigo_origem")

    # Repetir codigo_origem DENTRO do mesmo arquivo é erro, não "a segunda
    # atualiza a primeira" — isso seria perda de dado em silêncio, pior que
    # um crash. `codigos_vistos` só vive durante ESTA execução: reimportar o
    # mesmo arquivo depois, numa segunda chamada do script, continua
    # atualizando a peça normalmente (ver _importar_linha mais abaixo).
    if codigo_origem in codigos_vistos:
        raise ValueError(
            f"codigo_origem {codigo_origem!r} repetido neste arquivo — já apareceu na linha "
            f"{codigos_vistos[codigo_origem]} (esta é a linha {indice})."
        )
    codigos_vistos[codigo_origem] = indice

    nome = _validar_tamanho(_campo(linha, "nome"), 180, "nome")
    if not nome:
        raise ValueError("nome vazio.")

    nome_marca = _campo(linha, "marca")
    if not nome_marca:
        raise ValueError("marca vazia.")
    nome_categoria = _campo(linha, "categoria")
    if not nome_categoria:
        raise ValueError("categoria vazia.")
    valor_colecao = _campo(linha, "colecao")
    if not valor_colecao:
        raise ValueError("colecao vazia.")

    descricao = _campo(linha, "descricao") or None
    # text, sem limite de tamanho no schema (docs/modelagem-banco.md 4.4) — só rastreabilidade.
    origem_url = _campo(linha, "origem_url") or None
    tamanhos = [_validar_tamanho(v, 60, "tamanhos") for v in _dividir_tamanhos(_campo(linha, "tamanhos"))]
    cores = [_validar_tamanho(v, 60, "cores") for v in _lista(linha, "cores")]
    urls_foto = [_campo(linha, coluna) for coluna in COLUNAS_FOTO]
    urls_foto = [u for u in urls_foto if u]

    if urls_foto and (saida_dir is None or not url_base):
        raise ValueError(
            "linha tem foto, mas CATALOGO_IMAGENS_DIR e/ou CATALOGO_IMAGENS_URL_BASE "
            "não estão definidas no ambiente."
        )

    colecao = _obter_colecao(sessao, valor_colecao, cache_colecoes)
    marca = _obter_ou_criar_marca(sessao, nome_marca, cache_marcas)
    categoria = _obter_ou_criar_categoria(sessao, colecao, nome_categoria, cache_categorias)

    # Processa as fotos ANTES de tocar o produto: se uma URL falhar, a linha
    # falha sem ter mexido em nada do banco ainda (além de marca/categoria,
    # que são dado compartilhado e válido mesmo se ESTA linha falhar depois).
    imagens_processadas = (
        _processar_fotos(urls_foto, codigo_origem, nome, saida_dir, url_base) if urls_foto else []
    )

    produto = sessao.scalar(select(Produto).where(Produto.codigo_origem == codigo_origem))
    criando = produto is None

    if criando:
        # Todos os campos NOT NULL entram no construtor: _atribuir_codigo faz
        # o INSERT de verdade (add()+flush()) logo abaixo, e se `nome`,
        # `marca_id`, `categoria_id` ou `colecao_id` estiverem faltando nesse
        # instante o banco recusa a linha inteira na hora — antes preencher
        # DEPOIS do INSERT fazia o primeiro INSERT falhar sempre, por nome
        # nulo, e nunca dava pra saber se o resto da linha estava certo.
        produto = Produto(
            codigo_origem=codigo_origem,
            origem_url=origem_url,
            nome=nome,
            descricao=descricao,
            marca_id=marca.id,
            categoria_id=categoria.id,
            colecao_id=colecao.id,
        )
        prefixo = _prefixo_da_marca(sessao, marca.id)
        _atribuir_codigo(sessao, produto, prefixo)  # já dá add()+flush(); produto.id existe daqui pra frente
    else:
        # Produto já existe: apaga o conjunto antigo de imagens/variações
        # ANTES de inserir o novo. Precisa ser nesta ordem — não só ORM
        # .clear()+.append() — por causa do índice único parcial da capa
        # (uq_produto_imagens_capa), que não é adiável como o de ordem
        # (docs/modelagem-banco.md 4.5): se a inserção da nova capa
        # acontecesse antes da exclusão da capa antiga, o banco recusaria no
        # meio da própria linha. Apagar tudo primeiro evita o problema by
        # design, em vez de depender da ordem de flush do SQLAlchemy.
        sessao.execute(delete(ProdutoImagem).where(ProdutoImagem.produto_id == produto.id))
        sessao.execute(delete(ProdutoVariacao).where(ProdutoVariacao.produto_id == produto.id))
        sessao.flush()

        produto.nome = nome
        produto.descricao = descricao
        produto.origem_url = origem_url
        produto.marca_id = marca.id
        produto.categoria_id = categoria.id
        produto.colecao_id = colecao.id
        # codigo e codigo_origem NUNCA mudam numa atualização: codigo é o
        # identificador público (URL /produto/:codigo) já divulgado, e
        # codigo_origem é a própria chave que achou este produto.

    for ordem, valor in enumerate(tamanhos, start=1):
        sessao.add(
            ProdutoVariacao(produto_id=produto.id, tipo="tamanho", valor=valor, disponivel=True, ordem=ordem)
        )
    for ordem, valor in enumerate(cores, start=1):
        sessao.add(
            ProdutoVariacao(produto_id=produto.id, tipo="cor", valor=valor, disponivel=True, ordem=ordem)
        )
    for ordem, (url_final, alt) in enumerate(imagens_processadas, start=1):
        sessao.add(
            ProdutoImagem(produto_id=produto.id, url=url_final, alt=alt, ordem=ordem, capa=(ordem == 1))
        )

    sessao.flush()
    return criando


# ======================================================================
# Principal
# ======================================================================


def main() -> None:
    analisador = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    analisador.add_argument("csv_path", type=Path, help="caminho do CSV a importar")
    analisador.add_argument(
        "--delimitador", default=",", help='delimitador de COLUNA do CSV (padrão ","; Excel pt-BR costuma exportar ";")'
    )
    analisador.add_argument(
        "--simular",
        action="store_true",
        help="faz tudo (baixa/processa foto, resolve marca/categoria) mas desfaz no final — nada é gravado",
    )
    argumentos = analisador.parse_args()

    if not argumentos.csv_path.exists():
        sys.exit(f"arquivo não encontrado: {argumentos.csv_path}")

    linhas = _ler_linhas(argumentos.csv_path, argumentos.delimitador)
    if not linhas:
        sys.exit("CSV sem nenhuma linha de dado (só cabeçalho, ou vazio).")

    tem_foto = any(_campo(linha, coluna) for linha in linhas for coluna in COLUNAS_FOTO)
    saida_dir_env = os.environ.get("CATALOGO_IMAGENS_DIR")
    url_base_env = os.environ.get("CATALOGO_IMAGENS_URL_BASE")
    if tem_foto and not (saida_dir_env and url_base_env):
        sys.exit(
            "O CSV tem foto em pelo menos uma linha, e faltou definir "
            "CATALOGO_IMAGENS_DIR e/ou CATALOGO_IMAGENS_URL_BASE no ambiente. "
            "Ainda não decidimos onde as imagens processadas vão ficar hospedadas — "
            "ver o docstring deste script."
        )
    saida_dir = Path(saida_dir_env).expanduser().resolve() if saida_dir_env else None
    if saida_dir:
        saida_dir.mkdir(parents=True, exist_ok=True)

    relatorio = Relatorio()
    cache_marcas: dict[str, Marca] = {}
    cache_colecoes: dict[str, Colecao] = {}
    cache_categorias: dict[tuple[int, str], Categoria] = {}
    # codigo_origem -> linha onde apareceu primeiro NESTE arquivo, só para
    # detectar repetição dentro da própria execução (ver _importar_linha).
    codigos_vistos: dict[str, int] = {}

    with SessaoLocal() as sessao:
        for indice, linha in enumerate(linhas, start=2):  # start=2: linha 1 do arquivo é o cabeçalho
            codigo_origem_para_relato = _campo(linha, "codigo_origem")
            try:
                with sessao.begin_nested():
                    criou = _importar_linha(
                        sessao,
                        linha,
                        indice=indice,
                        saida_dir=saida_dir,
                        url_base=url_base_env,
                        cache_marcas=cache_marcas,
                        cache_colecoes=cache_colecoes,
                        cache_categorias=cache_categorias,
                        codigos_vistos=codigos_vistos,
                    )
                if not argumentos.simular:
                    # Confirma a linha inteira (produto + imagens + variações) de uma vez, JÁ NO
                    # DISCO — se o script for interrompido na linha seguinte, esta continua
                    # gravada, e reimportar o mesmo arquivo depois só atualiza a partir daqui.
                    # Em --simular NÃO commita: o SAVEPOINT acima só é liberado dentro da
                    # transação de fora, que segue aberta até o rollback final.
                    sessao.commit()
                if criou:
                    relatorio.criados += 1
                    print(f"  linha {indice} [{codigo_origem_para_relato}]: criado")
                else:
                    relatorio.atualizados += 1
                    print(f"  linha {indice} [{codigo_origem_para_relato}]: atualizado")
            except Exception as erro:  # noqa: BLE001 — linha ruim não pode derrubar a importação inteira (item 4 do pedido)
                # SEM sessao.rollback() aqui: o `with sessao.begin_nested()` acima já desfez o
                # SAVEPOINT desta linha sozinho ao sair por exceção. Um rollback do Session
                # inteiro nesse ponto desfaria a transação de FORA também — em --simular isso
                # apagaria as linhas boas que vieram antes desta na mesma execução.
                relatorio.falhas.append((indice, codigo_origem_para_relato, str(erro)))
                print(f"  linha {indice} [{codigo_origem_para_relato}]: FALHOU — {erro}")

        if argumentos.simular:
            # Desfaz tudo que as linhas bem-sucedidas deixaram pendente na
            # transação de fora (elas nunca tiveram commit próprio, ver acima).
            sessao.rollback()

    relatorio.imprimir(simulado=argumentos.simular)
    sys.exit(1 if relatorio.falhas else 0)


if __name__ == "__main__":
    main()
