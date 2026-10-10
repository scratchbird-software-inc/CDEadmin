#!/usr/bin/env python3
"""Exercise the default MongoDB provider on a disposable replica set."""
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
import test_cdeadmin_mongodb_provider  # noqa: E402,F401
from pgadmin.cdeadmin.providers.mongodb.provider import (  # noqa: E402
    create_provider)
from pgadmin.cdeadmin.security import SecretLease  # noqa: E402


def run(route, evidence, password=None):
    evidence = Path(evidence).resolve()
    if ROOT == evidence or ROOT in evidence.parents:
        raise ValueError('Use an external evidence directory')
    evidence.mkdir(parents=True, exist_ok=False)
    proof = {'complete': False, 'platform': platform.platform(), 'checks': []}
    files = list(
        (ROOT / 'web/pgadmin/cdeadmin/providers/mongodb').glob('*.py'))
    files += [Path(__file__), ROOT / (
        'web/pgadmin/cdeadmin/providers/retained_native.py')]
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
    database = 'cde_driver_' + uuid.uuid4().hex
    route = dict(route, database=database)
    native = None
    try:
        session = provider.open_session({'route': route})
        owner = provider._sessions[session['session_id']].handle
        native = owner.handle.client
        proof['runtime'] = provider.client.runtime_identity(
            {'route': route}, owner)

        def query(value, error=False):
            token = provider.execute(dict(session, source=json.dumps(value)))
            rows, deadline = [], time.monotonic() + 120
            while time.monotonic() < deadline:
                result = provider.describe_result(token)
                payload = result['extensions']['mongodb']['payload']
                rows.extend(payload.get('documents', []))
                if result['complete']:
                    if not error:
                        assert not payload.get('error'), payload
                    return rows, payload
            raise AssertionError('MongoDB operation did not terminate')

        query({'operation': 'insert_many', 'collection': 'values',
               'documents': [{'_id': i, 'n': {'$numberLong':
                              '9223372036854775807'}} for i in range(1001)]})
        rows, _ = query({'operation': 'find', 'collection': 'values'})
        assert len(rows) == 1001
        assert rows[0]['n'] == {'$numberLong': '9223372036854775807'}
        proof['checks'].append('untruncated-canonical-bson')
        for decision, expected in [('rollback', 0), ('commit', 1)]:
            provider.control_transaction(dict(session, action='begin'))
            query({'operation': 'insert_one', 'collection': 'decisions',
                   'document': {'_id': decision}})
            assert native[database].decisions.count_documents(
                {'_id': decision}) == 0
            provider.control_transaction(dict(session, action=decision))
            assert native[database].decisions.count_documents(
                {'_id': decision}) == expected
        proof['checks'].append('session-bound-commit-rollback')
        query({'operation': 'update_one', 'collection': 'decisions',
               'filter': {'_id': 'commit'}, 'update': {'$set': {'v': 5}}})
        assert native[database].decisions.find_one({'_id': 'commit'})['v'] == 5
        query({'operation': 'delete_one', 'collection': 'decisions',
               'filter': {'_id': 'commit'}})
        assert native[database].decisions.count_documents({}) == 0
        proof['checks'].append('query-crud')
        watch_session = provider.open_session({'route': route})
        watch_token = provider.execute(dict(watch_session, source=json.dumps({
            'operation': 'watch', 'collection': 'values',
            'max_await_time_ms': 50})))
        # An empty heartbeat confirms the native stream has been opened.
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            heartbeat = provider.describe_result(watch_token)
            if heartbeat['extensions']['mongodb']['payload'].get('has_page'):
                break
        else:
            raise AssertionError('Change stream did not open')
        native[database]['values'].insert_one({'_id': 'stream-event'})
        while time.monotonic() < deadline:
            event = provider.describe_result(watch_token)
            payload = event['extensions']['mongodb']['payload']
            if payload.get('documents'):
                assert payload['documents'][0]['operationType'] == 'insert'
                assert payload['resume_token']
                break
        else:
            raise AssertionError('Change stream event absent')
        provider.close_session(watch_session)
        proof['checks'].append('change-stream-heartbeat-resume-token-close')
        _, failure = query({'operation': 'command',
                            'command': {'notARealCommand': 1}}, error=True)
        assert failure['session_reuse_blocked'] and failure['error']
        proof['checks'].append('error-quarantine')
        proof['complete'] = True
    finally:
        if native is not None:
            native.drop_database(database)
        provider.close()
        (evidence / 'receipt.json').write_text(json.dumps(proof, indent=2))
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--password-file', type=Path)
    args = parser.parse_args()
    run(json.loads(args.route.read_text()), args.evidence,
        args.password_file.read_text().strip() if args.password_file else None)
