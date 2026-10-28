"""Bridge authoritative relational native facts into ordinary catalog review."""
from copy import deepcopy
from . import ddn_source as ddn
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import subprocess
from .firebird_catalog_export import _json
from .firebird_catalog_import import read_catalog, _decode, _equal, _SLOTS


# Native relation kinds each engine's *_erd.py publishes with a resource_id.
_KINDS = {
    'firebird': {'table', 'view', 'column', 'constraint'},
    'postgresql': {'table', 'partitioned-table', 'foreign-table', 'view', 'materialized-view', 'constraint', 'index'},
    'sqlite': {'table', 'view', 'virtual-table', 'fts-table', 'index'},
    'duckdb': {'table', 'view', 'index'},
}


def _exact_json(value):
    if isinstance(value, Decimal):
        if not value.is_finite(): raise ValueError('Non-finite native number')
        number = str(value)
        return number if '.' in number or 'e' in number.lower() else number + '.0'
    if isinstance(value, dict):
        return '{' + ','.join(_json(key) + ':' + _exact_json(fact) for key, fact in sorted(value.items())) + '}'
    if isinstance(value, list):
        return '[' + ','.join(_exact_json(fact) for fact in value) + ']'
    return _json(value)


_DRAFTS = {}


def _draft_key(snapshot, engine):
    return engine, hashlib.sha256(_json(snapshot).encode('utf-8')).hexdigest()


def read_relations(snapshot, *, engine="firebird"):
    rows, drafts = _read(snapshot, engine)
    # Physical-schema drafts (new indexes/constraints) are kept beside the rows for handoff().
    if len(_DRAFTS) > 8:
        _DRAFTS.clear()
    _DRAFTS[_draft_key(snapshot, engine)] = drafts
    return rows


def _read(snapshot, engine):
    if engine not in {"firebird", "postgresql", "mysql", "mariadb", "sqlite", "duckdb"}:
        raise ValueError("Unsupported relational engine")
    encoded = ddn.validate_workspace(snapshot, 'relational')
    if not _SLOTS.acquire(timeout=1):
        raise ValueError('Catalog reader is busy; retry shortly')
    try:
        result = subprocess.run(['node', ddn.NODE_HEAP_OPTION, str(Path(__file__).parent / 'ddn/read_relations.mjs'), engine],
            input=encoded, text=True, encoding='utf-8', capture_output=True, timeout=20,
            env={key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'TMPDIR') if key in os.environ})
        if result.returncode:
            raise ValueError('Invalid or unsupported relational design')
        parsed = _decode(result.stdout)
        rows = parsed['rows']
        fields = parsed['fields']
        if len(fields) != len(set(fields)):
            raise ValueError('Duplicate relational field identity')
        children = []
        for row in rows:
            if engine in {'firebird', 'postgresql', 'mysql', 'mariadb', 'sqlite', 'duckdb'}:
                row['fields'] = {field['uid']: {**field['properties'], '_label': field['label'],
                    '_property_names': field['property_names'], '_physical': field.get('physical', {})}
                                 for field in parsed['field_records']
                                 if field['parent_resource_id'] == row['resource_id']}
            row['native'] = _decode(row['native_json'])
            if not isinstance(row['native'], dict):
                raise ValueError('Native relational facts must be objects')
            columns = row['native'].pop('diagram_columns', []) if engine == 'firebird' else []
            if not isinstance(columns, list) or not row['uid'].endswith(':' + row['resource_id']):
                raise ValueError('Invalid relational native column mapping')
            prefix = row['uid'][:-len(row['resource_id'])]
            for column in columns:
                if (not isinstance(column, dict) or set(column) != {'resource_id', 'native'} or
                        not isinstance(column['resource_id'], str) or not isinstance(column['native'], dict)):
                    raise ValueError('Invalid relational native column definition')
                uid = prefix + column['resource_id']
                if uid not in fields:
                    raise ValueError('Relational column facts lack their exact field identity')
                children.append({**column, 'uid': uid, 'native_json': _exact_json(column['native']),
                                 'parent_resource_id': row['resource_id'],
                                 'fields': row.get('fields', {}).get(uid, {})})
        if engine in {"mysql", "mariadb"} and rows:
            rows[0]["graphical_relationships"] = parsed.get("relationships", [])
        combined = rows + children
        if len({row['resource_id'] for row in combined}) != len(combined):
            raise ValueError('Duplicate relational native identity')
        return {row['resource_id']: row for row in combined}, parsed.get('physical_drafts', [])
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError('Relational reader unavailable') from error
    finally:
        _SLOTS.release()


