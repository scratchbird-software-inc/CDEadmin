"""PostgreSQL sequence lifecycle on the provider tree (M4, 2026-11-11).

Create, alter and drop compile to exact native statements from the
dialog's draft and the captured catalog facts of the target (``pg_class``
row, ``pg_sequence`` child, comment), the way the other provider-native
PostgreSQL forms do (``native_admin.py``). Field ids follow the inherited
sequence dialog (``sequence.ui.js``) so the form descriptor and this
compiler name the same things.

Several statements may be needed (CREATE, OWNER TO, COMMENT, GRANT ...);
they travel as one text that the provider runs inside its own transaction
on a private attachment, so the change commits or rolls back whole.
"""
from collections.abc import Mapping

from .native_admin import (
    PostgreSQLNativeAdminError, privilege_words,
    _flag, _identifier, _literal, _name,
    _qualified,
)

PRIVILEGE_CODES = {'r': 'SELECT', 'w': 'UPDATE', 'U': 'USAGE'}
_COUNTERS = (('increment', 'INCREMENT BY'), ('start', 'START WITH'),
             ('minimum', 'MINVALUE'), ('maximum', 'MAXVALUE'),
             ('cache', 'CACHE'))
_NATIVE_COUNTERS = {'increment': 'seqincrement', 'start': 'seqstart',
                    'minimum': 'seqmin', 'maximum': 'seqmax',
                    'cache': 'seqcache'}
_INT64 = 2 ** 63


def _blank(value):
    return value is None or value == ''


def _integer(value, label, *, minimum=None):
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int):
        raise PostgreSQLNativeAdminError(f'{label} must be a whole number')
    if not -_INT64 <= value < _INT64:
        raise PostgreSQLNativeAdminError(f'{label} is outside bigint')
    if minimum is not None and value < minimum:
        raise PostgreSQLNativeAdminError(f'{label} is at least {minimum}')
    return value


def facts(native):
    """The target's current values, as the dialog and the compiler see
    them: schema, name, counters, cycle, persistence, comment, owner acl."""
    row = native.get('catalog_row') or {}
    sequence = ((native.get('children') or {}).get('pg_sequence') or [{}])[0]
    result = {
        'schema': native.get('schema'),
        'name': native.get('name') or row.get('relname'),
        'comment': native.get('comment'),
        'cycled': bool(sequence.get('seqcycle', False)),
        'relpersistence': ('unlogged' if row.get('relpersistence') == 'u'
                           else 'logged'),
        'relacl': list(row.get('relacl') or []),
    }
    for key, column in _NATIVE_COUNTERS.items():
        result[key] = sequence.get(column)
    return result


def _grantee(value):
    value = _name(value, 'grantee')
    return 'PUBLIC' if value.upper() == 'PUBLIC' else _identifier(
        value, 'grantee')


def _grant(qualified, row):
    if not isinstance(row, Mapping):
        raise PostgreSQLNativeAdminError('privilege rows must be objects')
    words = privilege_words(row.get('privileges'), PRIVILEGE_CODES,
                            'sequence')
    privileges = 'ALL' if len(words) == len(PRIVILEGE_CODES) else ', '.join(
        words)
    option = ' WITH GRANT OPTION' if _flag(row, 'with_grant') else ''
    return (f'GRANT {privileges} ON SEQUENCE {qualified} TO '
            f'{_grantee(row.get("grantee"))}{option}')


def _revoke(qualified, row):
    if not isinstance(row, Mapping):
        raise PostgreSQLNativeAdminError('revoke rows must be objects')
    return (f'REVOKE ALL ON SEQUENCE {qualified} FROM '
            f'{_grantee(row.get("grantee"))}')


def _security_label(qualified, row):
    if not isinstance(row, Mapping):
        raise PostgreSQLNativeAdminError('security label rows must be objects')
    provider = _identifier(row.get('provider'), 'security label provider')
    label = row.get('label')
    text = 'NULL' if _blank(label) else _literal(str(label), 'security label')
    return f'SECURITY LABEL FOR {provider} ON SEQUENCE {qualified} IS {text}'


def _rows(draft, key, label):
    value = draft.get(key)
    if value in (None, ''):
        return []
    if not isinstance(value, list):
        raise PostgreSQLNativeAdminError(f'{label} must be a list of rows')
    return value


