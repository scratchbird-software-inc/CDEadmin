"""Explicit PostgreSQL creation drafts; never infer creation from missing OIDs."""
import uuid
import re
from .firebird_schema_plan import digest
from ..providers.postgresql.native_admin import _identifier, _qualified, _type_reference

DEFINITION_KINDS = {
    'collation': ('OBJECT_COLLATION', 'pg_collation'),
    'conversion': (None, 'pg_conversion'),
    'text-search-configuration': ('OBJECT_TSCONFIGURATION', 'pg_ts_config'),
    'text-search-dictionary': ('OBJECT_TSDICTIONARY', 'pg_ts_dict'),
    'text-search-parser': ('OBJECT_TSPARSER', 'pg_ts_parser'),
    'text-search-template': ('OBJECT_TSTEMPLATE', 'pg_ts_template'),
}


TABLE_DEFINITIONS = {
    'trigger': ('CreateTrigStmt', 'trigname', 'relation', 'pg_trigger', 'tgrelid'),
    'rule': ('RuleStmt', 'rulename', 'relation', 'pg_rewrite', 'ev_class'),
    'policy': ('CreatePolicyStmt', 'policy_name', 'table', 'pg_policy', 'polrelid'),
}


def table_definition(kind, schema, name, draft):
    from pglast import parse_sql, ast
    value = draft.get('definition')
    table = draft.get('table')
    _identifier(table, 'owning table')
    if not isinstance(value, str) or not value or '\x00' in value or len(value.encode()) > 1024 * 1024:
        raise ValueError('Table-owned definition must be bounded SQL text')
    try:
        parsed = parse_sql(value)
    except Exception:
        raise ValueError('Table-owned definition failed native grammar validation') from None
    cls, name_field, relation_field, _, _ = TABLE_DEFINITIONS[kind]
    node = parsed[0].stmt if len(parsed) == 1 else None
    if not isinstance(node, getattr(ast, cls)) or getattr(node, 'replace', False) or getattr(node, name_field) != name:
        raise ValueError('Definition must match its exact native object kind and name without replacement')
    relation = getattr(node, relation_field)
    if relation.schemaname != schema or relation.relname != table:
        raise ValueError('Definition must identify the declared qualified owning table')
    return value, {'schema': schema, 'table': table}


def named_definition(kind, schema, name, draft):
    from pglast import parse_sql, ast
    from pglast.enums import ObjectType
    value = draft.get('definition')
    if not isinstance(value, str) or not value or '\x00' in value or len(value.encode()) > 1024 * 1024:
        raise ValueError('Native definition must be bounded SQL text')
    try:
        parsed = parse_sql(value)
        if len(parsed) != 1:
            raise ValueError()
        node = parsed[0].stmt
        if kind == 'conversion':
            if not isinstance(node, ast.CreateConversionStmt):
                raise ValueError()
            names = node.conversion_name
        else:
            if (not isinstance(node, ast.DefineStmt) or node.kind != getattr(ObjectType, DEFINITION_KINDS[kind][0]) or
                    node.replace or node.if_not_exists):
                raise ValueError()
            names = node.defnames
        if [part.sval for part in names] != [schema, name]:
            raise ValueError()
    except Exception:
        raise ValueError('Native CREATE definition must match its exact kind, schema and name without replacement') from None
    return value


def partition_definition(kind, schema, name, draft):
    from pglast import parse_sql, ast
    value = draft.get('definition')
    if (set(draft) - {'name', 'schema', 'depends_on', 'definition'} or
            not isinstance(value, str) or not value or '\x00' in value or len(value.encode()) > 1024 * 1024):
        raise ValueError('Partition creation requires one bounded native definition')
    try:
        parsed = parse_sql(value)
        if len(parsed) != 1 or not isinstance(parsed[0].stmt, ast.CreateStmt):
            raise ValueError()
        node = parsed[0].stmt
        relation = node.relation
        if (relation.schemaname != schema or relation.relname != name or relation.relpersistence != 'p' or
                node.if_not_exists or bool(node.partspec) != (kind == 'partitioned-table') or
                not (node.partspec or node.partbound)):
            raise ValueError()
        parents = node.inhRelations or ()
        if node.partbound:
            if len(parents) != 1 or not parents[0].schemaname:
                raise ValueError()
            parent = {'schema': parents[0].schemaname, 'table': parents[0].relname}
        else:
            if parents:
                raise ValueError()
            parent = None
    except Exception:
        raise ValueError('Partition definition must match exact permanent relation kind/schema/name and qualified parent') from None
    return value, parent


