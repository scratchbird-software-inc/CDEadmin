#!/usr/bin/env python3
"""Native legacy attachment identifiers, scalar and character ARRAYs."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from tools.cdeadmin_firebird_local_fixture import run_local
from tools.cdeadmin_firebird_stream_gate import (
    _create_client, _route_arguments,
)


def qualify(native, admin, route, accounts, evidence, root, embedded=False):
    user, password = (('OWNED_LOCAL', None)
                      if embedded else accounts['Srp'][0])
    if embedded:
        route = {'attachment_mode': 'embedded', 'filesystem_root': str(root)}
    selected = dict(route, user=user, database=str(root / 'metadata.fdb'))
    client = _create_client(SimpleNamespace(acquire_secret=None))
    observations = []
    cases = [('ISO8859_1', 'café', 'clé', 'été'),
             ('WIN1251', 'таблица', 'ключ', 'данные'),
             ('SJIS_0208', 'テーブル', '列', '日本語'),
             ('LATIN1', 'café2', 'clé', 'été'),
             ('SJIS', 'テーブル2', '列', '日本語'),
             ('NEXT', 'café3', 'clé', 'été'),
             ('TIS620', 'ไทย', 'ค่า', 'ฟ้า'),
             ('CYRL', 'Тест', 'ключ', 'ёж'),
             ('CP943C', '日本', '列', '日本語')]
    try:
        with native.create_database(password=password, **_route_arguments(
                selected, native)) as owner:
            with owner.cursor() as cur:
                for charset, table, column, value in cases:
                    cur.execute(f'CREATE TABLE "{table}"("{column}" '
                                'VARCHAR(40) CHARACTER SET UTF8, '
                                'A INTEGER[1:3], '
                                'C VARCHAR(40)[1:2] CHARACTER SET UTF8)')
            owner.commit()
            for charset, table, column, value in cases:
                con = native.connect(password=password, charset=charset,
                                     **{k: v for k, v in _route_arguments(
                                         selected, native).items()
                                        if k != 'charset'})
                client._connections.append(con)
                con.ping()
                for dialect in (None, 3):
                    policy = ({'client_sql_dialect': dialect}
                              if dialect else {})
                    result = client.describe_result(client.execute(con, {
                        'source': f'INSERT INTO "{table}"("{column}",A,C) '
                                  f'VALUES(?,?,?) RETURNING "{column}",A,C',
                        'parameters': [value, [1, 2, 3], [value, value]],
                        'output_policy': policy}))
                    observations.append({'charset': charset,
                                         'observed_charset': con.charset,
                                         'codec': con._encoding,
                                         'dialect': dialect, 'insert': result})
                    result = client.describe_result(client.execute(con, {
                        'source': f'SELECT "{column}" AS "{value}",A,C '
                                  f'FROM "{table}"', 'parameters': [],
                        'output_policy': policy}))
                    observations[-1]['select'] = result
                    assert result['payload']['rows'][0][0] == value
                    client.control_transaction(con, 'rollback')
                client.close_session(con)
    finally:
        client.close()
    (evidence / 'observations.json').write_text(
        json.dumps(observations, indent=2, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--embedded', action='store_true')
    options = parser.parse_args()
    if options.embedded:
        from tools.cdeadmin_firebird_recovery_group_gate import run_embedded
        result = run_embedded(
            options.runtime, options.evidence,
            fixture_check=lambda *args: qualify(*args, embedded=True))
    else:
        result = run_local(options.runtime, options.evidence, qualify)
    raise SystemExit(0 if result['complete'] else 1)