def _owned_by(draft, schema, qualified):
    """OWNED BY clauses: an explicit detach, or a column of the same
    schema (as the inherited dialog restricts it)."""
    if _flag(draft, 'owned_by_none'):
        return [f'ALTER SEQUENCE {qualified} OWNED BY NONE']
    table, column = draft.get('owned_table'), draft.get('owned_column')
    if _blank(table) and _blank(column):
        return []
    if _blank(table) or _blank(column):
        raise PostgreSQLNativeAdminError(
            'owned by needs both the table and the column')
    return [f'ALTER SEQUENCE {qualified} OWNED BY '
            f'{_qualified(schema, table)}.{_identifier(column, "column")}']


def _persistence(draft):
    value = draft.get('relpersistence')
    if _blank(value):
        return None
    if value not in ('logged', 'unlogged'):
        raise PostgreSQLNativeAdminError(
            'persistence is logged or unlogged')
    return value


def _counter_clauses(draft, current):
    clauses = []
    # The dialog drops a cleared number, so the bounds are removed through
    # explicit flags (NO MINVALUE / NO MAXVALUE), never by an absent value.
    unbounded = {key for key in ('minimum', 'maximum')
                 if _flag(draft, 'no_' + key)}
    for key, keyword in _COUNTERS:
        if key in unbounded:
            if current is not None:
                clauses.append('NO ' + keyword)
            continue
        if key not in draft or _blank(draft[key]):
            continue
        value = draft[key]
        value = _integer(value, key, minimum=1 if key == 'cache' else None)
        if key == 'increment' and value == 0:
            raise PostgreSQLNativeAdminError('increment must not be zero')
        if current is not None and current.get(key) == value:
            continue
        clauses.append(f'{keyword} {value}')
    if 'cycled' in draft and draft['cycled'] is not None:
        cycled = _flag(draft, 'cycled')
        if current is None or cycled != current.get('cycled'):
            clauses.append('CYCLE' if cycled else 'NO CYCLE')
    return clauses


def _create(draft):
    schema = _name(draft.get('schema'), 'schema')
    qualified = _qualified(schema, draft.get('name'))
    persistence = _persistence(draft)
    head = 'CREATE UNLOGGED SEQUENCE' if persistence == 'unlogged' else \
        'CREATE SEQUENCE'
    clauses = _counter_clauses(draft, None)
    statements = [' '.join([head, qualified, *clauses])]
    if not _blank(draft.get('seqowner')):
        statements.append(f'ALTER SEQUENCE {qualified} OWNER TO '
                          f'{_identifier(draft["seqowner"], "owner")}')
    statements.extend(_owned_by(draft, schema, qualified))
    if not _blank(draft.get('comment')):
        statements.append(f'COMMENT ON SEQUENCE {qualified} IS '
                          + _literal(str(draft['comment']), 'comment'))
    for row in _rows(draft, 'securities', 'security labels'):
        statements.append(_security_label(qualified, row))
    for row in _rows(draft, 'relacl', 'privileges'):
        statements.append(_grant(qualified, row))
    return statements


def _alter(native, draft):
    current = facts(native)
    schema = _name(current['schema'], 'schema')
    name = _name(current['name'], 'name')
    qualified = _qualified(schema, name)
    statements = []
    new_name = draft.get('name')
    if not _blank(new_name) and new_name != name:
        statements.append(f'ALTER SEQUENCE {qualified} RENAME TO '
                          + _identifier(new_name, 'name'))
        name = new_name
        qualified = _qualified(schema, name)
    if not _blank(draft.get('seqowner')):
        statements.append(f'ALTER SEQUENCE {qualified} OWNER TO '
                          f'{_identifier(draft["seqowner"], "owner")}')
    statements.extend(_owned_by(draft, schema, qualified))
    if not _blank(draft.get('current_value')):
        value = _integer(draft['current_value'], 'current value')
        # As the inherited dialog: the next nextval returns this value. The
        # regclass literal carries the quoted identifiers (live check).
        statements.append(
            f'SELECT pg_catalog.setval({_literal(qualified, "name")}'
            f'::regclass, {value}, false)')
    clauses = _counter_clauses(draft, current)
    if clauses:
        statements.append(f'ALTER SEQUENCE {qualified} ' + ' '.join(clauses))
    persistence = _persistence(draft)
    if persistence is not None and persistence != current['relpersistence']:
        statements.append(f'ALTER SEQUENCE {qualified} SET '
                          + persistence.upper())
    if 'comment' in draft and (draft['comment'] or None) != (
            current['comment'] or None):
        text = 'NULL' if _blank(draft['comment']) else _literal(
            str(draft['comment']), 'comment')
        statements.append(f'COMMENT ON SEQUENCE {qualified} IS {text}')
    for row in _rows(draft, 'securities', 'security labels'):
        statements.append(_security_label(qualified, row))
    for row in _rows(draft, 'revoke', 'revoked grantees'):
        statements.append(_revoke(qualified, row))
    for row in _rows(draft, 'relacl', 'privileges'):
        statements.append(_grant(qualified, row))
    new_schema = draft.get('schema')
    if not _blank(new_schema) and new_schema != schema:
        statements.append(f'ALTER SEQUENCE {qualified} SET SCHEMA '
                          + _identifier(new_schema, 'schema'))
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return statements


