##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Dependency-light compiler for PostgreSQL provider-native admin forms."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .preserved_surface import administration_operations


POSTGRESQL_ADMIN_OPERATIONS = administration_operations()
POSTGRESQL_NATIVE_FORM_KINDS = frozenset({
    'conversion', 'operator-class', 'operator-family', 'access-method', 'transform', 'operator', 'aggregate', 'large-object',
})
_NAME = r'(?:[^\W\d][\w$]*|"(?:[^"\x00]|"")+")'
_PG_REFERENCE = re.compile(rf'{_NAME}(?:\.{_NAME})?(?:\[\])?')
_PG_OPERATOR = re.compile(
    rf'(?:{_NAME}\.)?[+\-*/<>=~!@#%^&|`?]+'
)


class PostgreSQLNativeAdminError(RuntimeError):
    """A PostgreSQL provider-native operation cannot be compiled safely."""


def _required_text(value, label):
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise PostgreSQLNativeAdminError(f'{label} must not be empty')
    return value.strip()


def _flag(draft, name):
    value = draft.get(name, False)
    if type(value) is not bool:
        raise PostgreSQLNativeAdminError(f'{name} must be boolean')
    return value


def _identifier(value, label):
    value = _name(value, label)
    if len(value.encode('utf-8')) > 63:
        raise PostgreSQLNativeAdminError(f'{label} exceeds 63 bytes')
    return '"' + value.replace('"', '""') + '"'


def _name(value, label):
    # Quoted catalog names can contain leading/trailing whitespace, including
    # names made only of spaces. Stripping them selects a different object.
    if not isinstance(value, str) or not value or '\x00' in value:
        raise PostgreSQLNativeAdminError(f'{label} must not be empty')
    return value


def _qualified(schema, name):
    return f'{_identifier(schema, "schema")}.{_identifier(name, "name")}'


def _literal(value, label):
    value = _name(value, label)
    # E literals keep backslashes data even with standard_conforming_strings off.
    prefix = 'E' if '\\' in value else ''
    return prefix + "'" + value.replace('\\', '\\\\').replace("'", "''") + "'"


def _reference(value, label, operator=False):
    value = _required_text(value, label)
    pattern = _PG_OPERATOR if operator else _PG_REFERENCE
    if pattern.fullmatch(value) is None or (operator and ('--' in value or '/*' in value)):
        raise PostgreSQLNativeAdminError(
            f'{label} is not a catalog reference'
        )
    return value


def _type_reference(value, label):
    value = _required_text(value, label)
    if _PG_REFERENCE.fullmatch(value):
        return value
    if len(value.encode('utf8')) > 4096:
        raise PostgreSQLNativeAdminError(f'{label} exceeds 4096 bytes')
    from .language import analyze
    statement = 'SELECT CAST(NULL AS ' + value + ')'
    if analyze(statement, standard_strings='on')['grammar_valid'] is not True:
        raise PostgreSQLNativeAdminError(f'{label} is not an admitted native type')
    from pglast import parse_sql, ast
    from pglast.stream import RawStream
    parsed = parse_sql(statement)
    node = parsed[0].stmt if len(parsed) == 1 else None
    excluded = ('fromClause', 'whereClause', 'groupClause', 'havingClause', 'windowClause',
                'valuesLists', 'sortClause', 'limitOffset', 'limitCount', 'lockingClause',
                'withClause', 'larg', 'rarg', 'intoClause', 'distinctClause')
    if (not isinstance(node, ast.SelectStmt) or node.op != 0 or
            any(getattr(node, key, None) is not None for key in excluded) or
            not node.targetList or len(node.targetList) != 1 or node.targetList[0].name is not None):
        raise PostgreSQLNativeAdminError(f'{label} must contain only a native type')
    cast = node.targetList[0].val
    if not isinstance(cast, ast.TypeCast) or not isinstance(cast.arg, ast.A_Const) or not cast.arg.isnull:
        raise PostgreSQLNativeAdminError(f'{label} must contain only a native type')
    return RawStream()(cast.typeName)


def _native_target(request):
    target = request.get('target_resource') or {}
    extensions = target.get('extensions') or {}
    value = extensions.get('postgresql') or {}
    native = value.get('native', value)
    if not isinstance(native, Mapping):
        raise PostgreSQLNativeAdminError(
            'PostgreSQL native target identity is unavailable'
        )
    return dict(native)


