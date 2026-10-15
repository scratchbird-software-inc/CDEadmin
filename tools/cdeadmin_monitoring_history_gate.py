#!/usr/bin/env python3
"""Native archive roundtrip qualification. Uses a unique disposable namespace."""
import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'web'))
from tools.cdeadmin_firebird_admin_mapping_gate import _create_client  # noqa: F401,E402
from pgadmin.cdeadmin.workspace.monitoring import MonitoringPolicy  # noqa: E402
from pgadmin.cdeadmin.workspace.monitoring_history import configured_history, MonitoringHistory  # noqa: E402


def run(config, initialize=False):
    config = {**config, 'namespace': 'qualification-' + uuid.uuid4().hex}
    store = configured_history(SimpleNamespace(config={'CDEADMIN_MONITORING_HISTORY': config}))
    if store is None:
        raise ValueError('History must be enabled')
    if initialize:
        store.initialize()
    now = int(time.time())
    iso = lambda value: datetime.fromtimestamp(value, timezone.utc).isoformat()
    policy = MonitoringPolicy(1, 'native-gate', 'database', history_enabled=True)
    sample = {'sample_id': str(uuid.uuid4()), 'ended_at': iso(now),
              'source_epoch': 'epoch1', 'coverage': 'visible-to-collector',
              'status': 'available', 'groups': {'memory': {'values': {'used': '9007199254740993'}}}}
    store.write(policy, 'firebird', 'revision', 'route', sample)
    store.write(policy, 'firebird', 'revision', 'route', sample)
    restarted = MonitoringHistory(store.connect, namespace=store.namespace)
    args = {'start': iso(now-10), 'end': iso(now+10)}
    result = restarted.query(policy, 'firebird', **args)
    assert len(result['samples']) == 1
    assert result['samples'][0]['groups']['memory']['values']['used'] == '9007199254740993'
    assert not restarted.query(MonitoringPolicy(2, 'native-gate', 'database'), 'firebird', **args)['samples']
    restarted.write(policy, 'firebird', 'revision', 'route', {**sample, 'sample_id': str(uuid.uuid4()), 'source_epoch': 'epoch2'})
    rollups = restarted.query(policy, 'firebird', tier='rollup', **args)['samples']
    assert len(rollups) == 2
    assert all(item['rates']['status'] == 'gap' for item in rollups)
    page = restarted.query(policy, 'firebird', limit=1, **args)
    assert page['next']
    assert len(restarted.query(policy, 'firebird', after=page['next'], **args)['samples']) == 1
    # Expire only this gate's private namespace; never modify other deployments.
    restarted.clock = lambda: now + 91*86400
    restarted.maintain()
    assert not restarted.query(policy, 'firebird', **args)['samples']
    return {'status': 'passed', 'checks': ['native-commit', 'restart-read', 'exact-integers',
             'idempotency', 'owner-isolation', 'epoch-separated-rollups', 'pagination', 'retention']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--initialize', action='store_true', help='Create schema once in a dedicated new database')
    options = parser.parse_args()
    try:
        result = run(json.loads(options.config.read_text()), options.initialize)
    except Exception as error:
        result = {'status': 'failed', 'error_type': type(error).__name__, 'phase': getattr(error, 'phase', 'qualification')}
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
