"""Reviewed SQLite table transformations in one native write transaction."""

import re
import sqlite3
import uuid

from .firebird_schema_plan import digest
from .sqlite_schema_plan import _quote, _source


def _metadata(row):
    return row['native'].get('catalog_metadata', {})


def _autoincrement_table(ddl):
    probe = sqlite3.connect(':memory:')
    try:
        probe.execute(ddl)
        return probe.execute(
            "SELECT 1 FROM main.sqlite_schema WHERE name='sqlite_sequence'"
        ).fetchone() is not None
    finally:
        probe.close()


def _implicit_indexes(connection, table):
    signatures = []
    for index in connection.execute('PRAGMA main.index_list(' + _quote(table) + ')'):
        if index[3] == 'c':
            continue  # Independently declared indexes are replayed separately.
        keys = tuple((part[1], part[2], part[3], part[4])
                     for part in connection.execute('PRAGMA main.index_xinfo(' +
                         _quote(index[1]) + ')') if part[5])
        signatures.append((int(index[2]), str(index[3]), int(index[4]), keys))
    return sorted(signatures, key=repr)


def plan_rebuild(before, after, baseline, connection, *, temp_name=None,
                 column_renames=None):
    if (before['kind'] != 'table' or after['kind'] != 'table' or
            before['resource_id'] != after['resource_id'] or
            before['path'] != after['path'] or
            before['path'] != ['main', before['name']] or
            before['system'] != 'false' or after['system'] != 'false' or
            _metadata(before).get('table_list_type') != 'table'):
        raise ValueError('SQLite rebuild requires one ordinary main-file user table')
    if before['native'].get('ddl') == after['native'].get('ddl'):
        raise ValueError('SQLite rebuild requires a changed desired CREATE TABLE definition')
    source = _source(after)
    old = before['native']
    source_autoincrement = _autoincrement_table(old.get('ddl') or '')
    target_autoincrement = _autoincrement_table(source)
    indexes, triggers = old.get('indexes', []), old.get('triggers', [])
    explicit_indexes = [item for item in indexes if item.get('ddl')]
    if ([item for item in after['native'].get('indexes', []) if item.get('ddl')] != explicit_indexes or
            after['native'].get('triggers') != triggers):
        raise ValueError('SQLite rebuild must retain exact index and trigger definitions')
    if any((not item.get('ddl') and not item['name'].startswith('sqlite_autoindex_')) or
           (item.get('ddl') and not isinstance(item['ddl'], str))
           for item in indexes) or any(not isinstance(item.get('ddl'), str) or
                                      not item['ddl'] for item in triggers):
        raise ValueError('SQLite index or trigger definition cannot be preserved')
    inbound = {row['resource_id']: digest({
        'ddl': row['native'].get('ddl'),
        'dependencies': row['native'].get('dependencies')})
        for row in baseline['rows'].values()
        if row['kind'] == 'table' and row['resource_id'] != before['resource_id'] and
        any(dep.get('referenced_table') == before['name']
            for dep in row['native'].get('dependencies', []))}
    dependencies = {identity: digest(row['native'].get('ddl'))
        for identity, row in baseline['rows'].items()
        if row['kind'] == 'view' or
        (row['kind'] == 'trigger' and row['path'][:2] != before['path'])}
    if temp_name is None:
        temp_name = '__cde_rebuild_' + uuid.uuid4().hex
    elif not re.fullmatch(r'__cde_rebuild_[0-9a-f]{32}', temp_name):
        raise ValueError('SQLite rebuild temporary identity is invalid')
    prefix = re.compile(r'^(\s*CREATE\s+TABLE\s+)"main"\.' +
                        re.escape(_quote(before['name'])), re.I)
    temporary = prefix.sub(lambda match: match.group(1) + _quote('main') + '.' + _quote(temp_name),
                           source, count=1)
    if temporary == source:
        raise ValueError('SQLite table DDL must identify the exact qualified native target')
    probe = sqlite3.connect(':memory:')
    try:
        probe.execute(temporary)
        wanted = probe.execute('PRAGMA main.table_xinfo(' + _quote(temp_name) + ')').fetchall()
        table_options = probe.execute('PRAGMA main.table_list').fetchall()
        target_options = next(row for row in table_options if row[1] == temp_name)
        foreign_keys = probe.execute('PRAGMA main.foreign_key_list(' + _quote(temp_name) + ')').fetchall()
        target_indexes = _implicit_indexes(probe, temp_name)
        probe.execute('ALTER TABLE "main".' + _quote(temp_name) +
                      ' RENAME TO ' + _quote(before['name']))
        expected_ddl = probe.execute('SELECT sql FROM main.sqlite_schema WHERE name=?',
                                     (before['name'],)).fetchone()[0]
    finally:
        probe.close()
    old_probe = sqlite3.connect(':memory:')
    try:
        old_probe.execute(old.get('ddl') or '')
        old_keys = [(row[1], row[2], row[5]) for row in old_probe.execute(
            'PRAGMA main.table_xinfo(' + _quote(before['name']) + ')') if row[5]]
    finally:
        old_probe.close()
    previous = {item['name']: item for item in old.get('columns', [])}
    if not previous or len(previous) != len(old.get('columns', [])):
        raise ValueError('SQLite source columns are unavailable or ambiguous')
    new = {str(row[1]): {'type': str(row[2] or ''), 'pk': int(row[5] or 0),
                         'hidden': int(row[6] or 0), 'ordinal_position': int(row[0]),
                         'nullable': not bool(row[3]), 'default': row[4]}
           for row in wanted}
    if not new or len(new) != len(wanted) or any(col['hidden'] not in (0, 2, 3) for col in new.values()):
        raise ValueError('SQLite rebuild requires ordinary or native generated columns')
    column_renames = column_renames or {}
    if (not isinstance(column_renames, dict) or len(column_renames) > 16 or
            len(set(column_renames.values())) != len(column_renames)):
        raise ValueError('SQLite column rename mapping is invalid')
    for former, renamed in column_renames.items():
        if (not isinstance(former, str) or not isinstance(renamed, str) or
                former not in previous or former in new or
                renamed not in new or renamed in previous or
                new[renamed]['hidden']):
            raise ValueError('SQLite column rename needs an exact source and writable target')
    if column_renames and (indexes or triggers):
        raise ValueError('SQLite column rename with indexes or triggers needs a dependency review')
    removed = [name for name in previous
               if name not in new and name not in column_renames]
    added = [name for name in new
             if name not in previous and name not in column_renames.values()]
    if any(str(previous[former].get('data_type') or '') == new[renamed]['type']
           for former in removed for renamed in added):
        raise ValueError('SQLite removed/new columns may be a rename; map it explicitly or use separate changes')
    common = [name for name in previous if name in new and not new[name]['hidden']]
    if not common and not column_renames:
        raise ValueError('SQLite rebuild requires retained named columns')
    declared = after['native'].get('columns')
    if not isinstance(declared, list) or len(declared) != len(new):
        raise ValueError('Desired SQLite DDN must list every rebuilt column')
    for position, column in enumerate(declared):
        facts = new.get(column.get('name')) if isinstance(column, dict) else None
        if (facts is None or facts['ordinal_position'] != position or
                column.get('data_type') != facts['type'] or
                column.get('primary_key_position') != facts['pk'] or
                column.get('hidden') != facts['hidden'] or
                column.get('nullable') is not facts['nullable'] or
                column.get('default') != facts['default']):
            raise ValueError('Desired SQLite column facts differ from native CREATE TABLE')
    qualified = _quote('main') + '.' + _quote(before['name'])
    temp = _quote('main') + '.' + _quote(temp_name)
    source_names = common + list(column_renames)
    target_names = common + [column_renames[name] for name in column_renames]
    new_keys = [(row[1], row[2], row[5]) for row in wanted if row[5]]
    preserve_rowid = (not _metadata(before).get('without_rowid') and
        not target_options[4] and old_keys == new_keys)
    rowid_alias = None
    if preserve_rowid:
        rowid_alias = next((alias for alias in ('rowid', '_rowid_', 'oid')
                            if alias not in previous and alias not in new), None)
        if rowid_alias is None:
            raise ValueError('SQLite physical rowid is shadowed by declared columns')
    target_projection = ', '.join(([_quote(rowid_alias)] if rowid_alias else []) +
                                  [_quote(name) for name in target_names])
    source_projection = ', '.join(([_quote(rowid_alias)] if rowid_alias else []) +
                                  [_quote(name) for name in source_names])
    copy_sql = f'INSERT INTO {temp} ({target_projection}) SELECT {source_projection} FROM {qualified}'
    stages = [temporary, copy_sql, f'DROP TABLE {qualified}',
              f'ALTER TABLE {temp} RENAME TO {_quote(before["name"])}']
    stages.extend(item['ddl'] for item in explicit_indexes)
    stages.extend(item['ddl'] for item in triggers)
    if any(len(statement.encode('utf8')) > 1024 * 1024 for statement in stages):
        raise ValueError('SQLite rebuild statement exceeds 1 MiB')
    return {'operation': 'rebuild', 'resource_id': before['resource_id'],
        'name': before['name'], 'kind': 'table', 'source': '\n'.join(
            statement.rstrip(';') + ';' for statement in stages),
        'stages': stages, 'temp_name': temp_name,
        'preserved_columns': common, 'column_renames': column_renames,
        'preserve_rowid': preserve_rowid,
        'preserve_foreign_keys': True,
        'inbound_sha256': inbound,
        'dependency_sha256': dependencies,
        'preserve_autoincrement': source_autoincrement and target_autoincrement,
        'target_autoincrement': target_autoincrement,
        'implicit_index_signatures': target_indexes,
        'target_without_rowid': bool(target_options[4]),
        'target_strict': bool(target_options[5]),
        'rowid_alias': rowid_alias,
        'target_columns': [{'name': name, **facts} for name, facts in new.items()],
        'expected_ddl': expected_ddl,
        'preserved_child_ids': [item['resource_id'] for item in explicit_indexes + triggers],
        'baseline_sha256': digest({'ddl': before['native'].get('ddl'),
            'columns': before['native'].get('columns'),
            'indexes': before['native'].get('indexes'),
            'triggers': before['native'].get('triggers')}),
        'desired_sha256': digest({'ddl': after['native'].get('ddl'),
            'columns': after['native'].get('columns')}),
        'warnings': ['Rebuild copies rows under one SQLite write transaction; writers wait for the native lock.',
            'The desired native types apply SQLite affinity and STRICT conversion rules during copying. Generated columns are recomputed. New constraints must accept all copied rows.',
            'All native foreign keys and retained view/trigger bindings are checked before commit.',
            'Removed columns and constraints are explicitly discarded by this selected rebuild.',
            *(['Physical rowids are not preserved when changing storage mode or primary-key identity.'] if not preserve_rowid else []),
            *(['The live AUTOINCREMENT high-water mark is preserved.'] if source_autoincrement and target_autoincrement else []),
            *(['AUTOINCREMENT continuation changes with the explicitly selected desired identity definition.'] if source_autoincrement != target_autoincrement else [])]}
