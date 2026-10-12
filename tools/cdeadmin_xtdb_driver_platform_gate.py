#!/usr/bin/env python3
"""Native XTDB driver qualification on owned temporal documents."""
import argparse
import getpass
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import traceback
from types import ModuleType, SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web')]
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package
from pgadmin.cdeadmin.providers.xtdb.provider import (  # noqa: E402
    create_provider, PROFILE,
)
from tools.mysql_driver_gate_support import provider_access  # noqa: E402


def run(route, evidence, password=None, reply_loss=False):
    evidence = Path(evidence).resolve()
    if evidence == ROOT or ROOT in evidence.parents or 'password' in route:
        raise ValueError('Use external evidence and credential references')
    evidence.mkdir(parents=True, exist_ok=False)
    proof = dict(complete=False, cleanup_complete=False,
                 checks=[], failures=[],
                 platform=platform.platform())
    files = list((ROOT / 'web/pgadmin/cdeadmin/providers/xtdb').glob('*.py'))
    files += [ROOT / ('web/pgadmin/cdeadmin/providers/' + n) for n in [
        'temporal_wire.py', 'pgwire_driver.py', 'distributed_sql.py',
        'postgresql/execution.py']]
    files += [Path(__file__), ROOT / 'tools/postgresql_reply_loss_fixture.py']
    proof['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(
        p.read_bytes()).hexdigest() for p in files}
    table = 'cde_driver_' + uuid.uuid4().hex
    provider, proxy, session = None, None, None
    owned = False
    try:
        request_route, permissions = provider_access(route, password)
        permissions.require = lambda *_: None
        context = SimpleNamespace(endpoint_id=str(uuid.uuid4()),
                                  session_namespace=table,
                                  pool_namespace=table,
                                  cache_namespace=table,
                                  provider_id=PROFILE.provider_id,
                                  profile_id=PROFILE.profile_id,
                                  profile_version=PROFILE.exact_version,
                                  provider_version='0.1.0')
        provider = create_provider(context, permissions)
        session = provider.open_session({'route': request_route})
        client = provider.client
        handle = provider._sessions[session['session_id']].handle
        proof['runtime'] = client.runtime_identity(
            {'route': request_route}, handle)
        if route.get('tls_mode') == 'verify-full':
            assert handle.connection.pgconn.ssl_in_use
        proof['checks'].append('exact-native-identity')

        def observe(operation):
            pages = []
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                result = provider.describe_result(operation)
                pages.append(result['extensions']['xtdb']['payload'])
                if result['complete']:
                    return pages
            raise AssertionError('Native query timeout')

        def query(sql, bound=None, target=None):
            pages = observe(provider.execute(dict(
                target or session, source=sql, parameters=bound)))
            if pages[-1].get('error'):
                proof['native_error'] = pages[-1]['error']
                raise AssertionError('Native query failed')
            return [row for page in pages for row in page['rows']]

        owned = True
        query('INSERT INTO '+table+'(_id,value,nested) VALUES (%s,%s,%s)',
              ['one', {'$xtdb_type': 'integer', 'value': '9007199254740993'},
               {'field': ['Grüße', None]}])
        rows = query(
            'SELECT value AS same, value AS other, nested FROM '+table)
        assert rows[0]['same'] == {
            '$xtdb_type': 'integer', 'value': '9007199254740993'}
        assert rows[0]['other'] == rows[0]['same']
        assert rows[0]['nested'] == {'field': ['Grüße', None]}
        query('UPDATE '+table+' SET value=7 WHERE _id=%s', ['one'])
        history = query('SELECT _id,value,_system_from,_valid_from FROM ' +
                        table +
                        ' FOR ALL VALID_TIME FOR ALL SYSTEM_TIME')
        assert len(history) >= 2
        proof['checks'].append('exact-values-and-temporal-history')
        provider.control_transaction(dict(session, action='begin'))
        query('INSERT INTO '+table +
              '(_id,value) VALUES (%s,%s)', ['rollback', 1])
        provider.control_transaction(dict(session, action='rollback'))
        assert not query('SELECT * FROM '+table+" WHERE _id='rollback'")
        provider.control_transaction(dict(session, action='begin'))
        query('INSERT INTO '+table+'(_id,value) VALUES (%s,%s)', ['commit', 2])
        client.list_resources({'route': request_route})
        provider.control_transaction(dict(session, action='commit'))
        assert query('SELECT value FROM '+table+" WHERE _id='commit'") == [
            {'value': 2}]
        proof['checks'].append('native-decisions-and-independent-metadata')
        pages = observe(provider.execute(dict(session, source=(
            'SELECT a.n FROM (VALUES '+','.join('('+str(i)+')' for i in
                                              range(10017))+') AS a(n)'))))
        assert not pages[-1].get('error')
        assert sum(len(p['rows']) for p in pages) == 10017
        assert max(len(p['rows']) for p in pages) <= 256
        proof['checks'].append('ordered-pages-without-10000-row-truncation')
        operation = provider.execute(dict(session, source=(
            'SELECT a.n FROM (VALUES '+','.join('('+str(i)+')' for i in
                                                range(10017))+') AS a(n)')))
        provider.describe_result(operation)
        assert provider.cancel(operation)['provider_receipt'][
            'cancel_request_accepted']
        cancelled = observe(operation)[-1]
        assert cancelled['session_reuse_blocked']
        provider.close_session(session)
        session = provider.open_session({'route': request_route})
        proof['checks'].append('retained-transport-abort-and-quarantine')
        if reply_loss:
            assert route.get('tls_mode', 'disable') == 'disable'
            from tools.postgresql_reply_loss_fixture import CommitReplyLoss
            proxy = CommitReplyLoss(route['host'], route['port'])
            fault = provider.open_session({'route': dict(
                request_route, host='127.0.0.1', port=proxy.port)})
            provider.control_transaction(dict(fault, action='begin'))
            query('INSERT INTO '+table +
                  "(_id,value) VALUES ('lost',3)", target=fault)
            try:
                provider.control_transaction(dict(fault, action='commit'))
            except RuntimeError:
                pass
            else:
                raise AssertionError('Lost reply claimed success')
            assert proxy.acknowledged.wait(5)
            assert provider.describe_transaction(fault)[
                'provider_payload']['session_reuse_blocked']
            assert query('SELECT value FROM '+table+" WHERE _id='lost'") == [
                {'value': 3}]
            provider.close_session(fault)
            proxy.close()
            proxy = None
            proof['checks'].append('native-commit-reply-loss-without-replay')
        provider.close_session(session)
        session = provider.open_session({'route': dict(
            request_route, pool_enabled=True,
            pool_min_size=0, pool_max_size=1)})
        old = provider._sessions[session['session_id']].handle.connection
        provider.close_session(session)
        assert old.closed
        session = provider.open_session({'route': request_route})
        proof['checks'].append('physical-lease-discard')
        proof['complete'] = True
    except Exception as exc:
        proof['failures'].append(dict(type=type(exc).__name__, locations=[
            dict(file=Path(f.filename).name, line=f.lineno)
            for f in traceback.extract_tb(exc.__traceback__)]))
    finally:
        try:
            if provider:
                try:
                    if owned:
                        cleanup = provider.open_session(
                            {'route': request_route})
                        query('ERASE FROM '+table, target=cleanup)
                finally:
                    provider.client.close()
            if proxy:
                proxy.close()
            proof['cleanup_complete'] = True
        except Exception as exc:
            proof['complete'] = False
            proof['failures'].append(
                dict(phase='cleanup', type=type(exc).__name__))
        (evidence / 'summary.json').write_text(
            json.dumps(proof, indent=2)+'\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--no-password', action='store_true')
    parser.add_argument('--reply-loss', action='store_true')
    args = parser.parse_args()
    result = run(json.loads(args.route.read_text()), args.evidence,
                 None if args.no_password else getpass.getpass('Password: '),
                 args.reply_loss)
    sys.exit(0 if result['complete'] else 1)
