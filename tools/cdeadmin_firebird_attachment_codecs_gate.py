#!/usr/bin/env python3
"""Owned attachment codecs, UTF8 credentials/roles and BLOB boundaries."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import secrets
from types import SimpleNamespace

from tools.cdeadmin_firebird_local_fixture import run_local
from tools.cdeadmin_firebird_stream_gate import (
    _create_client, _route_arguments,
)
from pgadmin.cdeadmin.providers.firebird.provider import (
    _initialize_connection, _database_create_arguments,
)


def qualify(native, admin, route, accounts, evidence, root, embedded=False):
    creator, owner_password = (('OWNED_LOCAL', None) if embedded
                               else accounts['Srp'][0])
    if embedded:
        route = {'attachment_mode': 'embedded', 'filesystem_root': str(root)}
    user = 'OWNED_CODEC'
    password = None if embedded else secrets.token_urlsafe(24) + 'é漢'
    if not embedded:
        admin.execute_immediate(
            "CREATE USER OWNED_CODEC PASSWORD '" + password +
            "' USING PLUGIN Srp")
        admin.commit()
    selected = dict(route, user=creator, database=str(root / 'codecs.fdb'))
    client = _create_client(SimpleNamespace(acquire_secret=None))
    cases = [('UTF8', 'été', 'RÔLE'),
             ('UNICODE_FSS', 'été', 'RÔLE'),
             ('ISO8859_1', 'été', 'RÔLE'), ('LATIN1', 'été', 'RÔLE'),
             ('NEXT', 'été', 'RÔLE'), ('TIS620', 'ฟ้า', 'CODEC'),
             ('CYRL', 'ёж', 'CODEC'), ('CP943C', '日本語', 'CODEC'),
             ('SJIS', '日本語¥‾', 'CODEC'),
             ('EUCJ_0208', '日本語', 'CODEC'),
             ('BIG_5', '中文', 'CODEC'), ('GB_2312', '中文', 'CODEC'),
             ('GBK', '中文€', 'CODEC'),
             ('GB18030', 'ḿ龴︐🙂', 'CODEC'),
             ('KSC_5601', '한국', 'CODEC'),
             ('ISO8859_7', 'ʽʼ', 'CODEC'),
             ('ISO8859_8', '‾', 'CODEC'),
             ('KOI8U', 'ўЎ', 'CODEC'),
             ('WIN1258', 'Viê\u0323t', 'CODEC')]
    observations = []
    try:
        # Creation DPB must not confuse the SQL attachment charset with the
        # separately selected database default charset.
        creation_route = dict(selected, charset='NEXT')
        destination = (selected['database'] if embedded else
                       f"{route['host']}/{route['port']}:" +
                       selected['database'])
        arguments = _database_create_arguments(
            creation_route, destination,
            {'default_charset': 'UTF8'}, native)
        owner = client.config.database_creator(
            password=owner_password, **arguments)
        client._connections.append(owner)
        with owner.cursor() as cur:
            cur.execute('CREATE TABLE CODEC_TEST(ID INT PRIMARY KEY, '
                        'TXT BLOB SUB_TYPE TEXT CHARACTER SET UTF8)')
            cur.execute('CREATE ROLE "RÔLE"')
            cur.execute('CREATE ROLE CODEC')
            cur.execute('GRANT SELECT,INSERT ON CODEC_TEST TO "RÔLE"')
            cur.execute('GRANT SELECT,INSERT ON CODEC_TEST TO CODEC')
            cur.execute('GRANT "RÔLE" TO OWNED_CODEC')
            cur.execute('GRANT CODEC TO OWNED_CODEC')
        owner.commit()
        with owner.cursor() as cur:
            cur.execute('SELECT TRIM(RDB$CHARACTER_SET_NAME) '
                        'FROM RDB$DATABASE')
            assert cur.fetchone() == ('UTF8',)
        owner.rollback()
        for index, (charset, word, role) in enumerate(cases):
            target = dict(selected, user=user, role=role, charset=charset)
            connection = client._connector(
                password=password, **_route_arguments(target, native))
            client._connections.append(connection)
            _initialize_connection(connection, target, native)
            text = 'a' * 65535 + word * 25000
            client.describe_result(client.execute(connection, {
                'source': 'INSERT INTO CODEC_TEST VALUES(?,?)',
                'parameters': [index, text]}))
            result = client.describe_result(client.execute(connection, {
                'source': 'SELECT TXT FROM CODEC_TEST WHERE ID=?',
                'parameters': [index]}))
            assert result['payload']['rows'] == [(text,)]
            length_result = client.describe_result(client.execute(connection, {
                'source': 'SELECT CHAR_LENGTH(TXT) FROM CODEC_TEST WHERE ID=?',
                'parameters': [index]}))
            assert length_result['payload']['rows'] == [(len(text),)]

            def request(**values):
                return client.query_stream(connection, {
                    **values, 'owner_id': 'owned-codec-proof'})

            page = request(stream_action='open',
                           source='SELECT TXT FROM CODEC_TEST WHERE ID=?',
                           parameters=[index])
            reference = page['rows'][0][0]['blob_reference']
            raw = bytearray()
            while True:
                part = request(stream_action='blob', blob_reference=reference,
                               stream_reference=page['stream_reference'],
                               offset=len(raw))
                raw.extend(base64.b64decode(part['data']))
                if part['complete']:
                    break
            assert raw.decode(connection._encoding) == text
            request(stream_action='close')
            observations.append({
                'requested_charset': charset,
                'canonical_charset': connection.charset,
                'codec': connection._encoding,
                'blob_bytes': len(raw),
                'blob_sha256': hashlib.sha256(raw).hexdigest(),
                'native_utf8_credentials': not embedded,
                'native_role': role,
                'ordinary_and_streamed_values_match': True})
            client.control_transaction(connection, 'rollback')
            client.close_session(connection)
            with owner.cursor() as cur:
                cur.execute('SELECT COUNT(*) FROM CODEC_TEST')
                assert cur.fetchone() == (0,)
            owner.rollback()
        client.close_session(owner)
    except Exception as error:
        (evidence / 'failure-codes.json').write_text(json.dumps({
            'type': type(error).__name__,
            'native_status_codes': list(getattr(error, 'gds_codes', ())),
            'completed': len(observations)}, indent=2) + '\n')
        raise
    finally:
        client.close()
    (evidence / 'observations.json').write_text(
        json.dumps(observations, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--embedded', action='store_true')
    options = parser.parse_args()
    if options.embedded:
        from tools.cdeadmin_firebird_recovery_group_gate import run_embedded
        result = run_embedded(options.runtime, options.evidence,
                              fixture_check=lambda *args: qualify(
                                  *args, embedded=True))
    else:
        result = run_local(options.runtime, options.evidence, qualify)
    raise SystemExit(0 if result['complete'] else 1)
