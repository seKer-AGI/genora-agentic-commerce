"""initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-09-23 14:56:48.248884
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
import pgvector.sqlalchemy
from sqlalchemy.dialects import postgresql

revision: str = '0001_initial'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    op.execute('CREATE EXTENSION IF NOT EXISTS citext')
    op.create_table('categories',
    sa.Column('parent_id', sa.UUID(), nullable=True),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('slug', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('icon', sa.String(length=48), nullable=True),
    sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['parent_id'], ['categories.id'], name=op.f('fk_categories_parent_id_categories'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_categories')),
    sa.UniqueConstraint('slug', name=op.f('uq_categories_slug'))
    )
    op.create_index(op.f('ix_categories_parent_id'), 'categories', ['parent_id'], unique=False)
    op.create_table('email_outbox',
    sa.Column('to_email', sa.String(length=255), nullable=False),
    sa.Column('subject', sa.String(length=255), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('template', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='queued', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_email_outbox'))
    )
    op.create_table('permissions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_permissions')),
    sa.UniqueConstraint('code', name=op.f('uq_permissions_code'))
    )
    op.create_table('roles',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=32), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_roles')),
    sa.UniqueConstraint('name', name=op.f('uq_roles_name'))
    )
    op.create_table('users',
    sa.Column('email', postgresql.CITEXT(), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=120), nullable=False),
    sa.Column('phone', sa.String(length=32), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('is_email_verified', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('addresses',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('label', sa.String(length=40), nullable=True),
    sa.Column('recipient_name', sa.String(length=120), nullable=False),
    sa.Column('line1', sa.String(length=200), nullable=False),
    sa.Column('line2', sa.String(length=200), nullable=True),
    sa.Column('city', sa.String(length=100), nullable=False),
    sa.Column('state', sa.String(length=100), nullable=True),
    sa.Column('postal_code', sa.String(length=20), nullable=False),
    sa.Column('country', sa.String(length=2), nullable=False),
    sa.Column('phone', sa.String(length=32), nullable=True),
    sa.Column('is_default', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_addresses_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_addresses'))
    )
    op.create_index(op.f('ix_addresses_user_id'), 'addresses', ['user_id'], unique=False)
    op.create_table('audit_logs',
    sa.Column('actor_user_id', sa.UUID(), nullable=True),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('entity_type', sa.String(length=48), nullable=False),
    sa.Column('entity_id', sa.String(length=64), nullable=True),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_audit_logs_actor_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_logs'))
    )
    op.create_index(op.f('ix_audit_logs_actor_user_id'), 'audit_logs', ['actor_user_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)
    op.create_index('ix_audit_logs_entity', 'audit_logs', ['entity_type', 'entity_id'], unique=False)
    op.create_table('auth_tokens',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('purpose', sa.Enum('password_reset', 'email_verification', name='authtokenpurpose', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_auth_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_auth_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_auth_tokens_token_hash'))
    )
    op.create_index(op.f('ix_auth_tokens_user_id'), 'auth_tokens', ['user_id'], unique=False)
    op.create_table('buyer_profiles',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('display_name', sa.String(length=80), nullable=True),
    sa.Column('preferences', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('marketing_opt_in', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_buyer_profiles_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_buyer_profiles')),
    sa.UniqueConstraint('user_id', name=op.f('uq_buyer_profiles_user_id'))
    )
    op.create_table('carts',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('coupon_code', sa.String(length=40), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_carts_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_carts')),
    sa.UniqueConstraint('user_id', name=op.f('uq_carts_user_id'))
    )
    op.create_table('conversations',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('agent', sa.Enum('nova', 'astra', 'apex', name='agentname', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('title', sa.String(length=160), nullable=True),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_conversations_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_conversations'))
    )
    op.create_index('ix_conversations_user_agent', 'conversations', ['user_id', 'agent', 'updated_at'], unique=False)
    op.create_table('notifications',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.String(length=48), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_notifications_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notifications'))
    )
    op.create_index(op.f('ix_notifications_created_at'), 'notifications', ['created_at'], unique=False)
    op.create_index('ix_notifications_user_unread', 'notifications', ['user_id', 'read_at'], unique=False)
    op.create_table('refresh_tokens',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('family_id', sa.UUID(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('replaced_by_id', sa.UUID(), nullable=True),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_refresh_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_refresh_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_refresh_tokens_token_hash'))
    )
    op.create_index(op.f('ix_refresh_tokens_family_id'), 'refresh_tokens', ['family_id'], unique=False)
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)
    op.create_table('role_permissions',
    sa.Column('role_id', sa.Integer(), nullable=False),
    sa.Column('permission_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], name=op.f('fk_role_permissions_permission_id_permissions'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], name=op.f('fk_role_permissions_role_id_roles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('role_id', 'permission_id', name=op.f('pk_role_permissions'))
    )
    op.create_table('search_history',
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('query', sa.String(length=300), nullable=False),
    sa.Column('filters', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('mode', sa.String(length=16), nullable=False),
    sa.Column('source', sa.String(length=16), server_default='web', nullable=False),
    sa.Column('result_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('latency_ms', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_search_history_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_search_history'))
    )
    op.create_index('ix_search_history_created', 'search_history', ['created_at'], unique=False)
    op.create_index(op.f('ix_search_history_user_id'), 'search_history', ['user_id'], unique=False)
    op.create_table('seller_profiles',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('store_name', sa.String(length=120), nullable=False),
    sa.Column('slug', sa.String(length=140), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('logo_url', sa.String(length=512), nullable=True),
    sa.Column('support_email', sa.String(length=255), nullable=True),
    sa.Column('country', sa.String(length=2), nullable=True),
    sa.Column('status', sa.Enum('pending', 'active', 'suspended', name='sellerstatus', native_enum=False, create_constraint=True, length=32), server_default='pending', nullable=False),
    sa.Column('rating_avg', sa.Numeric(precision=3, scale=2), server_default='0', nullable=False),
    sa.Column('negotiation_enabled', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_seller_profiles_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_seller_profiles')),
    sa.UniqueConstraint('slug', name=op.f('uq_seller_profiles_slug')),
    sa.UniqueConstraint('store_name', name=op.f('uq_seller_profiles_store_name')),
    sa.UniqueConstraint('user_id', name=op.f('uq_seller_profiles_user_id'))
    )
    op.create_table('system_settings',
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_system_settings_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_system_settings'))
    )
    op.create_table('user_roles',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('role_id', sa.Integer(), nullable=False),
    sa.Column('granted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], name=op.f('fk_user_roles_role_id_roles'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_roles_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'role_id', name=op.f('pk_user_roles'))
    )
    op.create_table('wishlists',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_wishlists_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_wishlists')),
    sa.UniqueConstraint('user_id', name=op.f('uq_wishlists_user_id'))
    )
    op.create_table('agent_sessions',
    sa.Column('conversation_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('agent', sa.Enum('nova', 'astra', 'apex', name='agentname', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('context', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('pending_action', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('last_active_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_agent_sessions_conversation_id_conversations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_agent_sessions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_sessions')),
    sa.UniqueConstraint('conversation_id', name=op.f('uq_agent_sessions_conversation_id'))
    )
    op.create_index(op.f('ix_agent_sessions_user_id'), 'agent_sessions', ['user_id'], unique=False)
    op.create_table('bundles',
    sa.Column('seller_id', sa.UUID(), nullable=True),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('slug', sa.String(length=180), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('discount_type', sa.Enum('percentage', 'fixed', name='discounttype', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('value', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("(discount_type = 'percentage' AND value > 0 AND value <= 90) OR (discount_type = 'fixed' AND value > 0)", name=op.f('ck_bundles_value_valid')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_bundles_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['seller_id'], ['seller_profiles.id'], name=op.f('fk_bundles_seller_id_seller_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_bundles')),
    sa.UniqueConstraint('slug', name=op.f('uq_bundles_slug'))
    )
    op.create_index(op.f('ix_bundles_seller_id'), 'bundles', ['seller_id'], unique=False)
    op.create_table('coupons',
    sa.Column('code', postgresql.CITEXT(), nullable=False),
    sa.Column('seller_id', sa.UUID(), nullable=True),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('discount_type', sa.Enum('percentage', 'fixed', name='discounttype', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('value', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('min_subtotal', sa.Numeric(precision=12, scale=2), server_default='0', nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('usage_limit', sa.Integer(), nullable=True),
    sa.Column('per_user_limit', sa.Integer(), server_default='1', nullable=False),
    sa.Column('used_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("(discount_type = 'percentage' AND value > 0 AND value <= 90) OR (discount_type = 'fixed' AND value > 0)", name=op.f('ck_coupons_value_valid')),
    sa.ForeignKeyConstraint(['seller_id'], ['seller_profiles.id'], name=op.f('fk_coupons_seller_id_seller_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_coupons')),
    sa.UniqueConstraint('code', name=op.f('uq_coupons_code'))
    )
    op.create_table('forecast_results',
    sa.Column('target', sa.String(length=32), nullable=False),
    sa.Column('entity_id', sa.Uuid(), nullable=True),
    sa.Column('seller_id', sa.UUID(), nullable=True),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('model_name', sa.String(length=80), nullable=False),
    sa.Column('status', sa.Enum('completed', 'failed', name='forecaststatus', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('frequency', sa.String(length=8), server_default='D', nullable=False),
    sa.Column('horizon', sa.Integer(), nullable=False),
    sa.Column('history_start', sa.Date(), nullable=True),
    sa.Column('history_end', sa.Date(), nullable=True),
    sa.Column('history_points', sa.Integer(), server_default='0', nullable=False),
    sa.Column('points', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('requested_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['requested_by'], ['users.id'], name=op.f('fk_forecast_results_requested_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['seller_id'], ['seller_profiles.id'], name=op.f('fk_forecast_results_seller_id_seller_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_forecast_results'))
    )
    op.create_index('ix_forecast_results_target_entity', 'forecast_results', ['target', 'entity_id', 'created_at'], unique=False)
    op.create_table('orders',
    sa.Column('order_number', sa.String(length=32), nullable=False),
    sa.Column('checkout_group_id', sa.UUID(), nullable=False),
    sa.Column('buyer_id', sa.UUID(), nullable=False),
    sa.Column('seller_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.Enum('pending', 'confirmed', 'processing', 'shipped', 'delivered', 'cancelled', 'refunded', name='orderstatus', native_enum=False, create_constraint=True, length=32), server_default='pending', nullable=False),
    sa.Column('currency', sa.String(length=3), server_default='USD', nullable=False),
    sa.Column('subtotal', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('discount_total', sa.Numeric(precision=12, scale=2), server_default='0', nullable=False),
    sa.Column('tax_total', sa.Numeric(precision=12, scale=2), server_default='0', nullable=False),
    sa.Column('shipping_total', sa.Numeric(precision=12, scale=2), server_default='0', nullable=False),
    sa.Column('total', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('shipping_address', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('tracking_number', sa.String(length=64), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('placed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('shipped_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['buyer_id'], ['users.id'], name=op.f('fk_orders_buyer_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['seller_id'], ['seller_profiles.id'], name=op.f('fk_orders_seller_id_seller_profiles'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_orders')),
    sa.UniqueConstraint('order_number', name=op.f('uq_orders_order_number'))
    )
    op.create_index('ix_orders_buyer_placed', 'orders', ['buyer_id', 'placed_at'], unique=False)
    op.create_index(op.f('ix_orders_checkout_group_id'), 'orders', ['checkout_group_id'], unique=False)
    op.create_index('ix_orders_placed_at', 'orders', ['placed_at'], unique=False)
    op.create_index('ix_orders_seller_status', 'orders', ['seller_id', 'status'], unique=False)
    op.create_table('products',
    sa.Column('seller_id', sa.UUID(), nullable=False),
    sa.Column('category_id', sa.UUID(), nullable=True),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('slug', sa.String(length=240), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('seo_description', sa.String(length=320), nullable=True),
    sa.Column('sku', sa.String(length=64), nullable=False),
    sa.Column('brand', sa.String(length=80), nullable=True),
    sa.Column('price', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('sale_price', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('currency', sa.String(length=3), server_default='USD', nullable=False),
    sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('tags', sa.ARRAY(sa.String(length=48)), server_default='{}', nullable=False),
    sa.Column('keywords', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('draft', 'active', 'archived', 'blocked', name='productstatus', native_enum=False, create_constraint=True, length=32), server_default='draft', nullable=False),
    sa.Column('rating_avg', sa.Numeric(precision=3, scale=2), server_default='0', nullable=False),
    sa.Column('rating_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('sold_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('search_vector', postgresql.TSVECTOR(), sa.Computed("setweight(to_tsvector('english', coalesce(name, '')), 'A') || setweight(to_tsvector('english', coalesce(brand, '')), 'A') || setweight(to_tsvector('english', coalesce(keywords, '')), 'B') || setweight(to_tsvector('english', coalesce(description, '')), 'C')", persisted=True), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
    sa.Column('embedding_model', sa.String(length=80), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('price >= 0', name=op.f('ck_products_price_non_negative')),
    sa.CheckConstraint('sale_price IS NULL OR (sale_price >= 0 AND sale_price <= price)', name=op.f('ck_products_sale_price_valid')),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], name=op.f('fk_products_category_id_categories'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['seller_id'], ['seller_profiles.id'], name=op.f('fk_products_seller_id_seller_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_products')),
    sa.UniqueConstraint('seller_id', 'sku', name='uq_products_seller_sku'),
    sa.UniqueConstraint('slug', name=op.f('uq_products_slug'))
    )
    op.create_index(op.f('ix_products_brand'), 'products', ['brand'], unique=False)
    op.create_index('ix_products_embedding_hnsw', 'products', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index('ix_products_name_trgm', 'products', ['name'], unique=False, postgresql_using='gin', postgresql_ops={'name': 'gin_trgm_ops'})
    op.create_index('ix_products_search_vector', 'products', ['search_vector'], unique=False, postgresql_using='gin')
    op.create_index(op.f('ix_products_seller_id'), 'products', ['seller_id'], unique=False)
    op.create_index('ix_products_status_category', 'products', ['status', 'category_id'], unique=False)
    op.create_index('ix_products_tags', 'products', ['tags'], unique=False, postgresql_using='gin')
    op.create_table('agent_workflows',
    sa.Column('session_id', sa.UUID(), nullable=True),
    sa.Column('conversation_id', sa.UUID(), nullable=True),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('agent', sa.Enum('nova', 'astra', 'apex', name='agentname', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('intent', sa.String(length=64), nullable=False),
    sa.Column('workflow_name', sa.String(length=64), nullable=False),
    sa.Column('status', sa.Enum('running', 'completed', 'failed', 'needs_clarification', 'awaiting_confirmation', 'blocked', name='workflowstatus', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('nlu_mode', sa.String(length=16), server_default='rules', nullable=False),
    sa.Column('model_name', sa.String(length=80), nullable=True),
    sa.Column('prompt_tokens', sa.Integer(), server_default='0', nullable=False),
    sa.Column('completion_tokens', sa.Integer(), server_default='0', nullable=False),
    sa.Column('steps', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('safety_flags', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('error_code', sa.String(length=64), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_agent_workflows_conversation_id_conversations'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['session_id'], ['agent_sessions.id'], name=op.f('fk_agent_workflows_session_id_agent_sessions'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_agent_workflows_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_workflows'))
    )
    op.create_index('ix_agent_workflows_agent_started', 'agent_workflows', ['agent', 'started_at'], unique=False)
    op.create_index('ix_agent_workflows_intent', 'agent_workflows', ['intent'], unique=False)
    op.create_index(op.f('ix_agent_workflows_user_id'), 'agent_workflows', ['user_id'], unique=False)
    op.create_table('analytics_events',
    sa.Column('event_type', sa.String(length=48), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('session_key', sa.String(length=64), nullable=True),
    sa.Column('product_id', sa.UUID(), nullable=True),
    sa.Column('seller_id', sa.UUID(), nullable=True),
    sa.Column('category_id', sa.UUID(), nullable=True),
    sa.Column('order_id', sa.UUID(), nullable=True),
    sa.Column('value', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('properties', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], name=op.f('fk_analytics_events_category_id_categories'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_analytics_events_order_id_orders'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_analytics_events_product_id_products'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['seller_id'], ['seller_profiles.id'], name=op.f('fk_analytics_events_seller_id_seller_profiles'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_analytics_events_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_analytics_events'))
    )
    op.create_index('ix_analytics_events_product_type', 'analytics_events', ['product_id', 'event_type'], unique=False)
    op.create_index('ix_analytics_events_seller_created', 'analytics_events', ['seller_id', 'created_at'], unique=False)
    op.create_index('ix_analytics_events_type_created', 'analytics_events', ['event_type', 'created_at'], unique=False)
    op.create_index('ix_analytics_events_user_created', 'analytics_events', ['user_id', 'created_at'], unique=False)
    op.create_table('bundle_items',
    sa.Column('bundle_id', sa.UUID(), nullable=False),
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('quantity', sa.Integer(), server_default='1', nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_bundle_items_quantity_positive')),
    sa.ForeignKeyConstraint(['bundle_id'], ['bundles.id'], name=op.f('fk_bundle_items_bundle_id_bundles'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_bundle_items_product_id_products'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_bundle_items')),
    sa.UniqueConstraint('bundle_id', 'product_id', name='uq_bundle_items_product')
    )
    op.create_index(op.f('ix_bundle_items_bundle_id'), 'bundle_items', ['bundle_id'], unique=False)
    op.create_index(op.f('ix_bundle_items_product_id'), 'bundle_items', ['product_id'], unique=False)
    op.create_table('negotiation_rules',
    sa.Column('seller_id', sa.UUID(), nullable=False),
    sa.Column('product_id', sa.UUID(), nullable=True),
    sa.Column('is_enabled', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('max_discount_percent', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('auto_accept_percent', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('auto_accept_percent >= 0 AND auto_accept_percent <= max_discount_percent', name=op.f('ck_negotiation_rules_auto_accept_range')),
    sa.CheckConstraint('max_discount_percent >= 0 AND max_discount_percent <= 90', name=op.f('ck_negotiation_rules_max_discount_range')),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_negotiation_rules_product_id_products'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['seller_id'], ['seller_profiles.id'], name=op.f('fk_negotiation_rules_seller_id_seller_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_negotiation_rules')),
    sa.UniqueConstraint('seller_id', 'product_id', name='uq_negotiation_rules_seller_product', postgresql_nulls_not_distinct=True)
    )
    op.create_index(op.f('ix_negotiation_rules_seller_id'), 'negotiation_rules', ['seller_id'], unique=False)
    op.create_table('negotiations',
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('buyer_id', sa.UUID(), nullable=False),
    sa.Column('seller_id', sa.UUID(), nullable=False),
    sa.Column('list_price', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('offered_price', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('counter_price', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('agreed_price', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('status', sa.Enum('accepted', 'countered', 'rejected', 'expired', 'used', name='negotiationstatus', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('reason', sa.String(length=255), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['buyer_id'], ['users.id'], name=op.f('fk_negotiations_buyer_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_negotiations_product_id_products'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['seller_id'], ['seller_profiles.id'], name=op.f('fk_negotiations_seller_id_seller_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_negotiations'))
    )
    op.create_index('ix_negotiations_buyer_product', 'negotiations', ['buyer_id', 'product_id'], unique=False)
    op.create_index(op.f('ix_negotiations_seller_id'), 'negotiations', ['seller_id'], unique=False)
    op.create_table('offers',
    sa.Column('seller_id', sa.UUID(), nullable=True),
    sa.Column('product_id', sa.UUID(), nullable=True),
    sa.Column('category_id', sa.UUID(), nullable=True),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('discount_type', sa.Enum('percentage', 'fixed', name='discounttype', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('value', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('min_quantity', sa.Integer(), server_default='1', nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("(discount_type = 'percentage' AND value > 0 AND value <= 90) OR (discount_type = 'fixed' AND value > 0)", name=op.f('ck_offers_value_valid')),
    sa.CheckConstraint('ends_at IS NULL OR starts_at IS NULL OR ends_at > starts_at', name=op.f('ck_offers_window_valid')),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], name=op.f('fk_offers_category_id_categories'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_offers_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_offers_product_id_products'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['seller_id'], ['seller_profiles.id'], name=op.f('fk_offers_seller_id_seller_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_offers'))
    )
    op.create_index('ix_offers_active_window', 'offers', ['is_active', 'starts_at', 'ends_at'], unique=False)
    op.create_index(op.f('ix_offers_product_id'), 'offers', ['product_id'], unique=False)
    op.create_index(op.f('ix_offers_seller_id'), 'offers', ['seller_id'], unique=False)
    op.create_table('order_status_events',
    sa.Column('order_id', sa.UUID(), nullable=False),
    sa.Column('from_status', sa.String(length=32), nullable=True),
    sa.Column('to_status', sa.String(length=32), nullable=False),
    sa.Column('actor_user_id', sa.UUID(), nullable=True),
    sa.Column('note', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_order_status_events_actor_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_order_status_events_order_id_orders'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_order_status_events'))
    )
    op.create_index(op.f('ix_order_status_events_order_id'), 'order_status_events', ['order_id'], unique=False)
    op.create_table('payments',
    sa.Column('order_id', sa.UUID(), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('provider_reference', sa.String(length=128), nullable=True),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('status', sa.Enum('pending', 'authorized', 'captured', 'failed', 'refunded', name='paymentstatus', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('failure_reason', sa.String(length=255), nullable=True),
    sa.Column('provider_metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_payments_order_id_orders'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payments'))
    )
    op.create_index(op.f('ix_payments_order_id'), 'payments', ['order_id'], unique=False)
    op.create_index(op.f('ix_payments_provider_reference'), 'payments', ['provider_reference'], unique=False)
    op.create_table('product_images',
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('url', sa.String(length=512), nullable=False),
    sa.Column('alt_text', sa.String(length=200), nullable=True),
    sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
    sa.Column('is_primary', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_product_images_product_id_products'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_product_images'))
    )
    op.create_index(op.f('ix_product_images_product_id'), 'product_images', ['product_id'], unique=False)
    op.create_table('product_variants',
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('sku', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('price_override', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_product_variants_product_id_products'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_product_variants')),
    sa.UniqueConstraint('product_id', 'sku', name='uq_product_variants_product_sku')
    )
    op.create_index(op.f('ix_product_variants_product_id'), 'product_variants', ['product_id'], unique=False)
    op.create_table('ratings',
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('average', sa.Numeric(precision=3, scale=2), server_default='0', nullable=False),
    sa.Column('count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('distribution', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_ratings_product_id_products'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('product_id', name=op.f('pk_ratings'))
    )
    op.create_table('recommendations',
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('context_product_id', sa.UUID(), nullable=True),
    sa.Column('recommended_product_id', sa.UUID(), nullable=False),
    sa.Column('strategy', sa.String(length=32), nullable=False),
    sa.Column('score', sa.Float(), nullable=False),
    sa.Column('rank', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['context_product_id'], ['products.id'], name=op.f('fk_recommendations_context_product_id_products'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recommended_product_id'], ['products.id'], name=op.f('fk_recommendations_recommended_product_id_products'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_recommendations_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_recommendations'))
    )
    op.create_index('ix_recommendations_user_created', 'recommendations', ['user_id', 'created_at'], unique=False)
    op.create_table('reviews',
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('order_id', sa.UUID(), nullable=True),
    sa.Column('rating', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=160), nullable=True),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('status', sa.Enum('pending', 'approved', 'rejected', name='reviewstatus', native_enum=False, create_constraint=True, length=32), server_default='pending', nullable=False),
    sa.Column('is_verified_purchase', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('helpful_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('moderation_reason', sa.String(length=255), nullable=True),
    sa.Column('moderated_by', sa.UUID(), nullable=True),
    sa.Column('moderated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('rating BETWEEN 1 AND 5', name=op.f('ck_reviews_rating_range')),
    sa.ForeignKeyConstraint(['moderated_by'], ['users.id'], name=op.f('fk_reviews_moderated_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_reviews_order_id_orders'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_reviews_product_id_products'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_reviews_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reviews')),
    sa.UniqueConstraint('product_id', 'user_id', name='uq_reviews_product_user')
    )
    op.create_index('ix_reviews_product_status', 'reviews', ['product_id', 'status'], unique=False)
    op.create_index(op.f('ix_reviews_user_id'), 'reviews', ['user_id'], unique=False)
    op.create_table('wishlist_items',
    sa.Column('wishlist_id', sa.UUID(), nullable=False),
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_wishlist_items_product_id_products'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['wishlist_id'], ['wishlists.id'], name=op.f('fk_wishlist_items_wishlist_id_wishlists'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_wishlist_items')),
    sa.UniqueConstraint('wishlist_id', 'product_id', name='uq_wishlist_items_product')
    )
    op.create_index(op.f('ix_wishlist_items_wishlist_id'), 'wishlist_items', ['wishlist_id'], unique=False)
    op.create_table('agent_tool_calls',
    sa.Column('workflow_id', sa.UUID(), nullable=False),
    sa.Column('tool_name', sa.String(length=64), nullable=False),
    sa.Column('status', sa.Enum('success', 'error', 'denied', name='toolcallstatus', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('input', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('output_summary', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('error_code', sa.String(length=64), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['workflow_id'], ['agent_workflows.id'], name=op.f('fk_agent_tool_calls_workflow_id_agent_workflows'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_tool_calls'))
    )
    op.create_index('ix_agent_tool_calls_tool_created', 'agent_tool_calls', ['tool_name', 'created_at'], unique=False)
    op.create_index(op.f('ix_agent_tool_calls_workflow_id'), 'agent_tool_calls', ['workflow_id'], unique=False)
    op.create_table('cart_items',
    sa.Column('cart_id', sa.UUID(), nullable=False),
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('variant_id', sa.UUID(), nullable=True),
    sa.Column('bundle_id', sa.UUID(), nullable=True),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('quantity > 0 AND quantity <= 99', name=op.f('ck_cart_items_quantity_range')),
    sa.ForeignKeyConstraint(['bundle_id'], ['bundles.id'], name=op.f('fk_cart_items_bundle_id_bundles'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['cart_id'], ['carts.id'], name=op.f('fk_cart_items_cart_id_carts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_cart_items_product_id_products'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['variant_id'], ['product_variants.id'], name=op.f('fk_cart_items_variant_id_product_variants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_cart_items')),
    sa.UniqueConstraint('cart_id', 'product_id', 'variant_id', 'bundle_id', name='uq_cart_items_line', postgresql_nulls_not_distinct=True)
    )
    op.create_index(op.f('ix_cart_items_cart_id'), 'cart_items', ['cart_id'], unique=False)
    op.create_table('inventory',
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('variant_id', sa.UUID(), nullable=True),
    sa.Column('quantity_on_hand', sa.Integer(), server_default='0', nullable=False),
    sa.Column('quantity_reserved', sa.Integer(), server_default='0', nullable=False),
    sa.Column('low_stock_threshold', sa.Integer(), server_default='5', nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.CheckConstraint('quantity_on_hand >= 0', name=op.f('ck_inventory_on_hand_non_negative')),
    sa.CheckConstraint('quantity_reserved >= 0', name=op.f('ck_inventory_reserved_non_negative')),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_inventory_product_id_products'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['variant_id'], ['product_variants.id'], name=op.f('fk_inventory_variant_id_product_variants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_inventory')),
    sa.UniqueConstraint('product_id', 'variant_id', name='uq_inventory_product_variant', postgresql_nulls_not_distinct=True)
    )
    op.create_index(op.f('ix_inventory_product_id'), 'inventory', ['product_id'], unique=False)
    op.create_table('messages',
    sa.Column('conversation_id', sa.UUID(), nullable=False),
    sa.Column('role', sa.Enum('user', 'assistant', 'system', name='messagerole', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('workflow_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_messages_conversation_id_conversations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workflow_id'], ['agent_workflows.id'], name=op.f('fk_messages_workflow_id_agent_workflows'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_messages'))
    )
    op.create_index('ix_messages_conversation_created', 'messages', ['conversation_id', 'created_at'], unique=False)
    op.create_table('order_items',
    sa.Column('order_id', sa.UUID(), nullable=False),
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('variant_id', sa.UUID(), nullable=True),
    sa.Column('bundle_id', sa.UUID(), nullable=True),
    sa.Column('product_name', sa.String(length=200), nullable=False),
    sa.Column('sku', sa.String(length=64), nullable=False),
    sa.Column('unit_price', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('discount_amount', sa.Numeric(precision=12, scale=2), server_default='0', nullable=False),
    sa.Column('line_total', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_order_items_quantity_positive')),
    sa.ForeignKeyConstraint(['bundle_id'], ['bundles.id'], name=op.f('fk_order_items_bundle_id_bundles'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_order_items_order_id_orders'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_order_items_product_id_products'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['variant_id'], ['product_variants.id'], name=op.f('fk_order_items_variant_id_product_variants'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_order_items'))
    )
    op.create_index(op.f('ix_order_items_order_id'), 'order_items', ['order_id'], unique=False)
    op.create_index(op.f('ix_order_items_product_id'), 'order_items', ['product_id'], unique=False)
    op.create_table('discounts',
    sa.Column('order_id', sa.UUID(), nullable=False),
    sa.Column('order_item_id', sa.UUID(), nullable=True),
    sa.Column('source', sa.Enum('offer', 'bundle', 'coupon', 'negotiation', name='discountsource', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('source_id', sa.UUID(), nullable=True),
    sa.Column('description', sa.String(length=200), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_discounts_order_id_orders'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['order_item_id'], ['order_items.id'], name=op.f('fk_discounts_order_item_id_order_items'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_discounts'))
    )
    op.create_index(op.f('ix_discounts_order_id'), 'discounts', ['order_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_discounts_order_id'), table_name='discounts')
    op.drop_table('discounts')
    op.drop_index(op.f('ix_order_items_product_id'), table_name='order_items')
    op.drop_index(op.f('ix_order_items_order_id'), table_name='order_items')
    op.drop_table('order_items')
    op.drop_index('ix_messages_conversation_created', table_name='messages')
    op.drop_table('messages')
    op.drop_index(op.f('ix_inventory_product_id'), table_name='inventory')
    op.drop_table('inventory')
    op.drop_index(op.f('ix_cart_items_cart_id'), table_name='cart_items')
    op.drop_table('cart_items')
    op.drop_index(op.f('ix_agent_tool_calls_workflow_id'), table_name='agent_tool_calls')
    op.drop_index('ix_agent_tool_calls_tool_created', table_name='agent_tool_calls')
    op.drop_table('agent_tool_calls')
    op.drop_index(op.f('ix_wishlist_items_wishlist_id'), table_name='wishlist_items')
    op.drop_table('wishlist_items')
    op.drop_index(op.f('ix_reviews_user_id'), table_name='reviews')
    op.drop_index('ix_reviews_product_status', table_name='reviews')
    op.drop_table('reviews')
    op.drop_index('ix_recommendations_user_created', table_name='recommendations')
    op.drop_table('recommendations')
    op.drop_table('ratings')
    op.drop_index(op.f('ix_product_variants_product_id'), table_name='product_variants')
    op.drop_table('product_variants')
    op.drop_index(op.f('ix_product_images_product_id'), table_name='product_images')
    op.drop_table('product_images')
    op.drop_index(op.f('ix_payments_provider_reference'), table_name='payments')
    op.drop_index(op.f('ix_payments_order_id'), table_name='payments')
    op.drop_table('payments')
    op.drop_index(op.f('ix_order_status_events_order_id'), table_name='order_status_events')
    op.drop_table('order_status_events')
    op.drop_index(op.f('ix_offers_seller_id'), table_name='offers')
    op.drop_index(op.f('ix_offers_product_id'), table_name='offers')
    op.drop_index('ix_offers_active_window', table_name='offers')
    op.drop_table('offers')
    op.drop_index(op.f('ix_negotiations_seller_id'), table_name='negotiations')
    op.drop_index('ix_negotiations_buyer_product', table_name='negotiations')
    op.drop_table('negotiations')
    op.drop_index(op.f('ix_negotiation_rules_seller_id'), table_name='negotiation_rules')
    op.drop_table('negotiation_rules')
    op.drop_index(op.f('ix_bundle_items_product_id'), table_name='bundle_items')
    op.drop_index(op.f('ix_bundle_items_bundle_id'), table_name='bundle_items')
    op.drop_table('bundle_items')
    op.drop_index('ix_analytics_events_user_created', table_name='analytics_events')
    op.drop_index('ix_analytics_events_type_created', table_name='analytics_events')
    op.drop_index('ix_analytics_events_seller_created', table_name='analytics_events')
    op.drop_index('ix_analytics_events_product_type', table_name='analytics_events')
    op.drop_table('analytics_events')
    op.drop_index(op.f('ix_agent_workflows_user_id'), table_name='agent_workflows')
    op.drop_index('ix_agent_workflows_intent', table_name='agent_workflows')
    op.drop_index('ix_agent_workflows_agent_started', table_name='agent_workflows')
    op.drop_table('agent_workflows')
    op.drop_index('ix_products_tags', table_name='products', postgresql_using='gin')
    op.drop_index('ix_products_status_category', table_name='products')
    op.drop_index(op.f('ix_products_seller_id'), table_name='products')
    op.drop_index('ix_products_search_vector', table_name='products', postgresql_using='gin')
    op.drop_index('ix_products_name_trgm', table_name='products', postgresql_using='gin', postgresql_ops={'name': 'gin_trgm_ops'})
    op.drop_index('ix_products_embedding_hnsw', table_name='products', postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_index(op.f('ix_products_brand'), table_name='products')
    op.drop_table('products')
    op.drop_index('ix_orders_seller_status', table_name='orders')
    op.drop_index('ix_orders_placed_at', table_name='orders')
    op.drop_index(op.f('ix_orders_checkout_group_id'), table_name='orders')
    op.drop_index('ix_orders_buyer_placed', table_name='orders')
    op.drop_table('orders')
    op.drop_index('ix_forecast_results_target_entity', table_name='forecast_results')
    op.drop_table('forecast_results')
    op.drop_table('coupons')
    op.drop_index(op.f('ix_bundles_seller_id'), table_name='bundles')
    op.drop_table('bundles')
    op.drop_index(op.f('ix_agent_sessions_user_id'), table_name='agent_sessions')
    op.drop_table('agent_sessions')
    op.drop_table('wishlists')
    op.drop_table('user_roles')
    op.drop_table('system_settings')
    op.drop_table('seller_profiles')
    op.drop_index(op.f('ix_search_history_user_id'), table_name='search_history')
    op.drop_index('ix_search_history_created', table_name='search_history')
    op.drop_table('search_history')
    op.drop_table('role_permissions')
    op.drop_index(op.f('ix_refresh_tokens_user_id'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_family_id'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_index('ix_notifications_user_unread', table_name='notifications')
    op.drop_index(op.f('ix_notifications_created_at'), table_name='notifications')
    op.drop_table('notifications')
    op.drop_index('ix_conversations_user_agent', table_name='conversations')
    op.drop_table('conversations')
    op.drop_table('carts')
    op.drop_table('buyer_profiles')
    op.drop_index(op.f('ix_auth_tokens_user_id'), table_name='auth_tokens')
    op.drop_table('auth_tokens')
    op.drop_index('ix_audit_logs_entity', table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_created_at'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_actor_user_id'), table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_index(op.f('ix_addresses_user_id'), table_name='addresses')
    op.drop_table('addresses')
    op.drop_table('users')
    op.drop_table('roles')
    op.drop_table('permissions')
    op.drop_table('email_outbox')
    op.drop_index(op.f('ix_categories_parent_id'), table_name='categories')
    op.drop_table('categories')
