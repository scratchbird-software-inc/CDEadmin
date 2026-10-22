"""Native full-instance logical dumps, private credentials and sealed metadata."""
from copy import deepcopy
import json
import hashlib
from pathlib import Path
import socket
from urllib.parse import quote, quote_plus
import uuid

from ...operations.fileio import private_file
from ...sdk.tooling import ProviderToolGrant
from .mysql_binlog_archives import BinlogArchiveError, connection_options, manifest
from .mysql_dump_verification import document
from .mysql_shell_tools import NATIVE_ERROR_FUNCTION

CREDENTIAL_FILE = 'CDEADMIN_MYSQL_INSTANCE_DUMP_CREDENTIAL_FILE'
INSTANCE_FIELDS = {'users': 'users', 'include_schemas': 'includeSchemas', 'exclude_schemas': 'excludeSchemas',
                   'include_users': 'includeUsers', 'exclude_users': 'excludeUsers'}


def options(value, route):
    if not isinstance(value, dict):
        raise BinlogArchiveError('Select native instance backup options')
    from ..relational_admin import RelationalAdministration
    from .provider import MySQLDBAPIClient
    selected = deepcopy(value)
    if 'path' in selected:
        raise BinlogArchiveError('Managed instance output uses its private job directory')
    timeout = selected.pop('timeout_seconds', 3600)
    if timeout is not None and (type(timeout) is not int or not 1 <= timeout <= 2147483647):
        raise BinlogArchiveError('Select positive native client runtime seconds or null for no deadline')
    instance = {name: selected.pop(name) for name in INSTANCE_FIELDS if name in selected}
    if 'users' in instance and type(instance['users']) is not bool:
        raise BinlogArchiveError('Select whether native account definitions are included')
    for name in INSTANCE_FIELDS.keys() - {'users'}:
        if name in instance:
            try:
                valid = isinstance(instance[name], list) and len(instance[name]) <= 10000 and all(
                    isinstance(item, str) and item and '\x00' not in item and len(item.encode('utf8')) <= 1024 for item in instance[name])
            except UnicodeError: valid = False
            if not valid: raise BinlogArchiveError('Select bounded exact native schema/account identities')
    errors = RelationalAdministration._validate_mysql_shell_operation('backup_logical', {'path': 'managed-instance', **selected}, route, require_database=False)
    if errors:
        raise BinlogArchiveError('; '.join(row['message'] for row in errors))
    if selected.get('dry_run'):
        raise BinlogArchiveError('A managed backup requires native output; use configuration review for dry runs')
    native = MySQLDBAPIClient._shell_options('backup_logical', selected)
    native.update({INSTANCE_FIELDS[name]: item for name, item in instance.items()})
    native.setdefault('users', True)
    native.setdefault('checksum', True)
    native.setdefault('consistent', True)
    native.setdefault('showProgress', False)
    # Enterprise object_policy execution is post beta. Native declaration
    # handling does not establish the missing closed implementation.
    native['dataMaskingPolicies'] = False
    return {'native_options': native, 'timeout_seconds': timeout}


def _names(value, label):
    if not isinstance(value, list) or any(not isinstance(item, str) or not item or '\x00' in item for item in value) or len(set(value)) != len(value):
        raise BinlogArchiveError('Native instance dump ' + label + ' inventory is unavailable')
    return value


