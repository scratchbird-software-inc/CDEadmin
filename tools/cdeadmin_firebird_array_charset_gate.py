#!/usr/bin/env python3
"""Native character ARRAY qualification, including view reads."""
import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace

from tools.cdeadmin_firebird_stream_gate import (
    _create_client, _route_arguments,
)
from tools.cdeadmin_firebird_local_fixture import run_local
from pgadmin.cdeadmin.providers.firebird.temporal_arrays import cursor
from pgadmin.cdeadmin.providers.firebird.query_values import normalize_value
from pgadmin.cdeadmin.providers.firebird.grid_arrays import (
    editor_specs, convert,
)


def qualify(native, admin, route, accounts, evidence, root, *,
            attachment_charset='UTF8', embedded_mode=False):
    user, password = (('OWNED_LOCAL', None) if embedded_mode else
                      accounts['Srp'][0])
    if embedded_mode:
        route = {'attachment_mode': 'embedded', 'filesystem_root': str(root)}
    selected = dict(route, user=user, database=str(root / 'charsets.fdb'),
                    charset=attachment_charset)
    client = _create_client(SimpleNamespace(acquire_secret=None))
    connection = native.create_database(
        password=password, **_route_arguments(selected, native))
    client._connections.append(connection)
    checks, failures = [], []

    def request(action, **values):
        return client.query_stream(connection, {
            'stream_action': action, 'owner_id': 'charset-gate', **values})

    def sql(source, parameters=()):
        with cursor(connection) as query:
            query.execute(source, parameters)
            return query.fetchall() if query.description else []

    try:
        if embedded_mode:
            protocol, pid, version = sql(
                "SELECT MON$REMOTE_PROTOCOL, MON$SERVER_PID, "
                "RDB$GET_CONTEXT('SYSTEM','ENGINE_VERSION') "
                'FROM MON$ATTACHMENTS WHERE '
                'MON$ATTACHMENT_ID=CURRENT_CONNECTION')[0]
            assert protocol is None and pid == os.getpid()
            assert version == '5.0.4'
            connection.rollback()
        charsets = sql('SELECT TRIM(RDB$CHARACTER_SET_NAME), '
                       'RDB$CHARACTER_SET_ID, RDB$BYTES_PER_CHARACTER '
                       'FROM RDB$CHARACTER_SETS ORDER BY RDB$CHARACTER_SET_ID')
        for name, identifier, width in charsets:
            # Catalog spelling is quoted before inclusion as an identifier.
            quoted = '"' + name.replace('"', '""') + '"'
            samples = ['a\0b', '', 'tail ', ' \0 ', 'ascii']
            special = {
                'UNICODE_FSS': ['🙂', '𠀀', 'é'],
                'GBK': ['€', '\ue000', '\uf8f5'],
                'GB18030': ['🙂', 'ḿ', '︐'],
                'SJIS_0208': ['ｱ', '漢', '〜'],
                'EUCJ_0208': ['ｱ', '漢', '〜'],
                'CP943C': ['ｱ', '髙', '﨑'],
                'KSC_5601': ['\u3164', '\uac02', '한'],
            }.get(name, [])
            for text in special + [
                    'é', 'Ж', 'ש', 'ع', 'ก', '中', '日', '한', '€', 'Ł']:
                try:
                    actual = sql('SELECT CAST(? AS VARCHAR(8) CHARACTER SET '
                                 f'{quoted}) FROM RDB$DATABASE', [text])[0][0]
                    if actual == text:
                        samples.append(text)
                except (native.DatabaseError, UnicodeEncodeError):
                    pass  # An unmappable sample is not an admitted value.
            samples = samples[:8]
            samples += ['x'] * (8 - len(samples))
            if name == 'OCTETS':
                samples = [b'\0\xff\0 ', b'', b' \0 ', b'x'] * 2
            values = [samples[:4], samples[4:]]
            for kind in ('CHAR', 'VARCHAR'):
                case = f'{name}:{kind}'
                table = f'CHARSET_{identifier}_{kind}'
                view = 'V_' + table
                try:
                    sql(f'CREATE TABLE {table} '
                        f'(A {kind}(8)[-1:0,2:5] CHARACTER SET {quoted})')
                    connection.commit()
                    sql(f'CREATE VIEW {view} AS SELECT A FROM {table}')
                    connection.commit()
                    for relation in (table, view):
                        specification = editor_specs(connection, [{
                            'native_type': 'ARRAY',
                            'source_relation': relation,
                            'source_field': 'A', 'native_name': 'A',
                        }])['A']
                        assert specification['charset_id'] == identifier
                        assert specification['element_kind'] == (
                            'binary' if name == 'OCTETS' else 'text')
                        assert convert(normalize_value(values),
                                       specification) == values
                    sql(f'INSERT INTO {table} VALUES (?)', [values])
                    selectors = ','.join(f'A[{i},{j}]'
                                         for i in (-1, 0) for j in range(2, 6))
                    oracle = normalize_value(sql(
                        f'SELECT {selectors} FROM {table}')[0])
                    if kind == 'VARCHAR':
                        assert oracle == normalize_value(samples)
                    for relation in (table, view):
                        normal = normalize_value(sql(
                            f'SELECT A FROM {relation}')[0][0])
                        assert sum(normal, []) == oracle
                        page = request('open', source=(
                            f'SELECT A FROM {relation}'))
                        reference = page['rows'][0][0]['array_reference']
                        offset, collected = 0, []
                        while offset < 8:
                            part = request(
                                'array', stream_reference=page[
                                    'stream_reference'],
                                array_reference=reference, offset=offset)
                            collected.extend(part['values'])
                            offset = part['next_offset']
                        assert collected == oracle
                        request('close')
                    checks.append({'case': case, 'catalog_id': identifier,
                                   'native_bytes_per_character': width,
                                   'known_values': normalize_value(samples),
                                   'scalar_array_elements_match': True,
                                   'native_grid_editor_admitted': True,
                                   'normal_and_streamed_view_reads': True})
                except Exception as error:
                    failures.append({'case': case,
                                     'type': type(error).__name__})
                    if isinstance(error, UnicodeDecodeError):
                        failures[-1]['fixture_bytes'] = error.object[:32].hex()
                        failures[-1]['codec'] = error.encoding
                finally:
                    request('close')
                    connection.rollback()
                    (evidence / 'charset-checks.json').write_text(json.dumps({
                        'checks': checks, 'failures': failures,
                        'catalog_charsets': charsets,
                        'attachment_charset': attachment_charset,
                        'embedded_same_process_verified': embedded_mode,
                    }, indent=2) + '\n')
        assert not failures, 'Native charset cases failed'
    finally:
        client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--charset', default='UTF8')
    parser.add_argument('--embedded', action='store_true')
    options = parser.parse_args()
    if options.embedded:
        from tools.cdeadmin_firebird_recovery_group_gate import run_embedded
    fixture = run_embedded if options.embedded else run_local
    result = fixture(options.runtime, options.evidence,
                     lambda *args: qualify(
                         *args, attachment_charset=options.charset,
                         embedded_mode=options.embedded))
    raise SystemExit(0 if result['complete'] else 1)
