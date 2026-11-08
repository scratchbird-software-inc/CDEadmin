"""Catalog diagrams carry crow's-foot cardinality on every foreign key.

The Diagrams tool (owner direction 2026-11-06) defaults to crow's foot
(DDN profile erd.crowfoot@1), whose relations carry source_mark and
target_mark. The engines' catalog diagram builders write those marks on
each foreign key, so "To Diagram" can place relations in a crow's-foot
diagram without engine-specific code in the browser. DDN also draws the
marks in the ddn@1 views of the catalog diagrams.

The referencing side is zero or many; the referenced side is one when every
foreign-key column is NOT NULL and zero or one otherwise; no marks are
written when a column's nullability is unknown.
"""
import json
from pathlib import Path
import re
import sqlite3
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.workspace import ddn_source
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export

CHECKER = Path(__file__).with_name('check_firebird_catalog_ddn.mjs')
MARKS = re.compile(r'relation "[^"]+" as "ref"\n    with\n(?:.*\n)*?'
                   r'        properties\n            source_mark "(\w+)"\n'
                   r'            target_mark "(\w+)"\n'
                   r'            enforcement "database"\n')


def marks(diagram):
    return MARKS.findall(diagram['snapshot']['files']['relations.ddn'])


def admit(diagram, notation=None):
    """DDN admits the diagram, also with its views in another notation."""
    snapshot = json.loads(json.dumps(diagram['snapshot']))
    if notation:
        for name, source in snapshot['files'].items():
            snapshot['files'][name] = source.replace(
                ' as "ddn@1"', f' as "{notation}"')
    script = 'import ' + json.dumps(CHECKER.as_uri()) + ';'
    subprocess.run(['node', '--input-type=module', '-e', script],
                   input=json.dumps(snapshot), text=True,
                   capture_output=True, timeout=30, check=True)


def test_marks_follow_foreign_key_nullability():
    assert ddn_source.crowfoot_marks([False, False]) == {
        'source_mark': 'zeromany', 'target_mark': 'one'}
    assert ddn_source.crowfoot_marks([False, True]) == {
        'source_mark': 'zeromany', 'target_mark': 'zeroone'}
    assert ddn_source.crowfoot_marks([False, None]) is None
    assert ddn_source.crowfoot_marks([]) is None


def test_sqlite_catalog_diagram(tmp_path):
    from pgadmin.cdeadmin.providers.sqlite.provider import (
        SQLiteProvider, _create_client)
    path = tmp_path / 'native.sqlite'
    with sqlite3.connect(path) as owner:
        owner.executescript('''
            CREATE TABLE parent(id INTEGER PRIMARY KEY);
            CREATE TABLE required(id INTEGER PRIMARY KEY,
              parent_id INTEGER NOT NULL REFERENCES parent(id));
            CREATE TABLE optional(id INTEGER PRIMARY KEY,
              parent_id INTEGER REFERENCES parent(id));
        ''')
    client = _create_client()
    try:
        provider = SQLiteProvider(SimpleNamespace(),
                                  SimpleNamespace(require=Mock()), client)
        captured = provider.capture_catalog({
            'database': str(path), 'filesystem_root': str(tmp_path)})
    finally:
        client.close()
    diagram = build_export(captured['resources'], endpoint_id='e',
                           target_id='f', generation=captured['generation'],
                           refreshed=True, engine='sqlite')['diagram']
    assert sorted(marks(diagram)) == [('zeromany', 'one'),
                                      ('zeromany', 'zeroone')]
    admit(diagram)
    admit(diagram, 'erd.crowfoot@1')


