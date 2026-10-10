"""Read-only native database configuration observations."""

import json
from importlib import resources

from pgadmin.cdeadmin.sdk.relational import RelationalClientError


KEYS = json.loads(resources.files(__package__).joinpath(
    'configuration_keys_5_0_4.json').read_text(encoding='utf-8'))['keys']

SQL = (
    'SELECT RDB$CONFIG_NAME, RDB$CONFIG_ID, RDB$CONFIG_VALUE, '
    'RDB$CONFIG_DEFAULT, RDB$CONFIG_IS_SET, RDB$CONFIG_SOURCE '
    'FROM RDB$CONFIG ORDER BY RDB$CONFIG_NAME'
)


def metadata(row):
    if (not isinstance(row, (tuple, list)) or len(row) != 6 or
            not isinstance(row[0], str) or not row[0] or
            type(row[1]) is not int or type(row[4]) is not bool or
            any(value is not None and not isinstance(value, str)
                for value in (row[2], row[3], row[5]))):
        raise RelationalClientError(
            'Firebird configuration observation has invalid native fields')
    name, identifier, value, default, is_set, source = row
    declaration = KEYS.get(name, {
        'native_type': 'unknown', 'configuration_scope': 'unknown'})
    return {
        'config_id': identifier, 'value': value, 'default_value': default,
        'explicitly_set': is_set, 'value_source': source,
        **declaration,
        'observation_source': 'RDB$CONFIG database configuration snapshot',
        'visibility': 'current attachment native privileges',
        'sql_mutable': False,
        'configuration_note': (
            'Read-only engine configuration observation. Client/session '
            'overrides and installed plugin binaries are not inferred. '
            'File-managed changes require separate deployment procedures; '
            'refresh does not apply, reload or restart configuration.'),
    }
