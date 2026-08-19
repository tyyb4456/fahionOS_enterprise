"""product agent tables

Revision ID: d4f728a1c6e9
Revises: 9e4b1a7c5f02, b7c92d4f1a3e
Create Date: 2026-08-16 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4f728a1c6e9'
down_revision: Union[str, Sequence[str], None] = ('9e4b1a7c5f02', 'b7c92d4f1a3e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'product_proposals',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('product_name', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=255), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('variants', sa.JSON(), nullable=False),
        sa.Column('sizes', sa.JSON(), nullable=False),
        sa.Column('target_price', sa.Float(), nullable=True),
        sa.Column('market_demand', sa.Float(), nullable=False),
        sa.Column('brand_fit', sa.Float(), nullable=False),
        sa.Column('competition', sa.Float(), nullable=False),
        sa.Column('supplier_feasibility', sa.Float(), nullable=False),
        sa.Column('expected_margin', sa.Float(), nullable=True),
        sa.Column('composite_score', sa.Float(), nullable=False),
        sa.Column('recommended_initial_quantity', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('source_opportunity_id', sa.UUID(), nullable=True),
        sa.Column('shopify_product_id', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.ForeignKeyConstraint(['source_opportunity_id'], ['product_opportunities.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_product_proposals_brand_id'), 'product_proposals', ['brand_id'], unique=False)

    op.create_table(
        'collections',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('season', sa.String(length=100), nullable=True),
        sa.Column('theme', sa.Text(), nullable=False),
        sa.Column('product_names', sa.JSON(), nullable=False),
        sa.Column('launch_date', sa.Date(), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_collections_brand_id'), 'collections', ['brand_id'], unique=False)

    op.create_table(
        'product_lifecycle',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('product_ref', sa.String(length=255), nullable=False),
        sa.Column('stage', sa.String(length=30), nullable=False),
        sa.Column('performance_score', sa.Float(), nullable=True),
        sa.Column('next_review_date', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('stage_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('brand_id', 'product_ref', name='uq_lifecycle_brand_product'),
    )
    op.create_index(op.f('ix_product_lifecycle_brand_id'), 'product_lifecycle', ['brand_id'], unique=False)

    op.create_table(
        'merchandising_insights',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_merchandising_insights_brand_id'), 'merchandising_insights', ['brand_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_merchandising_insights_brand_id'), table_name='merchandising_insights')
    op.drop_table('merchandising_insights')
    op.drop_index(op.f('ix_product_lifecycle_brand_id'), table_name='product_lifecycle')
    op.drop_table('product_lifecycle')
    op.drop_index(op.f('ix_collections_brand_id'), table_name='collections')
    op.drop_table('collections')
    op.drop_index(op.f('ix_product_proposals_brand_id'), table_name='product_proposals')
    op.drop_table('product_proposals')