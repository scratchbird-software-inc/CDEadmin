"""MariaDB FLAGSET assignment admission from native option metadata."""
import re


def validate_flagset(value, options):
    if not isinstance(value, str) or not isinstance(options, str):
        raise ValueError('Native flag assignments and metadata are required')
    names = {name.casefold() for name in options.split(',') if name}
    if 'default' not in names or len(names) < 2:
        raise ValueError('Native flag metadata is incomplete')
    if value == '':
        return  # Native empty FLAGSET text retains the current flags.
    selected = set()
    for token in value.split(','):
        if token.casefold() == 'default':
            name = 'default'
        else:
            match = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_]*)=(on|off|default)',
                                 token, flags=re.I)
            if not match:
                raise ValueError('Choose a native flag and on/off/default')
            name = match.group(1).casefold()
            if name == 'default':
                raise ValueError('Default reset has no assignment value')
        if name not in names or name in selected:
            raise ValueError('Native flag is unavailable or repeated')
        selected.add(name)


def flagset_bitmask(value, options):
    """Parse exact decimal text against the native FLAGSET option count."""
    if not isinstance(options, str):
        raise ValueError('Native flag metadata is required')
    names = options.split(',')
    if (not 2 <= len(names) <= 64 or names[-1].casefold() != 'default'
            or any(not name for name in names)
            or len({name.casefold() for name in names}) != len(names)):
        raise ValueError('Native flag metadata is incomplete or unsupported')
    if not isinstance(value, str) or not re.fullmatch(r'0|[1-9][0-9]{0,19}', value):
        raise ValueError('Use unsigned decimal text for the native bitmask')
    parsed = int(value, 10)
    if parsed > (1 << len(names)) - 1:
        raise ValueError('The bitmask exceeds the native FLAGSET bound')
    return parsed


def flagset_assignments(rows, reset_defaults, options):
    """Translate structured flag choices to the native textual grammar."""
    if not isinstance(rows, list) or type(reset_defaults) is not bool:
        raise ValueError('Flag rows and an explicit reset choice are required')
    tokens = ['default'] if reset_defaults else []
    for row in rows:
        if not isinstance(row, dict) or set(row) - {'flag', 'state', '_id'}:
            raise ValueError('Each flag row requires a flag and state')
        name, state = row.get('flag'), row.get('state')
        if (not isinstance(name, str) or not re.fullmatch(
                r'[A-Za-z_][A-Za-z0-9_]*', name)
                or name.casefold() == 'default'
                or not isinstance(state, str)
                or state not in {'on', 'off', 'default'}):
            raise ValueError('Choose a native flag and on/off/default state')
        tokens.append(name + '=' + state)
    value = ','.join(tokens)
    validate_flagset(value, options)
    return value