def _native_identity(native, draft, creating=False):
    source = draft if creating else native
    return (
        _name(source.get('schema'), 'schema'),
        _name(source.get('name'), 'name'),
    )


def _alter_statement(kind, qualified_name, draft, native):
    action = _required_text(draft.get('action'), 'alter action').lower()
    if kind == 'operator-family' and action in {'add_members', 'drop_members'}:
        return _family_members(qualified_name, draft, native, action)
    value = _name(draft.get('value'), 'alter value')
    keyword = {
        'conversion': 'CONVERSION',
        'operator-class': 'OPERATOR CLASS',
        'operator-family': 'OPERATOR FAMILY',
    }[kind]
    using = ''
    if kind in {'operator-class', 'operator-family'}:
        method = _reference(native.get('index_method'), 'index access method')
        using = f' USING {method}'
    if action == 'owner':
        return (
            f'ALTER {keyword} {qualified_name}{using} OWNER TO '
            f'{_identifier(value, "owner")}'
        )
    if action == 'rename':
        return (
            f'ALTER {keyword} {qualified_name}{using} RENAME TO '
            f'{_identifier(value, "new name")}'
        )
    if action == 'schema':
        return (
            f'ALTER {keyword} {qualified_name}{using} SET SCHEMA '
            f'{_identifier(value, "new schema")}'
        )
    raise PostgreSQLNativeAdminError(
        'PostgreSQL alter action is unavailable'
    )


def _family_members(qualified_name, draft, native, action):
    method = _reference(native.get('index_method'), 'index access method')
    if action == 'add_members':
        items = _operator_class_items(draft)
        verb = 'ADD'
    else:
        members = draft.get('members')
        if not isinstance(members, list):
            raise PostgreSQLNativeAdminError('removed members must be a list')
        items = []
        for member in members:
            if not isinstance(member, Mapping) or member.get('kind') not in {'OPERATOR', 'FUNCTION'}:
                raise PostgreSQLNativeAdminError('member kind must be OPERATOR or FUNCTION')
            number = member.get('number')
            if type(number) is not int or not 1 <= number <= 32767:
                raise PostgreSQLNativeAdminError('member number is invalid')
            operands = _type_list(member.get('operand_types'), 'member operand types', sizes={2})
            items.append(f'{member["kind"]} {number}{operands}')
        verb = 'DROP'
    if not items:
        raise PostgreSQLNativeAdminError('operator family requires at least one member change')
    return f'ALTER OPERATOR FAMILY {qualified_name} USING {method} {verb} ' + ', '.join(items)


def _operator_class_items(draft):
    items = []
    operators = draft.get('operators', [])
    functions = draft.get('functions', [])
    if not isinstance(operators, list):
        raise PostgreSQLNativeAdminError(
            'operator class requires strategy operators'
        )
    if not isinstance(functions, list):
        raise PostgreSQLNativeAdminError(
            'operator class requires support functions'
        )
    for operator in operators:
        if not isinstance(operator, Mapping):
            raise PostgreSQLNativeAdminError(
                'strategy operator must be an object'
            )
        strategy = operator.get('strategy')
        if isinstance(strategy, bool) or not isinstance(strategy, int) or (
                strategy < 1 or strategy > 32767):
            raise PostgreSQLNativeAdminError(
                'operator strategy number is invalid'
            )
        reference = _reference(
            operator.get('operator'), 'strategy operator', operator=True
        )
        operands = _type_list(operator.get('operand_types'), 'operand types', optional=True, sizes={2})
        ordering = operator.get('sort_family')
        purpose = (' FOR ORDER BY ' + _reference(ordering, 'sort family')) if ordering else ' FOR SEARCH'
        items.append(f'OPERATOR {strategy} {reference}{operands}{purpose}')
    for function in functions:
        if not isinstance(function, Mapping):
            raise PostgreSQLNativeAdminError(
                'support function must be an object'
            )
        support = function.get('support')
        if isinstance(support, bool) or not isinstance(support, int) or (
                support < 1 or support > 32767):
            raise PostgreSQLNativeAdminError(
                'support function number is invalid'
            )
        reference = _reference(function.get('function'), 'support function')
        operands = _type_list(function.get('operand_types'), 'operand types', optional=True, sizes={1, 2})
        arguments = _type_list(function.get('argument_types'), 'function argument types')
        items.append(f'FUNCTION {support}{operands} {reference}{arguments}')
    return items


