"""finance agent tables

Revision ID: f3a91c6e2b7d
Revises: 833aec2968b0
Create Date: 2026-08-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a91c6e2b7d'
down_revision: Union[str, Sequence[str], None] = '833aec2968b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # cost_price is needed for margin/profitability calculations — it was
    # missing from product_variants entirely. Manually entered via
    # dashboard/seed (same role as Supplier/Warehouse), not Shopify-synced.
    op.add_column('product_variants', sa.Column('cost_price', sa.Float(), nullable=True))

    op.create_table(
        'expenses',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('recurring', sa.Boolean(), nullable=False),
        sa.Column('incurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_expenses_brand_id'), 'expenses', ['brand_id'], unique=False)
    op.create_index(op.f('ix_expenses_incurred_at'), 'expenses', ['incurred_at'], unique=False)

    op.create_table(
        'financial_reports',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('period', sa.String(length=50), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('revenue', sa.Float(), nullable=False),
        sa.Column('expenses', sa.Float(), nullable=False),
        sa.Column('profit', sa.Float(), nullable=False),
        sa.Column('margin', sa.Float(), nullable=False),
        sa.Column('kpis', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_financial_reports_brand_id'), 'financial_reports', ['brand_id'], unique=False)

    op.create_table(
        'financial_forecasts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('forecast_date', sa.Date(), nullable=False),
        sa.Column('forecast_days', sa.Integer(), nullable=False),
        sa.Column('cash_today', sa.Float(), nullable=False),
        sa.Column('predicted_cash', sa.Float(), nullable=False),
        sa.Column('predicted_revenue', sa.Float(), nullable=False),
        sa.Column('predicted_expenses', sa.Float(), nullable=False),
        sa.Column('risk', sa.String(length=20), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_financial_forecasts_brand_id'), 'financial_forecasts', ['brand_id'], unique=False)

    op.create_table(
        'financial_insights',
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
    op.create_index(op.f('ix_financial_insights_brand_id'), 'financial_insights', ['brand_id'], unique=False)

    op.create_table(
        'budget_recommendations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('department', sa.String(length=100), nullable=False),
        sa.Column('current_budget', sa.Float(), nullable=True),
        sa.Column('recommended_budget', sa.Float(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_budget_recommendations_brand_id'), 'budget_recommendations', ['brand_id'], unique=False)

    op.create_table(
        'risk_assessments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('risk', sa.Text(), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('related_amount', sa.Float(), nullable=True),
        sa.Column('recommendation', sa.Text(), nullable=False),
        sa.Column('resolved', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_risk_assessments_brand_id'), 'risk_assessments', ['brand_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_risk_assessments_brand_id'), table_name='risk_assessments')
    op.drop_table('risk_assessments')
    op.drop_index(op.f('ix_budget_recommendations_brand_id'), table_name='budget_recommendations')
    op.drop_table('budget_recommendations')
    op.drop_index(op.f('ix_financial_insights_brand_id'), table_name='financial_insights')
    op.drop_table('financial_insights')
    op.drop_index(op.f('ix_financial_forecasts_brand_id'), table_name='financial_forecasts')
    op.drop_table('financial_forecasts')
    op.drop_index(op.f('ix_financial_reports_brand_id'), table_name='financial_reports')
    op.drop_table('financial_reports')
    op.drop_index(op.f('ix_expenses_incurred_at'), table_name='expenses')
    op.drop_index(op.f('ix_expenses_brand_id'), table_name='expenses')
    op.drop_table('expenses')
    op.drop_column('product_variants', 'cost_price')