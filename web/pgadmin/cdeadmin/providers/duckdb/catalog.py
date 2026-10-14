"""Bounded native catalog observations on an independently owned connection."""
import json
import os
import tempfile
import threading
import time
import uuid

MAX_FACTS = 20000
MAX_BYTES = 8 * 1024 * 1024
MAX_SECONDS = 30
SAFE_OPTIONS = frozenset({'read_only', 'block_size', 'row_group_size',
    'storage_version', 'compression', 'encryption_cipher'})


def database_location(path, database_type, options):
    """Foreign attachment locations/options can contain connection credentials."""
    import os
    local = database_type == 'duckdb' and isinstance(path, str) and (
        os.path.isabs(path) or path == ':memory:')
    options = options if isinstance(options, dict) else {}
    safe = {key: value for key, value in options.items() if key.lower() in SAFE_OPTIONS}
    return {'path': path if local else None, 'path_redacted': bool(path) and not local,
            'options': safe, 'options_redacted': len(safe) != len(options)}


def _macro_target(source, database):
    """Read the object path from one DuckDB-exported CREATE MACRO statement."""
    import duckdb
    encoded = source.encode('utf8')
    positions = duckdb.tokenize(source)
    tokens = []
    for index, (offset, kind) in enumerate(positions):
        following = positions[index + 1][0] if index + 1 < len(positions) else len(encoded)
        word = encoded[offset:following].decode('utf8').strip()
        if kind == duckdb.token_type.identifier and word.startswith('"') and word.endswith('"'):
            word = word[1:-1].replace('""', '"')
        tokens.append((kind, word))
    if (len(tokens) < 5 or tokens[0][1].casefold() != 'create' or
            tokens[1][1].casefold() != 'macro'):
        return None
    names, expect_name = [], True
    for kind, word in tokens[2:]:
        if kind == duckdb.token_type.operator and word == '(':
            break
        if expect_name:
            if kind != duckdb.token_type.identifier or not word:
                return None
            names.append(word)
        elif kind != duckdb.token_type.operator or word != '.':
            return None
        expect_name = not expect_name
    if expect_name or not 1 <= len(names) <= 2:
        return None
    return (database, names[0], names[1]) if len(names) == 2 else (
        database, 'main', names[0])


def _capture_macro_source(connection, resources, account):
    """Recover source signatures from a transaction-consistent schema-only copy."""
    import duckdb
    macros = {(row['display_path'][0], row['display_path'][1], row['display_name']): row
        for row in resources if row['resource_kind'] == 'macro' and
        not row.get('native', {}).get('catalog_metadata', {}).get('internal')}
    if not macros:
        return
    active_database, active_schema = connection.execute(
        'SELECT current_database(), current_schema()').fetchone()
    quote = lambda value: '"' + value.replace('"', '""') + '"'
    literal = lambda value: "'" + value.replace("'", "''") + "'"
    for database in sorted({path[0] for path in macros}):
        with tempfile.TemporaryDirectory(prefix='scratchrobin-duckdb-macro-') as root:
            alias = '__scratchrobin_macro_' + uuid.uuid4().hex
            scratch = os.path.join(root, 'schema.duckdb')
            exported = os.path.join(root, 'export')
            connection.execute('ATTACH ' + literal(scratch) + ' AS ' +
                quote(alias) + ' (READ_WRITE)')
            connection.execute('COPY FROM DATABASE ' + quote(database) +
                ' TO ' + quote(alias) + ' (SCHEMA)')
            connection.execute('USE ' + quote(alias))
            connection.execute('EXPORT DATABASE ' + literal(exported))
            connection.execute('USE ' + quote(active_database) + '.' + quote(active_schema))
            connection.execute('DETACH ' + quote(alias))
            schema_file = os.path.join(exported, 'schema.sql')
            if os.path.getsize(schema_file) > MAX_BYTES:
                raise ValueError('DuckDB macro source export exceeds the catalog byte limit')
            with open(schema_file, encoding='utf8') as stream:
                source = stream.read()
            for statement in duckdb.extract_statements(source):
                target = _macro_target(statement.query, database)
                if target in macros:
                    row = macros[target]
                    if 'source_ddl' in row['native']:
                        raise ValueError('DuckDB macro source export repeated a macro group')
                    row['native']['source_ddl'] = statement.query.rstrip('; \n') + ';'
                    account(row['native']['source_ddl'])
    if any('source_ddl' not in row['native'] for row in macros.values()):
        raise ValueError('DuckDB macro source export omitted an observed macro')


def capture(connection, *, include_system=False, _in_transaction=False,
            include_macro_source=False):
    from .provider import _resources
    if type(include_system) is not bool or type(include_macro_source) is not bool:
        raise ValueError('DuckDB system-object selection must be Boolean')
    if include_macro_source and _in_transaction:
        raise ValueError('Macro source capture needs its own read transaction')
    started = time.monotonic()
    facts = size = 0
    def account(value):
        nonlocal facts, size
        facts += 1
        size += len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf8'))
        if facts > MAX_FACTS or size > MAX_BYTES or time.monotonic() - started > MAX_SECONDS:
            raise ValueError('DuckDB catalog exceeds 20,000 facts, 8 MiB or 30 seconds')
    class Reader:
        def execute(self, source, parameters=()):
            connection.execute(source, parameters)
            return self
        def fetchall(self):
            rows = []
            while True:
                batch = connection.fetchmany(128)
                if not batch: return rows
                for row in batch:
                    account(row); rows.append(row)
        def fetchone(self):
            row = connection.fetchone()
            if row is not None: account(row)
            return row
    # The provider supplies this dedicated connection. BEGIN refusing an
    # already active transaction prevents accidentally adopting caller work.
    if not _in_transaction:
        connection.execute('BEGIN TRANSACTION')
    timer = threading.Timer(MAX_SECONDS, connection.interrupt)
    timer.daemon = True
    timer.start()
    try:
        generation = str(uuid.uuid4())
        resources = _resources(Reader(), {'capability_generation': generation})
        if include_macro_source:
            _capture_macro_source(connection, list(resources), account)
        retained = []
        for resource in resources:
            native = resource.setdefault('native', {})
            metadata = native.get('catalog_metadata', {})
            system = bool(metadata.get('internal')) or (
                resource['resource_kind'] == 'schema' and
                resource['display_name'] in {'information_schema', 'pg_catalog'})
            native['system_object'] = system
            if system and not include_system: continue
            account(resource); retained.append(resource)
        warnings = [
            'Native catalog reads share one transaction; runtime extension state is observational.',
            'Temporary objects and interactive uncommitted work on other connections are not captured.',
            'Foreign attachment connection strings and confidential options are omitted.',
            'Sequence observations are not a resumable backup; nextval is never called.',
            'This metadata collection is not a physical backup or deployable migration.',
        ]
        for resource in retained:
            if resource['resource_kind'] in {'database', 'attached-database'}:
                resource['native'].update(catalog_warnings=warnings,
                    coverage_complete=False,
                    catalog_observations=[{'section': 'visible-native-catalog', 'available': True}])
        result = {'resources': retained, 'generation': generation, 'warnings': warnings,
                  'complete': False, 'consistency': 'owned-native-transaction'}
        # Account final provenance as well as native read/expanded rows.
        account(result)
        return result
    finally:
        timer.cancel(); timer.join()
        if not _in_transaction:
            connection.execute('ROLLBACK')