def _insert_rows(snapshot, engine, current, rows):
    """Append new native catalog records beside their owning table's record.

    Only the desired document gains them: the baseline never contained these objects."""
    import re
    provenance = current['provenance']
    for item in rows:
        owner = current['rows'][item['owner']]['source_location']
        local = 'o_' + hashlib.sha256(item['resource_id'].encode()).hexdigest()
        metadata = {'resource_id': item['resource_id'], 'kind': item['kind'], 'path_json': _json(item['path']),
                    'system': item['system'], 'native_json': _exact_json(item['native'])}
        uid = engine + ':' + provenance['endpoint_id'] + ':' + provenance['database_target_id'] + ':' + item['resource_id']
        snapshot['files'][owner['file']] += '\n' + ddn.record_definition(
            local, item['name'], metadata, module=f'scratchrobin.{engine}.catalog',
            block=owner['definition_id'].rsplit('.', 1)[0], uid=uid)
    counted = [(name, match) for name, text in snapshot['files'].items()
               for match in re.finditer(r'""objects"":([0-9]+)', text)]
    if len(counted) != 1:
        raise ValueError('Catalog provenance object count is unavailable')
    name, match = counted[0]
    text = snapshot['files'][name]
    snapshot['files'][name] = text[:match.start(1)] + str(int(match.group(1)) + len(rows)) + text[match.end(1):]