def verify(directory, expected_source, *, cancel=None):
    """Native completion and exact bytes; no recovered-data assertion."""
    directory = Path(directory); files = manifest(directory, cancel=cancel)
    top, done = document(directory / '@.json'), document(directory / '@.done.json')
    if (top.get('origin') != 'dumpInstance' or top.get('version') != '2.0.1' or
            top.get('source', {}).get('sysvars', {}).get('server_uuid') != expected_source['server_uuid'] or
            str(top.get('serverVersion')).split('-')[0] != expected_source['version'].split('-')[0] or
            expected_source['version'].split('-')[0] != '9.7.0' or not isinstance(done.get('end'), str)):
        raise BinlogArchiveError('Completed native instance dump source/version differs')
    schemas = _names(top.get('schemas'), 'schema')
    basenames = top.get('basenames')
    if not isinstance(basenames, dict) or set(basenames) != set(schemas):
        raise BinlogArchiveError('Native instance schema metadata coverage differs')
    inventories = []
    for schema in sorted(schemas):
        base = basenames[schema]
        if not isinstance(base, str) or not base or Path(base).name != base or base in {'.', '..'} or '\\' in base:
            raise BinlogArchiveError('Native instance schema basename is unavailable')
        facts = document(directory / (base + '.json'))
        if facts.get('schema') != schema:
            raise BinlogArchiveError('Native instance schema identity differs')
        objects = {name: _names(facts.get(name, []), name) for name in
                   ('tables', 'views', 'events', 'functions', 'procedures', 'libraries')}
        inventories.append({'schema': schema, 'includes_ddl': facts.get('includesDdl') is True,
                            'includes_data': facts.get('includesData') is True, 'objects': objects})
    users = _names(top['users'], 'account') if 'users' in top else None
    if users is not None and not any(row['path'] == '@.users.sql' for row in files):
        raise BinlogArchiveError('Native instance account DDL is missing')
    boundary = top.get('source', {}).get('binlog', {})
    if manifest(directory, cancel=cancel) != files:
        raise BinlogArchiveError('Native instance backup changed during verification')
    return {'format': 'mysqlsh-instance-dump@2.0.1', 'source_uuid': expected_source['server_uuid'],
            'native_dump_server_version': top['serverVersion'],
            'files': files, 'file_count': len(files), 'total_bytes': sum(row['size'] for row in files),
            'schemas': inventories, 'users': users, 'native_consistent': top.get('consistent') is True,
            'native_gtid_snapshot_inconsistent': top.get('gtidExecutedInconsistent') is True,
            'native_boundary': {name: str(boundary[name]) for name in ('file', 'position', 'gtidExecuted') if name in boundary},
            'native_checksums_included': top.get('checksum') is True,
            'verification_scope': 'Native dump completion, exact file hashes and schema/account metadata; not restored data/definition equality or physical recoverability',
            'data_recovery_verified': False, 'production_cutover_verified': False}


def script(client, route, directory, expected, selected, marker):
    fields = ('server_uuid', 'version', 'authenticated_principal', 'active_role')
    return ('const authentication=JSON.parse(os.loadTextFile(os.getenv(' + json.dumps(CREDENTIAL_FILE) + ')));\n'
        'const target=' + json.dumps(connection_options(client, route), ensure_ascii=True) + ';\n'
        'for(const key of Object.keys(authentication))target[key]=authentication[key];\n'
        + NATIVE_ERROR_FUNCTION +
        'let invoked=false,returned=false,stage="connecting",nativeErrorDetail=null;\ntry {shell.connect(target);stage="identity";\n'
        'const observed=shell.getSession().runSql("SELECT @@server_uuid,VERSION(),CURRENT_USER(),CURRENT_ROLE()").fetchOne();\n'
        'if(!' + json.dumps([expected[key] for key in fields]) + '.every((value,index)=>value===observed[index]))'
        'throw new Error("Native instance backup identity changed");\n'
        'stage="dumping";invoked=true;util.dumpInstance(' + json.dumps(str(directory)) + ',' + json.dumps(selected['native_options']) + ');returned=true;stage="returned";\n'
        '} catch(error) {nativeErrorDetail=nativeError(error);throw error;}'
        ' finally {print(' + json.dumps(marker) + '+JSON.stringify({native_dump_invoked:invoked,native_dump_returned:returned,stage:stage,native_error:nativeErrorDetail})+"\\n");}\n')


