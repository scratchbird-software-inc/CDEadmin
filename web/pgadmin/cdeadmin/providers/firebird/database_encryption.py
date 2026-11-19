"""Managed Firebird 5.0.4 database-at-rest encryption, decryption and key-provider status.

Keeps database page encryption (ALTER DATABASE ENCRYPT/DECRYPT + DbCrypt/KeyHolder
plugins) distinct from WireCrypt transport encryption and gbak backup-stream
encryption. Never implements cryptography in application code or claims that
core Firebird hook presence implies an installed production crypt provider.
"""
from collections.abc import Mapping
import time

from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from .character_metadata import identifier, text
from .encryption_info import read_encryption_text

OPERATIONS = frozenset({'encrypt_database', 'decrypt_database'})

CRYPT_STATES = {
    0: 'not_encrypted',
    1: 'encrypted',
    2: 'decrypting_in_progress',
    3: 'encrypting_in_progress',
}

WARNINGS = {
    'encrypt_database': (
        'Database-at-rest encryption rewrites database pages asynchronously using '
        'an external native Firebird DbCrypt plugin and KeyHolder provider. It is '
        'distinct from WireCrypt network encryption and gbak backup encryption. '
        'Losing the encryption key or KeyHolder configuration permanently prevents '
        'opening the database. ScratchRobin never stores raw cryptographic keys or '
        'emulates missing crypt plugins.'
    ),
    'decrypt_database': (
        'Decrypting rewrites database pages to plaintext asynchronously in the '
        'background. Keep the active KeyHolder and DbCrypt plugins installed and '
        'configured until MON$CRYPT_STATE reaches 0 (not encrypted).'
    ),
}


def _target_database(database):
    value = text(database, 'Database path or alias')
    if not value:
        raise RelationalClientError('A database path or alias is required')
    return value


def compile_operation(operation, draft, database):
    if not isinstance(operation, str) or operation not in OPERATIONS or not isinstance(draft, Mapping):
        raise RelationalClientError('Unknown Firebird database encryption task')
    target_db = _target_database(database)
    if draft.get('confirmation') != target_db:
        raise RelationalClientError('Confirm the exact database path or alias')

    if operation == 'encrypt_database':
        allowed = {
            'confirmation', 'crypt_plugin', 'key_name',
            'confirm_key_recovery_responsibility',
        }
        if set(draft) - allowed:
            raise RelationalClientError('Unknown Firebird encrypt_database form fields')
        if draft.get('confirm_key_recovery_responsibility') is not True:
            raise RelationalClientError(
                'Confirm key recovery responsibility before encrypting the database'
            )
        plugin_sql = identifier(draft.get('crypt_plugin'))
        raw_key = draft.get('key_name')
        key_clause = ''
        if raw_key not in (None, ''):
            key_clause = ' KEY ' + identifier(raw_key)
        return [f'ALTER DATABASE ENCRYPT WITH {plugin_sql}{key_clause}']

    allowed = {'confirmation', 'confirm_plaintext_storage'}
    if set(draft) - allowed:
        raise RelationalClientError('Unknown Firebird decrypt_database form fields')
    if draft.get('confirm_plaintext_storage') is not True:
        raise RelationalClientError(
            'Confirm plaintext disk storage before decrypting the database'
        )
    return ['ALTER DATABASE DECRYPT']


def form(operation, field):
    if not isinstance(operation, str) or operation not in OPERATIONS:
        raise RelationalClientError('Unknown Firebird database encryption form')
    titles = {
        'encrypt_database': 'Encrypt database at rest',
        'decrypt_database': 'Decrypt database to plaintext',
    }
    fields = [
        field(
            'confirmation',
            'Confirm database path or alias',
            'text',
            True,
            'The exact selected database target. ' + WARNINGS[operation],
        ),
    ]
    if operation == 'encrypt_database':
        fields.extend([
            field(
                'crypt_plugin',
                'Database crypt plugin',
                'text',
                True,
                'Installed native DbCrypt plugin name registered in plugins.conf.',
            ),
            field(
                'key_name',
                'Key name (optional)',
                'text',
                False,
                'Key identifier supplied by the configured KeyHolderPlugin. Leave empty only when the plugin selects a default key.',
                '',
            ),
            field(
                'confirm_key_recovery_responsibility',
                'I confirm key backup and external KeyHolder availability',
                'boolean',
                True,
                WARNINGS['encrypt_database'],
                False,
            ),
        ])
    else:
        fields.append(
            field(
                'confirm_plaintext_storage',
                'I confirm database pages will be stored unencrypted on disk',
                'boolean',
                True,
                WARNINGS['decrypt_database'],
                False,
            )
        )
    return {
        'form_id': 'firebird.database.' + operation,
        'title': titles[operation],
        'fields': fields,
    }


