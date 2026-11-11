"""PostgreSQL triggers, event triggers and rules on the provider tree
(M4, 2026-11-11).

Triggers: CREATE [OR REPLACE] [CONSTRAINT] TRIGGER with timing, events
(UPDATE OF columns), FOR EACH ROW | STATEMENT, WHEN, deferrability,
transition tables (REFERENCING), the function and its arguments, comment;
ALTER TRIGGER RENAME TO, ALTER TABLE ENABLE | DISABLE | ENABLE REPLICA |
ENABLE ALWAYS TRIGGER, COMMENT; a changed definition runs CREATE OR
REPLACE TRIGGER (constraint triggers are dropped and created, as PostgreSQL
has no OR REPLACE for them). Event triggers: CREATE EVENT TRIGGER ON event
WHEN TAG IN (...) EXECUTE FUNCTION, owner, comment, enable state, rename;
a changed event, tags or function is drop and create, as the inherited
dialog does. Rules: CREATE [OR REPLACE] RULE AS ON event TO table [WHERE]
DO [INSTEAD] NOTHING | (commands), rename, ALTER TABLE ENABLE | DISABLE
RULE, comment. Transition tables and constraint triggers, which YugabyteDB
refuses, are offered here. Field ids follow the inherited dialogs.

The alter dialogs' initial values come from ``pg_get_triggerdef`` and
``pg_get_ruledef`` read back through PostgreSQL's own parser.
"""
from .native_admin import (
    PostgreSQLNativeAdminError, _flag, _identifier, _literal, _name,
    _qualified, _reference,
)
from .policies import expression

FIRES = ('BEFORE', 'AFTER', 'INSTEAD OF')
_TIMING = {0: 'AFTER', 2: 'BEFORE', 64: 'INSTEAD OF'}
_EVENT_BITS = (('evnt_insert', 4, 'INSERT'), ('evnt_delete', 8, 'DELETE'),
               ('evnt_update', 16, 'UPDATE'),
               ('evnt_truncate', 32, 'TRUNCATE'))
ENABLE_STATES = {'O': 'ENABLE', 'D': 'DISABLE', 'R': 'ENABLE REPLICA',
                 'A': 'ENABLE ALWAYS'}
RULE_EVENTS = {1: 'SELECT', 2: 'UPDATE', 3: 'INSERT', 4: 'DELETE'}
EVENT_TRIGGER_EVENTS = ('ddl_command_start', 'ddl_command_end',
                        'table_rewrite', 'sql_drop', 'login')
_DEFINITION_KEYS = ('fires', 'evnt_insert', 'evnt_update', 'evnt_delete',
                    'evnt_truncate', 'columns', 'is_row_trigger',
                    'is_constraint_trigger', 'tgdeferrable',
                    'tginitdeferred', 'tgoldtable', 'tgnewtable',
                    'whenclause', 'tfunction', 'tgargs')


def _blank(value):
    return value is None or value == '' or value == []


def _render(node):
    from pglast.stream import RawStream
    return RawStream()(node)


# -- facts --------------------------------------------------------------------

def trigger_facts(native):
    row = native.get('catalog_row') or {}
    result = {'name': native.get('name') or row.get('tgname'),
              'schema': native.get('schema'), 'table': None,
              'fires': 'AFTER', 'evnt_insert': False, 'evnt_update': False,
              'evnt_delete': False, 'evnt_truncate': False, 'columns': [],
              'is_row_trigger': True, 'is_constraint_trigger': False,
              'tgdeferrable': False, 'tginitdeferred': False,
              'tgoldtable': None, 'tgnewtable': None, 'whenclause': None,
              'tfunction': None, 'tgargs': '',
              'is_enable_trigger': row.get('tgenabled', 'O'),
              'is_internal': bool(row.get('tgisinternal', False)),
              'description': native.get('comment'),
              'definition_parsed': False}
    definition = native.get('definition')
    if not isinstance(definition, str) or not definition.strip():
        return result
    try:
        from pglast import parse_sql
        statement = parse_sql(definition)[0].stmt
        result.update({
            'table': statement.relation.relname,
            'schema': statement.relation.schemaname or result['schema'],
            'fires': _TIMING.get(int(statement.timing or 0), 'AFTER'),
            'columns': [item.sval for item in statement.columns or []],
            'is_row_trigger': bool(statement.row),
            'is_constraint_trigger': bool(statement.isconstraint),
            'tgdeferrable': bool(statement.deferrable),
            'tginitdeferred': bool(statement.initdeferred),
            'whenclause': _render(statement.whenClause)
            if statement.whenClause is not None else None,
            'tfunction': '.'.join(_identifier(item.sval, 'function')
                                  for item in statement.funcname),
            'tgargs': ', '.join(item.sval for item in statement.args or [])})
        for key, bit, _ in _EVENT_BITS:
            result[key] = bool(int(statement.events or 0) & bit)
        for item in statement.transitionRels or []:
            result['tgnewtable' if item.isNew else 'tgoldtable'] = item.name
        result['definition_parsed'] = True
    except Exception:
        return result
    return result


