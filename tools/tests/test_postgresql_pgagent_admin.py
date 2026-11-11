"""PostgreSQL pgAgent job create/alter/drop and run now compile to exact
native statements (M6, 2026-11-11)."""
import pytest
from pgadmin.cdeadmin.providers.postgresql.native_admin import (
    compile_native_admin, PostgreSQLNativeAdminError,
)
from pgadmin.cdeadmin.providers.postgresql.pgagent import facts, form

JOB = {'name': 'nightly', 'catalog_metadata': {
    'jobid': 7, 'jobname': 'nightly', 'jobenabled': True, 'jobdesc': 'd',
    'jobhostagent': '', 'jobjclid': 1, 'jobclass': 'Routine Maintenance',
    'has_connstr': True,
    'steps': [{'jstid': 3, 'jstname': 'vac', 'jstenabled': True,
               'jstkind': True, 'jstconntype': True, 'jstdbname': 'app',
               'jstconnstr': '', 'jstonerror': 'f', 'jstcode': 'VACUUM',
               'jstdesc': ''}],
    'schedules': [{'jscid': 5, 'jscname': 'daily', 'jscenabled': True,
                   'jscstart': '2026-01-01 02:00:00+00', 'jscend': None,
                   'jscminutes': '{' + ','.join(['t'] + ['f'] * 59) + '}',
                   'jschours': [False] * 2 + [True] + [False] * 21,
                   'jscweekdays': '{t,t,t,t,t,t,t}',
                   'jscmonthdays': '{' + ','.join(['t'] * 32) + '}',
                   'jscmonths': '{' + ','.join(['t'] * 12) + '}',
                   'jscdesc': ''}]}}


def compile_job(operation, draft, native=JOB):
    native = dict(native)
    native['job_facts'] = facts(native)
    return compile_native_admin({
        'resource_kind': 'pgagent-job', 'operation_id': operation,
        'draft': draft,
        'target_resource': {'extensions': {'postgresql': {'native': native}}}})


def statements(operation, draft, native=JOB):
    return compile_job(operation, draft, native)['statement'].split(';\n')


def test_facts_render_grids_from_the_captured_rows():
    current = facts(JOB)
    assert (current['jobid'], current['jobname'], current['has_connstr']) == (
        7, 'nightly', True)
    assert current['jsteps'] == [{
        'jstid': 3, 'jstname': 'vac', 'jstenabled': True, 'jstkind': 'sql',
        'jstconntype': 'local', 'jstdbname': 'app', 'jstconnstr': '',
        'jstonerror': 'f', 'jstcode': 'VACUUM', 'jstdesc': ''}]
    schedule = current['jschedules'][0]
    assert (schedule['jscminutes'], schedule['jschours'],
            schedule['jscweekdays']) == ('0', '2', '0, 1, 2, 3, 4, 5, 6')
    assert schedule['jscend'] == ''


def test_create_is_one_do_block_with_steps_and_schedules():
    compiled = compile_job('create', {
        'jobname': "it's", 'jobenabled': True, 'jobjclid': 2,
        'jobhostagent': 'host1', 'jobdesc': 'desc',
        'jsteps': [{'jstname': 's1', 'jstkind': 'sql', 'jstconntype': 'local',
                    'jstdbname': 'app', 'jstcode': 'SELECT 1'},
                   {'jstname': 'b1', 'jstkind': 'batch', 'jstenabled': False,
                    'jstonerror': 'i', 'jstcode': 'echo hi'}],
        'jschedules': [{'jscname': 'sched', 'jscstart': '2026-01-01 00:00:00+00',
                        'jscminutes': '0, 30', 'jschours': [1],
                        'jscweekdays': [True] * 7, 'jscmonthdays': '',
                        'jscmonths': ''}]})
    text = compiled['statement']
    assert text.startswith('DO $$\nDECLARE\n    jid integer;\nBEGIN\n')
    assert text.endswith('\nEND\n$$')
    assert ("INSERT INTO pgagent.pga_job (jobname, jobenabled, jobjclid, "
            "jobhostagent, jobdesc) VALUES ('it''s'::text, true, 2::integer, "
            "'host1'::text, 'desc'::text) RETURNING jobid INTO jid;") in text
    assert ("INSERT INTO pgagent.pga_jobstep (jstjobid, jstname, jstenabled, "
            "jstkind, jstdbname, jstonerror, jstcode, jstdesc, jstconnstr) "
            "VALUES (jid, 's1'::text, true, 's'::character(1), 'app'::name, "
            "'f'::character(1), 'SELECT 1'::text, ''::text, ''::text);") in text
    assert ("VALUES (jid, 'b1'::text, false, 'b'::character(1), ''::name, "
            "'i'::character(1), 'echo hi'::text, ''::text, ''::text);") in text
    minutes = "'{" + ','.join(['t'] + ['f'] * 29 + ['t'] + ['f'] * 29) + "}'::boolean[]"
    hours = "'{" + ','.join(['f', 't'] + ['f'] * 22) + "}'::boolean[]"
    assert minutes in text and hours in text
    assert "'{" + ','.join(['f'] * 32) + "}'::boolean[]" in text  # no month days
    assert 'NULL::timestamp with time zone' in text  # no end
    assert compiled['read_only'] is False and 'autocommit' not in compiled


