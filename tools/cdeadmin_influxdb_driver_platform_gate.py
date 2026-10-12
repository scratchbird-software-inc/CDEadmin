#!/usr/bin/env python3
"""Native InfluxDB retained HTTP session and streaming qualification."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/tests'))
import test_cdeadmin_clickhouse_provider  # noqa: E402,F401
from pgadmin.cdeadmin.providers.influxdb.provider import (  # noqa: E402
    create_provider)
from pgadmin.cdeadmin.security import SecretLease  # noqa: E402


def run(route, evidence, password=None):
    evidence = Path(evidence).resolve()
    if ROOT == evidence or ROOT in evidence.parents:
        raise ValueError('Use an external evidence directory')
    evidence.mkdir(parents=True, exist_ok=False)
    proof = {'complete': False, 'platform': platform.platform(), 'checks': []}
    files = list(
        (ROOT / 'web/pgadmin/cdeadmin/providers/influxdb').glob('*.py'))
    files += [Path(__file__), *[ROOT / ('web/pgadmin/cdeadmin/providers/' + p)
                                for p in ('analytic_stream.py',
                                          'retained_native.py')]]
    proof['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(
        p.read_bytes()).hexdigest() for p in files}
    if password is not None:
        route = dict(route, principal_reference='fixture',
                     credential_reference_id='fixture', auth_kind='bearer',
                     credential_kind='api_token')
    provider = create_provider(SimpleNamespace(
        endpoint_id=str(uuid.uuid4()), session_namespace=str(uuid.uuid4())),
        SimpleNamespace(require=lambda *_: None,
                        acquire_secret=lambda *_: SecretLease(
                            password.encode())))
    database = 'cde_driver_' + uuid.uuid4().hex
    route = dict(route, database=database)
    backend = provider.client.backend
    native_route = backend._route({'route': route})
    try:
        session = provider.open_session({'route': route})

        def query(source, parameters=None, error=False):
            token = provider.execute(dict(session, source=source,
                                          parameters=parameters or {}))
            rows, deadline = [], time.monotonic() + 120
            pages = []
            while time.monotonic() < deadline:
                result = provider.describe_result(token)
                payload = result['extensions']['influxdb']['payload']
                rows.extend(payload.get('points', []))
                pages.append(payload)
                if result['complete']:
                    if not error:
                        assert not payload.get('error'), payload
                    return rows, pages
            raise AssertionError('InfluxDB operation did not terminate')

        stamp = time.time_ns()
        source = '\n'.join(
            f'values,tag=driver v=9223372036854775807i {stamp + i}'
            for i in range(10017))
        query(json.dumps({'operation': 'write', 'line_protocol': source}))
        rows, pages = query('SELECT * FROM "values" ORDER BY time')
        assert len(rows) == 10017
        assert rows[0]['v'] == {'$integer': '9223372036854775807'}
        assert max(len(p.get('points', [])) for p in pages) <= 256
        proof['checks'].append('native-write-untruncated-exact-integer')
        rows, _ = query('SELECT count(*) AS count FROM "values"')
        assert rows[0]['count'] == 10017
        rows, _ = query(json.dumps({'operation': 'query',
                                    'language': 'influxql',
                                    'source':
                                    'SELECT * FROM "values" LIMIT 2'}))
        assert len(rows) == 2
        proof['checks'].append('sql-and-influxql')
        _, pages = query('SELECT * FROM "absent_' + uuid.uuid4().hex + '"',
                         error=True)
        assert pages[-1]['error'] and pages[-1]['session_reuse_blocked']
        proof['checks'].append('native-error-quarantine')
        provider.close_session(session)
        proof['complete'] = True
    finally:
        backend._request(native_route, '/api/v3/configure/database',
                         method='DELETE', query={'db': database},
                         mutating=True)
        provider.close()
        (evidence / 'receipt.json').write_text(json.dumps(proof, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--password-file', type=Path)
    args = parser.parse_args()
    run(json.loads(args.route.read_text()), args.evidence,
        args.password_file.read_text().strip() if args.password_file else None)
