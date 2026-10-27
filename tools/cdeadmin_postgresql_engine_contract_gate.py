"""Owned PostgreSQL18.3 dialect/metrics inventories and native acceptance.

Refresh paired DDN and run this gate from an immutable source snapshot.
Native binaries and reference sources are explicit, independently owned inputs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def metric_gate(route,password,inventory,inventory_path,output):
    import psycopg
    from psycopg import sql
    from pgadmin.cdeadmin.providers.postgresql import metrics
    from pgadmin.cdeadmin.providers.postgresql.monitoring import PostgreSQLMonitor
    from pgadmin.cdeadmin.security import SecretLease
    from psycopg.rows import tuple_row
    arguments={'host':route['host'],'port':route['port'],'user':route['user'],'dbname':route['database'],'password':password,**route['connection_params']}
    mapping={entry['endpoint_id']:entry for entry in inventory['endpoints']}
    original=metrics.inventory;metrics.inventory=lambda:mapping
    result={'complete':False,'inventory_sha256':hashlib.sha256(inventory_path.read_bytes()).hexdigest(),'checks':[],
            'native_version':'18.3','history_testing':'not run','sample_sources':{}}
    source=limited=None
    permissions=SimpleNamespace(acquire_secret=lambda *_args:SecretLease(password))
    collector_route={**route,'principal_reference':'worker:native-metrics-contract','credential_reference_id':'owned-password'}
    try:
        with psycopg.connect(**arguments,autocommit=True,row_factory=tuple_row) as control:
            control.execute(sql.SQL('ALTER SYSTEM SET primary_conninfo={}').format(sql.Literal('host=127.0.0.1 password=native-metric-credential-canary')))
            control.execute('SELECT pg_reload_conf()')
            deadline=time.monotonic()+5
            while 'native-metric-credential-canary' not in control.execute("SELECT setting FROM pg_settings WHERE name='primary_conninfo'").fetchone()[0]:
                if time.monotonic()>deadline:raise RuntimeError('Owned credential-redaction fixture did not reload')
                time.sleep(.05)
            control.execute("SELECT 'native-observer-sql-canary'")
            source=PostgreSQLMonitor(permissions,collector_route,scope='server',native_metric_sources=tuple(mapping))
            sample=source.sample()
            if not sample.get('transaction_completed'):
                (output/'failed-native-metrics.json').write_text(json.dumps(sample,indent=2)+'\n');raise RuntimeError('Owned native metrics sample failed')
            families=sample['groups']['native_metrics']
            if set(families['sources'])!=set(mapping):raise AssertionError('Native metric family coverage differs')
            for name,frame in families['sources'].items():
                if frame['status'] not in {'available','partial'}:
                    (output/'failed-native-metrics.json').write_text(json.dumps(sample,indent=2)+'\n');raise AssertionError('Native metrics source unavailable: '+name)
                assert [column['name'] for column in frame['columns']]==[column['name'] for column in mapping[name]['columns']]
                assert len(frame['rows'])<=metrics.ROW_LIMIT
                for row in frame['rows']:
                    for column,value in zip(frame['columns'],row):
                        if column['redaction']=='query_or_credential_text':assert value is None
                result['sample_sources'][name]={'status':frame['status'],'rows':frame['visible_row_count'],'truncated':frame['truncated']}
            assert int(families['row_bytes_returned'])<=metrics.BYTE_LIMIT
            assert 'native-metric-credential-canary' not in json.dumps(families)
            assert 'native-observer-sql-canary' not in json.dumps(families)
            assert source._connection.info.backend_pid!=control.info.backend_pid
            assert source._connection.info.transaction_status==0
            result['checks'].append('all-native-view-projections-execute-on-an-independent-read-only-collector-with-explicit-row-and-byte-limits')
            result['checks'].append('query-and-credential-fields-are-redacted-without-dropping-native-columns-or-owning-rows')
            role='sr_native_metric_reader'
            control.execute(sql.SQL('CREATE ROLE {}').format(sql.Identifier(role)))
            try:
                limited=PostgreSQLMonitor(permissions,{**collector_route,'role':role},scope='database',native_metric_sources=tuple(mapping))
                restricted=limited.sample();assert restricted['transaction_completed']
                frames=restricted['groups']['native_metrics']['sources'];assert set(frames)==set(mapping)
                assert any(frame['status']=='denied' for frame in frames.values())
                assert all(frame['sqlstate']=='42501' for frame in frames.values() if frame['status']=='denied')
                assert limited._connection.info.transaction_status==0
                result['restricted_sources']={name:frame['status'] for name,frame in frames.items()}
                result['checks'].append('restricted-native-families-report-permission-denial-and-savepoints-preserve-the-collector-transaction')
            finally:
                if limited is not None:limited.close();limited=None
                control.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))
            result.update(complete=True,family_count=len(mapping),native_observation_count=sum(len(item['columns']) for item in mapping.values()))
    finally:
        if source is not None:source.close()
        if limited is not None:limited.close()
        metrics.inventory=original
        (output/'native-metrics-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def qualify(output,binary_path,reference_source,archive):
    from postgresql_qualification_support import local_server
    from tools.reference_engine_demos.generate_postgresql_dialect_inventory import generate as dialect_inventory
    from tools.reference_engine_demos.generate_postgresql_metrics_inventory import generate as metrics_inventory
    output=Path(output).resolve();reference_source=Path(reference_source).resolve();archive=Path(archive).resolve()
    if output==ROOT or ROOT in output.parents or output==reference_source or reference_source in output.parents:
        raise ValueError('Evidence belongs outside source trees')
    if 'AC_INIT([PostgreSQL], [18.3]' not in (reference_source/'configure.ac').read_text():raise ValueError('Select the pinned PostgreSQL18.3 source')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    proof={'complete':False,'history_testing':'not run','qualification_scope':'exact native SQL compiler and core statistics contracts; full product/platform/form acceptance separate'}
    try:
        with local_server(output/'fixture',binary_path) as (route,password,fixture):
            import psycopg
            arguments={'host':route['host'],'port':route['port'],'user':route['user'],'dbname':route['database'],'password':password,**route['connection_params']}
            with psycopg.connect(**arguments,autocommit=True) as connection:
                dialect=dialect_inventory(reference_source,connection,archive)
                metrics=metrics_inventory(reference_source,connection)
            di=output/'postgresql_dialect_inventory_18_3.json';mi=output/'postgresql_metrics_inventory_18_3.json'
            di.write_text(json.dumps(dialect,indent=2,ensure_ascii=False)+'\n');mi.write_text(json.dumps(metrics,indent=2,ensure_ascii=False)+'\n')
            from cdeadmin_postgresql_driver_platform_gate import qualify as driver_gate
            native=driver_gate(route,password,output/'native',native_transform=True,server_files=True)
            if not native['complete']:raise RuntimeError('Native PostgreSQL task qualification failed')
            measured=metric_gate(route,password,metrics,mi,output)
            if not measured['complete']:raise RuntimeError('Native PostgreSQL metrics qualification failed')
            from tools.reference_engine_demos.generate_postgresql_contracts import generate
            contracts=generate(di,mi,output/'native/summary.json',output/'native-metrics-receipt.json',ROOT)
            for filename,document in zip(('postgresql_dialect_18_3.json','postgresql_metrics_18_3.json'),contracts):
                (output/filename).write_text(json.dumps(document,indent=2,ensure_ascii=False)+'\n')
            proof.update(complete=True,native_task_count=len(contracts[0]['task_templates']),native_driver_checks=len(native['checks']),
                metric_families=measured['family_count'],native_observations=measured['native_observation_count'])
        assert fixture['owned_server_stopped']
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('evidence','binary-path','reference-source','source-archive'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();qualify(args.evidence,args.binary_path,args.reference_source,args.source_archive)
