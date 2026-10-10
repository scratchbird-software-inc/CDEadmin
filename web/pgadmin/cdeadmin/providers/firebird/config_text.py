"""Audited Firebird 5 network-client configuration, not firebird.conf editing.

Native authority: common/config/config.{h,cpp}, config_file.cpp and remote.
Windows/macOS teams repeat native merge/plugin/loader behavior. Includes and
macros are deliberately forbidden: a saved endpoint must not read host files.
"""

import re

from pgadmin.cdeadmin.sdk.relational import RelationalClientError


CLIENT_KEYS = {
    'wirecrypt': 'policy', 'wirecryptplugin': 'plugins',
    'authclient': 'plugins', 'wirecompression': 'boolean',
    'tcpnonagle': 'boolean', 'connectiontimeout': 'integer',
    'dummypacketinterval': 'integer', 'clientbatchbuffer': 'integer',
}


def validate_config_selection(route):
    keys = validate_config_text(route.get('wire_config'))
    # ConnectionTimeout is intentionally different: native explicit DPB/SPB
    # timeout overrides configuration. This precedence is tested natively.
    for key, field in (('WireCrypt', 'wire_crypt'),
                       ('WireCryptPlugin', 'wire_crypt_plugins'),
                       ('WireCompression', 'wire_compression'),
                       ('DummyPacketInterval', 'dummy_packet_interval'),
                       ('AuthClient', 'auth_plugin_list')):
        if route.get(field) is not None and key.lower() in keys:
            raise RelationalClientError(
                'Firebird wire configuration duplicates the explicit ' +
                key + ' field; use one configuration source')
    return keys


def validate_config_text(text):
    """Return assigned keys; preserve valid source text exactly for native use.

Unknown/engine/global/endpoint-routing keys are not silently accepted. Native
case-insensitive names, comments, quoted values and K/M/G integer suffixes are
supported, but malformed native values that coerce to zero/false are rejected.
"""
    if text is None:
        return set()
    if (not isinstance(text, str) or
            any(ord(c) < 32 and c not in '\t\r\n' for c in text) or
            '\x7f' in text):
        raise RelationalClientError('Firebird wire configuration is invalid')
    try:
        if len(text.encode('utf-8')) > 16384:
            raise RelationalClientError(
                'Firebird wire configuration exceeds 16 KiB')
    except UnicodeError:
        raise RelationalClientError(
            'Firebird wire configuration is not valid UTF-8') from None
    keys = set()
    for number, line in enumerate(text.split('\n'), 1):
        line = line.strip(' \t\r')
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(
            r'([A-Za-z][A-Za-z0-9]*)\s*=\s*(?:"([^"\r\n]*)"|'
            r'([^"#\r\n]*?))\s*(?:#.*)?', line)
        if not match:
            raise RelationalClientError(
                f'Firebird wire configuration line {number}: '
                'use one flat key=value assignment; no includes or blocks')
        key = match[1].lower()
        value = (match[2] if match[2] is not None else match[3]).strip()
        if key not in CLIENT_KEYS:
            raise RelationalClientError(
                f'Firebird wire configuration line {number}: setting is not '
                'an admitted client option; use the dedicated connection '
                'or server administration controls')
        if key in keys:
            raise RelationalClientError(
                f'Firebird wire configuration line {number}: duplicate key')
        keys.add(key)
        kind = CLIENT_KEYS[key]
        valid = bool(value) and not any(c in value for c in '$(){}=#')
        if kind == 'policy':
            valid &= value.lower() in {'disabled', 'enabled', 'required'}
        elif kind == 'boolean':
            valid &= value.lower() in {'true', 'false', 'yes', 'no',
                                       'y', 'n', '0', '1'}
        elif kind == 'integer':
            integer = re.fullmatch(r'([0-9]{1,10})([kKmMgG]?)', value)
            valid &= integer is not None
            if integer:
                multiplier = {'': 1, 'k': 1024, 'm': 1024**2, 'g': 1024**3}
                count = int(integer[1]) * multiplier[integer[2].lower()]
                valid &= 0 <= count <= 2147483647
        elif kind == 'plugins':
            valid &= bool(value.strip(' \t,;'))
        if not valid:
            raise RelationalClientError(
                f'Firebird wire configuration line {number}: invalid '
                'client setting value (macros are not permitted)')
    return keys
