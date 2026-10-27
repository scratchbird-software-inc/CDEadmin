"""Managed disposable session comparisons on an exact retained connection."""
from contextlib import ExitStack
import hashlib
import json
import os
import sqlite3
import threading
import time

from ..operations.fileio import durable_replace,private_directory,private_file
from ..providers.sqlite.diff_export import export_difference
from ..providers.sqlite.session_api import SessionAPIError
from ..providers.sqlite.transform_context import retained_context,schema_snapshot
from .sqlite_capture_jobs import SQLiteCaptureJobs
from .sqlite_upload_jobs import UploadTransport


class SQLiteDiffJobs(SQLiteCaptureJobs):
    operation='sqlite_native_table_diff'
    review_warnings=(
        'Compare the attached source with the destination on this exact retained query connection. The comparison includes the connection\'s visible uncommitted data and schema; it does not commit or roll back SQL.',
        'A new disposable native capture records the table difference. Existing captures stay separate. Cancellation can leave a partial private capture, which is discarded rather than added to a user capture.',
        'The native comparison uses the connection\'s current transaction and visibility. It reserves that connection until the worker finishes. Progress counts are native VM callback counts, not rows or a percentage.',
        'Native comparison, streamed export, output verification and publication have separate receipts. An uncertain operation is never automatically repeated. A changeset or patchset is not a database backup.',)

    def data_file_name(self,record):return 'difference.native'


class DiffTransport(UploadTransport):
    def __init__(self,jobs,library,binding):
        super().__init__(jobs,library);self.binding=binding

    def execute(self,record,directory,cancel,progress):
        selected=record['options'];started=time.monotonic();timeout=selected['timeout_seconds']
        stop=threading.Event();counts={'vm_progress_callbacks':0}
        def check():
            if cancel.is_set() or timeout is not None and time.monotonic()-started>=timeout:
                stop.set();raise SessionAPIError('Native table comparison was stopped',sqlite3.SQLITE_INTERRUPT)
        def report(event):progress({**event,'vm_progress_callbacks':str(counts['vm_progress_callbacks']),
            'progress_scope':'native VM progress callbacks; not rows or percentage'})
        incoming=directory/'archive.incoming';incoming.mkdir(mode=0o700);private_directory(incoming)
        path=incoming/'difference.native'
        check()
        with ExitStack() as cleanup:
            connection,api=cleanup.enter_context(retained_context(self.binding,record['source']['schema_binding']))
            if api.program!=record['program']:raise SessionAPIError('The reviewed native comparison helper changed')
            if schema_snapshot(connection,selected['source_database'],transient=True)!=record['source']['source_schema']:
                raise SessionAPIError('The reviewed attached source schema changed before native comparison')
            transaction_open=connection.in_transaction
            descriptor=os.open(path,os.O_RDWR|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0),0o600)
            cleanup.callback(os.close,descriptor);private_file(path)
            private_capture=None
            def acknowledge(event,data):
                nonlocal private_capture
                if event=='capture_created':private_capture=data['capture_id']
                self.jobs.update(record,**{event:True,event+'_details':data},
                    **({'native_returned':True,'native_returned_bytes':data['native_written_bytes']} if event=='export_returned' else {}))
            try:
                with self.native_cancellation(cancel,timeout,started,report,stage='native-table-diff',on_cancel=stop.set) as signal:
                    self.jobs.update(record,native_dispatch_admitted=True,source_transaction_open=transaction_open)
                    observed=export_difference(api,selected['database'],selected['source_database'],selected['table_name'],selected['kind'],descriptor,
                        cancel_event=stop,cancel_descriptor=signal,progress=counts,acknowledge=acknowledge,
                        estimate_size=selected['estimate_size'],track_rowids=selected['track_rowids'])
                    self.jobs.update(record,source_transaction_open_after=connection.in_transaction)
                    if str(os.fstat(descriptor).st_size)!=observed['native_written_bytes']:
                        raise SessionAPIError('Native table-difference output length differs from its acknowledgement')
                    os.lseek(descriptor,0,os.SEEK_SET);parsed=api.call('inspect_file',descriptor,signal)
                    self.jobs.update(record,native_output_inspection=parsed)
            finally:
                if private_capture is not None and private_capture in api.captures:
                    with self.binding['client']._lock:self.binding['client']._uncertain.add(id(connection))
                    self.jobs.update(record,native_capture_close_unconfirmed=True,source_connection_blocked=True)
            if schema_snapshot(connection,selected['source_database'],transient=True)!=record['source']['source_schema']:
                raise SessionAPIError('The attached source schema changed during native comparison')
            check();os.fsync(descriptor)
        metadata={'format':'sqlite-native-'+selected['kind']+'@3.53.0','native_kind':selected['kind'],'input_name':path.name,
            'program':record['program'],'options':selected,'source':record['source'],'native':observed,'inspection':parsed,
            'source_transaction_open':transaction_open,'database_mutation':False,'database_recovery_verified':False}
        with (incoming/'archive.json').open('x',encoding='utf8') as stream:
            private_file(incoming/'archive.json');json.dump(metadata,stream,sort_keys=True,ensure_ascii=True);stream.flush();os.fsync(stream.fileno())
        files=[]
        for target in (path,incoming/'archive.json'):
            checksum=hashlib.sha256()
            with target.open('rb') as stream:
                while block:=stream.read(1048576):check();checksum.update(block)
            files.append({'path':target.name,'size':target.stat().st_size,'sha256':checksum.hexdigest()})
        artifact={'format':metadata['format'],'native_kind':selected['kind'],'input_name':path.name,'files':files,
            'total_bytes':sum(row['size'] for row in files),**parsed}
        check();self.jobs.update(record,state='publishing',sealed_candidate={'artifact':artifact})
        durable_replace(incoming,directory/'archive')
        return {'artifact':artifact,'native_diff':observed,'database_mutation':False,'database_recovery_verified':False}
