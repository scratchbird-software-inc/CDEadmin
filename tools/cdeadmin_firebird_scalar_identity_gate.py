#!/usr/bin/env python3
"""Native scalar representation changes must invalidate stale grid edits."""
import argparse
import json
import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import nullcontext

from tools.cdeadmin_firebird_stream_gate import (
    _create_client, _route_arguments,
)
from tools.cdeadmin_firebird_local_fixture import run_local
from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION
from pgadmin.cdeadmin.providers.firebird.temporal_arrays import cursor
from pgadmin.cdeadmin.providers.firebird import grid_array_identity
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def qualify(native, admin, route, accounts, evidence, root):
    user, password = accounts['Srp'][0]
    selected = dict(route, user=user, database=str(root / 'identity.fdb'))
    client = _create_client(SimpleNamespace(acquire_secret=None))
    connection = native.create_database(
        password=password, **_route_arguments(selected, native))
    client._connections.append(connection)
    policy = native.tpb(native.Isolation.READ_COMMITTED_RECORD_VERSION,
                        lock_timeout=0)
    connection.default_tpb = policy
    connection.main_transaction.default_tpb = policy
    checks, failures = [], []

    def sql(handle, source, parameters=()):
        with cursor(handle) as query:
            query.execute(source, parameters)
            return query.fetchall() if query.description else None

    try:
        sql(connection, 'CREATE TABLE SCALAR_IDENTITY '
            '(ID INTEGER PRIMARY KEY, '
            'S TIMESTAMP WITH TIME ZONE, F FLOAT, D DOUBLE PRECISION, '
            'T TIME WITH TIME ZONE, V INTEGER)')
        sql(connection, 'CREATE TABLE SIDE_WORK (ID INTEGER)')
        connection.commit()
        sql(connection, 'CREATE VIEW SCALAR_VIEW AS SELECT * '
            'FROM SCALAR_IDENTITY')
        connection.commit()
        for kind, name in (('table', 'SCALAR_IDENTITY'),
                           ('view', 'SCALAR_VIEW')):
            for writer_kind in ('same-transaction', 'other-attachment',
                                'after-preflight'):
                for column, value in (
                        ('S', "S AT TIME ZONE 'UTC'"),
                        ('T', "T AT TIME ZONE 'UTC'"),
                        ('F', '-0.0'), ('D', '-0.0')):
                    for operation in ('update', 'delete'):
                        case = ':'.join((kind, writer_kind, column, operation))
                        writer = None
                        try:
                            sql(connection, 'DELETE FROM SCALAR_IDENTITY')
                            sql(connection, 'INSERT INTO SCALAR_IDENTITY '
                                'VALUES (1, CAST(\'2025-11-02 05:30 UTC\' AS '
                                'TIMESTAMP WITH TIME ZONE) AT TIME ZONE '
                                "'America/New_York', 0, 0, "
                                "CAST('12:30 America/New_York' AS TIME "
                                "WITH TIME ZONE), 1)")
                            connection.commit()
                            sql(connection, 'INSERT INTO SIDE_WORK VALUES (7)')
                            # Both later local changes must share the version
                            # already observed by the retained grid identity.
                            if writer_kind == 'same-transaction':
                                sql(connection, 'UPDATE SCALAR_IDENTITY '
                                    'SET V=2')
                            request = {
                                '_provider_route': selected,
                                'session_id': case,
                                'resource_kind': kind, 'target_resource': {
                                    'resource_kind': kind,
                                    'display_path': [name]}}
                            page = ADMINISTRATION.read_rows(
                                client, request, connection=connection)
                            token = page['rows'][0]['identity_token']
                            plan = ADMINISTRATION.plan({
                                **request, 'operation_id': operation,
                                'draft': {'selector': {
                                    'identity_token': token},
                                    'changes': {'V': 99}}})
                            transaction = connection.main_transaction.info.id
                            writer = connection
                            if writer_kind != 'same-transaction':
                                writer = native.connect(
                                    password=password,
                                    **_route_arguments(selected, native))

                            def change():
                                zoned = column in ('S', 'T')
                                sql(writer, f'UPDATE SCALAR_IDENTITY '
                                    f'SET {column}=' +
                                    (value if zoned else '?'),
                                    () if zoned else (-0.0,))
                                observed = sql(writer, f'SELECT {column} FROM '
                                               'SCALAR_IDENTITY')[0][0]
                                if column in ('S', 'T'):
                                    assert observed.time_zone == 'UTC'
                                else:
                                    assert math.copysign(1, observed) < 0
                                if writer is not connection:
                                    writer.commit()

                            original = grid_array_identity.verify

                            def race(*args):
                                original(*args)
                                change()

                            context = nullcontext()
                            if writer_kind == 'after-preflight':
                                context = patch.object(
                                    grid_array_identity, 'verify', race)
                            else:
                                change()
                            try:
                                with context:
                                    ADMINISTRATION.apply(
                                        client, plan, connection=connection)
                            except RelationalClientError as error:
                                expected_error = (
                                    'exactly one row' if writer_kind ==
                                    'after-preflight' else 'unchanged scalar')
                                assert expected_error in str(error)
                            else:
                                raise AssertionError(
                                    'Stale scalar grid mutation succeeded')
                            assert connection.main_transaction.info.id == (
                                transaction)
                            assert sql(connection, 'SELECT ID FROM '
                                       'SIDE_WORK') == [(7,)]
                            expected = (2 if writer is connection else 1)
                            assert sql(connection, 'SELECT V FROM '
                                       'SCALAR_IDENTITY') == [(expected,)]
                            checks.append({'case': case, 'passed': True})
                        except Exception as error:
                            detail = (str(error) if isinstance(
                                error, AssertionError) else None)
                            failures.append({'case': case,
                                             'type': type(error).__name__,
                                             'detail': detail})
                        finally:
                            connection.rollback()
                            if writer is not None and writer is not connection:
                                writer.close()
    finally:
        client.close()
        (evidence / 'checks.json').write_text(json.dumps(
            {'checks': checks, 'failures': failures}, indent=2)+'\n')
    assert not failures, 'Native scalar identity checks failed'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    options = parser.parse_args()
    result = run_local(options.runtime, options.evidence, qualify)
    raise SystemExit(0 if result['complete'] else 1)