def literal(value):
    if not isinstance(value, str) or '\x00' in value or len(value.encode('utf8')) > 63:
        raise ValueError('Enum labels must be text of at most 63 UTF-8 bytes')
    return "E'" + value.replace('\\', '\\\\').replace("'", "''") + "'"


def expression(value):
    """Admit one expression and render its AST, never a query/statement tail."""
    if not isinstance(value, str) or not value or len(value.encode('utf8')) > 65536 or '\x00' in value:
        raise ValueError('Expression must be bounded native SQL text')
    from pglast import parse_sql, ast
    from pglast.stream import RawStream
    try:
        parsed = parse_sql('SELECT (' + value + ')')
        statement = parsed[0].stmt
        if len(parsed) != 1 or not isinstance(statement, ast.SelectStmt):
            raise ValueError()
        if any(getattr(statement, field) not in (None, False, 0, ())
               for field in statement if field != 'targetList'):
            raise ValueError()
        if len(statement.targetList) != 1 or statement.targetList[0].name:
            raise ValueError()
        return RawStream()(statement.targetList[0].val)
    except Exception:
        raise ValueError('Invalid native SQL expression') from None


def select_query(value):
    if not isinstance(value, str) or not value or len(value.encode('utf8')) > 1024 * 1024 or '\x00' in value:
        raise ValueError('View query must be bounded native SQL text')
    from pglast import parse_sql, ast
    from pglast.stream import RawStream
    try:
        parsed = parse_sql(value)
        if len(parsed) != 1 or not isinstance(parsed[0].stmt, ast.SelectStmt) or parsed[0].stmt.intoClause:
            raise ValueError()
        return RawStream()(parsed[0].stmt)
    except Exception:
        raise ValueError('View query must be a single SELECT without INTO') from None


def view_definition(kind, qualified, draft):
    columns = draft.get('columns', [])
    if (not isinstance(columns, list) or len(columns) > 1600 or
            any(not isinstance(name, str) for name in columns) or len(set(columns)) != len(columns)):
        raise ValueError('View output columns must be distinct bounded names')
    text = 'CREATE ' + ('MATERIALIZED ' if kind == 'materialized-view' else '') + 'VIEW ' + qualified
    if columns:
        text += ' (' + ', '.join(_identifier(name, 'view column') for name in columns) + ')'
    if kind == 'view':
        options = []
        for key in ('security_barrier', 'security_invoker'):
            if key in draft:
                if type(draft[key]) is not bool:
                    raise ValueError('View security options must be boolean')
                options.append(key + '=' + str(draft[key]).lower())
        if options:
            text += ' WITH (' + ', '.join(options) + ')'
    text += ' AS ' + select_query(draft.get('query'))
    if kind == 'materialized-view':
        populated = draft.get('with_data', False)
        if type(populated) is not bool:
            raise ValueError('Materialized-view with_data must be boolean')
        text += ' WITH DATA' if populated else ' WITH NO DATA'
    elif 'check_option' in draft:
        if draft['check_option'] not in {'LOCAL', 'CASCADED'}:
            raise ValueError('View check option must be LOCAL or CASCADED')
        text += ' WITH ' + draft['check_option'] + ' CHECK OPTION'
    return text


def qualified_reference(value, label):
    if not isinstance(value, dict) or set(value) != {'schema', 'name'}:
        raise ValueError(label + ' requires exact schema and name')
    return _qualified(value['schema'], value['name'])


