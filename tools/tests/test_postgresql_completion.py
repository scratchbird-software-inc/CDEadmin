"""The shared completion action retains the authorized session and exact source."""
from unittest.mock import Mock
import pytest
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService, ProviderWorkspaceError


def service():
    result = object.__new__(ProviderWorkspaceService)
    result.endpoint_service = Mock()
    result.endpoint_service.workspace.return_value = ('owned-context', {}, None)
    result.studio_service = Mock()
    return result


def test_completion_dispatches_only_to_the_owned_language_session():
    host = service()
    host.language_tool_action('server', 'source_complete', {'database_target_id': 'postgresql-database:42',
        'session_id': 'retained', 'source':'SELECT 1', 'source_before_cursor':'SELECT '})
    host.endpoint_service.workspace.assert_called_once_with('server', database_target_id='postgresql-database:42')
    host.studio_service.complete.assert_called_once_with('owned-context', 'retained', 'SELECT 1', 'SELECT ')
    host.studio_service.execute.assert_not_called()


@pytest.mark.parametrize('source,prefix', [('SELECT 1','other'), (None,''), ('SELECT 1',None), ('x'*1048577,'')])
def test_invalid_completion_source_never_reaches_the_provider(source, prefix):
    host = service()
    with pytest.raises(ProviderWorkspaceError):
        host.language_tool_action('server', 'source_complete', {'source':source,'source_before_cursor':prefix})
    host.studio_service.complete.assert_not_called()


def test_native_completion_uses_the_supplied_owned_manager():
    from types import SimpleNamespace
    from unittest.mock import patch
    from pgadmin.utils.sqlautocomplete.autocomplete import SQLAutoComplete
    connection = Mock()
    connection.connected.return_value = False
    with patch('pgadmin.utils.sqlautocomplete.autocomplete.get_driver') as fallback:
        completion = SQLAutoComplete(sid=7, conn=connection, manager=SimpleNamespace(version=180003))
    fallback.assert_not_called()
    assert completion.sql_path == 'sqlautocomplete/sql/#180003#'


def test_native_completion_does_not_require_legacy_ui_preference_registration():
    from types import SimpleNamespace
    from unittest.mock import patch
    from pgadmin.utils.sqlautocomplete.autocomplete import SQLAutoComplete
    connection = Mock()
    connection.connected.return_value = True
    connection.execute_dict.return_value = (True, {'rows': []})
    with patch('pgadmin.utils.sqlautocomplete.autocomplete.Preferences.module', return_value=None), \
            patch('pgadmin.utils.sqlautocomplete.autocomplete.render_template', return_value='SELECT 1') as render:
        SQLAutoComplete(sid=7, conn=connection, manager=SimpleNamespace(version=180003))
    assert any(call.kwargs.get('upper_case') is True for call in render.call_args_list)


def test_native_argument_arrays_and_complex_defaults_are_not_split_as_csv():
    from pgadmin.utils.sqlautocomplete.autocomplete import _native_argument_array
    from pgadmin.utils.sqlautocomplete.parseutils.meta import parse_defaults
    assert _native_argument_array(['name,with,commas','plain']) == ['name,with,commas','plain']
    assert _native_argument_array('{"name,with,commas",plain}') == ['name,with,commas','plain']
    assert _native_argument_array('{}') == []
    assert _native_argument_array(None) is None
    defaults = tuple(parse_defaults("ARRAY[1,2], jsonb_build_object('a',1,'b',2), 'literal,comma'::text"))
    assert len(defaults) == 3
    assert defaults[0] == 'ARRAY[1, 2]'
    assert defaults[2] == "CAST('literal,comma' AS text)"


def test_schema_completion_quotes_explicit_names_and_search_path_entries():
    from pgadmin.utils.sqlautocomplete.autocomplete import SQLAutoComplete
    from pglast import parse_sql
    completion = object.__new__(SQLAutoComplete)
    value = "native'\\scope"
    completion.search_path = [value, 'public']
    for schema in (None, value):
        query = 'SELECT 1 WHERE true OR current_schema IN (' + completion._schema_literals(schema) + ')'
        parsed = parse_sql(query)
        assert len(parsed) == 1
        constants = parsed[0].stmt.whereClause.args[1].rexpr
        assert constants[0].val.sval == value


def test_search_path_filters_absent_object_categories_and_quoted_schema_keys():
    from pgadmin.utils.sqlautocomplete.autocomplete import SQLAutoComplete
    completion = object.__new__(SQLAutoComplete)
    completion.search_path = ["native scope", "empty_schema", "public"]
    completion.search_path_filter = True
    completion.escape_name = lambda name: '\"' + name + '\"' if ' ' in name else name
    completion.dbmetadata = {'views': {'public': {}}, 'tables': {'"native scope"': {}}}
    assert completion._get_schemas('views', None) == ['public']
    assert completion._get_schemas('tables', None) == ['"native scope"']
    assert completion._maybe_schema('"native scope"', None) is None


def test_native_identifier_completion_doubles_embedded_quotes():
    import re
    from pgadmin.utils.sqlautocomplete.autocomplete import SQLAutoComplete
    completion = object.__new__(SQLAutoComplete)
    completion.name_pattern = re.compile(r'^[a-z_][a-z_0-9]*$')
    completion.reserved_words = []
    completion.functions = []
    name = 'native"scope'
    quoted = completion.escape_name(name)
    assert quoted == '"native""scope"'
    assert completion.unescape_name(quoted) == name


@pytest.mark.parametrize('parameters',[{'value':42},[42],None,'{}'])
def test_script_preparation_refuses_bindings_before_history_or_execution(parameters):
    host=service()
    host._record_query_request=Mock()
    with pytest.raises(ProviderWorkspaceError,match='empty parameter'):
        host.language_tool_action('server','native_script_prepare',{'parameters':parameters,'source':'SELECT 1'})
    host._record_query_request.assert_not_called()
    host.studio_service.scripts.prepare.assert_not_called()


@pytest.mark.parametrize('parameters',[{},[]])
def test_empty_script_bindings_reach_the_owned_script_service(parameters):
    host=service()
    host._record_query_request=lambda *args:args[-1]()
    host.language_tool_action('server','native_script_prepare',{'parameters':parameters,'source':'SELECT 1','session_id':'owned'})
    host.studio_service.scripts.prepare.assert_called_once_with('owned-context','owned','SELECT 1')


def test_search_path_update_preserves_raw_names_and_schema_literals():
    import re
    from pglast import parse_sql
    from pgadmin.utils.sqlautocomplete.autocomplete import SQLAutoComplete
    completion = object.__new__(SQLAutoComplete)
    completion.name_pattern = re.compile(r'^[a-z_][a-z_0-9]*$')
    completion.reserved_words = []
    completion.functions = []
    name = "native'\\scope\"quoted"
    path = [name, 'public']
    completion.set_search_path(path)
    path.clear()
    assert completion.search_path == [name, 'public']
    literal = completion.escape_schema(completion.escape_name(name))
    assert parse_sql('SELECT '+literal)[0].stmt.targetList[0].val.val.sval == name
