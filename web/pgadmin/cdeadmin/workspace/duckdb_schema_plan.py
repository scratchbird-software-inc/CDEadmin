"""Three-way DuckDB DDN design preview; never an execution authorization."""

from copy import deepcopy
import re

from .firebird_catalog_import import _equal
from .firebird_schema_plan import digest
from ..providers.duckdb.provider import _resource_id


_KINDS = {'schema': 'SCHEMA', 'table': 'TABLE', 'view': 'VIEW',
          'sequence': 'SEQUENCE', 'type': 'TYPE', 'macro': 'MACRO'}
_NAME = r'"(?:""|[^"])+"'


def _quote(value):
    if not isinstance(value, str) or not value or '\x00' in value or len(value.encode('utf8')) > 256:
        raise ValueError('Native identifier is empty or exceeds 256 bytes')
    return '"' + value.replace('"', '""') + '"'


def _root(model):
    if model['provenance'].get('mapping') != 'scratchrobin.duckdb.catalog@1':
        raise ValueError('Native DuckDB DDN catalog is required')
    roots = [row for row in model['rows'].values() if row['kind'] == 'database']
    if len(roots) != 1 or roots[0]['system'] != 'false':
        raise ValueError('One exact registered DuckDB file root is required')
    return roots[0]['name']


def _address(row, catalog):
    kind, path = row['kind'], row['path']
    if kind not in _KINDS or not isinstance(path, list):
        raise ValueError('Native adapter for this object kind is not admitted')
    if len(path) != (2 if kind == 'schema' else 3) or path[0] != catalog or path[-1] != row['name']:
        raise ValueError('Object must identify this exact catalog and native schema')
    if row['resource_id'] != _resource_id(kind, path[:-1], path[-1]) or row['system'] != 'false':
        raise ValueError('Native object identity or system classification changed')
    native = row['native']
    if native.get('system_object') is not False or native.get('catalog_metadata', {}).get('temporary') is True:
        raise ValueError('System or temporary definitions are not deployable from a file design')
    return '.'.join(_quote(part) for part in path)


def _definition(row):
    native = row['native']
    catalog = {key: value for key, value in native.get('catalog_metadata', {}).items()
               if key not in {'oid', 'last_value'}}
    return {'ddl': native.get('ddl'),
            'catalog': catalog,
            'columns': native.get('columns') if row['kind'] in {'table', 'view'} else None,
            'constraints': native.get('constraints') if row['kind'] == 'table' else None,
            'indexes': native.get('indexes') if row['kind'] == 'table' else None,
            'overloads': native.get('overloads') if row['kind'] == 'macro' else None}


def _validated_ddl(source, kind, path, *, replace=False):
    if (not isinstance(source, str) or not source or '\x00' in source or
            len(source.encode('utf8')) > 1024 * 1024):
        raise ValueError('One bounded native DDL statement is required')
    qualified = '.'.join(_quote(part) for part in path)
    prefix = 'CREATE ' + ('OR REPLACE ' if replace else '') + _KINDS[kind] + ' ' + qualified
    # Only exact, fully qualified targets are admitted. Captured unqualified
    # DuckDB DDL must be edited to an explicit target before review.
    pattern = re.compile(r'^\s*' + re.escape(prefix) + r'(?=\s|\(|;|$)', re.I)
    if not pattern.match(source):
        raise ValueError('DDL must start with the exact fully qualified native CREATE target')
    import duckdb
    try:
        statements = duckdb.extract_statements(source)
    except duckdb.Error:
        raise ValueError('Native DuckDB parser rejected this DDL') from None
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.CREATE:
        raise ValueError('Exactly one native CREATE statement is required')
    return source


def plan(baseline, desired, live):
    catalog = _root(live)
    for model in (baseline, desired):
        if (_root(model) != catalog or any(model['provenance'].get(field) != live['provenance'].get(field)
            for field in ('endpoint_id', 'database_target_id'))):
            raise ValueError('Design belongs to another endpoint or registered DuckDB file')
    operations, blockers, conflicts, ignored = [], [], [], []
    for identity, after in sorted(desired['rows'].items()):
        before, current = baseline['rows'].get(identity), live['rows'].get(identity)
        if before is not None and _equal(_definition(before), _definition(after)) and not after['native'].get('duckdb_change'):
            continue
        try:
            if before is None and current is not None:
                raise ValueError('New native target already exists')
            target = _address(after, catalog)
            if before is not None:
                _address(before, catalog)
                if current is None or current['kind'] != before['kind'] or not _equal(_definition(current), _definition(before)):
                    conflicts.append({'resource_id': identity, 'reason': 'Live native definition changed since baseline'})
                    continue
            change = after['native'].get('duckdb_change')
            if before is None:
                if change is not None:
                    raise ValueError('Creation cannot carry replacement or deletion intent')
                operation = 'create'
                source = _validated_ddl(after['native'].get('ddl'), after['kind'], after['path'])
            elif change == {'action': 'drop', 'confirmation': before['name']}:
                retained = deepcopy(after)
                retained['native'].pop('duckdb_change')
                if not _equal(_definition(retained), _definition(before)):
                    raise ValueError('Review deletion separately from other native edits')
                operation = 'drop'
                source = 'DROP ' + _KINDS[after['kind']] + ' ' + target + ' RESTRICT'
                import duckdb
                try:
                    statements = duckdb.extract_statements(source)
                except duckdb.Error:
                    raise ValueError('Native DuckDB DROP grammar is unavailable') from None
                if len(statements) != 1 or statements[0].type != duckdb.StatementType.DROP:
                    raise ValueError('Native DROP grammar is unavailable')
            elif change == {'action': 'replace'} and after['kind'] == 'view':
                operation = 'replace'
                source = _validated_ddl(after['native'].get('ddl'), 'view', after['path'], replace=True)
            else:
                raise ValueError('Alteration requires a qualified native adapter; only explicit view replacement is previewed')
            operations.append({'resource_id': identity, 'kind': after['kind'],
                'name': after['name'], 'operation': operation, 'target': target,
                'source': source, 'baseline_sha256': digest(_definition(before)) if before else None,
                'desired_sha256': digest(_definition(after))})
        except (ValueError, KeyError, TypeError) as error:
            blockers.append({'resource_id': identity, 'name': after.get('name'), 'reason': str(error)})
    for identity, row in baseline['rows'].items():
        if identity not in desired['rows']:
            ignored.append({'resource_id': identity, 'name': row['name'],
                'reason': 'Missing desired selection is not deletion intent'})
    return {'format': 'scratchrobin.duckdb.schema-plan@1', 'engine_id': 'duckdb',
        'catalog': catalog, 'operations': operations, 'blockers': blockers,
        'conflicts': conflicts, 'ignored': ignored,
        'execution_sha256': digest(operations), 'native_grammar_validated': True,
        'ready_for_review': bool(operations) and not blockers and not conflicts,
        'application_supported': False, 'executed': False,
        'warnings': ['This native preview does not authorize or execute SQL.',
            'Catalog capture may be partial; absent desired rows never authorize drops.',
            'Fresh target and baseline verification plus reviewed apply are required before execution.']}
