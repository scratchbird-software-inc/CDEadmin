#!/usr/bin/env python3
"""Native OpenSearch retained scan and bulk qualification."""
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
from pgadmin.cdeadmin.providers.opensearch.provider import create_provider  # noqa: E402
from pgadmin.cdeadmin.security import SecretLease  # noqa: E402


def run(route, evidence, password):
    evidence = Path(evidence).resolve()
    if ROOT == evidence or ROOT in evidence.parents:
        raise ValueError('Use external evidence')
    evidence.mkdir(parents=True, exist_ok=False)
    proof = dict(complete=False, platform=platform.platform(), checks=[])
    files = list(
        (ROOT / 'web/pgadmin/cdeadmin/providers/opensearch').glob('*.py'))
    files += [Path(__file__), ROOT /
              'web/pgadmin/cdeadmin/search/opensearch.py', ROOT /
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
    index = 'cde-driver-' + uuid.uuid4().hex
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
                    'number_of_replicas': 0},
                'mappings': {
                    'properties': {
                        'value': {
                            'type': 'long'}}}})
        created = True
        session = provider.open_session({'route': dict(route, index=index)})

        def query(command):
            token = provider.execute(dict(session, source=json.dumps(command)))
            rows, observed, deadline = [], [], time.monotonic() + 120
            while time.monotonic() < deadline:
                result = provider.describe_result(token)
                payload = result['extensions']['opensearch']['payload']
                assert not payload.get('error'), payload
                rows.extend(payload.get('hits', []))
                observed.append(payload)
                if result['complete']:
                    return rows, observed
            raise AssertionError('Operation timed out')

        first = 9007199254741000
        for start in range(0, 10017, 500):
            actions = []
            for i in range(start, min(start + 500, 10017)):
                actions += [{'index': {'_id': str(i)}},
                            {'value': {'$integer': str(first + i)}}]
            _, observed = query(dict(operation='bulk', actions=actions))
            assert not any(p.get('native', {}).get('bulk_errors')
                           for p in observed)
        query(
            dict(
                operation='request',
                method='POST',
                path='/' +
                index +
                '/_refresh'))
        rows, observed = query(
            dict(
                operation='scan', body={
                    'query': {
                        'match_all': {}}}))
        assert len(rows) == 10017
        assert {int(row['_source']['value']['$integer'])
                for row in rows} == set(range(first, first + 10017))
        assert max(len(p.get('hits', [])) for p in observed) <= 256
        assert not backend._scrolls
        proof['checks'].append('untruncated-scroll-exact-int64-cleanup')
        rows, _ = query({'size': 3, 'query': {'match_all': {}}})
        assert len(rows) == 3
        rows, _ = query(dict(operation='bulk', actions=[
            {'create': {'_id': '0'}}, {'value': 1},
            {'index': {'_id': 'new'}}, {'value': 2}]))
        assert rows[0]['create']['status'] == 409
        assert rows[1]['index']['status'] == 201
        proof['checks'].append('native-top-k-and-bulk-partial-success')
        token = provider.execute(
            dict(session, source=json.dumps({'operation': 'scan'})))
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            result = provider.describe_result(token)
            payload = result['extensions']['opensearch']['payload']
            assert not payload.get('error'), payload
            if payload.get('has_page'):
                break
        else:
            raise AssertionError('Scroll did not start')
        provider.cancel(token)
        provider.close_session(session)
        assert not backend._scrolls
        proof['checks'].append('cancel-closes-scroll')
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
