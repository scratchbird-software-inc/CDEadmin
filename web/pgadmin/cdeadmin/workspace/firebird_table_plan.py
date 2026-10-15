"""Structured table DDL with explicit native property and child boundaries."""
from ..providers.firebird import tables, columns
from ..providers.firebird.character_metadata import identifier, literal
from ..providers.firebird_expressions import index_expression
from . import firebird_domain_plan as domains
from .firebird_view_plan import dependencies as schema_dependencies
from .firebird_table_constraints import creation as child_creation
from .firebird_trigger_plan import model as trigger_model

FIELDS = {'sql_security', 'publication_enabled', 'description'}
STRUCTURE = {'relation_type', 'external_file', 'columns', 'constraints', 'indexes', 'triggers'}
DERIVED = {'publications', 'column_order', 'ddl_available', 'ddl_unavailable_reason', 'metadata_warnings'}


def model(row):
    native = row['native']
    if str(native.get('relation_type')) not in {'0', '2', '4', '5'}:
        raise ValueError('Table planning requires an observed native table kind')
    flag = native.get('sql_security')
    if type(flag) is bool:
        flag = '1' if flag else '0'
    elif isinstance(flag, str) and flag.upper() in {'TRUE', 'FALSE'}:
        flag = '1' if flag.upper() == 'TRUE' else '0'
    if flag is not None and (type(flag) not in (int, str) or str(flag) not in {'0', '1'}):
        raise ValueError('SQL security requires a native zero/one flag or NULL')
    publication = native.get('publication_enabled')
    if type(publication) is not bool:
        raise ValueError('Publication membership must be observed as boolean')
    return {'sql_security': None if flag is None else str(flag),
            'publication_enabled': publication}


