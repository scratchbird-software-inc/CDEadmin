#!/usr/bin/env python3
"""Native Milvus retained HTTP session and streaming qualification."""
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
from pgadmin.cdeadmin.providers.milvus.provider import (  # noqa: E402
    create_provider)
from pgadmin.cdeadmin.security import SecretLease  # noqa: E402


def run(route, evidence, password=None):
    evidence = Path(evidence).resolve()
    if ROOT == evidence or ROOT in evidence.parents:
        raise ValueError('Use an external evidence directory')
    evidence.mkdir(parents=True, exist_ok=False)
    proof = {'complete': False, 'platform': platform.platform(), 'checks': []}
    files = list(
        (ROOT / 'web/pgadmin/cdeadmin/providers/milvus').glob('*.py'))
    files += [Path(__file__), *[ROOT / ('web/pgadmin/cdeadmin/providers/' + p)
                                for p in ('native_distributed.py',
                                          'retained_native.py')]]
    proof['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(
        p.read_bytes()).hexdigest() for p in files}
    if password is not None:
        route = dict(route, principal_reference='fixture',
                     credential_reference_id='fixture', auth_kind='basic')
    provider = create_provider(SimpleNamespace(
        endpoint_id=str(uuid.uuid4()), session_namespace=str(uuid.uuid4())),
        SimpleNamespace(require=lambda *_: None,
                        acquire_secret=lambda *_: SecretLease(
                            password.encode())))
    collection = 'cde_driver_' + uuid.uuid4().hex
    fixture = None
    try:
        fixture, _ = provider.client.backend._connect({'route': route})
        fixture.create_collection(collection_name=collection, dimension=4,
                                  auto_id=False, consistency_level='Strong')
        session = provider.open_session({'route': route})

        def query(source, parameters=None, error=False):
            if not isinstance(source, str):
                source = json.dumps(source)
            token = provider.execute(dict(session, source=source,
                                          parameters=parameters or {}))
            rows, deadline = [], time.monotonic() + 120
            pages = []
            while time.monotonic() < deadline:
                result = provider.describe_result(token)
                payload = result['extensions']['milvus']['payload']
                rows.extend(payload.get('matches', []))
                pages.append(payload)
                if result['complete']:
                    if not error:
                        assert not payload.get('error'), payload
                    return rows, pages
            raise AssertionError('Milvus operation did not terminate')

        first_id = 9007199254741000
        for start in range(0, 10017, 500):
            query({'operation': 'insert', 'collection_name': collection,
                   'data': [{'id': {'$integer': str(first_id + i)},
                             'vector': [float(i % 10), 1.0, 2.0, 3.0]}
                            for i in range(start, min(start + 500, 10017))]})
        fixture.flush(collection)
        rows, pages = query({'operation': 'query',
                             'collection_name': collection,
                             'filter': '', 'output_fields': ['id'],
                             'consistency_level': 'Strong'})
        assert len(rows) == 10017
        assert {int(row['id']['$integer']) for row in rows} == set(
            range(first_id, first_id + 10017))
        assert max(len(page.get('matches', [])) for page in pages) <= 256
        proof['checks'].append('native-write-untruncated-query-exact-int64')
        rows, _ = query({'operation': 'search', 'collection_name': collection,
                         'data': [[1.0, 1.0, 2.0, 3.0]], 'limit': 3})
        assert len(rows) == 3 and rows[0]['query_vector_index'] == 0
        proof['checks'].append('native-vector-search')
        rows, _ = query({'operation': 'search_iterator',
                         'collection_name': collection,
                         'data': [[1.0, 1.0, 2.0, 3.0]],
                         'limit': 5, 'batch_size': 2})
        assert len(rows) == 5
        proof['checks'].append('search-iterator-exhaustion')
        rows, _ = query({'operation': 'hybrid_search',
                         'collection_name': collection, 'limit': 3,
                         'ranker': {'type': 'rrf'}, 'reqs': [{
                             'data': [[1.0, 1.0, 2.0, 3.0]],
                             'anns_field': 'vector',
                             'param': {'metric_type': 'COSINE'},
                             'limit': 3}]})
        assert len(rows) == 3
        query({'operation': 'upsert', 'collection_name': collection,
               'data': [{'id': {'$integer': str(first_id)},
                         'vector': [0.0, 0.0, 0.0, 1.0]}]})
        query({'operation': 'delete', 'collection_name': collection,
               'ids': [{'$integer': str(first_id)}]})
        proof['checks'].append('hybrid-ranker-upsert-delete')
        _, pages = query({'operation': 'get', 'collection_name': 'absent_' +
                          uuid.uuid4().hex, 'ids': [1]}, error=True)
        assert pages[-1]['error'] and pages[-1]['session_reuse_blocked']
        proof['checks'].append('native-error-quarantine')
        provider.close_session(session)
        proof['complete'] = True
    finally:
        if fixture is not None:
            fixture.drop_collection(collection)
            fixture.close()
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
