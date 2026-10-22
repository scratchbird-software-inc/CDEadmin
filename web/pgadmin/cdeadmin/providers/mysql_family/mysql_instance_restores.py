"""Native instance-load admission and outcomes; no inferred recovery equality."""
from copy import deepcopy
import json
from pathlib import Path
import uuid
from urllib.parse import quote, quote_plus

from ...operations.fileio import private_file
from ...sdk.tooling import ProviderToolGrant
from .mysql_binlog_archives import BinlogArchiveError, connection_options, rows, program_identity
from .mysql_binlog_replay import capture_target

CREDENTIAL_FILE = 'CDEADMIN_MYSQL_INSTANCE_RESTORE_CREDENTIAL_FILE'


def options(value, route):
    from ..relational_admin import RelationalAdministration
    from .provider import MySQLDBAPIClient
    if not isinstance(value, dict):
        raise BinlogArchiveError('Select native instance restore options')
    selected = deepcopy(value)
    try:
        confirmation = selected.pop('target_confirmation')
        if not isinstance(confirmation, str) or str(uuid.UUID(confirmation)) != confirmation:
            raise ValueError()
    except (KeyError, ValueError, AttributeError):
        raise BinlogArchiveError('Confirm the exact native target server UUID') from None
    if set(selected) & {'path', 'progress_file', 'confirmation', 'schema', 'enable_local_infile'}:
        raise BinlogArchiveError('Managed instance loads assign private input/progress paths and preserve schema identities; configure trusted local_infile separately')
    timeout = selected.pop('timeout_seconds', 3600)
    if timeout is not None and (type(timeout) is not int or not 1 <= timeout <= 2147483647):
        raise BinlogArchiveError('Select positive native client runtime seconds or null for no deadline')
    errors = RelationalAdministration._validate_mysql_shell_operation('restore_logical',
        {'path': 'managed-instance', 'confirmation': None, **selected}, {**route, 'database': None}, require_database=False)
    if errors:
        raise BinlogArchiveError('; '.join(row['message'] for row in errors))
    native = MySQLDBAPIClient._shell_options('restore_logical', selected)
    native.setdefault('showProgress', False)
    native.setdefault('updateGtidSet', 'off')
    native.setdefault('checksum', True)
    return {'native_options': native, 'target_confirmation': confirmation, 'timeout_seconds': timeout}


def capture(connection):
    result = capture_target(connection)
    result['state']['local_infile'] = rows(connection, 'SELECT @@GLOBAL.local_infile AS enabled')[0]['enabled']
    result['state']['schemas'] = [row['SCHEMA_NAME'] for row in rows(connection,
        'SELECT SCHEMA_NAME FROM information_schema.SCHEMATA ORDER BY SCHEMA_NAME')]
    return result


def admission(connection, artifact, selected):
    observed = capture(connection)
    if observed['identity']['server_uuid'] != selected['target_confirmation']:
        raise BinlogArchiveError('The confirmed native restore target differs')
    if artifact['source_uuid'] == observed['identity']['server_uuid']:
        raise BinlogArchiveError('Select a separate instance recovery target')
    if not observed['state']['local_infile'] and not selected['native_options'].get('dryRun'):
        raise BinlogArchiveError('Native instance loading requires trusted local_infile to be configured on the recovery target')
    return observed


