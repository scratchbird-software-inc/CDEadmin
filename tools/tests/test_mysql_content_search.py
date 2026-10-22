"""Native search comparison, source binding, cancellation and privacy contracts."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
import time

import pytest
from pgadmin.cdeadmin.providers.mysql_family import mysql_content_search as native
from pgadmin.cdeadmin.workspace import mysql_content_search as jobs
from pgadmin.cdeadmin.workspace.mysql_content_search_service import selected_tables


def column(kind='varchar',name='note'):
    return {'COLUMN_NAME':name,'DATA_TYPE':kind,'COLUMN_TYPE':kind,'COLLATION_NAME':'utf8mb4_0900_ai_ci',
        'PRIVILEGES':'select','IS_NULLABLE':'NO'}


def test_text_wildcards_are_literal_and_native_collation_is_preserved():
    predicate, parameters = native.predicate(column(name='a`b'),native.options({'mode':'text_contains','value':"' OR 1=1 %_!"}))
    assert predicate == "`a``b` LIKE %s ESCAPE '!'"
    assert parameters == ("%' OR 1=1 !%!_!!%",)
    assert 'COLLATE' not in predicate and 'OR 1=1' not in predicate


@pytest.mark.parametrize('value',['18446744073709551615','12345678901234567890123456789012345678901234567890123456789012345',
    '1.0000000000000000000000000000000000000000000000000','0e-1000','1e-30','1e64'])
def test_exact_numeric_predicates_bind_explicit_native_decimal_without_approximate_coercion(value):
    sql, params = native.predicate(column('decimal'),native.options({'mode':'numeric_equal','value':value}))
    assert sql.startswith('`note`=CAST(%s AS DECIMAL(65,') and sql.endswith('))')
    assert isinstance(params[0],str) and Decimal(params[0])==Decimal(value) and 'E' not in params[0].upper()


def test_approximate_numeric_and_inapplicable_exact_values_are_explicit():
    selected = native.options({'mode':'numeric_equal','value':'1e100'})
    assert native.predicate(column('decimal'),selected) is None
    sql, params = native.predicate(column('double'),selected)
    assert sql=='`note`=CAST(%s AS DOUBLE)' and Decimal(params[0])==Decimal('1e100')
    assert native.predicate(column('varchar'),selected) is None


def test_binary_search_uses_bytes_and_does_not_conflate_text_or_null():
    selected = native.options({'mode':'binary_exact','value':'00ff2500'})
    assert native.predicate(column('blob'),selected)==('`note`=UNHEX(%s)',('00ff2500',))
    assert native.predicate(column('blob'),native.options({'mode':'binary_contains','value':'ff25'}))==('LOCATE(UNHEX(%s),`note`)>0',('ff25',))
    assert native.predicate(column(),selected) is None
    assert native.predicate(column('vector'),native.options({'mode':'is_null'}))==('`note` IS NULL',())


@pytest.mark.parametrize('value',['nan','inf','1.2.3','0); DELETE FROM t;','1e99999'])
def test_invalid_numeric_search_does_not_admit_sql_or_nonfinite_values(value):
    with pytest.raises(native.SearchError):native.options({'mode':'numeric_equal','value':value})


def test_selected_source_lists_are_distinct_and_bounded():
    item={'table_name':'t`雪','fingerprint':'a'*64,'columns':['note']}
    assert selected_tables([item])==[item]
    with pytest.raises(native.SearchError):selected_tables([item,item])
    with pytest.raises(native.SearchError):selected_tables([{**item,'columns':['n'+str(i) for i in range(257)]}])


def job_fixture(monkeypatch, *, warnings=False,indexed=False):
    source={'schema_name':'db','table_name':'t','fingerprint':'a'*64,'key':['id'],'engine':'InnoDB',
        'columns':[column(),column('bigint','id')],'indexes':[]}
    monkeypatch.setattr(native,'describe',Mock(return_value=source))
    observer=SimpleNamespace(identity={'server_uuid':'server','version':'9.7.0','account':'owner@%',
        'active_role':'NONE','connection_id':10,'thread_id':11},begin=Mock(),rollback=Mock(),close=Mock(),warning_count=0)
    def query(sql,params=None,**kwargs):
        if 'AS sr_preview' in sql:
            observer.warning_count=int(warnings)
            return [{'sr_preview':'private <img src=x>', 'sr_value_bytes':20,'sr_key_0':18446744073709551615}]
        if sql.startswith('SHOW WARNINGS'):
            return [{'Code':1292,'Message':'private SQL must never escape'}]
        return []
    observer.query=Mock(side_effect=query)
    control=SimpleNamespace(query=Mock(return_value=[{'server_uuid':'server'}]),connection=Mock(),close=Mock())
    selected=native.options({'mode':'text_exact','value':'private needle','indexed_only':indexed})
    item={'table_name':'t','fingerprint':'a'*64,'columns':['note']}
    job=jobs.SearchJob(('owner',1,None,'config'),observer,control,'db',[item],selected,Mock())
    return job,observer,control


def test_private_job_uses_bound_value_native_key_and_only_its_own_read_transaction(monkeypatch):
    job,observer,control=job_fixture(monkeypatch)
    job.run()
    result=job.snapshot()
    assert result['terminal'] and result['state']=='completed' and len(result['matches'])==1
    assert 'private needle' not in str(result)
    source,params=next(call.args for call in observer.query.call_args_list if 'AS sr_preview' in call.args[0])
    assert 'private needle' not in source and params==('private needle',)
    locator=next(iter(job.locators.values()))
    assert locator['keys']==[18446744073709551615]
    observer.begin.assert_called_once();observer.rollback.assert_called_once();observer.close.assert_called_once();control.close.assert_called_once()


def test_native_comparison_warnings_are_gaps_not_false_matches_or_source_leaks(monkeypatch):
    job,_,_=job_fixture(monkeypatch,warnings=True)
    job.run();result=job.snapshot()
    assert result['state']=='partial' and not result['matches']
    assert result['coverage'][0]['columns'][0]['warning_codes']==[1292]
    assert 'private SQL' not in str(result)


def test_indexed_only_refuses_a_native_table_or_full_index_scan(monkeypatch):
    job,observer,_=job_fixture(monkeypatch,indexed=True)
    monkeypatch.setattr(native,'indexed_plan',Mock(return_value=False))
    job.run()
    assert job.snapshot()['coverage'][0]['columns'][0]['reason']=='native-plan-has-no-key-lookup-or-range'
    assert not any('AS sr_preview' in call.args[0] for call in observer.query.call_args_list)


def test_changed_native_source_is_not_searched(monkeypatch):
    job,observer,_=job_fixture(monkeypatch)
    native.describe.return_value['fingerprint']='b'*64
    job.run()
    assert job.snapshot()['state']=='partial' and not job.matches
    assert not any('AS sr_preview' in call.args[0] for call in observer.query.call_args_list)


def test_cancellation_never_kills_an_unconfirmed_native_thread(monkeypatch):
    job,observer,control=job_fixture(monkeypatch)
    monkeypatch.setattr(jobs,'thread_matches',Mock(return_value=False))
    job.stop()
    assert job.cancelled.is_set() and not job.cancellation['native_kill_sent']
    assert not any(call.args[0].startswith('KILL') for call in control.query.call_args_list)
    observer.close.assert_not_called()  # Only worker finalization releases its connection ID.


def test_expiry_removes_values_and_native_locators_without_waiting_for_another_search(monkeypatch):
    job,_,_=job_fixture(monkeypatch);job.run();job.created=time.monotonic()-301
    manager=jobs.SearchJobs()
    try:
        manager.jobs[job.id]=job;manager.prune()
        assert not manager.jobs and not job.matches and not job.locators and job.selected['value'] is None
    finally:manager.close()


def test_row_navigation_revalidates_structure_before_reading_data(monkeypatch):
    job,_,_=job_fixture(monkeypatch);job.run()
    observer=SimpleNamespace(identity=job.identity,begin=Mock(),rollback=Mock(),query=Mock(return_value=[]))
    native.describe.return_value['fingerprint']='b'*64
    with pytest.raises(native.SearchError,match='structure changed'):
        jobs.navigate(observer,job,next(iter(job.locators)))
    assert len(observer.query.call_args_list)==1 and 'WHERE 0' in observer.query.call_args.args[0]


@pytest.mark.parametrize('access,key,expected',[('range','note',True),('ref','note',True),('ALL',None,False),('index','note',False)])
def test_native_explain_access_is_authoritative_for_indexed_only(access,key,expected):
    import json
    reader=SimpleNamespace(query=Mock(return_value=[{'EXPLAIN':json.dumps({'query_block':{'table':{
        'table_name':'t','access_type':access,'key':key}}})}]))
    assert native.indexed_plan(reader,'SELECT 1 FROM t WHERE note=%s',('bound',)) is expected
