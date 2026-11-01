"""YugabyteDB YSQL event triggers, rules, collations and publications.

Checked live on 2025.2.2.2 (2026-11-01):

- event triggers: CREATE EVENT TRIGGER ... ON ddl_command_start |
  ddl_command_end | sql_drop | table_rewrite [WHEN TAG IN (...)] EXECUTE
  FUNCTION; ALTER EVENT TRIGGER ENABLE [REPLICA | ALWAYS] | DISABLE |
  RENAME TO; COMMENT ON EVENT TRIGGER. Event, function and tags cannot
  change in place.
- rules: CREATE [OR REPLACE] RULE ... AS ON INSERT | UPDATE | DELETE TO t
  [WHERE ...] DO [ALSO | INSTEAD] NOTHING | command | (commands); COMMENT ON
  RULE; DROP RULE ... ON t. ALTER RULE ... RENAME is refused ("not
  supported yet"), so a rule keeps its name.
- collations: CREATE COLLATION s.n (provider = icu | libc, locale = ...);
  RENAME TO, SET SCHEMA, COMMENT ON COLLATION. A nondeterministic
  collation is refused, so it is not offered.
- publications: CREATE PUBLICATION n [FOR ALL TABLES | FOR TABLE ...]; ALTER
  PUBLICATION SET | ADD | DROP TABLE, RENAME TO; COMMENT ON PUBLICATION.
  Publishing a subset of DML commands and schema-level publications are
  refused ("not yet supported"), so neither is offered. A table without a
  primary key is refused ("cannot be replicated").
"""
import re

from ...sdk.relational import RelationalClientError

EVENTS = ('ddl_command_start', 'ddl_command_end', 'sql_drop',
          'table_rewrite')
ENABLED = {'ORIGIN': 'ENABLE', 'DISABLED': 'DISABLE',
           'REPLICA': 'ENABLE REPLICA', 'ALWAYS': 'ENABLE ALWAYS'}
STORED_ENABLED = {'O': 'ORIGIN', 'D': 'DISABLED', 'R': 'REPLICA',
                  'A': 'ALWAYS'}
RULE_EVENTS = ('INSERT', 'UPDATE', 'DELETE')
PROVIDERS = {'icu': 'icu', 'libc': 'libc'}
STORED_PROVIDERS = {'i': 'icu', 'c': 'libc'}
_TAG = re.compile(r'[A-Z][A-Z ]{0,62}')
_LOCALE = re.compile(r'[A-Za-z0-9_.@=;-]{1,128}')
_IGNORED = {'variant', 'confirmation'}


def _blank(value):
    return value is None or value == '' or value == []


def _known(draft, keys, kind):
    unknown = set(draft) - keys - _IGNORED
    if unknown:
        raise RelationalClientError(
            f'unknown {kind} option: ' + ', '.join(sorted(unknown)))


def _comment(admin, target, value):
    text = 'NULL' if _blank(value) else admin._literal(str(value))
    return {'source': f'COMMENT ON {target} IS {text}', 'parameters': ()}


def _function(admin, value):
    """A function reference as schema.name, from a reference control."""
    if isinstance(value, list):
        value = '.'.join(str(part) for part in value)
    if not isinstance(value, str) or not value:
        raise RelationalClientError('choose the event trigger function')
    parts = value.split('.')
    if len(parts) > 2 or not all(parts):
        raise RelationalClientError('the function is schema.name')
    # A routine's resource name carries its signature, evt(); an event
    # trigger function takes no arguments.
    if parts[-1].endswith('()'):
        parts[-1] = parts[-1][:-2]
    return '.'.join(admin._quote(admin._identifier(part)) for part in parts)


def _strings(value, label):
    if _blank(value):
        return []
    if not isinstance(value, list):
        raise RelationalClientError(f'{label} must be a list')
    result = [item.get('value') if isinstance(item, dict) else item
              for item in value]
    if not all(isinstance(item, str) and item for item in result) or len(
            set(result)) != len(result):
        raise RelationalClientError(f'{label} must be distinct names')
    return result


def _qualified(admin, value, label):
    if isinstance(value, list):
        parts = [str(part) for part in value]
    elif isinstance(value, str) and value:
        parts = value.split('.')
    else:
        raise RelationalClientError(f'{label} is required')
    if len(parts) > 2 or not all(parts):
        raise RelationalClientError(f'{label} is schema.name')
    return '.'.join(admin._quote(admin._identifier(part)) for part in parts)


# Event triggers -------------------------------------------------------------

