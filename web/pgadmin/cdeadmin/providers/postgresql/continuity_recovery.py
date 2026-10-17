"""Independent, offline recovery of a plain PostgreSQL physical backup.

The original backup is never a server data directory. Only the private copy is
opened by a supervised standalone backend, without a listener or source route.
"""
import csv
import json
import os
from pathlib import Path
import re
import stat

from ...operations.fileio import private_directory, private_file
from .continuity import ContinuityError, backup_options


def recovery_options(value):
    defaults = {'database':'postgres', 'checks':[], 'timeout_seconds':3600,
                'target':None, 'wal_archive':None}
    if not isinstance(value,dict) or set(value)-defaults.keys():
        raise ContinuityError('Invalid native recovery drill options')
    result = {**defaults,**value}
    target = result['target']
    if target is not None:
        from .continuity_wal import ARCHIVE_NAME
        if not isinstance(target,dict) or set(target)-{'kind','value','inclusive','timeline'} or target.get('kind') not in {'time','xid','lsn','name','immediate'}:
            raise ContinuityError('Select one native recovery target')
        target = {'inclusive':True, 'timeline':'current', **target}
        if type(target['inclusive']) is not bool or not isinstance(target['timeline'],str) or not re.fullmatch(r'current|latest|[1-9][0-9]{0,9}',target['timeline']):
            raise ContinuityError('Invalid native recovery inclusion or timeline')
        value = target.get('value')
        if target['kind']=='immediate':
            if value is not None: raise ContinuityError('Immediate recovery has no target value')
        elif not isinstance(value,str) or not value or '\x00' in value or len(value.encode('utf8'))>1024:
            raise ContinuityError('Recovery targets require bounded exact native text')
        elif target['kind']=='xid' and (not re.fullmatch(r'[0-9]{1,10}',value) or not 0<int(value)<=4294967295):
            raise ContinuityError('Recovery XIDs require exact native uint32 decimal text')
        elif target['kind']=='lsn' and not re.fullmatch(r'[0-9A-Fa-f]{1,8}/[0-9A-Fa-f]{1,8}',value):
            raise ContinuityError('Recovery LSN requires two native hexadecimal halves')
        elif target['kind']=='name' and len(value.encode('utf8'))>=64:
            raise ContinuityError('Native restore-point names require fewer than 64 UTF8 bytes')
        if not isinstance(result['wal_archive'],str) or ARCHIVE_NAME.fullmatch(result['wal_archive']) is None:
            raise ContinuityError('Point-in-time recovery requires a selected native WAL archive')
        result['target'] = target
    elif result['wal_archive'] is not None:
        raise ContinuityError('WAL archive selection requires a native recovery target')
    backup_options({'timeout_seconds':result['timeout_seconds']})
    def identifier(name):
        # Native byte length depends on the recovered database encoding. Exact
        # catalog binding below refuses names that do not exist after parsing.
        return isinstance(name,str) and name and '\x00' not in name and len(name)<=63
    if not identifier(result['database']):raise ContinuityError('Select an exact native recovery database name')
    if not isinstance(result['checks'],list) or len(result['checks'])>64:
        raise ContinuityError('Select at most 64 native heap table checks')
    seen=set()
    for item in result['checks']:
        if not isinstance(item,dict) or set(item)-{'schema','table','expected_rows'} or not all(identifier(item.get(key)) for key in ('schema','table')):
            raise ContinuityError('Recovery checks require exact native schema and table names')
        key=(item['schema'],item['table'])
        if key in seen:raise ContinuityError('Duplicate native recovery table check')
        seen.add(key)
        count=item.get('expected_rows')
        if count is not None and (not isinstance(count,str) or not re.fullmatch(r'0|[1-9][0-9]{0,18}',count) or int(count)>9223372036854775807):
            raise ContinuityError('Expected row counts require exact nonnegative int64 decimal text')
    return {**result,'format':'plain','wal_method':'stream','sync':True,'manifest_checksums':'SHA256'}