def rule_facts(native):
    row = native.get('catalog_row') or {}
    result = {'name': native.get('name') or row.get('rulename'),
              'schema': native.get('schema'), 'view': None,
              'event': 'SELECT', 'do_instead': bool(row.get('is_instead')),
              'condition': None, 'statements': 'NOTHING',
              'is_enable_rule': row.get('ev_enabled', 'O'),
              'comment': native.get('comment'), 'definition_parsed': False}
    definition = native.get('definition')
    if not isinstance(definition, str) or not definition.strip():
        return result
    try:
        from pglast import parse_sql
        statement = parse_sql(definition)[0].stmt
        actions = [_render(item) for item in statement.actions or []]
        result.update({
            'view': statement.relation.relname,
            'schema': statement.relation.schemaname or result['schema'],
            'event': RULE_EVENTS.get(int(getattr(statement.event, 'value',
                                                statement.event)), 'SELECT'),
            'do_instead': bool(statement.instead),
            'condition': _render(statement.whereClause)
            if statement.whereClause is not None else None,
            'statements': ';\n'.join(actions) if actions else 'NOTHING'})
        result['definition_parsed'] = True
    except Exception:
        return result
    return result


def event_trigger_facts(native):
    row = native.get('catalog_row') or {}
    return {'name': native.get('name') or row.get('evtname'),
            'eventname': row.get('evtevent'),
            'when': ', '.join(row.get('evttags') or []),
            'eventfunname': None,
            'enabled': row.get('evtenabled', 'O'),
            'comment': native.get('comment')}


# -- triggers -----------------------------------------------------------------

def _events(draft, current):
    parts = []
    for key, _, keyword in _EVENT_BITS:
        value = draft.get(key)
        if value is None and current is not None:
            value = current[key]
        if value is not None and _flag({key: value}, key):
            if keyword == 'UPDATE':
                columns = draft.get('columns')
                if columns is None and current is not None:
                    columns = current['columns']
                if isinstance(columns, str):
                    columns = [item.strip() for item in columns.split(',')
                               if item.strip()]
                if columns:
                    keyword += ' OF ' + ', '.join(
                        _identifier(item.get('column') if isinstance(
                            item, dict) else item, 'column')
                        for item in columns)
            parts.append(keyword)
    if not parts:
        raise PostgreSQLNativeAdminError('a trigger needs at least one event')
    return ' OR '.join(parts)


def _value(draft, current, key, default=None):
    value = draft.get(key)
    if value is None and current is not None:
        return current.get(key)
    return default if value is None else value


def _trigger_definition(draft, current, replace):
    schema = _name(_value(draft, current, 'schema'), 'schema')
    table = _qualified(schema, _value(draft, current, 'table'))
    name = _identifier(_value(draft, current, 'name'), 'name')
    constraint = bool(_value(draft, current, 'is_constraint_trigger', False))
    fires = str(_value(draft, current, 'fires', 'AFTER') or 'AFTER').upper()
    if fires not in FIRES:
        raise PostgreSQLNativeAdminError('fires is ' + ', '.join(FIRES))
    head = 'CREATE ' + ('OR REPLACE ' if replace and not constraint else '')
    head += ('CONSTRAINT ' if constraint else '') + f'TRIGGER {name}'
    text = f'{head} {fires} {_events(draft, current)} ON {table}'
    if constraint:
        if _value(draft, current, 'tgdeferrable', False):
            text += ' DEFERRABLE'
            if _value(draft, current, 'tginitdeferred', False):
                text += ' INITIALLY DEFERRED'
    old, new = _value(draft, current, 'tgoldtable'), _value(
        draft, current, 'tgnewtable')
    if not _blank(old) or not _blank(new):
        text += ' REFERENCING'
        if not _blank(new):
            text += ' NEW TABLE AS ' + _identifier(new, 'new table')
        if not _blank(old):
            text += ' OLD TABLE AS ' + _identifier(old, 'old table')
    row = _value(draft, current, 'is_row_trigger', True)
    text += ' FOR EACH ' + ('ROW' if row else 'STATEMENT')
    when = _value(draft, current, 'whenclause')
    if not _blank(when):
        text += ' WHEN (' + expression(when, 'WHEN') + ')'
    function = _value(draft, current, 'tfunction')
    text += ' EXECUTE FUNCTION ' + _reference(function, 'trigger function')
    arguments = _value(draft, current, 'tgargs', '')
    if isinstance(arguments, list):
        values = [str(item) for item in arguments]
    else:
        values = [item.strip() for item in str(arguments or '').split(',')
                  if item.strip()]
    text += '(' + ', '.join(_literal(item.strip("'"), 'argument')
                            for item in values) + ')'
    return text, name, table


