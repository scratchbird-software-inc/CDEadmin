"""Native original-session DuckDB attachment review, execution and receipts."""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'web'), str(ROOT/'tools')]


def qualify(output):
    import config  # noqa: F401
    import duckdb
    from pgadmin.cdeadmin.providers.duckdb.provider import DuckDBPilotProvider, _create_client
    from pgadmin.cdeadmin.providers.duckdb import attachments
    if duckdb.__version__ != '1.5.2':
        raise ValueError('Select exact native DuckDB 1.5.2')
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Evidence belongs outside source')
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    proof = {'complete': False, 'native_version': duckdb.__version__, 'history_testing': 'not run',
        'full_product_complete': False, 'checks': [], 'source_sha256': {}}
    for name in ['tools/cdeadmin_duckdb_attachment_qualification.py',
            'web/pgadmin/cdeadmin/providers/duckdb/attachments.py',
            'web/pgadmin/cdeadmin/providers/duckdb/catalog.py',
            'web/pgadmin/cdeadmin/providers/duckdb/driver.py',
            'web/pgadmin/cdeadmin/providers/duckdb/provider.py',
            'web/pgadmin/cdeadmin/data_studio/studio.py',
            'web/pgadmin/cdeadmin/workspace/service.py',
            'web/pgadmin/browser/server_groups/servers/__init__.py',
            'web/pgadmin/static/js/Dialogs/DuckDBAttachment.jsx',
            'web/pgadmin/static/js/Dialogs/ProviderWorkspaceContent.jsx']:
        proof['source_sha256'][name] = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    try:
        for memory in (False, True):
            directory = output/('memory' if memory else 'file');directory.mkdir()
            other = directory/'other . é.duckdb';replacement = directory/'replacement.duckdb'
            for path, value in ((other, 7), (replacement, 9)):
                connection = duckdb.connect(str(path));connection.execute('CREATE TABLE data(id INT)')
                connection.execute('INSERT INTO data VALUES (?)', (value,));connection.close()
            route = {'database': ':memory:' if memory else str(directory/'primary.duckdb'),
                'filesystem_root': str(directory), 'allow_memory': True}
            client = _create_client();permissions = SimpleNamespace(require=lambda *_: None)
            provider = DuckDBPilotProvider(SimpleNamespace(endpoint_id='owned-native', session_namespace='owned-native'), permissions, client)
            observer = None
            try:
                opened = provider.open_session({'route': route});sid = opened['session_id']
                handle = provider._sessions[sid].handle;handle.execute('CREATE TABLE pending(id INT)')
                client.control_transaction(handle, 'commit');observer = handle.cursor()
                def request(value, session=sid):
                    return provider.attachment_action({**value,'session_id':session,'language_profile':'duckdb-sql'},route)
                def review(draft):
                    return request({'operation':'review','draft':draft})
                def apply(record):
                    payload={'operation':'apply','review_id':record['review_id'],'review_digest':record['review_digest'],
                        'confirmation':record['alias'],'confirmed':True}
                    result=request(payload);assert request(payload)==result
                    return result
                alias='quoted " é . '+'long'*40
                draft={'action':'attach','alias':alias,'path':str(other),'read_only':True,
                    'conflict':'ERROR','create_if_missing':False}
                handle.execute('INSERT INTO pending VALUES (42)');handle.execute('CREATE TEMP TABLE private(id INT)')
                record=review(draft);result=apply(record)
                assert result['state']=='acknowledged' and result['rediscovery_verified'] and not result['caller_transaction_decision_requested']
                assert handle.execute('SELECT id FROM '+attachments.quote(alias)+'.main.data').fetchall()==[(7,)]
                assert handle.execute('SELECT id FROM pending').fetchall()==[(42,)] and observer.execute('SELECT id FROM pending').fetchall()==[]
                assert handle.execute("SELECT count(*) FROM duckdb_tables() WHERE temporary AND table_name='private'").fetchone()==(1,)
                assert alias in [row[0] for row in observer.execute('SELECT database_name FROM duckdb_databases()').fetchall()]
                client.control_transaction(handle,'rollback')
                assert alias not in [row['name'] for row in attachments.catalogs(handle)] and handle.execute('SELECT id FROM pending').fetchall()==[]
                assert apply(review(draft))['rediscovery_verified'];client.control_transaction(handle,'commit')
                handle.execute('INSERT INTO pending VALUES (42)')
                detached=apply(review({'action':'detach','alias':alias,'if_exists':False}))
                assert detached['rediscovery_verified'] and handle.execute('SELECT id FROM pending').fetchall()==[(42,)]
                client.control_transaction(handle,'rollback')
                assert alias not in [row['name'] for row in attachments.catalogs(handle)] and handle.execute('SELECT id FROM pending').fetchall()==[]
                created=directory/'created.duckdb'
                assert apply(review({**draft,'path':str(created),'read_only':False,'create_if_missing':True}))['rediscovery_verified']
                client.control_transaction(handle,'rollback');assert created.is_file()
                assert apply(review({**draft,'alias':'MiXeD é'}))['rediscovery_verified'];client.control_transaction(handle,'commit')
                unused=directory/'unused.duckdb'
                ignored=apply(review({**draft,'alias':'mixed é','path':str(unused),'conflict':'IGNORE'}))
                assert ignored['rediscovery_verified'] and not unused.exists()
                replaced=apply(review({**draft,'alias':'mixed é','path':str(replacement),'conflict':'REPLACE'}))
                assert replaced['rediscovery_verified'] and handle.execute('SELECT id FROM "MiXeD é".main.data').fetchall()==[(9,)]
                assert apply(review({'action':'detach','alias':'missing','if_exists':True}))['rediscovery_verified']
                client.control_transaction(handle,'rollback')
                stale=review(draft)
                handle.execute("ATTACH '"+str(replacement).replace("'","''")+"' AS external_change (READ_ONLY)")
                refused=apply(stale);assert refused['state']=='refused' and not refused['native_dispatched']
                handle.execute('DETACH external_change')
                assert apply(stale)==refused
                record=review(draft);second=provider.open_session({'route':route})
                try:
                    request({'operation':'apply','review_id':record['review_id'],'review_digest':record['review_digest'],
                        'confirmation':alias,'confirmed':True},second['session_id'])
                except ValueError:
                    pass
                else:
                    raise AssertionError('An attachment review moved to another native connection')
                provider.close_session({'session_id':second['session_id']})
                storage_file=directory/'native-storage.duckdb'
                storage_options={'block_size':'32768','row_group_size':'4096','storage_version':'v1.5.0'}
                handle.execute('INSERT INTO pending VALUES (43)')
                transaction=handle.execute('SELECT current_transaction_id()').fetchone()[0]
                storage_review=review({**draft,'path':str(storage_file),'read_only':False,
                    'create_if_missing':True,'storage_options':storage_options})
                storage_result=apply(storage_review)
                assert storage_result['state']=='acknowledged' and storage_result['rediscovery_verified']
                assert storage_result['native_storage']['block_size']=='32768'
                assert handle.execute('SELECT id FROM pending').fetchall()==[(43,)]
                assert observer.execute('SELECT id FROM pending').fetchall()==[]
                assert handle.execute('SELECT current_transaction_id()').fetchone()[0]==transaction
                client.control_transaction(handle,'rollback');assert storage_file.is_file()
                storage_review=review({**draft,'path':str(storage_file),'read_only':False,
                    'storage_options':storage_options})
                assert apply(storage_review)['rediscovery_verified']
                qualified=attachments.quote(alias)+'.main.'
                handle.execute('CREATE TABLE '+qualified+'storage_rows(id INT, payload STRUCT("field . é" VARCHAR))')
                handle.execute("INSERT INTO "+qualified+"storage_rows SELECT i, {'field . é':i::VARCHAR} FROM range(9000) r(i)")
                client.control_transaction(handle,'commit')
                assert handle.execute('SELECT count(*),sum(id) FROM '+qualified+'storage_rows').fetchone()==(9000,40495500)
                assert apply(review({'action':'detach','alias':alias,'if_exists':False}))['rediscovery_verified']
                try:
                    review({**draft,'path':':memory:','read_only':False,'storage_options':{'compress':True}})
                except ValueError as error:
                    assert 'current transaction' in str(error)
                else:
                    raise AssertionError('A retired native alias was reused before the caller transaction decision')
                client.control_transaction(handle,'commit')
                memory_review=review({**draft,'path':':memory:','read_only':False,'storage_options':{'compress':True}})
                memory_result=apply(memory_review)
                assert memory_result['rediscovery_verified'] and memory_result['native_storage']['block_size']=='0'
                assert next(row for row in memory_result['native_catalogs'] if row['name']==alias)['options']['compress']=='true'
                handle.execute('CREATE TABLE '+qualified+'memory_rows AS SELECT 42 AS id')
                assert handle.execute('SELECT id FROM '+qualified+'memory_rows').fetchone()==(42,)
                client.control_transaction(handle,'rollback')
                restored=duckdb.connect(str(storage_file),read_only=True)
                try:
                    assert restored.execute('SELECT count(*),sum(id) FROM storage_rows').fetchone()==(9000,40495500)
                    assert restored.execute("SELECT payload.\"field . é\" FROM storage_rows WHERE id=8999").fetchone()==('8999',)
                    assert restored.execute('SELECT block_size FROM pragma_database_size() WHERE database_name=current_database()').fetchone()==(32768,)
                finally:restored.close()
                record=review(draft)
                before=attachments.catalogs(handle)
                with patch.object(attachments,'catalogs',side_effect=[before,OSError('post-acknowledgement read failed'),before]):
                    uncertain=apply(record)
                assert uncertain['native_acknowledged'] and not uncertain['rediscovery_verified'] and uncertain['session_reuse_blocked']
                assert request({'operation':'receipt','review_id':record['review_id']})==uncertain
                proof['checks'].append({'root':'memory' if memory else 'file',
                    'native_provider_identity':opened['identity'],
                    'existing_readonly_and_long_quoted_alias_verified':True,
                    'pending_rows_and_temporary_objects_preserved':True,
                    'attach_rollback_removes_alias':True,'detach_rollback_does_not_restore_alias':True,
                    'native_instance_catalog_visibility_observed':True,
                    'native_creation_ignore_replace_and_missing_ok_verified':True,
                    'native_storage_options_pending_context_and_memory_compression_verified':True,
                    'independently_reopened_file_data_and_block_size_verified':True,
                    'retired_alias_refused_until_explicit_caller_decision':True,
                    'stale_namespace_refused_before_dispatch':True,
                    'review_bound_to_original_native_connection':True,
                    'post_acknowledgement_failure_retained_without_replay':True})
            finally:
                if observer is not None:observer.close()
                client.close()
        proof['complete']=True
    finally:
        (output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',required=True,type=Path)
    qualify(parser.parse_args().evidence)
