"""Independent native Shell checksum acceptance for a completed logical dump."""
import json
import hashlib
from copy import deepcopy
from pathlib import Path
import tempfile
import uuid

from ...sdk.relational import RelationalClientError
from ...sdk.tooling import ProviderToolGrant
from .mysql_binlog_archives import connection_options, delegate_credentials, manifest, program_identity

CREDENTIAL_FILE = 'CDEADMIN_MYSQL_VERIFY_CREDENTIAL_FILE'


def document(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate native metadata key')
            result[key] = value
        return result
    try:
        if path.stat().st_size > 16 * 1024 * 1024:
            raise RelationalClientError('Native dump metadata exceeds the supported observation size')
        value = json.loads(path.read_text(encoding='utf8'), object_pairs_hook=pairs)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (OSError, ValueError, UnicodeError):
        raise RelationalClientError('Completed native dump metadata is unavailable or ambiguous') from None


def inventory(path, database, target):
    """Observe native coverage/counts; Shell owns the checksum algorithm."""
    try:
        return _inventory(path, database, target)
    except (KeyError, TypeError, AttributeError):
        raise RelationalClientError('Native dump data metadata has an unsupported shape') from None


def _inventory(path, database, target):
    top = document(path / '@.json')
    done = document(path / '@.done.json')
    checks = document(path / '@.checksums.json')
    if top.get('checksum') is not True or database not in top.get('schemas', []):
        raise RelationalClientError('Select a completed dump with native checksums for this database')
    basename = top.get('basenames', {}).get(database)
    if not isinstance(basename, str) or Path(basename).name != basename or basename in {'.', '..'} or '\\' in basename:
        raise RelationalClientError('Native schema metadata filename is unavailable')
    schema = document(path / (basename + '.json'))
    tables = schema.get('tables')
    if (schema.get('schema') != database or schema.get('includesData') is not True or
            not isinstance(tables, list) or
            not all(isinstance(name, str) and name and '\x00' not in name for name in tables) or
            len(set(tables)) != len(tables)):
        raise RelationalClientError('Native dump data coverage is unavailable')
    data = checks.get('data', {}).get(database, {})
    if not isinstance(data, dict) or set(data) != set(tables):
        raise RelationalClientError('Native checksums do not cover every dumped table')
    result = []
    for table in sorted(tables):
        partitions = data[table].get('partitions')
        if not isinstance(partitions, dict) or not partitions:
            raise RelationalClientError('Native table checksum coverage is incomplete')
        count = 0
        chunks = 0
        for entries in partitions.values():
            if not isinstance(entries, dict) or not entries:
                raise RelationalClientError('Native partition checksum coverage is incomplete')
            for entry in entries.values():
                value = entry.get('count') if isinstance(entry, dict) else None
                if type(value) is not int or not 0 <= value <= 18446744073709551615:
                    raise RelationalClientError('Native checksum row count is unavailable')
                count += value
                chunks += 1
        total = done.get('tableRows', {}).get(database, {}).get(table)
        if type(total) is not int or total != count:
            raise RelationalClientError('Native dump row counts and checksum coverage differ')
        result.append({'source_schema': database, 'target_schema': target, 'table': table,
                       'expected_rows': str(count), 'checksum_chunks': chunks})
    return result


def quote(value):
    return '`' + value.replace('`', '``') + '`'


def identity(cursor):
    cursor.execute('SELECT @@server_uuid,VERSION(),CURRENT_USER(),CURRENT_ROLE()')
    row = cursor.fetchone()
    if len(row) != 4 or str(row[1]).split('-')[0] != '9.7.0':
        raise RelationalClientError('Native dump verification requires MySQL9.7.0')
    return dict(zip(('server_uuid', 'version', 'authenticated_principal', 'active_role'), row))


def script(client, route, path, database, target, expected, marker, threads):
    selected = {'loadDdl': False, 'loadData': False, 'loadIndexes': False, 'loadUsers': False,
                'checksum': True, 'progressFile': '', 'showProgress': False, 'threads': threads,
                'includeSchemas': [database], 'analyzeTables': 'off', 'updateGtidSet': 'off'}
    if target != database:
        selected['schema'] = target
    return ('const authentication=JSON.parse(os.loadTextFile(os.getenv(' + json.dumps(CREDENTIAL_FILE) + ')));\n'
        'const target=' + json.dumps(connection_options(client, route), ensure_ascii=True) + ';\n'
        'for(const key of Object.keys(authentication))target[key]=authentication[key];\n'
        'let stage="connecting";\ntry {shell.connect(target);stage="checking_target";\n'
        'const row=shell.getSession().runSql("SELECT @@server_uuid,VERSION(),CURRENT_USER(),CURRENT_ROLE()").fetchOne();\n'
        'if(!' + json.dumps(list(expected.values()), ensure_ascii=True) + '.every((value,index)=>value===row[index]))'
        'throw new Error("Native target identity changed");\n'
        'stage="checksums";util.loadDump(' + json.dumps(str(path)) + ',' + json.dumps(selected) + ');\n'
        'print(' + json.dumps(marker) + '+JSON.stringify({returned:true,stage:"returned"})+"\\n");\n'
        '} catch(error) {print(' + json.dumps(marker) + '+JSON.stringify({returned:false,stage:stage,'
        'error_code:Number.isInteger(error.code)?error.code:null})+"\\n");throw error;}\n')


def bind_review(client, planned):
    payload = planned['provider_payload']
    compiled = payload['compiled']
    route, options = payload['route'], compiled['options']
    root, path = client._workspace_path(route.get('tool_workspace'), options['path'], 'Native checksum dump path')
    files = manifest(path)
    inventory(path, options.get('source_schema') or route['database'], route['database'])
    program = program_identity(client, route, root)
    connection = client._connect({'route': {**route, 'database': None, 'autocommit': True}})
    cursor = None
    try:
        cursor = connection.cursor()
        target = identity(cursor)
    finally:
        try:
            if cursor is not None: cursor.close()
        finally:
            client._forget_and_close(connection)
    options['_verification_review'] = {'artifact_manifest': files, 'program': program, 'target': target}
    planned['command_preview']['mysql_data_verification_review'] = {
        'target': deepcopy(target), 'program': deepcopy(program), 'artifact_file_count': len(files),
        'artifact_digest': hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
        'server_wide_write_pause': True, 'restores_data': False}
    return planned


def verify(client, route, options):
    """An explicit new acceptance operation never reissues a restore."""
    fields = {'path', 'confirmation', 'source_schema', 'threads', 'enable_local_infile', '_verification_review'}
    if not isinstance(options, dict):
        raise RelationalClientError('Select native verification options')
    target = route.get('database')
    database = options.get('source_schema') or target
    if (set(options) - fields or
            not isinstance(target, str) or not target or options.get('confirmation') != target or
            not isinstance(database, str) or not database or '\x00' in database or
            type(options.get('threads', 4)) is not int or not 1 <= options.get('threads', 4) <= 1024 or
            type(options.get('enable_local_infile', False)) is not bool):
        raise RelationalClientError('Confirm the exact verification database and native options')
    root, path = client._workspace_path(route.get('tool_workspace'), options.get('path'), 'Native checksum dump path')
    before = manifest(path)
    tables = inventory(path, database, target)
    program = program_identity(client, route, root)
    review = options.get('_verification_review')
    if review is not None and (not isinstance(review, dict) or review.get('artifact_manifest') != before or review.get('program') != program):
        raise RelationalClientError('Reviewed native dump, utility or execution host changed; prepare a new review')
    connection = client._connect({'route': {**route, 'database': None, 'autocommit': True}})
    cursor = None
    locked = changed = False
    result = {'operation_id': 'verify_logical', 'data_recovery_verified': False,
              'restore_issued': False, 'production_cutover_verified': False,
              'scope': 'Dumped table data and exact target base-table inventory; definitions and production cutover require their own acceptance.',
              'artifact_manifest': before, 'artifact_path': str(path), 'tables': tables,
              'program': program, 'driver_observation_only': True,
              'transaction_finality_interpreted_by_common_code': False}
    try:
        cursor = connection.cursor()
        expected = identity(cursor)
        if review is not None and review.get('target') != expected:
            raise RelationalClientError('Reviewed native verification server or principal changed; prepare a new review')
        result['target'] = expected
        cursor.execute('SELECT @@GLOBAL.local_infile')
        prior = bool(cursor.fetchone()[0])
        if not prior and options.get('enable_local_infile') is True:
            cursor.execute('SET GLOBAL local_infile=ON')
            changed = True
        elif not prior:
            raise RelationalClientError('Native Shell checksum verification requires trusted local_infile; explicitly authorize temporary enablement')
        cursor.execute('SET SESSION lock_wait_timeout=5')
        cursor.execute('FLUSH TABLES WITH READ LOCK')
        locked = True
        result['server_read_lock_acquired'] = True
        cursor.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME", (target,))
        observed = sorted(row[0] for row in cursor.fetchall())
        result['target_table_inventory_matched'] = observed == sorted(row['table'] for row in tables)
        for table in tables:
            cursor.execute('SELECT CAST(COUNT(*) AS CHAR) FROM ' + quote(target) + '.' + quote(table['table']))
            table['observed_rows'] = str(cursor.fetchone()[0])
        result['row_counts_matched'] = all(row['observed_rows'] == row['expected_rows'] for row in tables)
        marker = 'CDEADMIN_MYSQL_DATA_VERIFY_' + uuid.uuid4().hex + ':'
        with tempfile.TemporaryDirectory(prefix='.mysql-data-verify-', dir=root) as temporary:
            source = Path(temporary) / 'verify.js'
            source.write_text(script(client, route, path, database, target, expected, marker, options.get('threads', 4)), encoding='utf8')
            from ...operations.fileio import private_file
            private_file(source)
            credentials = delegate_credentials(client, route)
            try:
                grant = ProviderToolGrant('mysql-shell', str(root), str(route.get('host') or 'localhost'),
                    int(route.get('port', 3306)), timeout_seconds=route.get('tool_timeout', 3600),
                    secret_environment_names=(CREDENTIAL_FILE,))
                native = credentials.use(lambda view: client._tool_runner.run(grant,
                    ['--no-defaults', '--js', '--log-level=none', '--quiet-start=2', '--file=' + str(source)],
                    secret_config=bytes(view), secret_argument=None, secret_environment_name=CREDENTIAL_FILE, secret_suffix='.json'))
            finally:
                credentials.close()
        result['tool'] = {key: native[key] for key in ('executable_sha256', 'execution_host', 'network_grant', 'return_code', 'process_observation')}
        controls = [json.loads(line[len(marker):]) for line in native['stdout'].splitlines() if line.startswith(marker)]
        control = controls[0] if len(controls) == 1 and isinstance(controls[0], dict) else None
        result['native_control'] = control
        result['native_checksums_returned'] = bool(control == {'returned': True, 'stage': 'returned'} and
            native['return_code'] == 0 and native.get('stdout_truncated') is False and
            native['executable_sha256'] == program['executable_sha256'] and
            native['process_observation'].get('cleanup_confirmed') is True)
        result['artifact_unchanged'] = manifest(path) == before
        result['target_identity_unchanged'] = identity(cursor) == expected
        result['data_recovery_verified'] = all(result.get(key) is True for key in (
            'target_table_inventory_matched', 'row_counts_matched', 'native_checksums_returned',
            'artifact_unchanged', 'target_identity_unchanged'))
        result['state'] = 'verified' if result['data_recovery_verified'] else 'verification_failed'
    finally:
        try:
            if cursor is not None:
                try:
                    if locked:
                        cursor.execute('UNLOCK TABLES')
                        result['server_read_lock_released'] = True
                finally:
                    if changed:
                        cursor.execute('SET GLOBAL local_infile=OFF')
        finally:
            try:
                if cursor is not None:
                    cursor.close()
            finally:
                client._forget_and_close(connection)
    result['local_infile_temporarily_enabled'] = changed
    result['local_infile_restored'] = True
    return result
