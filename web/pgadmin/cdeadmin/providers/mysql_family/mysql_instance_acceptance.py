"""Independent native dump data and exported-definition acceptance."""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import quote as url_quote, quote_plus
import uuid

from ...operations.fileio import private_file
from ...sdk.tooling import ProviderToolGrant
from .mysql_binlog_archives import BinlogArchiveError, manifest, connection_options, program_identity
from .mysql_dump_verification import document, inventory, quote
from .mysql_shell_tools import NATIVE_ERROR_FUNCTION
from . import mysql_system_state as system_state


def options(value):
    if not isinstance(value, dict) or set(value) - {'target_confirmation', 'server_wide_write_pause_confirmed', 'threads', 'timeout_seconds'}:
        raise BinlogArchiveError('Select native acceptance options')
    try:
        target = value['target_confirmation']
        if not isinstance(target, str) or str(uuid.UUID(target)) != target: raise ValueError()
    except (ValueError, KeyError, AttributeError):
        raise BinlogArchiveError('Confirm the exact native acceptance target UUID') from None
    if value.get('server_wide_write_pause_confirmed') is not True:
        raise BinlogArchiveError('Explicitly confirm the server-wide read lock for independent acceptance')
    threads, timeout = value.get('threads', 4), value.get('timeout_seconds', 3600)
    if type(threads) is not int or not 1 <= threads <= 1024 or timeout is not None and (type(timeout) is not int or not 1 <= timeout <= 2147483647):
        raise BinlogArchiveError('Select bounded native threads and positive client runtime seconds or null for no deadline')
    return {'target_confirmation': target, 'server_wide_write_pause_confirmed': True, 'threads': threads, 'timeout_seconds': timeout}


def scopes(directory, artifact):
    """An unexported surface is never an inferred successful check."""
    directory = Path(directory)
    schemas = artifact['schemas']
    data = bool(schemas) and all(row['includes_data'] for row in schemas)
    definitions = bool(schemas) and all(row['includes_ddl'] for row in schemas)
    accounts = bool(artifact['users'])
    top = document(directory / '@.json')
    tables = []
    if data:
        if not artifact['native_checksums_included']:
            raise BinlogArchiveError('Dump data acceptance requires native checksum coverage')
        for row in schemas:
            tables.extend(inventory(directory, row['schema'], row['schema']))
    if definitions:
        paths = {row['path'] for row in artifact['files']}
        for row in schemas:
            base = top['basenames'][row['schema']]
            facts = document(directory / (base + '.json'))
            if row['objects']['views'] and facts.get('includesViewsDdl') is not True:
                raise BinlogArchiveError('Exported view definitions are incomplete')
            required = {base + '.sql'}
            for name in row['objects']['tables'] + row['objects']['views']:
                object_base = facts.get('basenames', {}).get(name)
                if not isinstance(object_base, str) or Path(object_base).name != object_base or '\\' in object_base:
                    raise BinlogArchiveError('Native exported object filename coverage is incomplete')
                required.add(object_base + '.sql')
            if not required <= paths:
                raise BinlogArchiveError('Native exported object SQL files are incomplete')
    if not (data or definitions or accounts or artifact.get('system_state_checkpoint')):
        raise BinlogArchiveError('Select a dump with an exported acceptance surface')
    return {'schemas': [row['schema'] for row in schemas], 'users': artifact['users'],
            'data_requested': data, 'definitions_requested': definitions, 'accounts_requested': accounts,
            'tables': tables,**({'system_state_tables':artifact['system_state_checkpoint']['tables']} if artifact.get('system_state_checkpoint') else {})}


def definition_hash(path):
    """Ignore only the five native transport-header lines; preserve every SQL byte."""
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        header = [stream.readline(16385) for _ in range(5)]
        if (any(len(line) > 16384 for line in header) or
                not header[0].startswith(b'-- MySQLShell dump 2.0.1  Distrib Ver 9.7.0 ') or
                header[1] not in {b'--\n', b'--\r\n'} or not header[2].startswith(b'-- Host: ') or
                re.fullmatch(rb'-- -{10,}\r?\n', header[3]) is None or
                not header[4].startswith(b'-- Server version\t9.7.0')):
            raise BinlogArchiveError('Native definition transport header is unavailable or unsupported')
        while chunk := stream.read(1024 * 1024): digest.update(chunk)
    return digest.hexdigest()


