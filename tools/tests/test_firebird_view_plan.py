from copy import deepcopy
import pytest
from tools.tests.test_firebird_schema_plan import document, obj
from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan


def view(name='V', definition='SELECT 1 FROM RDB$DATABASE', **extra):
    return obj('view', name, relation_type=1, definition=definition,
               columns=[{'name': 'Exact"Name', 'position': 0}], **extra)


def test_create_and_alter_preserve_names_and_do_not_recreate():
    empty = document([])
    base = document([view()])
    create = build_plan(empty, base, empty)
    assert create['status'] == 'review-ready'
    assert 'CREATE VIEW "V" ("Exact""Name")' in create['script']
    desired = document([view(definition='SELECT 2 FROM RDB$DATABASE', description='changed')])
    change = build_plan(base, desired, base)
    assert change['status'] == 'review-ready'
    assert 'ALTER VIEW "V"' in change['script'] and 'RECREATE' not in change['script']
    assert set(change['operations'][0]['native_preconditions']) == {'view:V'}
    assert "COMMENT ON VIEW \"V\" IS 'changed'" in change['script']


@pytest.mark.parametrize('definition', ['SELECT 1 FROM RDB$DATABASE; DROP TABLE T', "SELECT 'unterminated", 'SELECT (1', 'SELECT 1 /*'])
def test_script_boundaries_refused(definition):
    empty = document([])
    assert build_plan(empty, document([view(definition=definition)]), empty)['status'] == 'blocked'


def test_quoted_semicolon_and_comments_are_native_source():
    empty = document([])
    desired = document([view(definition="SELECT q'{;}' FROM RDB$DATABASE -- ;")])
    assert build_plan(empty, desired, empty)['status'] == 'review-ready'


def test_column_edits_conflicts_and_unordered_multi_create_refused():
    base = document([view()]); changed = deepcopy(base)
    changed['rows']['view:V']['native']['columns'][0]['name'] = 'OTHER'
    assert build_plan(base, changed, base)['status'] == 'blocked'
    a = document([view(definition='SELECT 2 FROM RDB$DATABASE')])
    b = document([view(definition='SELECT 3 FROM RDB$DATABASE')])
    assert build_plan(base, a, b)['status'] == 'blocked'
    empty = document([])
    assert build_plan(empty, document([view('A'), view('B')]), empty)['status'] == 'blocked'


def test_whole_catalog_guards_detect_new_query_dependency_change():
    base = document([view(), obj('table', 'T', description='old')])
    desired = deepcopy(base); desired['rows']['view:V']['native']['definition'] = 'SELECT 2 FROM RDB$DATABASE'
    initial = build_plan(base, desired, base)
    current = deepcopy(base); current['rows']['table:T']['native']['description'] = 'new'
    fresh = build_plan(base, desired, current)
    assert initial['execution_sha256'] != fresh['execution_sha256']