def creation_model(row, current, *, observed=False):
    native = row['native']
    kind = str(native['relation_type'])
    if kind == '2' or native.get('external_file'):
        raise ValueError('External-file creation needs an explicit filesystem-effect workflow')
    # Do not lose explicitly authored keys, checks, indexes or triggers.
    triggers = native.get('triggers') or []
    owners = {item.get('name') for item in native.get('constraints', []) if isinstance(item, dict)}
    if observed:
        owners.update(item['name'] for item in current['rows'].values() if item['kind'] == 'constraint')
    for trigger in triggers:
        if not isinstance(trigger, dict):
            raise ValueError('Every table trigger definition must be an object')
        if observed and trigger.get('constraint_owner') in owners:
            continue
        matches = [item for item in current['rows'].values() if item['kind'] == 'trigger'
                   and item['name'] == trigger.get('name') and item['native'].get('relation') == row['name']]
        if len(matches) != 1 or trigger.get('relation') != row['name']:
            raise ValueError('Table creation with triggers requires matching standalone trigger definitions')
        if trigger_model(matches[0]) != trigger_model({'native': trigger}):
            raise ValueError('Nested and standalone trigger definitions disagree')
        if (matches[0]['native'].get('description') or None) != (trigger.get('description') or None):
            raise ValueError('Nested and standalone trigger comments disagree')
    raw = native.get('columns')
    if not isinstance(raw, list) or not 1 <= len(raw) <= 1024:
        raise ValueError('Table creation requires 1–1024 ordered native columns')
    if any(not isinstance(col, dict) for col in raw):
        raise ValueError('Every column definition must be an object')
    ordered = sorted(raw, key=lambda col: int(columns.integer(col.get('position'), 0, 1023, 'Column position')))
    children = child_creation(row, current)
    names, definitions, comments = set(), [], []
    dependencies = set(children['dependencies'])
    for position, col in enumerate(ordered):
        if int(columns.integer(col.get('position'), 0, 1023, 'Column position')) != position:
            raise ValueError('Column positions must be contiguous and unique')
        name = col.get('name'); identifier(name)
        if name in names:
            raise ValueError('Duplicate native column name')
        names.add(name)
        # Additional child behavior must be reviewed, not discarded.
        allowed = domains.TYPE_FIELDS | {'name', 'position', 'domain', 'domain_not_null',
            'not_null', 'default_source', 'computed_source', 'description',
            'identity_type', 'generator_name', 'identity_initial_value', 'identity_increment',
            'alteration', 'type_editor', 'dependencies', 'dependents', 'property_sections',
            'navigator_parent_resource_id', 'system_object'}
        unknown = {key for key, value in col.items() if key not in allowed and value not in (None, [], {})}
        if unknown:
            raise ValueError('Unsupported column properties: ' + ', '.join(sorted(unknown)))
        domain_null = col.get('domain_not_null')
        if domain_null is not None and (type(domain_null) not in (int, str) or str(domain_null) not in {'0', '1'}):
            raise ValueError('Domain nullability requires a native zero/one flag or NULL')
        if col.get('identity_type') is None and any(col.get(key) is not None for key in (
                'generator_name', 'identity_initial_value', 'identity_increment')):
            raise ValueError('Identity generator facts require an identity column')
        domain = col.get('domain')
        if domain is not None:
            identifier(domain)
        if domain and not domain.startswith('RDB$'):
            matches = [item for item in current['rows'].values() if item['kind'] == 'domain' and item['path'] == [domain]]
            if len(matches) != 1:
                raise ValueError('Referenced domain must be observed in the current catalog')
            dependency = matches[0]
            if 'domain_not_null' in col and str(domain_null or '0') != str(dependency['native'].get('not_null') or '0'):
                raise ValueError('Expanded column nullability disagrees with referenced domain')
            dependencies.add(dependency['resource_id'])
            # A domain reference is authoritative for its base type. Reject
            # conflicting expanded facts instead of silently ignoring edits.
            for key in domains.TYPE_FIELDS - {'collation'}:
                if key not in col:
                    continue
                left, right = col[key], dependency['native'].get(key)
                if key == 'array_dimensions':
                    equivalent = (left or []) == (right or [])
                elif key in {'character_set'}:
                    equivalent = left == right
                else:
                    equivalent = str(left or '0') == str(right or '0')
                if not equivalent:
                    raise ValueError('Expanded column type disagrees with referenced domain: ' + key)
            rendered, collation = identifier(domain), col.get('collation')
            if collation is not None:
                matches = [item for item in current['rows'].values() if item['kind'] == 'collation'
                           and item['name'] == collation and item['native'].get('character_set') == col.get('character_set')]
                if len(matches) != 1:
                    raise ValueError('Column collation must be observed for its character set')
                dependencies.add(matches[0]['resource_id'])
        else:
            if str(domain_null or '0') != '0':
                raise ValueError('Anonymous-domain NOT NULL requires explicit constraint reconciliation')
            type_facts = {**col, 'domain': None}
            # Firebird records the computed descriptor's physical precision
            # for plain integer results; this is not NUMERIC declaration syntax.
            precision = {'7': '4', '8': '9', '16': '18', '26': '38'}.get(str(col.get('field_type')))
            if (col.get('computed_source') and str(col.get('field_sub_type') or '0') == '0'
                    and precision is not None and str(col.get('field_precision')) == precision):
                type_facts['field_precision'] = 0
            typed = domains.creation_model({'native': type_facts}, current)
            dependencies.update(typed['dependencies'])
            rendered, collation = domains.render_type(typed), typed['collation']
        sql = identifier(name) + ' ' + rendered
        if col.get('identity_type') is not None:
            if str(col['identity_type']) not in {'0', '1'} or col.get('computed_source') or col.get('default_source'):
                raise ValueError('Invalid identity column metadata')
            identity = columns.definition({'name': name, 'column_mode': 'IDENTITY', 'data_type': 'BIGINT',
                'generation': 'ALWAYS' if str(col['identity_type']) == '0' else 'BY DEFAULT',
                'start_value': col.get('identity_initial_value'), 'increment': col.get('identity_increment')})
            if col.get('identity_initial_value') is None or col.get('identity_increment') is None:
                raise ValueError('Identity creation requires exact initial value and increment')
            sql += ' GENERATED ' + identity.partition(' GENERATED ')[2]
        if col.get('computed_source'):
            if col.get('default_source') or str(col.get('not_null')) == '1' or collation:
                raise ValueError('Computed columns cannot carry defaults/nullability/collation clauses')
            expression = index_expression(col['computed_source'], 'Computed expression', require_outer=True)
            sql += ' COMPUTED BY ' + expression + '\n'
        else:
            default = domains.clause(col.get('default_source'), 'DEFAULT')
            if default:
                if col.get('array_dimensions'):
                    raise ValueError('Array columns cannot have defaults')
                sql += ' ' + default + '\n'
            flag = col.get('not_null')
            if flag is not None and (type(flag) not in (int, str) or str(flag) not in {'0', '1'}):
                raise ValueError('Column nullability requires a native zero/one flag or NULL')
            if name in children['column_nulls']:
                if str(flag) != '1':
                    raise ValueError('NOT NULL constraint and expanded column nullability disagree')
                sql += ' ' + children['column_nulls'][name]
            elif str(flag) == '1' and col.get('identity_type') is None and name not in children['primary_columns']:
                raise ValueError('NOT NULL column creation requires named constraint planning')
            if collation:
                sql += ' COLLATE ' + identifier(collation)
        if col.get('computed_source') or col.get('default_source'):
            dependencies.update(schema_dependencies(current))
        definitions.append(sql)
        comment = col.get('description')
        if comment:
            comments.append('COMMENT ON COLUMN ' + identifier(row['path'][-1]) + '.' + identifier(name) + ' IS ' + literal(comment))
    return {'foreign_keys': children['foreign_keys'], 'relation_type': kind, 'definitions': definitions + children['clauses'],
            'comments': comments + children['statements'],
            'dependencies': sorted(dependencies)}