def type_definition(qualified, draft):
    kind = draft.get('type_kind', 'ENUM')
    fields = {'ENUM': {'labels'}, 'COMPOSITE': {'attributes'},
              'RANGE': {'subtype', 'subtype_opclass', 'collation', 'subtype_diff'}}
    if not isinstance(kind, str) or kind not in fields or set(draft) - (fields[kind] | {'name', 'schema', 'depends_on', 'type_kind'}):
        raise ValueError('Unsupported fields for native type kind')
    prefix = 'CREATE TYPE ' + qualified + ' AS '
    if kind == 'ENUM':
        labels = draft.get('labels')
        if not isinstance(labels, list) or len(labels) > 1000 or len(set(map(str, labels))) != len(labels):
            raise ValueError('Enum labels must be a distinct bounded list')
        return prefix + 'ENUM (' + ', '.join(literal(x) for x in labels) + ')'
    if kind == 'COMPOSITE':
        attributes = draft.get('attributes')
        if not isinstance(attributes, list) or len(attributes) > 1600:
            raise ValueError('Composite attributes must be a bounded ordered array')
        values, names = [], set()
        for attribute in attributes:
            if not isinstance(attribute, dict) or set(attribute) - {'name', 'data_type', 'collation'}:
                raise ValueError('Unsupported composite attribute fields')
            value = _identifier(attribute.get('name'), 'attribute') + ' ' + _type_reference(attribute.get('data_type'), 'attribute type')
            if attribute['name'] in names:
                raise ValueError('Composite attribute names must be distinct')
            names.add(attribute['name'])
            if 'collation' in attribute:
                value += ' COLLATE ' + qualified_reference(attribute['collation'], 'Attribute collation')
            values.append(value)
        return prefix + '(' + ', '.join(values) + ')'
    options = ['SUBTYPE = ' + _type_reference(draft.get('subtype'), 'range subtype')]
    for field in ('subtype_opclass', 'collation', 'subtype_diff'):
        if field in draft:
            options.append(field.upper() + ' = ' + qualified_reference(draft[field], field))
    return prefix + 'RANGE (' + ', '.join(options) + ')'


def index_parameters(parameters):
    if not isinstance(parameters, dict) or not 1 <= len(parameters) <= 64:
        raise ValueError('Index parameters require one to 64 named values')
    if any(not isinstance(name, str) for name in parameters):
        raise ValueError('Index parameter names must be text')
    rendered = []
    for name, value in sorted(parameters.items()):
        if type(value) is bool:
            value = 'true' if value else 'false'
        elif type(value) is int:
            value = str(value)
        if not isinstance(value, str) or '\x00' in value or len(value.encode('utf8')) > 4096:
            raise ValueError('Index parameter values must be bounded text, integers or booleans')
        quoted = "E'" + value.replace('\\', '\\\\').replace("'", "''") + "'"
        rendered.append(_identifier(name, 'index parameter') + ' = ' + quoted)
    return '(' + ', '.join(rendered) + ')'


def index_definition(name, schema, draft):
    unique = draft.get('unique', False)
    if type(unique) is not bool:
        raise ValueError('Index unique must be boolean')
    text = 'CREATE ' + ('UNIQUE ' if unique else '') + 'INDEX ' + _identifier(name, 'index')
    text += ' ON ' + _qualified(schema, draft.get('table'))
    text += ' USING ' + _identifier(draft.get('method', 'btree'), 'index method')
    keys = draft.get('keys')
    if not isinstance(keys, list) or not 1 <= len(keys) <= 32:
        raise ValueError('Index requires one to 32 keys')
    rendered = []
    for key in keys:
        if (not isinstance(key, dict) or set(key) - {'column', 'expression', 'order', 'nulls', 'collation', 'opclass', 'opclass_parameters'}
                or sum(field in key for field in ('column', 'expression')) != 1):
            raise ValueError('Index key requires exactly one column or expression')
        value = _identifier(key['column'], 'index column') if 'column' in key else '(' + expression(key['expression']) + ')'
        for field, prefix in [('collation', ' COLLATE '), ('opclass', ' ')]:
            if field in key:
                reference = key[field]
                if not isinstance(reference, dict) or set(reference) != {'schema', 'name'}:
                    raise ValueError('Index collation/opclass requires exact schema and name')
                value += prefix + _qualified(reference['schema'], reference['name'])
        if 'opclass_parameters' in key:
            if 'opclass' not in key:
                raise ValueError('Index operator-class parameters require an explicit operator class')
            value += ' ' + index_parameters(key['opclass_parameters'])
        for field, allowed, prefix in [('order', {'ASC', 'DESC'}, ' '), ('nulls', {'FIRST', 'LAST'}, ' NULLS ')]:
            if field in key:
                if not isinstance(key[field], str) or key[field] not in allowed:
                    raise ValueError('Invalid index ordering')
                value += prefix + key[field]
        rendered.append(value)
    text += ' (' + ', '.join(rendered) + ')'
    include = draft.get('include', [])
    if (not isinstance(include, list) or len(include) + len(keys) > 32 or
            any(not isinstance(item, str) for item in include) or len(set(include)) != len(include)):
        raise ValueError('Included index columns must be distinct and bounded')
    if include:
        text += ' INCLUDE (' + ', '.join(_identifier(item, 'included column') for item in include) + ')'
    if 'nulls_distinct' in draft:
        if type(draft['nulls_distinct']) is not bool or not unique:
            raise ValueError('Index null distinction requires a unique index and boolean value')
        text += ' NULLS DISTINCT' if draft['nulls_distinct'] else ' NULLS NOT DISTINCT'
    if 'storage_parameters' in draft:
        text += ' WITH ' + index_parameters(draft['storage_parameters'])
    if 'tablespace' in draft:
        text += ' TABLESPACE ' + _identifier(draft['tablespace'], 'tablespace')
    if 'predicate' in draft:
        text += ' WHERE (' + expression(draft['predicate']) + ')'
    return text


