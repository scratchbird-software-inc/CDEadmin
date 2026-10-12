"""Native MySQL definitions from catalog DDN. This module never executes SQL."""
import hashlib
import json
import re

from ..providers.mysql_family.mysql_catalog import identifier, SYSTEM
from .firebird_schema_plan import digest

KINDS = {'database', 'table', 'view', 'materialized-view', 'procedure', 'function', 'trigger', 'event'}
CONTEXTUAL = {'view', 'materialized-view', 'procedure', 'function', 'trigger', 'event'}


def _literal(value):
    if not isinstance(value, str) or '\0' in value:
        raise ValueError('Native session context must be text without NUL')
    return "CONVERT(X'" + value.encode('utf8').hex() + "' USING utf8mb4)"


def _script(blocks, database):
    joined = '\n'.join(block['statement'] for block in blocks)
    if len(joined.encode('utf8')) > 8 * 1024 * 1024:
        raise ValueError('Native SQL export exceeds 8 MiB')
    nonce = 0
    while True:
        suffix = hashlib.sha256((str(nonce) + joined).encode()).hexdigest()[:24]
        # The native mysql client stores delimiter in char[16], including NUL.
        delimiter = '__sr_' + suffix[:10]
        if delimiter not in joined:
            break
        nonce += 1
    prefix = '@sr_' + suffix + '_'
    lines = ['-- Native MySQL metadata export; not a migration or execution authorization.',
             '-- DDL commits implicitly. Definers, privileges and external prerequisites are retained.',
             'DELIMITER ' + delimiter]
    def append(value):
        lines.append(value + '\n' + delimiter)
    for setting in ('sql_mode', 'character_set_client', 'collation_connection'):
        append('SET ' + prefix + setting + ' = @@SESSION.' + setting)
    selected = False
    for block in blocks:
        for setting, value in block['context'].items():
            append('SET SESSION ' + setting + ' = ' + _literal(value))
        if block['kind'] != 'database' and not selected:
            append('USE ' + identifier(database))
            selected = True
        lines.append('-- ' + block['kind'])
        append(block['statement'])
    for setting in ('sql_mode', 'character_set_client', 'collation_connection'):
        append('SET SESSION ' + setting + ' = ' + prefix + setting)
        append('SET ' + prefix + setting + ' = NULL')
    lines.append('DELIMITER ;')
    result = '\n\n'.join(lines) + '\n'
    if len(result.encode('utf8')) > 8 * 1024 * 1024:
        raise ValueError('Native SQL export exceeds 8 MiB')
    return result