def test_alter_diffs_the_grids_against_the_captured_rows():
    lines = statements('alter', {
        'jobenabled': False,
        'jsteps': [{'jstid': 3, 'jstname': 'vac', 'jstkind': 'sql',
                    'jstconntype': 'local', 'jstdbname': 'app',
                    'jstcode': 'VACUUM ANALYZE'},
                   {'jstname': 'new', 'jstkind': 'sql', 'jstconntype': 'remote',
                    'jstconnstr': 'host=db2 dbname=app', 'jstcode': 'SELECT 2'}],
        'jschedules': []})
    assert lines[0] == 'UPDATE pgagent.pga_job SET jobenabled = false WHERE jobid = 7'
    assert lines[1].startswith('UPDATE pgagent.pga_jobstep SET jstname = \'vac\'::text')
    assert lines[1].endswith("jstcode = 'VACUUM ANALYZE'::text, jstdesc = ''::text, "
                             "jstconnstr = ''::text WHERE jstid = 3 AND jstjobid = 7")
    assert lines[2].startswith('INSERT INTO pgagent.pga_jobstep (jstjobid, jstname')
    assert "'host=db2 dbname=app'::text" in lines[2] and "''::name" in lines[2]
    assert lines[3] == 'DELETE FROM pgagent.pga_schedule WHERE jscid = 5 AND jscjobid = 7'
    assert len(lines) == 4
    # Leaving a grid out keeps it; nothing changed is refused.
    assert statements('alter', {'jobdesc': 'x'}) == [
        "UPDATE pgagent.pga_job SET jobdesc = 'x'::text WHERE jobid = 7"]
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_job('alter', {})


def test_refusals_keep_text_as_data():
    bad = [
        ('create', {'jobname': 'j', 'jsteps': [{'jstname': 's', 'jstkind': 'sql',
                                                'jstconntype': 'local'}]}, 'database name'),
        ('create', {'jobname': 'j', 'jsteps': [{'jstname': 's', 'jstkind': 'sql',
                                                'jstconntype': 'remote',
                                                'jstconnstr': 'host=h password=x'}]}, 'password'),
        ('create', {'jobname': 'j', 'jsteps': [{'jstname': 's', 'jstonerror': 'x'}]}, 'jstonerror'),
        ('create', {'jobname': 'j', 'jschedules': [{'jscname': 's', 'jscstart': 'tomorrow'}]}, 'timestamp'),
        ('create', {'jobname': 'j', 'jschedules': [{'jscname': 's', 'jscstart': '2026-01-01',
                                                    'jscminutes': '60'}]}, 'positions run'),
        ('create', {'jobname': 'j', 'jschedules': [{'jscname': 's', 'jscstart': '2026-01-01',
                                                    'jschours': 'noon'}]}, 'comma list'),
        ('alter', {'jsteps': [{'jstid': 99, 'jstname': 's', 'jstkind': 'batch'}]}, 'does not belong'),
        ('drop', {'confirmation': 'other'}, 'confirmation'),
        ('create', {'jobname': 'j', 'jobjclid': 'one'}, 'integer'),
    ]
    for operation, draft, message in bad:
        with pytest.raises(PostgreSQLNativeAdminError, match=message):
            compile_job(operation, draft)
    no_connstr = dict(JOB, catalog_metadata=dict(JOB['catalog_metadata'], has_connstr=False))
    with pytest.raises(PostgreSQLNativeAdminError, match='no connection-string column'):
        compile_job('create', {'jobname': 'j', 'jsteps': [{
            'jstname': 's', 'jstkind': 'sql', 'jstconntype': 'remote',
            'jstconnstr': 'host=h'}]}, no_connstr)
    compiled = compile_job('create', {'jobname': 'j', 'jsteps': [{
        'jstname': 's', 'jstkind': 'sql', 'jstconntype': 'local', 'jstdbname': 'app'}]}, no_connstr)
    assert 'jstconnstr' not in compiled['statement']


def test_drop_and_run_now():
    assert compile_job('drop', {'confirmation': 'nightly'}) == {
        'statement': 'DELETE FROM pgagent.pga_job WHERE jobid = 7', 'read_only': False}
    compiled = compile_native_admin({
        'resource_kind': 'pgagent-job', 'operation_id': 'run-now', 'draft': {},
        'target_resource': {'extensions': {'postgresql': {'native': JOB}}}})
    assert compiled['statement'] == 'UPDATE pgagent.pga_job SET jobnextrun = now() WHERE jobid = 7'
    assert compiled['maintenance']['action'] == 'run-now'
    with pytest.raises(PostgreSQLNativeAdminError):
        compile_native_admin({'resource_kind': 'pgagent-job', 'operation_id': 'run-now',
                              'draft': {'force': True},
                              'target_resource': {'extensions': {'postgresql': {'native': JOB}}}})


def test_forms_follow_the_inherited_ids():
    def field(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    create = {f['field_id']: f for f in form('create', field)['fields']}
    alter = {f['field_id']: f for f in form('alter', field)['fields']}
    assert create['jobname']['required'] and not alter['jobname']['required']
    assert alter['jsteps']['initial_value_path'] == ['job_facts', 'jsteps']
    columns = {c['field_id'] for c in create['jsteps']['columns']}
    assert {'jstid', 'jstname', 'jstkind', 'jstconntype', 'jstdbname',
            'jstconnstr', 'jstonerror', 'jstcode'} <= columns
    columns = {c['field_id'] for c in create['jschedules']['columns']}
    assert {'jscid', 'jscname', 'jscstart', 'jscend', 'jscminutes', 'jschours',
            'jscweekdays', 'jscmonthdays', 'jscmonths'} <= columns
    drop = {f['field_id'] for f in form('drop', field)['fields']}
    assert drop == {'confirmation'}