def definitions(source, target, selected, expected, observed):
    """Compare native re-exports without exposing SQL or authentication hashes."""
    source, target = Path(source), Path(target)
    def files(artifact, accounts):
        return {row['path'] for row in artifact['files'] if row['path'].endswith('.sql') and
                (row['path'] == '@.users.sql') is accounts}
    result = {}
    for name, accounts in (('definitions', False), ('accounts', True)):
        if not selected[name + '_requested']:
            result[name] = {'requested': False, 'matched': None}
            continue
        left, right = files(expected, accounts), files(observed, accounts)
        changes = []
        for name_path in sorted(left | right):
            before = definition_hash(source / name_path) if name_path in left else None
            after = definition_hash(target / name_path) if name_path in right else None
            if before != after:
                changes.append({'file': name_path, 'expected_body_sha256': before, 'observed_body_sha256': after})
        result[name] = {'requested': True, 'matched': bool(left) and not changes,
                        'expected_files': len(left), 'observed_files': len(right), 'differences': changes,
                        'scope': 'Exact exported native SQL bodies; only native tool/host/version transport headers are omitted'}
    return result


def table_counts(cursor, selected):
    result = {'requested': selected['data_requested'], 'matched': None, 'schemas': [], 'tables': []}
    if not selected['data_requested']: return result
    for schema in selected['schemas']:
        expected = sorted(row['table'] for row in selected['tables'] if row['source_schema'] == schema)
        cursor.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME", (schema,))
        observed = sorted(row[0] for row in cursor.fetchall())
        result['schemas'].append({'schema': schema, 'expected_tables': expected, 'observed_tables': observed, 'matched': expected == observed})
    for table in selected['tables']:
        cursor.execute('SELECT CAST(COUNT(*) AS CHAR) FROM ' + quote(table['source_schema']) + '.' + quote(table['table']))
        observed = str(cursor.fetchone()[0])
        result['tables'].append({**table, 'observed_rows': observed, 'matched': observed == table['expected_rows']})
    result['matched'] = all(row['matched'] for row in result['schemas'] + result['tables'])
    return result


def unchanged(directory, expected):
    if manifest(directory) != expected['files']:
        raise BinlogArchiveError('Native acceptance input changed during independent observation')


CREDENTIAL_FILE = 'CDEADMIN_MYSQL_INSTANCE_ACCEPTANCE_CREDENTIAL_FILE'


def script(client, route, directory, destination, target, selected, before, marker, threads):
    expected = [target[key] for key in ('server_uuid', 'version', 'authenticated_principal', 'active_role')]
    checksum = {'loadDdl': False, 'loadData': False, 'loadIndexes': False, 'loadUsers': False,
        'checksum': True, 'progressFile': '', 'showProgress': False, 'threads': threads,
        'includeSchemas': selected['schemas'], 'analyzeTables': 'off', 'updateGtidSet': 'off'}
    export = {'users': selected['accounts_requested'], 'ddlOnly': True, 'showProgress': False,
        'threads': threads, 'consistent': True, 'dataMaskingPolicies': False}
    if selected['schemas']: export['includeSchemas'] = selected['schemas']
    else: export['excludeSchemas'] = before['schemas']
    if selected['accounts_requested']: export['includeUsers'] = selected['users']
    lock = 'cdeadmin:binlog-load:' + target['server_uuid']
    return ('const authentication=JSON.parse(os.loadTextFile(os.getenv(' + json.dumps(CREDENTIAL_FILE) + ')));\n'
        'const target=' + json.dumps(connection_options(client, route), ensure_ascii=True) + ';\n'
        'for(const key of Object.keys(authentication))target[key]=authentication[key];\n'
        + NATIVE_ERROR_FUNCTION +
        'let locked=false,stage="connecting",checksumReturned=false,dumpReturned=false,errors=[];\n'
        'function failure(error){errors.push({stage:stage,...nativeError(error)});}\n'
        'try {shell.connect(target);stage="identity";const session=shell.getSession();\n'
        'const observed=session.runSql("SELECT @@server_uuid,VERSION(),CURRENT_USER(),CURRENT_ROLE()").fetchOne();\n'
        'if(!' + json.dumps(expected) + '.every((value,index)=>value===observed[index]))throw new Error("Native acceptance target identity changed");\n'
        'if(session.runSql("SELECT GET_LOCK(?,0)",' + json.dumps([lock]) + ').fetchOne()[0]!==1)throw new Error("Another native recovery holds this target");locked=true;\n'
        'const lineage=session.runSql("SELECT GTID_SUBSET(?,@@GLOBAL.gtid_executed),GTID_SUBSET(@@GLOBAL.gtid_executed,?)",' +
        json.dumps([before['gtid_executed'], before['gtid_executed']]) + ').fetchOne();\n'
        'if(lineage[0]!==1 || lineage[1]!==1)throw new Error("Native acceptance target GTIDs changed");\n'
        'if(' + json.dumps(selected['data_requested']) + '){stage="checksums";try{util.loadDump(' + json.dumps(str(directory)) + ',' + json.dumps(checksum) + ');checksumReturned=true;}catch(error){failure(error);}}\n'
        'if(' + json.dumps(selected['definitions_requested'] or selected['accounts_requested']) + '){stage="definitions";try{util.dumpInstance(' + json.dumps(str(destination)) + ',' + json.dumps(export) + ');dumpReturned=true;}catch(error){failure(error);}}stage="returned";\n'
        '}catch(error){failure(error);throw error;}finally{print(' + json.dumps(marker) + '+JSON.stringify({stage:stage,checksum_returned:checksumReturned,definition_dump_returned:dumpReturned,errors:errors})+"\\n");'
        'if(locked)shell.getSession().runSql("SELECT RELEASE_LOCK(?)",' + json.dumps([lock]) + ');}\n')