EVENT_TRIGGER_CREATE = {'name', 'event', 'function', 'tags', 'enabled',
                        'comment'}
EVENT_TRIGGER_ALTER = {'name', 'enabled', 'comment', 'event', 'function',
                       'tags'}


def create_event_trigger(admin, draft):
    _known(draft, EVENT_TRIGGER_CREATE, 'event trigger')
    name = admin._quote(admin._identifier(draft.get('name')))
    if draft.get('event') not in EVENTS:
        raise RelationalClientError('choose the event that fires the trigger')
    source = f'CREATE EVENT TRIGGER {name} ON {draft["event"]}'
    tags = _strings(draft.get('tags'), 'command tags')
    if tags:
        if not all(_TAG.fullmatch(tag) for tag in tags):
            raise RelationalClientError(
                'a command tag is upper case, for example CREATE TABLE')
        source += ' WHEN TAG IN (' + ', '.join(
            admin._literal(tag) for tag in tags) + ')'
    source += (' EXECUTE FUNCTION ' + _function(admin, draft.get('function'))
               + '()')
    statements = [{'source': source, 'parameters': ()}]
    enabled = draft.get('enabled') or 'ORIGIN'
    if enabled not in ENABLED:
        raise RelationalClientError('choose when the event trigger fires')
    if enabled != 'ORIGIN':
        statements.append({'source': (
            f'ALTER EVENT TRIGGER {name} {ENABLED[enabled]}'),
            'parameters': ()})
    if not _blank(draft.get('comment')):
        statements.append(_comment(admin, f'EVENT TRIGGER {name}',
                                   draft['comment']))
    return statements


def alter_event_trigger(admin, draft, target):
    _known(draft, EVENT_TRIGGER_ALTER, 'event trigger')
    native = (target or {}).get('native') or {}
    wanted = {**draft}
    if 'tags' in wanted:
        wanted['tags'] = _strings(wanted['tags'], 'command tags')
    for key in ('event', 'function', 'tags'):
        if key in wanted and wanted[key] != native.get(key) and not (
                _blank(wanted[key]) and _blank(native.get(key))):
            raise RelationalClientError(
                f'an event trigger cannot change its {key} in place; drop '
                'it and create it again')
    name = admin._quote((target or {}).get('display_name'))
    statements = []
    if not _blank(draft.get('enabled')) and (
            draft['enabled'] != native.get('enabled')):
        if draft['enabled'] not in ENABLED:
            raise RelationalClientError('choose when the event trigger fires')
        statements.append({'source': (
            f'ALTER EVENT TRIGGER {name} {ENABLED[draft["enabled"]]}'),
            'parameters': ()})
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        statements.append(_comment(admin, f'EVENT TRIGGER {name}',
                                   draft['comment']))
    if not _blank(draft.get('name')) and draft['name'] != (
            target or {}).get('display_name'):
        statements.append({'source': (
            f'ALTER EVENT TRIGGER {name} RENAME TO '
            f'{admin._quote(admin._identifier(draft["name"]))}'),
            'parameters': ()})
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


# Rules ----------------------------------------------------------------------

RULE_KEYS = {'name', 'parent', 'table', 'event', 'condition', 'instead',
             'actions', 'comment'}


def _rule_source(admin, draft, table, replace):
    if draft.get('event') not in RULE_EVENTS:
        raise RelationalClientError('choose INSERT, UPDATE or DELETE')
    name = admin._quote(admin._identifier(draft.get('name')))
    source = (f'CREATE {"OR REPLACE " if replace else ""}RULE {name} AS ON '
              f'{draft["event"]} TO {table}')
    condition = draft.get('condition')
    if not _blank(condition):
        source += f' WHERE {str(condition).strip()}'
    source += ' DO INSTEAD ' if draft.get('instead') else ' DO ALSO '
    # Sent as written; several commands are parenthesized, as rules
    # require. A parenthesized single command is equally valid, so a ';'
    # inside a literal is never split.
    actions = str(draft.get('actions') or '').strip().rstrip(';').strip()
    if not actions:
        source += 'NOTHING'
    elif ';' in actions:
        source += '(' + actions + ')'
    else:
        source += actions
    return source


def create_rule(admin, draft):
    _known(draft, RULE_KEYS, 'rule')
    table = _qualified(admin, draft.get('table'), 'table')
    statements = [{'source': _rule_source(admin, draft, table, False),
                   'parameters': ()}]
    if not _blank(draft.get('comment')):
        statements.append(_comment(
            admin, f'RULE {admin._quote(draft["name"])} ON {table}',
            draft['comment']))
    return statements