def _drop(native, draft):
    current = facts(native)
    name = _name(current['name'], 'name')
    if _name(draft.get('confirmation'), 'confirmation') != name:
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    cascade = ' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT'
    return [f'DROP SEQUENCE {_qualified(current["schema"], name)}{cascade}']


def compile_operation(operation, native, draft):
    """One exact native text for the sequence lifecycle; never partial."""
    if operation == 'create':
        statements = _create(draft)
    elif operation == 'alter':
        statements = _alter(native, draft)
    elif operation == 'drop':
        statements = _drop(native, draft)
    else:
        raise PostgreSQLNativeAdminError(
            'sequence inspection stays with the provider tree')
    return {'statement': ';\n'.join(statements), 'read_only': False}


def form(operation, field):
    """Dialog fields; ids follow the inherited sequence dialog."""
    def number(name, label, **kw):
        return field(name, label, 'number', **kw)

    def grid(name, label, columns, **kw):
        return field(name, label, 'grid', columns=columns, **kw)
    acl_columns = [
        {'field_id': 'grantee', 'label': 'Grantee', 'control': 'text',
         'required': True},
        {'field_id': 'privileges', 'label': 'Privileges (r, w, U)',
         'control': 'text', 'required': True},
        {'field_id': 'with_grant', 'label': 'With grant option',
         'control': 'boolean', 'required': False}]
    label_columns = [
        {'field_id': 'provider', 'label': 'Provider', 'control': 'text',
         'required': True},
        {'field_id': 'label', 'label': 'Security label', 'control': 'text',
         'required': False}]
    if operation == 'drop':
        fields = [field('cascade', 'Drop dependent objects', 'boolean'),
                  field('confirmation', 'Type the sequence name to confirm',
                        required=True)]
    else:
        alter = operation == 'alter'
        fields = [field('name', 'Name', required=not alter),
                  field('schema', 'Schema', required=not alter,
                        help='In alter: a different schema runs SET SCHEMA.'),
                  field('seqowner', 'Owner', help='OWNER TO'),
                  field('comment', 'Comment')]
        if alter:
            fields.append(number('current_value', 'Current value', help=(
                'Sets the value the next nextval returns (setval).')))
        fields += [number('increment', 'Increment'),
                   number('start', 'Start'),
                   number('minimum', 'Minimum'),
                   field('no_minimum', 'No minimum (NO MINVALUE)', 'boolean'),
                   number('maximum', 'Maximum'),
                   field('no_maximum', 'No maximum (NO MAXVALUE)', 'boolean'),
                   number('cache', 'Cache', help='At least 1.'),
                   field('cycled', 'Cycled', 'boolean'),
                   field('relpersistence', 'Persistence', 'select', options=[
                       {'value': 'logged', 'label': 'Logged'},
                       {'value': 'unlogged',
                        'label': 'Unlogged (PostgreSQL 15 and later)'}],
                       **({} if alter else {'default': 'logged'})),
                   field('owned_table', 'Owned by table',
                         help='A table of the same schema (OWNED BY).'),
                   field('owned_column', 'Owned by column'),
                   grid('relacl', 'Grant privileges', acl_columns,
                        help='Rows run GRANT; existing grants stay.'),
                   grid('securities', 'Security labels', label_columns,
                        help='Empty label unsets the provider\'s label.')]
        if alter:
            fields.insert(fields.index(next(
                f for f in fields if f['field_id'] == 'relacl')),
                field('owned_by_none', 'Detach from its column (OWNED BY '
                      'NONE)', 'boolean'))
            fields.append(grid('revoke', 'Revoke all privileges from',
                               [acl_columns[0]]))
            for item in fields:
                if item['field_id'] in facts({}) and item['field_id'] not \
                        in {'relacl', 'relpersistence'}:
                    item['initial_value_path'] = [
                        'sequence_facts', item['field_id']]
    return {'form_id': f'postgresql-sequence-{operation}',
            'form_key': 'native:postgresql:schema:sequence',
            'title': f'{operation.title()} sequence', 'fields': fields}
