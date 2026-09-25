#!/usr/bin/env python3
"""FM-FB03-005 native compression negotiation and payload integrity on Linux.

Windows/macOS teams repeat with their native client/zlib packaging and browser
controls. Services has no equivalent negotiated-compression metric: only its
admission is asserted. No server compression policy is invented (client-only).
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import hashlib
import json
from pathlib import Path
import traceback
import uuid

from tools.cdeadmin_firebird_wire_crypt_gate import check, observe
from tools.cdeadmin_firebird_password_gate import run, reject_password
from pgadmin.cdeadmin.providers.firebird.provider import (
    _database_create_arguments,
)
from pgadmin.cdeadmin.providers.firebird.database_creation import (
    create_database,
)
from pgadmin.cdeadmin.providers.firebird.connection_strings import database_dsn


def observe_compression(handle, encrypted, plugin, *, compressed):
    result = observe(handle, encrypted, plugin)
    payload = ('Native compression: é 密 ' * 1000)
    with handle.cursor() as cursor:
        cursor.execute('SELECT MON$WIRE_COMPRESSED FROM MON$ATTACHMENTS '
                       'WHERE MON$ATTACHMENT_ID=CURRENT_CONNECTION')
        actual = cursor.fetchone()[0]
        assert actual is not None and bool(actual) == compressed
        # Parameter upload and BLOB download must survive both compression
        # directions, including encryption plus multibyte text boundaries.
        cursor.execute('SELECT CAST(? AS BLOB SUB_TYPE TEXT) '
                       'FROM RDB$DATABASE', (payload,))
        returned = cursor.fetchone()[0]
        if hasattr(returned, 'read'):
            reader = returned
            try:
                returned = reader.read()
            finally:
                reader.close()
        assert returned == payload
        cursor.execute('SELECT FIRST 200 A.RDB$TYPE_NAME '
                       'FROM RDB$TYPES A CROSS JOIN RDB$TYPES B')
        count = 0
        while rows := cursor.fetchmany(17):
            count += len(rows)
        assert count == 200
    handle.rollback()
    result.update(compressed=bool(actual), rows=count,
                  blob_bytes=len(payload.encode()),
                  blob_sha256=hashlib.sha256(payload.encode()).hexdigest())
    return result


def matrix(native, admin, route, accounts, evidence):
    user, password = accounts['Srp'][0]
    selected = {**route, 'user': user, 'charset': 'UTF8'}
    results = {'checks': [], 'failures': []}

    def exercise(value, policy, raw=False, creation=True):
        configuration = ({'wire_config': 'WireCompression=' +
                          str(value).lower()} if raw else
                         {'wire_compression': value})
        values = {**selected, **configuration}
        result = check(values, password, policy, 'ChaCha64', True,
                       policy != 'Disabled',
                       'ChaCha64' if policy != 'Disabled' else None,
                       creation=creation, observation=partial(
                           observe_compression, compressed=bool(value)))
        # Compression must not bypass authentication on DB or Services.
        reject_password(values, user, 'WRONG-' + password, 'Srp256')
        result['wrong_password_rejected'] = True
        return result

    def case(name, operation):
        try:
            results['checks'].append({'case': name, 'result': operation()})
        except Exception as error:
            results['failures'].append({
                'case': name, 'type': type(error).__name__,
                'lines': [f.lineno for f in traceback.extract_tb(
                    error.__traceback__)]})
        (evidence / 'compression-matrix.json').write_text(
            json.dumps(results, indent=2) + '\n')

    for policy in ('Disabled', 'Enabled', 'Required'):
        for value in (None, False, True):
            case(f'{policy}/{value}', lambda: exercise(value, policy))
    for value in (False, True):
        case(f'raw/{value}', lambda: exercise(value, 'Required', raw=True))

    def denied_creation(compression):
        import firebird.driver.core as core
        other, secret = accounts['Srp'][1]
        admin.execute_immediate(f'REVOKE CREATE DATABASE FROM USER "{other}"')
        admin.commit()
        handle = None
        try:
            target = database_dsn(
                '/var/lib/firebird/data/compression-denied-' +
                uuid.uuid4().hex + '.fdb', route['host'], route['port'])
            values = {**selected, 'user': other,
                      'wire_compression': compression,
                      'wire_crypt': 'Required'}
            args = _database_create_arguments(values, target, {}, native)
            try:
                handle = create_database(native, core, password=secret, **args)
            except native.Error as error:
                # isc_no_priv: an arbitrary attachment/transport error must
                # not be mistaken for enforcement of the creation grant.
                assert 335544352 in error.gds_codes
                assert secret not in str(error)
                return {'creation_denied': True,
                        'gds_codes': list(error.gds_codes)}
            else:
                handle.drop_database()
                raise AssertionError('Compression bypassed create privilege')
        finally:
            if handle is not None:
                handle.close()
            admin.execute_immediate(f'GRANT CREATE DATABASE TO USER "{other}"')
            admin.commit()
    for value in (False, True):
        case(f'permission/{value}', lambda: denied_creation(value))

    def concurrent():
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(exercise, value, policy, creation=False)
                       for value in (False, True)
                       for policy in ('Disabled', 'Required')]
            return [future.result() for future in futures]
    case('concurrent-config-isolation', concurrent)
    assert len(results['checks']) == 14 and not results['failures']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', type=Path, required=True)
    options = parser.parse_args()
    outcome = run(options.evidence_root, selected_plugins=['Srp256'],
                  fixture_check=matrix)
    raise SystemExit(0 if outcome['complete'] else 1)
