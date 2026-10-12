"""Independent Firebird registration aliases and protected credentials."""

from alembic import op
import sqlalchemy as sa

revision = 'cde_registration_aliases_v1'
down_revision = 'cde_project_assets_v1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('cde_endpoint_database_target') as batch:
        batch.drop_constraint('uq_cde_endpoint_database_target', type_='unique')
        batch.add_column(sa.Column('registration_user', sa.String(255)))
        batch.add_column(sa.Column('registration_password', sa.String()))
        batch.add_column(sa.Column('registration_credentials', sa.Boolean(),
                                   nullable=False, server_default=sa.false()))


def downgrade():
    # Refuse before discarding credential scopes or coalescing distinct IDs.
    connection = op.get_bind()
    targets = sa.table('cde_endpoint_database_target',
                       sa.column('endpoint_id'), sa.column('database'),
                       sa.column('registration_credentials'))
    if connection.execute(sa.select(targets.c.endpoint_id).where(
            targets.c.registration_credentials == sa.true()).limit(1)).first():
        raise RuntimeError('Registration credentials must be removed before downgrade')
    if connection.execute(sa.select(targets.c.endpoint_id).group_by(
            targets.c.endpoint_id, targets.c.database).having(
            sa.func.count() > 1).limit(1)).first():
        raise RuntimeError('Registration aliases must be resolved before downgrade')
    with op.batch_alter_table('cde_endpoint_database_target') as batch:
        batch.drop_column('registration_password')
        batch.drop_column('registration_user')
        batch.drop_column('registration_credentials')
        batch.create_unique_constraint('uq_cde_endpoint_database_target',
                                       ['endpoint_id', 'database'])
