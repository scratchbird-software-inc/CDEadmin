"""PostgreSQL pgAgent job editor: create, alter, drop and run now (M6).

The job carries its steps and schedules, as the inherited job dialog did,
and compiles to the same statements the inherited templates render: one
``DO`` block for create (the job id flows into its steps and schedules),
plain ``UPDATE``/``INSERT``/``DELETE`` statements for alter, and one
``DELETE`` for drop (pgAgent cascades to steps, schedules and logs). The
grids are the desired full set: a row with an id updates that step or
schedule, a row without one inserts, and an existing id missing from the
grid deletes.

Owner direction: text as data, never as an identifier. Every value is a
literal; no identifier is taken from the draft. A step connection string
may not carry a password: pgAgent reads ``.pgpass`` and services.
"""
from __future__ import annotations

import re

from .native_admin import (
    PostgreSQLNativeAdminError, _flag, _literal, _name,
)

SCHEDULE_SIZES = (('jscminutes', 60), ('jschours', 24), ('jscweekdays', 7),
                  ('jscmonthdays', 32), ('jscmonths', 12))
ON_ERROR = {'f': 'Fail', 's': 'Succeed', 'i': 'Ignore'}
_TIMESTAMP = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}[ T0-9:.+\-Za-z]{0,40}')
_PASSWORD = re.compile(r'password\s*=', re.IGNORECASE)


def _refuse(message):
    raise PostgreSQLNativeAdminError(message)


def _text(value, label):
    """A text literal that may be empty (the shared literal refuses '')."""
    return "''" if value == '' else _literal(value, label)


def facts(native):
    """Current values from the server-scope row (the inherited properties
    template) with the steps and schedules the provider captured."""
    meta = native.get('catalog_metadata') or {}
    return {
        'jobid': meta.get('jobid'),
        'jobname': native.get('name') or meta.get('jobname'),
        'jobenabled': bool(meta.get('jobenabled', True)),
        'jobdesc': meta.get('jobdesc') or '',
        'jobhostagent': meta.get('jobhostagent') or '',
        'jobjclid': meta.get('jobjclid'),
        'jobclass': meta.get('jobclass'),
        'has_connstr': bool(meta.get('has_connstr', True)),
        'jsteps': [_step_row(row) for row in meta.get('steps') or []],
        'jschedules': [_schedule_row(row)
                       for row in meta.get('schedules') or []],
    }


def _step_row(row):
    return {
        'jstid': row.get('jstid'), 'jstname': row.get('jstname'),
        'jstenabled': bool(row.get('jstenabled', True)),
        'jstkind': 'sql' if row.get('jstkind') in (True, 's') else 'batch',
        'jstconntype': 'local' if row.get('jstconntype', True) else 'remote',
        'jstdbname': row.get('jstdbname') or '',
        'jstconnstr': row.get('jstconnstr') or '',
        'jstonerror': row.get('jstonerror') or 'f',
        'jstcode': row.get('jstcode') or '',
        'jstdesc': row.get('jstdesc') or '',
    }


def _flags_to_list(value):
    if isinstance(value, str):
        value = [part.strip() in ('t', 'true') for part in
                 value.strip('{}').split(',') if part.strip()]
    if not isinstance(value, list):
        return ''
    return ', '.join(str(index) for index, on in enumerate(value) if on)


def _schedule_row(row):
    out = {
        'jscid': row.get('jscid'), 'jscname': row.get('jscname'),
        'jscenabled': bool(row.get('jscenabled', True)),
        'jscstart': str(row.get('jscstart') or ''),
        'jscend': str(row.get('jscend') or ''),
        'jscdesc': row.get('jscdesc') or '',
    }
    for key, _size in SCHEDULE_SIZES:
        out[key] = _flags_to_list(row.get(key))
    return out


# -- values -----------------------------------------------------------------

def _int(value, label):
    if isinstance(value, bool) or value in (None, ''):
        _refuse(f'{label} must be an integer')
    if isinstance(value, str) and value.strip().lstrip('-').isdigit():
        value = int(value.strip())
    if type(value) is not int:
        _refuse(f'{label} must be an integer')
    return value


def _optional_text(draft, key, default=''):
    value = draft.get(key)
    if value is None:
        return default
    if not isinstance(value, str):
        _refuse(f'{key} must be text')
    return value


