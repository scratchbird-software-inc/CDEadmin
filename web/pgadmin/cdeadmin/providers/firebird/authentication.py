"""Per-attachment AuthClient selection; negotiation belongs to Firebird.

Linux qualified with native database and Services API attachments. Windows and
macOS teams must repeat ordered negotiation with their native plugin loaders;
Windows trusted Win_Sspi authentication has a separate qualification gate.
"""

import sys

from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def windows_authentication_host():
    """The native client runs on the app host, not the browser's computer.

    Windows team: verify real SSPI/domain and local-account login, service
    identity, database creation/Services API, failed trust and browser flows.
    Platform-mocked argument tests are not evidence of Windows authentication.
    macOS team: repeat the unsupported-platform rejection with its client.
    Linux cannot implement or qualify Windows SSPI by generating mapping DDL.
    """
    return sys.platform == 'win32'


def validate_authentication_plugins(route):
    """Preserve native spelling/order, including third-party plugin names.

    None/absence uses native configuration. Explicit empty input must not
    silently fall back to a broader native authentication policy. Firebird's
    ParsedList accepts spaces, tabs, commas and semicolons as separators.
    Availability and server compatibility can only be decided by the native
    client/server handshake, not by a hard-coded application allowlist.
    """
    trusted = route.get('trusted_auth')
    if trusted is not None and type(trusted) is not bool:
        raise RelationalClientError(
            'Firebird trusted authentication selection must be a boolean')
    if trusted and not windows_authentication_host():
        raise RelationalClientError(
            'Firebird Windows trusted authentication (Win_Sspi) requires '
            'the CDEadmin application host to run Windows. It is unavailable '
            'on this host; no password fallback was attempted.')
    value = route.get('auth_plugin_list')
    if value is None:
        return
    if (not isinstance(value, str) or not value.strip(' \t,;') or
            any(ord(char) < 32 and char != '\t' for char in value) or
            '\x7f' in value):
        raise RelationalClientError(
            'Firebird authentication plugin list must contain plugin names '
            'separated by spaces, tabs, commas or semicolons')
