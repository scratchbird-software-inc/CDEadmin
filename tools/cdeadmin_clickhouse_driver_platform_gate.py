#!/usr/bin/env python3
"""Native ClickHouse retained HTTP session and streaming qualification."""
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
from pgadmin.cdeadmin.providers.clickhouse.provider import (  # noqa: E402
    create_provider)
from pgadmin.cdeadmin.security import SecretLease  # noqa: E402


def run(route, evidence, password=None):
    evidence = Path(evidence).resolve()
    if ROOT == evidence or ROOT in evidence.parents:
        raise ValueError('Use an external evidence directory')
    evidence.mkdir(parents=True, exist_ok=False)
    proof = {'complete': False, 'platform': platform.platform(), 'checks': []}
    files = list(
        (ROOT / 'web/pgadmin/cdeadmin/providers/clickhouse').glob('*.py'))
    files += [Path(__file__), *[ROOT / ('web/pgadmin/cdeadmin/providers/' + p)
                                for p in ('analytic_stream.py',
                                          'retained_native.py')]]
    proof['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(
        p.read_bytes()).hexdigest() for p in files}
    if password is not None:
        route = dict(route, principal_reference='fixture',
                     credential_reference_id='fixture')
    provider = create_provider(SimpleNamespace(
        endpoint_id=str(uuid.uuid4()), session_namespace=str(uuid.uuid4())),
        SimpleNamespace(require=lambda *_: None,
                        acquire_secret=lambda *_: SecretLease(
                            password.encode())))
    try:
        session = provider.open_session({'route': route})

        def query(source, parameters=None, error=False):
            token = provider.execute(dict(session, source=source,
                                          parameters=parameters or {}))
            rows, deadline = [], time.monotonic() + 120
            pages = []
            while time.monotonic() < deadline:
                result = provider.describe_result(token)
                payload = result['extensions']['clickhouse']['payload']
                rows.extend(payload.get('rows', []))
                pages.append(payload)
                if result['complete']:
                    if not error:
                        assert not payload.get('error'), payload
                    return rows, pages
            raise AssertionError('ClickHouse operation did not terminate')

        rows, pages = query('SELECT number FROM numbers(10017)')
        assert len(rows) == 10017 and rows[-1] == ['10016']
        assert max(len(p.get('rows', [])) for p in pages) <= 256
        proof['checks'].append('untruncated-paging')
        rows, _ = query("SELECT toUInt64('18446744073709551615'), "
                        "toDecimal128('12345678901234567890.123456789', 9)")
        assert rows == [['18446744073709551615',
                         '12345678901234567890.123456789']]
        proof['checks'].append('exact-integer-decimal')
        rows, _ = query('SELECT {value:UInt64}', {'value': '9007199254740993'})
        assert rows == [['9007199254740993']]
        query('CREATE TEMPORARY TABLE cde_native_values (v UInt64)')
        query('INSERT INTO cde_native_values VALUES (42)')
        assert query('SELECT v FROM cde_native_values')[0] == [['42']]
        query('DROP TABLE cde_native_values')
        proof['checks'].append('typed-parameters-and-retained-session')
        _, pages = query('SELECT * FROM cde_nonexistent_' + uuid.uuid4().hex,
                         error=True)
        assert pages[-1]['error'] and pages[-1]['session_reuse_blocked']
        proof['checks'].append('native-error-quarantine')
        provider.close_session(session)
        proof['complete'] = True
    finally:
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