def _type_list(value, label, *, optional=False, sizes=None):
    if value is None and optional:
        return ''
    if not isinstance(value, list) or (sizes and len(value) not in sizes):
        raise PostgreSQLNativeAdminError(f'{label} must be a list of catalog type references')
    return ' (' + ', '.join(_type_reference(item, label) for item in value) + ')'


def _database_object(kind, operation, native, draft):
    source = draft if operation == 'create' else native
    if kind == 'access-method':
        name = _name(source.get('name'), 'name')
        identity = _identifier(name, 'name')
        keyword = 'ACCESS METHOD'
        query = ('SELECT oid, amname AS name, amtype AS method_type, '
                 'amhandler::pg_catalog.regproc::text AS handler FROM pg_catalog.pg_am '
                 'WHERE amname=' + _literal(name, 'name'))
    else:
        data_type = _type_reference(source.get('data_type'), 'data type')
        language = _name(source.get('language'), 'language')
        identity = 'FOR ' + data_type + ' LANGUAGE ' + _identifier(language, 'language')
        name = data_type + ' / ' + language
        keyword = 'TRANSFORM'
        query = ('SELECT t.oid, pg_catalog.format_type(t.trftype,NULL) AS data_type, '
                 'l.lanname AS language, t.trffromsql::pg_catalog.regprocedure::text AS from_sql, '
                 't.trftosql::pg_catalog.regprocedure::text AS to_sql '
                 'FROM pg_catalog.pg_transform t JOIN pg_catalog.pg_language l ON l.oid=t.trflang '
                 'WHERE t.trftype=pg_catalog.to_regtype(' + _literal(data_type, 'data type') + ') '
                 'AND l.lanname=' + _literal(language, 'language'))
    if operation == 'inspect':
        return {'statement': query, 'read_only': True}
    if operation == 'drop':
        if _name(draft.get('confirmation'), 'confirmation') != name:
            raise PostgreSQLNativeAdminError('drop confirmation does not match object name')
        cascade = ' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT'
        return {'statement': f'DROP {keyword} {identity}{cascade}', 'read_only': False}
    if kind == 'access-method':
        method_type = draft.get('method_type')
        if method_type not in ('INDEX', 'TABLE'):
            raise PostgreSQLNativeAdminError('access method type must be INDEX or TABLE')
        statement = (f'CREATE ACCESS METHOD {identity} TYPE {method_type} HANDLER '
                     + _reference(draft.get('handler'), 'handler function'))
    else:
        clauses = []
        for key, direction in (('from_sql', 'FROM'), ('to_sql', 'TO')):
            function = draft.get(key)
            if function is None:
                continue
            if not isinstance(function, Mapping):
                raise PostgreSQLNativeAdminError('transform function must be an object')
            reference = _reference(function.get('function'), 'transform function')
            arguments = _type_list(function.get('argument_types'), 'function argument types')
            clauses.append(f'{direction} SQL WITH FUNCTION {reference}{arguments}')
        if not clauses:
            raise PostgreSQLNativeAdminError('transform requires at least one conversion direction')
        replace = 'OR REPLACE ' if _flag(draft, 'replace') else ''
        statement = f'CREATE {replace}TRANSFORM {identity} (' + ', '.join(clauses) + ')'
    return {'statement': statement, 'read_only': False}


