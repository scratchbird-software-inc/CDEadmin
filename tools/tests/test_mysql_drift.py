"""Full-scope checksum, multiplicity, precision and interruption boundaries."""
import math
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_drift as native
from pgadmin.cdeadmin.workspace.mysql_drift_jobs import DriftJob,DriftJobs


def source(kind='varchar'):
    return {'columns':[{'COLUMN_NAME':'value','DATA_TYPE':kind}],'key':[]}


def record(value):return native.row_record((value,),source())


def test_complete_multisets_preserve_duplicates_and_order_independence(tmp_path):
    left=native.Runs(tmp_path/'left',lambda n:None);right=native.Runs(tmp_path/'right',lambda n:None)
    a,b,c=('a'*64,'b'*64,'c'*64)
    for value in [a,a,b,b]:left.add(record(value))
    for value in [b,a,c,c]:right.add(record(value))
    result=native.compare(left,right,1,lambda:None)
    assert result['state']=='different' and result['source_rows']==result['target_rows']=='4'
    assert result['source_only_rows']==result['target_only_rows']=='2'
    assert len(result['examples'])==1 and result['examples_truncated']


def test_spilled_and_compacted_runs_compare_all_rows(tmp_path):
    budget=[0]
    def reserve(n):budget[0]+=n
    left=native.Runs(tmp_path/'left',reserve);right=native.Runs(tmp_path/'right',reserve)
    values=[format(i,'064x') for i in range(140)]
    for run,items in [(left,values),(right,list(reversed(values)))]:
        for value in items:run.add(record(value));run.flush()
        assert len(run.paths)<64
    result=native.compare(left,right,0,lambda:None)
    assert result['state']=='matched' and result['source_rows']=='140'
    assert budget[0]==sum(p.stat().st_size for p in tmp_path.rglob('*') if p.is_file())


def test_binary_ieee_and_native_enum_set_indices_are_not_display_strings():
    first=1.0;second=math.nextafter(first,2.0)
    assert native.row_record((first,),source('double'))!=native.row_record((second,),source('double'))
    assert native.row_record((None,),source())!=record('0'*64)
    assert 'AS UNSIGNED' in native.projection(source('set'))[0]
    assert 'SHA2' not in native.projection(source('double'))[0]
    with pytest.raises(native.Error):native.row_record((),source())


def test_bounds_cannot_be_replaced_with_sampling_or_unreviewed_tables():
    policy={'consistency':'innodb_snapshot','replica':False,'channel':'','seconds':30,'disk_mib':64,'examples':10}
    assert native.options(policy)==policy
    for changes in [{'seconds':True},{'examples':201},{'disk_mib':0},{'where':'id<10'},{'consistency':'sample'}]:
        with pytest.raises(native.Error):native.options({**policy,**changes})
    with pytest.raises(native.Error):native.selections([{'source_table':'t','target_table':'t'}])


class FakeObserver:
    def __init__(self):
        self.identity={'server_uuid':'native','connection_id':1,'thread_id':2};self.connection=SimpleNamespace(rollback=lambda:None)
        self.native_interface='fake';self.commands=[]
    def query(self,sql,*args,**kwargs):self.commands.append(sql);return []
    def close(self):self.connection=None


def test_stale_identity_never_reports_matching_rows_and_releases_locks(tmp_path):
    observers=[FakeObserver(),FakeObserver()];controls=[FakeObserver(),FakeObserver()]
    table={'source_table':'t','target_table':'t','source_fingerprint':'a'*64,'target_fingerprint':'b'*64}
    options={'consistency':'innodb_snapshot','replica':False,'channel':'','seconds':30,'disk_mib':64,'examples':10}
    job=DriftJob(('owner',),observers,controls,['a','b'],[table],options,lambda:None,tmp_path/'job')
    with patch.object(native,'position',return_value={'gtid_mode':'ON','gtid_executed':'native:1'}),patch.object(native,'describe',return_value={'fingerprint':'changed'}):job.run()
    assert job.state=='incomplete' and job.closed and all(r['state']!='matched' for r in job.coverage)
    assert all('UNLOCK TABLES' in o.commands for o in observers)
    assert not job.directory.exists()


def test_cancel_before_dispatch_and_private_owner_expiry(tmp_path):
    observers=[FakeObserver(),FakeObserver()];controls=[FakeObserver(),FakeObserver()]
    options={'consistency':'locked_scan','replica':False,'channel':'','seconds':30,'disk_mib':1,'examples':0}
    job=DriftJob(('owner',),observers,controls,['a','b'],[],options,lambda:None,tmp_path/'job')
    job.cancelled.set();job.run()
    assert job.state=='cancelled' and not any('FLUSH TABLES' in command for observer in observers for command in observer.commands)
    jobs=DriftJobs(tmp_path/'jobs')
    try:
        jobs.jobs[job.id]=job
        with pytest.raises(native.Error):jobs.get(('another owner',),job.id)
        job.finished=time.monotonic()-301
        with pytest.raises(native.Error):jobs.get(('owner',),job.id)
        assert not job.coverage
    finally:jobs.close()
