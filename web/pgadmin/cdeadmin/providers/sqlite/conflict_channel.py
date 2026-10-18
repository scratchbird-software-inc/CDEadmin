"""Owner-process bridge between live native callbacks and durable responses."""
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time

from ...operations.fileio import durable_replace,private_file
from .changeset_inspection import decode_cell,decode_page
from .session_api import SessionAPIError

CHOICES={'omit':0,'replace':1,'abort':2}
NAMES={1:'data',2:'not_found',3:'conflict',4:'constraint',5:'foreign_key'}
MAX_EVENT=16777216


class ConflictChannel:
    def __init__(self,directory,publish,load,cancel_native):
        self.directory=Path(directory);self.publish,self.load,self.cancel_native=publish,load,cancel_native
        self.finished=threading.Event();self.failed=[];self.thread=None;self.descriptors=[];self.sent={};self.pending=None
        self.native_descriptors=None;self.response_write=None

    def __enter__(self):
        flags=os.O_RDWR|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0)
        try:
            self.events_path=self.directory/'native-conflicts.jsonl';self.values_path=self.directory/'native-conflict-values.bin'
            events=os.open(self.events_path,flags,0o600);self.descriptors.append(events);private_file(self.events_path)
            values=os.open(self.values_path,flags,0o600);self.descriptors.append(values);private_file(self.values_path)
            response_read,self.response_write=os.pipe();self.descriptors.extend((response_read,self.response_write))
            self.native_descriptors=(events,response_read,values)
            self.thread=threading.Thread(target=self._run,daemon=True,name='sqlite-native-conflict-channel');self.thread.start();return self
        except BaseException:self.close();raise

    def _write_pending(self,event):
        sequence=event.get('sequence');challenge=event.get('challenge');kind=event.get('kind')
        if not isinstance(sequence,str) or not re.fullmatch('[1-9][0-9]{0,18}',sequence) or int(sequence)>9223372036854775807 or not isinstance(challenge,str) or not re.fullmatch('[0-9A-F]{32}',challenge) or type(kind) is not int or kind not in NAMES:
            raise SessionAPIError('Native conflict event identity is invalid')
        if self.pending is not None and self.pending.get('waiting'):raise SessionAPIError('A second native callback arrived before its decision acknowledgement')
        if kind!=5:
            event['incoming']=decode_page({'rows':[event['incoming']]})['rows'][0]
            if event.get('current_values') is not None:event['current_values']=[decode_cell(cell) for cell in event['current_values']]
        event['kind_name']=NAMES[kind];event['allowed_choices']=['omit','replace','abort'] if kind in {1,3} else ['omit','abort']
        with self.values_path.open('rb') as stream:
            size=os.fstat(stream.fileno()).st_size
            for value in event.get('byte_values',[]):
                offset=int(value['byte_offset']);length=int(value['byte_length'])
                if offset<0 or length<0 or offset+length>size:raise SessionAPIError('Native conflict byte range is incomplete')
                stream.seek(offset);hashed=hashlib.sha256();remaining=length
                while remaining:
                    if self.finished.is_set():raise SessionAPIError('Native conflict observer was stopped during byte verification')
                    block=stream.read(min(remaining,1048576))
                    if not block:raise SessionAPIError('Native conflict byte range ended early')
                    hashed.update(block);remaining-=len(block)
                value['sha256']=hashed.hexdigest()
        candidate=self.directory/'pending-conflict.incoming';target=self.directory/'pending-conflict.json'
        data=json.dumps(event,sort_keys=True,ensure_ascii=True,separators=(',',':')).encode('utf8')
        with candidate.open('xb') as stream:private_file(candidate);stream.write(data);stream.flush();os.fsync(stream.fileno())
        durable_replace(candidate,target)
        self.pending={'sequence':sequence,'challenge':challenge,'kind':NAMES[kind],'waiting':True,
            'event_file':'pending-conflict.json','event_sha256':hashlib.sha256(data).hexdigest(),'event_size':str(len(data)),
            'allowed_choices':event['allowed_choices'],'received_at':time.time()}
        self.publish(pending_conflict=self.pending,conflict_response=None)

    def _acknowledge(self,event):
        if self.pending is None or event.get('challenge')!=self.pending['challenge'] or event.get('sequence')!=self.pending['sequence'] or event['challenge'] not in self.sent:
            raise SessionAPIError('Native conflict acknowledgement does not match its admitted response')
        expected=self.sent[event['challenge']]
        if event.get('choice')!=expected['choice'] or event.get('remember_kind')!=expected['remember_kind']:raise SessionAPIError('Native conflict acknowledgement differs from its admitted choice')
        self.pending={**self.pending,'waiting':False,'native_decision_ack':event}
        self.publish(pending_conflict=self.pending,last_native_conflict_decision=event)

    def _respond(self):
        if self.finished.is_set() or self.pending is None or not self.pending.get('waiting'):return
        response=self.load().get('conflict_response')
        if not response or response.get('challenge')!=self.pending['challenge'] or response['challenge'] in self.sent:return
        choice=response.get('choice');remember=response.get('remember_kind')
        if choice not in self.pending['allowed_choices'] or type(remember) is not bool:raise SessionAPIError('The admitted native conflict response is invalid')
        frame=b'SR'+bytes.fromhex(response['challenge'])+bytes([CHOICES[choice],int(remember)])
        if os.write(self.response_write,frame)!=20:raise SessionAPIError('Native conflict response write is incomplete')
        self.sent[response['challenge']]={'choice':CHOICES[choice],'remember_kind':remember};self.publish(conflict_response={**response,'native_pipe_write_returned':True})

    def _run(self):
        buffer=b''
        try:
            with self.events_path.open('rb') as stream:
                while True:
                    block=stream.read(1048576)
                    if block:
                        buffer+=block
                        if len(buffer)>MAX_EVENT+1048576:raise SessionAPIError('Native conflict event exceeds its bound')
                        while b'\n' in buffer:
                            line,buffer=buffer.split(b'\n',1)
                            if len(line)>MAX_EVENT:raise SessionAPIError('Native conflict event exceeds its bound')
                            event=json.loads(line)
                            if event.get('event')=='conflict':self._write_pending(event)
                            elif event.get('event')=='decision_ack':self._acknowledge(event)
                            else:raise SessionAPIError('Native conflict event kind is unavailable')
                        continue
                    self._respond()
                    if self.finished.is_set():
                        if stream.tell()!=os.fstat(stream.fileno()).st_size:continue
                        if buffer:raise SessionAPIError('Native conflict event stream ended inside a record')
                        return
                    self.finished.wait(.02)
        except BaseException as error:
            self.failed.append(error)
            try:self.cancel_native()
            except BaseException as stop_error:self.failed.append(stop_error)

    def finish(self):
        self.finished.set()
        if self.thread is not None:self.thread.join(5)
        if self.thread is not None and self.thread.is_alive():raise SessionAPIError('Native conflict observer termination is unconfirmed')
        if self.failed:raise SessionAPIError('Native conflict observer failed; roll back the owned transaction') from self.failed[0]
        if self.pending is not None and self.pending.get('waiting'):raise SessionAPIError('Native conflict decision consumption is unconfirmed')

    def close(self):
        self.finished.set()
        if self.thread is not None:self.thread.join(5)
        if self.thread is not None and self.thread.is_alive():raise SessionAPIError('Native conflict observer still owns its I/O')
        while self.descriptors:os.close(self.descriptors.pop())

    def __exit__(self,*_args):self.close()