def alter_rule(admin, draft, target):
    _known(draft, RULE_KEYS, 'rule')
    native = (target or {}).get('native') or {}
    path = (target or {}).get('display_path') or []
    if len(path) != 3:
        raise RelationalClientError('the rule target is invalid')
    if not _blank(draft.get('name')) and draft['name'] != path[2]:
        raise RelationalClientError(
            'YugabyteDB 2025.2.2.2 refuses ALTER RULE ... RENAME; a rule '
            'keeps its name')
    table = '.'.join(admin._quote(part) for part in path[:2])
    merged = {**{key: native.get(key) for key in (
        'event', 'condition', 'instead', 'actions')}, **draft,
        'name': path[2]}
    statements = []
    if any(key in draft and draft[key] != native.get(key)
           for key in ('event', 'condition', 'instead', 'actions')):
        statements.append({'source': _rule_source(admin, merged, table, True),
                           'parameters': ()})
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        statements.append(_comment(
            admin, f'RULE {admin._quote(path[2])} ON {table}',
            draft['comment']))
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


def drop_rule(admin, target):
    path = (target or {}).get('display_path') or []
    if len(path) != 3:
        raise RelationalClientError('the rule target is invalid')
    return [{'source': (f'DROP RULE {admin._quote(path[2])} ON '
                        f'{admin._quote(path[0])}.{admin._quote(path[1])}'),
             'parameters': ()}]


_RULE = re.compile(
    r'ON\s+(INSERT|UPDATE|DELETE)\s+TO\s+\S+\s*(?:WHERE\s+(.*?))?\s*DO\s+'
    r'(INSTEAD\s+)?(.*?);?\s*$', re.DOTALL | re.IGNORECASE)


def rule_native(definition, comment):
    """The editable parts of a rule from pg_rules.definition."""
    match = _RULE.search(str(definition or ''))
    if match is None:
        return {'definition': str(definition or ''),
                'comment': None if comment is None else str(comment)}
    condition = (match.group(2) or '').strip()
    if condition.startswith('(') and condition.endswith(')'):
        condition = condition[1:-1].strip()
    actions = match.group(4).strip()
    if actions.upper() == 'NOTHING':
        actions = ''
    elif actions.startswith('(') and actions.endswith(')'):
        actions = actions[1:-1].strip()
    return {
        'definition': str(definition), 'event': match.group(1).upper(),
        'condition': condition or None, 'instead': bool(match.group(3)),
        'actions': ' '.join(actions.split()) or None,
        'comment': None if comment is None else str(comment),
    }


# Collations -----------------------------------------------------------------

COLLATION_CREATE = {'name', 'parent', 'provider', 'locale', 'comment'}
COLLATION_ALTER = {'name', 'parent', 'comment', 'provider', 'locale'}


def create_collation(admin, draft):
    _known(draft, COLLATION_CREATE, 'collation')
    name = admin._quote(admin._identifier(draft.get('name')))
    if not _blank(draft.get('parent')):
        name = admin._quote(admin._identifier(draft['parent'])) + '.' + name
    provider = PROVIDERS.get(draft.get('provider') or 'icu')
    locale = draft.get('locale')
    if provider is None:
        raise RelationalClientError('choose the icu or libc provider')
    if not isinstance(locale, str) or not _LOCALE.fullmatch(locale):
        raise RelationalClientError('enter a locale such as de-DE or C')
    statements = [{'source': (
        f'CREATE COLLATION {name} (provider = {provider}, locale = '
        f'{admin._literal(locale)})'), 'parameters': ()}]
    if not _blank(draft.get('comment')):
        statements.append(_comment(admin, f'COLLATION {name}',
                                   draft['comment']))
    return statements


def alter_collation(admin, draft, target):
    _known(draft, COLLATION_ALTER, 'collation')
    native = (target or {}).get('native') or {}
    for key in ('provider', 'locale'):
        if not _blank(draft.get(key)) and draft[key] != native.get(key):
            raise RelationalClientError(
                f'a collation cannot change its {key}; create another')
    path = (target or {}).get('display_path') or []
    if len(path) != 2:
        raise RelationalClientError('the collation target is invalid')
    schema, current = path
    name = f'{admin._quote(schema)}.{admin._quote(current)}'
    statements = []
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        statements.append(_comment(admin, f'COLLATION {name}',
                                   draft['comment']))
    if not _blank(draft.get('name')) and draft['name'] != current:
        statements.append({'source': (
            f'ALTER COLLATION {name} RENAME TO '
            f'{admin._quote(admin._identifier(draft["name"]))}'),
            'parameters': ()})
        name = f'{admin._quote(schema)}.{admin._quote(draft["name"])}'
    if not _blank(draft.get('parent')) and draft['parent'] != schema:
        statements.append({'source': (
            f'ALTER COLLATION {name} SET SCHEMA '
            f'{admin._quote(admin._identifier(draft["parent"]))}'),
            'parameters': ()})
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


