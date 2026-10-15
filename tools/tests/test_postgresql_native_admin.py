"""Native advanced-object syntax retains signatures and catalog identity."""
import pytest
from pgadmin.cdeadmin.providers.postgresql.native_admin import (
    compile_native_admin, PostgreSQLNativeAdminError, _reference, _literal,
)


def request(**draft):
    return {'resource_kind': 'operator-class', 'operation_id': 'create', 'draft': {
        'schema': 'Mixed schema', 'name': 'é class', 'data_type': 'pg_catalog.int4',
        'index_method': 'btree', 'operators': [{'strategy': 1, 'operator': 'pg_catalog.<',
            'operand_types': ['pg_catalog.int4', 'pg_catalog.int4']}],
        'functions': [{'support': 1, 'function': 'pg_catalog.btint4cmp',
            'argument_types': ['pg_catalog.int4', 'pg_catalog.int4']}], **draft}}


def test_operator_class_signatures_parse_as_one_native_statement():
    from pglast import parse_sql
    statement = compile_native_admin(request())['statement']
    assert 'FUNCTION 1 pg_catalog.btint4cmp (pg_catalog.int4, pg_catalog.int4)' in statement
    assert 'OPERATOR 1 pg_catalog.< (pg_catalog.int4, pg_catalog.int4) FOR SEARCH' in statement
    assert len(parse_sql(statement)) == 1


def test_method_specific_members_can_omit_operators():
    from pglast import parse_sql
    assert len(parse_sql(compile_native_admin(request(operators=[]))['statement'])) == 1
    with pytest.raises(PostgreSQLNativeAdminError, match='at least one member'):
        compile_native_admin(request(operators=[], functions=[]))


def test_support_function_requires_explicit_arguments():
    with pytest.raises(PostgreSQLNativeAdminError, match='function argument types'):
        compile_native_admin(request(functions=[{'support': 1, 'function': 'pg_catalog.btint4cmp'}]))


@pytest.mark.parametrize('reference', ['"Quoted schema"."Odd""name"', 'école.type', 'pg_catalog.int4[]'])
def test_native_quoted_unicode_references(reference):
    assert _reference(reference, 'reference') == reference


@pytest.mark.parametrize('reference', ['public.name;SELECT 1', 'public.name--', 'public.name/*', '"unterminated', 'x.y.z'])
def test_reference_injection_refused(reference):
    with pytest.raises(PostgreSQLNativeAdminError):
        _reference(reference, 'reference')


def test_literals_do_not_depend_on_session_backslash_mode():
    assert _literal("a\\'b", 'literal') == "E'a\\\\''b'"


def test_inspection_binds_index_method():
    for kind in ['operator-class', 'operator-family']:
        statement = compile_native_admin({'resource_kind': kind, 'operation_id': 'inspect',
            'target_resource': {'extensions': {'postgresql': {'native': {
                'schema': 'public', 'name': 'same', 'index_method': 'hash'}}}}})['statement']
        assert "AND a.amname='hash'" in statement


def test_catalog_names_preserve_leading_trailing_and_only_whitespace():
    native = {'schema': ' schema ', 'name': ' ', 'index_method': 'btree'}
    target = {'extensions': {'postgresql': {'native': native}}}
    created = compile_native_admin({'resource_kind': 'operator-family', 'operation_id': 'create', 'draft': native})
    assert '" schema "." "' in created['statement']
    inspected = compile_native_admin({'resource_kind': 'operator-family', 'operation_id': 'inspect', 'target_resource': target})
    assert "n.nspname=' schema '" in inspected['statement'] and "f.opfname=' '" in inspected['statement']
    renamed = compile_native_admin({'resource_kind': 'operator-family', 'operation_id': 'alter',
        'target_resource': target, 'draft': {'action': 'rename', 'value': ' new '}})
    assert renamed['statement'].endswith('RENAME TO " new "')
    dropped = compile_native_admin({'resource_kind': 'operator-family', 'operation_id': 'drop',
        'target_resource': target, 'draft': {'confirmation': ' '}})
    assert '" schema "." "' in dropped['statement']


