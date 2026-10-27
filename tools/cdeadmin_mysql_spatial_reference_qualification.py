"""Qualify exact MySQL spatial-reference catalog and reviewed native operations."""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'web'), str(ROOT/'tools')]


def qualify(output):
    import config  # noqa: F401
    from mysql_qualification_support import server, _root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import (
        MYSQL_ADMINISTRATION as adapter, MYSQL_PROFILE, _create_client, _resources)
    from pgadmin.cdeadmin.providers.mysql_family import spatial_reference_systems as srs
    from pgadmin.cdeadmin.sdk import RelationalClientError
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Evidence belongs outside the repository')
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    proof = {'complete': False, 'history_testing': 'not run', 'full_product_complete': False,
             'checks': [], 'source_sha256': {}}
    for name in ['tools/cdeadmin_mysql_spatial_reference_qualification.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/spatial_reference_systems.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/administration.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/provider.py']:
        proof['source_sha256'][name] = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    try:
        with server(output/'fixture') as (route, _name, owned):
            connection = _root_connection('mysql', route['port'])
            connection.autocommit = True
            cursor = connection.cursor()
            try:
                cursor.execute('SELECT DEFINITION FROM information_schema.ST_SPATIAL_REFERENCE_SYSTEMS WHERE SRS_ID=4326')
                definition = cursor.fetchone()[0]
                cursor.execute('SELECT COUNT(*),SUM(OCTET_LENGTH(DEFINITION)) FROM information_schema.ST_SPATIAL_REFERENCE_SYSTEMS')
                count, bytes = cursor.fetchone()
                proof['independent_native_srs_count'] = count
                proof['native_definition_bytes'] = str(bytes)
                cursor.execute('CREATE DATABASE sr_spatial')
                for pure in (True, False):
                    for mode in ('', 'NO_BACKSLASH_ESCAPES,ANSI_QUOTES'):
                        selected = {**route, 'use_pure': pure, 'sql_mode': mode}
                        client = _create_client(MYSQL_PROFILE, SimpleNamespace(acquire_secret=None), SimpleNamespace())
                        srid = 4294967001
                        def observed():
                            cursor.execute(srs.SELECT + ' WHERE SRS_ID=%s', (srid,))
                            row = cursor.fetchone()
                            return srs.normalized(row) if row else None
                        def target():
                            rows = _resources(connection, {'route': {}}, MYSQL_PROFILE)
                            if not proof.get('independent_full_srs_catalog_verified'):
                                cursor.execute('SELECT SRS_NAME,SRS_ID,ORGANIZATION,ORGANIZATION_COORDSYS_ID,DEFINITION,DESCRIPTION '
                                    'FROM information_schema.ST_SPATIAL_REFERENCE_SYSTEMS ORDER BY SRS_ID')
                                keys = ['srs_name', 'srs_id', 'organization', 'organization_coordsys_id', 'definition', 'description']
                                expected = [dict(zip(keys, row)) for row in cursor.fetchall()]
                                for row in expected:
                                    if row['organization_coordsys_id'] is not None:
                                        row['organization_coordsys_id'] = str(row['organization_coordsys_id'])
                                actual = [{key: srs.native(row)[key] for key in keys} for row in rows if row['resource_kind'] == srs.KIND]
                                actual.sort(key=lambda row: row['srs_id'])
                                assert actual == expected and len(expected) == count + 1
                                proof['independent_full_srs_catalog_verified'] = {
                                    'count': len(expected), 'sha256': hashlib.sha256(json.dumps(expected,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
                            return next(row for row in rows if row['resource_kind'] == srs.KIND and row['display_name'] == str(srid))
                        def planned(operation, draft, resource=None):
                            request = {'resource_kind': srs.KIND, 'operation_id': operation,
                                'draft': draft, 'target_resource': resource, '_provider_route': selected}
                            assert not adapter.validate(request)['errors']
                            return client.plan_admin_operation(request)
                        draft = {'srs_id': str(srid), 'name': "Native ' ü \\ SRS", 'definition': definition,
                            'include_organization': True, 'organization': "CDEadmin ' ü \\",
                            'organization_id': '4294967295',
                            'include_description': True, 'description': "Native ' ü \\ description"}
                        try:
                            result = adapter.apply(client, planned('create', draft))
                            assert result['native_implicit_commit'] and result['spatial_reference_observation']['native_acknowledged']
                            after = observed()
                            assert after['srs_name'] == draft['name'] and after['definition'] == definition
                            assert after['description'] == draft['description']
                            assert after['organization'] == draft['organization'] and after['organization_coordsys_id'] == draft['organization_id']
                            resource = target()
                            assert all(srs.native(resource)[key] == after[key] for key in srs.FIELDS)
                            assert resource['native']['navigator_scope'] == 'server'
                            unchanged = adapter.apply(client, planned('create', {**draft, 'if_not_exists': True, 'name': 'must not replace'}))
                            assert unchanged['native_warnings'] and all(type(row['code']) is int for row in unchanged['native_warnings'])
                            assert observed() == after
                            alter = {key: value for key, value in draft.items() if key != 'srs_id'}
                            alter.update(name='Reviewed replacement ü', confirmation=str(srid))
                            stale = planned('alter', alter, resource)
                            cursor.execute('CREATE OR REPLACE SPATIAL REFERENCE SYSTEM ' + str(srid) +
                                ' NAME %s DEFINITION %s', ('external change', definition))
                            try:
                                adapter.apply(client, stale)
                            except RelationalClientError as error:
                                assert error.native_dispatched is False
                            else:
                                raise AssertionError('A changed SRS definition was overwritten')
                            result = adapter.apply(client, planned('alter', alter, target()))
                            assert result['spatial_reference_observation']['after']['srs_name'] == alter['name']
                            assert observed()['description'] == draft['description']
                            cursor.execute('CREATE TABLE sr_spatial.spatial_data(p POINT SRID ' + str(srid) + ')')
                            cursor.execute('INSERT INTO sr_spatial.spatial_data VALUES (ST_GeomFromText(%s,%s))', ('POINT(10 20)', srid))
                            try:
                                adapter.apply(client, planned('drop', {'confirmation': str(srid)}, target()))
                            except RelationalClientError as error:
                                assert error.native_dispatched and not error.native_acknowledged and error.errno is not None
                            else:
                                raise AssertionError('An in-use SRS was dropped')
                            cursor.execute('SELECT ST_SRID(p),ST_AsText(p) FROM sr_spatial.spatial_data')
                            assert cursor.fetchone() == (srid, 'POINT(10 20)')
                            cursor.execute('DROP TABLE sr_spatial.spatial_data')
                            drop = planned('drop', {'confirmation': str(srid)}, target())
                            assert adapter.apply(client, drop)['spatial_reference_observation']['after'] is None
                            assert observed() is None and client._connections == []
                            proof['checks'].append({'use_pure': pure, 'sql_mode': mode,
                                'full_attributes_and_uint32_verified': True,
                                'native_catalog_verified': True, 'if_not_exists_does_not_replace': True,
                                'native_if_not_exists_warnings': unchanged['native_warnings'],
                                'changed_review_refused_before_dispatch': True,
                                'native_in_use_refusal_preserves_data': True,
                                'replace_and_drop_independently_verified': True,
                                'task_sources': {
                                    'create': planned('create', draft)['command_preview']['statements'][0]['source'],
                                    'alter': stale['command_preview']['statements'][0]['source'],
                                    'drop': drop['command_preview']['statements'][0]['source']}})
                        finally:
                            client.close()
                cursor.execute("CREATE USER 'sr_srs_reader'@'%'")
                restricted = _create_client(MYSQL_PROFILE, SimpleNamespace(acquire_secret=None), SimpleNamespace())
                try:
                    selected = {**route, 'user': 'sr_srs_reader', 'use_pure': True}
                    denied = {'srs_id': '4294967002', 'name': 'not created', 'definition': definition}
                    item = {'resource_kind': srs.KIND, 'operation_id': 'create', 'draft': denied,
                            'target_resource': None, '_provider_route': selected}
                    try:
                        adapter.apply(restricted, restricted.plan_admin_operation(item))
                    except RelationalClientError as error:
                        assert error.native_dispatched and not error.native_acknowledged
                        assert error.errno is not None
                        proof['restricted_principal_native_refusal'] = {'error_code': error.errno, 'sqlstate': error.sqlstate}
                    else:
                        raise AssertionError('A restricted principal created a native SRS')
                    cursor.execute('SELECT COUNT(*) FROM information_schema.ST_SPATIAL_REFERENCE_SYSTEMS WHERE SRS_ID=4294967002')
                    assert cursor.fetchone() == (0,)
                finally:
                    restricted.close()
                    cursor.execute("DROP USER 'sr_srs_reader'@'%'")
                proof['native_engine'] = owned
                proof['complete'] = True
            finally:
                cursor.close()
                connection.close()
    except Exception as error:
        proof['failure'] = {'type': type(error).__name__, 'native_error_code': getattr(error, 'errno', None),
            'sqlstate': getattr(error, 'sqlstate', None), 'native_dispatched': getattr(error, 'native_dispatched', None),
            'native_acknowledged': getattr(error, 'native_acknowledged', None)}
        raise
    finally:
        (output/'proof.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2)+'\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True, type=Path)
    qualify(parser.parse_args().evidence)
