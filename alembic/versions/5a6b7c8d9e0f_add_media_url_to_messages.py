"""Add media_url column to messages table

Revision ID: 5a6b7c8d9e0f
Revises: f763da0c616a
Create Date: 2026-07-30 04:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5a6b7c8d9e0f"
down_revision: Union[str, None] = "f763da0c616a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("media_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "media_url")
