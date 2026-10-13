"""MariaDB receipts share durable ownership/dispatch machinery, not MySQL grammar."""
from .mysql_schema_apply import MySQLSchemaApplications
from .mariadb_schema_plan import schema


class MariaDBSchemaApplications(MySQLSchemaApplications):
    engine = 'mariadb'
    identity_key = 'server_uid'
    intent_key = 'mariadb_change'
    kinds = frozenset({'table'})
    schema = staticmethod(schema)
