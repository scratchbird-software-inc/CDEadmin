"""Typed MySQL Server controls bind existing native registration inputs."""
import json
from pathlib import Path

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.endpoints.profiles import registration_profile
from pgadmin.cdeadmin.endpoints.service import EndpointService
from ui_descriptor_roundtrip import resolved_form, backend_draft


def test_every_server_field_resolves_to_existing_registration_input():
    descriptor=json.loads((Path(__file__).resolve().parents[2]/
        'web/pgadmin/cdeadmin/ui_descriptors/mysql/forms/server.form.json').read_text())
    profile=registration_profile('mysql-native')
    declared={f['field_id'] for f in profile['form_contract']['server']['forms']['edit']['fields']}
    form=resolved_form('mysql','server')
    base={'name':'Owned profile','host':'127.0.0.1','port':3306}
    samples={'failover':[{'host':'127.0.0.2','port':3307,'priority':50}],
        'tls_versions':['TLSv1.2','TLSv1.3'],'tls_ciphersuites':[{'value':'TLS_AES_128_GCM_SHA256'}],
        'conn_attrs':{'application':'owned-test'},'charset':'utf8mb4','collation':'utf8mb4_bin',
        'sql_mode':'ANSI_QUOTES','time_zone':'+00:00','init_command':'SET @owned=1'}
    for field in descriptor['fields']:
        name=field['field_id'];assert field.get('backend_field_id',name) in declared,name
        value=samples.get(name, field.get('default'))
        if value is None:
            value=(field['options'][0]['value'] if field['control']=='select' else
                   2 if field['control']=='number' else False if field['control']=='boolean' else 'owned-value')
        draft=backend_draft(form,{**base,name:value},mode='alter')
        admitted=EndpointService._server_form_values(profile,'edit',draft)
        assert name in admitted,name
        if name=='tls_ciphersuites':assert admitted[name]==['TLS_AES_128_GCM_SHA256']
        elif name in samples:assert admitted[name]==samples[name]
    assert len(descriptor['fields'])==41
    assert not {'SQL'} & {tab['tab'] for tab in form['tabs']}
    assert descriptor['status']=='draft' and descriptor['gaps']


def test_failover_does_not_expose_ordinary_storage_for_nested_passwords():
    descriptor=json.loads((Path(__file__).resolve().parents[2]/
        'web/pgadmin/cdeadmin/ui_descriptors/mysql/forms/server.form.json').read_text())
    failover=next(field for field in descriptor['fields'] if field['field_id']=='failover')
    assert not {'password','pool_name','pool_size'} & {field['field_id'] for field in failover['columns']}
    assert all(field['control']!='json' for field in descriptor['fields'])
