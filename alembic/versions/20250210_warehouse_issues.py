"""Add warehouse_issues table for tracking seller take-from-warehouse

Revision ID: 20250210_warehouse_issues
Revises: 20251014_telegram_id_bigint
Create Date: 2025-02-10

"""
from alembic import op
import sqlalchemy as sa


revision = '20250210_warehouse_issues'
down_revision = '20251014_telegram_id_bigint'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'warehouse_issues',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('seller_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.ForeignKeyConstraint(['seller_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_warehouse_issues_product_id'), 'warehouse_issues', ['product_id'], unique=False)
    op.create_index(op.f('ix_warehouse_issues_seller_id'), 'warehouse_issues', ['seller_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_warehouse_issues_seller_id'), table_name='warehouse_issues')
    op.drop_index(op.f('ix_warehouse_issues_product_id'), table_name='warehouse_issues')
    op.drop_table('warehouse_issues')