def _timestamp(value, label, required):
    if value in (None, ''):
        if required:
            _refuse(f'{label} is required')
        return None
    if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value.strip()):
        _refuse(f'{label} must be a timestamp such as 2026-11-11 02:30:00+00')
    return value.strip()


def _flags(value, key, size):
    """A schedule's minutes/hours/... as ``'{t,f,...}'::boolean[]``, from a
    comma list of indexes (``0, 30``), a list of ints, or a list of bools
    of the exact size. Empty means none selected, as the inherited form."""
    if value in (None, ''):
        chosen = set()
    elif isinstance(value, str):
        parts = [part.strip() for part in value.split(',') if part.strip()]
        if any(not part.isdigit() for part in parts):
            _refuse(f'{key} must be a comma list of positions')
        chosen = {int(part) for part in parts}
    elif isinstance(value, list) and len(value) == size and all(
            type(item) is bool for item in value):
        chosen = {index for index, on in enumerate(value) if on}
    elif isinstance(value, list) and all(
            type(item) is int and not isinstance(item, bool)
            for item in value):
        chosen = set(value)
    else:
        _refuse(f'{key} must be positions or {size} booleans')
    if any(not 0 <= index < size for index in chosen):
        _refuse(f'{key} positions run from 0 to {size - 1}')
    flags = ','.join('t' if index in chosen else 'f' for index in range(size))
    return "'{" + flags + "}'::boolean[]"


def _rows(draft, key):
    value = draft.get(key)
    if value in (None, ''):
        return []
    if not isinstance(value, list) or any(
            not isinstance(item, dict) for item in value):
        _refuse(f'{key} must be a list of rows')
    return value


def _bool(row, key, default=True):
    value = row.get(key, default)
    if type(value) is not bool:
        _refuse(f'{key} must be boolean')
    return value


# -- statements -------------------------------------------------------------

def _job_values(draft, create):
    values = {}
    if create or 'jobname' in draft:
        values['jobname'] = _literal(_name(draft.get('jobname'), 'jobname'),
                                     'jobname') + '::text'
    if create or 'jobenabled' in draft:
        values['jobenabled'] = ('true' if _flag(draft, 'jobenabled')
                                else 'false')
    if create or 'jobjclid' in draft:
        values['jobjclid'] = str(_int(draft.get('jobjclid', 1) if create
                                      else draft.get('jobjclid'),
                                      'jobjclid')) + '::integer'
    if create or 'jobhostagent' in draft:
        values['jobhostagent'] = _text(
            _optional_text(draft, 'jobhostagent'), 'jobhostagent') + '::text'
    if create or 'jobdesc' in draft:
        values['jobdesc'] = _text(_optional_text(draft, 'jobdesc'),
                                  'jobdesc') + '::text'
    return values


def _step_values(row, has_connstr):
    name = _literal(_name(row.get('jstname'), 'jstname'), 'jstname')
    kind = row.get('jstkind', 'sql')
    if kind not in ('sql', 'batch'):
        _refuse('jstkind must be sql or batch')
    conntype = row.get('jstconntype', 'local')
    if conntype not in ('local', 'remote'):
        _refuse('jstconntype must be local or remote')
    onerror = row.get('jstonerror', 'f')
    if onerror not in ON_ERROR:
        _refuse('jstonerror must be f (fail), s (succeed) or i (ignore)')
    dbname = _optional_text(row, 'jstdbname')
    connstr = _optional_text(row, 'jstconnstr')
    if kind == 'batch':
        dbname, connstr = '', ''
    elif conntype == 'remote':
        if not has_connstr:
            _refuse('this pgAgent has no connection-string column; '
                    'remote steps are unavailable')
        if not connstr:
            _refuse('a remote step needs a connection string')
        if _PASSWORD.search(connstr):
            _refuse('a step connection string may not carry a password; '
                    'use .pgpass or a service')
        dbname = ''
    else:
        if not dbname:
            _refuse('a local SQL step needs a database name')
        connstr = ''
    values = {
        'jstname': name + '::text',
        'jstenabled': 'true' if _bool(row, 'jstenabled') else 'false',
        'jstkind': ("'s'" if kind == 'sql' else "'b'") + '::character(1)',
        'jstdbname': _text(dbname, 'jstdbname') + '::name',
        'jstonerror': _literal(onerror, 'jstonerror') + '::character(1)',
        'jstcode': _text(_optional_text(row, 'jstcode'), 'jstcode')
        + '::text',
        'jstdesc': _text(_optional_text(row, 'jstdesc'), 'jstdesc')
        + '::text',
    }
    if has_connstr:
        values['jstconnstr'] = _text(connstr, 'jstconnstr') + '::text'
    return values


