#!/usr/bin/env python3
"""Compare safe script boundaries with the pinned native isql utility."""
import argparse
import json
import os
from pathlib import Path
import subprocess

from tools.cdeadmin_firebird_local_fixture import run_local
from pgadmin.cdeadmin.providers.firebird.scripts import parse
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def qualify(native, admin, route, accounts, evidence, root):
    user, password = accounts['Srp'][0]
    checks = []
    for delimiter in ('^', '!!', '/^', '$$', '界', 'GO', '@@', '||', ';!'):
        prefix = (f'SET TERM ^ ;\nSET TERM {delimiter} ^\n'
                  if ';' in delimiter else f'SET TERM {delimiter} ;\n')
        source = (prefix +
                  "SELECT q'{a; '' !/}' AS V FROM RDB$DATABASE" + delimiter +
                  '\nSELECT \'LEXICAL_OK\' AS V FROM RDB$DATABASE' +
                  delimiter + '\nSET TERM ; ' + delimiter + '\n')
        try:
            entries = parse(source)
            assert [entry.kind for entry in entries][-3:] == [
                'sql', 'sql', 'terminator']
        except RelationalClientError:
            entries = ()
        assert bool(entries) == (delimiter not in ('/^', '界'))
        result = subprocess.run([
            str(root / 'runtime/bin/isql'), '-q', '-b', '-ch', 'UTF8',
            f'inet://{route["host"]}:{route["port"]}/{route["database"]}'],
            input=source.encode('utf8'), capture_output=True, timeout=15,
            env={**os.environ, 'ISC_USER': user, 'ISC_PASSWORD': password})
        checks.append({'delimiter': delimiter, 'native_returncode':
                       result.returncode,
                       'marker_seen': b'LEXICAL_OK' in result.stdout,
                       'unexpected_eof': b'Unexpected end of command' in
                       result.stderr,
                       'script_entries': len(entries),
                       'diagnostic': result.stderr.decode(
                           'utf8', errors='replace').replace(
                               password, '[REDACTED]')[:1024]})
        (evidence / 'checks.json').write_text(
            json.dumps(checks, indent=2) + '\n')
    assert all(item['native_returncode'] == 0 and item['marker_seen']
               for item in checks if item['script_entries'])
    assert all(item['native_returncode'] != 0
               for item in checks if not item['script_entries'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    options = parser.parse_args()
    result = run_local(options.runtime, options.evidence, qualify)
    raise SystemExit(0 if result['complete'] else 1)
