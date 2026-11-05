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


# Table options as MySQL reports them, for re-opening a table (2026-11-05).
CATALOG_OPTIONS = {'max_rows', 'min_rows', 'avg_row_length', 'row_format', 'stats_sample_pages', 'stats_auto_recalc',
                   'key_block_size', 'stats_persistent', 'pack_keys', 'checksum', 'delay_key_write', 'compression',
                   'encryption', 'secondary_engine'}
DDL_OPTIONS = re.compile(r'\n\) (?:/\*!\d+ TABLESPACE `((?:[^`]|``)+)` \*/ )?(?:/\*!\d+ AUTOEXTEND_SIZE=(\d+) \*/ )?'
                         r'ENGINE=\w+(?: AUTO_INCREMENT=(\d+))?')


def catalog_options(text):
    """The explicit options in information_schema.TABLES.CREATE_OPTIONS (key=value, strings in double quotes)."""
    found = {}
    for key, item in re.findall(r'([A-Za-z_]+)=("(?:[^"\\]|\\.)*"|\S+)', text or ''):
        key = key.lower()
        if key not in CATALOG_OPTIONS:
            continue
        item = item[1:-1] if item.startswith('"') else item
        found[key] = item.upper() if key == 'row_format' else item
    return found


def ddl_options(source):
    """TABLESPACE, AUTOEXTEND_SIZE and AUTO_INCREMENT from SHOW CREATE TABLE. The catalog's AUTO_INCREMENT
    is a cached statistic; the DDL is current. Only the options head after the column list is read, so a
    comment cannot be mistaken for an option."""
    matched = DDL_OPTIONS.search(source or '')
    if not matched:
        return {}
    tablespace, autoextend, increment = matched.groups()
    return {key: value for key, value in (('tablespace', tablespace and tablespace.replace('``', '`')),
            ('autoextend_size', autoextend), ('auto_increment', increment)) if value is not None}


NUMERIC_TYPES = {'tinyint', 'smallint', 'mediumint', 'int', 'bigint', 'decimal', 'float', 'double', 'bit', 'year'}


def default_sql(default, data_type, extra, sql_mode):
    """A column's catalog default as SQL: an expression default in parentheses (CURRENT_TIMESTAMP as
    written), a numeric or bit value as written, any other value as a string literal for sql_mode."""
    if default is None:
        return None
    default = str(default)
    if 'DEFAULT_GENERATED' in str(extra or '').upper():
        return default if re.fullmatch(r'CURRENT_TIMESTAMP(?:\(\d\))?', default, re.I) else '(' + default + ')'
    if str(data_type or '').lower() in NUMERIC_TYPES:
        return default
    if 'NO_BACKSLASH_ESCAPES' not in str(sql_mode or '').upper():
        default = default.replace('\\', '\\\\')
    return "'" + default.replace("'", "''") + "'"