def test_duckdb_catalog_diagram(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    from pgadmin.cdeadmin.providers.duckdb.catalog import capture
    connection = duckdb.connect(str(tmp_path / 'owned.duckdb'))
    try:
        connection.execute('CREATE TABLE parent (id INTEGER PRIMARY KEY)')
        connection.execute(
            'CREATE TABLE required (id INTEGER PRIMARY KEY, '
            'parent_id INTEGER NOT NULL, '
            'FOREIGN KEY (parent_id) REFERENCES parent(id))')
        connection.execute(
            'CREATE TABLE optional (id INTEGER PRIMARY KEY, '
            'parent_id INTEGER, '
            'FOREIGN KEY (parent_id) REFERENCES parent(id))')
        rows = capture(connection)['resources']
    finally:
        connection.close()
    diagram = build_export(rows, engine='duckdb', endpoint_id='embedded',
                           target_id='owned-file',
                           generation='native-1')['diagram']
    assert sorted(marks(diagram)) == [('zeromany', 'one'),
                                      ('zeromany', 'zeroone')]
    admit(diagram)
    admit(diagram, 'erd.crowfoot@1')


def test_postgresql_catalog_diagram():
    from test_postgresql_erd import PROVENANCE, constraint, relation
    from pgadmin.cdeadmin.workspace.postgresql_erd import build_diagram

    def rows():
        return [relation(100, 'a'), relation(200, 'b'), constraint(100, 200)]

    def first_column(items):
        return items[0]['native']['children']['pg_attribute'][0]
    # Column 1 ("id") is NOT NULL in the fixture.
    required = build_diagram(rows(), PROVENANCE)
    assert marks(required) == [('zeromany', 'one')]
    optional_rows = rows()
    first_column(optional_rows)['attnotnull'] = False
    assert marks(build_diagram(optional_rows, PROVENANCE)) == [
        ('zeromany', 'zeroone')]
    unknown_rows = rows()
    del first_column(unknown_rows)['attnotnull']
    unknown = build_diagram(unknown_rows, PROVENANCE)
    assert marks(unknown) == [] and unknown['foreign_keys'] == 1
    admit(required)
    admit(required, 'erd.crowfoot@1')


def test_firebird_catalog_diagram():
    from test_firebird_erd import fixture

    def diagram(rows):
        return build_export(rows, endpoint_id='engine', target_id='db',
                            generation='g')['diagram']
    required = diagram(fixture())
    assert marks(required) == [('zeromany', 'one')]
    rows = fixture()
    column = next(row for row in rows if row['display_name'] == 'Exact"A')
    column['native'].pop('not_null')
    optional = diagram(rows)
    assert marks(optional) == [('zeromany', 'zeroone')]
    admit(required)
    admit(required, 'erd.crowfoot@1')


@pytest.mark.parametrize('engine', ['mysql', 'mariadb'])
def test_mysql_family_catalog_diagram(engine):
    from test_mysql_catalog import Connection, capture
    from pgadmin.cdeadmin.workspace.mysql_erd import build_diagram
    results = {}
    for nullable in ('NO', 'YES'):
        captured = capture(Connection(), 'demo')
        children = captured['resources'][1]['native']['children']
        children['COLUMNS'][0].update(ordinal_position=1,
                                      is_nullable=nullable)
        children['KEY_COLUMN_USAGE'] = [{
            'constraint_name': 'self-reference', 'column_name': 'id',
            'ordinal_position': 1, 'referenced_column_name': 'id',
            'referenced_table_schema': 'demo',
            'referenced_table_name': 'a:`b'}]
        results[nullable] = build_diagram(
            captured['resources'],
            {'endpoint_id': 'ep', 'database_target_id': 'target'},
            engine=engine)
    assert marks(results['NO']) == [('zeromany', 'one')]
    assert marks(results['YES']) == [('zeromany', 'zeroone')]
    admit(results['NO'])
    admit(results['NO'], 'erd.crowfoot@1')


def _without_marks(snapshot):
    """The same diagram as the builders wrote it before marks were added."""
    result = json.loads(json.dumps(snapshot))
    for name, source in result['files'].items():
        result['files'][name] = re.sub(
            r'            source_mark "\w+"\n            target_mark "\w+"\n',
            '', source)
    return result


def test_saved_catalog_designs_take_the_marks_on_their_next_merge():
    # A saved catalog design is refreshed by a three-way merge of its
    # baseline (the capture it was made from), the user's draft and the new
    # capture. Relations the user did not edit take the marks; an edited
    # relation is reported, never overwritten.
    from test_postgresql_erd import PROVENANCE, constraint, relation
    from pgadmin.cdeadmin.workspace.postgresql_erd import build_diagram
    from pgadmin.cdeadmin.workspace.design_conversion import merge_design
    incoming = build_diagram(
        [relation(100, 'a'), relation(200, 'b'), constraint(100, 200)],
        PROVENANCE)['snapshot']
    baseline = _without_marks(incoming)
    assert baseline != incoming and not marks({'snapshot': baseline})
    merged = merge_design({'baseline': baseline, 'draft': baseline,
                           'incoming': incoming})
    assert marks({'snapshot': merged}) == [('zeromany', 'one')]
    edited = json.loads(json.dumps(baseline))
    # The relation's own title (its mapping record repeats the text).
    relation_title = re.compile(
        r'(as "ref"\n    with\n        id "[^"]+"\n        title )"[^"]+"')
    source = edited['files']['relations.ddn']
    assert len(relation_title.findall(source)) == 1
    edited['files']['relations.ddn'] = relation_title.sub(
        r'\1"orders belong to customers"', source)
    with pytest.raises(ValueError, match='changed on both sides'):
        merge_design({'baseline': baseline, 'draft': edited,
                      'incoming': incoming})
