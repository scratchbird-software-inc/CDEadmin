##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2026, The ScratchBird Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Store preference values as unbounded text.

``user_preferences.value`` was ``VARCHAR(1024)``. Validated JSON preference
documents (named appearance presets, the tabbed command bar customization,
icon/menu/command customization) outgrow that within their own limits; a
PostgreSQL configuration database refused them, while SQLite, which does not
enforce the length, kept them. Owner direction 2026-11-05: widen the column
and bump SCHEMA_VERSION to 60 so existing installations apply it.

Downgrade narrows the column again. On PostgreSQL it fails, rather than
truncating, while any value is longer than 1024 characters.

Revision ID: cde_user_preference_text_v1
Revises: cde_bi_embeds_v1
Create Date: 2026-11-05
"""

from alembic import op
import sqlalchemy as sa


revision = 'cde_user_preference_text_v1'
down_revision = 'cde_bi_embeds_v1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user_preferences') as batch_op:
        batch_op.alter_column('value',
                              existing_type=sa.String(length=1024),
                              type_=sa.Text(),
                              existing_nullable=False)


def downgrade():
    with op.batch_alter_table('user_preferences') as batch_op:
        batch_op.alter_column('value',
                              existing_type=sa.Text(),
                              type_=sa.String(length=1024),
                              existing_nullable=False)
