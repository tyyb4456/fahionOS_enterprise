"""customer support agent tables (merge heads)

Revision ID: c1d83f6a9e21
Revises: 9e4b1a7c5f02, b7c92d4f1a3e
Create Date: 2026-08-10 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1d83f6a9e21'
down_revision: Union[str, Sequence[str], None] = ('9e4b1a7c5f02', 'b7c92d4f1a3e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # research_agent_tables and supplier_agent_tables both branched off
    # f3a91c6e2b7d independently, leaving two heads — this migration
    # merges them back into one line and adds the Customer Support Agent's
    # own tables on top.
    op.add_column('customers', sa.Column('phone', sa.String(length=50), nullable=True))

    op.create_table(
        'support_conversations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('shopify_customer_id', sa.BigInteger(), nullable=True),
        sa.Column('channel', sa.String(length=20), nullable=False),
        sa.Column('external_thread_id', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_message_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_support_conversations_brand_id'), 'support_conversations', ['brand_id'], unique=False)
    op.create_index(op.f('ix_support_conversations_shopify_customer_id'), 'support_conversations', ['shopify_customer_id'], unique=False)

    op.create_table(
        'support_messages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('sender', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.ForeignKeyConstraint(['conversation_id'], ['support_conversations.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_support_messages_brand_id'), 'support_messages', ['brand_id'], unique=False)
    op.create_index(op.f('ix_support_messages_conversation_id'), 'support_messages', ['conversation_id'], unique=False)

    op.create_table(
        'support_tickets',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=True),
        sa.Column('shopify_customer_id', sa.BigInteger(), nullable=True),
        sa.Column('shopify_order_id', sa.BigInteger(), nullable=True),
        sa.Column('issue_type', sa.String(length=50), nullable=False),
        sa.Column('priority', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('resolution', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.ForeignKeyConstraint(['conversation_id'], ['support_conversations.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_support_tickets_brand_id'), 'support_tickets', ['brand_id'], unique=False)
    op.create_index(op.f('ix_support_tickets_shopify_customer_id'), 'support_tickets', ['shopify_customer_id'], unique=False)
    op.create_index(op.f('ix_support_tickets_shopify_order_id'), 'support_tickets', ['shopify_order_id'], unique=False)

    op.create_table(
        'support_actions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('ticket_id', sa.UUID(), nullable=False),
        sa.Column('action_type', sa.String(length=50), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.ForeignKeyConstraint(['ticket_id'], ['support_tickets.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_support_actions_brand_id'), 'support_actions', ['brand_id'], unique=False)
    op.create_index(op.f('ix_support_actions_ticket_id'), 'support_actions', ['ticket_id'], unique=False)

    op.create_table(
        'refund_records',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('ticket_id', sa.UUID(), nullable=True),
        sa.Column('shopify_order_id', sa.BigInteger(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('shopify_refund_id', sa.BigInteger(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.ForeignKeyConstraint(['ticket_id'], ['support_tickets.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_refund_records_brand_id'), 'refund_records', ['brand_id'], unique=False)

    op.create_table(
        'exchange_records',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('ticket_id', sa.UUID(), nullable=True),
        sa.Column('shopify_order_id', sa.BigInteger(), nullable=False),
        sa.Column('original_sku', sa.String(length=255), nullable=False),
        sa.Column('new_sku', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.ForeignKeyConstraint(['ticket_id'], ['support_tickets.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_exchange_records_brand_id'), 'exchange_records', ['brand_id'], unique=False)

    op.create_table(
        'customer_feedback',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.String(length=100), nullable=False),
        sa.Column('shopify_customer_id', sa.BigInteger(), nullable=True),
        sa.Column('sentiment', sa.String(length=20), nullable=False),
        sa.Column('feedback', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.brand_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_customer_feedback_brand_id'), 'customer_feedback', ['brand_id'], unique=False)
    op.create_index(op.f('ix_customer_feedback_shopify_customer_id'), 'customer_feedback', ['shopify_customer_id'], unique=False)

    op.create_table(
        'support_insights',
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
    op.create_index(op.f('ix_support_insights_brand_id'), 'support_insights', ['brand_id'], unique=False)

    # policy_documents.agent is unconstrained String — "customer_support"
    # needs no schema change there either, same note as supplier's migration.


def downgrade() -> None:
    op.drop_index(op.f('ix_support_insights_brand_id'), table_name='support_insights')
    op.drop_table('support_insights')
    op.drop_index(op.f('ix_customer_feedback_shopify_customer_id'), table_name='customer_feedback')
    op.drop_index(op.f('ix_customer_feedback_brand_id'), table_name='customer_feedback')
    op.drop_table('customer_feedback')
    op.drop_index(op.f('ix_exchange_records_brand_id'), table_name='exchange_records')
    op.drop_table('exchange_records')
    op.drop_index(op.f('ix_refund_records_brand_id'), table_name='refund_records')
    op.drop_table('refund_records')
    op.drop_index(op.f('ix_support_actions_ticket_id'), table_name='support_actions')
    op.drop_index(op.f('ix_support_actions_brand_id'), table_name='support_actions')
    op.drop_table('support_actions')
    op.drop_index(op.f('ix_support_tickets_shopify_order_id'), table_name='support_tickets')
    op.drop_index(op.f('ix_support_tickets_shopify_customer_id'), table_name='support_tickets')
    op.drop_index(op.f('ix_support_tickets_brand_id'), table_name='support_tickets')
    op.drop_table('support_tickets')
    op.drop_index(op.f('ix_support_messages_conversation_id'), table_name='support_messages')
    op.drop_index(op.f('ix_support_messages_brand_id'), table_name='support_messages')
    op.drop_table('support_messages')
    op.drop_index(op.f('ix_support_conversations_shopify_customer_id'), table_name='support_conversations')
    op.drop_index(op.f('ix_support_conversations_brand_id'), table_name='support_conversations')
    op.drop_table('support_conversations')
    op.drop_column('customers', 'phone')