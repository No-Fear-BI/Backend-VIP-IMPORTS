"""Converte fotos do proxy removido para arquivos persistentes da API.

Execute dentro do container: python scripts/reparar_imagens_legadas.py
Sem --aplicar apenas lista os registros. Guarda os links antigos antes do commit.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from sqlalchemy import select

from vip_api.banco import SessaoLocal
from vip_api.configuracao import configuracao
from vip_api.modelos.catalogo import ProdutoImagem
from vip_api.rotas.admin_revisao import _baixar_foto_yupoo
from vip_api.servicos.imagens_processamento import LADO_GRANDE, para_webp, redimensionado


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--aplicar', action='store_true')
    args = parser.parse_args()
    with SessaoLocal() as sessao:
        fotos = [foto for foto in sessao.scalars(select(ProdutoImagem)).all()
                 if urlsplit(foto.url).path == '/api/v1/produtos-aprovados/imagem']
        print(f'{len(fotos)} imagem(ns) legada(s).', flush=True)
        if not args.aplicar or not fotos:
            return
        alteracoes = []
        for foto in fotos:
            parametros = parse_qs(urlsplit(foto.url).query, strict_parsing=True)
            imagem = _baixar_foto_yupoo(parametros['url'][0], parametros['source'][0])
            relativo = Path('recuperadas') / f'{uuid4().hex}.webp'
            destino = Path(configuracao.IMAGENS_DIR) / relativo
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(para_webp(redimensionado(imagem, LADO_GRANDE)))
            nova_url = f'{configuracao.IMAGENS_URL_BASE.rstrip("/")}/{relativo.as_posix()}'
            alteracoes.append({'id': foto.id, 'url_anterior': foto.url, 'url_nova': nova_url})
            foto.url = nova_url
            print(f'Imagem {foto.id}: arquivo salvo.', flush=True)
        # Fora da pasta servida publicamente. Copiar o backup para o host
        # antes de recriar o container.
        backup = Path(configuracao.IMAGENS_DIR).resolve().parent / 'backup-imagens-legadas'
        backup.mkdir(parents=True, exist_ok=True)
        registro = backup / f'{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid4().hex}.json'
        registro.write_text(json.dumps(alteracoes, indent=2), encoding='utf-8')
        sessao.commit()
        print(f'{len(alteracoes)} imagem(ns) corrigida(s). Backup: {registro}', flush=True)


if __name__ == '__main__':
    main()