def domain_definition(qualified, draft):
    text = 'CREATE DOMAIN ' + qualified + ' AS ' + _type_reference(draft.get('data_type'), 'domain type')
    if 'default' in draft:
        text += ' DEFAULT (' + expression(draft['default']) + ')'
    nullable = draft.get('nullable', True)
    if type(nullable) is not bool:
        raise ValueError('Domain nullable must be boolean')
    if not nullable:
        text += ' NOT NULL'
    checks = draft.get('checks', [])
    if not isinstance(checks, list) or len(checks) > 128:
        raise ValueError('Domain checks must be a bounded array')
    names = set()
    for check in checks:
        if not isinstance(check, dict) or set(check) != {'name', 'expression'}:
            raise ValueError('Domain CHECK requires a name and expression')
        quoted = _identifier(check['name'], 'domain constraint')
        if check['name'] in names:
            raise ValueError('Domain constraint names must be distinct')
        names.add(check['name'])
        text += ' CONSTRAINT ' + quoted + ' CHECK (' + expression(check['expression']) + ')'
    return text


def column_definition(column):
    if not isinstance(column, dict) or set(column) - {'name', 'data_type', 'nullable', 'default', 'generated', 'identity'}:
        raise ValueError('Unsupported native column fields')
    text = _identifier(column.get('name'), 'column name') + ' ' + _type_reference(column.get('data_type'), 'column type')
    nullable = column.get('nullable', True)
    if type(nullable) is not bool:
        raise ValueError('Column nullable must be boolean')
    if sum(key in column for key in ('default', 'generated', 'identity')) > 1:
        raise ValueError('Column default, generation and identity are mutually exclusive')
    if 'default' in column:
        text += ' DEFAULT (' + expression(column['default']) + ')'
    if 'generated' in column:
        generated = column['generated']
        if (not isinstance(generated, dict) or set(generated) != {'expression', 'storage'} or
                generated['storage'] not in {'STORED', 'VIRTUAL'}):
            raise ValueError('Generated column requires expression and STORED/VIRTUAL storage')
        text += ' GENERATED ALWAYS AS (' + expression(generated['expression']) + ') ' + generated['storage']
    if 'identity' in column:
        if column['identity'] not in {'ALWAYS', 'BY DEFAULT'} or column.get('nullable') is True:
            raise ValueError('Identity requires ALWAYS/BY DEFAULT and cannot be nullable')
        text += ' GENERATED ' + column['identity'] + ' AS IDENTITY'
    return text + ('' if nullable else ' NOT NULL')


