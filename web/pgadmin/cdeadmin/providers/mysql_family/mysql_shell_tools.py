"""Native Shell operations with exact registered credential factor positions."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile

from ...operations.fileio import private_file
from ...sdk.relational import RelationalClientError
from .mysql_binlog_archives import connection_options

CREDENTIAL_FILE = 'CDEADMIN_MYSQL_SHELL_CREDENTIAL_FILE'

# The pinned polyglot JavaScript bridge wraps native exception metadata in
# Error.cause. Keep the reported code/state; message masking happens while the
# credential lease is still available, before the public text is truncated.
NATIVE_ERROR_FUNCTION = (
    'function nativeError(error){const detail=error && error.cause && typeof error.cause==="object"?error.cause:error;'
    'return {code:Number.isInteger(error.code)?error.code:Number.isInteger(detail.code)?detail.code:null,'
    'sqlstate:typeof error.sqlState==="string"?error.sqlState:typeof detail.sqlState==="string"?detail.sqlState:typeof detail.state==="string"?detail.state:null,'
    'message:String(error.message || error)};}\n'
)


def run(client, route, source, passwords):
    references = dict(route.get('credential_references') or {})
    if route.get('credential_reference_id') is not None:
        references.setdefault('database_password', route['credential_reference_id'])
    names = {'database_password': 'password', 'database_password_2': 'password2',
             'database_password_3': 'password3'}
    kinds = [key for key in names if key in references]
    if len(kinds) != len(passwords):
        raise RelationalClientError('Native Shell credential factor bindings changed')
    authentication = {'password': '', **{names[key]: value for key, value in zip(kinds, passwords)}}
    grant = replace(client._tool_grant(route), secret_environment_names=(CREDENTIAL_FILE,))
    Path(grant.workspace).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.mysql-shell-operation-', dir=grant.workspace) as temporary:
        path = Path(temporary) / 'operation.js'
        script = ('const authentication=JSON.parse(os.loadTextFile(os.getenv(' + json.dumps(CREDENTIAL_FILE) + ')));\n'
            'const target=' + json.dumps(connection_options(client, route), ensure_ascii=True) + ';\n'
            'for(const name of Object.keys(authentication))target[name]=authentication[name];\n'
            'shell.connect(target);\n' + source + ';\n')
        path.write_text(script, encoding='utf8'); private_file(path)
        return client._tool_runner.run(grant,
            ['--no-defaults', '--js', '--quiet-start=2', '--log-level=none', '--file=' + str(path)],
            secret_config=json.dumps(authentication, ensure_ascii=True).encode('utf8'),
            secret_argument=None, secret_suffix='.json', secret_environment_name=CREDENTIAL_FILE,
            redact_values=tuple(passwords))
