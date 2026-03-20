"""add bill_subject_tags table

Revision ID: a2f8c3d91e04
Revises: 75cd02f1b576
Create Date: 2026-03-19 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2f8c3d91e04'
down_revision: Union[str, None] = '75cd02f1b576'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('bill_subject_tags',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('canonical_version_id', sa.String(length=30), nullable=False),
        sa.Column('subject_tag', sa.String(length=50), nullable=False),
        sa.Column('tag_confidence', sa.Float(), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['canonical_version_id'], ['file_copies.canonical_version_id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('canonical_version_id', 'subject_tag', name='uq_bill_subject_tag_version_tag'),
    )


def downgrade() -> None:
    op.drop_table('bill_subject_tags')