def run_checks(client, route, credentials, directory, destination, target, selected, before, workspace, expected_program, options, *, cancel=None, progress=None, boundary=None):
    workspace = Path(workspace)
    for path in (directory, destination):
        try: Path(path).resolve().relative_to(workspace.resolve())
        except ValueError: raise BinlogArchiveError('Native acceptance files escape their execution-host scope') from None
    if program_identity(client, route, workspace, cancel=cancel, progress=progress) != expected_program:
        raise BinlogArchiveError('Native acceptance utility or execution host changed')
    reservation = None
    if route.get('mysql_recovery_binding'):
        from .mysql_recovery_bridge import require_replay_utility, UTILITY_KEY
        require_replay_utility(route, family='acceptance'); reservation = route[UTILITY_KEY].bridge.listener
    marker = 'CDEADMIN_INSTANCE_ACCEPTANCE_' + uuid.uuid4().hex + ':'
    path = workspace / 'native-instance-acceptance.js'
    with path.open('x', encoding='utf8') as stream:
        private_file(path); stream.write(script(client, route, directory, destination, target, selected, before, marker, options['threads']))
    grant = ProviderToolGrant('mysql-shell', str(workspace), str(route.get('host') or 'localhost'),
        int(route.get('port', 3306)), timeout_seconds=options['timeout_seconds'],
        allow_unbounded_runtime=options['timeout_seconds'] is None, secret_environment_names=(CREDENTIAL_FILE,),
        durable_name='mysql-instance-acceptance',guard_parent_death=True)
    def invoke(view):
        if boundary is not None: boundary()
        observed = client._tool_runner.run(grant,
            ['--no-defaults', '--js', '--log-level=none', '--quiet-start=2', '--file=' + str(path)],
            secret_config=bytes(view), secret_argument=None, secret_environment_name=CREDENTIAL_FILE, secret_suffix='.json',
            cancel_signal=cancel, progress=progress, reservation_socket=reservation)
        try: controls = [json.loads(line[len(marker):]) for line in observed['stdout'].splitlines() if line.startswith(marker)]
        except (ValueError, UnicodeError): controls = []
        control = controls[0] if len(controls) == 1 and isinstance(controls[0], dict) else None
        if control is not None:
            if (set(control) != {'stage', 'checksum_returned', 'definition_dump_returned', 'errors'} or
                    any(type(control.get(key)) is not bool for key in ('checksum_returned', 'definition_dump_returned')) or
                    not isinstance(control.get('errors'), list)):
                control = None
        if control:
            variants = {item for value in json.loads(bytes(view)).values() if isinstance(value, str) and value
                        for item in (value, url_quote(value, safe=''), quote_plus(value, safe=''))}
            for error in control['errors']:
                if not isinstance(error, dict): continue
                message = error.get('message', '')
                if not isinstance(message, str): message = ''
                for value in sorted(variants, key=len, reverse=True): message = message.replace(value, '[redacted]')
                error['message'] = message[:2048]
        return {key: value for key, value in observed.items() if key not in {'stdout', 'stderr'}}, control
    tool, control = credentials.use(invoke)
    result = {'tool': tool, 'control': control}
    if tool['executable_sha256'] != expected_program['executable_sha256']:
        error = BinlogArchiveError('Native acceptance executable identity changed')
        error.observation = tool; error.native_check_result = result; raise error
    return result
