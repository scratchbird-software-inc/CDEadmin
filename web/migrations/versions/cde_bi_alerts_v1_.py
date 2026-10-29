##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Add BI threshold alerts and scheduled subscriptions.

Tables: the alert definition, its revocable delegation (shaped like
``cde_report_delegation`` so the report scheduler machinery serves both),
delegated credential envelopes, scheduled occurrences, evaluation history
and in-app notifications.

Additive only; SCHEMA_VERSION is deliberately not bumped (owner-confirmed
convention for the BI tables).

Revision ID: cde_bi_alerts_v1
Revises: cde_bi_permissions_v1
Create Date: 2026-10-28
"""

from alembic import op
import sqlalchemy as sa


revision = 'cde_bi_alerts_v1'
down_revision = 'cde_bi_permissions_v1'
branch_labels = None
depends_on = None

OCCURRENCE_STATES = (
    "state IN ('scheduled', 'claimed', 'executing', 'delivering', "
    "'delivered', 'failed', 'cancel_requested', 'cancelled', "
    "'outcome_unknown')"
)


def upgrade():
    op.create_table(
        'cde_bi_alert',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('endpoint_id', sa.String(length=36), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('resource_type', sa.String(length=16), nullable=False),
        sa.Column('resource_id', sa.String(length=36), nullable=False),
        sa.Column('resource_revision', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('pause_reason', sa.String(length=48), nullable=True),
        sa.Column('paused_at', sa.DateTime(), nullable=True),
        sa.Column('muted_until', sa.DateTime(), nullable=True),
        sa.Column('breach_state', sa.String(length=16), nullable=False),
        sa.Column('pending_notify', sa.Boolean(), nullable=False),
        sa.Column('last_value', sa.Text(), nullable=True),
        sa.Column('last_evaluated_at', sa.DateTime(), nullable=True),
        sa.Column('last_fired_at', sa.DateTime(), nullable=True),
        sa.Column('consecutive_failures', sa.Integer(), nullable=False),
        sa.Column('schedule_anchor', sa.DateTime(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('definition', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("kind IN ('alert', 'subscription')",
                           name='ck_cde_bi_alert_kind'),
        sa.CheckConstraint("resource_type IN ('question', 'dashboard')",
                           name='ck_cde_bi_alert_resource'),
        sa.CheckConstraint("status IN ('active', 'paused')",
                           name='ck_cde_bi_alert_status'),
        sa.CheckConstraint("breach_state IN ('unknown', 'ok', 'breach')",
                           name='ck_cde_bi_alert_breach'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['endpoint_id'], ['cde_endpoint.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'endpoint_id', 'kind', 'name',
                            name='uq_cde_bi_alert_name'),
    )
    op.create_index('ix_cde_bi_alert_resource', 'cde_bi_alert',
                    ['endpoint_id', 'resource_type', 'resource_id'])
    op.create_table(
        'cde_bi_alert_delegation',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('alert_id', sa.String(length=36), nullable=False),
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
                           name='ck_cde_bi_alert_delegation_state'),
        sa.ForeignKeyConstraint(['alert_id'], ['cde_bi_alert.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['endpoint_id'], ['cde_endpoint.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('alert_id', name='uq_cde_bi_alert_delegation'),
    )
    op.create_table(
        'cde_bi_alert_credential',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('delegation_id', sa.String(length=36), nullable=False),
        sa.Column('secret_kind', sa.String(length=128), nullable=False),
        sa.Column('key_id', sa.String(length=64), nullable=False),
        sa.Column('encrypted_value', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['delegation_id'],
                                ['cde_bi_alert_delegation.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('delegation_id', 'secret_kind',
                            name='uq_cde_bi_alert_secret_kind'),
    )
    op.create_table(
        'cde_bi_alert_occurrence',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('delegation_id', sa.String(length=36), nullable=False),
        sa.Column('scheduled_for', sa.DateTime(), nullable=False),
        sa.Column('state', sa.String(length=32), nullable=False),
        sa.Column('claim_token_digest', sa.String(length=64), nullable=True),
        sa.Column('claimed_by', sa.String(length=128), nullable=True),
        sa.Column('lease_expires_at', sa.DateTime(), nullable=True),
        sa.Column('phase', sa.String(length=32), nullable=False),
        sa.Column('progress', sa.Text(), nullable=False),
        sa.Column('delivery_occurrence_ids', sa.Text(), nullable=True),
        sa.Column('error_type', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint(OCCURRENCE_STATES,
                           name='ck_cde_bi_alert_occurrence_state'),
        sa.ForeignKeyConstraint(['delegation_id'],
                                ['cde_bi_alert_delegation.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('delegation_id', 'scheduled_for',
                            name='uq_cde_bi_alert_instant'),
    )
    op.create_table(
        'cde_bi_alert_event',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('alert_id', sa.String(length=36), nullable=False),
        sa.Column('trigger', sa.String(length=16), nullable=False),
        sa.Column('outcome', sa.String(length=24), nullable=False),
        sa.Column('fired', sa.Boolean(), nullable=False),
        sa.Column('suppressed', sa.String(length=24), nullable=True),
        sa.Column('resource_revision', sa.Integer(), nullable=True),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('deliveries', sa.Text(), nullable=False),
        sa.Column('error_class', sa.String(length=64), nullable=True),
        sa.Column('error_message', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['alert_id'], ['cde_bi_alert.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_cde_bi_alert_event_alert', 'cde_bi_alert_event',
                    ['alert_id', 'created_at'])
    op.create_table(
        'cde_bi_notification',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('endpoint_id', sa.String(length=36), nullable=False),
        sa.Column('alert_id', sa.String(length=36), nullable=True),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('resource_type', sa.String(length=16), nullable=False),
        sa.Column('resource_id', sa.String(length=36), nullable=False),
        sa.Column('title', sa.String(length=256), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('data', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['endpoint_id'], ['cde_endpoint.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['alert_id'], ['cde_bi_alert.id'],
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_cde_bi_notification_user', 'cde_bi_notification',
                    ['user_id', 'endpoint_id', 'read_at'])


def downgrade():
    op.drop_index('ix_cde_bi_notification_user',
                  table_name='cde_bi_notification')
    op.drop_table('cde_bi_notification')
    op.drop_index('ix_cde_bi_alert_event_alert',
                  table_name='cde_bi_alert_event')
    op.drop_table('cde_bi_alert_event')
    op.drop_table('cde_bi_alert_occurrence')
    op.drop_table('cde_bi_alert_credential')
    op.drop_table('cde_bi_alert_delegation')
    op.drop_index('ix_cde_bi_alert_resource', table_name='cde_bi_alert')
    op.drop_table('cde_bi_alert')