def independent_copy(source, destination, tablespaces, *, progress, cancel_signal):
    """Copy bytes, retaining only independently remapped managed tablespaces."""
    source,destination=Path(source),Path(destination)
    if (source/'postmaster.pid').exists():raise ContinuityError('Recovery input contains a live-cluster lock file')
    allowed={str(item['oid']) for item in tablespaces if item.get('location')}
    total=0
    def tick():
        progress({'phase':'copying_recovery_artifact','copied_bytes':total})
        if cancel_signal.is_set():raise ContinuityError('Native recovery copy was cancelled')
    def copy_tree(original,target,relative=Path()):
        nonlocal total
        target.mkdir(mode=0o700);private_directory(target)
        with os.scandir(original) as entries:
            for entry in entries:
                tick()
                src,dst=Path(entry.path),target/entry.name
                rel=relative/entry.name
                info=entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
                    if len(rel.parts)!=2 or rel.parts[0]!='pg_tblspc' or rel.name not in allowed:
                        raise ContinuityError('Recovery input contains an unmanaged link or reparse point')
                    resolved=src.resolve(strict=True)
                    expected=source.parent/'tablespaces'/rel.name
                    if resolved!=expected.resolve(strict=True) or not resolved.is_relative_to(source.parent.resolve(strict=True)):
                        raise ContinuityError('Recovery tablespace points outside its managed artifact')
                    mapped=destination.parent/'tablespaces'/rel.name
                    mapped.parent.mkdir(mode=0o700,exist_ok=True);private_directory(mapped.parent)
                    copy_tree(resolved,mapped,Path('tablespaces')/rel.name)
                    dst.symlink_to(mapped,target_is_directory=True)
                elif stat.S_ISDIR(info.st_mode):copy_tree(src,dst,rel)
                elif stat.S_ISREG(info.st_mode):
                    with src.open('rb') as incoming,dst.open('xb') as outgoing:
                        private_file(dst)
                        while block:=incoming.read(1024*1024):
                            outgoing.write(block);total+=len(block);tick()
                        outgoing.flush();os.fsync(outgoing.fileno())
                else:raise ContinuityError('Recovery input contains a nonregular native file')
    tick();copy_tree(source,destination);tick()
    return {'independent_byte_copy':True,'copied_bytes':total,'tablespace_links_remapped':True}


def literal(value):
    return "E'"+value.replace('\\','\\\\').replace("'","''").replace('\r','\\r').replace('\n','\\n')+"'"


def identifier(value):
    # Standalone -j uses two newlines as a command delimiter. Escape every
    # code point so even quoted identifiers containing newlines stay exact.
    return 'U&"'+''.join('\\'+format(ord(char),'04X') if ord(char)<=0xffff else '\\+'+format(ord(char),'06X') for char in value)+'"'


def unicode_literal(value):
    # Standalone SQL input is not a libpq text protocol. ASCII Unicode escapes
    # preserve names when the recovered database encoding is not UTF8.
    return "U&'"+''.join('\\'+format(ord(char),'04X') if ord(char)<=0xffff else '\\+'+format(ord(char),'06X') for char in value)+"'"