def descriptor():
    return {
        'schema': 'scratchrobin.firebird.database-encryption-api@1',
        'engine_version': '5.0.4',
        'actions': ['describe', 'inspect', 'wait_settle'],
        'visual_admin_operations': sorted(OPERATIONS),
        'application_implements_cryptography': False,
        'distinct_from_wire_crypt_and_gbak_crypt': True,
        'external_plugin_dependency': (
            'Database-at-rest encryption requires external native Firebird '
            'DbCrypt and KeyHolder plugins; core Firebird 5.0.4 ships plugin '
            'hooks without a built-in production database-crypt plugin.'
        ),
    }


def inspect_encryption_status(client, route, host_scope=None):
    import firebird.driver as native

    conn = client._connect({'route': route})
    try:
        cur = conn.cursor()
        try:
            cur.execute('SELECT MON$CRYPT_STATE, MON$CRYPT_PAGE, MON$PAGES FROM MON$DATABASE')
            crypt_state_num, crypt_page, total_pages = cur.fetchone()
            cur.execute(
                "SELECT TRIM(TRAILING FROM RDB$CONFIG_NAME), RDB$CONFIG_VALUE, RDB$CONFIG_IS_SET "
                "FROM RDB$CONFIG WHERE TRIM(TRAILING FROM RDB$CONFIG_NAME) IN "
                "('KeyHolderPlugin', 'WireCrypt', 'AllowEncryptedSecurityDatabase')"
            )
            cfg = {
                r[0]: {'value': r[1], 'is_set': bool(r[2])}
                for r in cur.fetchall()
            }
        finally:
            cur.close()
        conn.rollback()

        info_flags = int(conn.info.get_info(native.DbInfoCode.CRYPT_STATE))
        try:
            plugin_name = read_encryption_text(conn.info, 'encryption_plugin')
        except RelationalClientError:
            plugin_name = ''
        try:
            key_name = read_encryption_text(conn.info, 'encryption_key_name')
        except RelationalClientError:
            key_name = ''
    finally:
        client._forget_and_close(conn)

    state_code = int(crypt_state_num or 0)
    host_plugins = None
    if host_scope is not None:
        from .plugin_deployment import inspect_plugin_environment
        inv = inspect_plugin_environment(host_scope)
        host_plugins = [
            {
                'module_name': p['module_name'],
                'classification': p['classification'],
                'production_safe': p['production_safe'],
            }
            for p in inv.get('plugins', ())
            if p.get('valid_elf_dso')
        ]

    return {
        'schema': 'scratchrobin.firebird.database-encryption-status@1',
        'crypt_state_code': state_code,
        'crypt_state': CRYPT_STATES.get(state_code, 'unknown'),
        'in_transition': state_code in (2, 3),
        'crypt_page': int(crypt_page or 0),
        'total_pages': int(total_pages or 0),
        'info_crypt_flags': info_flags,
        'encryption_plugin': plugin_name,
        'encryption_key_name': key_name,
        'sample_non_secure_plugin_active': plugin_name in {'fbSampleDbCrypt', '暗号'},
        'key_holder_config': cfg.get('KeyHolderPlugin'),
        'wire_crypt_config': cfg.get('WireCrypt'),
        'allow_encrypted_security_db': cfg.get('AllowEncryptedSecurityDatabase'),
        'host_installed_plugins': host_plugins,
        'application_implements_cryptography': False,
    }


def wait_for_encryption_settle(client, route, expected_state_code, timeout_seconds=15, host_scope=None):
    if expected_state_code not in (0, 1):
        raise ValueError('expected_state_code must be 0 (not_encrypted) or 1 (encrypted)')
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 60:
        raise ValueError('timeout_seconds must be an integer between 1 and 60')
    # Hold one attachment open across the settle window so Classic/SuperClassic
    # per-attachment background crypt workers run continuously to completion.
    anchor = client._connect({'route': route})
    try:
        deadline = time.monotonic() + timeout_seconds
        last = None
        while time.monotonic() < deadline:
            cur = anchor.cursor()
            try:
                cur.execute('SELECT MON$CRYPT_STATE FROM MON$DATABASE')
                observed = int(cur.fetchone()[0] or 0)
            finally:
                cur.close()
                anchor.rollback()
            if observed == expected_state_code:
                last = inspect_encryption_status(client, route, host_scope=host_scope)
                if last['crypt_state_code'] == expected_state_code and not last['in_transition']:
                    return {**last, 'settled': True}
            time.sleep(0.1)
        last = inspect_encryption_status(client, route, host_scope=host_scope)
        return {**last, 'settled': last['crypt_state_code'] == expected_state_code and not last['in_transition']}
    finally:
        client._forget_and_close(anchor)
