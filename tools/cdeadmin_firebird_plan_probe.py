#!/usr/bin/env python3
"""Observe native prepare-only plan bytes, charset and transaction effects."""
import argparse
import ctypes
import json
from pathlib import Path
from types import SimpleNamespace

from tools.cdeadmin_firebird_local_fixture import run_local
from tools.cdeadmin_firebird_stream_gate import (
    _create_client, _route_arguments,
)


def qualify(native, admin, route, accounts, evidence, root):
    user, password = accounts['Srp'][0]
    selected = dict(route, user=user, database=str(root / 'plans.fdb'))
    client = _create_client(SimpleNamespace(acquire_secret=None))
    result = []
    with native.create_database(password=password, **_route_arguments(
            selected, native)) as owner:
        with owner.cursor() as cursor:
            cursor.execute('CREATE TABLE "café"(ID INTEGER PRIMARY KEY)')
        owner.commit()
        for charset in ('UTF8', 'ISO8859_1'):
            with native.connect(password=password, charset=charset,
                                **{key: value for key, value in
                                   _route_arguments(selected, native).items()
                                   if key != 'charset'}) as connection:
                with connection.cursor() as cursor:
                    cursor.execute('INSERT INTO "café" VALUES(1)')
                identity = connection.main_transaction.info.id
                for source in ('SELECT * FROM "café" WHERE ID=?',
                               'DELETE FROM "café" WHERE ID=?', 'COMMIT',
                               'ROLLBACK',
                               'CREATE TABLE NEVER_CREATED(ID INT)'):
                    statement = None
                    try:
                        statement = connection._att.prepare(
                            connection.main_transaction._tra, source, 3)
                        plans = []
                        for item in (22, 26):
                            for size in (32, 65539):
                                buffer = ctypes.create_string_buffer(size)
                                statement.get_info(bytes([item]), buffer)
                                raw = buffer.raw
                                length = (int.from_bytes(raw[1:3], 'little')
                                          if raw[0] == item else 0)
                                text = raw[3:3+length].decode(
                                    connection._encoding) if length else None
                                end = raw[3+length] if length else raw[0]
                                plans.append({'item': item, 'buffer': size,
                                              'text': text, 'terminator': end})
                        result.append({'charset': charset, 'source': source,
                                       'statement_type': (
                                           statement.get_type().name),
                                       'plans': plans})
                        (evidence / 'observations.json').write_text(
                            json.dumps(result, indent=2, ensure_ascii=False) +
                            '\n')
                    finally:
                        if statement is not None:
                            statement.free()
                    assert connection.main_transaction.info.id == identity
                with connection.cursor() as cursor:
                    cursor.execute('SELECT COUNT(*) FROM "café"')
                    assert cursor.fetchall() == [(1,)]
                    cursor.execute("SELECT COUNT(*) FROM RDB$RELATIONS WHERE "
                                   "RDB$RELATION_NAME='NEVER_CREATED'")
                    assert cursor.fetchone() == (0,)
                connection.rollback()
    client.close()
    (evidence / 'observations.json').write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    options = parser.parse_args()
    result = run_local(options.runtime, options.evidence, qualify)
    raise SystemExit(0 if result['complete'] else 1)