def _schedule_values(row):
    values = {
        'jscname': _literal(_name(row.get('jscname'), 'jscname'), 'jscname')
        + '::text',
        'jscdesc': _text(_optional_text(row, 'jscdesc'), 'jscdesc')
        + '::text',
        'jscenabled': 'true' if _bool(row, 'jscenabled') else 'false',
        'jscstart': _literal(_timestamp(row.get('jscstart'), 'jscstart', True),
                             'jscstart') + '::timestamp with time zone',
    }
    end = _timestamp(row.get('jscend'), 'jscend', False)
    values['jscend'] = ('NULL::timestamp with time zone' if end is None else
                        _literal(end, 'jscend') + '::timestamp with time zone')
    for key, size in SCHEDULE_SIZES:
        values[key] = _flags(row.get(key), key, size)
    return values


def _insert(table, values, extra):
    columns = list(extra) + list(values)
    rendered = list(extra.values()) + list(values.values())
    return (f'INSERT INTO pgagent.{table} ({", ".join(columns)}) VALUES ('
            + ', '.join(rendered) + ')')


def _create(draft, has_connstr):
    job = _job_values(draft, create=True)
    steps = [_step_values(row, has_connstr) for row in _rows(draft, 'jsteps')]
    schedules = [_schedule_values(row) for row in _rows(draft, 'jschedules')]
    lines = ['DO $$', 'DECLARE', '    jid integer;', 'BEGIN',
             _insert('pga_job', job, {}) + ' RETURNING jobid INTO jid;']
    for values in steps:
        lines.append(_insert('pga_jobstep', values, {'jstjobid': 'jid'}) + ';')
    for values in schedules:
        lines.append(
            _insert('pga_schedule', values, {'jscjobid': 'jid'}) + ';')
    lines += ['END', '$$']
    return '\n'.join(lines)


def _alter(current, draft):
    jobid = _int(current['jobid'], 'jobid')
    has_connstr = current['has_connstr']
    statements = []
    job = _job_values(draft, create=False)
    if job:
        statements.append('UPDATE pgagent.pga_job SET ' + ', '.join(
            f'{key} = {value}' for key, value in job.items())
            + f' WHERE jobid = {jobid}')
    for key, table, id_column, job_column, render, existing in (
            ('jsteps', 'pga_jobstep', 'jstid', 'jstjobid',
             lambda row: _step_values(row, has_connstr), current['jsteps']),
            ('jschedules', 'pga_schedule', 'jscid', 'jscjobid',
             _schedule_values, current['jschedules'])):
        if key not in draft:
            continue
        known = {row[id_column] for row in existing if row.get(id_column)
                 is not None}
        kept = set()
        for row in _rows(draft, key):
            values = render(row)
            row_id = row.get(id_column)
            if row_id in (None, ''):
                statements.append(
                    _insert(table, values, {job_column: str(jobid)}))
                continue
            row_id = _int(row_id, id_column)
            if row_id not in known:
                _refuse(f'{id_column} {row_id} does not belong to this job')
            kept.add(row_id)
            statements.append(
                f'UPDATE pgagent.{table} SET ' + ', '.join(
                    f'{column} = {value}' for column, value in values.items())
                + f' WHERE {id_column} = {row_id} AND {job_column} = {jobid}')
        for row_id in sorted(known - kept):
            statements.append(
                f'DELETE FROM pgagent.{table} WHERE {id_column} = '
                f'{row_id} AND {job_column} = {jobid}')
    if not statements:
        _refuse('nothing to change')
    return ';\n'.join(statements)


def _drop(current, draft):
    if _name(draft.get('confirmation'), 'confirmation') != current['jobname']:
        _refuse('drop confirmation does not match object name')
    return (f'DELETE FROM pgagent.pga_job WHERE jobid = '
            f'{_int(current["jobid"], "jobid")}')