def _trigger_create(draft):
    text, name, table = _trigger_definition(draft, None, False)
    statements = [text]
    if not _blank(draft.get('description')):
        statements.append(f'COMMENT ON TRIGGER {name} ON {table} IS '
                          + _literal(str(draft['description']), 'comment'))
    return statements


def _trigger_alter(native, draft):
    current = native.get('trigger_facts') or trigger_facts(native)
    if current.get('is_internal'):
        raise PostgreSQLNativeAdminError(
            'an internal trigger belongs to its constraint')
    schema = _name(current['schema'], 'schema')
    table = _qualified(schema, _name(current['table'], 'table'))
    name = _name(current['name'], 'name')
    statements = []
    changed = [key for key in _DEFINITION_KEYS
               if draft.get(key) is not None and draft[key] != current[key]]
    if changed:
        if not current['definition_parsed']:
            raise PostgreSQLNativeAdminError(
                'the current definition could not be read back; edit it '
                'from the inherited dialog')
        if current['is_constraint_trigger'] or draft.get(
                'is_constraint_trigger'):
            statements.append(f'DROP TRIGGER {_identifier(name, "name")} ON '
                              f'{table}')
            text, _, _ = _trigger_definition(
                {**draft, 'name': name}, current, False)
        else:
            text, _, _ = _trigger_definition(
                {**draft, 'name': name}, current, True)
        statements.append(text)
    state = draft.get('is_enable_trigger')
    if not _blank(state) and state != current['is_enable_trigger']:
        if state not in ENABLE_STATES:
            raise PostgreSQLNativeAdminError(
                'enable state is O, D, R or A')
        statements.append(f'ALTER TABLE {table} {ENABLE_STATES[state]} '
                          f'TRIGGER {_identifier(name, "name")}')
    if 'description' in draft and (draft['description'] or None) != (
            current['description'] or None):
        text = 'NULL' if _blank(draft['description']) else _literal(
            str(draft['description']), 'comment')
        statements.append(f'COMMENT ON TRIGGER {_identifier(name, "name")} '
                          f'ON {table} IS {text}')
    new_name = draft.get('name')
    if not _blank(new_name) and new_name != name:
        statements.append(f'ALTER TRIGGER {_identifier(name, "name")} ON '
                          f'{table} RENAME TO {_identifier(new_name, "name")}')
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return statements


def _trigger_drop(native, draft):
    current = native.get('trigger_facts') or trigger_facts(native)
    name = _name(current['name'], 'name')
    if _name(draft.get('confirmation'), 'confirmation') != name:
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    table = _qualified(current['schema'], _name(current['table'], 'table'))
    cascade = ' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT'
    return [f'DROP TRIGGER {_identifier(name, "name")} ON {table}{cascade}']


# -- event triggers -----------------------------------------------------------

def _tags(value):
    if _blank(value):
        return []
    if isinstance(value, str):
        value = [item.strip() for item in value.split(',') if item.strip()]
    if not isinstance(value, list):
        raise PostgreSQLNativeAdminError('tags are a list of command tags')
    return [_literal(str(item).strip("'"), 'tag') for item in value]


