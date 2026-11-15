"""Typed native extended statistics; no collected values or ANALYZE emulation."""
from .native_admin import PostgreSQLNativeAdminError,_identifier,_name,_qualified,_literal,_flag
from .policies import expression

KINDS=('ndistinct','dependencies','mcv')


def target(value):
    if type(value)is not int or not -1<=value<=10000:
        raise PostgreSQLNativeAdminError('Statistics target must be -1 through 10000')
    return str(value)


def definition(draft):
    name=_qualified(_name(draft.get('schema'),'schema'),_name(draft.get('name'),'name'))
    rows=draft.get('elements')
    if not isinstance(rows,list)or not 1<=len(rows)<=32:
        raise PostgreSQLNativeAdminError('Statistics need 1–32 typed elements; the native dimensional limit also applies')
    elements=[]
    for row in rows:
        if not isinstance(row,dict)or set(row)-{'kind','value','_id'}:
            raise PostgreSQLNativeAdminError('Each statistics element has kind and value')
        if row.get('kind')=='column':elements.append(_identifier(_name(row.get('value'),'column'),'column'))
        elif row.get('kind')=='expression':elements.append('('+expression(row.get('value'),'expression')+')')
        else:raise PostgreSQLNativeAdminError('Statistics element kind is column or expression')
    kinds=draft.get('kinds',[])
    if not isinstance(kinds,list)or any(not isinstance(row,dict)or set(row)-{'kind','_id'}or row.get('kind')not in KINDS for row in kinds):
        raise PostgreSQLNativeAdminError('Select native ndistinct, dependencies or mcv kinds')
    kinds=[row['kind']for row in kinds]
    if len(set(kinds))!=len(kinds):raise PostgreSQLNativeAdminError('Statistics kinds must be distinct')
    if len(rows)==1 and (rows[0]['kind']!='expression'or kinds):
        raise PostgreSQLNativeAdminError('Single-element statistics require an expression and no multivariate kinds')
    return ('CREATE STATISTICS '+name+(' ('+', '.join(kinds)+')'if kinds else '')+' ON '+', '.join(elements)+
            ' FROM '+_qualified(_name(draft.get('table_schema'),'table_schema'),_name(draft.get('table'),'table')))


def compile_operation(operation,native,draft):
    schema=draft.get('schema')if operation=='create'else native.get('schema')
    name=draft.get('name')if operation=='create'else native.get('name')or(native.get('catalog_row')or{}).get('stxname')
    qualified=_qualified(_name(schema,'schema'),_name(name,'name'));statements=[]
    if operation=='create':statements.append(definition(draft))
    elif operation=='drop':
        if draft.get('confirmation')!=name:raise PostgreSQLNativeAdminError('Drop confirmation must match the statistics name')
        statements.append('DROP STATISTICS '+qualified+(' CASCADE'if _flag(draft,'cascade')else ''))
    elif operation=='alter':
        if any(key in draft for key in ('elements','kinds','table','table_schema')):
            raise PostgreSQLNativeAdminError('Statistics operands and kinds require reviewed drop/create')
    elif operation=='inspect':
        oid=native.get('oid')
        if type(oid)is not int or not 0<oid<2**32:raise PostgreSQLNativeAdminError('Refresh the native statistics OID')
        return {'statement':f'SELECT s.oid, n.nspname AS schema, s.stxname, s.stxrelid, s.stxowner, s.stxkeys, s.stxkind, s.stxstattarget, pg_catalog.pg_get_statisticsobjdef(s.oid) AS definition FROM pg_catalog.pg_statistic_ext s JOIN pg_catalog.pg_namespace n ON n.oid=s.stxnamespace WHERE s.oid={oid}', 'read_only':True}
    else:raise PostgreSQLNativeAdminError('Unknown native statistics operation')
    if operation in ('create','alter'):
        if 'target'in draft:statements.append('ALTER STATISTICS '+qualified+' SET STATISTICS '+target(draft['target']))
        if 'comment'in draft:statements.append('COMMENT ON STATISTICS '+qualified+' IS '+('NULL'if draft['comment']in (None,'')else _literal(draft['comment'],'comment')))
        if operation=='alter'and draft.get('name')and draft['name']!=name:
            statements.append('ALTER STATISTICS '+qualified+' RENAME TO '+_identifier(_name(draft['name'],'name'),'name'))
            name=draft['name'];qualified=_qualified(schema,name)
        if operation=='alter'and draft.get('schema')and draft['schema']!=schema:
            statements.append('ALTER STATISTICS '+qualified+' SET SCHEMA '+_identifier(_name(draft['schema'],'schema'),'schema'))
            qualified=_qualified(draft['schema'],name)
        if draft.get('owner'):statements.append('ALTER STATISTICS '+qualified+' OWNER TO '+_identifier(_name(draft['owner'],'owner'),'owner'))
    if not statements:raise PostgreSQLNativeAdminError('Nothing to change')
    result={'statement':';\n'.join(statements),'read_only':False}
    if operation=='create' and any(row.get('kind')=='expression' for row in draft.get('elements',[])):
        result['minimum_server_version']=140000
    return result


def form(operation,field):
    if operation=='drop':fields=[field('cascade','Drop dependent objects','boolean'),field('confirmation','Type statistics name',required=True)]
    elif operation=='inspect':fields=[]
    else:
        fields=[field('name','Name',required=operation=='create'),field('schema','Schema',required=operation=='create'),field('owner','Owner'),field('target','Statistics target','number',help='-1 uses default; 0–10000 native target.'),field('comment','Comment','multiline')]
        if operation=='create':fields += [field('table_schema','Table schema',required=True),field('table','Table',required=True),field('elements','Statistics elements','grid',required=True,columns=[field('kind','Kind','select',required=True,options=[{'value':'column','label':'Column'},{'value':'expression','label':'Expression'}]),field('value','Column or expression',required=True)]),field('kinds','Multivariate kinds','grid',columns=[field('kind','Kind','select',required=True,options=[{'value':v,'label':v}for v in KINDS])])]
    return {'form_key':'native:postgresql:schema:extended-statistics','form_id':'postgresql-statistics-'+operation,'title':operation.title()+' statistics','fields':fields}