def compile_native_admin(request: Mapping[str, Any]) -> dict[str, Any]:
    """Compile one exact PostgreSQL provider-native administration action."""
    kind = request.get('resource_kind')
    operation = request.get('operation_id')
    if kind not in POSTGRESQL_NATIVE_FORM_KINDS:
        raise PostgreSQLNativeAdminError(
            'operation is owned by the preserved PostgreSQL UI'
        )
    if operation not in POSTGRESQL_ADMIN_OPERATIONS[kind]:
        raise PostgreSQLNativeAdminError(
            'PostgreSQL native administration operation is unavailable'
        )
    draft = request.get('draft') or {}
    if not isinstance(draft, Mapping):
        raise PostgreSQLNativeAdminError('PostgreSQL draft is invalid')
    native = _native_target(request)
    if kind == 'large-object':
        from .large_objects import compile_operation
        return compile_operation(operation, native, draft)
    if kind == 'operator':
        return _operator_admin(operation, native, draft)
    if kind == 'aggregate':
        return _aggregate_admin(operation, native, draft)
    if kind in {'access-method', 'transform'}:
        return _database_object(kind, operation, native, draft)
    schema, name = _native_identity(
        native, draft, creating=operation == 'create'
    )
    qualified_name = _qualified(schema, name)
    if operation == 'inspect':
        queries = {
            'conversion': (
                'SELECT n.nspname AS schema, c.conname AS name, '
                'pg_encoding_to_char(c.conforencoding) AS source_encoding, '
                'pg_encoding_to_char(c.contoencoding) AS target_encoding, '
                'c.conproc::regproc::text AS function, c.condefault '
                'AS is_default FROM pg_conversion c JOIN pg_namespace n '
                'ON n.oid=c.connamespace WHERE n.nspname={schema} '
                'AND c.conname={name}'
            ),
            'operator-class': (
                'SELECT n.nspname AS schema, c.opcname AS name, '
                'a.amname AS index_method, c.opcintype::regtype::text '
                'AS data_type, c.opcdefault AS is_default '
                'FROM pg_opclass c JOIN pg_namespace n '
                'ON n.oid=c.opcnamespace JOIN pg_am a '
                'ON a.oid=c.opcmethod WHERE n.nspname={schema} '
                'AND c.opcname={name}'
            ),
            'operator-family': (
                'SELECT n.nspname AS schema, f.opfname AS name, '
                'a.amname AS index_method FROM pg_opfamily f '
                'JOIN pg_namespace n ON n.oid=f.opfnamespace '
                'JOIN pg_am a ON a.oid=f.opfmethod '
                'WHERE n.nspname={schema} AND f.opfname={name}'
            ),
        }
        statement = queries[kind].format(
                schema=_literal(schema, 'schema'),
                name=_literal(name, 'name'),
            )
        if kind in {'operator-class', 'operator-family'}:
            statement += ' AND a.amname=' + _literal(native.get('index_method'), 'index access method')
        return {
            'statement': statement,
            'read_only': True,
        }
    if operation == 'drop':
        confirmation = _name(
            draft.get('confirmation'), 'confirmation'
        )
        if confirmation != name:
            raise PostgreSQLNativeAdminError(
                'drop confirmation does not match object name'
            )
        keyword = {
            'conversion': 'CONVERSION',
            'operator-class': 'OPERATOR CLASS',
            'operator-family': 'OPERATOR FAMILY',
        }[kind]
        using = ''
        if kind in {'operator-class', 'operator-family'}:
            using = ' USING ' + _reference(
                native.get('index_method'), 'index access method'
            )
        cascade = ' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT'
        return {
            'statement': f'DROP {keyword} {qualified_name}{using}{cascade}',
            'read_only': False,
        }
    if operation == 'alter':
        return {
            'statement': _alter_statement(
                kind, qualified_name, draft, native
            ),
            'read_only': False,
        }
    if kind == 'conversion':
        default = 'DEFAULT ' if _flag(draft, 'default') else ''
        statement = (
            f'CREATE {default}CONVERSION {qualified_name} FOR '
            f'{_literal(draft.get("source_encoding"), "source encoding")} '
            'TO '
            f'{_literal(draft.get("target_encoding"), "target encoding")} '
            f'FROM {_reference(draft.get("function"), "function")}'
        )
    elif kind == 'operator-family':
        method = _reference(draft.get('index_method'), 'index access method')
        statement = f'CREATE OPERATOR FAMILY {qualified_name} USING {method}'
    else:
        method = _reference(draft.get('index_method'), 'index access method')
        data_type = _type_reference(draft.get('data_type'), 'data type')
        default = 'DEFAULT ' if _flag(draft, 'default') else ''
        family = draft.get('family')
        family_clause = '' if not family else (
            f' FAMILY {_reference(family, "operator family")}'
        )
        storage = draft.get('storage_type')
        items = _operator_class_items(draft)
        if storage:
            items.append(f'STORAGE {_type_reference(storage, "storage type")}')
        if not items:
            raise PostgreSQLNativeAdminError('operator class requires at least one member')
        statement = (
            f'CREATE OPERATOR CLASS {qualified_name} {default}'
            f'FOR TYPE {data_type} USING {method}{family_clause} AS ' +
            ', '.join(items)
        )
    return {'statement': statement, 'read_only': False}


