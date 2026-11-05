"""Typed MySQL Server controls bind existing native registration inputs."""
import json
from pathlib import Path

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.endpoints.profiles import registration_profile
from pgadmin.cdeadmin.endpoints.service import EndpointService
from ui_descriptor_roundtrip import resolved_form, backend_draft


GENERIC = {'name', 'host', 'port', 'username', 'save_password', 'db', 'connect_now', 'comment', 'bgcolor', 'fgcolor', 'tags'}


def test_every_server_field_resolves_to_existing_registration_input():
    # The completed form (2026-11-05) binds the servers-API keys the registration host sends
    # (cde_route_<id>, cde_secret_<id>), as the other engines' server forms do; each value
    # must reach the persisted route through the registration contract.
    from ui_descriptor_roundtrip import registration_data, registration_route
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
        name=field['field_id'];backend=field.get('backend_field_id',name)
        if backend in GENERIC:continue
        prefix,contract=('cde_secret_',backend[11:]) if backend.startswith('cde_secret_') else ('cde_route_',backend[10:])
        assert backend==prefix+contract and contract==name and contract in declared,name
        value=samples.get(name, field.get('default'))
        if value is None:
            value=(field['options'][0]['value'] if field['control']=='select' else
                   2 if field['control']=='number' else False if field['control']=='boolean' else 'owned-value')
        data=registration_data(form,{**base,name:value})
        if prefix=='cde_secret_':
            assert data[backend]==value,name  # secrets are stored apart from the route
            continue
        route=registration_route(profile,data)
        assert name in route,name
        if name=='tls_ciphersuites':assert route[name]==['TLS_AES_128_GCM_SHA256']
        elif name in samples:assert route[name]==samples[name]
    assert len(descriptor['fields'])==48
    assert not {'SQL'} & {tab['tab'] for tab in form['tabs']}
    assert descriptor['status']=='complete'
    assert [gap['concept'] for gap in descriptor['gaps']]==['Optional authentication runtimes']


def test_failover_does_not_expose_ordinary_storage_for_nested_passwords():
    descriptor=json.loads((Path(__file__).resolve().parents[2]/
        'web/pgadmin/cdeadmin/ui_descriptors/mysql/forms/server.form.json').read_text())
    failover=next(field for field in descriptor['fields'] if field['field_id']=='failover')
    columns = {field['field_id']:field for field in failover['columns']}
    assert 'password' not in columns
    assert {'credential_reference_id','pool_name','pool_size'} <= columns.keys()
    assert columns['credential_reference_id']['control'] == 'reference'
    assert all(field['control']!='json' for field in descriptor['fields'])
