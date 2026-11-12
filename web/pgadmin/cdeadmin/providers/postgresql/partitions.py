"""PostgreSQL partitions on the provider tree (M7, 2026-11-11).

A partition is a table whose ``relispartition`` is set; the provider lists
it as a table and the inherited tree showed it as a partition node. Three
operations cover what the inherited partition and table nodes offered:

* ``create-partition`` on a partitioned table: ``CREATE TABLE child
  PARTITION OF parent <bound>`` with optional sub-partitioning, access
  method, storage options and tablespace, then owner and comment (the
  inherited ``partitions/sql/pg/default/create.sql``);
* ``attach-partition`` on a partitioned table: ``ALTER TABLE parent
  ATTACH PARTITION existing <bound>`` (``attach.sql``);
* ``detach-partition`` on a partition: plain, CONCURRENTLY or FINALIZE
  (``detach.sql``); the concurrent form cannot run in a transaction.

The partition bound is text the user writes (``FOR VALUES FROM (1) TO
(10)``, ``FOR VALUES IN ('a')``, ``FOR VALUES WITH (MODULUS 4, REMAINDER
1)`` or ``DEFAULT``); it is admitted only when PostgreSQL's own parser
accepts it inside a ``CREATE TABLE ... PARTITION OF`` statement, so text
never reaches the engine unparsed.
"""
from __future__ import annotations

import re

from . import tables as table_editor
from .native_admin import (
    PostgreSQLNativeAdminError, _flag, _identifier, _literal, _name,
    _qualified, _reference,
)

DETACH_MODES = {'plain': '', 'concurrently': ' CONCURRENTLY',
                'finalize': ' FINALIZE'}
_BOUND = re.compile(r'(?is)^\s*(DEFAULT|FOR\s+VALUES\s+.+)\s*$')


def _refuse(message):
    raise PostgreSQLNativeAdminError(message)


def _blank(value):
    return value is None or value == ''


def partition_facts(native, relations=None):
    """The partition side of a table: its parent and bound (from the
    captured ``pg_inherits`` child row and ``relpartbound``)."""
    row = native.get('catalog_row') or {}
    relations = relations or {}
    parent = native.get('parent_table')
    inherits = (native.get('children') or {}).get('pg_inherits') or []
    if parent is None and row.get('relispartition') and inherits:
        oid = inherits[0].get('inhparent')
        if isinstance(oid, str) and oid.isdigit():
            oid = int(oid)
        schema, name = relations.get(oid, (None, None))
        parent = {'schema': schema, 'name': name}
    return {
        'is_partition': bool(row.get('relispartition')),
        'parent': parent,
        'partition_bound': row.get('partition_bound_sql'),
        'partition_key': row.get('partition_key_sql'),
    }


def bound(value):
    """A partition bound admitted by PostgreSQL's parser."""
    if not isinstance(value, str) or _BOUND.match(value) is None:
        _refuse('the partition bound is FOR VALUES ... or DEFAULT')
    text = value.strip()
    if ';' in text or '--' in text or '/*' in text or '\x00' in text:
        _refuse('the partition bound contains unsafe syntax')
    from pglast import ast, parse_sql
    from pglast.parser import ParseError
    try:
        parsed = parse_sql(f'CREATE TABLE p_ PARTITION OF q_ {text}')
    except ParseError as exc:
        _refuse(f'the partition bound is not valid: {exc}')
    statement = parsed[0].stmt if len(parsed) == 1 else None
    if not isinstance(statement, ast.CreateStmt) or \
            statement.partbound is None:
        _refuse('the partition bound is not valid')
    return text


def _reference_table(value, label):
    """``schema.table`` typed or picked; both parts become identifiers."""
    if isinstance(value, dict):
        schema, name = value.get('schema'), value.get('name')
    else:
        text = _name(value, label)
        schema, dot, name = text.rpartition('.')
        if not dot:
            _refuse(f'{label} names a table as schema.table')
    return _qualified(_name(schema, label), _name(name, label))


def _parent(native):
    current = table_editor.facts(native)
    return _qualified(_name(current['schema'], 'schema'),
                      _name(current['name'], 'name'))


