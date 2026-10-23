"""Complete native row multisets at admitted MySQL snapshot boundaries."""
import hashlib
import heapq
import json
from pathlib import Path
import struct
import re

from . import mysql_content_search as catalog
from .mysql_catalog import identifier

Error = catalog.SearchError
LOCAL_ENGINES = {'InnoDB', 'MyISAM', 'MEMORY', 'CSV', 'ARCHIVE', 'MRG_MYISAM', 'BLACKHOLE'}


class Observer:
    query = catalog.Observer.query

    def __init__(self, connection, dispose, seconds):
        self.connection, self.dispose = connection, dispose
        self.native_interface=type(connection).__name__
        try:
            connection.set_charset_collation(charset='utf8mb4', collation='utf8mb4_0900_ai_ci')
            self.query("SET SESSION time_zone='+00:00',sql_mode='',sql_quote_show_create=1,"
                'show_gipk_in_create_table_and_information_schema=ON,lock_wait_timeout=5,max_execution_time='+str(seconds*1000))
            self.identity = self.query('SELECT @@server_uuid AS server_uuid,VERSION() AS version,CURRENT_USER() AS account,'
                'CURRENT_ROLE() AS active_role,CONNECTION_ID() AS connection_id,PS_CURRENT_THREAD_ID() AS thread_id')[0]
            if self.identity['version'].split('-')[0] != '9.7.0':raise Error('Data drift requires native MySQL 9.7.0')
        except BaseException:
            self.close();raise

    def close(self):
        connection, self.connection = self.connection, None
        if connection is not None:self.dispose(connection)


def options(value):
    if not isinstance(value,dict) or set(value)!={'consistency','replica','channel','seconds','disk_mib','examples'}:
        raise Error('Select explicit snapshot, replica and resource limits')
    if value['consistency'] not in {'innodb_snapshot','locked_scan'} or type(value['replica']) is not bool:
        raise Error('Select a native snapshot or server-locked scan')
    if not isinstance(value['channel'],str) or len(value['channel'])>64 or '\0' in value['channel']:
        raise Error('Select the exact native replica channel')
    for key,low,high in [('seconds',1,86400),('disk_mib',1,4096),('examples',0,200)]:
        if type(value[key]) is not int or not low<=value[key]<=high:raise Error('Data drift '+key+' is outside its admitted bound')
    return dict(value)


def selections(value):
    if not isinstance(value,list) or not 1<=len(value)<=64:raise Error('Select 1–64 complete native table pairs')
    result=[];left=set();right=set()
    for item in value:
        if not isinstance(item,dict) or set(item)!={'source_table','target_table','source_fingerprint','target_fingerprint'}:
            raise Error('Select observed native table identities for both sides')
        for field in ('source_table','target_table'):catalog.name(item[field])
        for field in ('source_fingerprint','target_fingerprint'):
            if not isinstance(item[field],str) or len(item[field])!=64 or any(c not in '0123456789abcdef' for c in item[field]):
                raise Error('Rediscover both native table structures')
        if item['source_table'] in left or item['target_table'] in right:raise Error('Select distinct table pairs')
        left.add(item['source_table']);right.add(item['target_table']);result.append(dict(item))
    return result


def shape(source):
    return [{k:v for k,v in column.items() if k not in {'PRIVILEGES'}} for column in source['columns']]


def describe(observer,schema,table):
    from ...workspace.mysql_table_clauses import table_layout
    source=catalog.describe(observer,schema,table)
    rows=observer.query('SHOW CREATE TABLE '+identifier(schema)+'.'+identifier(table),limit=2)
    definition=next(v for k,v in rows[0].items() if k.lower()=='create table')
    if len(definition.encode('utf8'))>4*1024*1024:raise Error('Native table definition exceeds the comparison metadata bound')
    clauses=table_layout(definition,'')['clauses']
    names=[match.group(1).replace('``','`') for clause in clauses if (match:=re.match(r'^\s*`((?:``|[^`])+)`\s',clause))]
    if names!=[c['COLUMN_NAME'] for c in source['columns']]:raise Error('Native metadata does not expose the complete logical column scope')
    return source


def position(observer):
    value=observer.query('SELECT @@GLOBAL.gtid_executed AS gtid_executed,@@GLOBAL.gtid_mode AS gtid_mode,'
        '@@GLOBAL.log_bin AS log_bin,@@GLOBAL.lower_case_table_names AS lower_case_table_names')[0]
    # SHOW BINARY LOG STATUS is unavailable when native binary logging is off.
    logs=observer.query('SHOW BINARY LOG STATUS') if value['log_bin'] else []
    return {**{k:catalog.display(v) for k,v in value.items()},'binary_log_status':[
        {k:catalog.display(v) for k,v in row.items()} for row in logs]}


def projection(source):
    expressions=[]
    for column in source['columns']:
        field=identifier(column['COLUMN_NAME']);kind=column['DATA_TYPE']
        # Binary prepared results preserve IEEE values; native text rendering
        # can round distinct floating-point values to the same string.
        value=field if kind in {'float','double'} else 'CAST('+field+' AS UNSIGNED)' if kind in {'enum','set'} else 'SHA2(CAST('+field+' AS BINARY),256)'
        expressions.append(value)
    for key in source['key']:
        column=next(c for c in source['columns'] if c['COLUMN_NAME']==key);field=identifier(key)
        expressions.append(field if column['DATA_TYPE'] in {'float','double'} else 'HEX(CAST('+field+' AS BINARY))')
    return expressions


