"""Exact native planning, independent changes, conflicts and no implicit DDL."""
from copy import deepcopy

import pytest

from tools.tests.test_firebird_catalog_export import export, resource, service
from pgadmin.cdeadmin.providers.firebird.identity import catalog_resource_id
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceError


def obj(kind, name, **native):
    row = resource(name, kind, **native)
    row['resource_id'] = catalog_resource_id(kind, [], name)
    return row


def source(rows):
    return export([obj('server', 'Firebird', version='5.0.4.1812'),
                   obj('database', 'database', sql_dialect='3'), *rows])['snapshot']['files']['catalog.ddn']


def document(rows):
    return read_catalog(source(rows))


def seq(name='S', **values):
    return obj('sequence', name, **{'initial_value': '9007199254740993', 'increment': 1,
                                  'description': None, **values})


def test_create_generates_native_sql_not_embedded_text_and_preserves_quotes():
    base = document([])
    desired = document([seq('S:ü"'), obj('exception', 'E"', message="Don't; DROP TABLE X", description='comment')])
    desired['rows']['exception:E"']['native']['ddl'] = 'DROP DATABASE'
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready'
    assert 'START WITH 9007199254740993 INCREMENT BY 1' in plan['script']
    assert '"S:ü"""' in plan['script']
    assert "CREATE EXCEPTION \"E\"\"\" 'Don''t; DROP TABLE X'" in plan['script']
    assert 'DROP DATABASE' not in plan['script']
    assert plan['apply_available'] is False
    assert all(item['before'] is None for item in plan['operations'])
    assert all(item['source_location']['unit'] == 'utf16-code-units' for item in plan['operations'])


def test_three_way_merges_independent_changes_and_preserves_sequence_position():
    base = document([seq()])
    desired = document([seq(increment=-3)])
    current = document([seq(description='external comment', state={'current': '123456'})])
    plan = build_plan(base, desired, current)
    assert plan['status'] == 'review-ready'
    assert plan['operations'][0]['statements'] == ['ALTER SEQUENCE "S" INCREMENT BY -3']
    assert plan['operations'][0]['after']['description'] == 'external comment'
    assert 'RESTART' not in plan['script'] and 'SET GENERATOR' not in plan['script']
    assert plan['statistics']['preserved_live_changes'] == 1


def test_conflicting_changes_block_all_script_output_and_converged_changes_are_noop():
    base, desired = document([seq()]), document([seq(increment=2)])
    plan = build_plan(base, desired, document([seq(increment=3)]))
    assert plan['status'] == 'blocked' and plan['script'] is None
    assert plan['blockers'][0]['fields'] == ['increment']
    assert build_plan(base, desired, desired)['status'] == 'no-op'
    # Diagram labels and equivalent integer spellings are not schema changes.
    alternate = document([seq(initial_value='+09007199254740993')])
    alternate['rows']['sequence:S']['name'] = 'Pretty diagram label'
    assert build_plan(base, alternate, base)['status'] == 'no-op'


def test_missing_objects_are_not_drop_and_external_additions_are_not_create():
    base, empty = document([seq()]), document([])
    for documents in ((base, empty, base), (empty, base, base),
                      (base, document([seq(increment=2)]), empty)):
        plan = build_plan(*documents)
        assert plan['status'] == 'blocked' and plan['script'] is None


@pytest.mark.parametrize('changes', [
    {'initial_value': '4'}, {'increment': 0}, {'increment': 2147483648},
    {'owner': 'OTHER'}, {'privileges': [{'privilege': 'G'}]}, {'unknown': 42},
])
def test_non_equivalent_or_unsupported_edits_block(changes):
    base = document([seq()])
    plan = build_plan(base, document([seq(**changes)]), base)
    assert plan['status'] == 'blocked' and plan['script'] is None


def test_unsupported_kind_edits_and_inconsistent_identity_block():
    table = obj('table', 'T', columns=[{'name': 'A'}])
    base = document([table, seq()])
    desired = deepcopy(base)
    desired['rows']['table:T']['native']['columns'][0]['name'] = 'B'
    desired['rows']['sequence:S']['path'] = ['OTHER']
    assert len(build_plan(base, desired, base)['blockers']) == 2


def test_exception_alter_and_comment_removal_do_not_recreate():
    base = document([obj('exception', 'E', message='old', description='comment')])
    desired = document([obj('exception', 'E', message='new', description=None)])
    plan = build_plan(base, desired, base)
    assert plan['operations'][0]['statements'] == ["ALTER EXCEPTION \"E\" 'new'", 'COMMENT ON EXCEPTION "E" IS NULL']
    assert 'RECREATE' not in plan['script']


def test_version_dialect_and_cross_database_scope_are_checked():
    base = document([seq()])
    for field, value in [('version', '4.0.0'), ('sql_dialect', '1')]:
        current = deepcopy(base)
        identity = 'server:Firebird' if field == 'version' else 'database:database'
        current['rows'][identity]['native'][field] = value
        with pytest.raises(ValueError):
            build_plan(base, base, current)
    other = deepcopy(base)
    other['provenance']['database_target_id'] = 'other'
    with pytest.raises(ValueError):
        build_plan(base, other, base)


def test_host_binds_target_and_never_calls_mutation_path():
    value, server = service()
    rows = [obj('server', 'Firebird', version='5.0.4'), obj('database', 'database', sql_dialect='3'), seq()]
    value.resource_service.list_page.return_value.to_dict.return_value['items'] = rows
    capture = value.export_firebird_catalog(server, {'generation': 'current'})
    source_text = capture['snapshot']['files']['catalog.ddn']
    plan = value.plan_firebird_schema(server, {'generation': 'current', 'baseline': source_text, 'desired': source_text})
    assert plan['status'] == 'no-op'
    assert plan['target']['database_target_id'] == 'target'
    value.resource_service.invalidate.assert_not_called()
    with pytest.raises(ProviderWorkspaceError):
        value.plan_firebird_schema(server, {'generation': 'current', 'baseline': source_text, 'desired': source_text, 'sql': 'DROP DATABASE'})


def test_empty_comments_are_native_null_in_the_schema_model():
    base = document([seq(description='old')])
    desired = document([seq(description='')])
    current = document([seq(description=None)])
    plan = build_plan(base, desired, base)
    assert plan['operations'][0]['statements'] == ['COMMENT ON SEQUENCE "S" IS NULL']
    assert build_plan(base, desired, current)['status'] == 'no-op'
    assert desired['rows']['sequence:S']['native']['description'] == ''


def test_stored_dialect_one_generates_native_identifiers_without_case_conversion():
    base = document([])
    base['rows']['database:database']['native']['sql_dialect'] = '1'
    desired = deepcopy(base)
    new = read_catalog(source([obj('exception', 'UPPER_EXCEPTION', message='native', description=None)]))['rows']['exception:UPPER_EXCEPTION']
    desired['rows']['exception:UPPER_EXCEPTION'] = new
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready'
    assert plan['sql_dialect'] == 1
    assert "CREATE EXCEPTION UPPER_EXCEPTION 'native'" in plan['script']
    desired['rows']['exception:UPPER_EXCEPTION']['name'] = 'MixedCase'
    desired['rows']['exception:UPPER_EXCEPTION']['path'] = ['MixedCase']
    assert build_plan(base, desired, base)['status'] == 'blocked'
