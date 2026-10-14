"""Bridge authoritative relational native facts into ordinary catalog review."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import subprocess
from .firebird_catalog_export import MAX_BYTES, MAX_DDN_UNITS, MAX_FILES, _json
from .firebird_catalog_import import read_catalog, _decode, _equal, _SLOTS


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


def read_relations(snapshot, *, engine="firebird"):
    if engine not in {"firebird", "postgresql", "mysql", "mariadb"}:
        raise ValueError("Unsupported relational engine")
    if (not isinstance(snapshot, dict) or set(snapshot) != {'format', 'entry', 'view', 'files'} or
            snapshot['format'] != 'ddn-workspace@1' or not isinstance(snapshot['files'], dict) or
            not 1 <= len(snapshot['files']) <= MAX_FILES or not isinstance(snapshot['entry'], str) or
            not isinstance(snapshot['view'], str) or snapshot['entry'] not in snapshot['files']):
        raise ValueError('Invalid relational workspace envelope')
    for name, source in snapshot['files'].items():
        if (not isinstance(name, str) or not name.endswith('.ddn') or
                any(part in {'', '.', '..'} for part in name.split('/')) or '\\' in name or '\0' in name or
                not isinstance(source, str) or len(source.encode('utf-16-le')) // 2 > MAX_DDN_UNITS):
            raise ValueError('Invalid relational source file')
    encoded = _json(snapshot)
    if len(encoded.encode()) > MAX_BYTES:
        raise ValueError('Relational design exceeds 8 MiB')
    if not _SLOTS.acquire(timeout=1):
        raise ValueError('Catalog reader is busy; retry shortly')
    try:
        result = subprocess.run(['node', str(Path(__file__).parent / 'ddn/read_relations.mjs'), engine],
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
            if engine in {'postgresql', 'mysql', 'mariadb'}:
                row['fields'] = {field['uid']: {**field['properties'], '_label': field['label'],
                    '_property_names': field['property_names']} for field in parsed['field_records']
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
                                 'parent_resource_id': row['resource_id']})
        if engine in {"mysql", "mariadb"} and rows:
            rows[0]["graphical_relationships"] = parsed.get("relationships", [])
        combined = rows + children
        if len({row['resource_id'] for row in combined}) != len(combined):
            raise ValueError('Duplicate relational native identity')
        return {row['resource_id']: row for row in combined}
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError('Relational reader unavailable') from error
    finally:
        _SLOTS.release()


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
        if old is None or live is None or live['kind'] not in ({'table', 'view', 'column', 'constraint'} if engine == 'firebird' else
                {'table', 'partitioned-table', 'foreign-table', 'view', 'materialized-view', 'constraint'}):
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
        if engine == 'postgresql':
            from .postgresql_relational_fields import merge_fields
            facts[1] = merge_fields(old, row)
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
            text = ('record ' + key + ' ' + _json(live['name']) + ' {uid: ' + _json(live['uid']) +
                '; x_record: {' + ','.join(name + ':' + _json(fact) for name, fact in metadata.items()) + '};}')
            replacements[index].append({**live['source_location'], 'text': text})
    for snapshot, edits in zip((baseline, proposed), replacements):
        for edit in sorted(edits, key=lambda value: value['start'], reverse=True):
            # Public DDN source locations are UTF-16 code-unit offsets.
            encoded = snapshot['files'][edit['file']].encode('utf-16-le')
            snapshot['files'][edit['file']] = (encoded[:edit['start'] * 2] + edit['text'].encode('utf-16-le') +
                encoded[edit['end'] * 2:]).decode('utf-16-le')
        read_catalog(_json(snapshot), engine=engine)
    return {'baseline': _json(baseline), 'desired': _json(proposed), 'changed_resource_ids': changed,
            'status': 'prepared-for-native-preview', 'executed': False}
