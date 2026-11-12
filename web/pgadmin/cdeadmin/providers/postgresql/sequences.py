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
        # The dialog's shape: true = unlogged (the compiler reads the
        # words too).
        'relpersistence': row.get('relpersistence') == 'u',
        'relacl': list(row.get('relacl') or []),
        'seqowner': native.get('owner'),
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
    # The dialog's table picker sends schema.table; a bare name is a
    # table of the sequence's schema.
    table = _name(table, 'owned table')
    if '.' in table:
        table_schema, _dot, table = table.rpartition('.')
        owner = _qualified(_name(table_schema, 'schema'), table)
    else:
        owner = _qualified(schema, table)
    return [f'ALTER SEQUENCE {qualified} OWNED BY '
            f'{owner}.{_identifier(column, "column")}']


def _persistence(draft):
    """'unlogged' / 'logged', or the dialog's boolean (true = unlogged)."""
    value = draft.get('relpersistence')
    if _blank(value):
        return None
    if isinstance(value, bool):
        return 'unlogged' if value else 'logged'
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
    if persistence is not None and (persistence == 'unlogged') != \
            current['relpersistence']:
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


# The family form's field ids (sequence.form.json) by operation, plus the
# provider's own flags and grids: the validator admits exactly these.
_FAMILY_FIELDS = {
    'create': ('name', 'seqowner', 'schema', 'comment', 'increment', 'start',
               'minimum', 'no_minimum', 'maximum', 'no_maximum', 'cache',
               'cycled', 'relpersistence', 'owned_table', 'owned_column',
               'relacl', 'securities'),
    'alter': ('name', 'oid', 'seqowner', 'schema', 'is_sys_obj', 'comment',
              'current_value', 'increment', 'start', 'minimum', 'no_minimum',
              'maximum', 'no_maximum', 'cache', 'cycled', 'relpersistence',
              'owned_table', 'owned_column', 'owned_by_none', 'acl', 'relacl',
              'securities', 'revoke'),
}
_GRIDS = ('relacl', 'securities', 'revoke')
_BOOLEANS = ('no_minimum', 'no_maximum', 'cycled', 'relpersistence',
             'owned_by_none', 'is_sys_obj')
_NUMBERS = ('increment', 'start', 'minimum', 'maximum', 'cache',
            'current_value')


def form(operation, field):
    """The validator's view of the sequence family form: every field id the
    dialog sends, typed loosely; the family form file carries the labels,
    tabs and grid columns."""
    if operation == 'drop':
        return {'form_id': 'postgresql-sequence-drop',
                'form_key': 'native:postgresql:schema:sequence',
                'title': 'Drop sequence', 'fields': [
                    field('cascade', 'Drop dependent objects', 'boolean'),
                    field('confirmation', 'Type the sequence name to confirm',
                          required=True)]}
    alter = operation == 'alter'
    known = facts({})

    def initial(key):
        return {'initial_value_path': ['sequence_facts', key]} \
            if alter and key in known and key != 'relacl' else {}
    fields = []
    for field_id in _FAMILY_FIELDS[operation]:
        label = field_id.replace('_', ' ').capitalize()
        if field_id in _GRIDS:
            fields.append(field(field_id, label, 'grid', columns=[]))
        elif field_id in _BOOLEANS:
            fields.append(field(field_id, 'Unlogged' if field_id ==
                                'relpersistence' else label, 'boolean',
                                **initial(field_id)))
        elif field_id in _NUMBERS or field_id == 'oid':
            fields.append(field(field_id, label, 'number',
                                **initial(field_id)))
        else:
            fields.append(field(field_id, label,
                                required=field_id in ('name', 'schema')
                                and not alter, **initial(field_id)))
    return {'form_id': f'postgresql-sequence-{operation}',
            'form_key': 'native:postgresql:schema:sequence',
            'title': f'{operation.title()} sequence', 'fields': fields,
            'notes': ('A bound is removed through its No minimum / No '
                      'maximum flag (a cleared number never reaches the '
                      'provider); OWNED BY NONE detaches the sequence; '
                      'privileges are stated and revoked through the Revoke '
                      'grid.')}
