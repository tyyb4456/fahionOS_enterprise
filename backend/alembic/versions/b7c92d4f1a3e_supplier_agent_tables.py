"""supplier agent tables

Revision ID: b7c92d4f1a3e
Revises: f3a91c6e2b7d
Create Date: 2026-08-08 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c92d4f1a3e'
down_revision: Union[str, Sequence[str], None] = 'f3a91c6e2b7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('suppliers', sa.Column('quality_score', sa.Float(), nullable=False, server_default='0.8'))

    op.add_column('purchase_orders', sa.Column('unit_cost', sa.Float(), nullable=True))
    op.add_column('purchase_orders', sa.Column('total_cost', sa.Float(), nullable=True))
    op.add_column('purchase_orders', sa.Column('payment_terms', sa.String(length=255), nullable=True))
    op.add_column('purchase_orders', sa.Column('actual_delivery', sa.Date(), nullable=True))

    op.create_table(
        'supplier_quotes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('supplier_id', sa.UUID(), nullable=False),
        sa.Column('sku', sa.String(length=255), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit_price', sa.Float(), nullable=False),
        sa.Column('moq', sa.Integer(), nullable=False),
        sa.Column('lead_time_days', sa.Integer(), nullable=False),
        sa.Column('valid_until', sa.Date(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_supplier_quotes_brand_id'), 'supplier_quotes', ['brand_id'], unique=False)
    op.create_index(op.f('ix_supplier_quotes_supplier_id'), 'supplier_quotes', ['supplier_id'], unique=False)
    op.create_index(op.f('ix_supplier_quotes_sku'), 'supplier_quotes', ['sku'], unique=False)

    op.create_table(
        'negotiation_records',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('supplier_id', sa.UUID(), nullable=False),
        sa.Column('sku', sa.String(length=255), nullable=True),
        sa.Column('initial_offer', sa.Float(), nullable=True),
        sa.Column('counter_offer', sa.Float(), nullable=True),
        sa.Column('final_price', sa.Float(), nullable=True),
        sa.Column('result', sa.String(length=20), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_negotiation_records_brand_id'), 'negotiation_records', ['brand_id'], unique=False)
    op.create_index(op.f('ix_negotiation_records_supplier_id'), 'negotiation_records', ['supplier_id'], unique=False)

    op.create_table(
        'shipment_tracking',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('purchase_order_id', sa.UUID(), nullable=False),
        sa.Column('carrier', sa.String(length=255), nullable=True),
        sa.Column('tracking_number', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('current_location', sa.String(length=255), nullable=True),
        sa.Column('estimated_arrival', sa.Date(), nullable=True),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_shipment_tracking_brand_id'), 'shipment_tracking', ['brand_id'], unique=False)
    op.create_index(op.f('ix_shipment_tracking_purchase_order_id'), 'shipment_tracking', ['purchase_order_id'], unique=False)

    op.create_table(
        'supplier_insights',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('supplier_id', sa.UUID(), nullable=True),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_supplier_insights_brand_id'), 'supplier_insights', ['brand_id'], unique=False)

    # policy_documents.agent is a plain, unconstrained String column (no DB
    # CHECK) — "supplier" needs no schema change there, only the Python
    # Literal in api/routers/policy_documents.py.


def downgrade() -> None:
    op.drop_index(op.f('ix_supplier_insights_brand_id'), table_name='supplier_insights')
    op.drop_table('supplier_insights')
    op.drop_index(op.f('ix_shipment_tracking_purchase_order_id'), table_name='shipment_tracking')
    op.drop_index(op.f('ix_shipment_tracking_brand_id'), table_name='shipment_tracking')
    op.drop_table('shipment_tracking')
    op.drop_index(op.f('ix_negotiation_records_supplier_id'), table_name='negotiation_records')
    op.drop_index(op.f('ix_negotiation_records_brand_id'), table_name='negotiation_records')
    op.drop_table('negotiation_records')
    op.drop_index(op.f('ix_supplier_quotes_sku'), table_name='supplier_quotes')
    op.drop_index(op.f('ix_supplier_quotes_supplier_id'), table_name='supplier_quotes')
    op.drop_index(op.f('ix_supplier_quotes_brand_id'), table_name='supplier_quotes')
    op.drop_table('supplier_quotes')
    op.drop_column('purchase_orders', 'actual_delivery')
    op.drop_column('purchase_orders', 'payment_terms')
    op.drop_column('purchase_orders', 'total_cost')
    op.drop_column('purchase_orders', 'unit_cost')
    op.drop_column('suppliers', 'quality_score')