def key_definition(key, names):
    if not isinstance(key, dict):
        raise ValueError('Native table key must be an object')
    kind = key.get('kind')
    allowed = {'PRIMARY KEY': {'columns'}, 'UNIQUE': {'columns'}, 'CHECK': {'expression'},
        'FOREIGN KEY': {'columns', 'references', 'match', 'on_update', 'on_delete'}}
    if kind not in allowed or set(key) - (allowed[kind] | {'kind', 'name', 'deferrable', 'initially_deferred'}):
        raise ValueError('Unsupported native table key')
    text = 'CONSTRAINT ' + _identifier(key.get('name'), 'key name') + ' ' + kind
    if kind == 'CHECK':
        if 'deferrable' in key or 'initially_deferred' in key:
            raise ValueError('CHECK constraints do not support deferrability')
        return text + ' (' + expression(key.get('expression')) + ')'
    fields = key.get('columns')
    if (not isinstance(fields, list) or not fields or any(not isinstance(x, str) or x not in names for x in fields)
            or len(set(fields)) != len(fields)):
        raise ValueError('Ordered column references must be unique and valid')
    text += ' (' + ', '.join(_identifier(x, 'column') for x in fields) + ')'
    if kind == 'FOREIGN KEY':
        ref = key.get('references')
        if not isinstance(ref, dict) or set(ref) != {'schema', 'table', 'columns'}:
            raise ValueError('Foreign key requires referenced schema, table and columns')
        columns = ref['columns']
        if (not isinstance(columns, list) or len(columns) != len(fields) or
                any(not isinstance(x, str) for x in columns) or len(set(columns)) != len(columns)):
            raise ValueError('Foreign key column counts must match without duplicates')
        text += ' REFERENCES ' + _qualified(ref['schema'], ref['table']) + ' (' + ', '.join(_identifier(x, 'referenced column') for x in columns) + ')'
        match = key.get('match', 'SIMPLE')
        if match not in {'SIMPLE', 'FULL'}:
            raise ValueError('Foreign key MATCH must be SIMPLE or FULL')
        text += ' MATCH ' + match
        for field, clause in [('on_update', ' ON UPDATE '), ('on_delete', ' ON DELETE ')]:
            action = key.get(field, 'NO ACTION')
            if action not in {'NO ACTION', 'RESTRICT', 'CASCADE', 'SET NULL', 'SET DEFAULT'}:
                raise ValueError('Invalid foreign key action')
            text += clause + action
    deferred, initial = key.get('deferrable', False), key.get('initially_deferred', False)
    if type(deferred) is not bool or type(initial) is not bool or (initial and not deferred):
        raise ValueError('Invalid constraint deferrability')
    return text + (' DEFERRABLE' if deferred else ' NOT DEFERRABLE') + (' INITIALLY DEFERRED' if initial else ' INITIALLY IMMEDIATE')


def routine_definition(kind, schema, name, draft):
    from pglast import parse_sql, ast
    from pglast.stream import RawStream
    definition = draft.get('definition')
    if (not isinstance(definition, str) or not definition.strip() or '\x00' in definition or
            len(definition.encode('utf8')) > 2 * 1024 * 1024):
        raise ValueError('Routine definition must be bounded native SQL')
    try:
        parsed = parse_sql(definition)
        node = parsed[0].stmt
        if len(parsed) != 1:
            raise ValueError()
        if kind == 'aggregate':
            if (not isinstance(node, ast.DefineStmt) or node.kind.name != 'OBJECT_AGGREGATE' or
                    node.oldstyle or node.replace or node.if_not_exists or
                    [part.sval for part in node.defnames] != [schema, name]):
                raise ValueError()
            parameters = node.args[0] or ()
        else:
            if (not isinstance(node, ast.CreateFunctionStmt) or node.replace or
                    bool(node.is_procedure) != (kind == 'procedure') or
                    [part.sval for part in node.funcname] != [schema, name]):
                raise ValueError()
            window = any(option.defname == 'window' for option in (node.options or ()))
            if window != (kind == 'window-function'):
                raise ValueError()
            parameters = node.parameters or ()
        inputs = [RawStream()(parameter.argType) for parameter in parameters
                  if parameter.mode.name not in {'FUNC_PARAM_OUT', 'FUNC_PARAM_TABLE'}]
        signature = _qualified(schema, name) + '(' + ', '.join(inputs) + ')'
        return definition, signature
    except Exception:
        raise ValueError('Routine draft must create exactly its declared qualified routine kind without replacement') from None


