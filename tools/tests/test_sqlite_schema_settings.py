"""Native typed pager/header settings, exact values and original TEMP lifecycle."""
import sqlite3
import pytest
from test_sqlite_connection_pragmas import native,run  # noqa: F401
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.providers.sqlite.schema_settings import SPECS
from ui_descriptor_roundtrip import engine_operations,operation_draft

VALUES={'cache_size':-800,'cache_spill':0,'max_page_count':2000,'default_cache_size':777,
 'schema_version':77,'journal_size_limit':'1048576','mmap_size':'1048576',
 'secure_delete':'FAST','locking_mode':'EXCLUSIVE','temp_store':'MEMORY'}


def change(native,name,value,revision=0,receipt=None):
    receipt=receipt or run(native,'review',pragma=name,value=value,_native_work_revision=revision)
    values={'value':value,'expected_value':receipt['expected_value'],'confirmed':True}
    if name!='temp_store':values['schema']='main'
    else:values.update(review_id=receipt['review_id'],temp_objects_drop_confirmed=True)
    if name=='schema_version':values['direct_header_change_confirmed']=True
    draft=operation_draft(engine_operations('sqlite')['set_connection_pragma_'+name+'@database'],values)
    return run(native,'set_connection_pragma',pragma=name,_native_work_revision=revision,**draft)


@pytest.mark.parametrize('name',SPECS)
def test_native_descriptor_setter_readback_without_transaction_finalization(native,name):
    source=native[2];source.execute('CREATE TABLE owned(value)');source.commit()
    if name!='temp_store':source.execute('SAVEPOINT caller');source.execute('INSERT INTO owned VALUES(7)')
    result=change(native,name,VALUES[name])
    assert result['effective_value']==run(native,'inspect',pragma=name)['effective_value']
    assert result['outcome'] in ('applied','native_adjusted')
    assert not result['commit_requested'] and not result['rollback_requested']
    assert not result['physical_allocation_or_lock_ownership_observed']
    if name!='temp_store':
        assert source.in_transaction and source.execute('SELECT * FROM owned').fetchall()==[(7,)]
        source.execute('ROLLBACK TO caller');source.execute('RELEASE caller')


@pytest.mark.parametrize('name',SPECS)
def test_native_stale_or_invalid_value_refuses(native,name):
    with pytest.raises(RelationalClientError):run(native,'review',pragma=name,value=True,_native_work_revision=0)
    receipt=run(native,'review',pragma=name,value=VALUES[name],_native_work_revision=0)
    with pytest.raises(RelationalClientError):
        run(native,'set_connection_pragma',pragma=name,value=VALUES[name],expected_value='unobserved',confirmed=True,_native_work_revision=0)
    assert run(native,'inspect',pragma=name)['effective_value']==receipt['before_value']


def test_exact_decimal_and_schema_admission(native):
    for value in [2**53, '-0','1e6','9223372036854775808','01']:
        with pytest.raises(RelationalClientError):run(native,'review',pragma='journal_size_limit',value=value)
    with pytest.raises(RelationalClientError):run(native,'review',pragma='cache_size',schema='missing',value=7)
    with pytest.raises(RelationalClientError):run(native,'review',pragma='temp_store',schema='main',value='MEMORY')
    source=native[2];source.execute('ATTACH DATABASE ? AS extra',(str(native[0].parent/'extra.db'),))
    before=run(native,'inspect',pragma='cache_size')['effective_value']
    review=run(native,'review',pragma='cache_size',schema='extra',value=-333)
    result=run(native,'set_connection_pragma',pragma='cache_size',schema='extra',value=-333,expected_value=review['before_value'],confirmed=True)
    assert result['effective_value']==-333 and run(native,'inspect',pragma='cache_size')['effective_value']==before


def test_native_header_rollback_does_not_restore_connection_cache(native):
    source=native[2];source.execute('CREATE TABLE owned(value)');source.commit()
    before=source.execute('PRAGMA default_cache_size').fetchone()[0]
    source.execute('BEGIN');result=change(native,'default_cache_size',777)
    assert result['connection_cache_after']==777 and result['file_persisted'] is None
    source.rollback()
    assert source.execute('PRAGMA default_cache_size').fetchone()[0]==before
    assert source.execute('PRAGMA cache_size').fetchone()[0]==777


def test_temp_policy_review_deletion_scope_revision_and_one_use(native):
    source=native[2];source.executescript('CREATE TEMP TABLE private(value);INSERT INTO private VALUES(7);CREATE TABLE kept(value)')
    review=run(native,'review',pragma='temp_store',value='MEMORY',_native_work_revision=0)
    assert review['temp_objects'][0]['name_preview']=='private'
    with pytest.raises(RelationalClientError):change(native,'temp_store','MEMORY',revision=1,receipt=review)
    source.execute('SAVEPOINT caller')
    with pytest.raises(RelationalClientError):change(native,'temp_store','MEMORY',receipt=review)
    assert source.execute('SELECT * FROM private').fetchall()==[(7,)]
    source.execute('RELEASE caller')
    result=change(native,'temp_store','MEMORY',receipt=review)
    assert result['effective_value']=='MEMORY'
    assert source.execute("SELECT name FROM temp.sqlite_schema").fetchall()==[]
    assert source.execute("SELECT name FROM main.sqlite_schema WHERE name='kept'").fetchone()==('kept',)
    with pytest.raises(RelationalClientError):change(native,'temp_store','MEMORY',receipt=review)


def test_native_pager_adjustment_and_defensive_header_refusal_are_observed(native):
    source=native[2];source.execute('CREATE TABLE kept(value)');source.commit()
    result=change(native,'max_page_count',1)
    assert result['outcome']=='native_adjusted' and result['effective_value']>=2
    if hasattr(source,'setconfig'):
        source.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE,True)
        result=change(native,'schema_version',77)
        # SQLite 3.40.0 added defensive schema_version no-op protection.
        if sqlite3.sqlite_version_info >= (3,40,0):
            assert result['outcome']=='native_adjusted' and result['effective_value']!=77
        else:
            assert result['outcome']=='applied' and result['effective_value']==77
