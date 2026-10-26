"""Independent grants and stable channel identities across catalog observations."""
from copy import deepcopy
import json

import pytest

from test_mysql_channel_catalog import Channels, facts
from pgadmin.cdeadmin.providers.mysql_family import mysql_server_catalog as catalog
from pgadmin.cdeadmin.providers.mysql_family.installed_catalog import APPLIER_COLUMNS, CHANNEL_OBSERVATIONS
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE, _resources
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
from pgadmin.cdeadmin.workspace.mysql_server_plan import address, state, SPEC

QUERIES = dict(CHANNEL_OBSERVATIONS)


def configuration(name):
    return dict(zip((key.lower() for key in APPLIER_COLUMNS), [
        name, 17, "'policy\\'雪@user'@'%'", 'YES', 'GENERATE', 'UUID', '01234567-89ab-cdef-0123-456789abcdef']))


class Observed(Channels):
    def __init__(self, name='', receiver=True, config=True, status=True):
        super().__init__([facts(name)] if receiver else [], denied=not receiver)
        self.observed = {'applier_configuration': [configuration(name)] if config else None,
            'applier': [{'channel_name':name,'service_state':'ON','remaining_delay':None,
                         'count_transactions_retries':str(2**64-1)}] if status else None}

    def cursor(self, **options):
        cursor = super().cursor(**options); execute = cursor.execute
        def selected(source, parameters=None):
            key = next((key for key, query in QUERIES.items() if query == source), None)
            if key not in self.observed:
                return execute(source, parameters)
            self.calls.append(source); rows = self.observed[key]
            if rows is None:
                error = RuntimeError('Private native denial detail'); error.errno = 1142; error.sqlstate = '42000'; raise error
            cursor.description = [(key,) for key in rows[0]]
            cursor.rows = [tuple(row.values()) for row in rows]
        cursor.execute = selected
        return cursor


def restored(captured):
    export = build_export(captured['resources'], endpoint_id='ep', target_id='server:server-id',
                          generation=captured['generation'], engine='mysql')
    return read_catalog(json.dumps(export['snapshot']), engine='mysql')


@pytest.mark.parametrize('receiver', [True, False])
@pytest.mark.parametrize('config', [True, False])
@pytest.mark.parametrize('status', [True, False])
def test_each_native_table_can_be_visible_independently_without_erasing_other_channel_facts(receiver, config, status):
    connection = Observed(receiver=receiver, config=config, status=status)
    rows = _resources(connection, {'route':{}}, MYSQL_PROFILE)
    channels = [row for row in rows if row['resource_kind']=='replication-channel']
    assert len(channels)==int(receiver or config or status)
    captured = catalog.capture(Observed(receiver=receiver, config=config, status=status))
    exchanged = [row for row in restored(captured)['rows'].values() if row['kind']=='replication-channel']
    assert len(exchanged)==len(channels)
    if not channels: return
    native = channels[0]['native']; row = exchanged[0]; values = row['native']['catalog_row']
    address(row, 'server-id')
    assert row['native']['section']=='replication-channels' and native['channel_name']==values['channel_name']==''
    assert native['replication_password_returned'] is False
    if receiver:
        assert all(native[key]==value==values[key] for key,value in facts().items())
    else:
        assert 'host' not in native and 'host' not in values
    if config:
        assert native['applier_configuration']==values['applier_configuration']==configuration('')
    else:
        assert 'applier_configuration' not in native and 'applier_configuration' not in values
    if status:
        assert native['applier']==row['native']['applier']
        assert native['applier']['count_transactions_retries']==str(2**64-1)
    else:
        assert 'applier' not in native and 'applier' not in row['native']
    assert 'applier' not in values  # Status must not become configuration.


@pytest.mark.parametrize('name', ['', 'group_replication_applier'])
def test_applier_only_channel_discovery_keeps_the_same_identity_and_reserved_namespace_boundary(name):
    def inspect(connection):
        return next(row for row in _resources(connection, {'route':{}}, MYSQL_PROFILE)
                    if row['resource_kind']=='replication-channel')
    partial = inspect(Observed(name, receiver=False)); full = inspect(Observed(name))
    assert partial['resource_id']==full['resource_id']
    if name.startswith('group_replication_'):
        assert partial['native']['administration']['allowed_operations']==['inspect']
    else:
        assert partial['display_name']=='Default channel'


def test_transient_status_does_not_change_migration_state_but_applier_configuration_does():
    row = next(row for row in restored(catalog.capture(Observed()))['rows'].values() if row['kind']=='replication-channel')
    baseline = state(row); changed = deepcopy(row)
    changed['native']['applier']['service_state']='OFF'
    changed['native']['applier']['count_transactions_retries']='0'
    assert state(changed)==baseline
    changed['native']['catalog_row']['applier_configuration']['desired_delay']=0
    assert state(changed)!=baseline
    assert not any('applier' in key for key in SPEC)  # Observations are not object kinds.


def test_native_projection_preserves_nullable_policy_and_exact_status_fields_without_joins_or_error_text():
    assert len(APPLIER_COLUMNS)==len(set(APPLIER_COLUMNS))==7
    assert all('JOIN' not in query and 'LAST_ERROR_MESSAGE' not in query for query in QUERIES.values())
    assert 'CAST(COUNT_TRANSACTIONS_RETRIES AS CHAR)' in QUERIES['applier']
    assert 'CAST(LAST_ERROR_TIMESTAMP AS CHAR)' in QUERIES['receiver']
