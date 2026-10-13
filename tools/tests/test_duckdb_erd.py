"""Native DuckDB identities survive catalog capture and public DDN rendering."""

import json
from pathlib import Path
import subprocess

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.catalog import capture
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_catalog_import import compare_catalogs, read_catalog


def _export(rows, **options):
    return build_export(rows, engine='duckdb', endpoint_id='embedded',
                        target_id='owned-file', generation='native-1', **options)


def test_native_identity_scope_roundtrip_and_render(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    connection = duckdb.connect(str(tmp_path / 'owned.duckdb'))
    try:
        connection.execute('CREATE SCHEMA "a:b"')
        connection.execute('CREATE SCHEMA a')
        connection.execute('CREATE TABLE "a:b".c (id INTEGER PRIMARY KEY, amount DECIMAL(20,3))')
        connection.execute('CREATE TABLE a."b:c" (id INTEGER PRIMARY KEY, parent_id INTEGER, '
                           'CONSTRAINT parent_fk FOREIGN KEY(parent_id) REFERENCES a."b:c"(id))')
        connection.execute('CREATE MACRO a.f(x) AS x + 1, (x,y) AS x + y')
        captured = capture(connection)
        rows = captured['resources']
        tables = [row for row in rows if row['resource_kind'] == 'table' and
                  row['display_name'] in {'c', 'b:c'}]
        assert len(tables) == 2
        assert len({row['resource_id'] for row in tables}) == 2
        assert len({row['resource_id'] for row in rows}) == len(rows)
        for row in tables:
            assert len(row['native']['columns']) >= 1
            assert all(child['native']['navigator_parent_resource_id'] == row['resource_id']
                       for child in rows if child['resource_kind'] in {'column', 'constraint'}
                       and child['display_path'][:-1] == row['display_path'])

        exported = _export(rows)
        assert exported['provenance']['coverage'] == 'partial'
        decoded = read_catalog(json.dumps(exported['snapshot']), engine='duckdb')
        native = _export(rows, native_model=True)
        assert not compare_catalogs(decoded, native)['changes']
        assert exported['diagram']['foreign_keys'] == 1
        assert len(exported['diagram']['resource_mapping']) >= 2

        source = exported['diagram']['snapshot']
        runtime = (Path(__file__).resolve().parents[2] /
                   'web/pgadmin/static/vendor/ddn/current/ddn.mjs').as_uri()
        script = f'''import runtime from {json.dumps(runtime)};
          let input='';for await(const chunk of process.stdin)input+=chunk;
          const snapshot=JSON.parse(input), workspace=runtime.createWorkspace(snapshot.files);
          try {{const output=workspace.renderSync({{entry:snapshot.entry,view:snapshot.view}});
            if(output.diagnostics.some(x=>x.severity==='error'))throw Error(JSON.stringify(output.diagnostics));
            if(!output.svg.includes('a:b') || !output.svg.includes('b:c'))throw Error('Missing native relation labels');
          }}finally{{workspace.destroy();}}'''
        subprocess.run(['node', '--input-type=module', '-e', script], input=json.dumps(source),
                       text=True, capture_output=True, timeout=15, check=True)

        selected = _export(rows, resource_id=tables[0]['resource_id'])
        only = read_catalog(json.dumps(selected['snapshot']), engine='duckdb')
        assert tables[0]['resource_id'] in only['rows']
        assert all(row['path'][:3] == tables[0]['display_path'] or
                   row['resource_id'] == tables[0]['resource_id']
                   for row in only['rows'].values())
    finally:
        connection.close()
