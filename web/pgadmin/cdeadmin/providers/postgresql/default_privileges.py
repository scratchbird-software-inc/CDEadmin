"""Complete typed default privilege selectors; future objects, never existing ACLs."""
from .native_admin import PostgreSQLNativeAdminError,_identifier,_name,_literal,_flag

OBJECTS={
 'TABLES':('r',('SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN')),
 'SEQUENCES':('S',('USAGE','SELECT','UPDATE')),
 'FUNCTIONS':('f',('EXECUTE',)), 'ROUTINES':('f',('EXECUTE',)),
 'TYPES':('T',('USAGE',)), 'SCHEMAS':('n',('USAGE','CREATE')),
 'LARGE OBJECTS':('L',('SELECT','UPDATE'))}


def names(draft,key,field):
    rows=draft.get(key,[])
    if not isinstance(rows,list)or len(rows)>100 or any(not isinstance(row,dict)or set(row)-{field,'_id'}for row in rows):
        raise PostgreSQLNativeAdminError(key+' must be a bounded typed grid')
    result=[_name(row.get(field),field)for row in rows]
    if len(set(result))!=len(result):raise PostgreSQLNativeAdminError(key+' must be distinct')
    return result


def compile_operation(operation,native,draft):
    objects=draft.get('object_type')
    if not isinstance(objects,str)or objects not in OBJECTS:raise PostgreSQLNativeAdminError('Select a native default-privilege object family')
    owners=names(draft,'owners','role');schemas=names(draft,'schemas','schema')
    mode=draft.get('owner_mode','CURRENT_ROLE');scope=draft.get('scope','GLOBAL');owner_kind=draft.get('owner_kind','ROLE')
    if mode not in ('CURRENT_ROLE','NAMED_ROLES')or (mode=='NAMED_ROLES')!=bool(owners):
        raise PostgreSQLNativeAdminError('Select CURRENT_ROLE without names or NAMED_ROLES with owners')
    if owner_kind not in ('ROLE','USER'):raise PostgreSQLNativeAdminError('FOR selector is ROLE or USER')
    if scope not in ('GLOBAL','SCHEMAS')or (scope=='SCHEMAS')!=bool(schemas):
        raise PostgreSQLNativeAdminError('Select GLOBAL without schemas or SCHEMAS with names')
    if schemas and objects in ('SCHEMAS','LARGE OBJECTS'):
        raise PostgreSQLNativeAdminError(objects+' default privileges cannot use IN SCHEMA')
    code,allowed=OBJECTS[objects]
    owners_filter=('d.defaclrole IN (SELECT oid FROM pg_catalog.pg_roles WHERE rolname IN ('+', '.join(_literal(v,'role')for v in owners)+'))'if owners else 'd.defaclrole=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=CURRENT_USER)')
    schema_filter=('n.nspname IN ('+', '.join(_literal(v,'schema')for v in schemas)+')'if schemas else 'd.defaclnamespace=0')
    observe=("SELECT d.oid,d.defaclrole,pg_catalog.pg_get_userbyid(d.defaclrole) AS owner,d.defaclnamespace,n.nspname AS schema,d.defaclobjtype,d.defaclacl,COALESCE((SELECT jsonb_agg(jsonb_build_object('grantor_oid',a.grantor,'grantee_oid',a.grantee,'privilege',a.privilege_type,'is_grantable',a.is_grantable)) FROM pg_catalog.aclexplode(d.defaclacl) a),'[]'::jsonb) AS explicit_grants FROM pg_catalog.pg_default_acl d LEFT JOIN pg_catalog.pg_namespace n ON n.oid=d.defaclnamespace WHERE "+owners_filter+' AND '+schema_filter+' AND d.defaclobjtype='+_literal(code,'object_type'))
    minimum=180000 if objects=='LARGE OBJECTS'else None
    if operation=='inspect':result={'statement':observe,'read_only':True}
    else:
        if operation not in ('grant','revoke'):raise PostgreSQLNativeAdminError('Select grant/revoke/inspect default privileges')
        rows=draft.get('privileges')
        if not isinstance(rows,list)or not rows or any(not isinstance(row,dict)or set(row)-{'privilege','_id'}for row in rows):raise PostgreSQLNativeAdminError('Select typed native privileges')
        words=[row.get('privilege')for row in rows]
        if any(not isinstance(word,str)for word in words)or len(set(words))!=len(words)or (words!=['ALL']and any(word not in allowed for word in words)):
            raise PostgreSQLNativeAdminError('Privileges must match the native object family, or be ALL alone')
        if 'MAINTAIN'in words:minimum=170000
        grantees=names(draft,'grantees','role')
        if not grantees:raise PostgreSQLNativeAdminError('Select native grantees')
        prefix='ALTER DEFAULT PRIVILEGES'
        if owners:prefix+=' FOR '+owner_kind+' '+', '.join(_identifier(v,'role')for v in owners)
        if schemas:prefix+=' IN SCHEMA '+', '.join(_identifier(v,'schema')for v in schemas)
        who=', '.join('PUBLIC'if v=='PUBLIC'else _identifier(v,'role')for v in grantees)
        if operation=='grant':
            if _flag(draft,'grant_option_only')or _flag(draft,'cascade'):raise PostgreSQLNativeAdminError('Grant-option-only and CASCADE belong to revoke')
            statement=prefix+' GRANT '+', '.join(words)+' ON '+objects+' TO '+who+(' WITH GRANT OPTION'if _flag(draft,'with_grant')else '')
        else:
            if _flag(draft,'with_grant'):raise PostgreSQLNativeAdminError('WITH GRANT OPTION belongs to grant')
            statement=prefix+' REVOKE '+('GRANT OPTION FOR 'if _flag(draft,'grant_option_only')else '')+', '.join(words)+' ON '+objects+' FROM '+who+(' CASCADE'if _flag(draft,'cascade')else ' RESTRICT')
        result={'statement':statement,'read_only':False,'observation_statement':observe}
    if minimum:result['minimum_server_version']=minimum
    return result


def form(operation,field):
    def grid(key,label,entry):return field(key,label,'grid',columns=[field(entry,entry.title(),required=True)])
    fields=[field('object_type','Future object family','select',required=True,options=[{'value':v,'label':v.title()}for v in OBJECTS]),
     field('owner_mode','Creation owner','select',default='CURRENT_ROLE',options=[{'value':'CURRENT_ROLE','label':'Current database role'},{'value':'NAMED_ROLES','label':'Named roles'}]),
     field('owner_kind','Owner selector','select',default='ROLE',options=[{'value':'ROLE','label':'FOR ROLE'},{'value':'USER','label':'FOR USER'}]),grid('owners','Creation owners','role'),
     field('scope','Scope','select',default='GLOBAL',options=[{'value':'GLOBAL','label':'Entire selected database'},{'value':'SCHEMAS','label':'Selected schemas'}]),grid('schemas','Schemas','schema')]
    if operation!='inspect':fields += [field('privileges','Privileges','grid',required=True,columns=[field('privilege','Privilege','select',required=True,options=[{'value':v,'label':v}for v in ('ALL','SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN','USAGE','EXECUTE','CREATE')])]),grid('grantees','Grantees','role')]
    if operation=='grant':fields.append(field('with_grant','With grant option','boolean'))
    if operation=='revoke':fields += [field('grant_option_only','Revoke grant option only','boolean'),field('cascade','Cascade dependent grants','boolean')]
    return {'form_id':'postgresql-default-privileges-'+operation,'form_key':'native:postgresql:database:default-privileges','title':operation.title()+' default privileges','fields':fields}