def script(client, route, directory, target, before, selected, workspace, marker):
    expected = [target[key] for key in ('server_uuid', 'version', 'authenticated_principal', 'active_role')]
    native = {**selected['native_options'], 'progressFile': str(Path(workspace) / 'native-load-progress.json')}
    lock = 'cdeadmin:binlog-load:' + target['server_uuid']
    return ('const authentication=JSON.parse(os.loadTextFile(os.getenv(' + json.dumps(CREDENTIAL_FILE) + ')));\n'
        'const target=' + json.dumps(connection_options(client, route), ensure_ascii=True) + ';\n'
        'for(const key of Object.keys(authentication))target[key]=authentication[key];\n'
        'let invoked=false,returned=false,locked=false,stage="connecting",nativeError=null;\n'
        'try {shell.connect(target);stage="identity";const session=shell.getSession();\n'
        'const observed=session.runSql("SELECT @@server_uuid,VERSION(),CURRENT_USER(),CURRENT_ROLE()").fetchOne();\n'
        'if(!' + json.dumps(expected) + '.every((value,index)=>value===observed[index]))throw new Error("Native restore target identity changed");\n'
        'if(session.runSql("SELECT GET_LOCK(?,0)",' + json.dumps([lock]) + ').fetchOne()[0]!==1)throw new Error("Another native recovery holds this target");locked=true;\n'
        'const lineage=session.runSql("SELECT GTID_SUBSET(?,@@GLOBAL.gtid_executed),GTID_SUBSET(@@GLOBAL.gtid_executed,?)",' +
        json.dumps([before['gtid_executed'], before['gtid_executed']]) + ').fetchOne();\n'
        'if(lineage[0]!==1 || lineage[1]!==1)throw new Error("Native recovery target GTIDs changed after review");\n'
        'stage="loading";invoked=true;util.loadDump(' + json.dumps(str(directory)) + ',' + json.dumps(native) + ');returned=true;stage="returned";\n'
        '} catch(error) {nativeError={code:Number.isInteger(error.code)?error.code:null,sqlstate:typeof error.sqlState==="string"?error.sqlState:null,message:String(error.message || error).slice(0,2048)};throw error;}'
        ' finally {print(' + json.dumps(marker) + '+JSON.stringify({native_load_invoked:invoked,native_load_returned:returned,stage:stage,native_error:nativeError})+"\\n");'
        'if(locked)shell.getSession().runSql("SELECT RELEASE_LOCK(?)",' + json.dumps([lock]) + ');}\n')


def run_load(client, route, credentials, directory, target, before, selected, workspace, program, *, cancel=None, progress=None, boundary=None):
    workspace, directory = Path(workspace), Path(directory)
    result = control = None
    try:
        directory.resolve(strict=True).relative_to(workspace.resolve(strict=True))
        if program_identity(client, route, workspace, cancel=cancel, progress=progress) != program:
            raise BinlogArchiveError('Native restore utility or execution host changed before dispatch')
        path = workspace / 'native-instance-restore.js'
        with path.open('x', encoding='utf8') as stream:
            private_file(path)
            stream.write(script(client, route, directory, target, before, selected, workspace,
                                marker := 'CDEADMIN_INSTANCE_LOAD_' + uuid.uuid4().hex + ':'))
        grant = ProviderToolGrant('mysql-shell', str(workspace), str(route.get('host') or 'localhost'),
            int(route.get('port', 3306)), timeout_seconds=selected['timeout_seconds'],
            allow_unbounded_runtime=selected['timeout_seconds'] is None, secret_environment_names=(CREDENTIAL_FILE,))
    except BaseException as error:
        error.native_preparation_refused = True
        raise
    try:
        def invoke(view):
            def dispatch():
                if boundary is not None: boundary()
                return client._tool_runner.run(grant,
                    ['--no-defaults', '--js', '--log-level=none', '--quiet-start=2', '--file=' + str(path)],
                    secret_config=bytes(view), secret_argument=None, secret_environment_name=CREDENTIAL_FILE, secret_suffix='.json',
                    cancel_signal=cancel, progress=progress)
            observed = dispatch()
            try: controls = [json.loads(line[len(marker):]) for line in observed['stdout'].splitlines() if line.startswith(marker)]
            except (ValueError, UnicodeError): controls = []
            selected_control = controls[0] if len(controls) == 1 and isinstance(controls[0], dict) else None
            if selected_control is not None:
                allowed = {'native_load_invoked', 'native_load_returned', 'stage', 'native_error'}
                if set(selected_control) != allowed or any(type(selected_control.get(key)) is not bool for key in ('native_load_invoked', 'native_load_returned')):
                    selected_control = None
            if selected_control and isinstance(selected_control.get('native_error'), dict):
                message = selected_control['native_error'].get('message', '')
                if not isinstance(message, str): message = ''
                variants = {item for value in json.loads(bytes(view)).values() if isinstance(value, str) and value
                            for item in (value, quote(value, safe=''), quote_plus(value, safe=''))}
                for value in sorted(variants, key=len, reverse=True): message = message.replace(value, '[redacted]')
                selected_control['native_error']['message'] = message[:2048]
            return {key: value for key, value in observed.items() if key not in {'stdout', 'stderr'}}, selected_control
        result, control = credentials.use(invoke)
        if result['executable_sha256'] != program['executable_sha256']:
            raise BinlogArchiveError('Native restore utility identity changed')
        return {'tool': result, 'control': control, 'data_recovery_verified': False,
                'definition_recovery_verified': False, 'production_cutover_verified': False}
    except BaseException as error:
        if result is not None: error.observation = result
        error.control = control
        raise
