"""add pipeline_runs table for run-level audit records

Revision ID: d4f1a5b83c29
Revises: c3e9f4a72b18
Create Date: 2026-03-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4f1a5b83c29'
down_revision: Union[str, None] = 'c3e9f4a72b18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('pipeline_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_type', sa.String(length=30), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='running'),
        sa.Column('entries_collected', sa.Integer(), server_default='0', nullable=True),
        sa.Column('entries_processed', sa.Integer(), server_default='0', nullable=True),
        sa.Column('entries_failed', sa.Integer(), server_default='0', nullable=True),
        sa.Column('alerts_sent', sa.Integer(), server_default='0', nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('pipeline_runs')