def _event_trigger_definition(draft, current):
    name = _identifier(_value(draft, current, 'name'), 'name')
    event = _value(draft, current, 'eventname')
    if event not in EVENT_TRIGGER_EVENTS:
        raise PostgreSQLNativeAdminError(
            'event is ' + ', '.join(EVENT_TRIGGER_EVENTS))
    text = f'CREATE EVENT TRIGGER {name} ON {event}'
    tags = _tags(_value(draft, current, 'when'))
    if tags:
        text += ' WHEN TAG IN (' + ', '.join(tags) + ')'
    function = _value(draft, current, 'eventfunname')
    if _blank(function):
        raise PostgreSQLNativeAdminError(
            'the trigger function is required (the capture does not name '
            'the current one)')
    return text + ' EXECUTE FUNCTION ' + _reference(
        function, 'trigger function') + '()', name


def _event_trigger_create(draft):
    text, name = _event_trigger_definition(draft, None)
    statements = [text]
    if not _blank(draft.get('eventowner')):
        statements.append(f'ALTER EVENT TRIGGER {name} OWNER TO '
                          + _identifier(draft['eventowner'], 'owner'))
    if not _blank(draft.get('comment')):
        statements.append(f'COMMENT ON EVENT TRIGGER {name} IS '
                          + _literal(str(draft['comment']), 'comment'))
    return statements


def _event_trigger_alter(native, draft):
    current = native.get('event_trigger_facts') or event_trigger_facts(
        native)
    name = _name(current['name'], 'name')
    quoted = _identifier(name, 'name')
    statements = []
    changed = any(draft.get(key) is not None and draft[key] != current[key]
                  for key in ('eventname', 'when'))
    if changed or not _blank(draft.get('eventfunname')):
        # As the inherited dialog: event, tags and function change by drop
        # and create (there is no ALTER for them).
        statements.append(f'DROP EVENT TRIGGER {quoted}')
        text, _ = _event_trigger_definition({**draft, 'name': name}, current)
        statements.append(text)
    if not _blank(draft.get('eventowner')):
        statements.append(f'ALTER EVENT TRIGGER {quoted} OWNER TO '
                          + _identifier(draft['eventowner'], 'owner'))
    state = draft.get('enabled')
    if not _blank(state) and (state != current['enabled'] or changed):
        if state not in ENABLE_STATES:
            raise PostgreSQLNativeAdminError(
                'enable state is O, D, R or A')
        statements.append(f'ALTER EVENT TRIGGER {quoted} '
                          + ENABLE_STATES[state])
    if 'comment' in draft and (draft['comment'] or None) != (
            current['comment'] or None):
        text = 'NULL' if _blank(draft['comment']) else _literal(
            str(draft['comment']), 'comment')
        statements.append(f'COMMENT ON EVENT TRIGGER {quoted} IS {text}')
    new_name = draft.get('name')
    if not _blank(new_name) and new_name != name:
        statements.append(f'ALTER EVENT TRIGGER {quoted} RENAME TO '
                          + _identifier(new_name, 'name'))
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return statements


def _event_trigger_drop(native, draft):
    current = native.get('event_trigger_facts') or event_trigger_facts(
        native)
    name = _name(current['name'], 'name')
    if _name(draft.get('confirmation'), 'confirmation') != name:
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    cascade = ' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT'
    return [f'DROP EVENT TRIGGER {_identifier(name, "name")}{cascade}']


# -- rules --------------------------------------------------------------------

def _commands(value):
    text = (value or '').strip()
    if not text or text.upper().rstrip(';') == 'NOTHING':
        return 'NOTHING'
    if '--' in text or '/*' in text or '\x00' in text:
        raise PostgreSQLNativeAdminError('commands contain unsafe syntax')
    from pglast import ast, parse_sql
    from pglast.parser import ParseError
    try:
        statements = parse_sql(text)
    except ParseError as exc:
        raise PostgreSQLNativeAdminError(
            f'commands are not valid SQL: {exc}') from None
    allowed = (ast.SelectStmt, ast.InsertStmt, ast.UpdateStmt,
               ast.DeleteStmt, ast.NotifyStmt)
    if not statements or any(not isinstance(item.stmt, allowed)
                             for item in statements):
        raise PostgreSQLNativeAdminError(
            'rule commands are SELECT, INSERT, UPDATE, DELETE or NOTIFY')
    return '(' + '; '.join(_render(item.stmt) for item in statements) + ')'


