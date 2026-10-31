"""YugabyteDB yb-admin operations: arguments, records and refusals."""
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

from pgadmin.cdeadmin.providers.yugabytedb import control_plane  # noqa: E402
from pgadmin.cdeadmin.providers.yugabytedb.provider import (  # noqa: E402
    ADMINISTRATION,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402

ROUTE = {'host': '127.0.0.1', 'database': 'd', 'yb_admin_path': '/bin/true',
         'master_addresses': 'node:7100'}
TABLE = {'resource_id': 'table:public:t', 'display_name': 't',
         'display_path': ['public', 't'], 'native': {}}


def arguments(kind, operation, draft, target=None):
    planned = ADMINISTRATION.plan({
        'resource_kind': kind, 'operation_id': operation, 'draft': draft,
        'target_resource': target, '_provider_route': ROUTE})
    return planned['provider_payload']['compiled']['provider_action'][
        'arguments']


def test_namespaces_are_typed():
    assert arguments('schedule', 'create', {
        'interval_minutes': 60, 'retention_minutes': 120,
        'namespace': 'd'})[-1] == 'ysql.d'
    assert arguments('schedule', 'create', {
        'interval_minutes': 60, 'retention_minutes': 120,
        'namespace': 'ks', 'namespace_type': 'ycql'})[-1] == 'ycql.ks'
    # An already-prefixed name (the full live gate's) is kept.
    assert arguments('changefeed', 'create', {
        'namespace': 'ysql.d'})[1] == 'ysql.d'


def test_placement_rows_and_flush():
    assert arguments('placement-policy', 'configure', {
        'placements': [{'cloud': 'c', 'region': 'r', 'zone': 'z',
                        'min_num_replicas': 1},
                       {'cloud': 'c', 'region': 'r', 'zone': 'y'}],
        'replication_factor': 2}) == [
        'modify_placement_info', 'c.r.z:1,c.r.y', '2']
    assert arguments('table', 'flush', {'timeout_seconds': 30},
                     TABLE) == ['flush_table', 'ysql.d', 't', '30']


def test_rejections_carry_the_tools_error_line():
    assert control_plane._reason(
        "Error running x: Invalid argument: Namespace 'n' not found\n"
        'Usage: yb-admin x <keyspace>\n') == (
        ": Error running x: Invalid argument: Namespace 'n' not found")
    assert control_plane._reason('') == ''


def test_stream_and_schedule_records():
    text = '''CDC Streams:
streams {
  stream_id: "46d0bb2812b781ad374fbdd676b67c1f"
  options {
    key: "checkpoint_type"
    value: "EXPLICIT"
  }
  options {
    key: "record_type"
    value: "ALL"
  }
  options {
    key: "state"
    value: "DELETING_METADATA"
  }
  namespace_id: "00004038000030008000000000000000"
  cdcsdk_consistent_snapshot_option: NOEXPORT_SNAPSHOT
  cdcsdk_disable_dynamic_table_addition: true
}
'''
    assert control_plane.changefeed_streams(text) == [{
        'stream_id': '46d0bb2812b781ad374fbdd676b67c1f',
        'checkpoint_type': 'EXPLICIT', 'record_type': 'ALL',
        'source_type': None, 'state': 'DELETING_METADATA',
        'namespace_id': '00004038000030008000000000000000',
        'snapshot_mode': 'NOEXPORT_SNAPSHOT', 'dynamic_tables': False}]
    facts = control_plane.schedule_facts({'id': 's', 'options': {
        'filter': 'ysql.d', 'interval': '60 min', 'retention': '120 min'}})
    assert (facts['namespace'], facts['namespace_type'],
            facts['interval_minutes'], facts['retention_minutes']) == (
        'd', 'ysql', 60, 120)


@pytest.mark.parametrize('kind, operation, draft, reason', [
    ('schedule', 'create', {'interval_minutes': 60, 'retention_minutes': 1,
                            'namespace': 'd', 'namespace_type': 'x'},
     # The shared control-plane check refuses an undeclared choice first.
     'request is invalid'),
    ('placement-policy', 'configure', {
        'placements': [{'cloud': 'c', 'region': 'r'}],
        'replication_factor': 1}, 'cloud, region and zone'),
])
def test_refusals(kind, operation, draft, reason):
    with pytest.raises(RelationalClientError, match=reason):
        arguments(kind, operation, draft)
