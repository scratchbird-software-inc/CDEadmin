"""Explicit original-session MariaDB variable assignments, never a disposable SET."""
import math
import re

from ...sdk import RelationalClientError
from .mariadb_variables import flagset_assignments, flagset_bitmask, validate_flagset

NAME_PATTERN = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,63}')
METADATA_SQL = (
    'SELECT VARIABLE_NAME,VARIABLE_SCOPE,VARIABLE_TYPE,READ_ONLY,'
    'NUMERIC_MIN_VALUE,NUMERIC_MAX_VALUE,NUMERIC_BLOCK_SIZE,ENUM_VALUE_LIST,'
    'SESSION_VALUE,GLOBAL_VALUE,DEFAULT_VALUE '
    'FROM information_schema.SYSTEM_VARIABLES WHERE UPPER(VARIABLE_NAME)=?'
)


def _compile_expression(request, row):
    _name, _scope, variable_type, _read_only, minimum, maximum, _block, options, *_rest = row
    kind = str(variable_type or '').upper()
    mode = request.get('value_mode')
    if mode == 'DEFAULT':
        return 'DEFAULT', ()
    if mode == 'FLAGS':
        if kind != 'FLAGSET':
            raise ValueError('Structured flags apply only to FLAGSET variables')
        value = flagset_assignments(
            request.get('flags'), request.get('reset_defaults', False), options
        )
        return '?', (value,)
    if mode == 'BITMASK':
        if kind != 'FLAGSET':
            raise ValueError('Numeric masks apply only to FLAGSET variables')
        return str(flagset_bitmask(request.get('bitmask'), options)), ()
    if mode != 'VALUE':
        raise ValueError('Select a native MariaDB session variable value mode')
    if 'value' not in request:
        raise ValueError('A MariaDB session value is required')
    raw = request.get('value')
    if isinstance(raw, bool) or raw is None:
        raise ValueError('Supply typed text for the MariaDB session variable value')
    if kind in {'INT', 'INT UNSIGNED', 'BIGINT', 'BIGINT UNSIGNED'}:
        text = str(raw)
        if not re.fullmatch(r'-?(?:0|[1-9][0-9]{0,20})', text):
            raise ValueError('Integer MariaDB session variables require exact base-10 text')
        parsed = int(text, 10)
        if minimum not in {None, ''} and parsed < int(minimum):
            raise ValueError('Value is below the MariaDB variable minimum')
        if maximum not in {None, ''} and parsed > int(maximum):
            raise ValueError('Value exceeds the MariaDB variable maximum')
        return str(parsed), ()
    if kind == 'DOUBLE':
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError('Floating-point MariaDB session variables require numeric text')
        parsed = float(raw)
        if not math.isfinite(parsed):
            raise ValueError('Floating-point MariaDB session variables must be finite')
        if minimum not in {None, ''} and parsed < float(minimum):
            raise ValueError('Value is below the MariaDB variable minimum')
        if maximum not in {None, ''} and parsed > float(maximum):
            raise ValueError('Value exceeds the MariaDB variable maximum')
        return repr(parsed), ()
    if kind == 'BOOLEAN':
        token = str(raw).strip().upper()
        if token not in {'ON', 'OFF', 'TRUE', 'FALSE', '1', '0'}:
            raise ValueError('Boolean MariaDB session variables require ON/OFF, TRUE/FALSE or 1/0')
        return ('1' if token in {'ON', 'TRUE', '1'} else '0'), ()
    if kind == 'FLAGSET':
        validate_flagset(raw, options)
        return '?', (raw,)
    if kind in {'ENUM', 'SET'}:
        if not isinstance(raw, str):
            raise ValueError('MariaDB ENUM/SET session variables require string choices')
        choices = {item.casefold(): item for item in str(options or '').split(',') if item}
        if not choices:
            raise ValueError('MariaDB ENUM/SET option metadata is unavailable')
        if kind == 'ENUM':
            if raw.casefold() not in choices:
                raise ValueError('Value is not an admitted MariaDB ENUM choice')
            return '?', (choices[raw.casefold()],)
        if raw == '':
            return '?', ('',)
        parts = raw.split(',')
        if any(not part or part.casefold() not in choices for part in parts):
            raise ValueError('Value contains an unknown MariaDB SET choice')
        return '?', (','.join(choices[part.casefold()] for part in parts),)
    if kind == 'VARCHAR':
        if not isinstance(raw, str) or '\x00' in raw:
            raise ValueError('MariaDB VARCHAR session variables require NUL-free text')
        return '?', (raw,)
    raise ValueError('MariaDB session variable type is unsupported')