def statements(before, after):
    security = {'0': 'INVOKER', '1': 'DEFINER', None: 'INHERIT'}[after['sql_security']]
    publication = 'ENABLE' if after['publication_enabled'] else 'DISABLE'
    if before is not None:
        return tables.alterations(after['name'], {
            'sql_security': security if before['sql_security'] != after['sql_security'] else 'UNCHANGED',
            'publication': publication if before['publication_enabled'] != after['publication_enabled'] else 'UNCHANGED'})
    typed = after['creation_table']; temporary = typed['relation_type'] in {'4', '5'}
    options = {'table_type': 'GLOBAL TEMPORARY' if temporary else 'PERSISTENT',
               'sql_security': security, 'publication': 'DEFAULT' if temporary else publication}
    if temporary:
        options['on_commit'] = 'PRESERVE ROWS' if typed['relation_type'] == '4' else 'DELETE ROWS'
    result = [tables.create(after['name'], typed['definitions'], options)]
    if temporary:
        result.extend(tables.alterations(after['name'], {'publication': publication}))
    return result + typed['comments']


def staged_creation(after, new_tables):
    """Render inter-table foreign keys only after every new key exists."""
    typed = after['creation_table']
    deferred = [item for item in typed['foreign_keys']
                if item['referenced_table'] in new_tables
                and item['referenced_table'] != after['name']]
    clauses = {item['clause'] for item in deferred}
    prefixes = {'COMMENT ON INDEX ' + identifier(item['index_name']) + ' IS '
                for item in deferred}
    comments = [sql for sql in typed['comments'] if any(sql.startswith(prefix) for prefix in prefixes)]
    effective = {**after, 'creation_table': {**typed,
        'definitions': [sql for sql in typed['definitions'] if sql not in clauses],
        'comments': [sql for sql in typed['comments'] if sql not in comments]}}
    late = ['ALTER TABLE ' + identifier(after['name']) + ' ADD ' + item['clause'] for item in deferred]
    return effective, late + comments