def _operator_symbol(value):
    value = _name(value, 'operator symbol')
    if (len(value) > 63 or not re.fullmatch(r'[+\-*/<>=~!@#%^&|`?]+', value)
            or '--' in value or '/*' in value or value in {'=>', '!='}
            or (len(value) > 1 and value[-1] in '+-' and not re.search(r'[~!@#%^&|`?]', value))):
        raise PostgreSQLNativeAdminError('Invalid native operator symbol; use <> rather than !=')
    return value


def _operator_options(values, *, creating=False):
    if not isinstance(values, Mapping) or set(values) - {'commutator', 'negator', 'restrict', 'join', 'hashes', 'merges'}:
        raise PostgreSQLNativeAdminError('Invalid operator optimization options')
    clauses = []
    for key, value in values.items():
        if key in {'hashes', 'merges'}:
            if type(value) is not bool or (not creating and not value):
                raise PostgreSQLNativeAdminError('ALTER cannot unset operator hash or merge support')
            if value:
                clauses.append(key.upper())
        elif value is None and key in {'restrict', 'join'} and not creating:
            clauses.append(key.upper() + ' = NONE')
        else:
            reference = _reference(value, key, operator=key in {'commutator', 'negator'})
            if key in {'commutator', 'negator'}:
                reference = 'OPERATOR(' + reference + ')'
            clauses.append(key.upper() + ' = ' + reference)
    return clauses


def _operator_admin(operation, native, draft):
    source = draft if operation == 'create' else native
    name = _operator_symbol(source.get('name'))
    schema = _name(source.get('schema'), 'schema')
    qualified = _identifier(schema, 'schema') + '.' + name
    right = _type_reference(source.get('right_type'), 'right operand type')
    left_value = source.get('left_type')
    if left_value == '':
        left_value = None
    left = 'NONE' if left_value is None else _type_reference(left_value, 'left operand type')
    identity = qualified + ' (' + left + ', ' + right + ')'
    if operation == 'inspect':
        left_test = 'c.oprleft=0' if left_value is None else 'c.oprleft=pg_catalog.to_regtype(' + _literal(left, 'left operand') + ')'
        statement = ('SELECT c.*, pg_catalog.obj_description(c.oid,\'pg_operator\') AS comment '
                     'FROM pg_catalog.pg_operator c JOIN pg_catalog.pg_namespace n ON n.oid=c.oprnamespace '
                     'WHERE n.nspname=' + _literal(schema, 'schema') + ' AND c.oprname=' + _literal(name, 'name') +
                     ' AND ' + left_test + ' AND c.oprright=pg_catalog.to_regtype(' + _literal(right, 'right operand') + ')')
    elif operation == 'create':
        clauses = ['FUNCTION = ' + _reference(draft.get('function'), 'operator function')]
        if left_value is not None:
            clauses.append('LEFTARG = ' + left)
        clauses.append('RIGHTARG = ' + right)
        clauses.extend(_operator_options(draft.get('options', {}), creating=True))
        statement = 'CREATE OPERATOR ' + qualified + ' (' + ', '.join(clauses) + ')'
    elif operation == 'drop':
        if draft.get('confirmation') != name:
            raise PostgreSQLNativeAdminError('drop confirmation does not match object name')
        statement = 'DROP OPERATOR ' + identity + (' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT')
    else:
        action = draft.get('action')
        if action in {'owner', 'schema'}:
            statement = 'ALTER OPERATOR ' + identity + (' OWNER TO ' if action == 'owner' else ' SET SCHEMA ') + _identifier(draft.get('value'), action)
        elif action == 'comment':
            value = draft.get('value')
            statement = 'COMMENT ON OPERATOR ' + identity + ' IS ' + ('NULL' if value is None or value == '' else _literal(value, 'comment'))
        elif action == 'options':
            clauses = _operator_options(draft.get('options'))
            if not clauses:
                raise PostgreSQLNativeAdminError('Select at least one operator option')
            statement = 'ALTER OPERATOR ' + identity + ' SET (' + ', '.join(clauses) + ')'
        else:
            raise PostgreSQLNativeAdminError('Unsupported native operator alteration')
    return {'statement': statement, 'read_only': operation == 'inspect'}