def action(handle, request):
    if not isinstance(request, dict):
        raise RelationalClientError('Select a typed MariaDB session variable request')
    operation, requested_name = request.get('operation'), request.get('variable')
    common = {'operation', 'variable', 'diagnostics_change_confirmed'}
    fields = {
        'inspect': common,
        'review': common | {'value_mode', 'value', 'flags', 'reset_defaults', 'bitmask'},
        'set_session': common | {
            'value_mode', 'value', 'flags', 'reset_defaults', 'bitmask',
            'expected_value', 'confirmed',
        },
    }
    if (not isinstance(operation, str) or operation not in fields or
            set(request) - fields[operation] or
            not isinstance(requested_name, str) or
            not NAME_PATTERN.fullmatch(requested_name)):
        raise RelationalClientError('Select an admitted MariaDB session variable request')
    if request.get('diagnostics_change_confirmed') is not True:
        raise RelationalClientError(
            'Confirm that explicit native inspection changes session diagnostics'
        )
    cursor = handle.cursor()
    try:
        def read():
            cursor.execute(METADATA_SQL, (requested_name.upper(),))
            row = cursor.fetchone()
            if not row:
                raise RelationalClientError('Unknown MariaDB system variable')
            scope = str(row[1] or '').strip().upper()
            read_only = str(row[3] or '').strip().upper()
            if read_only != 'NO':
                raise RelationalClientError(
                    'MariaDB reports this system variable as read-only'
                )
            if scope not in {'SESSION', 'SESSION ONLY'}:
                raise RelationalClientError(
                    'MariaDB does not expose a session scope for this variable'
                )
            return row

        before = read()
        canonical = str(before[0]).lower()
        before_session = None if before[8] is None else str(before[8])
        expression = None
        arguments = ()
        warnings = []
        warnings_truncated = False
        if operation != 'inspect':
            try:
                expression, arguments = _compile_expression(request, before)
            except (TypeError, ValueError) as error:
                raise RelationalClientError(str(error)) from None
        if operation == 'set_session':
            expected = request.get('expected_value', Ellipsis)
            if (request.get('confirmed') is not True or
                    expected is Ellipsis or
                    (expected is not None and not isinstance(expected, str))):
                raise RelationalClientError(
                    'Refresh and confirm the original MariaDB session variable'
                )
            if before_session != expected:
                raise RelationalClientError(
                    'Original MariaDB session variable changed; review again'
                )
            dispatched_ok = False
            try:
                cursor.execute(
                    'SET SESSION `' + canonical + '` = ' + expression,
                    arguments,
                )
                dispatched_ok = True
                cursor.execute('SHOW WARNINGS LIMIT 101')
                native_warnings = cursor.fetchall()
                warnings_truncated = len(native_warnings) > 100
                warnings = [
                    {'level': str(row[0]), 'code': int(row[1])}
                    for row in native_warnings[:100]
                ]
                after = read()
                if after[:4] != before[:4]:
                    raise ValueError('Native variable metadata changed')
                if str(after[2] or '').upper() == 'FLAGSET' and isinstance(after[8], str):
                    validate_flagset(after[8], after[7])
            except Exception as error:
                code = getattr(error, 'errno', None)
                sqlstate = getattr(error, 'sqlstate', None)
                if (not dispatched_ok and type(code) is int and code >= 1000 and
                        not 2000 <= code < 3000 and isinstance(sqlstate, str)):
                    refusal = RelationalClientError(
                        'MariaDB refused the session variable assignment'
                    )
                    refusal.errno = code
                    refusal.sqlstate = sqlstate
                    refusal.native_status_codes = (code,)
                    refusal.native_dispatched = True
                    refusal.native_acknowledged = False
                    refusal.automatic_retry = False
                    raise refusal from None
                failure = RelationalClientError(
                    'Native session variable outcome unconfirmed; inspect before retrying'
                )
                failure.native_outcome = 'unknown_outcome'
                raise failure from error
        else:
            after = before
        after_session = None if after[8] is None else str(after[8])
        result = dict(
            variable=canonical,
            variable_name=str(before[0]),
            native_scope=str(before[1]),
            native_type=str(before[2]),
            scope='original-session',
            before_value=before_session,
            effective_value=after_session,
            global_value=None if after[9] is None else str(after[9]),
            native_default=None if before[10] is None else str(before[10]),
            commit_requested=False,
            rollback_requested=False,
            future_connection_defaults_changed=False,
            global_value_changed=False,
            automatic_retry=False,
            native_diagnostics_preserved=False,
            native_warnings=warnings,
            native_warnings_truncated=warnings_truncated,
            native_warning_messages_included=False,
        )
        if before[7]:
            result['native_option_names'] = str(before[7]).split(',')
        if operation != 'inspect':
            result.update(
                expected_value=before_session,
                native_statement='SET SESSION `' + canonical + '` = ' + expression,
                bound_parameters=list(arguments),
            )
        if operation == 'review':
            result['ready_to_apply'] = True
        if operation == 'set_session':
            result['outcome'] = 'native_acknowledged_with_readback'
        return result
    finally:
        cursor.close()
