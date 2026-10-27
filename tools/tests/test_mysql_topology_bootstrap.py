"""Bootstrap credentials stay private and native instance rules stay native."""
import json
import uuid

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_topology as native
from pgadmin.cdeadmin.providers.mysql_family import mysql_topology_accounts as accounts


def selected(**changes):
    return native.options({'operation': 'instance.configure_cluster',
        'arguments_json': '[{"clusterAdmin":"`quoted``雪`@`%`","clusterAdminPasswordExpiration":"NEVER"}]',
        'account_password_mode': 'set', 'target_confirmation': str(uuid.uuid4()), **changes})


@pytest.mark.parametrize('operation', ['instance.configure_cluster', 'instance.configure_replica_set'])
def test_only_native_bootstrap_methods_admit_a_separate_password_mode(operation):
    value = selected(operation=operation)
    assert value['account_password_mode'] == 'set'
    assert native.CALLS[operation]['bootstrap'] is True
    assert accounts.bootstrap_name(value) == '`quoted``雪`@`%`'
    assert 'clusterAdminPassword' not in native.parse(value['arguments_json'])[0]


@pytest.mark.parametrize('arguments', ['[]', '[{}]', '[null]', '[{"clusterAdmin":""}]',
    '[{"clusterAdmin":{}}]', '[{"clusterAdmin":"name","clusterAdminPassword":"private"}]'])
def test_password_creation_requires_a_native_account_and_refuses_inline_credentials(arguments):
    with pytest.raises(native.BinlogArchiveError): selected(arguments_json=arguments)


def test_bootstrap_preserve_mode_keeps_native_defaults_and_native_account_text():
    assert selected(account_password_mode='preserve', arguments_json='[]')['account_password_mode'] == 'preserve'
    assert accounts.bootstrap_name(selected(account_password_mode='preserve', arguments_json='[{"clusterAdmin":"name"}]')) == 'name'


def test_omitted_host_uses_the_native_percent_lookup_and_target(monkeypatch):
    calls = []
    def capture(_connection, account, context):
        calls.append((account, context))
        return {'account': dict(account), 'exists': account['host'] == '%',
            'queries': [{'sql': account['host']}], 'results': [[account['host']]]}
    monkeypatch.setattr(accounts, 'capture', capture)
    result = accounts.capture_bootstrap(object(), {'user': 'name', 'host': ''})
    assert calls == [({'user': 'name', 'host': '%'}, 'instance')]
    assert result['exists']
    assert len(result['queries']) == len(result['results']) == 1
