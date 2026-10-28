##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Add BI collections and immutable saved-question revisions.

Revision ID: cde_bi_saved_questions_v1
Revises: cde_registration_aliases_v1
Create Date: 2026-10-28
"""

from alembic import op
import sqlalchemy as sa


revision = 'cde_bi_saved_questions_v1'
down_revision = 'cde_registration_aliases_v1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cde_bi_collection',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('parent_id', sa.String(length=36), nullable=True),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_id'], ['cde_bi_collection.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_cde_bi_collection_parent', 'cde_bi_collection',
                    ['user_id', 'parent_id'])
    op.create_table(
        'cde_bi_saved_question',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('endpoint_id', sa.String(length=36), nullable=False),
        sa.Column('collection_id', sa.String(length=36), nullable=True),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('semantic_model_id', sa.String(length=36), nullable=True),
        sa.Column('semantic_model_revision', sa.Integer(), nullable=True),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('definition', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'archived')",
            name='ck_cde_bi_saved_question_status',
        ),
        sa.ForeignKeyConstraint(['endpoint_id'], ['cde_endpoint.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['collection_id'], ['cde_bi_collection.id'],
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_cde_bi_saved_question_scope', 'cde_bi_saved_question',
                    ['user_id', 'endpoint_id', 'collection_id'])
    op.create_table(
        'cde_bi_saved_question_revision',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('question_id', sa.String(length=36), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('definition', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['question_id'], ['cde_bi_saved_question.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('question_id', 'revision',
                            name='uq_cde_bi_question_revision'),
    )


def downgrade():
    op.drop_table('cde_bi_saved_question_revision')
    op.drop_index('ix_cde_bi_saved_question_scope',
                  table_name='cde_bi_saved_question')
    op.drop_table('cde_bi_saved_question')
    op.drop_index('ix_cde_bi_collection_parent',
                  table_name='cde_bi_collection')
    op.drop_table('cde_bi_collection')