def create_partition(native, draft):
    parent = _parent(native)
    schema = draft.get('schema') or table_editor.facts(native)['schema']
    name = _name(draft.get('name'), 'name')
    qualified = _qualified(_name(schema, 'schema'), name)
    statement = 'CREATE '
    if _flag(draft, 'relpersistence') if 'relpersistence' in draft else False:
        statement += 'UNLOGGED '
    statement += f'TABLE {qualified} PARTITION OF {parent} '
    statement += 'DEFAULT' if (_flag(draft, 'is_default')
                               if 'is_default' in draft else False) \
        else bound(draft.get('partition_value'))
    if _flag(draft, 'is_partitioned') if 'is_partitioned' in draft else False:
        statement += table_editor._partition_by(draft)
    if not _blank(draft.get('amname')):
        statement += ' USING ' + _identifier(_name(draft['amname'], 'amname'),
                                             'amname')
    statement += table_editor._with_options(draft)
    if not _blank(draft.get('spcname')):
        statement += ' TABLESPACE ' + _identifier(
            _name(draft['spcname'], 'spcname'), 'spcname')
    statements = [statement]
    if not _blank(draft.get('relowner')):
        statements.append(f'ALTER TABLE {qualified} OWNER TO '
                          + _identifier(_name(draft['relowner'], 'relowner'),
                                        'relowner'))
    if not _blank(draft.get('description')):
        statements.append(f'COMMENT ON TABLE {qualified} IS '
                          + _literal(str(draft['description']), 'comment'))
    return {'statement': ';\n'.join(statements), 'read_only': False}


def attach_partition(native, draft):
    parent = _parent(native)
    child = _reference_table(draft.get('partition'), 'partition')
    clause = 'DEFAULT' if (_flag(draft, 'is_default')
                           if 'is_default' in draft else False) \
        else bound(draft.get('partition_value'))
    return {'statement': f'ALTER TABLE {parent} ATTACH PARTITION {child} '
                         f'{clause}', 'read_only': False}


def detach_partition(native, draft, relations=None):
    current = table_editor.facts(native)
    facts = partition_facts(native, relations)
    if not facts['is_partition'] or not facts['parent'] or \
            not facts['parent'].get('name'):
        _refuse('this table is not a partition the listing knows the '
                'parent of')
    mode = draft.get('mode', 'plain')
    if mode not in DETACH_MODES:
        _refuse('mode must be plain, concurrently or finalize')
    parent = _qualified(_name(facts['parent']['schema'], 'schema'),
                        _name(facts['parent']['name'], 'name'))
    child = _qualified(_name(current['schema'], 'schema'),
                       _name(current['name'], 'name'))
    return {'statement': f'ALTER TABLE {parent} DETACH PARTITION {child}'
                         f'{DETACH_MODES[mode]}',
            'read_only': False,
            # DETACH ... CONCURRENTLY cannot run inside a transaction block.
            'autocommit': mode == 'concurrently'}


def compile_operation(operation, native, draft):
    if operation == 'create-partition':
        return create_partition(native, draft)
    if operation == 'attach-partition':
        return attach_partition(native, draft)
    if operation == 'detach-partition':
        return detach_partition(native, draft)
    _refuse('unknown partition operation')


def form(operation, field):
    def column(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    if operation == 'detach-partition':
        fields = [field('mode', 'Mode', 'select', default='plain', options=[
            {'value': 'plain', 'label': 'Detach'},
            {'value': 'concurrently', 'label': 'Detach concurrently '
                                               '(outside a transaction)'},
            {'value': 'finalize', 'label': 'Finalize a pending detach'}])]
        title = 'Detach partition'
    elif operation == 'attach-partition':
        fields = [
            field('partition', 'Table to attach', required=True,
                  help='schema.table of an existing table whose columns '
                       'match.'),
            field('is_default', 'Default partition', 'boolean'),
            field('partition_value', 'Partition bound', help=(
                'FOR VALUES FROM (...) TO (...), FOR VALUES IN (...) or '
                'FOR VALUES WITH (MODULUS m, REMAINDER r); empty with '
                'Default partition.')),
        ]
        title = 'Attach partition'
    else:
        fields = [
            field('name', 'Name', required=True),
            field('schema', 'Schema', help="Empty uses the parent's schema."),
            field('is_default', 'Default partition', 'boolean'),
            field('partition_value', 'Partition bound', help=(
                'FOR VALUES FROM (...) TO (...), FOR VALUES IN (...) or '
                'FOR VALUES WITH (MODULUS m, REMAINDER r).')),
            field('relpersistence', 'Unlogged', 'boolean'),
            field('is_partitioned', 'Sub-partitioned', 'boolean'),
            field('partition_type', 'Sub-partition type', 'select', options=[
                {'value': kind, 'label': kind.title()}
                for kind in table_editor.PARTITION_TYPES]),
            field('partition_keys', 'Sub-partition keys', 'grid', columns=[
                column('key_type', 'Key type', 'select', options=[
                    {'value': 'column', 'label': 'Column'},
                    {'value': 'expression', 'label': 'Expression'}]),
                column('pt_column', 'Column'),
                column('expression', 'Expression'),
                column('collationame', 'Collation'),
                column('op_class', 'Operator class')]),
            field('amname', 'Access method'),
            field('fillfactor', 'Fill factor', 'number'),
            field('spcname', 'Tablespace'),
            field('relowner', 'Owner'),
            field('description', 'Comment', 'multiline'),
        ]
        title = 'Create partition'
    return {'form_id': f'postgresql-table-{operation}',
            'form_key': 'native:postgresql:schema:table',
            'title': title, 'fields': fields}
