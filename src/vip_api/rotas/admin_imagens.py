"""Exclusão de imagem pelo id dela, sem o produto na URL.

É o caminho que o contrato define (seção 4.2). Fica em roteador próprio porque
o prefixo é `/admin/imagens`, e não `/admin/produtos/...` — mas entra no mesmo
roteador protegido, e a varredura confere.
"""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.esquemas.produto import ImagemDetalhe
from vip_api.servicos.admin_imagens import remover_imagem

roteador = APIRouter(prefix="/imagens", tags=["admin"])


@roteador.delete("/{imagemId}", response_model=list[ImagemDetalhe])
def excluir(
    imagem_id: int = Path(alias="imagemId"), sessao: Session = Depends(obter_sessao)
) -> list[ImagemDetalhe]:
    """Devolve as imagens que sobraram, renumeradas: apagar a capa promove a
    seguinte, e a tela precisa mostrar isso sem outra chamada."""
    return remover_imagem(sessao, imagem_id)
