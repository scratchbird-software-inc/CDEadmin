"""PostgreSQL 15+ parameter privileges, independent of configuration values."""
from .native_admin import PostgreSQLNativeAdminError,_identifier,_name,_literal,_flag

PRIVILEGES=('SET','ALTER SYSTEM')
_ASCII_LOWER=str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')


def observation(name):
    literal=_literal(name,'parameter')
    # Native GUC aliases are not ACL identities. Resolve reference aliases
    # without reading any configuration value; ssl_groups is18+ only.
    canonical=("CASE WHEN "+literal+"='sort_mem' THEN 'work_mem' WHEN "+literal+"='vacuum_mem' THEN 'maintenance_work_mem' WHEN "+literal+"='ssl_ecdh_curve' AND EXISTS(SELECT 1 FROM pg_catalog.pg_settings WHERE name='ssl_groups') THEN 'ssl_groups' ELSE "+literal+' END')
    return ("SELECT p.oid,p.parname,p.paracl,COALESCE((SELECT jsonb_agg(jsonb_build_object('grantor_oid',a.grantor,'grantee_oid',a.grantee,'privilege',a.privilege_type,'is_grantable',a.is_grantable)) FROM pg_catalog.aclexplode(p.paracl) a),'[]'::jsonb) AS explicit_grants,pg_catalog.has_parameter_privilege(current_user,p.parname,'SET') AS can_set,pg_catalog.has_parameter_privilege(current_user,p.parname,'ALTER SYSTEM') AS can_alter_system FROM pg_catalog.pg_parameter_acl p WHERE p.parname="+canonical)


def compile_operation(operation,native,draft):
    selected=native.get('name')or(native.get('catalog_row')or{}).get('parname')
    name=_name(selected or draft.get('parameter'),'parameter').translate(_ASCII_LOWER)
    if draft.get('parameter') and selected and _name(draft['parameter'],'parameter').translate(_ASCII_LOWER)!=_name(selected,'parameter').translate(_ASCII_LOWER):
        raise PostgreSQLNativeAdminError('The parameter draft disagrees with its native target')
    quoted='.'.join(_identifier(part,'parameter component')for part in name.split('.'))
    if operation=='inspect':
        statement=observation(name)
        return {'statement':statement,'read_only':True,'minimum_server_version':150000}
    if operation not in ('grant','revoke'):raise PostgreSQLNativeAdminError('Select parameter grant/revoke/inspect')
    choices=draft.get('privileges');roles=draft.get('roles')
    if not isinstance(choices,list)or not choices or any(not isinstance(row,dict)or set(row)-{'privilege','_id'}or row.get('privilege')not in PRIVILEGES for row in choices):
        raise PostgreSQLNativeAdminError('Select SET and/or ALTER SYSTEM parameter privileges')
    words=[row['privilege']for row in choices]
    if len(set(words))!=len(words):raise PostgreSQLNativeAdminError('Parameter privileges must be distinct')
    if not isinstance(roles,list)or not 1<=len(roles)<=100 or any(not isinstance(row,dict)or set(row)-{'role','_id'}for row in roles):
        raise PostgreSQLNativeAdminError('Select 1–100 distinct native grantees')
    names=[_name(row.get('role'),'role')for row in roles]
    if len(set(names))!=len(names):raise PostgreSQLNativeAdminError('Grantees must be distinct')
    grantees=', '.join('PUBLIC'if role=='PUBLIC'else _identifier(role,'role')for role in names)
    if operation=='grant':
        if _flag(draft,'grant_option_only')or _flag(draft,'cascade'):raise PostgreSQLNativeAdminError('Grant-option-only and CASCADE belong to revoke')
        statement='GRANT '+', '.join(words)+' ON PARAMETER '+quoted+' TO '+grantees+(' WITH GRANT OPTION'if _flag(draft,'with_grant')else '')
    else:
        if _flag(draft,'with_grant'):raise PostgreSQLNativeAdminError('WITH GRANT OPTION belongs to grant')
        statement='REVOKE '+('GRANT OPTION FOR 'if _flag(draft,'grant_option_only')else '')+', '.join(words)+' ON PARAMETER '+quoted+' FROM '+grantees+(' CASCADE'if _flag(draft,'cascade')else ' RESTRICT')
    return {'statement':statement,'read_only':False,'minimum_server_version':150000,'observation_statement':observation(name)}


def form(operation,field):
    fields=[field('parameter','Parameter',help='Use a catalog parameter name, never a setting value.')]
    if operation!='inspect':fields += [field('privileges','Privileges','grid',required=True,columns=[field('privilege','Privilege','select',required=True,options=[{'value':v,'label':v}for v in PRIVILEGES])]),field('roles','Grantees','grid',required=True,columns=[field('role','Role or PUBLIC',required=True)])]
    if operation=='grant':fields.append(field('with_grant','With grant option','boolean'))
    if operation=='revoke':fields += [field('grant_option_only','Revoke grant option only','boolean'),field('cascade','Cascade dependent grants','boolean')]
    return {'form_id':'postgresql-parameter-acl-'+operation,'form_key':'native:postgresql:server:parameter-acl','title':operation.title()+' parameter privileges','fields':fields}
