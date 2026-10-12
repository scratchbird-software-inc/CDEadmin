from copy import deepcopy
import pytest
from tools.tests.test_firebird_schema_plan import document, obj
from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan


def package(**changes):
    return obj('package', 'P"ü', **{'header_source': 'BEGIN FUNCTION F RETURNS INTEGER; END',
        'body_source': 'BEGIN FUNCTION F RETURNS INTEGER AS BEGIN RETURN 1; END END',
        'sql_security': None, 'description': None, **changes})


def catalog(*rows):
    result = document(list(rows))
    result['rows']['database:database']['native']['catalog_observations'] = [
        {'section': 'package objects', 'available': True}]
    return result


def test_create_separates_headers_and_bodies_without_splitting_psql():
    base = catalog(); desired = catalog(package(description='native package', ddl='DROP DATABASE'))
    result = build_plan(base, desired, base)
    assert result['status'] == 'review-ready', result['blockers']
    operation = result['operations'][0]
    assert operation['statements'] == [
        'CREATE PACKAGE "P""ü" AS BEGIN FUNCTION F RETURNS INTEGER; END',
        'COMMENT ON PACKAGE "P""ü" IS \'native package\'']
    assert operation['deferred_statements'] == [
        'CREATE PACKAGE BODY "P""ü" AS BEGIN FUNCTION F RETURNS INTEGER AS BEGIN RETURN 1; END END']
    assert 'SET TERM ' in result['script'] and 'DROP DATABASE' not in result['script']


def test_security_change_restores_unchanged_body_and_preserves_live_comment():
    base = catalog(package()); desired = catalog(package(sql_security=False))
    result = build_plan(base, desired, catalog(package(description='live')))
    assert result['status'] == 'review-ready', result['blockers']
    operation = result['operations'][0]
    assert operation['statements'][0].startswith('ALTER PACKAGE "P""ü" SQL SECURITY INVOKER')
    assert operation['deferred_statements'][0].startswith('RECREATE PACKAGE BODY')
    assert operation['after']['description'] == 'live'


def test_body_removal_is_explicit_and_header_is_preserved():
    base = catalog(package()); desired = catalog(package(body_source=None))
    result = build_plan(base, desired, base)
    assert result['status'] == 'review-ready', result['blockers']
    assert result['operations'][0]['statements'] == []
    assert result['operations'][0]['deferred_statements'] == ['DROP PACKAGE BODY "P""ü"']
    assert build_plan(base, desired, desired)['status'] == 'no-op'


@pytest.mark.parametrize('changes', [{'body_source': ''}, {'header_source': None}, {'sql_security': 2}, {'owner': 'SOMEONE'}])
def test_incomplete_or_unadmitted_package_changes_refuse(changes):
    base = catalog(package())
    result = build_plan(base, catalog(package(**changes)), base)
    assert result['status'] == 'blocked' and result['script'] is None


def test_conflicts_and_missing_observation_refuse():
    base = catalog(package()); wanted = catalog(package(description='desired'))
    assert build_plan(base, wanted, catalog(package(description='competing')))['status'] == 'blocked'
    current = deepcopy(base)
    current['rows']['database:database']['native']['catalog_observations'] = []
    assert build_plan(base, wanted, current)['status'] == 'blocked'
