"""Native MySQL literal boundaries preserve body text and script ownership."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import test_cdeadmin_provider_navigator  # noqa: F401
from pgadmin.cdeadmin.data_studio.mysql_quoting import available, marker_at, end_of_quote
from pgadmin.cdeadmin.providers.native_editor import mysql_bind_markers, validate_mysql
from pgadmin.cdeadmin.data_studio.language_tools import analyze


@pytest.mark.parametrize('tag', ['', 'tag', '123', '雪', '🦆', '_tag'])
def test_qualified_literal_boundaries_preserve_inner_quotes_comments_markers_and_delimiters(tag):
    marker = '$' + tag + '$'
    body = "/* %s */ export const value = 'x; \\\"'; // %(name)s\nDELIMITER //\n"
    source = 'CREATE LIBRARY lib LANGUAGE JAVASCRIPT AS ' + marker + body + marker
    start = source.index(marker)
    assert marker_at(source, start) == marker
    assert end_of_quote(source, start, marker) == len(source)
    assert mysql_bind_markers(source + ', %s', set(), dollar_quotes=True) == source + ', ? '
    framed = analyze(source + '; SELECT 2;', 'mysql-sql', script=True,
                     settings={'mysql_dollar_quotes': True})
    assert framed['script_ready'] and len(framed['statements']) == 2, framed
    assert framed['statements'][0]['source'] == source


def test_native_consumed_dollar_mismatch_does_not_start_an_overlapping_delimiter():
    marker = '$tag$'; body = 'export const x = "$$tag$";'
    source = marker + body + marker
    assert end_of_quote(source, 0, marker) == len(source)
    assert end_of_quote('$tag$"$$tag$";', 0, marker) is None


@pytest.mark.parametrize('source,position', [('name$tag$', 4), ('123$tag$', 3), ('db.$tag$', 3)])
def test_identifier_dollars_do_not_start_literals(source, position):
    assert marker_at(source, position) is None


def test_unknown_native_version_does_not_approve_dollar_quoted_script():
    assert available('9.7.0') and available('9.7.0-commercial')
    assert not available('9.7.1') and not available('12.2.2-MariaDB')
    checked = analyze('CREATE LIBRARY lib LANGUAGE JAVASCRIPT AS $$export const x=1;$$;', 'mysql-sql', script=True)
    assert not checked['script_ready']
    assert checked['diagnostics'][0]['code'] == 'NATIVE_VERSION_REQUIRED'


def test_unterminated_literal_keeps_all_inner_markers_and_refuses_script_dispatch():
    source = 'CREATE LIBRARY lib LANGUAGE JAVASCRIPT AS $tag$// %s\nexport const x=1;'
    assert mysql_bind_markers(source, set(), dollar_quotes=True) == source
    checked = analyze(source, 'mysql-sql', script=True, settings={'mysql_dollar_quotes': True})
    assert not checked['script_ready'] and checked['diagnostics'][0]['code'] == 'UNTERMINATED'


def test_custom_dollar_client_delimiter_retains_existing_sql_routine_framing():
    source = 'DELIMITER $$\nCREATE PROCEDURE p() BEGIN SELECT 1; END $$\nDELIMITER ;\nSELECT 2;'
    checked = analyze(source, 'mysql-sql', script=True, settings={'mysql_dollar_quotes': True})
    assert checked['script_ready'] and len(checked['statements']) == 2, checked


def test_bound_native_library_source_is_not_rewritten_inside_dollar_quoted_body():
    source = 'CREATE LIBRARY lib LANGUAGE JAVASCRIPT AS $tag$// %s %(value)s\nexport const x="$$tag$";$tag$'
    cursor = Mock(); cursor.fetchone.return_value = ('9.7.0', '', 60)
    handle = SimpleNamespace(cursor=lambda: cursor)
    checked = validate_mysql(SimpleNamespace(_uncertain_sessions=set()), handle, source, 'mysql')
    assert checked['grammar_valid'] is True
    bindings = [call for call in cursor.execute.call_args_list if 'CONVERT(' in call.args[0]]
    assert bindings[0].args[1] == (source.encode(),)
    assert not any(call.args[0].startswith(('EXECUTE ', 'COMMIT', 'ROLLBACK')) for call in cursor.execute.call_args_list)
