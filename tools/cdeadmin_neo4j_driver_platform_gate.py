#!/usr/bin/env python3
"""Native Neo4j retained HTTP session and streaming qualification."""
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
import test_cdeadmin_neo4j_provider  # noqa: E402,F401
from pgadmin.cdeadmin.providers.neo4j.provider import (  # noqa: E402
    create_provider)
from pgadmin.cdeadmin.security import SecretLease  # noqa: E402


def run(route, evidence, password=None):
    evidence = Path(evidence).resolve()
    if ROOT == evidence or ROOT in evidence.parents:
        raise ValueError('Use an external evidence directory')
    evidence.mkdir(parents=True, exist_ok=False)
    proof = {'complete': False, 'platform': platform.platform(), 'checks': []}
    files = list((ROOT / 'web/pgadmin/cdeadmin/providers/neo4j').glob('*.py'))
    files += [Path(__file__), *[ROOT / ('web/pgadmin/cdeadmin/providers/' + p)
                                for p in ('analytic_stream.py',
                                          'retained_native.py')]]
    proof['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(
        p.read_bytes()).hexdigest() for p in files}
    if password is not None:
        route = dict(route, principal_reference='fixture',
                     credential_references={'database_password': 'fixture'},
                     auth_mode='basic')
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
                payload = result['extensions']['neo4j']['payload']
                rows.extend(payload.get('graphs', []))
                pages.append(payload)
                if result['complete']:
                    if not error:
                        assert not payload.get('error'), payload
                    return rows, pages
            raise AssertionError('Neo4j operation did not terminate')

        rows, pages = query('UNWIND range(0, 10016) AS n RETURN n')
        assert len(rows) == 10017 and rows[-1]['n'] == 10016
        assert max(len(p.get('graphs', [])) for p in pages) <= 256
        proof['checks'].append('untruncated-paging')
        rows, _ = query('RETURN $n AS n, $b AS b, '
                        'datetime("2026-10-10T12:00:00.123456789Z") AS t, '
                        'point({x:1.5,y:2.5}) AS p',
                        {'n': {'$integer': '9223372036854775807'},
                         'b': {'$binary': 'AP8='}})
        assert rows[0]['n'] == {'$integer': '9223372036854775807'}
        assert rows[0]['b'] == {'$binary': 'AP8='}
        assert '123456789' in rows[0]['t']['$neo4j_temporal']['value']
        assert rows[0]['p']['$neo4j_point']['srid'] == 7203
        proof['checks'].append('exact-bolt-values')
        label = 'CDEDriver_' + uuid.uuid4().hex
        for decision, expected in [('rollback', 0), ('commit', 1)]:
            provider.control_transaction(dict(session, action='begin'))
            rows, _ = query(f'CREATE (a:{label} {{v:$v}})-[r:LINK]->'
                            f'(b:{label}) RETURN a,r,b', {'v': decision})
            assert rows[0]['a']['kind'] == 'node'
            assert rows[0]['r']['kind'] == 'relationship'
            assert rows[0]['a']['labels'] == [label]
            provider.control_transaction(dict(session, action=decision))
            rows, _ = query(f'MATCH (n:{label} {{v:$v}}) '
                            'RETURN count(n) AS count', {'v': decision})
            assert rows[0]['count'] == expected
        query(f'MATCH (n:{label}) DETACH DELETE n')
        proof['checks'].append('graph-fidelity-commit-rollback')
        _, pages = query('THIS IS NOT CYPHER', error=True)
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
