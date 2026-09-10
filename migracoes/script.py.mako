"""${message}

Revisão: ${up_revision}
Anterior: ${down_revision | comma,n}
Criada em: ${create_date}
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${"pass" if not process_revision_directives else "..."}


def downgrade() -> None:
    ${"pass" if not process_revision_directives else "..."}