def acknowledged(control):
    return (isinstance(control, dict) and set(control) == {'native_dump_invoked', 'native_dump_returned', 'stage', 'native_error'} and
            control['native_dump_invoked'] is True and control['native_dump_returned'] is True and
            control['stage'] == 'returned' and control['native_error'] is None)


def run_dump(client, route, credentials, source, selected, directory, workspace, expected_program, *, cancel=None, progress=None):
    workspace = Path(workspace); directory = Path(directory)
    if directory.exists():
        raise BinlogArchiveError('Native instance backup output must be new')
    marker = 'CDEADMIN_MYSQL_INSTANCE_DUMP_' + uuid.uuid4().hex + ':'
    path = workspace / ('native-instance-dump-' + uuid.uuid4().hex + '.js')
    content = script(client, route, directory, source, selected, marker)
    path.write_text(content, encoding='utf8'); private_file(path)
    grant = ProviderToolGrant('mysql-shell', str(workspace), str(route.get('host') or 'localhost'),
        int(route.get('port', 3306)), timeout_seconds=selected['timeout_seconds'],
        allow_unbounded_runtime=selected['timeout_seconds'] is None, secret_environment_names=(CREDENTIAL_FILE,),
        durable_name='mysql-instance-backup')
    result = None; control = None; reply = failure = None
    try:
        def invoke(view):
            payload = bytes(view)
            observed = client._tool_runner.run(grant,
                ['--no-defaults', '--js', '--log-level=none', '--quiet-start=2', '--file=' + str(path)],
                secret_config=payload, secret_argument=None, secret_environment_name=CREDENTIAL_FILE, secret_suffix='.json',
                cancel_signal=cancel, progress=progress)
            try:
                controls = [json.loads(line[len(marker):]) for line in observed['stdout'].splitlines() if line.startswith(marker)]
            except (ValueError, UnicodeError):
                controls = []
            selected_control = controls[0] if len(controls) == 1 and isinstance(controls[0], dict) else None
            # Parse control before masking text: a valid short password such as
            # "true" must not corrupt protocol booleans or the nonce marker.
            if selected_control and isinstance(selected_control.get('native_error'), dict):
                message = selected_control['native_error'].get('message', '')
                if not isinstance(message, str): message = ''
                sensitive = [value for value in json.loads(payload).values() if isinstance(value, str) and value]
                variants = {variant for value in sensitive for variant in (value, quote(value, safe=''), quote_plus(value, safe=''))}
                for value in sorted(variants, key=len, reverse=True): message = message.replace(value, '[redacted]')
                selected_control['native_error']['message'] = message[:2048]
            return {key: value for key, value in observed.items() if key not in {'stdout', 'stderr'}}, selected_control
        result, control = credentials.use(invoke)
        if (result['return_code'] != 0 or result.get('stdout_truncated') is not False or
                result['executable_sha256'] != expected_program['executable_sha256'] or
                result['process_observation'].get('cleanup_confirmed') is not True or
                not acknowledged(control)):
            raise BinlogArchiveError('Native instance backup did not return a qualified completion reply')
        artifact = verify(directory, source, cancel=cancel)
        reply = {'tool': {key: value for key, value in result.items() if key not in {'stdout', 'stderr'}},
                 'native_control': control, 'native_dump_acknowledged': True, 'artifact': artifact}
        return reply
    except BaseException as error:
        failure = error
        if result is not None:
            error.observation = {key: value for key, value in result.items() if key not in {'stdout', 'stderr'}}
        error.native_dump_acknowledged = acknowledged(control)
        error.native_control = control
        error.native_error = control.get('native_error') if control else None
        raise
    finally:
        try: path.unlink(missing_ok=True)
        except OSError as error:
            cleanup = {'complete': False, 'error_type': type(error).__name__, 'relative_file': path.name,
                       'sha256': hashlib.sha256(content.encode('utf8')).hexdigest(), 'execution_hostname': socket.gethostname()}
            if reply is not None:
                reply['private_script_cleanup'] = cleanup
            elif failure is not None:
                failure.private_script_cleanup = cleanup
