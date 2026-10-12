#!/usr/bin/env python3
"""Qualify catalog coordinates and names through public native slices."""
import argparse
from ctypes import addressof, create_string_buffer, memmove
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.cdeadmin_firebird_stream_gate import (
    _create_client, _route_arguments,
)
from tools.cdeadmin_firebird_local_fixture import run_local
from pgadmin.cdeadmin.providers.firebird.array_layout import lookup, scalar_sdl
from firebird.driver import core, fbapi
from pgadmin.cdeadmin.providers.firebird import array_upload
from pgadmin.cdeadmin.providers.firebird.temporal_arrays import cursor
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


class IdentityCursor(core.Cursor):
    """Fixture-only assignment of an already written native ARRAY identity."""

    def _unpack_output(self):
        desc = self._stmt._out_desc[0]
        return (fbapi.ISC_QUAD.from_buffer_copy(self._stmt._out_buffer[
            desc.offset:desc.offset+desc.length]),)

    def _pack_input(self, meta, buffer, parameters):
        result_meta, result = super()._pack_input(meta, buffer, [None])
        memmove(addressof(result)+result_meta.get_offset(0),
                addressof(parameters[0]), 8)
        result[result_meta.get_null_offset(0)] = b'\0'
        return result_meta, result


def verify_parameter_admission(connection):
    """An invalid late value must not publish even the first native slice."""
    connection.execute_immediate(
        'CREATE TABLE BINDING_GUARD (ID INTEGER, A SMALLINT[1:300], '
        'N NUMERIC(18,2)[1:2], B BOOLEAN[1:2])')
    connection.commit()
    with cursor(connection) as query:
        query.execute('INSERT INTO BINDING_GUARD VALUES (1, ?, ?, ?)',
                      [[7]*300, ['1.25', '-2.50'], [True, False]])
    connection.commit()
    cases = [
        ('A', [7]*299 + [65537]),
        ('A', [7]*299),
        ('A', [7]*299 + [None]),
        ('N', ['1.25', '0.001']),
        ('B', [True, 1]),
    ]
    for column, values in cases:
        with patch.object(array_upload.ArrayWriter, 'write',
                          side_effect=AssertionError(
                              'Invalid values reached native slice write')) \
                as write:
            with cursor(connection) as query:
                try:
                    query.execute(
                        f'UPDATE BINDING_GUARD SET {column}=? WHERE ID=1',
                        [values])
                except RelationalClientError:
                    pass
                else:
                    raise AssertionError('Invalid ARRAY binding accepted')
            write.assert_not_called()
        assert connection.main_transaction.is_active()
        with connection.cursor() as oracle:
            oracle.execute('SELECT A[300], N[2], B[2] FROM BINDING_GUARD')
            actual = oracle.fetchone()
            assert actual[0] == 7 and actual[1] == Decimal('-2.50')
            assert actual[2] is False
        connection.rollback()
    # A later invalid parameter also prevents an earlier valid ARRAY write.
    with patch.object(array_upload.ArrayWriter, 'write',
                      side_effect=AssertionError('Premature native write')) \
            as write:
        with cursor(connection) as query:
            try:
                query.execute('UPDATE BINDING_GUARD SET A=?, B=?',
                              [[8]*300, [True, 1]])
            except RelationalClientError:
                pass
            else:
                raise AssertionError('Invalid second ARRAY accepted')
        write.assert_not_called()
    connection.rollback()
    return {'invalid_parameter_cases': len(cases)+1,
            'no_native_slice_before_full_validation': True,
            'stored_values_unchanged': True,
            'explicit_transaction_outcome': True}


def qualify(native, admin, route, accounts, evidence, root):
    user, password = accounts['Srp'][0]
    selected = dict(route, user=user, database=str(root / 'layout.fdb'))
    client = _create_client(SimpleNamespace(acquire_secret=None))
    connection = native.create_database(
        password=password, **_route_arguments(selected, native))
    client._connections.append(connection)
    checks = []
    try:
        checks.append(verify_parameter_admission(connection))
        for index, (low, high) in enumerate((
                (65536, 65537), (-65538, -65537),
                (2147483646, 2147483647), (-2147483647, -2147483646),
                (-2147483648, -2147483647))):
            table = 'ARRAY_LAYOUT_' + str(index) + '_' + 'X'*40
            field = '区域'*20
            try:
                connection.execute_immediate(
                    f'CREATE TABLE "{table}" '
                    f'("{field}" INTEGER[{low}:{high}])')
            except native.DatabaseError as exc:
                if low != -2147483648 or str(exc.sqlstate).startswith('08'):
                    raise
                checks.append({'bounds': [low, high],
                               'native_ddl_error': list(exc.gds_codes),
                               'sqlstate': exc.sqlstate})
                connection.rollback()
                continue
            connection.commit()
            with IdentityCursor(connection, connection.main_transaction) as q:
                connection.main_transaction.begin()
                layout, subtype = lookup(q, table, field)
                assert subtype == 0
                bound = layout.array_desc_bounds[0]
                assert (bound.array_bound_lower, bound.array_bound_upper) == (
                    low, high)
                identity = fbapi.ISC_QUAD(0, 0)
                raw = (101).to_bytes(4, 'little', signed=True) + (
                    -202).to_bytes(4, 'little', signed=True)
                data = create_string_buffer(raw, len(raw))
                sdl = scalar_sdl(layout)
                try:
                    connection._att.put_slice(
                        connection.main_transaction._tra, identity, sdl, b'',
                        data)
                except native.DatabaseError as exc:
                    (evidence / 'native-status.json').write_text(json.dumps({
                        'codes': list(exc.gds_codes), 'sdl': sdl.hex(),
                        'bounds': [low, high]}, indent=2))
                    raise
                q.execute(f'INSERT INTO "{table}" VALUES (?)', [identity])
                q.execute(f'SELECT "{field}" FROM "{table}"')
                identity = q.fetchone()[0]
                result = create_string_buffer(8)
                try:
                    received = connection._att.get_slice(
                        connection.main_transaction._tra, identity, sdl, b'',
                        result)
                except native.DatabaseError as exc:
                    status = evidence / 'slice-read-status.json'
                    status.write_text(json.dumps({
                        'codes': list(exc.gds_codes), 'message': str(exc),
                        'bounds': [low, high], 'sdl': sdl.hex()}, indent=2))
                    raise
                assert received == 8 and result.raw == raw
            with connection.cursor() as oracle:
                oracle.execute(
                    f'SELECT "{field}"[{low}], "{field}"[{high}] '
                    f'FROM "{table}"')
                assert oracle.fetchone() == (101, -202)
            connection.rollback()
            checks.append({'bounds': [low, high], 'exact_native_values': True,
                           'full_identifier_bytes':
                               len(field.encode('utf8'))})
    finally:
        client.close()
        (evidence / 'checks.json').write_text(
            json.dumps(checks, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    options = parser.parse_args()
    result = run_local(options.runtime, options.evidence, qualify)
    raise SystemExit(0 if result['complete'] else 1)