@pytest.mark.parametrize('kind,draft,expected', [
    ('access-method', {'name': 'Mixed method', 'method_type': 'INDEX', 'handler': 'pg_catalog.bthandler'}, 'CreateAmStmt'),
    ('access-method', {'name': 'Heap method', 'method_type': 'TABLE', 'handler': 'pg_catalog.heap_tableam_handler'}, 'CreateAmStmt'),
    ('transform', {'data_type': 'pg_catalog.int4', 'language': 'plpython3u', 'replace': True,
        'from_sql': {'function': 'public.from_int', 'argument_types': ['pg_catalog.internal']},
        'to_sql': {'function': 'public.to_int', 'argument_types': ['pg_catalog.internal']}}, 'CreateTransformStmt'),
])
def test_database_object_create_exact_native_ast(kind, draft, expected):
    from pglast import parse_sql
    compiled = compile_native_admin({'resource_kind': kind, 'operation_id': 'create', 'draft': draft})
    parsed = parse_sql(compiled['statement'])
    assert len(parsed) == 1 and type(parsed[0].stmt).__name__ == expected
    assert not compiled['read_only']


@pytest.mark.parametrize('kind,native,confirmation', [
    ('access-method', {'name': ' Mixed method '}, ' Mixed method '),
    ('transform', {'data_type': '"Odd schema"."Odd type"', 'language': 'Odd language'}, '"Odd schema"."Odd type" / Odd language'),
])
def test_database_object_drop_and_inspect_native_identity(kind, native, confirmation):
    from pglast import parse_sql
    request = {'resource_kind': kind, 'target_resource': {'extensions': {'postgresql': {'native': native}}}}
    inspected = compile_native_admin({**request, 'operation_id': 'inspect'})
    assert inspected['read_only'] and len(parse_sql(inspected['statement'])) == 1
    dropped = compile_native_admin({**request, 'operation_id': 'drop', 'draft': {'confirmation': confirmation}})
    assert len(parse_sql(dropped['statement'])) == 1 and dropped['statement'].endswith(' RESTRICT')
    with pytest.raises(PostgreSQLNativeAdminError, match='confirmation'):
        compile_native_admin({**request, 'operation_id': 'drop', 'draft': {'confirmation': 'different'}})
    with pytest.raises(PostgreSQLNativeAdminError, match='unavailable'):
        compile_native_admin({**request, 'operation_id': 'alter'})


def test_transform_requires_direction_and_function_signature():
    request = {'resource_kind': 'transform', 'operation_id': 'create',
               'draft': {'data_type': 'pg_catalog.int4', 'language': 'plpython3u'}}
    with pytest.raises(PostgreSQLNativeAdminError, match='conversion direction'):
        compile_native_admin(request)
    request['draft']['from_sql'] = {'function': 'public.from_int'}
    with pytest.raises(PostgreSQLNativeAdminError, match='argument types'):
        compile_native_admin(request)


@pytest.mark.parametrize('draft', [
    {'action': 'add_members', 'operators': [{'strategy': 1, 'operator': 'pg_catalog.<', 'operand_types': ['pg_catalog.int4', 'pg_catalog.int4']}]},
    {'action': 'drop_members', 'members': [{'kind': 'OPERATOR', 'number': 1, 'operand_types': ['pg_catalog.int4', 'pg_catalog.int4']}]},
])
def test_operator_family_add_remove_preserves_native_member_identity(draft):
    from pglast import parse_sql
    statement = compile_native_admin({'resource_kind': 'operator-family', 'operation_id': 'alter',
        'target_resource': {'extensions': {'postgresql': {'native': {'schema': 'public', 'name': 'family', 'index_method': 'btree'}}}},
        'draft': draft})['statement']
    parsed = parse_sql(statement)
    assert len(parsed) == 1 and type(parsed[0].stmt).__name__ == 'AlterOpFamilyStmt'


def test_operator_family_empty_change_is_refused():
    with pytest.raises(PostgreSQLNativeAdminError, match='at least one member change'):
        compile_native_admin({'resource_kind': 'operator-family', 'operation_id': 'alter',
            'target_resource': {'extensions': {'postgresql': {'native': {'schema': 'public', 'name': 'family', 'index_method': 'btree'}}}},
            'draft': {'action': 'add_members'}})


@pytest.mark.parametrize('value', ['double precision', 'character varying(32)', 'timestamp with time zone', 'numeric(12, 3)[]'])
def test_native_multiword_type_references(value):
    from pgadmin.cdeadmin.providers.postgresql.native_admin import _type_reference
    from pglast import parse_sql
    result = _type_reference(value, 'type')
    assert len(parse_sql('SELECT CAST(NULL AS ' + result + ')')) == 1