def creation(identity, row):
    if not identity.startswith('postgresql:new:'):
        raise ValueError('Creation requires a new PostgreSQL draft UUID, not a catalog OID')
    try:
        if str(uuid.UUID(identity.removeprefix('postgresql:new:'))) != identity.removeprefix('postgresql:new:'):
            raise ValueError()
    except ValueError:
        raise ValueError('Creation requires a canonical draft UUID') from None
    if row.get('system') != 'false':
        raise ValueError('Creation requires an explicitly user-managed object')
    if set(row.get('native', {})) - {'system_object', 'create'}:
        raise ValueError('New objects cannot claim captured catalog identities or definitions')
    draft = row.get('native', {}).get('create')
    if not isinstance(draft, dict):
        raise ValueError('Object creation requires an explicit native create draft')
    kind = row['kind']
    allowed = {'schema': {'owner'}, 'function': {'definition'}, 'procedure': {'definition'},
               'window-function': {'definition'}, 'aggregate': {'definition'}, 'type': {'labels', 'type_kind', 'attributes', 'subtype', 'subtype_opclass', 'collation', 'subtype_diff'},
               'domain': {'data_type', 'default', 'nullable', 'checks'},
               'index': {'table', 'keys', 'method', 'unique', 'include', 'nulls_distinct', 'predicate', 'tablespace', 'storage_parameters'},
               'view': {'query', 'columns', 'security_barrier', 'security_invoker', 'check_option'},
               'materialized-view': {'query', 'columns', 'with_data'},
               'sequence': {'data_type', 'increment', 'start', 'minvalue', 'maxvalue', 'cache', 'cycle'},
               'table': {'columns', 'keys', 'unlogged', 'definition'},
               'partitioned-table': {'definition'}}
    allowed.update({kind: {'definition'} for kind in DEFINITION_KINDS})
    allowed.update({kind: {'definition','table'} for kind in TABLE_DEFINITIONS})
    if kind not in allowed or set(draft) - (allowed[kind] | {'name', 'schema', 'depends_on'}):
        raise ValueError('Unsupported native creation kind or fields')
    name = draft.get('name')
    quoted = _identifier(name, 'name')
    if name != row.get('name'):
        raise ValueError('Creation name disagrees with the catalog row')
    schema = draft.get('schema')
    routine_signature = None
    partition_parent = None
    table_owner = None
    if kind == 'schema':
        if schema is not None:
            raise ValueError('A schema does not have a parent schema')
        statement = 'CREATE SCHEMA ' + quoted
        if draft.get('owner') is not None:
            statement += ' AUTHORIZATION ' + _identifier(draft['owner'], 'owner')
    else:
        qualified = _qualified(schema, name)
        if kind in {'function', 'procedure', 'window-function', 'aggregate'}:
            statement, routine_signature = routine_definition(kind, schema, name, draft)
        elif kind in TABLE_DEFINITIONS:
            statement, table_owner = table_definition(kind, schema, name, draft)
        elif kind in DEFINITION_KINDS:
            statement = named_definition(kind, schema, name, draft)
        elif kind == 'partitioned-table' or kind == 'table' and 'definition' in draft:
            statement, partition_parent = partition_definition(kind, schema, name, draft)
        elif kind == 'type':
            statement = type_definition(qualified, draft)
        elif kind == 'index':
            statement = index_definition(name, schema, draft)
        elif kind == 'domain':
            statement = domain_definition(qualified, draft)
        elif kind in {'view', 'materialized-view'}:
            statement = view_definition(kind, qualified, draft)
        elif kind == 'sequence':
            data_type = draft.get('data_type', 'bigint')
            if data_type not in {'smallint', 'integer', 'bigint'}:
                raise ValueError('Sequence data type must be smallint, integer or bigint')
            statement = 'CREATE SEQUENCE ' + qualified + ' AS ' + data_type
            for field, token in [('increment','INCREMENT BY'), ('start','START WITH'),
                                 ('minvalue','MINVALUE'), ('maxvalue','MAXVALUE'), ('cache','CACHE')]:
                if field in draft:
                    value = draft[field]
                    if isinstance(value, str) and re.fullmatch(r'-?(?:0|[1-9][0-9]{0,18})', value):
                        value = int(value)
                    if type(value) is not int or not -(2**63) <= value < 2**63:
                        raise ValueError('Sequence values must be exact signed 64-bit integers')
                    statement += f' {token} {value}'
            cycle = draft.get('cycle', False)
            if type(cycle) is not bool:
                raise ValueError('Sequence cycle must be boolean')
            statement += ' CYCLE' if cycle else ' NO CYCLE'
        else:
            columns, keys = draft.get('columns'), draft.get('keys', [])
            if not isinstance(columns, list) or len(columns) > 1600 or not isinstance(keys, list) or len(keys) > 128:
                raise ValueError('Table columns and keys must be bounded arrays')
            definitions, names, key_names = [], set(), set()
            for column in columns:
                text = column_definition(column)
                column_name = column['name']
                if column_name in names:
                    raise ValueError('Duplicate native column name')
                names.add(column_name)
                definitions.append(text)
            for key in keys:
                text = key_definition(key, names)
                if key['name'] in key_names:
                    raise ValueError('Duplicate native key name')
                key_names.add(key['name'])
                definitions.append(text)
            unlogged = draft.get('unlogged', False)
            if type(unlogged) is not bool:
                raise ValueError('Table unlogged must be boolean')
            statement = 'CREATE ' + ('UNLOGGED ' if unlogged else '') + 'TABLE ' + qualified + ' (' + ', '.join(definitions) + ')'
    dependencies = draft.get('depends_on', [])
    if (not isinstance(dependencies, list) or len(dependencies) > 1024 or
            any(not isinstance(x, str) or not x for x in dependencies) or len(set(dependencies)) != len(dependencies)):
        raise ValueError('Creation dependencies must be a bounded distinct list of resource identities')
    if len(statement.encode('utf8')) > 2 * 1024 * 1024:
        raise ValueError('Creation statement exceeds 2 MiB')
    from ..providers.postgresql.language import analyze
    if analyze(statement, standard_strings='on')['grammar_valid'] is not True:
        raise ValueError('Generated creation statement did not pass native grammar validation')
    return {'resource_id': identity, 'kind': kind, 'name': name, 'schema': schema,
            'operation': 'create', 'statement': statement, 'dependencies': dependencies,
            'routine_signature': routine_signature,
            'partition_parent': partition_parent, 'table_owner': table_owner,
            'type_kind': draft.get('type_kind', 'ENUM') if kind == 'type' else None,
            'references': ([table_owner] if table_owner else [partition_parent] if partition_parent else [{'schema': schema, 'table': draft['table']}] if kind == 'index' else
                [key['references'] for key in draft.get('keys', []) if key.get('kind') == 'FOREIGN KEY'])}