def _rule_definition(draft, current, replace):
    schema = _name(_value(draft, current, 'schema'), 'schema')
    table = _qualified(schema, _value(draft, current, 'view'))
    name = _identifier(_value(draft, current, 'name'), 'name')
    event = str(_value(draft, current, 'event', 'SELECT') or 'SELECT').upper()
    if event not in RULE_EVENTS.values():
        raise PostgreSQLNativeAdminError(
            'event is ' + ', '.join(RULE_EVENTS.values()))
    text = ('CREATE OR REPLACE RULE ' if replace else 'CREATE RULE ') + \
        f'{name} AS ON {event} TO {table}'
    condition = _value(draft, current, 'condition')
    if not _blank(condition):
        text += ' WHERE (' + expression(condition, 'condition') + ')'
    text += ' DO' + (' INSTEAD' if _value(draft, current, 'do_instead',
                                         False) else ' ALSO')
    return text + ' ' + _commands(_value(draft, current, 'statements')), \
        name, table


def _rule_create(draft):
    text, name, table = _rule_definition(draft, None, False)
    statements = [text]
    if not _blank(draft.get('comment')):
        statements.append(f'COMMENT ON RULE {name} ON {table} IS '
                          + _literal(str(draft['comment']), 'comment'))
    return statements


def _rule_alter(native, draft):
    current = native.get('rule_facts') or rule_facts(native)
    schema = _name(current['schema'], 'schema')
    table = _qualified(schema, _name(current['view'], 'view'))
    name = _name(current['name'], 'name')
    quoted = _identifier(name, 'name')
    statements = []
    changed = [key for key in ('event', 'do_instead', 'condition',
                               'statements')
               if draft.get(key) is not None and draft[key] != current[key]]
    if changed:
        if not current['definition_parsed']:
            raise PostgreSQLNativeAdminError(
                'the current definition could not be read back; edit it '
                'from the inherited dialog')
        text, _, _ = _rule_definition({**draft, 'name': name}, current, True)
        statements.append(text)
    state = draft.get('is_enable_rule')
    if not _blank(state) and state != current['is_enable_rule']:
        if state not in ENABLE_STATES:
            raise PostgreSQLNativeAdminError(
                'enable state is O, D, R or A')
        statements.append(f'ALTER TABLE {table} {ENABLE_STATES[state]} '
                          f'RULE {quoted}')
    if 'comment' in draft and (draft['comment'] or None) != (
            current['comment'] or None):
        text = 'NULL' if _blank(draft['comment']) else _literal(
            str(draft['comment']), 'comment')
        statements.append(f'COMMENT ON RULE {quoted} ON {table} IS {text}')
    new_name = draft.get('name')
    if not _blank(new_name) and new_name != name:
        statements.append(f'ALTER RULE {quoted} ON {table} RENAME TO '
                          + _identifier(new_name, 'name'))
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return statements


def _rule_drop(native, draft):
    current = native.get('rule_facts') or rule_facts(native)
    name = _name(current['name'], 'name')
    if _name(draft.get('confirmation'), 'confirmation') != name:
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    table = _qualified(current['schema'], _name(current['view'], 'view'))
    cascade = ' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT'
    return [f'DROP RULE {_identifier(name, "name")} ON {table}{cascade}']


# -- dispatch -----------------------------------------------------------------

_COMPILERS = {
    'trigger': (_trigger_create, _trigger_alter, _trigger_drop),
    'event-trigger': (_event_trigger_create, _event_trigger_alter,
                      _event_trigger_drop),
    'rule': (_rule_create, _rule_alter, _rule_drop),
}


def compile_operation(kind, operation, native, draft):
    """One exact native text for a trigger, event trigger or rule."""
    create, alter, drop = _COMPILERS[kind]
    if operation == 'create':
        statements = create(draft)
    elif operation == 'alter':
        statements = alter(native, draft)
    elif operation == 'drop':
        statements = drop(native, draft)
    else:
        raise PostgreSQLNativeAdminError(
            f'{kind} inspection stays with the provider tree')
    return {'statement': ';\n'.join(statements), 'read_only': False}


# -- forms --------------------------------------------------------------------

def _enable_field(field, field_id, facts_key, alter):
    options = [{'value': key, 'label': label.title()}
               for key, label in ENABLE_STATES.items()]
    extra = {'initial_value_path': [facts_key, field_id]} if alter else {}
    return field(field_id, 'Enabled', 'select', options=options, **extra)