@pytest.mark.parametrize('value', ['integer); SELECT 1; --', 'integer) FROM pg_roles --', 'integer) + 1 --', 'integer) AS other --'])
def test_native_type_field_cannot_add_query_structure(value):
    from pgadmin.cdeadmin.providers.postgresql.native_admin import _type_reference
    with pytest.raises(PostgreSQLNativeAdminError):
        _type_reference(value, 'type')


@pytest.mark.parametrize('value', ['false', 'true', 0, 1, None])
def test_native_boolean_options_are_not_truthiness_flags(value):
    with pytest.raises(PostgreSQLNativeAdminError, match='must be boolean'):
        compile_native_admin(request(default=value))


def operator_request(operation='create', **draft):
    native = {'schema': 'Odd schema', 'name': '===', 'left_type': 'pg_catalog.int4', 'right_type': 'pg_catalog.int4'}
    return {'resource_kind': 'operator', 'operation_id': operation,
            'target_resource': {'extensions': {'postgresql': {'native': native}}},
            'draft': {**(dict(native, function='pg_catalog.int4eq') if operation == 'create' else {}), **draft}}


@pytest.mark.parametrize('operation,draft,kind', [
    ('create', {}, 'DefineStmt'),
    ('create', {'left_type': None, 'function': 'pg_catalog.int4abs'}, 'DefineStmt'),
    ('create', {'options': {'hashes': True, 'merges': True, 'restrict': 'pg_catalog.eqsel', 'join': 'pg_catalog.eqjoinsel', 'commutator': 'pg_catalog.='}}, 'DefineStmt'),
    ('alter', {'action': 'owner', 'value': 'Odd owner'}, 'AlterOwnerStmt'),
    ('alter', {'action': 'schema', 'value': 'Next schema'}, 'AlterObjectSchemaStmt'),
    ('alter', {'action': 'comment', 'value': "a\\'b"}, 'CommentStmt'),
    ('alter', {'action': 'comment', 'value': ''}, 'CommentStmt'),
    ('alter', {'action': 'options', 'options': {'restrict': None, 'join': None}}, 'AlterOperatorStmt'),
    ('alter', {'action': 'options', 'options': {'hashes': True, 'commutator': 'pg_catalog.='}}, 'AlterOperatorStmt'),
    ('drop', {'confirmation': '==='}, 'DropStmt'),
    ('inspect', {}, 'SelectStmt'),
])
def test_operator_native_statements(operation, draft, kind):
    from pglast import parse_sql
    compiled = compile_native_admin(operator_request(operation, **draft))
    parsed = parse_sql(compiled['statement'])
    assert len(parsed) == 1 and type(parsed[0].stmt).__name__ == kind
    assert compiled['read_only'] == (operation == 'inspect')


@pytest.mark.parametrize('name', ['x', '!=', '=>', '--', '/*', '++', '*-', '==='*22, 'public.=', '=;SELECT 1'])
def test_operator_invalid_symbol_refused(name):
    with pytest.raises(PostgreSQLNativeAdminError):
        compile_native_admin(operator_request(name=name))


@pytest.mark.parametrize('draft', [
    {'action': 'rename', 'value': '+++'},
    {'action': 'options', 'options': {}},
    {'action': 'options', 'options': {'hashes': False}},
    {'action': 'options', 'options': {'merges': 1}},
    {'action': 'options', 'options': {'unknown': True}},
    {'action': 'options', 'options': {'restrict': 'f;SELECT 1'}},
])
def test_operator_unsupported_alteration_refused(draft):
    with pytest.raises(PostgreSQLNativeAdminError):
        compile_native_admin(operator_request('alter', **draft))


def test_operator_inspection_preserves_overload_and_prefix_identity():
    payload = operator_request('inspect')
    statement = compile_native_admin(payload)['statement']
    assert 'c.oprleft=pg_catalog.to_regtype' in statement
    assert 'c.oprright=pg_catalog.to_regtype' in statement
    payload['target_resource']['extensions']['postgresql']['native']['left_type'] = None
    assert 'c.oprleft=0' in compile_native_admin(payload)['statement']
    with pytest.raises(PostgreSQLNativeAdminError):
        compile_native_admin(operator_request('drop', confirmation='=='))


