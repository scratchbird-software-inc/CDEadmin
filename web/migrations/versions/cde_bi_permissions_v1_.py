##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Add BI sharing: grants, inheritance overrides, audit, revision actor.

Additive only; SCHEMA_VERSION is deliberately not bumped (owner-confirmed
convention for the BI tables).

Revision ID: cde_bi_permissions_v1
Revises: cde_bi_dashboards_v1
Create Date: 2026-10-28
"""

from alembic import op
import sqlalchemy as sa


revision = 'cde_bi_permissions_v1'
down_revision = 'cde_bi_dashboards_v1'
branch_labels = None
depends_on = None

RESOURCES = "resource_type IN ('collection', 'question', 'dashboard')"


def upgrade():
    op.create_table(
        'cde_bi_grant',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('endpoint_id', sa.String(length=36), nullable=False),
        sa.Column('resource_type', sa.String(length=16), nullable=False),
        sa.Column('resource_id', sa.String(length=36), nullable=False),
        sa.Column('principal_user_id', sa.Integer(), nullable=True),
        sa.Column('principal_role_id', sa.Integer(), nullable=True),
        sa.Column('level', sa.String(length=16), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(RESOURCES, name='ck_cde_bi_grant_resource'),
        sa.CheckConstraint("level IN ('view', 'edit', 'manage')",
                           name='ck_cde_bi_grant_level'),
        sa.CheckConstraint(
            '(principal_user_id IS NOT NULL AND principal_role_id IS NULL)'
            ' OR (principal_user_id IS NULL AND '
            'principal_role_id IS NOT NULL)',
            name='ck_cde_bi_grant_principal'),
        sa.ForeignKeyConstraint(['endpoint_id'], ['cde_endpoint.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['principal_user_id'], ['user.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['principal_role_id'], ['role.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['user.id'],
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('endpoint_id', 'resource_type', 'resource_id',
                            'principal_user_id',
                            name='uq_cde_bi_grant_user'),
        sa.UniqueConstraint('endpoint_id', 'resource_type', 'resource_id',
                            'principal_role_id',
                            name='uq_cde_bi_grant_role'),
    )
    op.create_index('ix_cde_bi_grant_resource', 'cde_bi_grant',
                    ['endpoint_id', 'resource_type', 'resource_id'])
    op.create_table(
        'cde_bi_access_override',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('endpoint_id', sa.String(length=36), nullable=False),
        sa.Column('resource_type', sa.String(length=16), nullable=False),
        sa.Column('resource_id', sa.String(length=36), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(RESOURCES,
                           name='ck_cde_bi_access_override_resource'),
        sa.ForeignKeyConstraint(['endpoint_id'], ['cde_endpoint.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['user.id'],
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('endpoint_id', 'resource_type', 'resource_id',
                            name='uq_cde_bi_access_override'),
    )
    op.create_table(
        'cde_bi_audit',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=48), nullable=False),
        sa.Column('endpoint_id', sa.String(length=36), nullable=True),
        sa.Column('resource_type', sa.String(length=16), nullable=False),
        sa.Column('resource_id', sa.String(length=36), nullable=False),
        sa.Column('target_type', sa.String(length=16), nullable=True),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('detail', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['actor_user_id'], ['user.id'],
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_cde_bi_audit_resource', 'cde_bi_audit',
                    ['resource_type', 'resource_id'])
    for table in ('cde_bi_saved_question_revision',
                  'cde_bi_dashboard_revision'):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column('actor_user_id', sa.Integer(),
                                       nullable=True))
            batch.create_foreign_key(
                'fk_' + table + '_actor', 'user', ['actor_user_id'], ['id'],
                ondelete='SET NULL')


def downgrade():
    for table in ('cde_bi_dashboard_revision',
                  'cde_bi_saved_question_revision'):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint('fk_' + table + '_actor',
                                  type_='foreignkey')
            batch.drop_column('actor_user_id')
    op.drop_index('ix_cde_bi_audit_resource', table_name='cde_bi_audit')
    op.drop_table('cde_bi_audit')
    op.drop_table('cde_bi_access_override')
    op.drop_index('ix_cde_bi_grant_resource', table_name='cde_bi_grant')
    op.drop_table('cde_bi_grant')
