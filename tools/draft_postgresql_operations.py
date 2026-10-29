#!/usr/bin/env python3
"""Generate ui_descriptors/postgresql/operations.json.

Only operations the PostgreSQL provider executes through its own
validate/plan/apply route are drafted here: the large-object actions
(providers/postgresql/large_objects.py) and the maintenance actions
(providers/postgresql/maintenance.py: VACUUM, ANALYZE, REINDEX of a table,
index, schema or database, CLUSTER, table TRUNCATE and REFRESH MATERIALIZED
VIEW). Rename, set schema, owner and grant on tables, indexes, sequences, roles
and databases are still legacy-preserved and stay provider gaps.

The descriptor operation_id is sent to the provider verbatim, so only
provider operations that are tier 2/3 and need no ``action`` discriminator
qualify. The ``alter`` actions and create/drop/grant/revoke are tier-1
lifecycle and stay out of this file (design Decision 15).

Usage: python3 tools/draft_postgresql_operations.py [--complete id[@kind],...]
``--complete`` marks the named operations ``complete`` (a bare id means the
large-object action; maintenance ids are ``operation@kind``); the live test
tools/tests/test_ui_descriptor_operations_postgresql.py is the gate for that.
"""
import argparse
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'web/pgadmin/cdeadmin/ui_descriptors/postgresql/operations.json'
KIND = 'large-object'
EVIDENCE = ('Round-tripped by tools/tests/test_ui_descriptor_operations_postgresql.py (dialog draft -> '
            'validate -> plan -> apply on a live PostgreSQL 16.15 server, effect observed). Not PostgreSQL 18.3 '
            'evidence: the profile pins 18.3, this host has 16.')
MAINTENANCE_NOTE = ('Not yet round-tripped against a live server. The provider route is maintenance.compile_operation.')
DRAFT_NOTE = ('Not yet round-tripped against a live server. The provider route is large_objects.compile_operation.')


def text(field_id, label, **kw):
    return {'field_id': field_id, 'label': label, 'control': 'text', 'required': kw.pop('required', False), **kw}


OFFSET = text('offset', 'Byte offset (exact decimal)', default='0',
              help='Decimal text so offsets above 2^53 survive the browser; at most 4 TiB.')


def operation(operation_id, title, category, order, fields, confirmation='none', notes=None, kind=KIND):
    return {
        'operation_id': operation_id,
        'resource_kind': kind,
        'title': title,
        'menu': {'category': category, 'order': order},
        'tier': 2,
        'status': 'draft',
        'confirmation': confirmation,
        'fields': fields,
        'notes': notes or (DRAFT_NOTE if kind == KIND else MAINTENANCE_NOTE),
    }


OPERATIONS = [
    operation('read', 'Read bytes', 'open', 10, [
        OFFSET,
        text('length', 'Byte length (exact decimal)', required=True, default='1048576',
             help='At most 1 MiB per read; the result carries the chunk as base64 with its SHA-256.'),
    ]),
    operation('write', 'Write bytes', 'maintenance', 10, [
        OFFSET,
        {'field_id': 'large_object_data_base64', 'label': 'Binary chunk', 'control': 'code', 'language': 'base64',
         'required': True,
         'help': 'Canonical base64, at most 1 MiB per reviewed chunk. The write is verified by a SHA-256 read-back '
                 'before the transaction commits.'},
    ]),
    operation('truncate', 'Truncate to length', 'maintenance', 20, [
        text('length', 'New length in bytes (exact decimal)', required=True, default='0',
             help='Bytes beyond this length are discarded; a longer length extends the object with zero bytes.'),
    ], confirmation='typed_name',
        notes=DRAFT_NOTE + ' The typed name is the large-object OID, which is the resource display name.'),
    operation('import-server-file', 'Import file from database server', 'backup_restore', 10, [
        text('oid', 'OID (0 allocates a native identity)', default='0'),
        text('server_file', 'Source file on database server', required=True,
             help='The path belongs to the database server host; server file privileges and operating-system '
                  'access apply.'),
    ], confirmation='none',
        notes=DRAFT_NOTE + ' Creates a large object from a server-side file, so it has no existing target; it is '
                           'kept as a data-transfer action rather than the tier-1 create.'),
    operation('export-server-file', 'Export to file on database server', 'backup_restore', 20, [
        text('server_file', 'Destination file on database server (an existing file is overwritten)', required=True,
             help='The path belongs to the database server host; SQL rollback cannot undo the file it writes.'),
        text('confirmation', 'Type the exact server destination path', required=True,
             help='Must equal the destination path above.'),
    ], confirmation='confirm',
        notes=DRAFT_NOTE + ' The typed value is the destination path, not the target name, so it is an ordinary '
                           'required field (as the Firebird confirm-type operations do), not typed_name.'),
]


