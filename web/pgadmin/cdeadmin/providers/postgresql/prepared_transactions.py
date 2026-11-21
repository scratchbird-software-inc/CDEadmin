"""PostgreSQL prepared 2PC transaction inspection and reviewed resolution (PG-AUDIT-TWOPHASE-01).

Resolves orphaned or externally decided two-phase transactions (`COMMIT PREPARED` /
`ROLLBACK PREPARED`) on an owned autocommit administrative connection with exact
GID, database, owner and transaction XID revalidation before dispatch. Never guesses
an external distributed-transaction coordinator decision and never auto-replays.
"""
from __future__ import annotations

from psycopg import Cursor
from psycopg.rows import dict_row

from .native_admin import PostgreSQLNativeAdminError, _literal, _name, _required_text

OPERATIONS = frozenset({'inspect', 'resolve'})


def applies_resolution(request) -> bool:
    return (
        request.get('resource_kind') == 'prepared-transaction'
        and request.get('operation_id') == 'resolve'
    ) or (
        request.get('resource_kind') == 'server'
        and request.get('operation_id') == 'resolve-prepared-transaction'
    )


def observe_gid(connection, gid: str) -> dict | None:
    with Cursor(connection, row_factory=dict_row) as cursor:
        cursor.execute(
            'SELECT gid, prepared::text AS prepared_at, owner, database, '
            'transaction::text AS xid, '
            'CURRENT_USER AS effective_user, '
            '(SELECT rolsuper FROM pg_catalog.pg_roles WHERE rolname = CURRENT_USER) AS is_superuser '
            'FROM pg_catalog.pg_prepared_xacts WHERE gid = %s',
            (gid,),
        )
        row = cursor.fetchone()
        return dict(row) if row is not None else None


def verify_binding(connection, expected: dict) -> dict:
    gid = expected['gid']
    live = observe_gid(connection, gid)
    if live is None:
        raise PostgreSQLNativeAdminError(
            f'Prepared transaction {gid!r} is no longer present in pg_prepared_xacts'
        )
    if expected.get('database') and live['database'] != expected['database']:
        raise PostgreSQLNativeAdminError(
            f'Prepared transaction {gid!r} belongs to database {live["database"]!r}, not {expected["database"]!r}'
        )
    if expected.get('owner') and live['owner'] != expected['owner']:
        raise PostgreSQLNativeAdminError(
            f'Prepared transaction {gid!r} is owned by {live["owner"]!r}, not {expected["owner"]!r}'
        )
    if expected.get('xid') and live['xid'] != str(expected['xid']):
        raise PostgreSQLNativeAdminError(
            f'Prepared transaction {gid!r} XID changed ({live["xid"]} != {expected["xid"]}); review again'
        )
    if not live.get('is_superuser') and live.get('effective_user') != live.get('owner'):
        raise PostgreSQLNativeAdminError(
            f'Resolving prepared transaction {gid!r} requires owner {live["owner"]!r} or superuser authority'
        )
    return live


def compile_operation(operation: str, native: dict, draft: dict) -> dict:
    if operation in {'inspect', 'inspect-prepared-transactions'}:
        return {
            'statement': (
                'SELECT gid, prepared::text AS prepared_at, owner, database, transaction::text AS xid '
                'FROM pg_catalog.pg_prepared_xacts ORDER BY prepared, gid'
            ),
            'read_only': True,
            'returns_rows': True,
        }
    if operation not in {'resolve', 'resolve-prepared-transaction'}:
        raise PostgreSQLNativeAdminError('Unsupported prepared-transaction operation')

    selected_gid = native.get('gid') or native.get('name') or draft.get('gid')
    gid = _name(selected_gid, 'gid')
    if len(gid.encode('utf-8')) > 200:
        raise PostgreSQLNativeAdminError('Prepared transaction GID exceeds PostgreSQL 200-byte limit')
    if draft.get('gid') and native.get('gid') and draft['gid'] != native['gid']:
        raise PostgreSQLNativeAdminError('Prepared transaction GID disagrees with target')

    decision = str(draft.get('decision') or '').strip().upper()
    if decision not in {'COMMIT', 'ROLLBACK'}:
        raise PostgreSQLNativeAdminError('Select explicit COMMIT or ROLLBACK prepared-transaction decision')

    expected_db = _required_text(
        draft.get('expected_database') or native.get('database'),
        'expected_database',
    )
    expected_owner = _required_text(
        draft.get('expected_owner') or native.get('owner'),
        'expected_owner',
    )
    expected_xid = str(draft.get('expected_xid') or native.get('xid') or '').strip() or None
    coordinator_ref = _required_text(
        draft.get('coordinator_reference'),
        'coordinator_reference',
    )
    if draft.get('confirmation') != gid:
        raise PostgreSQLNativeAdminError('Type the exact prepared transaction GID to confirm resolution')

    gid_lit = _literal(gid, 'gid')
    stmt = f'{decision} PREPARED {gid_lit}'
    post = f'SELECT count(*)::integer AS remaining_for_gid FROM pg_catalog.pg_prepared_xacts WHERE gid = {gid_lit}'
    return {
        'statement': stmt,
        'read_only': False,
        'autocommit': True,
        'observation_statement': post,
        'maintenance': {
            'action': f'{decision.lower()}-prepared',
            'object_kind': 'prepared-transaction',
            'object': gid,
            'expected_binding': {
                'gid': gid,
                'database': expected_db,
                'owner': expected_owner,
                **({'xid': expected_xid} if expected_xid else {}),
                'coordinator_reference': coordinator_ref,
            },
            'transaction_mode': 'autocommit',
        },
    }


def form(operation: str, field) -> dict:
    if operation in {'inspect', 'inspect-prepared-transactions'}:
        return {
            'form_id': 'postgresql-prepared-transaction-inspect',
            'form_key': 'native:postgresql:server:prepared-transaction',
            'title': 'Inspect prepared 2PC transactions',
            'fields': [],
        }
    return {
        'form_id': 'postgresql-prepared-transaction-resolve',
        'form_key': 'native:postgresql:server:prepared-transaction',
        'title': 'Resolve prepared 2PC transaction',
        'fields': [
            field('gid', 'Prepared transaction GID', required=True),
            field('expected_database', 'Expected database name', required=True),
            field('expected_owner', 'Expected owner role', required=True),
            field('expected_xid', 'Expected transaction XID (optional)'),
            field(
                'decision',
                'Resolution decision',
                'select',
                required=True,
                options=[
                    {'value': 'COMMIT', 'label': 'COMMIT PREPARED'},
                    {'value': 'ROLLBACK', 'label': 'ROLLBACK PREPARED'},
                ],
            ),
            field(
                'coordinator_reference',
                'External coordinator / incident decision reference',
                required=True,
                help='ScratchRobin never guesses distributed recovery decisions; record the authoritative reference.',
            ),
            field('confirmation', 'Type the exact GID to confirm', required=True),
        ],
    }