def row_record(row, source):
    count=len(source['columns']);digest=hashlib.sha256(b'cdeadmin-mysql-row-sha256-v1\0')
    if len(row)!=count+len(source['key']):raise Error('Native projection column coverage changed')
    for column,value in zip(source['columns'],row[:count]):
        if value is None:digest.update(b'N');continue
        kind=column['DATA_TYPE']
        if kind in {'float','double'}:encoded=struct.pack('!d',value);tag=b'F'
        elif kind in {'enum','set'}:encoded=str(value).encode('ascii');tag=b'I'
        else:
            encoded=value.encode('ascii') if isinstance(value,str) else bytes(value);tag=b'H'
            if len(encoded)!=64 or any(c not in b'0123456789abcdefABCDEF' for c in encoded):raise Error('Native SHA256 projection is unavailable')
        digest.update(tag+struct.pack('!I',len(encoded))+encoded)
    keys=[]
    for name,value in zip(source['key'],row[count:]):
        text=value.decode('ascii') if isinstance(value,(bytes,bytearray)) else repr(value) if isinstance(value,float) else str(value)
        keys.append({'column':name,'value':text[:512],'truncated':len(text)>512,
            'encoding':'native IEEE value' if isinstance(value,float) else 'hex of native key representation'})
    payload=json.dumps(keys,separators=(',',':'),ensure_ascii=True).encode('ascii')
    return digest.digest(),payload


class Runs:
    """Bounded external sort; retain multiplicity and private key examples."""
    def __init__(self, directory, reserve):
        self.directory,self.reserve=Path(directory),reserve
        self.directory.mkdir(mode=0o700)
        self.buffer=[];self.size=0;self.paths=[];self.rows=0;self.sequence=0

    def add(self, record):
        self.buffer.append(record);self.size+=len(record[1])+96;self.rows+=1
        if self.size>=4*1024*1024:self.flush()

    def flush(self):
        if not self.buffer:return
        path=self.directory/('run-'+str(self.sequence));self.sequence+=1;self.buffer.sort()
        with path.open('xb') as output:
            path.chmod(0o600)
            for digest,payload in self.buffer:
                record=digest+struct.pack('!I',len(payload))+payload
                self.reserve(len(record));output.write(record)
        self.paths.append(path);self.buffer=[];self.size=0
        if len(self.paths)>=64:
            inputs=self.paths[:32];merged=self.directory/('merged-'+str(self.sequence));self.sequence+=1
            with merged.open('xb') as output:
                merged.chmod(0o600)
                for digest,payload in heapq.merge(*(self.read(p) for p in inputs)):
                    record=digest+struct.pack('!I',len(payload))+payload
                    self.reserve(len(record));output.write(record)
            for path in inputs:
                size=path.stat().st_size;path.unlink();self.reserve(-size)
            self.paths=[merged,*self.paths[32:]]

    @staticmethod
    def read(path):
        with path.open('rb') as source:
            while digest:=source.read(32):
                if len(digest)!=32:raise Error('Private comparison run is incomplete')
                size=source.read(4)
                if len(size)!=4:raise Error('Private comparison record is incomplete')
                length=struct.unpack('!I',size)[0]
                if length>65536:raise Error('Private comparison key exceeds its bound')
                payload=source.read(length)
                if len(payload)!=length:raise Error('Private comparison key is incomplete')
                yield digest,payload

    def ordered(self):
        self.flush()
        # Compaction keeps the final merge below 64 open files per side.
        return heapq.merge(*(self.read(p) for p in self.paths))


def compare(left,right,limit,checkpoint):
    streams=[iter(left.ordered()),iter(right.ordered())];current=[next(s,None) for s in streams]
    counts=[0,0];examples=[];summaries=[hashlib.sha256(),hashlib.sha256()]
    while any(item is not None for item in current):
        checkpoint()
        if current[0] is not None and current[1] is not None and current[0][0]==current[1][0]:take=(0,1)
        else:take=(0,) if current[1] is None or (current[0] is not None and current[0][0]<current[1][0]) else (1,)
        for side in take:
            record=current[side];summaries[side].update(record[0])
            if len(take)==1:
                counts[side]+=1
                if len(examples)<limit:examples.append({'side':'source' if side==0 else 'target','row_sha256':record[0].hex(),'key':json.loads(record[1])})
            current[side]=next(streams[side],None)
    return {'state':'matched' if counts==[0,0] else 'different','source_only_rows':str(counts[0]),'target_only_rows':str(counts[1]),
        'examples':examples,'examples_truncated':sum(counts)>len(examples),'source_rows':str(left.rows),'target_rows':str(right.rows),
        'source_multiset_sha256':summaries[0].hexdigest(),'target_multiset_sha256':summaries[1].hexdigest(),
        'basis':'Complete SHA256 row multisets with duplicate multiplicity; cryptographic digest comparison, not physical byte equality'}


def scan(observer,schema,source,runs,checkpoint,progress):
    qualified=identifier(schema)+'.'+identifier(source['table_name'])
    sql='SELECT '+','.join(projection(source))+' FROM '+qualified
    if source['key']:sql+=' ORDER BY '+','.join(identifier(k) for k in source['key'])
    cursor=observer.connection.cursor(prepared=True)
    try:
        cursor.execute(sql)
        while True:
            checkpoint();batch=cursor.fetchmany(512)
            if not batch:break
            for row in batch:runs.add(row_record(row,source))
            progress(runs.rows)
        if cursor.warning_count:raise Error('Native comparison produced warnings; table coverage is incomplete')
        runs.flush()
    finally:cursor.close()
