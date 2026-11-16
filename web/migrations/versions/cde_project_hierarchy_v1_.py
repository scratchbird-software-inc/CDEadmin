##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2026, The ScratchBird Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Add hierarchical parent_project_id relationship to cde_project.

Allows a project to be the parent or child of another project while service
validation enforces strict DAG acyclicity (no self-parenting or circular
dependency loops). Bumps SCHEMA_VERSION to 61.

Revision ID: cde_project_hierarchy_v1
Revises: cde_user_preference_text_v1
Create Date: 2026-11-15
"""

from alembic import op
import sqlalchemy as sa


revision = 'cde_project_hierarchy_v1'
down_revision = 'cde_user_preference_text_v1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('cde_project') as batch_op:
        batch_op.add_column(
            sa.Column('parent_project_id', sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            'fk_cde_project_parent_id',
            'cde_project',
            ['parent_project_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_index(
            'ix_cde_project_parent', ['parent_project_id']
        )


def downgrade():
    with op.batch_alter_table('cde_project') as batch_op:
        batch_op.drop_index('ix_cde_project_parent')
        batch_op.drop_constraint(
            'fk_cde_project_parent_id', type_='foreignkey'
        )
        batch_op.drop_column('parent_project_id')
