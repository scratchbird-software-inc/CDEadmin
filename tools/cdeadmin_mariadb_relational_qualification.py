"""Qualify actual DDN graphical edits through native MariaDB reviewed execution."""
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
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
from pgadmin.cdeadmin.workspace.firebird_relational_review import handoff
from pgadmin.cdeadmin.workspace.mariadb_schema_plan import plan
from pgadmin.cdeadmin.workspace.mariadb_schema_apply import MariaDBSchemaApplications


def qualify(route, evidence, *, password=None):
    import mariadb
    evidence.mkdir(parents=True, exist_ok=False)
    proof = {'complete': False, 'checks': []}
    schema = 'owned_graphical_' + secrets.token_hex(8)
    credentials = {'password':password} if password is not None else {}
    owner = mariadb.connect(**route, autocommit=True, **credentials)
    cursor = owner.cursor(); client = observer = None
    try:
        cursor.execute('CREATE DATABASE `'+schema+'`'); owner.database = schema
        cursor.execute('CREATE TABLE temporal (id INT PRIMARY KEY, value VARCHAR(40)) WITH SYSTEM VERSIONING')
        cursor.execute("INSERT INTO temporal(id,value) VALUES (1,'prior')")
        cursor.execute("UPDATE temporal SET value='current' WHERE id=1")
        cursor.execute('CREATE TABLE periods (begins DATE, ends DATE, PERIOD FOR validity(begins,ends), KEY by_start(begins))')
        native_route, permissions = provider_access(route, password)
        def require(permission, scope=None):
            assert permission in {'data_read','administer'} and scope == 'resource'
        permissions.require = require
        context = SimpleNamespace(pool_namespace='graphical:'+secrets.token_hex(8))
        client = _create_client(MARIADB_PROFILE, permissions, context)
        provider = MariaDBPilotProvider(context, permissions, client)
        selected = {**native_route,'database':schema}
        applications = MariaDBSchemaApplications(evidence/'receipts.json')
        observer = mariadb.connect(**{**route,'database':schema}, autocommit=True, **credentials)
        def capture():
            native = provider.capture_catalog(selected)
            return build_export(native['resources'], endpoint_id='owned', target_id=schema,
                                generation=native['generation'], engine='mariadb')
        def apply_graphical(before, desired, **options):
            value = handoff(before['snapshot'], before['diagram']['snapshot'], desired, engine='mariadb', **options)
            baseline, proposed = [read_catalog(value[key],engine='mariadb') for key in ('baseline','desired')]
            native = provider.capture_catalog(selected)
            live = build_export(native['resources'],endpoint_id='owned',target_id=schema,
                                generation=native['generation'],engine='mariadb',native_model=True)
            preview = plan(baseline,proposed,live)
            assert preview['ready_for_review'], preview
            preview.update(provider.validate_schema_plan(selected,preview))
            assert preview['native_grammar_validated'], preview
            receipt = applications.review(preview,baseline,proposed,'owner','binding',schema)
            result = applications.apply({'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],
                                         'confirmed':True},'owner','binding',lambda record:provider.apply_schema_review(selected,record))
            assert result['state']=='committed' and result['outcome']['rediscovery_verified'], result
            return preview
        before = capture(); desired = deepcopy(before['diagram']['snapshot'])
        source = desired['files']['relations.ddn']
        assert source.count('datatype:"varchar(40)"') == 1
        desired['files']['relations.ddn'] = source.replace('datatype:"varchar(40)"','datatype:"varchar(80)"')
        try:
            handoff(before['snapshot'],before['diagram']['snapshot'],desired,engine='mariadb')
        except ValueError as error:
            assert 'KEEP-history' in str(error)
        else: raise AssertionError('Temporal history acceptance was omitted')
        apply_graphical(before,desired,allow_temporal_history=True)
        observed = observer.cursor(); observed.execute('SELECT value FROM temporal FOR SYSTEM_TIME ALL')
        assert sorted(row[0] for row in observed.fetchall()) == ['current','prior']; observed.close()
        proof['checks'].append('public_ddn_type_edit_requires_keep_and_native_apply_preserves_committed_history')
        before = capture(); desired = deepcopy(before['diagram']['snapshot'])
        source = desired['files']['relations.ddn']
        assert source.count('"begins" {uid:') == 1
        desired['files']['relations.ddn'] = source.replace('"begins" {uid:','"starts" {uid:')
        preview = apply_graphical(before,desired,allow_column_renames=True)
        assert 'CHANGE COLUMN `begins` `starts`' in preview['operations'][0]['source']
        assert 'DROP PERIOD FOR `validity`' in preview['operations'][0]['source']
        assert 'ADD PERIOD FOR `validity`' in preview['operations'][0]['source']
        observed = observer.cursor(); observed.execute('SHOW CREATE TABLE periods'); definition = observed.fetchone()[1]; observed.close()
        assert 'PERIOD FOR `validity` (`starts`, `ends`)' in definition
        assert 'KEY `by_start` (`starts`)' in definition
        proof['checks'].append('stable_field_uid_rename_preserves_native_application_period_and_index')
        proof['complete'] = True
    finally:
        if observer is not None: observer.close()
        if client is not None: client.close()
        cursor.execute('DROP DATABASE IF EXISTS `'+schema+'`'); cursor.close(); owner.close()
        (evidence/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',default='mariadb:12.2.2')
    parser.add_argument('--evidence',type=Path,required=True)
    options = parser.parse_args()
    raise SystemExit(0 if run(options.image,options.evidence,qualify)['complete'] else 1)