def flag(field_id, label, **kw):
    return {'field_id': field_id, 'label': label, 'control': 'boolean', 'required': False, **kw}


def maintenance(operation_id, kind, title, category, order, fields, confirmation='none', notes=None):
    return operation(operation_id, title, category, order, fields, confirmation, notes, kind=kind)


VERBOSE = flag('verbose', 'Verbose')
CONCURRENTLY = flag('concurrently', 'Concurrently (cannot run in a transaction block)')
REINDEX_NOTE = ' Runs in autocommit when CONCURRENTLY is chosen.'
OPERATIONS += [
    maintenance('vacuum', 'table', 'Vacuum', 'maintenance', 10, [
        flag('full', 'Full (rewrite the table; exclusive lock)'), flag('freeze', 'Freeze row versions'),
        flag('analyze', 'Also analyze'), VERBOSE,
        {'field_id': 'parallel', 'label': 'Parallel workers (not with Full)', 'control': 'number', 'required': False,
         'help': 'Leave empty to let the server decide; 0 disables parallel index vacuuming.'},
    ], notes=MAINTENANCE_NOTE + ' VACUUM cannot run in a transaction block: the apply route runs it in autocommit.'),
    maintenance('analyze', 'table', 'Analyze', 'maintenance', 20, [
        VERBOSE, flag('skip_locked', 'Skip tables that cannot be locked')]),
    maintenance('reindex', 'table', 'Reindex', 'maintenance', 30, [CONCURRENTLY, VERBOSE],
                notes=MAINTENANCE_NOTE + REINDEX_NOTE),
    maintenance('cluster', 'table', 'Cluster', 'maintenance', 40, [
        {'field_id': 'index', 'label': 'Index to cluster on', 'control': 'text', 'required': False,
         'help': 'Leave empty to reuse the index the table was last clustered on.'}, VERBOSE],
        confirmation='confirm',
        notes=MAINTENANCE_NOTE + ' Rewrites the table under an exclusive lock, hence the confirmation.'),
    maintenance('truncate', 'table', 'Truncate', 'maintenance', 50, [
        flag('restart_identity', 'Restart identity (reset owned sequences)'),
        flag('cascade', 'Cascade to tables with foreign keys to this table'),
    ], confirmation='typed_name', notes=MAINTENANCE_NOTE + ' The typed name is the table name (the resource display name).'),
    maintenance('reindex', 'index', 'Reindex', 'maintenance', 10, [CONCURRENTLY, VERBOSE],
                notes=MAINTENANCE_NOTE + REINDEX_NOTE),
    maintenance('reindex', 'schema', 'Reindex', 'maintenance', 10, [CONCURRENTLY, VERBOSE], confirmation='confirm',
                notes=MAINTENANCE_NOTE + ' REINDEX SCHEMA always runs in autocommit.'),
    maintenance('reindex', 'database', 'Reindex', 'maintenance', 10, [CONCURRENTLY, VERBOSE], confirmation='confirm',
                notes=MAINTENANCE_NOTE + ' REINDEX DATABASE always runs in autocommit and only the connected database.'),
    maintenance('refresh', 'materialized-view', 'Refresh data', 'refresh', 10, [
        flag('with_data', 'Populate with data', default=True),
        flag('concurrently', 'Concurrently (requires a unique index)')]),
]


def key(op):
    return op['operation_id'] if op['resource_kind'] == KIND else f"{op['operation_id']}@{op['resource_kind']}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--complete', default='', help='comma-separated operation ids verified by the live test')
    args = parser.parse_args()
    complete = {item for item in args.complete.split(',') if item}
    unknown = complete - {key(op) for op in OPERATIONS}
    if unknown:
        raise SystemExit(f'unknown operations: {sorted(unknown)}')
    for op in OPERATIONS:
        if key(op) in complete:
            op['status'] = 'complete'
            base = DRAFT_NOTE if op['resource_kind'] == KIND else MAINTENANCE_NOTE
            op['notes'] = EVIDENCE + ('' if op['notes'] == base else op['notes'][len(base):])
    doc = {'schema': 'cdeadmin.ui-operations.v1', 'engine': 'postgresql', 'operations': OPERATIONS}
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + '\n')
    print(f'{len(OPERATIONS)} operations, {len(complete)} complete')


if __name__ == '__main__':
    main()
