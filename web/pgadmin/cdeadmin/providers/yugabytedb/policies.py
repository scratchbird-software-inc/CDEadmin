"""YugabyteDB YSQL row-level security policies.

Checked live on 2025.2.2.2: CREATE POLICY ... AS PERMISSIVE | RESTRICTIVE
FOR command TO roles (PUBLIC, CURRENT_USER) USING (...) WITH CHECK (...);
ALTER POLICY ... TO / USING / WITH CHECK / RENAME TO; COMMENT ON POLICY
(which CockroachDB refuses); DROP POLICY ... ON table. As in PostgreSQL, AS
and FOR are fixed once created and a clause cannot be removed. The rules
are CockroachDB's (providers/cockroachdb/policies.py), plus comments; the
table's ENABLE / FORCE ROW LEVEL SECURITY are table settings (tables.py).
"""
from ...sdk.relational import RelationalClientError
from ..cockroachdb import policies as shared

CREATE_KEYS = shared.CREATE_KEYS | {'comment'}
ALTER_KEYS = shared.ALTER_KEYS | {'comment'}


def _comment(admin, name, table, value):
    text = 'NULL' if value in (None, '') else admin._literal(str(value))
    return {'source': f'COMMENT ON POLICY {name} ON {table} IS {text}',
            'parameters': ()}


def create(admin, draft):
    unknown = set(draft) - CREATE_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown policy option: ' + ', '.join(sorted(unknown)))
    rest = {key: value for key, value in draft.items() if key != 'comment'}
    statements = shared.create(admin, rest)
    if draft.get('comment') not in (None, ''):
        statements.append(_comment(
            admin, admin._quote(admin._identifier(draft.get('name'))),
            shared._table(admin, rest), draft['comment']))
    return statements


def alter(admin, draft, target):
    native = (target or {}).get('native') or {}
    path = admin._target_path(target)
    rest = {key: value for key, value in draft.items() if key != 'comment'}
    statements = []
    if set(rest) - {'confirmation'}:
        try:
            statements = shared.alter(admin, rest, target,
                                      engine='YugabyteDB')
        except RelationalClientError as error:
            if str(error) != 'nothing to change':
                raise
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        # Before a rename in the same change, the policy has its old name.
        statements.insert(
            len([item for item in statements
                 if ' RENAME TO ' not in item['source']]),
            _comment(admin, admin._quote(path[-1]),
                     admin._qualified(path[:-1]), draft['comment']))
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


def drop(admin, target):
    return shared.drop(admin, target)
