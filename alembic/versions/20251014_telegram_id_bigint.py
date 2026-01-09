"""Alter users.telegram_id to BIGINT

Revision ID: 20251014_telegram_id_bigint
Revises: 
Create Date: 2025-10-14
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251014_telegram_id_bigint'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alter column type to BIGINT
    op.alter_column(
        'users',
        'telegram_id',
        existing_type=sa.INTEGER(),
        type_=sa.BigInteger(),
        existing_nullable=False
    )


def downgrade() -> None:
    # Revert back to INTEGER (may fail if values exceed int range)
    op.alter_column(
        'users',
        'telegram_id',
        existing_type=sa.BigInteger(),
        type_=sa.INTEGER(),
        existing_nullable=False
    )

















