"""customer support inbound email alias

Revision ID: d29a4c7f1b83
Revises: c1d83f6a9e21
Create Date: 2026-08-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd29a4c7f1b83'
down_revision: Union[str, Sequence[str], None] = 'c1d83f6a9e21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('brands', sa.Column('support_inbound_email', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_brands_support_inbound_email'), 'brands', ['support_inbound_email'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_brands_support_inbound_email'), table_name='brands')
    op.drop_column('brands', 'support_inbound_email')