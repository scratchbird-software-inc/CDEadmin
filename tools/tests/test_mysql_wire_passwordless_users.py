"""Passwordless user creation on Dolt and TiDB (owner direction 2026-10-29)."""
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.providers.dolt.provider import (  # noqa: E402
    ADMINISTRATION as DOLT,
)
from pgadmin.cdeadmin.providers.tidb.provider import (  # noqa: E402
    ADMINISTRATION as TIDB,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402
from pgadmin.cdeadmin.visual_admin.catalog import (  # noqa: E402
    catalog_for_engine,
)


def plan(administration, draft):
    request = {'resource_kind': 'user', 'operation_id': 'create',
               'target_resource': None, '_provider_route': {'database': 'x'},
               'draft': {'name': 'u', 'host': '%', **draft}}
    return [statement['source'] for statement in
            administration.plan(request)['command_preview']['statements']]


@pytest.mark.parametrize('administration', [DOLT, TIDB])
def test_passwordless_account_is_explicit(administration):
    assert plan(administration, {'authentication_mode': 'NONE'}) == [
        "CREATE USER 'u'@'%'"]
    assert 'IDENTIFIED BY' in plan(administration, {
        'authentication_mode': 'PASSWORD', 'password': 'pw'})[0]
    # An empty password never silently means "passwordless".
    with pytest.raises(RelationalClientError, match='password is required'):
        plan(administration, {'authentication_mode': 'PASSWORD'})
    with pytest.raises(RelationalClientError, match='cannot also set'):
        plan(administration, {'authentication_mode': 'NONE',
                              'password': 'pw'})


@pytest.mark.parametrize('engine, administration',
                         [('dolt', DOLT), ('tidb', TIDB)])
def test_form_offers_the_mode(engine, administration):
    catalog = administration.catalog(catalog_for_engine(engine))
    form = next(
        operation['form'] for item in catalog['objects']
        if item['resource_kind'] == 'user'
        for operation in item['operations']
        if operation['operation_id'] == 'create')
    fields = {field['field_id']: field for field in form['fields']}
    assert [option['value'] for option in
            fields['authentication_mode']['options']] == ['PASSWORD', 'NONE']
    assert fields['password']['required'] is False
