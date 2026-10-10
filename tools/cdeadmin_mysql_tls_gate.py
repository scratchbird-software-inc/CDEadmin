"""Native certificate validation and negotiated MySQL TLS version proof."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from tools.cdeadmin_mysql_connection_ownership_gate import run
from tools.cdeadmin_mysql_execution_gate import collect, qualify as execution
from pgadmin.cdeadmin.providers.mysql_family.provider import (
    MYSQL_PROFILE, _create_client,
)
from pgadmin.cdeadmin.sdk import RelationalClientError


def qualify(route, evidence):
    evidence.mkdir(parents=True, exist_ok=False)
    proof = {'complete': False, 'checks': []}
    client = _create_client(
        MYSQL_PROFILE, SimpleNamespace(acquire_secret=None), None)
    try:
        for version in ('TLSv1.2', 'TLSv1.3'):
            handle = client.open_session({'route': dict(
                route, tls_versions=[version])})
            pages = collect(client, client.execute(handle, {
                'source': "SHOW SESSION STATUS LIKE 'Ssl_version'"}))
            assert not pages[-1]['payload']['error']
            assert [row for p in pages for row in p['payload']['rows']] == [
                ('Ssl_version', version)]
            client.close_session(handle)
            proof['checks'].append('verified_' + version)
        for label, options in (
                ('hostname_mismatch', {'host': 'localhost'}),
                ('untrusted_certificate', {'ssl_ca': None})):
            try:
                handle = client.open_session({'route': dict(route, **options)})
            except RelationalClientError:
                proof['checks'].append(label + '_rejected')
            else:
                client.close_session(handle)
                raise AssertionError(
                    'TLS verification silently accepted ' + label)
        streamed = execution(route, evidence / 'execution', reply_loss=False)
        assert streamed['complete']
        proof['checks'].append('verified_tls_execution_and_cancel')
        proof['complete'] = True
    finally:
        client.close()
        (evidence / 'summary.json').write_text(json.dumps(proof, indent=2))
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='mysql:9.7.0')
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.image, args.evidence, qualify, tls=True)
    raise SystemExit(0 if result['complete'] else 1)
