"""Observed FTS settings and their native maintenance commands on SQLite3.53."""
import sqlite3
import struct

KEYS={'pgsz','hashsize','automerge','usermerge','crisismerge','deletemerge','rank','secure-delete','insttoken'}


def quote(value):return '"'+value.replace('"','""')+'"'


def capture(connection,schema,name,module):
    module=module.lower()
    try:
        if module=='fts5':
            rows=list(connection.execute('SELECT k,v FROM '+quote(schema)+'.'+quote(name+'_config')+' ORDER BY k'))
            version=next((value for key,value in rows if key=='version'),None)
            commands=[list(row) for row in rows if row[0]!='version']
        elif module in {'fts3','fts4'}:
            present=connection.execute('SELECT 1 FROM '+quote(schema)+'.sqlite_schema WHERE type=\'table\' AND name=?',(name+'_stat',)).fetchone()
            # FTS_STAT_AUTOINCRMERGE=2 in the exact3.53 native release source.
            rows=list(connection.execute('SELECT value FROM '+quote(schema)+'.'+quote(name+'_stat')+' WHERE id=2')) if present else []
            version=None;commands=[['automerge',rows[0][0]]] if rows else []
        else:raise ValueError('Select a native FTS module')
        restorable=all(isinstance(key,str) and key in (KEYS if module=='fts5' else {'automerge'}) and
            type(value) in {int,str} for key,value in commands) and (module!='fts5' or version in {4,5})
        if not restorable:
            def encoded(value):
                if isinstance(value,bytes):return {'type':'blob','hex':value.hex()}
                if isinstance(value,float):return {'type':'float64','network_hex':struct.pack('>d',value).hex()}
                return value
            return {'available':True,'module':module,'restorable':False,'observed_settings':[[key,encoded(value)] for key,value in commands],
                'native_format_version':version,'reason':'Native FTS settings cannot be restored through the qualified maintenance commands'}
        return {'available':True,'module':module,'restorable':True,'native_format_version':version,'commands':commands}
    except sqlite3.Error as error:
        return {'available':False,'module':module,'restorable':False,'native_error':getattr(error,'sqlite_errorname','SQLITE_ERROR')}


def identity(value):
    if value is None:return None
    if not isinstance(value,dict):raise ValueError('Native FTS configuration must be an observed object')
    return {key:item for key,item in value.items() if key!='native_format_version'}


def statements(name,configuration):
    if not isinstance(configuration,dict) or configuration.get('available') is not True or configuration.get('restorable') is not True:
        raise ValueError('Capture complete restorable native FTS configuration first')
    module=configuration.get('module');commands=configuration.get('commands')
    if (set(configuration)-{'available','module','restorable','native_format_version','commands'} or
            module not in {'fts3','fts4','fts5'} or not isinstance(commands,list) or len(commands)>len(KEYS) or
            (configuration.get('native_format_version') not in {4,5} if module=='fts5' else configuration.get('native_format_version') is not None)):
        raise ValueError('Native FTS configuration is invalid')
    def literal(value):
        if type(value) is int:return str(value)
        if isinstance(value,str):return "CAST(X'"+value.encode('utf8').hex()+"' AS TEXT)"
        raise ValueError('Native FTS settings require exact integer or text values')
    result=[];seen=set()
    for item in commands:
        if not isinstance(item,list) or len(item)!=2:raise ValueError('Invalid native FTS setting')
        key,value=item
        if not isinstance(key,str) or key not in (KEYS if module=='fts5' else {'automerge'}) or key in seen:
            raise ValueError('Invalid or repeated native FTS setting')
        seen.add(key)
        if module=='fts5':result.append('INSERT INTO "main".'+quote(name)+'('+quote(name)+',rank) VALUES('+literal(key)+','+literal(value)+')')
        else:
            if type(value) is not int or not 0<=value<=2147483647:raise ValueError('Native FTS merge setting is invalid')
            result.append('INSERT INTO "main".'+quote(name)+'('+quote(name)+') VALUES('+literal('automerge='+str(value))+')')
    return result


def validate(configuration):
    """Native setters must reproduce the exact proposed catalog values."""
    name='__scratchrobin_fts_configuration_probe'
    commands=statements(name,configuration);probe=sqlite3.connect(':memory:')
    try:
        probe.execute('CREATE VIRTUAL TABLE '+quote(name)+' USING '+quote(configuration['module'])+'(body)')
        for source in commands:probe.execute(source)
        if identity(capture(probe,'main',name,configuration['module']))!=identity(configuration):
            raise ValueError('Desired FTS settings differ from the native normalized catalog values')
    except sqlite3.Error as error:
        raise ValueError('Native FTS configuration refused ('+str(getattr(error,'sqlite_errorname','SQLITE_ERROR'))+')') from None
    finally:probe.close()
