"""Native MySQL Server table options; no cross-engine substitutions."""
from collections.abc import Mapping
import json
import re

from ...sdk import RelationalClientError
from .mysql_catalog import identifier

TEXT={'engine':'ENGINE','comment':'COMMENT','compression':'COMPRESSION','encryption':'ENCRYPTION',
    'character_set':'DEFAULT CHARACTER SET','collation':'DEFAULT COLLATE',
    'data_directory':'DATA DIRECTORY','index_directory':'INDEX DIRECTORY'}
NUMBERS={'auto_increment','max_rows','min_rows','avg_row_length','stats_sample_pages','checksum','table_checksum',
    'delay_key_write','key_block_size','autoextend_size'}
CHOICES={'row_format':{'DEFAULT','DYNAMIC','FIXED','COMPRESSED','REDUNDANT','COMPACT'},
    'insert_method':{'NO','FIRST','LAST'},'pack_keys':{'DEFAULT','0','1'},
    'stats_auto_recalc':{'DEFAULT','0','1'},'stats_persistent':{'DEFAULT','0','1'}}
JSON_OPTIONS={'engine_attribute','secondary_engine_attribute'}
KEYS=set(TEXT)|NUMBERS|set(CHOICES)|JSON_OPTIONS|{'secondary_engine','tablespace','union'}


def selected(options):
    value=options.get('mysql_table_options',{})
    if not isinstance(value,Mapping):raise RelationalClientError('Native MySQL table options require an object')
    value=dict(value)
    for key in KEYS&set(options):
        if key in value and value[key]!=options[key]:raise RelationalClientError('Conflicting native MySQL '+key+' selections')
        value[key]=options[key]
    return value


def compile_options(value,connection=None):
    if not isinstance(value,Mapping) or set(value)-KEYS:
        raise RelationalClientError('Select supported native MySQL table options by their exact names')
    clauses=[];parameters=[]
    for key,item in value.items():
        keyword=TEXT.get(key,key.upper())
        if key in TEXT:
            if not isinstance(item,str) or '\0' in item or len(item)>16384:
                raise RelationalClientError('Native '+key+' requires bounded text without NUL')
            clauses.append(keyword+'=%s');parameters.append(item)
        elif key in NUMBERS:
            if key=='stats_sample_pages' and item=='DEFAULT':clauses.append('STATS_SAMPLE_PAGES=DEFAULT');continue
            if not isinstance(item,str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,19})',item) or int(item)>2**64-1:
                raise RelationalClientError('Native '+key+' requires exact unsigned decimal text')
            clauses.append(keyword+'='+item)
        elif key in CHOICES:
            if not isinstance(item,str) or item not in CHOICES[key]:raise RelationalClientError('Select native '+key+' explicitly')
            clauses.append(keyword+'='+item)
        elif key in JSON_OPTIONS:
            try:text=json.dumps(item,ensure_ascii=False,separators=(',',':'),allow_nan=False)
            except (TypeError,ValueError):raise RelationalClientError('Native engine attributes require JSON values') from None
            if len(text.encode('utf8'))>65536:raise RelationalClientError('Native engine attributes exceed 64 KiB')
            clauses.append(keyword+'=%s');parameters.append(text)
        elif key=='secondary_engine' and item is None:clauses.append('SECONDARY_ENGINE=NULL')
        elif key in {'secondary_engine','tablespace'}:clauses.append(keyword+'='+identifier(item))
        elif key=='union':
            if not isinstance(item,list) or len(item)>256:raise RelationalClientError('Select a bounded native MERGE member list')
            names=[]
            for path in item:
                if not isinstance(path,list) or not 1<=len(path)<=2:raise RelationalClientError('Use exact MERGE member identifier paths')
                names.append('.'.join(identifier(name) for name in path))
            clauses.append('UNION=('+','.join(names)+')')
    if connection is not None:
        if not isinstance(connection,str) or '\0' in connection or len(connection)>4096:
            raise RelationalClientError('Select bounded native FEDERATED connection text or a named server reference')
        clauses.append('CONNECTION=%s');parameters.append(connection)
    return (' '+ ' '.join(clauses) if clauses else ''),tuple(parameters)