def recovery_command(directory, options, token):
    directory=Path(directory);clone=directory/'recovered-clone'
    # Verified backup configuration is evidence, not an execution policy.
    # These edits apply to the independent clone only. Never load its includes,
    # auto-conf credentials, preload libraries, archive commands or source route.
    for name in ('standby.signal','recovery.signal','tablespace_map'):
        (clone/name).unlink(missing_ok=True)
    auto=clone/'postgresql.auto.conf'
    auto.write_bytes(b'');private_file(auto)
    config=directory/'recovery.conf'
    configuration="listen_addresses = ''\nshared_preload_libraries = ''\nsession_preload_libraries = ''\nlocal_preload_libraries = ''\narchive_mode = off\narchive_command = ''\narchive_library = ''\nrestore_command = ''\nrecovery_end_command = ''\nrecovery_min_apply_delay = 0\nhot_standby = off\nprimary_conninfo = ''\nprimary_slot_name = ''\nssl = off\n"
    target = options.get('target')
    if target is not None:
        if target['kind']=='time':
            # PostgreSQL checks recovery timestamps while reading GUCs, before
            # its default timezone abbreviation table is otherwise initialized.
            configuration += "timezone_abbreviations = 'Default'\n"
        # All reviewed archive bytes are staged in the clone's own pg_wal.
        # No caller-supplied archive command or source connection is executed.
        configuration += "restore_command = '"+('cmd /c exit /b 1' if os.name=='nt' else 'false')+"'\nrecovery_target_action = 'promote'\n"
        def setting(value): return "'"+str(value).replace('\\','\\\\').replace("'","''")+"'"
        key = 'recovery_target' if target['kind']=='immediate' else 'recovery_target_'+target['kind']
        configuration += key+' = '+setting('immediate' if target['kind']=='immediate' else target['value'])+'\n'
        configuration += 'recovery_target_inclusive = '+('on' if target['inclusive'] else 'off')+'\n'
        configuration += 'recovery_target_timeline = '+setting(target['timeline'])+'\n'
        signal = clone/'recovery.signal'; signal.write_bytes(b''); private_file(signal)
    config.write_text(configuration,encoding='utf8')
    private_file(config)
    output=directory/'recovery-result.csv'
    if output.exists():raise ContinuityError('A native recovery result already exists; automatic replay is refused')
    assertions=[];checks=[]
    for item in options['checks']:
        schema,table=item['schema'],item['table']
        assertions.append("IF NOT EXISTS (SELECT FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN pg_catalog.pg_am a ON a.oid=c.relam WHERE n.nspname="+unicode_literal(schema)+" AND c.relname="+unicode_literal(table)+" AND c.relkind IN ('r','m') AND a.amname='heap') THEN RAISE EXCEPTION 'Recovery check requires a native heap relation'; END IF;")
        checks.append("pg_catalog.jsonb_build_object('schema',"+unicode_literal(schema)+",'table',"+unicode_literal(table)+",'rows',(SELECT count(*)::text FROM "+identifier(schema)+'.'+identifier(table)+'))')
    validate='DO '+literal('BEGIN '+''.join(assertions)+' END;')+';' if assertions else ''
    observed_target=''
    if target is not None:
        observed_target=",'native_target',pg_catalog.jsonb_build_object('value',pg_catalog.current_setting("+literal(key)+"),'timeline',pg_catalog.current_setting('recovery_target_timeline'),'inclusive',pg_catalog.current_setting('recovery_target_inclusive'),'action',pg_catalog.current_setting('recovery_target_action'))"
    query="SELECT pg_catalog.jsonb_build_object('token',"+literal(token)+",'system_identifier',(SELECT system_identifier::text FROM pg_catalog.pg_control_system()),'database',pg_catalog.current_database(),'server_version',current_setting('server_version_num')::int,'in_recovery',pg_catalog.pg_is_in_recovery()"+observed_target+",'checks',pg_catalog.jsonb_build_array("+','.join(checks)+'))'
    sql="BEGIN READ ONLY;SET LOCAL search_path=pg_catalog;SET LOCAL row_security=off;"+validate+'COPY ('+query+') TO '+literal(str(output))+" WITH (FORMAT csv, ENCODING 'UTF8');COMMIT;\n\n"
    return ['--single','-j','-D',str(clone),'-c','config_file='+str(config),'--',options['database']],sql.encode('utf8'),output


def read_result(path, options, token, system_identifier):
    path=Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size>1024*1024:
        raise ContinuityError('Native recovery did not produce a bounded SQL result')
    private_file(path)
    with path.open(encoding='utf8',newline='') as stream:
        rows=list(csv.reader(stream))
    if len(rows)!=1 or len(rows[0])!=1:raise ContinuityError('Invalid native recovery SQL result')
    try:result=json.loads(rows[0][0])
    except (ValueError,TypeError):raise ContinuityError('Invalid native recovery SQL result') from None
    if not isinstance(result,dict) or result.get('token')!=token or result.get('system_identifier')!=system_identifier or result.get('database')!=options['database'] or result.get('in_recovery') is not False or type(result.get('server_version')) is not int or not 180000<=result['server_version']<190000:
        raise ContinuityError('Native recovery identity or completion could not be established')
    if not isinstance(result.get('checks'),list) or len(result['checks'])!=len(options['checks']):
        raise ContinuityError('Native recovery table checks are incomplete')
    target=options.get('target')
    if target is not None and result.get('native_target')!={'value':'immediate' if target['kind']=='immediate' else target['value'],
            'timeline':target['timeline'],'inclusive':'on' if target['inclusive'] else 'off','action':'promote'}:
        raise ContinuityError('Native recovery target observation differs from the reviewed target')
    for actual,expected in zip(result['checks'],options['checks']):
        if not isinstance(actual,dict) or any(actual.get(key)!=expected[key] for key in ('schema','table')) or not isinstance(actual.get('rows'),str) or not re.fullmatch(r'0|[1-9][0-9]{0,18}',actual['rows']):
            raise ContinuityError('Invalid native recovery table result')
        if expected.get('expected_rows') is not None and expected['expected_rows']!=actual['rows']:
            raise ContinuityError('Native recovery row count differs from the reviewed expectation')
    result.pop('token')
    return {**result,'network_listener_started':False,'source_connection_used':False,
            'scope':'native WAL recovery, cluster identity and selected heap row counts',
            'production_restore':False,'point_in_time_recovery':options.get('target') is not None,
            'recovery_target':options.get('target')}
