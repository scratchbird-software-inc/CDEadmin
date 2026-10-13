"""Bounded native catalog observations on an independently owned connection."""
import json
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


def capture(connection, *, include_system=False):
    from .provider import _resources
    if type(include_system) is not bool:
        raise ValueError('DuckDB system-object selection must be Boolean')
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
    connection.execute('BEGIN TRANSACTION')
    timer = threading.Timer(MAX_SECONDS, connection.interrupt)
    timer.daemon = True
    timer.start()
    try:
        generation = str(uuid.uuid4())
        resources = _resources(Reader(), {'capability_generation': generation})
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
        connection.execute('ROLLBACK')