def order_creations(operations, current):
    """Order declared dependencies and new schema ownership without DROP guesses."""
    creates = {op['resource_id']: op for op in operations if op.get('operation') == 'create'}
    schemas = {op['name']: key for key, op in creates.items() if op['kind'] == 'schema'}
    edges, occupied = {}, {}
    def namespaces(kind, type_kind=None):
        if kind in TABLE_DEFINITIONS or kind in DEFINITION_KINDS:
            return {kind}
        return {'routine'} if kind in {'function', 'procedure', 'window-function', 'aggregate'} else {'schema'} if kind == 'schema' else {'relation', 'type'} if kind in {'table', 'partitioned-table', 'view', 'materialized-view'} or type_kind == 'COMPOSITE' else {'relation'} if kind in {'sequence', 'index'} else {'type'}
    for identity, operation in creates.items():
        dependencies = set(operation['dependencies'])
        if operation['schema'] in schemas:
            dependencies.add(schemas[operation['schema']])
        elif operation['kind'] != 'schema':
            matches = [(key, row) for key, row in current['rows'].items()
                       if row['kind'] == 'schema' and row['name'] == operation['schema']]
            if len(matches) != 1:
                raise ValueError('Creation schema is unavailable or ambiguous: ' + operation['schema'])
            key, row = matches[0]
            native = row.get('native', {})
            oid = native.get('oid')
            if (row.get('system') == 'false' and native.get('catalog') == 'pg_namespace' and
                    type(oid) is int and 0 < oid < 2**32 and key == f'postgresql:pg_namespace:{oid}'):
                operation['schema_guard'] = {'oid': oid, 'resource_id': key, 'native_sha256': digest(native)}
        for reference in operation.get('references', []):
            targets = [key for key, candidate in creates.items() if candidate['kind'] in {'table', 'partitioned-table', 'materialized-view'} and
                       candidate['schema'] == reference['schema'] and candidate['name'] == reference['table']]
            if operation.get('table_owner') == reference:
                if targets:
                    if len(targets) != 1 or creates[targets[0]]['kind'] != 'table' or creates[targets[0]].get('partition_parent') or targets[0] not in dependencies:
                        raise ValueError('Table-owned creation requires an explicit ordinary-table dependency')
                else:
                    owners = [(key, row) for key, row in current['rows'].items() if row['kind'] == 'table' and
                              row['name'] == reference['table'] and row['native'].get('schema') == reference['schema']]
                    if len(owners) != 1:
                        raise ValueError('Owning ordinary table is unavailable or ambiguous')
                    key, row = owners[0]; native = row['native']; oid = native.get('oid')
                    facts = native.get('catalog_row', {})
                    if (key not in dependencies or row.get('system') != 'false' or native.get('catalog') != 'pg_class' or
                            type(oid) is not int or not 0 < oid < 2**32 or key != f'postgresql:pg_class:{oid}' or
                            facts.get('relname') != reference['table'] or facts.get('relispartition') or facts.get('relhassubclass') or
                            native.get('children', {}).get('pg_inherits')):
                        raise ValueError('Owning table requires an explicit, ordinary captured native identity')
                    operation['owner_guard'] = {'resource_id': key, 'oid': oid, 'native_sha256': digest(native)}
                    operation['lock_target'] = {'oid': oid, 'schema': reference['schema'], 'name': reference['table']}
            if operation.get('partition_parent') == reference:
                if targets:
                    if len(targets) != 1 or creates[targets[0]]['kind'] != 'partitioned-table' or targets[0] not in dependencies:
                        raise ValueError('Partition parent requires an explicit dependency on its partitioned table')
                else:
                    parents = [(key, row) for key, row in current['rows'].items()
                               if row['kind'] == 'partitioned-table' and row['name'] == reference['table'] and
                               row['native'].get('schema') == reference['schema']]
                    if len(parents) != 1:
                        raise ValueError('Existing partition parent is unavailable or ambiguous')
                    key, row = parents[0]
                    native = row['native']
                    oid = native.get('oid')
                    if (key not in dependencies or row.get('system') != 'false' or
                            native.get('catalog') != 'pg_class' or type(oid) is not int or
                            not 0 < oid < 2**32 or key != f'postgresql:pg_class:{oid}' or
                            native.get('catalog_row', {}).get('relname') != reference['table']):
                        raise ValueError('Existing partition parent requires an explicit captured native identity')
                    operation['parent_guard'] = {'resource_id': key, 'oid': oid, 'native_sha256': digest(native)}
                    operation['lock_target'] = {'oid': oid, 'schema': reference['schema'], 'name': reference['table']}
            if any(key != identity and key not in dependencies for key in targets):
                raise ValueError('New referenced tables require an explicit creation dependency')
        missing = dependencies - creates.keys() - current['rows'].keys()
        if missing:
            raise ValueError('Creation dependencies are unavailable: ' + ', '.join(sorted(missing)))
        for namespace in namespaces(operation['kind'], operation.get('type_kind')):
            key = namespace, operation['schema'], ((operation['table_owner']['table'], operation['name']) if operation.get('table_owner') else operation.get('routine_signature') if namespace == 'routine' else operation['name'])
            if key in occupied:
                raise ValueError('Creation drafts collide in a native namespace: ' + operation['name'])
            occupied[key] = identity
        for row in current['rows'].values():
            native = row.get('native', {})
            namespace = {'pg_class': 'relation', 'pg_type': 'type', 'pg_namespace': 'schema', 'pg_proc': 'routine'}.get(native.get('catalog'))
            namespace = next((kind for kind, (_, catalog) in DEFINITION_KINDS.items()
                              if catalog == native.get('catalog')), namespace)
            namespace = next((kind for kind, definition in TABLE_DEFINITIONS.items() if definition[3] == native.get('catalog')), namespace)
            collision = row['name'] == operation['name'] and namespace in namespaces(operation['kind'], operation.get('type_kind'))
            if collision and operation.get('table_owner'):
                field = TABLE_DEFINITIONS[operation['kind']][4]
                collision = str(native.get('catalog_row', {}).get(field)) == str(operation.get('owner_guard', {}).get('oid', 'new'))
            # Names alone cannot identify overloaded routines. Native CREATE
            # (never OR REPLACE) rejects any resolved input-signature collision.
            if collision and namespace != 'routine' and (namespace == 'schema' or native.get('schema') == operation['schema']):
                raise ValueError('A native object already occupies the requested name: ' + operation['name'])
        edges[identity] = dependencies & creates.keys()
    ordered = []
    while edges:
        ready = sorted(key for key, dependencies in edges.items() if not dependencies)
        if not ready:
            raise ValueError('Creation dependencies contain a cycle')
        for key in ready:
            ordered.append(creates[key]);del edges[key]
        for dependencies in edges.values():
            dependencies.difference_update(ready)
    return ordered + [op for op in operations if op.get('operation') != 'create']
