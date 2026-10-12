#!/usr/bin/env python3
"""Native FSS conversion, exact reads and explicit malformed-input refusal."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from tools.cdeadmin_firebird_gb18030_oracle_gate import ENCODE
from tools.cdeadmin_firebird_local_fixture import run_local
from tools.cdeadmin_firebird_stream_gate import (
    _create_client, _route_arguments,
)
from pgadmin.cdeadmin.providers.firebird.attachment_codecs import codec_name
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.providers.firebird.provider import (
    _initialize_connection,
)


def conversion_oracle(connection, evidence):
    name = codec_name('UNICODE_FSS')
    digest = hashlib.sha256()
    count = 0
    # FSS emits six bytes per supplementary scalar, unlike four-byte UTF8.
    source = ENCODE.replace('VARCHAR(4)', 'VARCHAR(8)')
    with connection.cursor() as query:
        query.execute(source.format(charset='UNICODE_FSS'))
        for cp, raw in query:
            text = chr(cp)
            assert text.encode(name) == raw, cp
            assert raw.decode(name) == text, cp
            digest.update(cp.to_bytes(4, 'big') + raw)
            count += 1
    assert count == 1112064
    (evidence / 'unicode-fss-oracle.json').write_text(json.dumps({
        'unicode_scalars_verified': count,
        'native_encode_and_provider_decode_sha256': digest.hexdigest(),
        'canonical_conversion_not_input_validator_acceptance': True,
    }, indent=2) + '\n')


def qualify(native, admin, route, accounts, evidence, root, embedded=False):
    user, password = ('OWNED_LOCAL', None) if embedded else accounts['Srp'][0]
    if embedded:
        route = {'attachment_mode': 'embedded', 'filesystem_root': str(root)}
    selected = dict(route, user=user, database=str(root / 'fss.fdb'))
    client = _create_client(SimpleNamespace(acquire_secret=None))
    owner = native.create_database(password=password,
                                   **_route_arguments(selected, native))
    client._connections.append(owner)

    def sql(handle, source, parameters=()):
        result = client.describe_result(client.execute(handle, {
            'source': source, 'parameters': list(parameters)}))
        return result['payload'].get('rows', [])

    try:
        conversion_oracle(owner, evidence)
        sql(owner, 'CREATE TABLE FSS_TEST(ID INT, V VARCHAR(40) '
            'CHARACTER SET UTF8, B BLOB SUB_TYPE TEXT CHARACTER SET UTF8, '
            'A VARCHAR(8)[1:2] CHARACTER SET UNICODE_FSS)')
        owner.commit()
        text = 'a' * 65535 + '🙂𠀀é' * 20000
        sql(owner, 'INSERT INTO FSS_TEST VALUES(?,?,?,?)',
            [1, '🙂𠀀é', text, ['🙂', '𠀀']])
        owner.commit()
        target = dict(selected, charset='UNICODE_FSS')
        connection = client._connector(password=password,
                                       **_route_arguments(target, native))
        client._connections.append(connection)
        _initialize_connection(connection, target, native)
        assert sql(connection, 'SELECT V,A FROM FSS_TEST') == [
            ('🙂𠀀é', ['🙂', '𠀀'])]
        try:
            sql(connection, 'SELECT B FROM FSS_TEST')
        except RelationalClientError as error:
            assert 'UnicodeDecodeError' in str(error)
        else:
            raise AssertionError('Expected native FSS BLOB conversion failure')
        client.control_transaction(connection, 'rollback')
        bad = client.query_stream(connection, {
            'stream_action': 'open', 'owner_id': 'fss-failure',
            'source': 'SELECT B FROM FSS_TEST'})
        offset = 0
        try:
            while True:
                part = client.query_stream(connection, {
                    'stream_action': 'blob', 'owner_id': 'fss-failure',
                    'stream_reference': bad['stream_reference'],
                    'blob_reference': bad['rows'][0][0]['blob_reference'],
                    'offset': offset})
                assert not part['complete']
                offset = part['next_offset']
        except RelationalClientError as error:
            assert 'UNICODE_FSS' in str(error)
        finally:
            client.query_stream(connection, {
                'stream_action': 'close', 'owner_id': 'fss-failure'})
        client.control_transaction(connection, 'rollback')
        assert sql(owner, 'SELECT B FROM FSS_TEST') == [(text,)]

        def stream(action, **values):
            return client.query_stream(owner, {
                'stream_action': action, 'owner_id': 'fss-proof', **values})

        page = stream('open', source='SELECT B FROM FSS_TEST')
        raw = bytearray()
        while True:
            part = stream('blob', stream_reference=page['stream_reference'],
                          blob_reference=page['rows'][0][0]['blob_reference'],
                          offset=len(raw))
            raw.extend(base64.b64decode(part['data']))
            if part['complete']:
                break
        assert raw.decode(owner._encoding) == text
        stream('close')
        for value in ('🙂', '𠀀'):
            try:
                sql(connection, 'INSERT INTO FSS_TEST(ID,V) VALUES(?,?)',
                    [2, value])
            except RelationalClientError as error:
                assert set(error.gds_codes) & {335544849, 335544565}
            else:
                raise AssertionError('Expected native FSS input rejection')
            client.control_transaction(connection, 'rollback')
        assert sql(connection, 'SELECT COUNT(*) FROM FSS_TEST') == [(1,)]
        client.close_session(connection)
        client.close_session(owner)
        (evidence / 'fss-values.json').write_text(json.dumps({
            'scalar_array_exact_reads': True,
            'native_fss_blob_failure_reported_without_corrupt_result': True,
            'fss_blob_stream_fails_before_completion': True,
            'same_blob_utf8_materialized_and_streamed_exact': True,
            'native_fss_input_failure_reported_without_narrowing': True,
            'rolled_back_inputs_created_no_rows': True,
        }, indent=2) + '\n')
    finally:
        client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--embedded', action='store_true')
    options = parser.parse_args()
    if options.embedded:
        from tools.cdeadmin_firebird_recovery_group_gate import run_embedded
    fixture = run_embedded if options.embedded else run_local
    result = fixture(options.runtime, options.evidence,
                     lambda *args: qualify(*args, embedded=options.embedded))
    raise SystemExit(0 if result['complete'] else 1)
