"""Núcleo compartilhado de importação de catálogo: cria ou atualiza um
`Produto` de verdade (marca/categoria por slug, imagens em WebP, variações) a
partir de dados já resolvidos.

Duas entradas chamam esta mesma função hoje, e é proposital que seja só uma:
- `scripts/importar_catalogo.py`: CSV do cliente, uma linha = um produto.
- `vip_api.rotas.admin_revisao` (POST /admin/revisao): aprovação de um álbum
  da fila do Yupoo vira produto de verdade assim que o admin aprova — antes
  disso a aprovação só gravava numa tabela paralela, sem nenhum produto
  navegável na loja.

Ter a mecânica de código/marca/categoria/imagem num lugar só evita as duas
entradas divergirem (ex.: uma aceitar categoria vazia e a outra não). Cada
chamador continua dono de COMO os bytes da foto chegam até aqui — download
simples por URL no CSV, download com `Referer` do Yupoo na revisão — porque
os dois têm regra de rede diferente; esta função só recebe a imagem já
aberta (`PIL.Image`).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vip_api.modelos.catalogo import (
    Categoria,
    Colecao,
    Cor,
    Marca,
    Produto,
    ProdutoImagem,
    ProdutoVariacao,
)
from vip_api.servicos.admin_produtos import (
    TENTATIVAS_DE_CODIGO,
    _e_colisao_de_codigo,
    _prefixo_da_marca,
    _proximo_sequencial,
)
from vip_api.servicos.admin_variacoes import obter_ou_criar_cor
from vip_api.servicos.imagens_processamento import LADO_GRANDE, QUALIDADE_WEBP, redimensionado
from vip_api.texto import gerar_slug

# Só desta importação em lote (CSV e Yupoo) — o upload ao vivo do painel não
# gera miniatura (ver docstring de scripts/importar_catalogo.py, "Imagens").
LADO_MINIATURA = 400


def obter_ou_criar_marca(sessao: Session, nome: str, cache: dict[str, Marca]) -> Marca:
    slug = gerar_slug(nome)
    if not slug:
        raise ValueError(f"marca {nome!r} não vira um slug válido.")
    if slug in cache:
        return cache[slug]

    existente = sessao.scalar(select(Marca).where(Marca.slug == slug))
    if existente:
        cache[slug] = existente
        return existente

    nova = Marca(nome=nome, slug=slug)
    sessao.add(nova)
    sessao.flush()  # precisa do id antes de qualquer produto referenciar marca_id
    cache[slug] = nova
    return nova


def obter_colecao(sessao: Session, valor: str, cache: dict[str, Colecao]) -> Colecao:
    slug = gerar_slug(valor)
    if slug in cache:
        return cache[slug]

    colecao = sessao.scalar(select(Colecao).where(Colecao.slug == slug))
    if not colecao:
        raise ValueError(
            f"colecao {valor!r} não existe. Só 'feminino' e 'masculino' — "
            "esta importação não cria coleção nova (são só duas, fixas)."
        )
    cache[slug] = colecao
    return colecao


def obter_ou_criar_categoria(
    sessao: Session, colecao: Colecao, nome: str, cache: dict[tuple[int, str], Categoria]
) -> Categoria:
    slug = gerar_slug(nome)
    if not slug:
        raise ValueError(f"categoria {nome!r} não vira um slug válido.")
    chave = (colecao.id, slug)
    if chave in cache:
        return cache[chave]

    existente = sessao.scalar(
        select(Categoria).where(Categoria.colecao_id == colecao.id, Categoria.slug == slug)
    )
    if existente:
        cache[chave] = existente
        return existente

    nova = Categoria(colecao_id=colecao.id, nome=nome, slug=slug)
    sessao.add(nova)
    sessao.flush()
    cache[chave] = nova
    return nova


def atribuir_codigo(sessao: Session, produto: Produto, prefixo: str) -> None:
    """Reaproveita a mesma mecânica de código do painel (tarefa 71): prefixo
    da marca + sequencial, com retentativa em SAVEPOINT na colisão."""
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


def salvar_imagens(
    imagens: list[Image.Image],
    *,
    codigo_origem: str,
    nome_produto: str,
    saida_dir: Path,
    url_base: str,
    pasta_chave: str | None = None,
) -> list[tuple[str, str]]:
    """Redimensiona (grande 1200px + miniatura 400px, WebP) e salva cada
    imagem já ABERTA em `CATALOGO_IMAGENS_DIR/<slug>/`. Devolve
    [(url_final, alt), ...] na mesma ordem — url_final é o que entra em
    produto_imagens.url, PÚBLICA.

    O slug da pasta é, por padrão, o de `codigo_origem` — no CSV do cliente
    isso é só o SKU do fornecedor, sem problema em aparecer numa URL. Quem
    chama com um `codigo_origem` que carrega o NOME do fornecedor (a fila do
    Yupoo, ver vip_api.rotas.admin_revisao) passa `pasta_chave` à parte —
    senão o fornecedor vaza pela URL da imagem mesmo com a rota protegida.
    """
    pasta_slug = gerar_slug(pasta_chave if pasta_chave is not None else codigo_origem) or "produto"
    pasta = saida_dir / pasta_slug
    resultado: list[tuple[str, str]] = []

    for ordem, imagem in enumerate(imagens, start=1):
        grande = redimensionado(imagem, LADO_GRANDE)
        miniatura = redimensionado(imagem, LADO_MINIATURA)

        pasta.mkdir(parents=True, exist_ok=True)
        caminho_grande = pasta / f"{ordem}.webp"
        caminho_miniatura = pasta / f"{ordem}-miniatura.webp"
        grande.save(caminho_grande, format="WEBP", quality=QUALIDADE_WEBP, method=6)
        miniatura.save(caminho_miniatura, format="WEBP", quality=QUALIDADE_WEBP, method=6)

        url_final = f"{url_base.rstrip('/')}/{pasta_slug}/{ordem}.webp"
        alt = f"{nome_produto} — foto {ordem}"[:200]
        resultado.append((url_final, alt))

    return resultado


def importar_produto(
    sessao: Session,
    *,
    codigo_origem: str,
    nome: str,
    descricao: str | None,
    nome_marca: str,
    nome_categoria: str,
    valor_colecao: str,
    origem_url: str | None,
    tamanhos: list[str],
    cores: list[str],
    imagens: list[Image.Image],
    saida_dir: Path | None,
    url_base: str | None,
    cache_marcas: dict[str, Marca],
    cache_colecoes: dict[str, Colecao],
    cache_categorias: dict[tuple[int, str], Categoria],
    pasta_imagens: str | None = None,
) -> tuple[Produto, bool]:
    """Cria ou atualiza (por `codigo_origem`) um produto de verdade — marca e
    categoria são resolvidas por slug (criadas se não existirem), a coleção
    precisa já existir. Devolve `(produto, criou)`.

    `codigo_origem` é a chave de deduplicação (`produtos.codigo_origem`, nunca
    exposta ao público — ver docs/modelagem-banco.md 4.4): reimportar o mesmo
    código atualiza a peça em vez de duplicar. `pasta_imagens` é o slug da
    pasta de imagem quando ele PRECISA ser diferente de `codigo_origem` — ver
    `salvar_imagens`.
    """
    if imagens and (saida_dir is None or not url_base):
        raise ValueError("há imagem para salvar, mas saida_dir/url_base não foram informados.")

    colecao = obter_colecao(sessao, valor_colecao, cache_colecoes)
    marca = obter_ou_criar_marca(sessao, nome_marca, cache_marcas)
    categoria = obter_ou_criar_categoria(sessao, colecao, nome_categoria, cache_categorias)

    # Processa as fotos ANTES de tocar o produto: se uma imagem falhar ao
    # salvar, a operação falha sem ter mexido em nada do produto ainda (além
    # de marca/categoria, que são dado compartilhado e válido mesmo se esta
    # importação falhar depois).
    imagens_processadas = (
        salvar_imagens(
            imagens,
            codigo_origem=codigo_origem,
            nome_produto=nome,
            saida_dir=saida_dir,
            url_base=url_base,
            pasta_chave=pasta_imagens,
        )
        if imagens
        else []
    )

    produto = sessao.scalar(select(Produto).where(Produto.codigo_origem == codigo_origem))
    criando = produto is None

    if criando:
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
        atribuir_codigo(sessao, produto, prefixo)  # já dá add()+flush(); produto.id existe daqui pra frente
    else:
        # Produto já existe: apaga o conjunto antigo de imagens/variações
        # ANTES de inserir o novo (mesma ordem de scripts/importar_catalogo.py
        # — ver o comentário lá sobre o índice único parcial da capa).
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

    cores_da_linha: list[Cor] = []
    for valor in cores:
        cor = obter_ou_criar_cor(sessao, valor)
        if cor not in cores_da_linha:
            cores_da_linha.append(cor)
    for ordem, cor in enumerate(cores_da_linha, start=1):
        sessao.add(
            ProdutoVariacao(
                produto_id=produto.id,
                tipo="cor",
                valor=cor.nome,
                cor_id=cor.id,
                disponivel=True,
                ordem=ordem,
            )
        )

    for ordem, (url_final, alt) in enumerate(imagens_processadas, start=1):
        sessao.add(
            ProdutoImagem(produto_id=produto.id, url=url_final, alt=alt, ordem=ordem, capa=(ordem == 1))
        )

    sessao.flush()
    return produto, criando
