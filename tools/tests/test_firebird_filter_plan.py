"""BLOB filter declarations preserve exact native metadata and lifecycle."""
from copy import deepcopy

import pytest

from tools.tests.test_firebird_schema_plan import document, obj
from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan


def filter_object(name='F', **native):
    return obj('blob-filter', name, **{'input_subtype': -20, 'output_subtype': -21,
        'module_name': 'not_loaded', 'entrypoint': 'not_invoked', 'description': None, **native})


def catalog(*rows):
    result = document(list(rows))
    result['rows']['database:database']['native']['catalog_observations'] = [
        {'section': 'blob-filter objects', 'available': True}]
    return result


def test_filter_declaration_uses_native_compiler_and_exact_quoting():
    base = catalog()
    desired = catalog(filter_object('F"ü', module_name="file'name", entrypoint="entry'point", description=''))
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    assert plan['operations'][0]['statements'] == [
        'DECLARE FILTER "F""ü" INPUT_TYPE -20 OUTPUT_TYPE -21 ENTRY_POINT \'entry\'\'point\' MODULE_NAME \'file\'\'name\'']
    assert any('native server code' in warning for warning in plan['warnings'])
    assert not plan['apply_available']


def test_filter_comment_preserves_independent_native_definition():
    base = catalog(filter_object(description='old'))
    desired = catalog(filter_object(description=None))
    live = catalog(filter_object(description='old', module_name='live_module'))
    plan = build_plan(base, desired, live)
    assert plan['status'] == 'review-ready', plan['blockers']
    assert plan['operations'][0]['statements'] == ['COMMENT ON FILTER "F" IS NULL']
    assert plan['operations'][0]['after']['module_name'] == 'live_module'


@pytest.mark.parametrize('native', [
    {'input_subtype': 32768}, {'output_subtype': -32769},
    {'input_subtype': True}, {'input_subtype': None},
    {'module_name': ''}, {'entrypoint': 'ü' * 128}, {'module_name': 'a\x00b'},
    {'owner': 'OTHER'}, {'security_class': 'CUSTOM'},
])
def test_invalid_or_other_lifecycle_metadata_blocks(native):
    base = catalog()
    plan = build_plan(base, catalog(filter_object(**native)), base)
    assert plan['status'] == 'blocked' and plan['script'] is None


@pytest.mark.parametrize('native', [{'input_subtype': -22}, {'output_subtype': -23},
                                   {'module_name': 'other'}, {'entrypoint': 'other'}])
def test_definition_change_does_not_silently_drop_redeclare(native):
    base = catalog(filter_object())
    plan = build_plan(base, catalog(filter_object(**native)), base)
    assert plan['status'] == 'blocked' and plan['script'] is None
    assert 'drop/redeclare' in plan['blockers'][0]['reason']


def test_catalog_visibility_conflict_and_convergence():
    base = catalog(filter_object(description='old'))
    desired = catalog(filter_object(description='new'))
    live = catalog(filter_object(description='competing'))
    assert build_plan(base, desired, live)['status'] == 'blocked'
    assert build_plan(base, desired, desired)['status'] == 'no-op'
    unavailable = deepcopy(base)
    unavailable['rows']['database:database']['native']['catalog_observations'] = []
    assert build_plan(base, desired, unavailable)['status'] == 'blocked'
