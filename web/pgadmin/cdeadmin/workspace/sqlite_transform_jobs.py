"""Reviewed native file transformations, separate from database application."""
from contextlib import ExitStack
import hashlib
import json
import os
import time

from ..operations.fileio import durable_replace,private_directory,private_file
from ..providers.sqlite.changeset_transform import transform
from ..providers.sqlite.transform_context import context,schema_snapshot
from ..providers.sqlite.session_api import SessionAPIError
from .sqlite_capture_jobs import SQLiteCaptureJobs
from .sqlite_upload_jobs import UploadTransport


class SQLiteTransformJobs(SQLiteCaptureJobs):
    operation='sqlite_native_file_transform'
    review_warnings=(
        'Native transformations write a new private artifact. Input artifacts and registered database data are not modified. Ordered inputs and optional schema basis belong to the reviewed operation.',
        'Native inversion, concatenation, changegroups and rebasing preserve SQLite format semantics. Unsupported combinations return native errors; no missing old values or schema are invented.',
        'Rebase buffers come from acknowledged native apply operations. A transformed file still requires its own reviewed application. Native output validation does not establish database recovery.',)

    def data_file_name(self,record):return 'transformed.native'


class TransformTransport(UploadTransport):
    def __init__(self,jobs,library,inputs,route=None):
        super().__init__(jobs,library);self.inputs,self.route=inputs,route

    def execute(self,record,directory,cancel,progress):
        selected=record['options'];started=time.monotonic();timeout=selected['timeout_seconds']
        def check():
            if cancel.is_set() or timeout is not None and time.monotonic()-started>=timeout:raise SessionAPIError('Native file transformation was stopped')
        incoming=directory/'archive.incoming';incoming.mkdir(mode=0o700);private_directory(incoming)
        path=incoming/self.jobs.data_file_name(record)
        with ExitStack() as cleanup:
            streams=[cleanup.enter_context(factory())[0] for factory in self.inputs]
            connection,api=cleanup.enter_context(context(self.library,self.route))
            if api.program!=record['program']:raise SessionAPIError('The reviewed native transformation helper changed')
            if selected['schema_database'] is not None:
                connection.execute('BEGIN')
                if schema_snapshot(connection,selected['schema_database'])!=record['source']['schema']:
                    raise SessionAPIError('The reviewed registered schema changed before native transformation')
            identities=[self.jobs.file_identity(os.fstat(stream.fileno())) for stream in streams]
            descriptor=os.open(path,os.O_RDWR|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0),0o600);cleanup.callback(os.close,descriptor);private_file(path)
            check()
            with self.native_cancellation(cancel,timeout,started,progress,stage='native-transform') as cancel_descriptor:
                observed=transform(api,[stream.fileno() for stream in streams],descriptor,selected,cancel_descriptor=cancel_descriptor)
                self.jobs.update(record,native_returned=True,native_transform=observed)
                if str(os.fstat(descriptor).st_size)!=observed['native_written_bytes']:raise SessionAPIError('Native transformed output length differs from its acknowledgement')
                os.lseek(descriptor,0,os.SEEK_SET);header=os.read(descriptor,1);os.lseek(descriptor,0,os.SEEK_SET)
                kind='patchset' if header==b'P' else 'changeset' if header in {b'T',b''} else None
                if kind is None:raise SessionAPIError('Native transform output has an unknown header')
                parsed=api.call('inspect_file',descriptor,cancel_descriptor)
                self.jobs.update(record,native_output_inspection=parsed)
            for stream,before in zip(streams,identities):
                if self.jobs.file_identity(os.fstat(stream.fileno()))!=before:raise SessionAPIError('A reviewed native input changed during transformation')
            check();os.fsync(descriptor)
            if connection.in_transaction:connection.rollback()
        metadata={'format':'sqlite-native-'+kind+'@3.53.0','native_kind':kind,'input_name':path.name,
            'program':record['program'],'options':selected,'source':record['source'],'native':observed,'inspection':parsed,
            'database_mutation':False,'database_recovery_verified':False}
        with (incoming/'archive.json').open('x',encoding='utf8') as stream:
            private_file(incoming/'archive.json');json.dump(metadata,stream,sort_keys=True,ensure_ascii=True);stream.flush();os.fsync(stream.fileno())
        files=[]
        for target in (path,incoming/'archive.json'):
            hashed=hashlib.sha256()
            with target.open('rb') as stream:
                while block:=stream.read(1048576):check();hashed.update(block)
            files.append({'path':target.name,'size':target.stat().st_size,'sha256':hashed.hexdigest()})
        artifact={'format':metadata['format'],'native_kind':kind,'input_name':path.name,'files':files,
            'total_bytes':sum(row['size'] for row in files),**parsed}
        check();self.jobs.update(record,state='publishing',sealed_candidate={'artifact':artifact})
        durable_replace(incoming,directory/'archive')
        return {'artifact':artifact,'native_transform':observed,'database_mutation':False,'database_recovery_verified':False}
