"""whatsapp phone number routing + instagram page id uniqueness

Revision ID: e47b9a1d3c56
Revises: a58f2d6c4e91
Create Date: 2026-08-11 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e47b9a1d3c56'
down_revision: Union[str, Sequence[str], None] = 'a58f2d6c4e91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('brands', sa.Column('whatsapp_phone_number_id', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_brands_whatsapp_phone_number_id'), 'brands', ['whatsapp_phone_number_id'], unique=True)

    # instagram_page_id existed with no index or uniqueness constraint at
    # all — now used as a routing lookup key for inbound Instagram DM
    # webhooks (api/routers/customer_support_webhook.py), so it needs one.
    # NOTE: if any dev/seed data already has duplicate non-null values here
    # (shouldn't happen — Meta IDs are globally unique — but worth
    # checking before running against a populated DB), this index creation
    # will fail until those rows are deduplicated.
    op.create_index(op.f('ix_brands_instagram_page_id'), 'brands', ['instagram_page_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_brands_instagram_page_id'), table_name='brands')
    op.drop_index(op.f('ix_brands_whatsapp_phone_number_id'), table_name='brands')
    op.drop_column('brands', 'whatsapp_phone_number_id')