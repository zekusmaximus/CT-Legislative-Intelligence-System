"""add bill_summaries table and alert delivery tracking columns

Revision ID: c3e9f4a72b18
Revises: a2f8c3d91e04
Create Date: 2026-03-20 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3e9f4a72b18'
down_revision: Union[str, None] = 'a2f8c3d91e04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create bill_summaries table
    op.create_table('bill_summaries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('canonical_version_id', sa.String(length=30), nullable=False),
        sa.Column('bill_id', sa.String(length=10), nullable=False),
        sa.Column('one_sentence_summary', sa.Text(), nullable=False),
        sa.Column('deep_summary', sa.Text(), nullable=False),
        sa.Column('key_sections_json', sa.Text(), nullable=True),
        sa.Column('practical_takeaways_json', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['canonical_version_id'], ['file_copies.canonical_version_id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('canonical_version_id', name='uq_bill_summary_version_id'),
    )

    # Add delivery tracking columns to alerts table
    with op.batch_alter_table('alerts') as batch_op:
        batch_op.add_column(sa.Column('delivery_status', sa.String(length=20), server_default='pending', nullable=True))
        batch_op.add_column(sa.Column('delivery_attempts', sa.Integer(), server_default='0', nullable=True))
        batch_op.add_column(sa.Column('last_delivery_attempt_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('delivery_error', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('alerts') as batch_op:
        batch_op.drop_column('delivery_error')
        batch_op.drop_column('last_delivery_attempt_at')
        batch_op.drop_column('delivery_attempts')
        batch_op.drop_column('delivery_status')

    op.drop_table('bill_summaries')