def handoff(catalog_snapshot, original, desired, *, engine="firebird", allow_new_columns=False, allow_column_renames=False, allow_foreign_keys=False, allow_temporal_history=False):
    if type(allow_new_columns) is not bool or (allow_new_columns and engine not in {"mysql", "mariadb"}):
        raise ValueError("New-column admission is available only for MySQL/MariaDB")
    if type(allow_column_renames) is not bool or (allow_column_renames and engine not in {"mysql", "mariadb"}):
        raise ValueError("Column-rename admission is available only for MySQL/MariaDB")
    if type(allow_foreign_keys) is not bool or (allow_foreign_keys and engine not in {"mysql", "mariadb"}):
        raise ValueError("Foreign-key design admission is available only for MySQL/MariaDB")
    if type(allow_temporal_history) is not bool or (allow_temporal_history and engine!='mariadb'):
        raise ValueError('Temporal KEEP-history admission applies only to MariaDB')
    constraint_changes = {}
    current = read_catalog(_json(catalog_snapshot), engine=engine)
    before, after = read_relations(original, engine=engine), read_relations(desired, engine=engine)
    before_drafts = _DRAFTS.get(_draft_key(original, engine), [])
    after_drafts = _DRAFTS.get(_draft_key(desired, engine), [])
    known = {item['uid'] for item in before_drafts}
    drafts = {}
    for item in after_drafts:
        if item['uid'] not in known:
            drafts.setdefault(item['parent_resource_id'], []).append(item)
    if drafts and engine not in {'postgresql', 'sqlite', 'duckdb'}:
        raise ValueError('New physical-schema objects are not admitted for this engine')
    new_rows = []
    if set(drafts) - set(after):
        raise ValueError('A physical draft names a parent outside the edited relations')
    if engine in {"mysql", "mariadb"}:
        def relationships(rows):
            values = [edge for row in rows.values() for edge in row.get('graphical_relationships', [])]
            for edge in values:
                if isinstance(edge.get('native_json'), str):edge['native_json'] = _decode(edge['native_json'])
            return sorted(values, key=_exact_json)
        previous={edge.get('uid'):edge for edge in relationships(before)}
        if allow_foreign_keys:
            from .mysql_relational_constraints import relationship_changes
            constraint_changes = relationship_changes(relationships(before), relationships(after), current['rows'],engine=engine)
        elif any(edge.get('uid') is None or not _equal(previous.get(edge['uid']),edge) for edge in relationships(after)):
            raise ValueError('Graphical relationship changes require explicit native foreign-key reconciliation; enable foreign-key design admission or edit the owning table native definition')
    baseline, proposed = deepcopy(catalog_snapshot), deepcopy(catalog_snapshot)
    replacements = [[], []]
    changed = []
    for identity, row in after.items():
        old, live = before.get(identity), current['rows'].get(identity)
        if old is None or live is None or live['kind'] not in _KINDS.get(engine, _KINDS['postgresql']):
            raise ValueError('Relational definition requires explicit catalog identity reconciliation: ' + identity)
        if old['uid'] != live['uid'] or row['uid'] != live['uid']:
            raise ValueError('Relational design belongs to another database or object')
        facts = [deepcopy(old['native']), deepcopy(row['native'])]
        if engine in {'mysql', 'mariadb'}:
            from .mysql_relational_fields import merge_fields
            roots = [item for item in current['rows'].values() if item['kind'] == 'database']
            if len(roots) != 1: raise ValueError('Native relational review requires one database')
            mode=roots[0]['native'].get('definition_context',{}).get('sql_mode',roots[0]['native']['catalog_row'].get('sql_mode',''))
            facts[1] = merge_fields({**old, 'name': live['name'], 'kind': live['kind']},
                {**row, 'name': live['name'], 'kind': live['kind']},
                mode, allow_new_columns=allow_new_columns, allow_column_renames=allow_column_renames,engine=engine)
            if identity in constraint_changes:
                from .mysql_relational_constraints import merge_constraints
                facts[1] = merge_constraints({'name':live['name'],'native':facts[0]},facts[1],
                    constraint_changes[identity],mode,engine=engine)
        if engine == 'firebird' and row.get('parent_resource_id'):
            from .firebird_relational_fields import merge_fields
            facts[1] = merge_fields(old, row, current)
        if engine == 'postgresql':
            from .postgresql_relational_fields import merge_fields
            from .postgresql_physical import merge_physical
            facts[1] = merge_fields(old, row)
            facts[1] = merge_physical({**old, 'native': facts[0]}, {**row, 'native': facts[1]}, live, current,
                                      drafts.get(identity, []))
        if engine in {'sqlite', 'duckdb'}:
            from .embedded_physical import merge as merge_index
            facts[1], created = merge_index(engine, old, row, live, current, drafts.get(identity, []))
            new_rows.extend(created)
            # Column rows are separate native resources; a graphical field edit
            # must not silently diverge from them.
            for uid, fields in row.get('fields', {}).items():
                original = old.get('fields', {}).get(uid)
                if original is None or any(fields.get(name) != original.get(name)
                        for name in ('datatype', 'nullable', 'description')):
                    raise ValueError('Edit the native column definition rather than graphical field properties: ' + identity)
        if engine=='mariadb' and facts[0].get('definition')!=facts[1].get('definition') and 'WITH SYSTEM VERSIONING' in facts[0].get('definition','').upper():
            if not allow_temporal_history:raise ValueError('Graphical system-versioned schema edits require explicit native KEEP-history acceptance')
            intent=facts[1].setdefault('mariadb_change',{})
            if not isinstance(intent,dict):raise ValueError('Invalid native MariaDB change intent')
            intent['temporal_history']='KEEP'
        if engine == 'firebird' and live['kind'] == 'constraint':
            for key in ('source_columns', 'target_columns'):
                if not _equal(facts[0].get(key), facts[1].get(key)):
                    raise ValueError('Edit native constraint definitions rather than adapter column labels')
                for value in facts: value.pop(key, None)
        if not _equal(facts[0], facts[1]): changed.append(identity)
        for index, value in enumerate(facts):
            metadata = {key: live[key] for key in ('resource_id', 'kind', 'path_json', 'system')}
            metadata['native_json'] = _exact_json(value)
            key = 'o_' + hashlib.sha256(identity.encode()).hexdigest()
            declaration_id = live['source_location']['definition_id']
            block, local_id = declaration_id.rsplit('.', 1)
            text = ddn.record_definition(local_id, live['name'], metadata,
                module=f'scratchrobin.{engine}.catalog', block=block, uid=live['uid'])
            replacements[index].append({**live['source_location'], 'text': text})
    for snapshot, edits in zip((baseline, proposed), replacements):
        for edit in sorted(edits, key=lambda value: value['start'], reverse=True):
            # Public DDN source locations are UTF-16 code-unit offsets.
            encoded = snapshot['files'][edit['file']].encode('utf-16-le')
            snapshot['files'][edit['file']] = (encoded[:edit['start'] * 2] + edit['text'].encode('utf-16-le') +
                encoded[edit['end'] * 2:]).decode('utf-16-le')
        if snapshot is proposed and new_rows:
            _insert_rows(snapshot, engine, current, new_rows)
        read_catalog(_json(snapshot), engine=engine)
    changed.extend(item['resource_id'] for item in new_rows)
    return {'baseline': _json(baseline), 'desired': _json(proposed), 'changed_resource_ids': changed,
            'status': 'prepared-for-native-preview', 'executed': False}
