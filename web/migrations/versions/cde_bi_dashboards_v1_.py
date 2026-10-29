##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Add BI dashboards and their immutable revisions.

Revision ID: cde_bi_dashboards_v1
Revises: cde_bi_saved_questions_v1
Create Date: 2026-10-28
"""

from alembic import op
import sqlalchemy as sa


revision = 'cde_bi_dashboards_v1'
down_revision = 'cde_bi_saved_questions_v1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cde_bi_dashboard',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('endpoint_id', sa.String(length=36), nullable=False),
        sa.Column('collection_id', sa.String(length=36), nullable=True),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('definition', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'archived')",
            name='ck_cde_bi_dashboard_status',
        ),
        sa.ForeignKeyConstraint(['endpoint_id'], ['cde_endpoint.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['collection_id'], ['cde_bi_collection.id'],
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_cde_bi_dashboard_scope', 'cde_bi_dashboard',
                    ['user_id', 'endpoint_id', 'collection_id'])
    op.create_table(
        'cde_bi_dashboard_revision',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('dashboard_id', sa.String(length=36), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('definition', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['dashboard_id'], ['cde_bi_dashboard.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('dashboard_id', 'revision',
                            name='uq_cde_bi_dashboard_revision'),
    )


def downgrade():
    op.drop_table('cde_bi_dashboard_revision')
    op.drop_index('ix_cde_bi_dashboard_scope', table_name='cde_bi_dashboard')
    op.drop_table('cde_bi_dashboard')
