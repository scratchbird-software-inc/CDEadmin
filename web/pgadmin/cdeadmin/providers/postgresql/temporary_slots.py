"""Native temporary slots bound to one independently owned PostgreSQL backend."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import uuid

from .large_object_files import cursor,identity


class TemporarySlotError(ValueError):
    pass


CHANGES={'peek_text','get_text','peek_binary','get_binary'}
OPERATIONS={'physical_create','logical_create','physical_copy','logical_copy','advance','drop',*CHANGES}
PROPERTIES="(pg_catalog.to_jsonb(s) || pg_catalog.jsonb_build_object('safe_wal_size',s.safe_wal_size::pg_catalog.text))"


def name(value):
    if not isinstance(value,str) or re.fullmatch(r'[a-z0-9_]{1,63}',value) is None:
        raise TemporarySlotError('Select an exact native slot name using lowercase ASCII letters, digits and underscores')
    return value


def options(operation,value):
    if not isinstance(operation,str) or operation not in OPERATIONS or not isinstance(value,dict):
        raise TemporarySlotError('Select a temporary native slot operation')
    if operation in CHANGES:
        from ...workspace.postgresql_slot_changes import options as change_options
        return change_options(value)
    allowed={'slot','timeout_seconds'}
    if operation=='physical_create':allowed.add('reserve_wal')
    if operation=='logical_create':allowed.update(('plugin','two_phase'))
    if operation.endswith('_copy'):allowed.add('source_slot')
    if operation=='logical_copy':allowed.add('plugin')
    if operation=='advance':allowed.add('upto_lsn')
    if set(value)-allowed:raise TemporarySlotError('Select exact temporary slot options')
    result={'slot':name(value.get('slot')),'timeout_seconds':value.get('timeout_seconds',30)}
    timeout=result['timeout_seconds']
    if timeout is not None and (type(timeout) is not int or not 1<=timeout<=2147483):
        raise TemporarySlotError('Select 1 to 2147483 seconds for a native slot command or no deadline')
    for key in ('reserve_wal','two_phase'):
        if key in allowed:
            result[key]=value.get(key,key=='reserve_wal')
            if type(result[key]) is not bool:raise TemporarySlotError('Native temporary slot switches require boolean values')
    if 'source_slot' in allowed:
        result['source_slot']=name(value.get('source_slot'))
        if result['source_slot']==result['slot']:raise TemporarySlotError('Select a distinct temporary destination slot')
    if 'plugin' in allowed:
        plugin=value.get('plugin','pgoutput' if operation=='logical_create' else '')
        try:encoded=plugin.encode('utf8') if isinstance(plugin,str) else None
        except UnicodeError:encoded=None
        if encoded is None or len(plugin)>63 or b'\0' in encoded or operation=='logical_create' and not encoded:
            raise TemporarySlotError('Select an exact native output plugin name without NUL or invalid Unicode')
        result['plugin']=plugin
    if operation=='advance':
        lsn=value.get('upto_lsn')
        if not isinstance(lsn,str) or re.fullmatch(r'[0-9A-Fa-f]{1,8}/[0-9A-Fa-f]{1,8}',lsn) is None or int(lsn.replace('/',''),16)==0:
            raise TemporarySlotError('Select an exact nonzero native WAL position')
        result['upto_lsn']=lsn.upper()
    return result


def statement(operation,selected):
    slot=selected['slot']
    prefix='SELECT slot_name::pg_catalog.text,lsn::pg_catalog.text FROM pg_catalog.'
    if operation=='physical_create':return prefix+'pg_create_physical_replication_slot(%s::pg_catalog.name,%s,true)',(slot,selected['reserve_wal'])
    if operation=='logical_create':return prefix+'pg_create_logical_replication_slot(%s::pg_catalog.name,%s::pg_catalog.name,true,%s,false)',(slot,selected['plugin'],selected['two_phase'])
    if operation=='physical_copy':return prefix+'pg_copy_physical_replication_slot(%s::pg_catalog.name,%s::pg_catalog.name,true)',(selected['source_slot'],slot)
    if operation=='logical_copy':
        return (prefix+'pg_copy_logical_replication_slot(%s::pg_catalog.name,%s::pg_catalog.name,true'+(',%s::pg_catalog.name)' if selected['plugin'] else ')'),
            (selected['source_slot'],slot,selected['plugin']) if selected['plugin'] else (selected['source_slot'],slot))
    if operation=='advance':return 'SELECT slot_name::pg_catalog.text,end_lsn::pg_catalog.text FROM pg_catalog.pg_replication_slot_advance(%s::pg_catalog.name,%s::pg_catalog.pg_lsn)',(slot,selected['upto_lsn'])
    if operation=='drop':return 'SELECT pg_catalog.pg_drop_replication_slot(%s::pg_catalog.name)',(slot,)
    raise TemporarySlotError('Temporary slot operation is unavailable')


class TemporarySlots:
    """The caller owns this connection lifetime and all durable acknowledgements."""
    def __init__(self,connection):
        self.connection=connection;self.resource_id=str(uuid.uuid4());self.usable=True;self.require_idle();self.source=identity(connection)
        with cursor(connection) as query:
            query.execute('SELECT pg_catalog.pg_backend_pid()::pg_catalog.text,'
                '(SELECT EXTRACT(EPOCH FROM backend_start)::pg_catalog.text FROM pg_catalog.pg_stat_activity WHERE pid=pg_catalog.pg_backend_pid())')
            self.backend_pid,self.backend_started_epoch=query.fetchone()
        self.adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        if self.inventory()['total']:raise TemporarySlotError('Use a new independently owned backend without existing temporary slots')

    def require_idle(self):
        from psycopg.pq import TransactionStatus
        if not self.usable or self.connection.closed or self.connection.broken or not self.connection.autocommit or self.connection.info.transaction_status!=TransactionStatus.IDLE:
            raise TemporarySlotError('Temporary slots require their healthy independently owned idle connection; reconnect never recreates slots')

    def observation(self,slot):
        with cursor(self.connection) as query:
            query.execute('SELECT '+PROPERTIES+'::pg_catalog.text FROM pg_catalog.pg_replication_slots s WHERE s.slot_name=%s',(name(slot),))
            row=query.fetchone()
        return json.loads(row[0]) if row else None

    def inventory(self,offset=0,limit=25):
        self.require_idle()
        if type(offset) is not int or not 0<=offset<=9223372036854775807 or type(limit) is not int or not 1<=limit<=100:
            raise TemporarySlotError('Select a bounded native temporary-slot catalog page')
        with cursor(self.connection) as query:
            query.execute('WITH native_slots AS MATERIALIZED (SELECT s.slot_name,'+PROPERTIES+' AS properties '
                'FROM pg_catalog.pg_replication_slots s WHERE s.temporary AND s.active_pid=%s::pg_catalog.int4) '
                'SELECT (SELECT pg_catalog.count(*) FROM native_slots),'
                "COALESCE((SELECT pg_catalog.jsonb_agg(properties ORDER BY slot_name) FROM "
                "(SELECT slot_name,properties FROM native_slots ORDER BY slot_name LIMIT %s OFFSET %s) visible),'[]'::pg_catalog.jsonb)::pg_catalog.text",
                (self.backend_pid,limit,offset))
            total,rows=query.fetchone()
        return {'slots':json.loads(rows),'total':int(total),'offset':offset,'limit':limit,'more':offset+limit<int(total)}

    def review(self,operation,value):
        self.require_idle();selected=options(operation,value)
        if identity(self.connection)!=self.source:raise TemporarySlotError('The retained native role or server identity changed')
        if selected.get('plugin'):
            with cursor(self.connection) as query:
                query.execute("SELECT pg_catalog.octet_length(pg_catalog.convert_to(%s::pg_catalog.text,pg_catalog.current_setting('server_encoding')::pg_catalog.name))",(selected['plugin'],))
                if query.fetchone()[0]>63:raise TemporarySlotError('The output plugin name exceeds 63 bytes in this database encoding')
        target=self.observation(selected['slot'])
        if operation in {'advance','drop',*CHANGES}:
            if target is None or target['temporary'] is not True or str(target['active_pid'])!=self.backend_pid:
                raise TemporarySlotError('Select a temporary slot owned by this retained backend')
            if operation in CHANGES and target['slot_type']!='logical':raise TemporarySlotError('Select an owned temporary logical slot for decoding')
        elif target is not None:raise TemporarySlotError('The requested temporary slot name is already in use')
        source=self.observation(selected['source_slot']) if 'source_slot' in selected else None
        if 'source_slot' in selected and (source is None or source['slot_type']!=('logical' if operation.startswith('logical') else 'physical')):
            raise TemporarySlotError('Select an existing native source slot of the matching type')
        return {'operation':operation,'options':selected,'resource_id':self.resource_id,'backend_pid':self.backend_pid,
            'source':self.source,'slot_before':target,'copy_source_before':source,'adapter_sha256':self.adapter_sha256}

    @contextmanager
    def command_context(self,reviewed,*,dispatching=None,finished=None):
        """One owned native dispatch, with observer termination before later SQL."""
        current=self.review(reviewed['operation'],reviewed['options'])
        if current!=reviewed:raise TemporarySlotError('The retained backend, role or reviewed slot state changed')
        selected=reviewed['options'];timeout=selected['timeout_seconds']
        with cursor(self.connection) as query:
            query.execute("SELECT pg_catalog.current_setting('statement_timeout')");prior=query.fetchone()[0]
        safe_cleanup=True
        try:
            with cursor(self.connection) as query:
                query.execute("SELECT pg_catalog.set_config('statement_timeout',%s,false)",('0' if timeout is None else str(timeout*1000),))
                safe_cleanup=False
                try:
                    if dispatching is not None:dispatching()
                    yield
                finally:
                    # The resource owner joins its cancellation observer here,
                    # before restoring settings or reading later liveness.
                    try:
                        if finished is not None:finished()
                        safe_cleanup=True
                    except BaseException:self.usable=False;raise
        finally:
            if safe_cleanup and not self.connection.closed and not self.connection.broken:
                try:
                    with cursor(self.connection) as query:query.execute("SELECT pg_catalog.set_config('statement_timeout',%s,false)",(prior,))
                except BaseException:self.usable=False;raise

    def command(self,reviewed,acknowledge,*,dispatching=None,finished=None):
        """One native dispatch. The durable owner must never replay a lost result."""
        with self.command_context(reviewed,dispatching=dispatching,finished=finished):
            with cursor(self.connection) as query:
                sql,bindings=statement(reviewed['operation'],reviewed['options'])
                query.execute(sql,bindings);returned=query.fetchone()
            acknowledgement={'resource_id':self.resource_id,'backend_pid':self.backend_pid,'operation':reviewed['operation'],
                'slot':reviewed['options']['slot'],'native_command_returned':True,
                'native_result':None if reviewed['operation']=='drop' else {'slot_name':returned[0],'lsn':returned[1]},
                'temporary':True,'connection_release_returned':False}
            acknowledge(acknowledgement)
        # This is a later liveness observation, distinct from native return.
        return {'acknowledgement':acknowledgement,'slot_after':self.observation(reviewed['options']['slot']),
            'owned_temporary_slots':self.inventory()}