# Publications ---------------------------------------------------------------

PUBLICATION_CREATE = {'name', 'all_tables', 'tables', 'comment'}
PUBLICATION_ALTER = {'name', 'all_tables', 'tables', 'comment'}


def _tables(admin, value):
    return [_qualified(admin, item, 'table') for item in _strings(
        [entry if not isinstance(entry, list) else '.'.join(entry)
         for entry in (value or [])], 'tables')]


def create_publication(admin, draft):
    _known(draft, PUBLICATION_CREATE, 'publication')
    name = admin._quote(admin._identifier(draft.get('name')))
    source = f'CREATE PUBLICATION {name}'
    tables = _tables(admin, draft.get('tables'))
    if draft.get('all_tables'):
        if tables:
            raise RelationalClientError(
                'a publication for all tables lists no tables')
        source += ' FOR ALL TABLES'
    elif tables:
        source += ' FOR TABLE ' + ', '.join(tables)
    statements = [{'source': source, 'parameters': ()}]
    if not _blank(draft.get('comment')):
        statements.append(_comment(admin, f'PUBLICATION {name}',
                                   draft['comment']))
    return statements


def alter_publication(admin, draft, target):
    _known(draft, PUBLICATION_ALTER, 'publication')
    native = (target or {}).get('native') or {}
    current = (target or {}).get('display_name')
    name = admin._quote(current)
    if 'all_tables' in draft and bool(draft['all_tables']) != bool(
            native.get('all_tables')):
        raise RelationalClientError(
            'FOR ALL TABLES cannot change in place; create another '
            'publication')
    statements = []
    if 'tables' in draft and not native.get('all_tables'):
        wanted = _tables(admin, draft.get('tables'))
        held = _tables(admin, native.get('tables') or [])
        if wanted and set(wanted) != set(held):
            statements.append({'source': (
                f'ALTER PUBLICATION {name} SET TABLE ' + ', '.join(wanted)),
                'parameters': ()})
        elif not wanted and held:
            statements.append({'source': (
                f'ALTER PUBLICATION {name} DROP TABLE ' + ', '.join(held)),
                'parameters': ()})
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        statements.append(_comment(admin, f'PUBLICATION {name}',
                                   draft['comment']))
    if not _blank(draft.get('name')) and draft['name'] != current:
        statements.append({'source': (
            f'ALTER PUBLICATION {name} RENAME TO '
            f'{admin._quote(admin._identifier(draft["name"]))}'),
            'parameters': ()})
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


def form(field, kind, operation):
    """Provider forms; the descriptor forms carry the full layout."""
    fields = {
        'event-trigger': lambda: [
            field('name', 'Name', 'text', True),
            field('event', 'Event', 'select', True, options=list(EVENTS)),
            field('function', 'Function', 'text', True),
            field('tags', 'Command tags', 'json', False, default=[]),
            field('enabled', 'Fires', 'select', False, default='ORIGIN',
                  options=list(ENABLED)),
            field('comment', 'Comment', 'text')],
        'rule': lambda: [
            field('name', 'Name', 'text', True),
            field('parent', 'Schema', 'text'),
            field('table', 'Table', 'text', True),
            field('event', 'Event', 'select', True,
                  options=list(RULE_EVENTS)),
            field('condition', 'Condition', 'text'),
            field('instead', 'Instead', 'boolean', False, default=False),
            field('actions', 'Commands', 'text'),
            field('comment', 'Comment', 'text')],
        'collation': lambda: [
            field('name', 'Name', 'text', True),
            field('parent', 'Schema', 'text'),
            field('provider', 'Provider', 'select', False, default='icu',
                  options=list(PROVIDERS)),
            field('locale', 'Locale', 'text', True),
            field('comment', 'Comment', 'text')],
        'publication': lambda: [
            field('name', 'Name', 'text', True),
            field('all_tables', 'All tables', 'boolean', False,
                  default=False),
            field('tables', 'Tables', 'json', False, default=[]),
            field('comment', 'Comment', 'text')],
    }[kind]()
    if operation == 'alter':
        for item in fields:
            # A create default would read as a requested change.
            item.pop('default', None)
            item['required'] = False
            item['initial_value_path'] = [item['field_id']]
    return {'form_id': f'yugabytedb.{kind}.{operation}',
            'title': f'{operation.title()} {kind.replace("-", " ")}',
            'fields': fields}


