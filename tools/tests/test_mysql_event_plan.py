"""Native event DDN retains identity, complete schedules and event time zone."""
from copy import deepcopy
import pytest
from pgadmin.cdeadmin.workspace.mysql_event_plan import compile_event
from test_mysql_sql_export import model
from pgadmin.cdeadmin.workspace.mysql_sql_export import build_metadata


def event():
    return {'name':'e`é','native':{'definition':"CREATE DEFINER=`root`@`%` EVENT `e``é` ON SCHEDULE AT '2037-01-01 12:00:00' ON COMPLETION PRESERVE DISABLE DO BEGIN SELECT 1; SELECT 2; END"}}


def test_event_compilation_retains_exact_definer_schedule_and_body():
    row=event()
    assert compile_event(row,'create','d`é').startswith('CREATE DEFINER=`root`@`%` EVENT `d``é`.`e``é` ON SCHEDULE')
    assert compile_event(row,'alter','db').endswith('DO BEGIN SELECT 1; SELECT 2; END')
    assert compile_event(row,'alter','db').startswith('ALTER DEFINER=')
    row['native']['mysql_change']={'action':'drop','confirmation':'e`é'}
    assert compile_event(row,'drop','db')=='DROP EVENT `db`.`e``é`'


def test_event_header_identity_and_explicit_removal_are_required():
    row=event();row['name']='other'
    with pytest.raises(ValueError,match='identity'):compile_event(row,'create','db')
    with pytest.raises(ValueError,match='confirmation'):compile_event(event(),'drop','db')


def test_native_export_sets_and_restores_event_time_zone_and_missing_context_blocks():
    context={'sql_mode':'','character_set_client':'utf8mb4','collation_connection':'utf8mb4_bin','time_zone':'+05:30'}
    document=model([('event','e',event()['native']['definition'],{'definition_context':context})])
    result=build_metadata(document);assert result['script_available']
    assert 'SET SESSION time_zone = CONVERT(' in result['script']
    assert ' = @@SESSION.time_zone' in result['script']
    assert next(row for row in result['statements'] if row['kind']=='event')['context']['time_zone']=='+05:30'
    altered=deepcopy(document);next(row for row in altered['rows'].values() if row['kind']=='event')['native']['definition_context'].pop('time_zone')
    assert not build_metadata(altered)['script_available']
