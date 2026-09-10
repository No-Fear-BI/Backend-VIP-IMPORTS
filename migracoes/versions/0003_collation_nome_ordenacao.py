"""Fixa COLLATE "C" na própria coluna produtos.nome_ordenacao.

POR QUE ISSO É UMA MIGRAÇÃO E NÃO UM DETALHE DE CONSULTA:

O índice ix_produtos_pub_nome (e os irmãos por marca/categoria/coleção) foi
criado com COLLATE "C", mas a collation padrão do banco é en_US.utf8. Enquanto
a collation vivia só no índice, TODA consulta de `ordem=nome` precisava repetir
`COLLATE "C"` no ORDER BY e na comparação do cursor.

Quem esquecer de repetir não recebe erro nenhum. Acontecem duas coisas em
silêncio: o índice deixa de ser usado (vira Sort), e — pior — a comparação do
cursor passa a ordenar por uma regra diferente da do índice. Ordem diferente
entre a página anterior e a seguinte é exatamente como produto some ou repete
na virada de página, sem nada quebrar e sem ninguém perceber até um cliente
reclamar que um item sumiu do catálogo.

Com a collation na coluna, o comportamento correto passa a ser o padrão: quem
escrever `ORDER BY nome_ordenacao` já ordena por byte, igual ao índice, sem
precisar lembrar de nada.

Revisão: 0003
Anterior: 0002
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Reescreve a tabela e reconstrói os índices que dependem da coluna —
    # operação rápida nesse volume, mas toma ACCESS EXCLUSIVE: em produção,
    # rodar em janela, não no meio do expediente.
    op.execute('ALTER TABLE produtos ALTER COLUMN nome_ordenacao TYPE text COLLATE "C"')


def downgrade() -> None:
    # Volta à collation padrão do banco. Os índices continuam com o COLLATE "C"
    # explícito na definição, então voltam a ser expressão — e a consulta volta
    # a precisar repetir o COLLATE para usá-los.
    op.execute(
        'ALTER TABLE produtos ALTER COLUMN nome_ordenacao TYPE text '
        'COLLATE "default"'
    )
