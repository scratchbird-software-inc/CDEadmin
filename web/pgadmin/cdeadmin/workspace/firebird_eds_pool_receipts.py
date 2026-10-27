"""Owner/registration-scoped EDS observations that never authorize replay."""
from contextlib import contextmanager
from copy import deepcopy
import os
from pathlib import Path
import threading
import time
import uuid

from ..operations.fileio import exclusive_file_lock
from ..operations.store import JsonOperationStore


class EDSPoolReceipts:
    def __init__(self,path,owner,endpoint,target):
        if type(owner) is not int or owner<=0 or not isinstance(target,str) or not target:
            raise ValueError('Select an owned Firebird EDS receipt scope')
        self.path=Path(path);self.binding=[owner,endpoint,target];self.lock=threading.RLock()

    @contextmanager
    def store(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.lock:
            descriptor=os.open(str(self.path)+'.lock',os.O_RDWR|os.O_CREAT,0o600)
            try:
                with exclusive_file_lock(descriptor):yield JsonOperationStore(self.path)
            finally:os.close(descriptor)

    def record(self,state,key):
        try:valid=isinstance(key,str) and str(uuid.UUID(key))==key
        except ValueError:valid=False
        value=state.get('firebird_eds_pool',{}).get(key) if valid else None
        if value is None or value.get('binding')!=self.binding:
            raise ValueError('Native EDS receipt is unavailable for this owner, endpoint and registration')
        return value

    @staticmethod
    def public(value):
        return {**deepcopy({key:item for key,item in value.items() if key!='binding'}),
            'automatic_retry':False,'live_native_state_observed':False,'transaction_finality_inferred':False}

    def create(self,record):
        with self.store() as store:
            def save(state):
                records=state.setdefault('firebird_eds_pool',{})
                if record['review_id'] in records:raise ValueError('Native EDS review identity already exists')
                for key in list(records):
                    if records[key]['state']=='reviewed' and records[key]['expires_at']<time.time():records.pop(key)
                if len(records)>=1000:raise ValueError('Native EDS receipt capacity reached; explicit retention review is required')
                records[record['review_id']]={**deepcopy(record),'binding':self.binding}
            store.change(save)

    def get(self,key):
        with self.store() as store:return self.public(self.record(store.read(),key))

    def update(self,key,**changes):
        if set(changes)&{'binding','review_id','session_id','review_digest','source','draft','adapter_identity'}:
            raise ValueError('Native EDS review identities cannot change after capture')
        with self.store() as store:
            def save(state):
                value=self.record(state,key);value.update(deepcopy(changes),recorded_at=time.time())
                return self.public(value)
            return store.change(save)

    def claim(self,key,digest):
        with self.store() as store:
            def save(state):
                value=self.record(state,key)
                if digest!=value['review_digest']:raise ValueError('Native EDS review fingerprint changed')
                if value['state']!='reviewed':return False
                if value['expires_at']<time.time():raise ValueError('Native EDS review expired')
                value.update(state='unknown_outcome',native_dispatch_admitted=True,dispatch_admitted_at=time.time())
                return True
            return store.change(save)

    def recent(self,offset=0,limit=25):
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:
            raise ValueError('Select a bounded native EDS receipt page')
        with self.store() as store:
            records=sorted((self.public(value) for value in store.read().get('firebird_eds_pool',{}).values()
                if value.get('binding')==self.binding),key=lambda value:(value['created_at'],value['review_id']),reverse=True)
        return {'receipts':records[offset:offset+limit],'offset':offset,'limit':limit,'total':len(records),
            'more':offset+limit<len(records),'automatic_retry':False,'live_native_state_observed':False}

    def remove(self,key,digest,confirmed):
        with self.store() as store:
            def save(state):
                value=self.record(state,key)
                if confirmed is not True or digest!=value['review_digest']:
                    raise ValueError('Confirm removal of this retained EDS receipt')
                if value['native_dispatch_admitted'] and value.get('last_native_phase')!='session_release':
                    raise ValueError('Retain unresolved EDS dispatch evidence; native completion is unconfirmed')
                del state['firebird_eds_pool'][key]
                return {'removed_review_id':key,'native_operation_requested':False,'automatic_retry':False}
            return store.change(save)


def for_workspace(service,server,target):
    endpoint=server.endpoint_profile
    if (endpoint is None or (endpoint.profile_id,endpoint.provider_id) not in {
            ('firebird-native','org.cdeadmin.firebird'),
            ('firebird-embedded','org.cdeadmin.firebird.embedded')}):
        raise ValueError('Select a native Firebird EDS registration')
    if not isinstance(target,str) or not target:raise ValueError('Select one registered Firebird database target')
    service.endpoint_service._owned_database_target(endpoint,target)
    context=service.endpoint_service._context(endpoint,())
    admitted=service.endpoint_service.provider_registry.admitted_permissions(context)
    if 'data_read' not in admitted:raise ValueError('Native Firebird EDS receipt permission is unavailable')
    store=getattr(service.operation_bus,'store',None)
    if not isinstance(store,JsonOperationStore):raise ValueError('Native EDS operations require durable application storage')
    return EDSPoolReceipts(str(store.path)+'.firebird-eds-pool',service._principal_id(server),endpoint.id,target)