def run_now(native):
    """The inherited Run now: the agent picks the job up at its next poll."""
    current = facts(native)
    return {'statement': 'UPDATE pgagent.pga_job SET jobnextrun = now() '
                         f'WHERE jobid = {_int(current["jobid"], "jobid")}',
            'read_only': False, 'autocommit': False}


def compile_operation(operation, native, draft):
    """One exact native text for the job lifecycle."""
    current = facts(native)
    if operation == 'create':
        statement = _create(draft, current['has_connstr'])
    elif operation == 'alter':
        statement = _alter(current, draft)
    elif operation == 'drop':
        statement = _drop(current, draft)
    else:
        _refuse('pgAgent job inspection stays with the provider tree')
    return {'statement': statement, 'read_only': False}


# -- form -------------------------------------------------------------------

def form(operation, field):
    """Dialog fields; ids follow the inherited job dialog."""
    def column(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    if operation == 'drop':
        return {'form_id': 'postgresql-pgagent-job-drop',
                'form_key': 'native:postgresql:server:pgagent-job',
                'title': 'Drop pgAgent job', 'fields': [
                    field('confirmation', 'Type the job name to confirm',
                          required=True)],
                'notes': 'Removes the job with its steps, schedules and logs.'}
    alter = operation == 'alter'
    initial = (lambda key: {'initial_value_path': ['job_facts', key]}) \
        if alter else (lambda key: {})
    steps = field('jsteps', 'Steps', 'grid', columns=[
        column('jstid', 'Id', 'number', help='Blank for a new step.'),
        column('jstname', 'Name', required=True),
        column('jstenabled', 'Enabled', 'boolean'),
        column('jstkind', 'Kind', 'select', options=[
            {'value': 'sql', 'label': 'SQL'},
            {'value': 'batch', 'label': 'Batch'}]),
        column('jstconntype', 'Connection', 'select', options=[
            {'value': 'local', 'label': 'Local (database name)'},
            {'value': 'remote', 'label': 'Remote (connection string)'}]),
        column('jstdbname', 'Database'),
        column('jstconnstr', 'Connection string', help=(
            'libpq keywords without a password; pgAgent reads .pgpass '
            'and services.')),
        column('jstonerror', 'On error', 'select', options=[
            {'value': code, 'label': label}
            for code, label in ON_ERROR.items()]),
        column('jstcode', 'Code', 'multiline'),
        column('jstdesc', 'Comment'),
    ], **initial('jsteps'))
    schedules = field('jschedules', 'Schedules', 'grid', columns=[
        column('jscid', 'Id', 'number', help='Blank for a new schedule.'),
        column('jscname', 'Name', required=True),
        column('jscenabled', 'Enabled', 'boolean'),
        column('jscstart', 'Start', required=True,
               help='Timestamp with time zone.'),
        column('jscend', 'End', help='Empty for no end.'),
        column('jscminutes', 'Minutes',
               help='Positions 0-59, comma separated; empty for none.'),
        column('jschours', 'Hours', help='Positions 0-23.'),
        column('jscweekdays', 'Week days',
               help='Positions 0-6, Sunday first.'),
        column('jscmonthdays', 'Month days',
               help='Positions 0-31; 31 is the last day.'),
        column('jscmonths', 'Months', help='Positions 0-11.'),
        column('jscdesc', 'Comment'),
    ], **initial('jschedules'))
    fields = [
        field('jobname', 'Name', required=not alter, **initial('jobname')),
        field('jobenabled', 'Enabled', 'boolean', default=True,
              **initial('jobenabled')),
        field('jobjclid', 'Job class id', 'number', default=1,
              help='pgagent.pga_jobclass.jclid; 1 is Routine Maintenance.',
              **initial('jobjclid')),
        field('jobhostagent', 'Host agent',
              help='Empty lets any agent run it.', **initial('jobhostagent')),
        field('jobdesc', 'Comment', 'multiline', **initial('jobdesc')),
        steps, schedules,
    ]
    return {'form_id': f'postgresql-pgagent-job-{operation}',
            'form_key': 'native:postgresql:server:pgagent-job',
            'title': ('Edit' if alter else 'Create') + ' pgAgent job',
            'fields': fields,
            'notes': ('Steps and schedules are the full set: a row with an '
                      'id updates it, a row without one adds it, and an '
                      'existing id left out is removed.')}
