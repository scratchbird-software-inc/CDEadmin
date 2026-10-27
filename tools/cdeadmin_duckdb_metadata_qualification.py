"""Qualify reviewed DuckDB native comments and retained transaction ownership."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify(output):
    import config  # noqa: F401
    import duckdb
    from pgadmin.cdeadmin.providers.duckdb.provider import ADMINISTRATION, _create_client, _resources
    from pgadmin.cdeadmin.sdk import RelationalClientError
    if duckdb.__version__ != '1.5.2':
        raise ValueError('Select the native DuckDB 1.5.2 profile')
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Evidence belongs outside source')
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    path = output / 'catalog . ü.duckdb'
    observer = duckdb.connect(str(path))
    client = _create_client()
    route = {'database': str(path), 'filesystem_root': str(output)}
    proof = {'complete': False, 'native_version': duckdb.__version__,
             'history_testing': 'not run', 'full_product_complete': False,
             'cases': [], 'source_sha256': {}}
    for name in ['tools/cdeadmin_duckdb_metadata_qualification.py',
            'web/pgadmin/cdeadmin/providers/duckdb/object_metadata.py',
            'web/pgadmin/cdeadmin/providers/duckdb/administration.py',
            'web/pgadmin/cdeadmin/providers/duckdb/provider.py']:
        proof['source_sha256'][name] = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    def target(kind, name, connection=observer):
        return next(row for row in _resources(connection, {'session_catalog': True})
                    if row['resource_kind'] == kind and row['display_name'] == name)
    def plan(resource, comment=None, clear=False):
        request = {'resource_kind': resource['resource_kind'], 'operation_id': 'comment',
                   'target_resource': resource, '_provider_route': route,
                   'draft': {'comment': comment, 'clear_comment': clear,
                             'confirmation': resource['display_name']}}
        assert ADMINISTRATION.validate(request)['errors'] == []
        return ADMINISTRATION.plan(request)
    # These observations are independent native catalog queries, not provider output.
    observers = {
        'database': ('duckdb_databases()', ('database_name',)),
        'attached-database': ('duckdb_databases()', ('database_name',)),
        'schema': ('duckdb_schemas()', ('database_name', 'schema_name')),
        'table': ('duckdb_tables()', ('database_name', 'schema_name', 'table_name')),
        'view': ('duckdb_views()', ('database_name', 'schema_name', 'view_name')),
        'column': ('duckdb_columns()', ('database_name', 'schema_name', 'table_name', 'column_name')),
        'index': ('duckdb_indexes()', ('database_name', 'schema_name', 'index_name')),
        'sequence': ('duckdb_sequences()', ('database_name', 'schema_name', 'sequence_name')),
        'type': ('duckdb_types()', ('database_name', 'schema_name', 'type_name')),
        'macro': ('duckdb_functions()', ('database_name', 'schema_name', 'function_name')),
        'function': ('duckdb_functions()', ('database_name', 'schema_name', 'function_name')),
    }
    def observed(resource, connection=observer):
        relation, keys = observers[resource['resource_kind']]
        values = resource['display_path']
        if resource['resource_kind'] == 'index':
            values = [*values[:2], values[-1]]
        return connection.execute('SELECT comment FROM ' + relation + ' WHERE ' +
            ' AND '.join(key + '=?' for key in keys), values).fetchall()
    retained = None
    try:
        observer.execute('CREATE SCHEMA "schema . ü"')
        observer.execute('CREATE TABLE "schema . ü"."table . ü"("column . ü" INT)')
        observer.execute('CREATE INDEX "index . ü" ON "schema . ü"."table . ü"("column . ü")')
        observer.execute('CREATE VIEW "schema . ü"."view . ü" AS SELECT "column . ü" FROM "schema . ü"."table . ü"')
        observer.execute('CREATE SEQUENCE "schema . ü"."sequence . ü"')
        observer.execute('CREATE TYPE "schema . ü"."type . ü" AS ENUM (\'one\',\'two\')')
        observer.execute('CREATE MACRO "schema . ü"."scalar . ü"(x) AS x+1, (x,y) AS x+y')
        observer.execute('CREATE MACRO "schema . ü"."table macro . ü"(x) AS TABLE SELECT x')
        cases = [('table', 'table . ü'), ('column', 'column . ü'), ('index', 'index . ü'),
                 ('view', 'view . ü'), ('sequence', 'sequence . ü'), ('type', 'type . ü'),
                 ('macro', 'scalar . ü'), ('macro', 'table macro . ü')]
        for kind, name in cases:
            resource = target(kind, name)
            for comment, clear in [("spaces ' apostrophe \\ slash\n雪; DROP TABLE innocent;", False),
                                   ('', False), (None, True)]:
                planned = plan(resource, comment, clear)
                result = ADMINISTRATION.apply(client, planned)
                assert result['accepted'] and result['metadata_observation']['comment_matches']
                native_values = observed(resource)
                assert native_values and native_values == [(comment,)] * len(native_values)
                resource = target(kind, name)
            proof['cases'].append({'kind': kind, 'name': name,
                'independent_comment_empty_and_null_observed': True,
                'source': planned['command_preview']['statements'][0]['source']})
        resource = target('table', 'table . ü')
        stale = plan(resource, 'stale review')
        observer.execute('COMMENT ON TABLE "schema . ü"."table . ü" IS \'external comment\'')
        try:
            ADMINISTRATION.apply(client, stale)
        except RelationalClientError as error:
            assert error.native_dispatched is False
        else:
            raise AssertionError('A stale comment review was dispatched')
        assert observed(resource) == [('external comment',)]
        proof['changed_comment_refused_before_dispatch'] = True
        retained = client.open_session({'route': route})
        retained.execute('INSERT INTO "schema . ü"."table . ü" VALUES (42)')
        resource = target('table', 'table . ü', retained)
        result = ADMINISTRATION.apply(client, plan(resource, 'pending comment'), retained)
        assert result['staged_in_provider_session'] and not result['commit_requested']
        assert retained.execute('SELECT count(*) FROM "schema . ü"."table . ü"').fetchone() == (1,)
        assert observed(resource, retained) == [('pending comment',)]
        assert observed(resource) == [('external comment',)]
        retained.execute('CREATE TEMP TABLE "pending . ü"(id INT)')
        temporary = target('table', 'pending . ü', retained)
        assert ADMINISTRATION.apply(client, plan(temporary, 'temporary comment'), retained)['accepted']
        assert observed(temporary, retained) == [('temporary comment',)]
        retained.rollback()
        assert observed(resource) == [('external comment',)]
        assert observer.execute('SELECT count(*) FROM "schema . ü"."table . ü"').fetchone() == (0,)
        client._forget_and_close(retained)
        retained = None
        proof['retained_pending_and_temporary_comments_preserve_caller_finality'] = True
        database_name = observer.execute('SELECT current_database()').fetchone()[0]
        for kind, name in [('database', database_name), ('schema', 'schema . ü')]:
            assert not ADMINISTRATION.supports(kind, 'comment')
            try:
                observer.execute('COMMENT ON ' + kind.upper() + ' "' + name.replace('"', '""') + '" IS \'unimplemented\'')
            except duckdb.NotImplementedException:
                pass
            else:
                raise AssertionError('Native unsupported scope changed')
        assert not ADMINISTRATION.supports('function', 'comment')
        proof['native_database_schema_function_comment_limits_preserved'] = True
        proof['complete'] = True
    finally:
        if retained is not None:
            client._forget_and_close(retained)
        client.close()
        observer.close()
        (output/'proof.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2)+'\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True, type=Path)
    qualify(parser.parse_args().evidence)