def form(kind, operation, field):
    """Dialog fields; ids follow the inherited dialogs."""
    label = {'trigger': 'trigger', 'event-trigger': 'event trigger',
             'rule': 'rule'}[kind]
    facts_key = {'trigger': 'trigger_facts',
                 'event-trigger': 'event_trigger_facts',
                 'rule': 'rule_facts'}[kind]
    alter = operation == 'alter'

    def initial(key):
        return {'initial_value_path': [facts_key, key]} if alter else {}
    if operation == 'drop':
        fields = [field('cascade', 'Drop dependent objects', 'boolean'),
                  field('confirmation', f'Type the {label} name to confirm',
                        required=True)]
    elif kind == 'trigger':
        fields = [field('name', 'Name', required=not alter, **initial('name'))]
        if not alter:
            fields += [field('schema', 'Schema', required=True),
                       field('table', 'Table', required=True)]
        fields += [
            field('is_constraint_trigger', 'Constraint trigger', 'boolean',
                  **initial('is_constraint_trigger')),
            field('fires', 'Fires', 'select', options=[
                {'value': item, 'label': item.title()} for item in FIRES],
                **({} if alter else {'default': 'AFTER'}),
                **initial('fires')),
            field('evnt_insert', 'INSERT', 'boolean',
                  **initial('evnt_insert')),
            field('evnt_update', 'UPDATE', 'boolean',
                  **initial('evnt_update')),
            field('evnt_delete', 'DELETE', 'boolean',
                  **initial('evnt_delete')),
            field('evnt_truncate', 'TRUNCATE', 'boolean',
                  **initial('evnt_truncate')),
            field('columns', 'Columns (UPDATE OF)', 'grid', columns=[
                {'field_id': 'column', 'label': 'Column', 'control': 'text',
                 'required': True}], **initial('columns')),
            field('is_row_trigger', 'Row trigger', 'boolean',
                  **({} if alter else {'default': True}),
                  **initial('is_row_trigger')),
            field('tgdeferrable', 'Deferrable', 'boolean',
                  help='Constraint triggers only.', **initial('tgdeferrable')),
            field('tginitdeferred', 'Initially deferred', 'boolean',
                  **initial('tginitdeferred')),
            field('tgoldtable', 'Old table (REFERENCING)',
                  **initial('tgoldtable')),
            field('tgnewtable', 'New table (REFERENCING)',
                  **initial('tgnewtable')),
            field('whenclause', 'When', 'code', **initial('whenclause')),
            field('tfunction', 'Trigger function', required=not alter,
                  help='schema.function', **initial('tfunction')),
            field('tgargs', 'Arguments', help='Comma-separated text values.',
                  **initial('tgargs')),
            field('description', 'Comment', 'multiline',
                  **initial('description'))]
        if alter:
            fields.append(_enable_field(field, 'is_enable_trigger', facts_key,
                                        True))
    elif kind == 'event-trigger':
        fields = [
            field('name', 'Name', required=not alter, **initial('name')),
            field('eventname', 'Event', 'select', required=not alter,
                  options=[{'value': item, 'label': item}
                           for item in EVENT_TRIGGER_EVENTS],
                  **initial('eventname')),
            field('when', 'When TAG in', help=(
                "Comma-separated command tags, e.g. CREATE TABLE, DROP TABLE"),
                **initial('when')),
            field('eventfunname', 'Trigger function', required=not alter,
                  help='schema.function' + (
                      '; required with a changed event or tags.' if alter
                      else '')),
            field('eventowner', 'Owner'),
            field('comment', 'Comment', 'multiline', **initial('comment'))]
        if alter:
            fields.append(_enable_field(field, 'enabled', facts_key, True))
    else:
        fields = [field('name', 'Name', required=not alter, **initial('name'))]
        if not alter:
            fields += [field('schema', 'Schema', required=True),
                       field('view', 'Table or view', required=True)]
        fields += [
            field('event', 'Event', 'select', required=not alter, options=[
                {'value': item, 'label': item}
                for item in RULE_EVENTS.values()],
                **({} if alter else {'default': 'SELECT'}),
                **initial('event')),
            field('do_instead', 'Do instead', 'boolean',
                  **initial('do_instead')),
            field('condition', 'Condition', 'code', **initial('condition')),
            field('statements', 'Commands', 'code', help=(
                'SELECT, INSERT, UPDATE, DELETE or NOTIFY statements, or '
                'NOTHING.'), **initial('statements')),
            field('comment', 'Comment', 'multiline', **initial('comment'))]
        if alter:
            fields.append(_enable_field(field, 'is_enable_rule', facts_key,
                                        True))
    return {'form_id': f'postgresql-{kind}-{operation}',
            'form_key': f'native:postgresql:schema:{kind}',
            'title': f'{operation.title()} {label}', 'fields': fields}
