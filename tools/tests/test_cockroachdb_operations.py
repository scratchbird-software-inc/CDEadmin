"""CockroachDB control-plane operations: what 26.1.3 refuses or needs."""
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

from pgadmin.cdeadmin.providers.cockroachdb.provider import (  # noqa: E402
    ADMINISTRATION,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402

ROUTE = {'host': '127.0.0.1',
         'backup_destination_allowlist': 'nodelocal://1/b/',
         'changefeed_sink_allowlist': 'null://,nodelocal://1/c/'}
TABLE = {'resource_id': 'table:public:t', 'display_name': 't',
         'display_path': ['public', 't'], 'native': {}}
FEED = {'resource_id': 'changefeed:42', 'display_name': '42',
        'display_path': ['42'], 'native': {'sink_uri': 'null://'}}


def plan(kind, operation, draft, target):
    planned = ADMINISTRATION.plan({
        'resource_kind': kind, 'operation_id': operation,
        'target_resource': target, 'draft': draft, '_provider_route': ROUTE})
    return planned['provider_payload']['compiled']['statements']


def test_lease_preferences_take_one_comma_separated_row_each():
    statement = plan('table', 'configure_zone', {
        'lease_preferences': ['+region=a, +zone=b', '+region=c']}, TABLE)[0]
    assert statement['parameters'] == ('[["+region=a","+zone=b"],'
                                       '["+region=c"]]',)


def test_changefeed_table_takes_a_picked_dotted_name():
    assert plan('changefeed', 'add_table', {
        'table_name': 'public.t2', 'initial_scan': 'no'}, FEED)[0][
        'source'] == ('ALTER CHANGEFEED %s ADD TABLE "public"."t2" '
                      "WITH initial_scan = 'no'")


@pytest.mark.parametrize('kind, operation, draft, target, reason', [
    ('table', 'configure_zone', {'range_max_bytes': 1 << 29}, TABLE,
     'together'),
    ('changefeed', 'set_sink', {'sink_uri': 'nodelocal://1/c/x'}, FEED,
     'sink type'),
])
def test_refusals(kind, operation, draft, target, reason):
    with pytest.raises(RelationalClientError, match=reason):
        plan(kind, operation, draft, target)
