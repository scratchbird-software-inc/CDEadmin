##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Add signed embedding of BI dashboards and questions.

Tables: the embed definition, its (at most two) encrypted signing secrets,
the run-as delegation and credential envelopes (shaped like
``cde_bi_alert_delegation`` so the report scheduler machinery serves it),
consumed one-time token ids and daily view counters.

Additive only; SCHEMA_VERSION is deliberately not bumped (owner-confirmed
convention for the BI tables).

Revision ID: cde_bi_embeds_v1
Revises: cde_bi_alerts_v1
Create Date: 2026-10-28
"""

from alembic import op
import sqlalchemy as sa


revision = 'cde_bi_embeds_v1'
down_revision = 'cde_bi_alerts_v1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cde_bi_embed',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('endpoint_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('resource_type', sa.String(length=16), nullable=False),
        sa.Column('resource_id', sa.String(length=36), nullable=False),
        sa.Column('resource_revision', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('disabled_reason', sa.String(length=48), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('definition', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("resource_type IN ('question', 'dashboard')",
                           name='ck_cde_bi_embed_resource'),
        sa.CheckConstraint("status IN ('enabled', 'disabled', 'revoked')",
                           name='ck_cde_bi_embed_status'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['endpoint_id'], ['cde_endpoint.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'endpoint_id', 'name',
                            name='uq_cde_bi_embed_name'),
    )
    op.create_index('ix_cde_bi_embed_resource', 'cde_bi_embed',
                    ['endpoint_id', 'resource_type', 'resource_id'])
    op.create_table(
        'cde_bi_embed_key',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('embed_id', sa.String(length=36), nullable=False),
        sa.Column('kid', sa.String(length=32), nullable=False),
        sa.Column('slot', sa.String(length=16), nullable=False),
        sa.Column('key_id', sa.String(length=64), nullable=False),
        sa.Column('encrypted_value', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("slot IN ('current', 'previous')",
                           name='ck_cde_bi_embed_slot'),
        sa.ForeignKeyConstraint(['embed_id'], ['cde_bi_embed.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('embed_id', 'kid', name='uq_cde_bi_embed_kid'),
        sa.UniqueConstraint('embed_id', 'slot', name='uq_cde_bi_embed_slot'),
    )
    op.create_table(
        'cde_bi_embed_delegation',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('embed_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('endpoint_id', sa.String(length=36), nullable=False),
        sa.Column('route_id', sa.String(length=128), nullable=False),
        sa.Column('primary_secret_kind', sa.String(length=128),
                  nullable=True),
        sa.Column('endpoint_generation', sa.String(length=64),
                  nullable=False),
        sa.Column('state', sa.String(length=16), nullable=False),
        sa.Column('credential_generation', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint("state IN ('active', 'revoked', 'expired')",
                           name='ck_cde_bi_embed_delegation_state'),
        sa.ForeignKeyConstraint(['embed_id'], ['cde_bi_embed.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['endpoint_id'], ['cde_endpoint.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('embed_id', name='uq_cde_bi_embed_delegation'),
    )
    op.create_table(
        'cde_bi_embed_credential',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('delegation_id', sa.String(length=36), nullable=False),
        sa.Column('secret_kind', sa.String(length=128), nullable=False),
        sa.Column('key_id', sa.String(length=64), nullable=False),
        sa.Column('encrypted_value', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['delegation_id'],
                                ['cde_bi_embed_delegation.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('delegation_id', 'secret_kind',
                            name='uq_cde_bi_embed_secret_kind'),
    )
    op.create_table(
        'cde_bi_embed_jti',
        sa.Column('embed_id', sa.String(length=36), nullable=False),
        sa.Column('jti', sa.String(length=128), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['embed_id'], ['cde_bi_embed.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('embed_id', 'jti'),
    )
    op.create_index('ix_cde_bi_embed_jti_expiry', 'cde_bi_embed_jti',
                    ['expires_at'])
    op.create_table(
        'cde_bi_embed_stat',
        sa.Column('embed_id', sa.String(length=36), nullable=False),
        sa.Column('day', sa.String(length=10), nullable=False),
        sa.Column('views', sa.Integer(), nullable=False),
        sa.Column('card_runs', sa.Integer(), nullable=False),
        sa.Column('errors', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['embed_id'], ['cde_bi_embed.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('embed_id', 'day'),
    )


def downgrade():
    op.drop_table('cde_bi_embed_stat')
    op.drop_index('ix_cde_bi_embed_jti_expiry',
                  table_name='cde_bi_embed_jti')
    op.drop_table('cde_bi_embed_jti')
    op.drop_table('cde_bi_embed_credential')
    op.drop_table('cde_bi_embed_delegation')
    op.drop_table('cde_bi_embed_key')
    op.drop_index('ix_cde_bi_embed_resource', table_name='cde_bi_embed')
    op.drop_table('cde_bi_embed')