BUILDERS = {
    'event-trigger': {'create': create_event_trigger,
                      'alter': alter_event_trigger},
    'rule': {'create': create_rule, 'alter': alter_rule,
             'drop': lambda admin, _draft, target: drop_rule(admin, target)},
    'collation': {'create': create_collation, 'alter': alter_collation},
    'publication': {'create': create_publication,
                    'alter': alter_publication},
}


def compile_request(admin, kind, operation, draft, target):
    builder = BUILDERS[kind][operation]
    if operation == 'create':
        return builder(admin, draft)
    return builder(admin, draft, target)


def resources(cursor, generation, resource, optional_rows, excluded):
    """Event triggers, rules, collations and publications of a database."""
    values = []
    for name, event, schema, function, enabled, tags, owner, comment in \
            optional_rows(
                cursor,
                'SELECT e.evtname, e.evtevent, n.nspname, p.proname, '
                'e.evtenabled, e.evttags, r.rolname, '
                "obj_description(e.oid, 'pg_event_trigger') "
                'FROM pg_catalog.pg_event_trigger e '
                'JOIN pg_catalog.pg_proc p ON p.oid = e.evtfoid '
                'JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace '
                'JOIN pg_catalog.pg_roles r ON r.oid = e.evtowner '
                'ORDER BY 1'):
        values.append(resource('event-trigger', [], name, generation, {
            'event': str(event), 'function': f'{schema}.{function}',
            'tags': [str(tag) for tag in tags or ()],
            'enabled': STORED_ENABLED.get(str(enabled), str(enabled)),
            'owner': str(owner),
            'comment': None if comment is None else str(comment),
        }))
    for schema, table, name, definition, comment in optional_rows(
        cursor,
        'SELECT n.nspname, c.relname, r.rulename, '
        'pg_catalog.pg_get_ruledef(r.oid), '
        "obj_description(r.oid, 'pg_rewrite') "
        'FROM pg_catalog.pg_rewrite r '
        'JOIN pg_catalog.pg_class c ON c.oid = r.ev_class '
        'JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace '
        # A view's _RETURN rule is the view itself.
        f"WHERE r.rulename <> '_RETURN' AND n.nspname NOT IN {excluded} "
        'ORDER BY 1, 2, 3',
    ):
        values.append(resource('rule', [schema, table], name, generation, {
            **rule_native(definition, comment),
            'table': [str(schema), str(table)],
        }))
    for schema, name, provider, collate, locale, owner, comment in \
            optional_rows(
                cursor,
                'SELECT n.nspname, c.collname, c.collprovider, '
                'c.collcollate, c.colliculocale, r.rolname, '
                "obj_description(c.oid, 'pg_collation') "
                'FROM pg_catalog.pg_collation c '
                'JOIN pg_catalog.pg_namespace n ON n.oid = c.collnamespace '
                'JOIN pg_catalog.pg_roles r ON r.oid = c.collowner '
                f'WHERE n.nspname NOT IN {excluded} ORDER BY 1, 2'):
        provider = STORED_PROVIDERS.get(str(provider), str(provider))
        values.append(resource('collation', [schema], name, generation, {
            'provider': provider,
            'locale': str(locale if provider == 'icu' else collate),
            'owner': str(owner),
            'comment': None if comment is None else str(comment),
        }))
    tables = {}
    for publication, schema, table in optional_rows(
        cursor,
        'SELECT pubname, schemaname, tablename '
        'FROM pg_catalog.pg_publication_tables ORDER BY 1, 2, 3',
    ):
        tables.setdefault(str(publication), []).append(f'{schema}.{table}')
    for name, all_tables, owner, comment in optional_rows(
        cursor,
        'SELECT p.pubname, p.puballtables, r.rolname, '
        "obj_description(p.oid, 'pg_publication') "
        'FROM pg_catalog.pg_publication p '
        'JOIN pg_catalog.pg_roles r ON r.oid = p.pubowner ORDER BY 1',
    ):
        values.append(resource('publication', [], name, generation, {
            'all_tables': bool(all_tables),
            # For all tables the list is what it covers today, not a
            # setting.
            'tables': [] if all_tables else tables.get(str(name), []),
            'covered_tables': tables.get(str(name), []),
            'owner': str(owner),
            'comment': None if comment is None else str(comment),
        }))
    return values
