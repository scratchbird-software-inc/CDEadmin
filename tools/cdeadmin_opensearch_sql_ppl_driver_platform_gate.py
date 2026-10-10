#!/usr/bin/env python3
"""Native SQL cursor and PPL limit qualification on OpenSearch 3.6.0."""
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
sys.path[:0] = [str(ROOT), str(ROOT / 'tools/tests')]
import test_cdeadmin_actual_engine_pilots  # noqa: E402,F401
from pgadmin.cdeadmin.providers.opensearch_sql_ppl.provider import create_provider  # noqa: E402
from pgadmin.cdeadmin.security import SecretLease  # noqa: E402


def run(route, evidence, password):
    evidence = Path(evidence).resolve()
    if ROOT == evidence or ROOT in evidence.parents:
        raise ValueError('Use external evidence')
    evidence.mkdir(parents=True, exist_ok=False)
    proof = dict(complete=False, platform=platform.platform(), checks=[])
    directory = ROOT / 'web/pgadmin/cdeadmin/providers/opensearch_sql_ppl'
    files = list(directory.glob('*.py'))
    files += [Path(__file__), ROOT /
              'web/pgadmin/cdeadmin/providers/opensearch/driver.py', ROOT /
              'web/pgadmin/cdeadmin/transports/analytics_http.py']
    files += [ROOT / ('web/pgadmin/cdeadmin/providers/' + p) for p in
              ('retained_native.py', 'native_distributed.py')]
    proof['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(
        p.read_bytes()).hexdigest() for p in files}
    route = dict(route, credential_reference_id='fixture',
                 principal_reference='fixture', auth_kind='basic')
    provider = create_provider(
        SimpleNamespace(
            endpoint_id=uuid.uuid4().hex,
            session_namespace=uuid.uuid4().hex),
        SimpleNamespace(
            require=lambda *_: None,
            acquire_secret=lambda *_: SecretLease(
                password.encode())))
    backend = provider.client.backend
    index = 'cde-sql-' + uuid.uuid4().hex
    native_route = backend._route({'route': route})
    created = False
    try:
        backend._request(
            native_route,
            '/' + index,
            method='PUT',
            mutating=True,
            json_body={
                'settings': {
                    'number_of_shards': 1,
                    'number_of_replicas': 0,
                    'max_result_window': 20000},
                'mappings': {
                    'properties': {
                        'value': {
                            'type': 'long'}}}})
        created = True
        first = 9007199254741000
        for start in range(0, 10017, 500):
            actions = []
            for i in range(start, min(start + 500, 10017)):
                actions += [{'index': {'_id': str(i)}}, {'value': first + i}]
            response = backend._request(
                native_route,
                '/' + index + '/_bulk',
                method='POST',
                mutating=True,
                body='\n'.join(
                    json.dumps(a) for a in actions) + '\n',
                headers={
                    'Content-Type': 'application/x-ndjson'}).json()
            assert not response['errors']
        backend._request(
            native_route,
            '/' + index + '/_refresh',
            method='POST',
            mutating=True)
        session = provider.open_session({'route': route})

        def query(source, language='sql'):
            token = provider.execute(
                dict(
                    session,
                    source=source,
                    language=language))
            rows, observed, deadline = [], [], time.monotonic() + 120
            while time.monotonic() < deadline:
                result = provider.describe_result(token)
                payload = result['extensions']['opensearch_sql_ppl']['payload']
                assert not payload.get('error'), payload
                rows.extend(payload.get('rows', []))
                observed.append(payload)
                if result['complete']:
                    return rows, observed
            raise AssertionError('Operation timed out')

        rows, sql_pages = query(
            'SELECT value FROM `' + index + '` ORDER BY value LIMIT 10017')
        proof['sql_observation'] = {'rows': len(rows), 'pages': len(
            sql_pages), 'first': sql_pages[0].get('native'),
            'last': sql_pages[-2].get('native')}
        assert len(rows) == 10000, proof['sql_observation']
        assert {int(row[0]['$integer'])
                for row in rows} == set(range(first, first + 10000))
        assert not backend._cursors
        proof['checks'].append(
            'sql-native-cursor-exhaustion-exact-int64-server-limit')
        rows, observed = query(
            'source = `' + index + '` | head 1100 | fields value', 'ppl')
        assert len(rows) == 1100, len(rows)
        assert any(p.get('native', {}).get('server_limit_applies')
                   for p in observed)
        assert not backend._cursors
        proof['checks'].append('ppl-no-injected-1000-limit')
        token = provider.execute(
            dict(
                session,
                source='SELECT value FROM `' +
                index +
                '` ORDER BY value LIMIT 10017'))
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            result = provider.describe_result(token)
            payload = result['extensions']['opensearch_sql_ppl']['payload']
            if payload.get('has_page'):
                break
        else:
            raise AssertionError('SQL cursor did not start')
        provider.cancel(token)
        provider.close_session(session)
        assert not backend._cursors
        proof['checks'].append('sql-cancel-closes-cursor')
        proof['complete'] = True
    finally:
        if created:
            backend._request(
                native_route,
                '/' + index,
                method='DELETE',
                mutating=True)
        provider.close()
        (evidence / 'receipt.json').write_text(json.dumps(proof, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--password-file', type=Path, required=True)
    args = parser.parse_args()
    run(json.loads(args.route.read_text()), args.evidence,
        args.password_file.read_text().strip())
