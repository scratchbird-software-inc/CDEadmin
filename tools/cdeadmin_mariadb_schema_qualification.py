"""Native MariaDB temporal/check diff, PREPARE and durable reviewed table apply."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import secrets
from types import SimpleNamespace
from tools.cdeadmin_mariadb_driver_gate import run
from tools.mysql_driver_gate_support import provider_access
from pgadmin.cdeadmin.providers.mysql_family.provider import MariaDBPilotProvider, MARIADB_PROFILE, _create_client
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.mariadb_schema_plan import plan
from pgadmin.cdeadmin.workspace.mariadb_schema_apply import MariaDBSchemaApplications


def qualify(route, evidence, *, password=None):
    import mariadb
    evidence.mkdir(parents=True, exist_ok=False)
    proof = {'complete': False, 'checks': []}
    schema = 'owned_schema_'+secrets.token_hex(8)
    owner = mariadb.connect(**route, autocommit=True, **({'password': password} if password is not None else {}))
    cursor, client, observer = owner.cursor(), None, None
    try:
        cursor.execute('CREATE DATABASE `'+schema+'`'); owner.database = schema
        cursor.execute('CREATE TABLE temporal (id INT, value VARCHAR(40), CONSTRAINT positive CHECK (id>0)) WITH SYSTEM VERSIONING')
        cursor.execute("INSERT INTO temporal(id,value) VALUES (1,'prior')")
        cursor.execute("UPDATE temporal SET value='current' WHERE id=1")
        cursor.execute('CREATE TABLE periods (id INT, begins DATE, ends DATE, PERIOD FOR validity(begins,ends))')
        native_route, permissions = provider_access(route, password)
        def require(permission, scope=None):
            assert permission in {'data_read', 'administer'} and scope == 'resource'
        permissions.require = require
        context = SimpleNamespace(pool_namespace='schema:'+secrets.token_hex(8))
        client = _create_client(MARIADB_PROFILE, permissions, context)
        provider = MariaDBPilotProvider(context, permissions, client)
        selected = {**native_route, 'database': schema}
        def capture():
            native = provider.capture_catalog(selected)
            return build_export(native['resources'], endpoint_id='owned', target_id=schema,
                generation=native['generation'], engine='mariadb', native_model=True)
        def table(document, name): return next(row for row in document['rows'].values() if row['kind']=='table' and row['name']==name)
        before = capture(); desired = deepcopy(before)
        definition = table(desired, 'temporal')['native']['definition']
        table(desired, 'temporal')['native']['definition'] = definition.replace('`value` varchar(40)', '`value` varchar(80)')
        assert not plan(before, desired, before)['ready_for_review']
        table(desired, 'temporal')['native']['mariadb_change'] = {'temporal_history':'KEEP'}
        preview = plan(before, desired, before)
        assert preview['ready_for_review'] and 'PERIOD FOR' not in preview['operations'][0]['source']
        preview.update(provider.validate_schema_plan(selected, preview))
        assert preview['native_grammar_validated'] and not preview['executed']
        assert 'varchar(40)' in table(capture(), 'temporal')['native']['definition']
        proof['checks'].append('native_prepare_preserves_system_time_and_has_no_ddl_effect')
        applications = MariaDBSchemaApplications(evidence/'receipts.json')
        receipt = applications.review(preview, before, desired, 'owner', 'binding', schema)
        request = {'review_id': receipt['review_id'], 'review_digest': receipt['review_digest'], 'confirmed': True}
        result = applications.apply(request, 'owner', 'binding', lambda record: provider.apply_schema_review(selected, record))
        assert result['state']=='committed' and result['outcome']['rediscovery_verified'], result
        observer = mariadb.connect(**{**route, 'database': schema}, autocommit=True, **({'password': password} if password is not None else {}))
        observed = observer.cursor(); observed.execute('SHOW CREATE TABLE temporal'); source = observed.fetchone()[1]; observed.close()
        observed = observer.cursor(); observed.execute('SELECT value FROM temporal FOR SYSTEM_TIME ALL'); values=sorted(row[0] for row in observed.fetchall()); observed.close()
        assert values == ['current','prior'], values
        assert 'varchar(80)' in source and 'WITH SYSTEM VERSIONING' in source and 'positive' in source
        proof['checks'].append('reviewed_native_alter_commits_and_independent_observer_retains_temporal_history_contract')
        before = capture(); desired = deepcopy(before)
        # Native CHECK removal uses DROP CONSTRAINT, not MySQL DROP CHECK.
        row = table(desired, 'temporal'); row['native']['definition'] = row['native']['definition'].replace(',\n  CONSTRAINT `positive` CHECK (`id` > 0)', '')
        row['native']['mariadb_change'] = {'temporal_history':'KEEP'}
        preview = plan(before, desired, before)
        assert 'DROP CONSTRAINT `positive`' in preview['operations'][0]['source'], preview
        preview.update(provider.validate_schema_plan(selected, preview)); assert preview['native_grammar_validated']
        receipt = applications.review(preview, before, desired, 'owner', 'binding', schema)
        result = applications.apply({'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True}, 'owner', 'binding', lambda record: provider.apply_schema_review(selected, record))
        assert result['state']=='committed' and 'positive' not in table(capture(), 'temporal')['native']['definition'], result
        proof['checks'].append('native_named_check_removal_uses_mariadb_drop_constraint')
        before = capture(); desired = deepcopy(before)
        row = table(desired, 'periods'); import re
        row['native']['definition'] = re.sub(r',\n  PERIOD FOR `validity` \(`begins`, `ends`\)', '', row['native']['definition'])
        row['native']['mariadb_change'] = {'drop_periods':['validity']}
        preview = plan(before, desired, before)
        assert 'DROP PERIOD FOR `validity`' in preview['operations'][0]['source'], preview
        preview.update(provider.validate_schema_plan(selected, preview)); assert preview['native_grammar_validated']
        receipt = applications.review(preview, before, desired, 'owner', 'binding', schema)
        result = applications.apply({'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True}, 'owner', 'binding', lambda record: provider.apply_schema_review(selected, record))
        assert result['state']=='committed' and 'PERIOD FOR' not in table(capture(), 'periods')['native']['definition'], result
        proof['checks'].append('native_application_period_drop_requires_exact_intent_and_is_independently_committed')
        # Recheck drift after review on a separate native connection.
        before = capture(); desired = deepcopy(before)
        table(desired, 'periods')['native']['definition'] = table(desired, 'periods')['native']['definition'].replace('`id` int(11)', '`id` bigint')
        preview = plan(before, desired, before); preview.update(provider.validate_schema_plan(selected, preview))
        receipt = applications.review(preview, before, desired, 'owner', 'binding', schema)
        cursor.execute('ALTER TABLE periods ADD COLUMN concurrent_change INT')
        result = applications.apply({'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True}, 'owner', 'binding', lambda record: provider.apply_schema_review(selected, record))
        assert result['state']=='not_dispatched', result
        proof['checks'].append('post_review_native_baseline_drift_prevents_dispatch')
        before = capture(); desired = deepcopy(before)
        row = deepcopy(table(before, 'periods'))
        parent = row['native']['navigator_parent_resource_id']
        key = 'mariadb:'+json.dumps([schema,'table',parent,'created_from_ddn'],separators=(',',':'))
        row.update(resource_id=key,name='created_from_ddn',path=[schema,'created_from_ddn'])
        row['native']['definition']='CREATE TABLE `created_from_ddn` (`id` INT PRIMARY KEY) ENGINE=InnoDB'
        desired['rows'][key]=row
        preview=plan(before,desired,before);preview.update(provider.validate_schema_plan(selected,preview))
        receipt=applications.review(preview,before,desired,'owner','binding',schema)
        result=applications.apply({'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True},'owner','binding',lambda record:provider.apply_schema_review(selected,record))
        assert result['state']=='committed' and table(capture(),'created_from_ddn'),result
        before=capture();desired=deepcopy(before)
        table(desired,'created_from_ddn')['native']['mariadb_change']={'action':'drop','confirmation':'created_from_ddn'}
        preview=plan(before,desired,before);preview.update(provider.validate_schema_plan(selected,preview))
        receipt=applications.review(preview,before,desired,'owner','binding',schema)
        result=applications.apply({'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True},'owner','binding',lambda record:provider.apply_schema_review(selected,record))
        assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
        proof['checks'].append('native_explicit_create_and_confirmed_drop_revalidate_absence_and_rediscover')
        for name in ('batch_a','batch_b'):cursor.execute('CREATE TABLE `'+name+'` (id INT)')
        before=capture();desired=deepcopy(before)
        for name in ('batch_a','batch_b'):table(desired,name)['native']['definition']+=" COMMENT='reviewed batch'"
        preview=plan(before,desired,before);preview.update(provider.validate_schema_plan(selected,preview))
        receipt=applications.review(preview,before,desired,'owner','binding',schema)
        cursor.execute("ALTER TABLE batch_b COMMENT='external drift'")
        request={'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True}
        result=applications.apply(request,'owner','binding',lambda record:provider.apply_schema_review(selected,record))
        assert result['state']=='partially_committed' and result['outcome']['completed_statements']==1,result
        assert 'reviewed batch' in table(capture(),'batch_a')['native']['definition']
        assert 'external drift' in table(capture(),'batch_b')['native']['definition']
        def no_replay(record):raise AssertionError('Completed native prefix was replayed')
        assert applications.apply(request,'owner','binding',no_replay)['state']=='partially_committed'
        proof['checks'].append('native_batch_retains_committed_prefix_after_later_baseline_drift_without_replay')
        proof['complete'] = True
    finally:
        if observer is not None: observer.close()
        if client is not None: client.close()
        cursor.execute('DROP DATABASE IF EXISTS `'+schema+'`'); cursor.close(); owner.close()
        (evidence/'summary.json').write_text(json.dumps(proof, indent=2)+'\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='mariadb:12.2.2')
    parser.add_argument('--evidence', type=Path, required=True)
    options = parser.parse_args()
    raise SystemExit(0 if run(options.image, options.evidence, qualify)['complete'] else 1)