def aggregate_request(operation='create', *, arguments='integer', **draft):
    native = {'schema': 'Odd schema', 'name': 'sum', 'oid': 12345, 'identity_arguments': arguments}
    return {'resource_kind': 'aggregate', 'operation_id': operation,
            'target_resource': {'extensions': {'postgresql': {'native': native}}},
            'draft': {**({'schema': native['schema'], 'name': native['name'],
                         'definition': 'CREATE AGGREGATE "Odd schema".sum(integer) (SFUNC=int4pl,STYPE=integer)'} if operation == 'create' else {}), **draft}}


@pytest.mark.parametrize('arguments', ['integer', '', 'ORDER BY integer', 'integer ORDER BY integer', 'VARIADIC integer[]'])
@pytest.mark.parametrize('operation,draft,kind', [
    ('drop', {'confirmation': 'sum'}, 'DropStmt'),
    ('alter', {'action': 'rename', 'value': 'New sum'}, 'RenameStmt'),
    ('alter', {'action': 'schema', 'value': 'New schema'}, 'AlterObjectSchemaStmt'),
    ('alter', {'action': 'owner', 'value': 'New owner'}, 'AlterOwnerStmt'),
    ('alter', {'action': 'comment', 'value': 'comment'}, 'CommentStmt'),
    ('inspect', {}, 'SelectStmt'),
])
def test_aggregate_native_signature_variants(arguments, operation, draft, kind):
    from pglast import parse_sql
    parsed = parse_sql(compile_native_admin(aggregate_request(operation, arguments=arguments, **draft))['statement'])
    assert len(parsed) == 1 and type(parsed[0].stmt).__name__ == kind


@pytest.mark.parametrize('signature,options', [
    ('integer', 'SFUNC=int4pl,STYPE=integer,INITCOND=\'0\',PARALLEL=SAFE'),
    ('ORDER BY integer', 'SFUNC=int4pl,STYPE=integer'),
    ('integer ORDER BY integer', 'SFUNC=int4pl,STYPE=integer,HYPOTHETICAL'),
    ('*', 'SFUNC=int8inc,STYPE=bigint'),
])
def test_aggregate_create_complete_native_definition(signature, options):
    from pglast import parse_sql
    text = 'CREATE AGGREGATE "Odd schema".sum(' + signature + ') (' + options + ')'
    result = compile_native_admin(aggregate_request(definition=text))
    assert result['statement'] == text and len(parse_sql(text)) == 1


def test_aggregate_replace_is_an_explicit_matching_choice():
    text = 'CREATE OR REPLACE AGGREGATE "Odd schema".sum(integer) (SFUNC=int4pl,STYPE=integer)'
    with pytest.raises(PostgreSQLNativeAdminError):
        compile_native_admin(aggregate_request(definition=text))
    assert compile_native_admin(aggregate_request(definition=text, replace=True))['statement'] == text


@pytest.mark.parametrize('definition', [
    'CREATE AGGREGATE public.sum(integer) (SFUNC=int4pl,STYPE=integer)',
    'CREATE AGGREGATE "Odd schema".sum(integer) (SFUNC=int4pl,STYPE=integer); SELECT 1',
    'SELECT 1',
])
def test_aggregate_definition_target_and_statement_guard(definition):
    with pytest.raises(PostgreSQLNativeAdminError):
        compile_native_admin(aggregate_request(definition=definition))


@pytest.mark.parametrize('arguments', ['integer) CASCADE --', 'integer); DROP TABLE t; --', 'integer) IS NULL --'])
def test_aggregate_signature_injection_refused(arguments):
    with pytest.raises(PostgreSQLNativeAdminError):
        compile_native_admin(aggregate_request('drop', arguments=arguments, confirmation='sum'))


def test_aggregate_uses_canonical_qualified_identity_and_validates_its_target():
    payload = aggregate_request('drop', arguments='custom', confirmation='sum')
    native = payload['target_resource']['extensions']['postgresql']['native']
    native['sql_identity'] = '"Odd schema".sum("Type schema".custom)'
    assert '"Type schema".custom' in compile_native_admin(payload)['statement']
    native['sql_identity'] = 'public.other(integer)'
    with pytest.raises(PostgreSQLNativeAdminError):
        compile_native_admin(payload)
    native.update(identity_arguments='', sql_identity='"Odd schema".sum()')
    assert '(*)' in compile_native_admin(payload)['statement']
