"""Database fields bind native DDL and preserve observed native options."""
from pathlib import Path
import json
import pytest
from types import SimpleNamespace

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MYSQL_PROFILE, _resources
from pgadmin.cdeadmin.providers.form_contracts import provider_form_contract
from ui_descriptor_roundtrip import resolved_form, record_draft, backend_draft


def test_database_descriptor_is_the_endpoint_and_visual_native_field_source():
    root=Path(__file__).resolve().parents[2]/'web/pgadmin/cdeadmin/ui_descriptors/mysql'
    document=json.loads((root/'forms/database.form.json').read_text())
    forms=provider_form_contract({'profile_id':'mysql-native','engine_id':'mysql','display_name':'MySQL',
        'route_kind':'network','connection_fields':[],'secret_fields':[]})['database']['forms']
    target={'display_name':'owned','display_path':['owned']}
    for mode in ('create','alter'):
        expected={f['field_id'] for f in document['fields'] if mode in f.get('modes',['create','alter'])}
        assert {f['field_id'] for f in forms[mode]['fields']}==expected
        base={'name':'owned'} if mode=='create' else {'character_set':'utf8mb4'}
        samples={'name':'changed','if_not_exists':True,'character_set':'latin1','collation':'latin1_bin','encryption':'Y','read_only':'ON'}
        for field in document['fields']:
            if mode not in field.get('modes',['create','alter']):continue
            draft={**base,field['field_id']:samples[field['field_id']]}
            request={'resource_kind':'database','operation_id':mode,'draft':draft,'target_resource':target}
            assert not MYSQL_ADMINISTRATION.validate(request)['errors'],field['field_id']
            request['_provider_route']={'host':'owned','user':'root'}
            actual=MYSQL_ADMINISTRATION.plan(request)['provider_payload']['compiled']['statements']
            original=MYSQL_ADMINISTRATION.plan({**request,'draft':base})['provider_payload']['compiled']['statements']
            assert actual!=original,field['field_id']


def test_shared_record_projection_preserves_native_encryption_and_read_only():
    form=resolved_form('mysql','database')
    for encryption,expected in [('YES','Y'),('NO','N')]:
        baseline=record_draft(form,{'default_character_set':'utf8mb4','default_collation':'utf8mb4_bin',
            'default_encryption':encryption,'read_only':'ON'})
        assert baseline=={'character_set':'utf8mb4','collation':'utf8mb4_bin','encryption':expected,'read_only':'ON'}
        assert backend_draft(form,baseline,mode='alter')==baseline
    assert 'read_only' not in record_draft(form,{'database_options_state':'unavailable'})


class CatalogConnection:
    def __init__(self,definition=None,denied=False):self.definition=definition;self.denied=denied
    def cursor(self):
        owner=self
        class Cursor:
            description=[]
            def execute(self,sql,parameters=()):
                self.rows=[]
                if 'FROM information_schema.SCHEMATA ORDER BY' in sql:self.rows=[('db`literal','utf8mb4','utf8mb4_bin','NO')]
                elif sql.startswith('SHOW CREATE DATABASE '):
                    assert sql=='SHOW CREATE DATABASE `db``literal`'
                    if owner.denied:
                        error=RuntimeError('owned denied native observation');error.errno=1227;error.sqlstate='42000';raise error
                    self.rows=[('db`literal',owner.definition)]
            def fetchall(self):return self.rows
            def fetchone(self):return self.rows[0] if self.rows else None
            def close(self):pass
        return Cursor()


@pytest.mark.parametrize('suffix,state',[('','OFF'),(' /* READ ONLY = 1 */','ON')])
def test_catalog_reports_only_successfully_observed_native_database_state(suffix,state):
    rows=_resources(CatalogConnection('CREATE DATABASE `db``literal` /*!80016 DEFAULT ENCRYPTION=\'N\' */'+suffix),{},MYSQL_PROFILE)
    native=next(row['native'] for row in rows if row['resource_kind']=='database')
    assert native['database_options_state']=='observed' and native['read_only']==state


def test_failed_database_option_observation_never_becomes_writable():
    rows=_resources(CatalogConnection(denied=True),{},MYSQL_PROFILE)
    native=next(row['native'] for row in rows if row['resource_kind']=='database')
    assert native['database_options_state']=='unavailable' and 'read_only' not in native
