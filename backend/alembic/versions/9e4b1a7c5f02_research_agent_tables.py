"""research agent tables

Revision ID: 9e4b1a7c5f02
Revises: f3a91c6e2b7d
Create Date: 2026-08-07 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9e4b1a7c5f02'
down_revision: Union[str, Sequence[str], None] = 'f3a91c6e2b7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'market_trends',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('trend', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('growth_pct', sa.Float(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('source', sa.String(length=255), nullable=True),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_market_trends_brand_id'), 'market_trends', ['brand_id'], unique=False)

    op.create_table(
        'competitor_analysis',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('competitor', sa.String(length=255), nullable=False),
        sa.Column('products', sa.JSON(), nullable=False),
        sa.Column('pricing_summary', sa.Text(), nullable=False),
        sa.Column('promotions', sa.Text(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_competitor_analysis_brand_id'), 'competitor_analysis', ['brand_id'], unique=False)

    op.create_table(
        'product_opportunities',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('product', sa.String(length=255), nullable=False),
        sa.Column('market_score', sa.Float(), nullable=False),
        sa.Column('competition', sa.String(length=20), nullable=False),
        sa.Column('priority', sa.String(length=20), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_product_opportunities_brand_id'), 'product_opportunities', ['brand_id'], unique=False)

    op.create_table(
        'pricing_intelligence',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('product', sa.String(length=255), nullable=False),
        sa.Column('our_price', sa.Float(), nullable=True),
        sa.Column('competitor_price', sa.Float(), nullable=True),
        sa.Column('competitor_name', sa.String(length=255), nullable=True),
        sa.Column('recommended_price', sa.Float(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pricing_intelligence_brand_id'), 'pricing_intelligence', ['brand_id'], unique=False)

    op.create_table(
        'research_insights',
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
    op.create_index(op.f('ix_research_insights_brand_id'), 'research_insights', ['brand_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_research_insights_brand_id'), table_name='research_insights')
    op.drop_table('research_insights')
    op.drop_index(op.f('ix_pricing_intelligence_brand_id'), table_name='pricing_intelligence')
    op.drop_table('pricing_intelligence')
    op.drop_index(op.f('ix_product_opportunities_brand_id'), table_name='product_opportunities')
    op.drop_table('product_opportunities')
    op.drop_index(op.f('ix_competitor_analysis_brand_id'), table_name='competitor_analysis')
    op.drop_table('competitor_analysis')
    op.drop_index(op.f('ix_market_trends_brand_id'), table_name='market_trends')
    op.drop_table('market_trends')