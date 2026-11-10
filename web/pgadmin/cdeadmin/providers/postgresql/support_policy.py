"""PostgreSQL version admission policy.

Owner decision, 2026-11-08 (AGENTS.md, "PostgreSQL onto the provider tree"):
ScratchRobin supports the PostgreSQL versions the PostgreSQL project
currently supports, and no version the project has stopped supporting.
Before this module, the provider and the endpoint service admitted only
the exact profile version 18.3.

The table below follows the project's versioning policy: a major version
receives minor releases for five years after its initial release, and the
final minor release is in the November after that. Dates come from
https://www.postgresql.org/support/versioning/ as read on 2026-11-10;
``POLICY_READ_ON`` records that date so a stale table is visible. The test
``test_postgresql_support_policy.py`` checks the table against the five-year
rule, so an entry cannot drift from the policy unnoticed.

Admission widens only what versions may connect. The dialect, metrics and
template contracts stay pinned to the tested profile version; whether a
feature exists on an admitted version is decided per feature by its own
version gate, never assumed from admission.
"""
from datetime import date

POLICY_READ_ON = date(2026, 11, 10)

# major -> (initial release, final minor release). Five years of support
# per the project policy; the final release lands in November.
SUPPORTED_MAJORS = {
    13: (date(2020, 9, 24), date(2025, 11, 13)),
    14: (date(2021, 9, 30), date(2026, 11, 12)),
    15: (date(2022, 10, 13), date(2027, 11, 11)),
    16: (date(2023, 9, 14), date(2028, 11, 9)),
    17: (date(2024, 9, 26), date(2029, 11, 8)),
    18: (date(2025, 9, 25), date(2030, 11, 14)),
}


def runtime_major_minor(native_version):
    """Return ``(major, minor)`` from libpq's integer or a text version.

    libpq reports ``server_version_num`` as ``major * 10000 + minor``
    (``180003`` is 18.3). Text forms such as ``'18.3'`` or ``'16.15'`` are
    accepted as well. Returns ``None`` when the value cannot be read.
    """
    if isinstance(native_version, bool):
        return None
    if isinstance(native_version, int):
        if native_version >= 100000:
            return native_version // 10000, native_version % 10000
        return None
    text = str(native_version).strip()
    parts = text.split('.')
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 and parts[1] else 0
    except (ValueError, IndexError):
        return None
    return major, minor


def public_version(native_version):
    """Render a version as PostgreSQL's public ``major.minor`` notation."""
    parsed = runtime_major_minor(native_version)
    if parsed is None:
        return str(native_version)
    return f'{parsed[0]}.{parsed[1]}'


def support_state(native_version, today=None):
    """Classify a runtime version against the project's support window.

    Returns one of ``'supported'``, ``'end_of_life'`` (the major's final
    release date has passed), ``'unknown_major'`` (a major absent from the
    table: older than the table, or newer than the policy snapshot) or
    ``'unreadable'``.
    """
    today = today or date.today()
    parsed = runtime_major_minor(native_version)
    if parsed is None:
        return 'unreadable'
    window = SUPPORTED_MAJORS.get(parsed[0])
    if window is None:
        return 'unknown_major'
    return 'supported' if today <= window[1] else 'end_of_life'


def admission_error(native_version, today=None):
    """Return the refusal text for a version ScratchRobin does not admit.

    ``None`` means the version is admitted.
    """
    state = support_state(native_version, today)
    if state == 'supported':
        return None
    shown = public_version(native_version)
    if state == 'end_of_life':
        parsed = runtime_major_minor(native_version)
        final = SUPPORTED_MAJORS[parsed[0]][1].isoformat()
        return (f'PostgreSQL {shown} is no longer supported by the PostgreSQL '
                f'project (final release {final}); ScratchRobin supports the '
                'versions the project supports')
    if state == 'unknown_major':
        return (f'PostgreSQL {shown} is outside the support table '
                f'ScratchRobin carries (read {POLICY_READ_ON.isoformat()}); '
                'update support_policy.py from the PostgreSQL versioning '
                'policy')
    return f'PostgreSQL runtime version {native_version!r} could not be read'
