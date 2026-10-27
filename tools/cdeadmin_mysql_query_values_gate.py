"""Compare provider query values to independent native MySQL text/hex."""
import argparse
import base64
import json
import re
from pathlib import Path
import secrets
import traceback

from tools.cdeadmin_mysql_connection_ownership_gate import run
from tools.cdeadmin_mysql_execution_gate import collect
from pgadmin.cdeadmin.providers.mysql_family.provider import (
    MYSQL_PROFILE, _create_client,
)


from tools.mysql_driver_gate_support import provider_access


def qualify(route, evidence, *, password=None):
    import mysql.connector as native
    evidence.mkdir(parents=True, exist_ok=False)
    proof = {'complete': False, 'checks': [], 'failures': []}
    owner = native.connect(**route, **(
        {'password': password} if password is not None else {}))
    provider_route, permissions = provider_access(route, password)
    schema = 'owned_values_' + secrets.token_hex(8)
    client = None
    created = False
    cursor = owner.cursor()
    try:
        cursor.execute(f'CREATE DATABASE `{schema}` CHARACTER SET utf8mb4')
        created = True
        client = _create_client(
            MYSQL_PROFILE, permissions, None)
        handle = client.open_session({'route': dict(
            provider_route, database=schema, charset='utf8mb4', sql_mode='',
            autocommit=False, time_zone='+00:00')})

        def sql(source, parameters=()):
            pages = collect(client, client.execute(handle, {
                'source': source, 'parameters': parameters}))
            assert not pages[-1]['payload']['error']
            result = next(p for p in pages if p['payload']['has_page'])
            result['payload']['rows'] = [row for p in pages
                                         for row in p['payload']['rows']]
            return result

        def rows(source, parameters=()):
            return sql(source, parameters)['payload']['rows']

        rows('CREATE TABLE sample (I BIGINT, U BIGINT UNSIGNED, '
             'D DECIMAL(65,30), B LONGBLOB, T LONGTEXT, J JSON, '
             'BITS BIT(64), TM TIME(6), DT DATE, TS DATETIME(6), '
             'G GEOMETRY, V VECTOR(3))')
        number = ('12345678901234567890123456789012345.'
                  '123456789012345678901234567890')
        raw = bytes(range(256)) * 4096
        text = 'été🙂日本\x00' * 10000
        rows('INSERT INTO sample VALUES (%(i)s,%(u)s,%(d)s,%(b)s,%(t)s,'
             '%(j)s,%(bits)s,%(tm)s,%(dt)s,%(ts)s,'
             "ST_GEOMFROMTEXT('POINT(1 2)'),STRING_TO_VECTOR('[1,2,3]'))", {
                 'i': {'encoding': 'integer', 'data': '-9223372036854775808'},
                 'u': {'encoding': 'integer', 'data': '18446744073709551615'},
                 'd': {'encoding': 'decimal', 'data': number},
                 'b': {'encoding': 'base64',
                       'data': base64.b64encode(raw).decode('ascii')},
                 't': text, 'j': '{"n":9007199254740993}',
                 'bits': {'encoding': 'integer',
                          'data': '18446744073709551615'},
                 'tm': '-36:12:11.123456', 'dt': '0000-00-00',
                 'ts': '0000-00-00 00:00:00.000000'})
        actual = sql('SELECT * FROM sample')
        row = actual['payload']['rows'][0]
        assert row[0:3] == ('-9223372036854775808', '18446744073709551615',
                            number)
        assert base64.b64decode(row[3]['data']) == raw
        assert row[4] == text
        assert json.loads(row[5]) == {'n': 9007199254740993}
        assert row[6:10] == ('18446744073709551615', '-36:12:11.123456',
                             '0000-00-00', '0000-00-00 00:00:00.000000')
        json.dumps(actual, allow_nan=False)
        assert all(c['cell_type'] in {'json', 'text'}
                   for c in actual['schema']['columns'])
        cursor.execute(f'SELECT COUNT(*) FROM `{schema}`.sample')
        assert cursor.fetchone() == (0,)
        owner.rollback()
        client.control_transaction(handle, 'commit')
        cursor.execute(f'SELECT HEX(G), HEX(V) FROM `{schema}`.sample')
        geometry, vector = cursor.fetchone()
        assert base64.b64decode(row[10]['data']).hex().upper() == geometry
        assert base64.b64decode(row[11]['data']).hex().upper() == vector
        proof['checks'].append('exact_native_types_and_independent_commit')
        rows('DELETE FROM sample')
        client.control_transaction(handle, 'rollback')
        assert rows('SELECT COUNT(*) FROM sample') == [(1,)]
        assert rows('SELECT %s,CAST(%s AS BINARY)',
                    [None, {'encoding': 'base64', 'data': ''}]) \
            == [(None, {'encoding': 'base64', 'data': '', 'byte_length': 0})]
        names = sql('SELECT 1 AS `été`, 2 AS `été`, 3 AS `été#2`')
        assert [c['name'] for c in names['schema']['columns']] == [
            'été', 'été#3', 'été#2']
        proof['checks'].append('rollback_null_empty_and_duplicate_labels')
        rows('SET character_set_results=NULL')
        for charset, raw in (
                ('latin1', bytes(range(256))),
                ('latin2', 'Zażółć'.encode('iso8859_2')),
                ('cp1251', 'Привет'.encode('cp1251')),
                ('sjis', '日本'.encode('shift_jis')),
                ('gb18030', '中文🙂'.encode('gb18030')),
                ('utf16', 'été🙂'.encode('utf_16_be')),
                ('utf32', 'été🙂'.encode('utf_32_be'))):
            expression = f'CONVERT(0x{raw.hex()} USING {charset})'
            actual = rows(f'SELECT {expression} AS sample')[0][0]
            cursor.execute(f'SELECT CONVERT({expression} USING utf8mb4)')
            expected = cursor.fetchone()[0]
            assert actual == expected, charset
        opaque = rows('SELECT CONVERT(0x4142 USING armscii8) AS sample')[0][0]
        assert opaque == {'encoding': 'base64', 'data': 'QUI=',
                          'byte_length': 2, 'native_charset': 'armscii8',
                          'charset_id': 32}
        rows('SET character_set_results=utf8mb4')
        proof['checks'].append('per_column_native_charset_and_exact_fallback')
        rows('INSERT INTO sample SELECT * FROM sample')
        assert client.describe_transaction(handle)['in_transaction'] is True
        cursor.execute(f'KILL CONNECTION {int(handle.connection_id)}')
        assert client.describe_transaction(handle)['connection_health_checked'] is False
        # A passive status observation cannot discover an unread disconnect.
        # The next user command owns that transport failure; it is never replayed.
        failed = collect(client, client.execute(handle, {'source': 'SELECT 1'}))
        assert failed[-1]['payload']['session_reuse_blocked'] is True
        observed = client.describe_transaction(handle)
        assert observed['state'] == 'unknown'
        assert observed['connection_usable'] is False
        receipt = client.close_session(handle)
        assert receipt['rollback_requested'] is False
        assert receipt['state'] == 'unknown'
        owner.rollback()
        cursor.execute(f'SELECT COUNT(*) FROM `{schema}`.sample')
        assert cursor.fetchone() == (1,)
        proof['checks'].append('dead_retained_session_unknown_no_replay')
    except Exception as error:
        proof['failures'].append({
            'type': type(error).__name__,
            'native_identity': re.findall(
                r'(?:errno=[0-9]+|sqlstate=[A-Z0-9]{5})', str(error)),
            'locations': [{'file': Path(f.filename).name, 'line': f.lineno}
                          for f in traceback.extract_tb(error.__traceback__)]})
    finally:
        if client:
            client.close()
        owner.rollback()
        if created:
            cursor.execute(f'DROP DATABASE `{schema}`')
        cursor.close()
        owner.close()
        proof['owned_objects_removed'] = True
    proof['complete'] = not proof['failures']
    (evidence / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='mysql:9.7.0')
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.image, args.evidence, qualify)
    raise SystemExit(0 if result['complete'] else 1)
