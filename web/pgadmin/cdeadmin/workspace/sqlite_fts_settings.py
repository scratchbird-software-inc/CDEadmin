"""Native normalized FTS settings and configuration-only DDN transitions."""
from copy import deepcopy
import sqlite3

from .sqlite_schema_plan import _definition, _source
from .firebird_schema_plan import digest
from ..providers.sqlite.fts_configuration import capture, identity, quote, statements, validate


def generate(baseline, resource_id, settings):
    row = baseline['rows'].get(resource_id)
    if row is None or row['kind'] != 'fts-table':
        raise ValueError('Select an observed native FTS table')
    _source(row)
    old = row['native'].get('fts_configuration')
    validate(old)
    if not isinstance(settings, dict) or not settings or len(settings) > 9:
        raise ValueError('Select one or more native FTS settings')
    commands = dict(old['commands'])
    commands.update(settings)
    configured = {**old, 'commands': [[key, value] for key, value in sorted(commands.items())]}
    name = '__scratchrobin_fts_settings_probe'
    proposed = statements(name, configured)
    probe = sqlite3.connect(':memory:')
    try:
        probe.execute('CREATE VIRTUAL TABLE ' + quote(name) + ' USING ' + quote(old['module']) + '(body)')
        for source in proposed:
            probe.execute(source)
        normalized = capture(probe, 'main', name, old['module'])
        # The registered index format is an observed engine-owned fact. The
        # empty normalization probe cannot infer its data-dependent version.
        normalized['native_format_version'] = old.get('native_format_version')
        validate(normalized)
    except sqlite3.Error as error:
        raise ValueError('Native FTS setting refused (' + str(getattr(error, 'sqlite_errorname', 'SQLITE_ERROR')) + ')') from None
    finally:
        probe.close()
    desired = deepcopy(baseline)
    desired['rows'][resource_id]['native']['fts_configuration'] = normalized
    return desired


def plan(old, wanted):
    if old['kind'] != 'fts-table' or wanted['kind'] != 'fts-table' or old['resource_id'] != wanted['resource_id']:
        raise ValueError('FTS settings require the exact retained native table')
    _source(old); _source(wanted)
    original, desired = _definition(old), _definition(wanted)
    if {key: value for key, value in original.items() if key != 'fts_configuration'} != {
            key: value for key, value in desired.items() if key != 'fts_configuration'}:
        raise ValueError('FTS configuration change cannot also rewrite the table definition')
    before, after = old['native']['fts_configuration'], wanted['native']['fts_configuration']
    validate(before); validate(after)
    if before['module'] != after['module'] or not set(dict(before['commands'])) <= set(dict(after['commands'])):
        raise ValueError('Preserve observed FTS settings; reset using explicit native values')
    if identity(before) == identity(after):
        raise ValueError('Native FTS configuration has no changes')
    stages = statements(wanted['name'], after)
    return {'operation': 'fts-configure', 'resource_id': old['resource_id'], 'kind': 'fts-table',
            'name': old['name'], 'module': after['module'], 'stages': stages,
            'source': '\n'.join(source + ';' for source in stages),
            'baseline_sha256': digest(original), 'desired_sha256': digest(desired)}
