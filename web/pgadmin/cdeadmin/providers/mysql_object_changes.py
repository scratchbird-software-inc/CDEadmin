"""Native MySQL routine characteristics and secondary-index changes."""
from ..sdk.relational import RelationalClientError
from .mysql_tablespaces import identifier

OPERATIONS = {
    'procedure': frozenset({'alter'}),
    'function': frozenset({'alter'}),
    'index': frozenset({'rename', 'visibility'}),
}
TITLES = {'rename': 'Rename index', 'visibility': 'Change index visibility', 'alter': 'Alter routine'}
DATA_ACCESS = ('UNCHANGED', 'CONTAINS SQL', 'NO SQL', 'READS SQL DATA',
               'MODIFIES SQL DATA')
SECURITY = ('UNCHANGED', 'DEFINER', 'INVOKER')


def compile_operation(kind, operation, draft, target):
    if operation not in OPERATIONS.get(kind, ()) or not isinstance(draft, dict):
        raise RelationalClientError('Native object change is unavailable')
    path = (target or {}).get('display_path', [])
    if not isinstance(path, list) or len(path) != (3 if kind == 'index' else 2):
        raise RelationalClientError('Exact native owning object identity is required')
    qualified = '.'.join(identifier(name) for name in path[:2])
    allowed = {'confirmation'} | ({'new_name'} if operation == 'rename' else
                                  {'visibility'} if kind == 'index' else
                                  {'comment', 'sql_security', 'data_access'})
    if set(draft) - allowed:
        raise RelationalClientError('Unknown native object change option')
    if kind == 'index':
        if path[2].upper() == 'PRIMARY':
            raise RelationalClientError('A native primary key cannot be renamed or made invisible')
        source = 'ALTER TABLE ' + qualified + ' '
        if operation == 'rename':
            source += 'RENAME INDEX ' + identifier(path[2]) + ' TO ' + identifier(draft.get('new_name'))
        else:
            visibility = draft.get('visibility')
            if visibility not in {'VISIBLE', 'INVISIBLE'}:
                raise RelationalClientError('Select native VISIBLE or INVISIBLE')
            source += 'ALTER INDEX ' + identifier(path[2]) + ' ' + visibility
        return {'source': source, 'parameters': ()}
    clauses, parameters = [], []
    for key, choices, prefix in (
            ('sql_security', SECURITY, 'SQL SECURITY '),
            ('data_access', DATA_ACCESS, '')):
        value = draft.get(key, 'UNCHANGED')
        if value not in choices:
            raise RelationalClientError('Select a native routine characteristic')
        if value != 'UNCHANGED':
            clauses.append(prefix + value)
    if 'comment' in draft:
        comment = draft['comment']
        if not isinstance(comment, str) or not comment or '\x00' in comment or len(comment.encode('utf8')) > 65535:
            raise RelationalClientError('Routine comment requires nonempty bounded text; native MySQL 9.7 ignores an empty ALTER comment')
        clauses.append('COMMENT %s')
        parameters.append(comment)
    if not clauses:
        raise RelationalClientError('Select at least one native routine characteristic')
    source = 'ALTER ' + kind.upper() + ' ' + qualified + ' ' + ' '.join(clauses)
    return {'source': source, 'preview_source': source.replace('%s', '<bound-comment>'),
            'parameters': tuple(parameters)}
