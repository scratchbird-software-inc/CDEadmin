"""Whether a YugabyteDB server runs YSQL DDL inside the enclosing transaction.

Checked live on 2025.2.2.2. With the tserver flag
ysql_yb_ddl_transaction_block_enabled off (the default; a server-start
setting a session cannot change), CREATE TABLE / SEQUENCE / ROLE /
EXTENSION and COMMENT survived ROLLBACK and a plan failing at its third
statement kept the first two. With it on, all of those and CREATE INDEX,
ALTER TABLE and COMMENT ON DATABASE rolled back, and the failed plan left
nothing (CREATE DATABASE / TABLESPACE still refuse a transaction block).
ysql_yb_disable_ddl_transaction_block_for_read_committed turns it back
off for READ COMMITTED sessions.

The mode is read with the catalog and remembered per server, so a plan can
say which applies; apply reads it again before running several DDL
statements.
"""
from ..distributed_sql import optional_rows

ATOMIC, PER_STATEMENT, UNKNOWN = 'atomic', 'per-statement', 'unknown'
_QUERY = ("SELECT current_setting('yb_ddl_transaction_block_enabled', "
          "true), current_setting("
          "'yb_disable_ddl_transaction_block_for_read_committed', true), "
          "current_setting('transaction_isolation')")
_DML = ('INSERT', 'UPDATE', 'DELETE', 'SELECT', 'WITH', 'MERGE')
_KNOWN = {}

PER_STATEMENT_WARNING = (
    'This YugabyteDB server runs each DDL statement in its own transaction '
    '(yb_ddl_transaction_block_enabled is off): if a later statement fails, '
    'the earlier ones stay applied.')
UNKNOWN_WARNING = (
    'Unless this YugabyteDB server enables yb_ddl_transaction_block_enabled '
    '(off by default), each DDL statement commits on its own: if a later '
    'statement fails, the earlier ones stay applied. Its setting is read '
    'with the catalog and again when the change is applied.')


def mode(cursor):
    rows = optional_rows(cursor, _QUERY)
    if not rows:
        return UNKNOWN
    enabled, read_committed_off, isolation = rows[0]
    if str(enabled or '').lower() != 'on':
        # Absent (an older release) or off: DDL commits on its own.
        return PER_STATEMENT
    if str(read_committed_off or '').lower() == 'on' and \
            str(isolation or '').lower() == 'read committed':
        return PER_STATEMENT
    return ATOMIC


def _key(route):
    route = route or {}
    return (str(route.get('host') or ''), str(route.get('port') or ''))


def remember(route, value):
    _KNOWN[_key(route)] = value


def known(route):
    return _KNOWN.get(_key(route), UNKNOWN)


def ddl_count(statements):
    return sum(1 for item in statements
               if not str(item.get('source', '')).lstrip().upper()
               .startswith(_DML))


def several_ddl(compiled):
    statements = compiled.get('statements', [])
    return len(statements) > 1 and ddl_count(statements) > 0
