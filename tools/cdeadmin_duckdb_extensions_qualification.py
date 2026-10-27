"""Qualify full DuckDB extension facts, native updates and retained finality."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'web'), str(ROOT/'tools')]


def qualify(output):
    import config  # noqa: F401
    import duckdb
    from pgadmin.cdeadmin.providers.duckdb.provider import ADMINISTRATION, _create_client, _resources
    from pgadmin.cdeadmin.providers.duckdb import extension_updates as updates
    from pgadmin.cdeadmin.sdk import RelationalClientError
    if duckdb.__version__ != '1.5.2':
        raise ValueError('Select exact DuckDB 1.5.2')
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Evidence belongs outside source')
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    path = output/'owned.duckdb';configuration = {'extension_directory': str(output/'extension-cache')}
    owner = duckdb.connect(str(path), config=configuration);client = _create_client()
    route = {'database': str(path), 'filesystem_root': str(output), 'config': configuration}
    proof = {'complete': False, 'native_version': duckdb.__version__, 'history_testing': 'not run',
        'full_product_complete': False, 'source_sha256': {}}
    for name in ['tools/cdeadmin_duckdb_extensions_qualification.py',
            'web/pgadmin/cdeadmin/providers/duckdb/extension_updates.py',
            'web/pgadmin/cdeadmin/providers/duckdb/administration.py',
            'web/pgadmin/cdeadmin/providers/duckdb/provider.py']:
        proof['source_sha256'][name] = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    def target(kind, connection=owner):
        return next(row for row in _resources(connection, {'session_catalog': True})
            if row['resource_kind'] == kind and (kind == 'database' or row['display_name'] == 'httpfs'))
    def plan(resource):
        return ADMINISTRATION.plan({'resource_kind': resource['resource_kind'],
            'operation_id': 'update' if resource['resource_kind'] == 'extension' else 'update_extensions',
            'target_resource': resource, '_provider_route': route,
            'draft': {'confirmation': resource['display_name'], 'filesystem_effects_acknowledged': True}})
    try:
        owner.execute("INSTALL httpfs FROM 'https://extensions.duckdb.org'")
        owner.execute('CREATE TABLE pending(id INT)')
        owner.execute('SELECT * FROM duckdb_extensions() ORDER BY extension_name')
        columns = [row[0] for row in owner.description]
        expected = [dict(zip(columns, row)) for row in owner.fetchall()]
        actual = [row['native']['catalog_metadata'] for row in _resources(owner, {}) if row['resource_kind'] == 'extension']
        assert actual == expected and set(columns) == set(updates.FIELDS)
        proof['all_native_extension_fields_verified'] = {'fields': columns, 'rows': len(actual)}
        resource = target('extension');record = resource['native']['catalog_metadata']
        binary = Path(record['install_path']);info = Path(str(binary)+'.info')
        assert binary.is_relative_to(output) and info.is_file()
        proof['native_installed_extension'] = {'name': record['extension_name'],
            'version': record['extension_version'], 'repository': record['installed_from'],
            'sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
        planned = plan(resource)
        one = ADMINISTRATION.apply(client, planned)['extension_update_observation']
        assert len(one['native_results']) == 1 and one['native_results'][0]['extension_name'] == 'httpfs'
        assert set(one['native_results'][0]) == {'extension_name', 'repository', 'update_result', 'previous_version', 'current_version'}
        assert one['native_results'][0]['update_result'] in {'NO_UPDATE_AVAILABLE', 'UPDATED', 'REDOWNLOADED'}
        assert one['native_results'][0]['current_version'] == owner.execute(
            "SELECT extension_version FROM duckdb_extensions() WHERE extension_name='httpfs'").fetchone()[0]
        proof['native_single_update'] = one['native_results']
        stale = plan(target('extension'));saved = info.read_bytes();info.unlink()
        try:
            try:
                ADMINISTRATION.apply(client, stale)
            except RelationalClientError as error:
                assert not error.native_dispatched
            else:
                raise AssertionError('A changed extension installation was updated')
        finally:
            info.write_bytes(saved)
        proof['changed_installation_refused_before_dispatch'] = True
        retained = client.open_session({'route': route})
        retained.execute('INSERT INTO pending VALUES (42)');retained.execute('CREATE TEMP TABLE private(id INT)')
        all_plan = plan(target('database', retained))
        result = ADMINISTRATION.apply(client, all_plan, retained)
        assert not result['commit_requested'] and not result['rollback_requested'] and not result['staged_in_provider_session']
        assert len(result['extension_update_observation']['native_results']) == 1
        assert retained.execute('SELECT id FROM pending').fetchall() == [(42,)]
        assert retained.execute("SELECT COUNT(*) FROM duckdb_tables() WHERE temporary AND table_name='private'").fetchone() == (1,)
        assert owner.execute('SELECT id FROM pending').fetchall() == []
        retained.rollback()
        assert owner.execute('SELECT id FROM pending').fetchall() == [] and binary.is_file()
        proof['retained_transaction_and_temporary_objects_preserved'] = True
        proof['native_all_update'] = result['extension_update_observation']['native_results']
        client.close_session(retained)
        resource = target('extension');bad_plan = plan(resource);saved_binary = binary.read_bytes()
        binary.write_bytes(b'invalid extension binary')
        try:
            try:
                ADMINISTRATION.apply(client, bad_plan)
            except RelationalClientError as error:
                assert error.native_dispatched and not error.native_acknowledged
                assert error.native_filesystem_effects_possible and error.automatic_retry is False
            else:
                raise AssertionError('A corrupt extension file was accepted')
        finally:
            binary.write_bytes(saved_binary)
        proof['native_corrupt_file_refusal_without_replay'] = True
        assert client._connections == []
        proof['task_sources'] = {'visual_admin.extension.update': planned['command_preview']['statements'][0]['source'],
            'visual_admin.database.update_extensions': all_plan['command_preview']['statements'][0]['source']}
        proof['complete'] = True
    finally:
        client.close();owner.close();(output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',required=True,type=Path)
    qualify(parser.parse_args().evidence)
