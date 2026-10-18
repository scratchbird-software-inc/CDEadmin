"""Owned offline native inspection results; they are never apply inputs."""
from contextlib import ExitStack
import hashlib
import json
import os
import time

from ..operations.fileio import durable_replace,private_directory,private_file
from ..providers.sqlite.changeset_inspection import inspect
from ..providers.sqlite.transform_context import context
from ..providers.sqlite.session_api import SessionAPIError
from .sqlite_capture_jobs import SQLiteCaptureJobs,checked_archive_reads
from .sqlite_upload_jobs import UploadTransport


class SQLiteInspectionJobs(SQLiteCaptureJobs):
    operation='sqlite_native_file_inspection'
    review_warnings=(
        'Native inspection reads a verified retained file on an independent in-memory connection. Registered databases and query transactions are not modified.',
        'Native files store column positions and primary-key masks, not original column names or declared SQL types. Missing values are distinct from SQL NULL.',
        'Bounded pages do not validate an unvisited suffix. A preview may split UTF-8 characters; exact byte ranges remain available. Inspection JSON is not a changeset or apply input.',)

    def data_file_name(self,record):return 'value.bin' if record['options']['mode']=='extract' else 'inspection.json'

    def result(self,job_id,owner,endpoint):
        record=self.load(job_id,owner,endpoint)
        if record['state'] not in {'completed','artifact_verified'}:raise SessionAPIError('Select a completed or sealed verified native inspection')
        with self.download(job_id,owner,endpoint,'inspection.json') as (stream,row):
            if row['size']>134217728:raise SessionAPIError('Native inspection JSON exceeds its admitted bound')
            return json.load(stream)


class InspectionTransport(UploadTransport):
    def __init__(self,jobs,library,input_factory):
        super().__init__(jobs,library);self.input_factory=input_factory

    def execute(self,record,directory,cancel,progress):
        started=time.monotonic();selected=record['options'];timeout=selected['timeout_seconds']
        def check():
            if cancel.is_set() or timeout is not None and time.monotonic()-started>=timeout:raise SessionAPIError('Native file inspection was stopped')
        incoming=directory/'archive.incoming';incoming.mkdir(mode=0o700);private_directory(incoming);path=incoming/'inspection.json'
        value_path=incoming/'value.bin' if selected['mode']=='extract' else None
        last_progress=[started]
        def read_check():
            check();now=time.monotonic()
            if now-last_progress[0]>=.2:
                progress({'stage':'verify-native-input','elapsed_seconds':now-started});last_progress[0]=now
        check();progress({'stage':'verify-native-input','elapsed_seconds':0})
        with ExitStack() as cleanup:
            cleanup.enter_context(checked_archive_reads(read_check))
            stream=cleanup.enter_context(self.input_factory())[0];identity=self.jobs.file_identity(os.fstat(stream.fileno()))
            _connection,api=cleanup.enter_context(context(self.library))
            if api.program!=record['program']:raise SessionAPIError('The reviewed native inspection helper changed')
            check()
            output_descriptor=None
            if value_path is not None:
                output_descriptor=os.open(value_path,os.O_RDWR|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0),0o600);cleanup.callback(os.close,output_descriptor);private_file(value_path)
            self.jobs.update(record,native_dispatch_admitted=True)
            with self.native_cancellation(cancel,timeout,started,lambda event:progress({**event,**({'bytes_written':str(value_path.stat().st_size)} if value_path is not None else {})}),stage='native-file-inspection') as cancel_descriptor:
                observed=inspect(api,stream.fileno(),selected,cancel_descriptor,output_descriptor)
                self.jobs.update(record,native_returned=True,native_inspection_ack=observed if selected['mode']=='extract' else {'mode':selected['mode']})
                if output_descriptor is not None:
                    if str(os.fstat(output_descriptor).st_size)!=observed['native_written_bytes']:raise SessionAPIError('Native extracted byte length differs from its acknowledgement')
                    os.fsync(output_descriptor)
            if self.jobs.file_identity(os.fstat(stream.fileno()))!=identity:raise SessionAPIError('The selected native input changed during inspection')
            check()
        metadata={'format':'sqlite-native-inspection@1','program':record['program'],'source':record['source'],
            'options':selected,'inspection':observed,'database_mutation':False,'apply_input':False}
        with path.open('x',encoding='utf8') as stream:
            private_file(path);json.dump(metadata,stream,sort_keys=True,ensure_ascii=True);stream.flush();os.fsync(stream.fileno())
        files=[]
        if path.stat().st_size>134217728:raise SessionAPIError('Native inspection JSON exceeds its admitted bound')
        for file in [path]+([value_path] if value_path is not None else []):
            hashed=hashlib.sha256()
            with file.open('rb') as stream:
                while block:=stream.read(1048576):check();hashed.update(block)
            files.append({'path':file.name,'size':file.stat().st_size,'sha256':hashed.hexdigest()})
        artifact={'format':metadata['format'],'files':files,'total_bytes':sum(file['size'] for file in files),
            'native_inspection_returned':True,'apply_input':False}
        check();self.jobs.update(record,state='publishing',sealed_candidate={'artifact':artifact})
        durable_replace(incoming,directory/'archive')
        return {'artifact':artifact,'database_mutation':False,'apply_input':False}