def _aggregate_admin(operation, native, draft):
    from pglast import parse_sql, ast
    from pglast.stream import RawStream
    source = draft if operation == 'create' else native
    schema, name = _native_identity(native, draft, creating=operation == 'create')
    qualified = _qualified(schema, name)
    if operation == 'create':
        statement = _required_text(draft.get('definition'), 'aggregate definition')
        if len(statement.encode('utf8')) > 2 * 1024 * 1024:
            raise PostgreSQLNativeAdminError('Aggregate definition exceeds 2 MiB')
        replace = _flag(draft, 'replace')
        try:
            parsed = parse_sql(statement)
            node = parsed[0].stmt
            if (len(parsed) != 1 or not isinstance(node, ast.DefineStmt) or
                    node.kind.name != 'OBJECT_AGGREGATE' or node.if_not_exists or
                    bool(node.replace) != replace or [x.sval for x in node.defnames] != [schema, name]):
                raise ValueError()
        except Exception:
            raise PostgreSQLNativeAdminError('Definition must create exactly the qualified aggregate with the selected replacement choice') from None
    else:
        arguments = source.get('identity_arguments')
        if not isinstance(arguments, str) or '\x00' in arguments or len(arguments.encode('utf8')) > 65536:
            raise PostgreSQLNativeAdminError('Native aggregate signature is unavailable')
        identity = qualified + ' (' + (arguments or '*') + ')'
        if native.get('sql_identity') is not None:
            identity = _required_text(native['sql_identity'], 'native aggregate identity')
            if len(identity.encode('utf8')) > 65536:
                raise PostgreSQLNativeAdminError('Native aggregate identity exceeds 64 KiB')
            if not arguments and identity.endswith('()'):
                identity = identity[:-2] + '(*)'
        try:
            parsed = parse_sql('DROP AGGREGATE ' + identity)
            node = parsed[0].stmt
            if (len(parsed) != 1 or not isinstance(node, ast.DropStmt) or node.removeType.name != 'OBJECT_AGGREGATE'
                    or node.missing_ok or node.behavior.name != 'DROP_RESTRICT' or len(node.objects) != 1
                    or [x.sval for x in node.objects[0].objname] != [schema, name]):
                raise ValueError()
        except Exception:
            raise PostgreSQLNativeAdminError('Native aggregate signature is invalid') from None
        identity = RawStream()(node).removeprefix('DROP AGGREGATE ')
        if operation == 'inspect':
            oid = native.get('oid')
            if type(oid) is not int or not 0 < oid <= 4294967295:
                raise PostgreSQLNativeAdminError('Native aggregate OID is unavailable')
            statement = ('SELECT p.*, to_jsonb(a) AS aggregate, pg_catalog.obj_description(p.oid,\'pg_proc\') AS comment '
                         'FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_aggregate a ON a.aggfnoid=p.oid WHERE p.oid=' + str(oid))
        elif operation == 'drop':
            if draft.get('confirmation') != name:
                raise PostgreSQLNativeAdminError('drop confirmation does not match object name')
            statement = 'DROP AGGREGATE ' + identity + (' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT')
        else:
            action = draft.get('action')
            if action == 'comment':
                value = draft.get('value')
                statement = 'COMMENT ON AGGREGATE ' + identity + ' IS ' + ('NULL' if value is None or value == '' else _literal(value, 'comment'))
            elif action in {'owner', 'schema', 'rename'}:
                clause = {'owner': ' OWNER TO ', 'schema': ' SET SCHEMA ', 'rename': ' RENAME TO '}[action]
                statement = 'ALTER AGGREGATE ' + identity + clause + _identifier(draft.get('value'), action)
            else:
                raise PostgreSQLNativeAdminError('Unsupported native aggregate alteration')
    return {'statement': statement, 'read_only': operation == 'inspect'}
