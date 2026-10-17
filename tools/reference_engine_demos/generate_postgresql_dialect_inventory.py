"""Inventory PostgreSQL 18.3 grammar and native catalogs independently of tasks."""
import hashlib
import json
from pathlib import Path
import re

VERSION='18.3'
GRAMMARS=('src/backend/parser/gram.y','src/pl/plpgsql/src/pl_gram.y')
KEYWORDS='src/include/parser/kwlist.h'
PL_KEYWORDS=('src/pl/plpgsql/src/pl_reserved_kwlist.h','src/pl/plpgsql/src/pl_unreserved_kwlist.h')
SCANNER='src/backend/parser/scan.l'
ERRORS='src/backend/utils/errcodes.txt'


def sha256(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while data:=stream.read(1024*1024):result.update(data)
    return result.hexdigest()


def record(family,index,name,source,**properties):
    return {'item_id':family+'.'+str(index).zfill(5),'native_name':name,'source':source,**properties}


def grammar_inventory(source):
    source=Path(source);commands=[];files={};statement_names=[]
    for relative in GRAMMARS:
        path=source/relative;text=path.read_text();files[relative]=sha256(path)
        for match in re.finditer(r'(?m)^([A-Za-z_][A-Za-z0-9_]*)\s*:',text):
            commands.append(record('commands',len(commands)+1,match[1],relative+':'+str(text.count('\n',0,match.start())+1),
                language_profile='postgresql-plpgsql' if '/plpgsql/' in relative else 'postgresql-sql'))
        if relative==GRAMMARS[0]:
            block=re.search(r'(?ms)^stmt:\s*(.*?)^\s*;\s*$',text)
            if block is None:raise RuntimeError('Native PostgreSQL top-level statement production is unavailable')
            statement_names=re.findall(r'(?m)^\s*(?:\|\s*)?([A-Z][A-Za-z0-9_]*)\s*$',block[1])
            top=re.search(r'(?ms)^toplevel_stmt:\s*(.*?)^\s*;\s*$',text)
            if top is None:raise RuntimeError('Native PostgreSQL top-level command context is unavailable')
            statement_names.extend(name for name in re.findall(r'(?m)^\s*(?:\|\s*)?([A-Z][A-Za-z0-9_]*)\s*$',top[1]) if name not in statement_names)
    if not statement_names or len(statement_names)!=len(set(statement_names)):
        raise RuntimeError('Native PostgreSQL statement grammar inventory is ambiguous')
    statements=[record('statements',index,name,GRAMMARS[0]+':stmt') for index,name in enumerate(statement_names,1)]
    text=(source/ERRORS).read_text();files[ERRORS]=sha256(source/ERRORS)
    diagnostics=[]
    for number,line in enumerate(text.splitlines(),1):
        match=re.fullmatch(r'([0-9A-Z]{5})\s+([EWS])\s+(ERRCODE_[A-Z0-9_]+)(?:\s+([a-z_0-9]+))?\s*',line)
        if match:
            diagnostics.append(record('diagnostics',len(diagnostics)+1,match[3],ERRORS+':'+str(number),
                sqlstate=match[1],severity_class=match[2],condition_name=match[4]))
    source_keywords=[match[1] for match in re.finditer(r'^PG_KEYWORD\("([a-z_0-9]+)"',
        (source/KEYWORDS).read_text(),re.MULTILINE)]
    files[KEYWORDS]=sha256(source/KEYWORDS);files[SCANNER]=sha256(source/SCANNER)
    if not diagnostics or not source_keywords:raise RuntimeError('Native PostgreSQL diagnostic or keyword source inventory is unavailable')
    return {'commands':commands,'statements':statements,'diagnostics':diagnostics},files,source_keywords


def generate(source,connection,archive):
    from psycopg import Cursor
    from psycopg.rows import tuple_row
    if connection.info.transaction_status!=0:raise ValueError('Dialect inventory requires an owned idle connection')
    source=Path(source);inventory,files,source_keywords=grammar_inventory(source)
    def rows(statement):
        with Cursor(connection,row_factory=tuple_row) as cursor:
            cursor.execute(statement)
            return cursor.fetchall() if cursor.description else []
    rows('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
    try:
        if str(rows('SHOW server_version_num')[0][0])!='180003':raise RuntimeError('Native dialect inventory requires PostgreSQL18.3')
        build=rows('SELECT version(),current_setting(\'block_size\'),current_setting(\'integer_datetimes\')')[0]
        keywords=rows('SELECT word,catcode::text,barelabel::text FROM pg_catalog.pg_get_keywords() ORDER BY word')
        if sorted(source_keywords)!=[row[0] for row in keywords]:raise RuntimeError('Native PostgreSQL keywords differ from the pinned source inventory')
        inventory['lexical_rules']=[record('lexical_rules',index,name,'pg_get_keywords()',category=category,bare_label=bare)
            for index,(name,category,bare) in enumerate(keywords,1)]
        for relative in PL_KEYWORDS:
            path=source/relative;files[relative]=sha256(path)
            for match in re.finditer(r'^PG_KEYWORD\("([a-z_0-9]+)"',path.read_text(),re.MULTILINE):
                inventory['lexical_rules'].append(record('lexical_rules',len(inventory['lexical_rules'])+1,match[1],relative,
                    language_profile='postgresql-plpgsql',category='unreserved' if 'unreserved' in relative else 'reserved'))
        for match in re.finditer(r'^%x\s+([^\n]+)',(source/SCANNER).read_text(),re.MULTILINE):
            for state in match[1].split():
                inventory['lexical_rules'].append(record('lexical_rules',len(inventory['lexical_rules'])+1,state,SCANNER,
                    lexical_kind='native_scanner_state'))
        types=rows("SELECT t.oid::text,pg_catalog.format_type(t.oid,NULL),t.typtype::text,t.typcategory::text,"
            "t.typlen::text,t.typbyval::text,t.typelem::text,t.typcollation::text FROM pg_catalog.pg_type t "
            "JOIN pg_catalog.pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='pg_catalog' ORDER BY t.oid")
        inventory['data_types']=[record('data_types',index,row[1],'pg_catalog.pg_type:'+row[0],oid=row[0],
            type_kind=row[2],type_category=row[3],length=row[4],by_value=row[5],element_oid=row[6],collation_oid=row[7])
            for index,row in enumerate(types,1)]
        functions=rows("SELECT p.oid::text,pg_catalog.quote_ident(n.nspname)||'.'||pg_catalog.quote_ident(p.proname),"
            "pg_catalog.pg_get_function_identity_arguments(p.oid),pg_catalog.pg_get_function_result(p.oid),p.prokind::text,"
            "p.provolatile::text,p.proparallel::text,p.prosecdef::text FROM pg_catalog.pg_proc p "
            "JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='pg_catalog' ORDER BY p.oid")
        inventory['functions']=[record('functions',index,row[1]+'('+row[2]+')','pg_catalog.pg_proc:'+row[0],oid=row[0],
            return_type=row[3],function_kind=row[4],volatility=row[5],parallel_safety=row[6],security_definer=row[7])
            for index,row in enumerate(functions,1)]
        operators=rows("SELECT o.oid::text,n.nspname,o.oprname,o.oprkind::text,"
            "CASE WHEN o.oprleft=0 THEN NULL ELSE pg_catalog.format_type(o.oprleft,NULL) END,"
            "CASE WHEN o.oprright=0 THEN NULL ELSE pg_catalog.format_type(o.oprright,NULL) END,"
            "pg_catalog.format_type(o.oprresult,NULL) FROM pg_catalog.pg_operator o "
            "JOIN pg_catalog.pg_namespace n ON n.oid=o.oprnamespace WHERE n.nspname='pg_catalog' ORDER BY o.oid")
        inventory['operators']=[record('operators',index,row[1]+'.'+row[2],'pg_catalog.pg_operator:'+row[0],
            oid=row[0],operator_kind=row[3],left_type=row[4],right_type=row[5],result_type=row[6])
            for index,row in enumerate(operators,1)]
        settings=rows('SELECT name,vartype,context,unit,enumvals::text,min_val,max_val FROM pg_catalog.pg_settings ORDER BY name')
        inventory['session_settings']=[record('session_settings',index,row[0],'pg_catalog.pg_settings',
            value_type=row[1],context=row[2],unit=row[3],enum_values=row[4],minimum=row[5],maximum=row[6])
            for index,row in enumerate(settings,1)]
        extensions=rows('SELECT extname,extversion FROM pg_catalog.pg_extension ORDER BY extname')
        languages=rows('SELECT lanname,lanispl::text,lanpltrusted::text FROM pg_catalog.pg_language ORDER BY lanname')
    finally:rows('ROLLBACK')
    counts={name:len(records) for name,records in inventory.items()}
    return {'schema':'cdeadmin.engine-dialect-inventory.v1','inventory_id':'postgresql.dialect-inventory.18.3.v1',
        'engine_id':'postgresql','reference_version':VERSION,'collection_authority':'PostgreSQL18.3 native catalogs and pinned SQL/PLpgSQL grammar',
        'source_evidence':{'archive':Path(archive).name,'archive_sha256':sha256(archive),'files':files},
        'completeness':{'runtime_version':VERSION,'runtime_catalogs_exhausted':True,'grammar_files_exhausted':True,
            'inventory_counts':counts,'build':str(build[0]),'block_size':str(build[1]),'integer_datetimes':str(build[2]),
            'installed_extensions':[list(row) for row in extensions],'installed_languages':[list(row) for row in languages],
            'scope':'Native pg_catalog inventories of the observed installation; optional extension languages and arbitrary user schemas retain separate acceptance.'},
        'inventories':inventory}