def build_metadata(document):
    provenance, rows = document['provenance'], document['rows']
    if provenance.get('mapping') != 'scratchrobin.mysql.catalog@1':
        raise ValueError('Select a native MySQL catalog DDN document')
    roots = [row for row in rows.values() if row['kind'] == 'database']
    database_names = {row['native'].get('database') for row in rows.values()}
    if len(database_names) != 1 or len(roots) > 1:
        raise ValueError('Native export requires one unambiguous database')
    database = next(iter(database_names))
    identifier(database)
    if database in SYSTEM:
        raise ValueError('System database definitions are not deployable metadata')
    root = roots[0] if roots else None
    root_facts = root['native'].get('catalog_row', {}) if root else {}
    if root_facts.get('version', '').split('-')[0] != '9.7.0':
        raise ValueError('Native MySQL 9.7.0 identity/context is required; capture the database')
    if root_facts.get('database_name') != database or not root_facts.get('server_uuid'):
        raise ValueError('Native database/server identity is incomplete')
    default_context = {key: root_facts.get(key) for key in ('sql_mode', 'character_set_client', 'collation_connection')}
    observations = root['native'].get('catalog_observations', [])
    unavailable = {item.get('section') for item in observations if item.get('available') is not True}
    blocks, dependencies, blockers, prerequisites = {}, {}, [], []
    deferred_foreign_keys = []
    names = {}
    def problem(row, reason):
        blockers.append({'resource_id': row['resource_id'], 'kind': row['kind'], 'name': row['name'], 'reason': reason})
    for identity, row in sorted(rows.items()):
        native, kind, name = row['native'], row['kind'], row['name']
        address = 'mysql:' + json.dumps([database, kind, native.get('navigator_parent_resource_id'), name], ensure_ascii=False, separators=(',', ':'))
        if (kind not in KINDS or row.get('system') != 'false' or native.get('system_object') is not False or
                identity != address or row['resource_id'] != identity or row.get('path') != [database] + ([] if kind == 'database' else [name])):
            problem(row, 'Unsupported or inconsistent native object identity')
            continue
        statement = native.get('definition')
        if not isinstance(statement, str) or not statement.strip() or '\0' in statement:
            problem(row, 'Exact native SHOW CREATE definition is unavailable')
            continue
        context = {**default_context, **{key: value for key, value in native.get('definition_context', {}).items() if key in default_context}}
        try:
            for value in context.values(): _literal(value)
            charset = context['character_set_client']
            collation = context['collation_connection']
            if not re.fullmatch(r'[A-Za-z0-9_]+', charset) or not re.fullmatch(r'[A-Za-z0-9_]+', collation):
                raise ValueError('Invalid native charset/collation context')
            if kind in CONTEXTUAL and any(native.get('definition_context', {}).get(key) is None
                    for key in ('character_set_client', 'collation_connection')):
                raise ValueError('Stored definition character context is unavailable')
            if charset in {'utf8mb3', 'utf8'} and any(ord(char) > 0xffff for char in statement):
                raise ValueError('Definition does not fit its native utf8mb3 creation context')
        except (ValueError, TypeError) as error:
            problem(row, str(error)); continue
        blocks[identity] = {'resource_id': identity, 'kind': kind, 'name': name, 'statement': statement,
                            'context': context, 'definition_sha256': hashlib.sha256(statement.encode('utf8')).hexdigest()}
        dependencies[identity] = set()
        if kind in {'table', 'view', 'materialized-view'}:
            key = (database, name)
            if key in names:
                problem(row, 'Ambiguous native relation name')
            names[key] = identity
    def require(row, schema, name, kind):
        target = names.get((schema, name))
        if target is None:
            prerequisites.append({'resource_id': row['resource_id'], 'database': schema, 'name': name, 'kind': kind})
        elif target != row['resource_id']:
            dependencies[row['resource_id']].add(target)
    for identity, block in blocks.items():
        row, kind = rows[identity], block['kind']
        native = row['native']
        if root and kind != 'database' and root['resource_id'] in blocks:
            dependencies[identity].add(root['resource_id'])
        if kind == 'table':
            if 'KEY_COLUMN_USAGE' in unavailable or not any(item.get('section') == 'KEY_COLUMN_USAGE' for item in observations):
                problem(row, 'Native foreign-key dependency observations are unavailable')
            foreign_keys = [fk for fk in native.get('children', {}).get('KEY_COLUMN_USAGE', [])
                            if fk.get('referenced_table_name') is not None]
            from .mysql_table_clauses import separate_foreign_keys
            try:
                body, clauses = separate_foreign_keys(block['statement'],
                    {fk['constraint_name'] for fk in foreign_keys}, block['context']['sql_mode'])
                block['statement'] = body
                block['definition_sha256'] = hashlib.sha256(body.encode('utf8')).hexdigest()
                for clause in clauses:
                    source = 'ALTER TABLE ' + identifier(database) + '.' + identifier(block['name']) + ' ADD ' + clause
                    deferred_foreign_keys.append({**block, 'kind': 'foreign-key', 'statement': source,
                        'definition_sha256': hashlib.sha256(source.encode('utf8')).hexdigest()})
            except ValueError as error:
                problem(row, str(error))
            for fk in foreign_keys:
                if (fk.get('referenced_table_schema'), fk['referenced_table_name']) not in names:
                    prerequisites.append({'resource_id': row['resource_id'], 'database': fk.get('referenced_table_schema'),
                        'name': fk['referenced_table_name'], 'kind': 'table'})
        if kind in {'view', 'materialized-view'}:
            if 'VIEW_TABLE_USAGE' in unavailable or not any(item.get('section') == 'VIEW_TABLE_USAGE' for item in observations):
                problem(row, 'Native view dependency observations are unavailable')
            for target in native.get('children', {}).get('VIEW_TABLE_USAGE', []):
                require(row, target.get('table_schema'), target.get('table_name'), 'relation')
        if kind == 'trigger':
            require(row, native.get('catalog_row', {}).get('event_object_schema'), native.get('catalog_row', {}).get('event_object_table'), 'table')
        # Routine bodies are preserved whole. Their dynamic/external references
        # cannot be inferred from lexical matches in SQL text.
        if kind in CONTEXTUAL:
            prerequisites.append({'resource_id': identity, 'kind': 'native-body-and-definer',
                'name': block['name'], 'database': database})
    ordered, pending = [], {key: value.copy() for key, value in dependencies.items()}
    while pending:
        ready = sorted(key for key, needs in pending.items() if not needs)
        if not ready:
            for identity in sorted(pending): problem(rows[identity], 'Native dependency cycle requires an explicit staged adapter')
            break
        for identity in ready:
            ordered.append(blocks[identity]); del pending[identity]
        for needs in pending.values(): needs.difference_update(ready)
    if deferred_foreign_keys and not blockers:
        # Table bodies must all exist before any FK is admitted. Other native
        # object dependencies retain their previous topological order.
        ordered = [block for block in ordered if block['kind'] in {'database', 'table'}] + deferred_foreign_keys + [
            block for block in ordered if block['kind'] not in {'database', 'table'}]
    # Deterministically deduplicate composite-FK prerequisite observations.
    prerequisites = list({json.dumps(item, sort_keys=True): item for item in prerequisites}.values())
    encoding_required = any(block['context']['character_set_client'] not in {'utf8mb4','utf8mb3','utf8'} for block in ordered)
    script = _script(ordered, database) if ordered and not blockers and not encoding_required else None
    return {'format': 'scratchrobin.mysql.native-metadata@1', 'engine_id': 'mysql',
        'mode': 'export-only', 'executed': False, 'deployment_authorized': False,
        'source_sha256': document.get('sha256'), 'database': database, 'server_uuid': root_facts['server_uuid'],
        'statements': ordered, 'statements_sha256': digest(ordered), 'script': script,
        'native_encoding_required': encoding_required and not blockers,
        'script_sha256': hashlib.sha256(script.encode('utf8')).hexdigest() if script else None,
        'blockers': blockers, 'prerequisites': prerequisites, 'script_available': script is not None,
        'warnings': ['Imported definitions are user input; native grammar and live state have not been validated.',
            'MySQL DDL commits implicitly. This export is not an atomic migration or a reviewed apply plan.',
            'Privilege-filtered observational metadata does not prove complete coverage or dependency discovery.',
            'Account/grant creation and data are excluded; visible privilege facts remain documentary.']}
