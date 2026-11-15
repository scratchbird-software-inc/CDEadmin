"""Native qualification for five explicitly tracked PostgreSQL audit issues."""
from types import SimpleNamespace
import pytest
from psycopg import sql
from test_postgresql_drop_identity import native, SETTINGS  # noqa: F401
from pgadmin.cdeadmin.providers.postgresql.native_admin import compile_native_admin,PostgreSQLNativeAdminError
from pgadmin.cdeadmin.providers.postgresql.provider import PostgreSQLProvider,PostgreSQLStatementRejected
from pgadmin.cdeadmin.providers.postgresql.columns import facts
from ui_descriptor_roundtrip import engine_operations,operation_draft

live=pytest.mark.skipif(SETTINGS is None,reason='Owned PostgreSQL qualification fixture not selected')


def request(native,kind,operation,draft,target=None):
    return {'resource_kind':kind,'operation_id':operation,'draft':draft,
        '_provider_route':{'server_id':1,'database_id':native.dboid},
        'target_resource':{'extensions':{'postgresql':{'native':target or {}}}}}


def execute(provider,value):
    plan=provider.plan_admin_operation(value)
    result=provider.apply_admin_operation({'provider_payload':plan['provider_payload']})
    assert result['transaction_outcome']=='committed'
    return plan,result


def column(native,name='calc'):
    row=native.admin.execute('''SELECT a.attnum,a.attgenerated,pg_catalog.pg_get_expr(d.adbin,d.adrelid)
FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
WHERE n.nspname=%s AND c.relname='target' AND a.attname=%s''',(native.schema,name)).fetchone()
    return {'schema':native.schema,'table':'target','name':name,'attnum':row[0],
            'catalog_row':{'attgenerated':row[1],'generated_expression':row[2]},'generated_expression':row[2]}


@live
@pytest.mark.parametrize('kind',['s','v'])
def test_generated_native_create_and_expression_change_with_comment(native,kind):
    native.create();p=native.provider()
    draft=operation_draft(engine_operations('postgresql')['create@column'],
        {'name':'calc','cltype':'integer','colconstype':'g','generated_kind':kind,'genexpr':'id*2'})
    execute(p,request(native,'column','create',draft,{'schema':native.schema,'table':'target'}))
    native.admin.execute(sql.SQL('INSERT INTO {}.target(id) VALUES(3)').format(sql.Identifier(native.schema)))
    observed=column(native);assert facts(observed)['generated_kind']==kind
    assert 'id' in facts(observed)['genexpr']
    draft=operation_draft(engine_operations('postgresql')['alter@column'],
        {'colconstype':'g','generated_kind':kind,'generated_action':'SET','genexpr':'id*3','description':'expression changed'})
    plan,_=execute(p,request(native,'column','alter',draft,observed))
    assert 'SET EXPRESSION'in plan['command_preview']['statement']
    assert native.admin.execute(sql.SQL('SELECT calc FROM {}.target').format(sql.Identifier(native.schema))).fetchall()==[(9,)]
    assert '* 3'in column(native)['generated_expression']


@live
def test_generated_native_drop_preserves_stored_values_and_virtual_refusal(native):
    native.create();p=native.provider()
    execute(p,request(native,'column','create',{'name':'calc','cltype':'integer','colconstype':'g','genexpr':'id*2'}, {'schema':native.schema,'table':'target'}))
    native.admin.execute(sql.SQL('INSERT INTO {}.target(id) VALUES(4)').format(sql.Identifier(native.schema)))
    execute(p,request(native,'column','alter',{'generated_action':'DROP'},column(native)))
    assert column(native)['catalog_row']['attgenerated']==''
    native.admin.execute(sql.SQL('UPDATE {}.target SET id=9').format(sql.Identifier(native.schema)))
    assert native.admin.execute(sql.SQL('SELECT calc FROM {}.target').format(sql.Identifier(native.schema))).fetchall()==[(8,)]
    execute(p,request(native,'column','create',{'name':'virtual','cltype':'integer','colconstype':'g','generated_kind':'v','genexpr':'id*2'}, {'schema':native.schema,'table':'target'}))
    with pytest.raises(Exception,match='stored'):p.plan_admin_operation(request(native,'column','alter',{'generated_action':'DROP'},column(native,'virtual')))


def test_generated_versions_and_changed_expression_never_silently_ignore():
    target={'schema':'s','table':'t','name':'x','catalog_row':{'attgenerated':'s','generated_expression':'id*2'}}
    r={'resource_kind':'column','operation_id':'alter','draft':{'genexpr':'id*3','description':'changed'},'target_resource':{'extensions':{'postgresql':{'native':target}}}}
    compiled=compile_native_admin(r);assert compiled['minimum_server_version']==170000 and 'SET EXPRESSION'in compiled['statement']
    with pytest.raises(PostgreSQLStatementRejected,match='17'):
        PostgreSQLProvider._check_admin_version(SimpleNamespace(info=SimpleNamespace(server_version=160016)),compiled)
    r['draft']['generated_action']='KEEP'
    with pytest.raises(PostgreSQLNativeAdminError,match='Select SET'):compile_native_admin(r)


@live
def test_statistics_native_descriptor_lifecycle_and_expression(native):
    native.create();p=native.provider()
    native.admin.execute(sql.SQL('ALTER TABLE {}.target ADD COLUMN other integer').format(sql.Identifier(native.schema)))
    values={'schema':native.schema,'name':'stats','table_schema':native.schema,'table':'target',
            'elements':[{'kind':'column','value':'id'},{'kind':'expression','value':'other+1'}],
            'kinds':[{'kind':'dependencies'},{'kind':'mcv'}],'target':123,'comment':'owned'}
    draft=operation_draft(engine_operations('postgresql')['create@extended-statistics'],values)
    execute(p,request(native,'extended-statistics','create',draft))
    row=native.admin.execute('SELECT s.oid,s.stxkind,s.stxstattarget FROM pg_statistic_ext s JOIN pg_namespace n ON n.oid=s.stxnamespace WHERE n.nspname=%s AND stxname=%s',(native.schema,'stats')).fetchone()
    assert set(row[1])=={'e','f','m'} and row[2]==123
    target={'schema':native.schema,'name':'stats','oid':row[0],'catalog':'pg_statistic_ext'}
    draft=operation_draft(engine_operations('postgresql')['alter@extended-statistics'],{'name':'renamed','target':-1,'comment':'changed'})
    execute(p,request(native,'extended-statistics','alter',draft,target))
    target['name']='renamed'
    plan=p.plan_admin_operation(request(native,'extended-statistics','inspect',{},target))
    observed=p.apply_admin_operation({'provider_payload':plan['provider_payload']})['result']['rows']
    assert observed[0]['stxname']=='renamed' and observed[0]['stxstattarget'] is None
    execute(p,request(native,'extended-statistics','drop',{'confirmation':'renamed'},target))
    assert native.admin.execute('SELECT count(*)::integer FROM pg_statistic_ext WHERE oid=%s',(row[0],)).fetchone()==(0,)


@live
def test_statistics_native_virtual_operand_refuses_and_ddn_creation_applies(native,tmp_path):
    import uuid
    from copy import deepcopy
    from pgadmin.cdeadmin.workspace.postgresql_creation import creation
    from pgadmin.cdeadmin.workspace.postgresql_schema_plan import build_plan
    from pgadmin.cdeadmin.workspace.postgresql_schema_apply import PostgreSQLSchemaApplications
    from pgadmin.cdeadmin.providers.postgresql.schema_application import apply_review,_model
    native.create();p=native.provider()
    native.admin.execute(sql.SQL('ALTER TABLE {}.target ADD COLUMN v integer GENERATED ALWAYS AS (id*2) VIRTUAL').format(sql.Identifier(native.schema)))
    values={'schema':native.schema,'name':'bad_virtual','table_schema':native.schema,'table':'target','elements':[{'kind':'column','value':'id'},{'kind':'column','value':'v'}]}
    with pytest.raises(PostgreSQLStatementRejected):execute(p,request(native,'extended-statistics','create',values))
    # Use the actual retained DDN capture/plan/review/apply path.
    import psycopg
    record={'plan':{'endpoint_id':'owned','database_target_id':'postgresql-database:'+str(native.dboid)}}
    with psycopg.connect(native.dsn,autocommit=True)as connection:before=_model(connection,record,native.dboid)
    desired=deepcopy(before);identity='postgresql:new:'+str(uuid.uuid4())
    table=next(key for key,row in before['rows'].items()if row['kind']=='table'and row['name']=='target'and row['native'].get('schema')==native.schema)
    desired['rows'][identity]={'resource_id':identity,'kind':'extended-statistics','name':'ddn_stats','system':'false','path':['postgres',native.schema,'ddn_stats'],
        'native':{'system_object':False,'create':{**values,'name':'ddn_stats','elements':[{'kind':'expression','value':'id+1'}],'depends_on':[table]}}}
    preview=build_plan(before,desired,before);assert preview['application_supported'],preview.get('blockers')
    store=PostgreSQLSchemaApplications(tmp_path/'reviews.json');receipt=store.review(preview,before,desired,'owner','bound','postgresql-database:'+str(native.dboid))
    result=store.apply({'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True},'owner','bound',lambda retained:apply_review(p,{'server_id':1,'database_id':native.dboid},retained))
    assert result['state']=='native_commit_returned',result
    assert result['outcome']['created_objects'] and result['outcome']['rediscovery']['matches_reviewed_properties'],result


@live
def test_statistics_native_owner_move_and_restricted_refusal(native):
    native.create();p=native.provider();owner=native.role();other=native.role()
    other_schema=native.schema+'_destination'
    native.admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(other_schema)))
    try:
        native.admin.execute(sql.SQL('GRANT USAGE,CREATE ON SCHEMA {} TO {}').format(sql.Identifier(other_schema),sql.Identifier(owner)))
        values={'schema':native.schema,'name':'owned_stat','table_schema':native.schema,'table':'target','elements':[{'kind':'expression','value':'id+1'}]}
        execute(p,request(native,'extended-statistics','create',values))
        target={'schema':native.schema,'name':'owned_stat'}
        with pytest.raises(PostgreSQLStatementRejected):execute(native.provider(other),request(native,'extended-statistics','alter',{'target':99},target))
        execute(p,request(native,'extended-statistics','alter',{'name':'moved_stat','schema':other_schema,'owner':owner},target))
        row=native.admin.execute('SELECT s.oid,r.rolname FROM pg_statistic_ext s JOIN pg_namespace n ON n.oid=s.stxnamespace JOIN pg_roles r ON r.oid=s.stxowner WHERE n.nspname=%s AND stxname=%s',(other_schema,'moved_stat')).fetchone()
        assert row[1]==owner
        execute(native.provider(owner),request(native,'extended-statistics','alter',{'target':44},{'schema':other_schema,'name':'moved_stat','oid':row[0]}))
        assert native.admin.execute('SELECT stxstattarget FROM pg_statistic_ext WHERE oid=%s',(row[0],)).fetchone()==(44,)
    finally:native.admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(other_schema)))


@live
def test_parameter_acl_native_grant_option_cascade_effective_use_and_inventory(native):
    import psycopg
    p=native.provider();role=native.role();delegate=native.role()
    target={'name':'log_min_duration_statement'}
    fields={'privileges':[{'privilege':'SET'},{'privilege':'ALTER SYSTEM'}],'roles':[{'role':role}],'with_grant':True}
    draft=operation_draft(engine_operations('postgresql')['grant@parameter-acl'],fields)
    _,result=execute(p,request(native,'parameter-acl','grant',draft,target))
    grants=result['native_observation']['rows'][0]['explicit_grants']
    role_oid=native.admin.execute('SELECT oid FROM pg_roles WHERE rolname=%s',(role,)).fetchone()[0]
    assert {g['privilege']for g in grants if int(g['grantee_oid'])==int(role_oid) and g['is_grantable']}=={'SET','ALTER SYSTEM'},(grants,role_oid,type(role_oid).__name__)
    with psycopg.connect(native.dsn,autocommit=True)as source:
        source.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(role)))
        source.execute('SET log_min_duration_statement=5000')
        assert source.execute('SHOW log_min_duration_statement').fetchone()==('5s',)
        source.execute('ALTER SYSTEM SET log_min_duration_statement=5000')
        delegated=operation_draft(engine_operations('postgresql')['grant@parameter-acl'],{'privileges':[{'privilege':'SET'}],'roles':[{'role':delegate}]})
        execute(native.provider(role),request(native,'parameter-acl','grant',delegated,target))
    revoke=operation_draft(engine_operations('postgresql')['revoke@parameter-acl'],{'privileges':[{'privilege':'SET'},{'privilege':'ALTER SYSTEM'}],'roles':[{'role':role}],'grant_option_only':True,'cascade':True})
    _,result=execute(p,request(native,'parameter-acl','revoke',revoke,target))
    grants=result['native_observation']['rows'][0]['explicit_grants']
    assert not any(g['is_grantable']for g in grants if int(g['grantee_oid'])==int(role_oid))
    assert native.admin.execute("SELECT has_parameter_privilege(%s,'log_min_duration_statement','SET')",(delegate,)).fetchone()==(False,)
    # Catalog observation must contain the real shared ACL, without settings.
    from pgadmin.cdeadmin.providers.postgresql.server_catalog import SECTIONS
    query=next(row[3]for row in SECTIONS if row[0]=='parameter-acls')
    assert any(row[1]=='log_min_duration_statement'for row in native.admin.execute(query))
    full=operation_draft(engine_operations('postgresql')['revoke@parameter-acl'],{'privileges':[{'privilege':'SET'},{'privilege':'ALTER SYSTEM'}],'roles':[{'role':role}]})
    execute(p,request(native,'parameter-acl','revoke',full,target))
    assert native.admin.execute("SELECT has_parameter_privilege(%s,'log_min_duration_statement','SET')",(role,)).fetchone()==(False,)


@live
def test_parameter_acl_native_restricted_and_validation_refusals(native):
    role=native.role();recipient=native.role();p=native.provider(role)
    value=request(native,'parameter-acl','grant',{'privileges':[{'privilege':'SET'}],'roles':[{'role':recipient}]},{'name':'log_statement'})
    try:execute(p,value)
    except PostgreSQLStatementRejected:pass
    assert native.admin.execute("SELECT has_parameter_privilege(%s,'log_statement','SET')",(recipient,)).fetchone()==(False,)
    value['draft']['privileges']=[{'privilege':'SELECT'}]
    with pytest.raises(Exception,match='SET'):p.plan_admin_operation(value)
    compiled=compile_native_admin(request(native,'parameter-acl','inspect',{}, {'name':'log_statement'}))
    with pytest.raises(PostgreSQLStatementRejected,match='15'):
        PostgreSQLProvider._check_admin_version(SimpleNamespace(info=SimpleNamespace(server_version=140025)),compiled)


@live
def test_default_privileges_native_future_table_scope_and_grant_options(native):
    import psycopg
    p=native.provider();owner=native.role();recipient=native.role()
    native.admin.execute(sql.SQL('GRANT USAGE,CREATE ON SCHEMA {} TO {}').format(sql.Identifier(native.schema),sql.Identifier(owner)))
    values={'object_type':'TABLES','owner_mode':'NAMED_ROLES','owners':[{'role':owner}],'scope':'SCHEMAS','schemas':[{'schema':native.schema}],
            'grantees':[{'role':recipient}],'privileges':[{'privilege':'SELECT'}],'with_grant':True}
    draft=operation_draft(engine_operations('postgresql')['grant@default-privileges'],values)
    _,result=execute(p,request(native,'default-privileges','grant',draft))
    assert result['native_observation']['rows'][0]['owner']==owner
    def create(name):
        with psycopg.connect(native.dsn,autocommit=True)as c:
            c.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(owner)))
            c.execute(sql.SQL('CREATE TABLE {}.{}(id integer)').format(sql.Identifier(native.schema),sql.Identifier(name)))
    def privilege(name,word):
        return native.admin.execute('SELECT has_table_privilege(%s,%s,%s)',(recipient,native.schema+'.'+name,word)).fetchone()[0]
    create('before_revoke');assert privilege('before_revoke','SELECT WITH GRANT OPTION')is True
    revoke={**values,'with_grant':False,'grant_option_only':True,'cascade':True}
    execute(p,request(native,'default-privileges','revoke',operation_draft(engine_operations('postgresql')['revoke@default-privileges'],revoke)))
    create('after_option_revoke');assert privilege('after_option_revoke','SELECT')is True and privilege('after_option_revoke','SELECT WITH GRANT OPTION')is False
    assert privilege('before_revoke','SELECT WITH GRANT OPTION')is True
    execute(p,request(native,'default-privileges','revoke',{**revoke,'grant_option_only':False}))
    create('after_full_revoke');assert privilege('after_full_revoke','SELECT')is False
    assert privilege('before_revoke','SELECT')is True


@live
def test_default_privileges_native_schema_and_large_object_families(native):
    import psycopg
    p=native.provider();owner=native.role();recipient=native.role()
    native.admin.execute(sql.SQL('GRANT CREATE ON DATABASE postgres TO {}').format(sql.Identifier(owner)))
    common={'owner_mode':'NAMED_ROLES','owner_kind':'USER','owners':[{'role':owner}],
            'scope':'GLOBAL','grantees':[{'role':recipient}]}
    execute(p,request(native,'default-privileges','grant',{**common,'object_type':'SCHEMAS','privileges':[{'privilege':'USAGE'}]}))
    execute(p,request(native,'default-privileges','grant',{**common,'object_type':'LARGE OBJECTS','privileges':[{'privilege':'SELECT'}]}))
    schema=native.schema+'_future'
    try:
        with psycopg.connect(native.dsn,autocommit=True)as c:
            c.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(owner)))
            c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            loid=int(c.execute('SELECT lo_create(0)').fetchone()[0])
        assert native.admin.execute("SELECT has_schema_privilege(%s,%s,'USAGE')",(recipient,schema)).fetchone()==(True,)
        assert native.admin.execute("SELECT has_largeobject_privilege(%s,%s::oid,'SELECT')",(recipient,loid)).fetchone()==(True,)
        compiled=compile_native_admin(request(native,'default-privileges','grant',{**common,'object_type':'LARGE OBJECTS','privileges':[{'privilege':'UPDATE'}]}))
        with pytest.raises(PostgreSQLStatementRejected,match='18'):
            PostgreSQLProvider._check_admin_version(SimpleNamespace(info=SimpleNamespace(server_version=170012)),compiled)
    finally:native.admin.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))


@live
def test_default_privileges_native_restricted_and_scope_refusals(native):
    p=native.provider();owner=native.role();other=native.role()
    values={'owner_mode':'NAMED_ROLES','owners':[{'role':owner}],'scope':'GLOBAL','object_type':'TABLES',
            'grantees':[{'role':other}],'privileges':[{'privilege':'SELECT'}]}
    with pytest.raises(PostgreSQLStatementRejected):execute(native.provider(other),request(native,'default-privileges','grant',values))
    for family in ('SCHEMAS','LARGE OBJECTS'):
        with pytest.raises(Exception,match='IN SCHEMA'):
            p.plan_admin_operation(request(native,'default-privileges','grant',{**values,'scope':'SCHEMAS','schemas':[{'schema':native.schema}],'object_type':family}))
    with pytest.raises(Exception,match='object family'):
        p.plan_admin_operation(request(native,'default-privileges','grant',{**values,'object_type':'TYPES','privileges':[{'privilege':'SELECT'}]}))


@live
def test_checkpoint_native_peer_ack_and_caller_savepoint_preserved(native):
    import psycopg
    native.create();p=native.provider()
    before=native.admin.execute('SELECT checkpoint_lsn::text FROM pg_control_checkpoint()').fetchone()[0]
    with psycopg.connect(native.dsn)as source:
        source.execute('SAVEPOINT caller')
        source.execute(sql.SQL('INSERT INTO {}.target VALUES(7)').format(sql.Identifier(native.schema)))
        draft=operation_draft(engine_operations('postgresql')['checkpoint@server'],{'wait_timeout_ms':30000})
        planned=p.plan_admin_operation(request(native,'server','checkpoint',draft))
        assert planned['command_preview']['native_peer_identity']['database_oid']==native.dboid
        result=p.apply_admin_operation({'provider_payload':planned['provider_payload']})
        receipt=result['checkpoint_receipt']
        assert result['transaction_outcome']=='not_applicable' and receipt['native_command_tag']=='CHECKPOINT'
        assert receipt['connection_release']['connection_released']and not receipt['rollback_undoes_checkpoint']
        assert native.admin.execute(sql.SQL('SELECT count(*)::integer FROM {}.target').format(sql.Identifier(native.schema))).fetchone()==(0,)
        assert source.execute(sql.SQL('SELECT id FROM {}.target').format(sql.Identifier(native.schema))).fetchall()==[(7,)]
        source.execute('ROLLBACK TO caller');source.execute('RELEASE caller')
    after=native.admin.execute('SELECT checkpoint_lsn::text FROM pg_control_checkpoint()').fetchone()[0]
    assert after!=before


@live
def test_checkpoint_native_privilege_and_stale_peer_refusals(native):
    role=native.role();p=native.provider(role)
    value=request(native,'server','checkpoint',{})
    planned=p.plan_admin_operation(value)
    with pytest.raises(PostgreSQLStatementRejected)as error:p.apply_admin_operation({'provider_payload':planned['provider_payload']})
    assert error.value.sqlstate=='42501' and error.value.nothing_changed
    native.admin.execute(sql.SQL('GRANT pg_checkpoint TO {}').format(sql.Identifier(role)))
    planned=p.plan_admin_operation(value)
    result=p.apply_admin_operation({'provider_payload':planned['provider_payload']})
    assert result['checkpoint_receipt']['native_command_tag']=='CHECKPOINT'
    planned=p.plan_admin_operation(value);planned['provider_payload']['checkpoint_peer_identity']['effective_principal']='stale'
    with pytest.raises(PostgreSQLStatementRejected,match='peer/principal'):p.apply_admin_operation({'provider_payload':planned['provider_payload']})
    for invalid in (0,True,600001,'30000'):
        with pytest.raises(Exception,match='timeout'):p.plan_admin_operation(request(native,'server','checkpoint',{'wait_timeout_ms':invalid}))


@live
@pytest.mark.parametrize('failure',['lost_acknowledgement','cancel_response'])
def test_checkpoint_native_completed_but_unconfirmed_never_claims_rollback(native,monkeypatch,failure):
    import psycopg
    from pgadmin.cdeadmin.providers.postgresql import provider as module
    p=native.provider();planned=p.plan_admin_operation(request(native,'server','checkpoint',{}))
    original=module.NativeCursor
    class Unconfirmed:
        def __init__(self,*args,**kwargs):self.cursor=original(*args,**kwargs)
        def __enter__(self):self.cursor.__enter__();return self
        def __exit__(self,*args):return self.cursor.__exit__(*args)
        def execute(self,statement):
            self.cursor.execute(statement)
            if failure=='lost_acknowledgement':raise psycopg.OperationalError('Injected lost checkpoint acknowledgement')
            raise psycopg.errors.QueryCanceled('Injected cancellation response after native completion')
    before=native.admin.execute('SELECT checkpoint_lsn::text FROM pg_control_checkpoint()').fetchone()[0]
    monkeypatch.setattr(module,'NativeCursor',Unconfirmed)
    with pytest.raises(module.PostgreSQLProviderError,match='outcome is unknown')as error:
        p.apply_admin_operation({'provider_payload':planned['provider_payload']})
    assert not getattr(error.value,'nothing_changed',False)and not p._sessions
    after=native.admin.execute('SELECT checkpoint_lsn::text FROM pg_control_checkpoint()').fetchone()[0]
    assert after!=before


@live
@pytest.mark.parametrize('family,privilege,ddl,check',[
 ('SEQUENCES','USAGE','CREATE SEQUENCE {schema}.future_object',"has_sequence_privilege(%s,%s,'USAGE WITH GRANT OPTION')"),
 ('TYPES','USAGE',"CREATE TYPE {schema}.future_object AS ENUM ('a')","has_type_privilege(%s,%s,'USAGE WITH GRANT OPTION')"),
 ('FUNCTIONS','EXECUTE',"CREATE FUNCTION {schema}.future_object() RETURNS integer LANGUAGE sql AS 'SELECT 1'","has_function_privilege(%s,%s,'EXECUTE WITH GRANT OPTION')"),
 ('ROUTINES','EXECUTE',"CREATE PROCEDURE {schema}.future_object() LANGUAGE plpgsql AS 'BEGIN NULL; END'","has_function_privilege(%s,%s,'EXECUTE WITH GRANT OPTION')")])
def test_default_privileges_native_remaining_families(native,family,privilege,ddl,check):
    import psycopg
    owner=native.role();recipient=native.role();p=native.provider()
    native.admin.execute(sql.SQL('GRANT USAGE,CREATE ON SCHEMA {} TO {}').format(sql.Identifier(native.schema),sql.Identifier(owner)))
    values={'object_type':family,'owner_mode':'NAMED_ROLES','owners':[{'role':owner}],
        'scope':'GLOBAL','privileges':[{'privilege':privilege}],'grantees':[{'role':recipient}],'with_grant':True}
    execute(p,request(native,'default-privileges','grant',values))
    with psycopg.connect(native.dsn,autocommit=True)as c:
        c.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(owner)))
        c.execute(sql.SQL(ddl).format(schema=sql.Identifier(native.schema)))
    name=native.schema+'.future_object'+('()'if family in ('FUNCTIONS','ROUTINES')else '')
    assert native.admin.execute('SELECT '+check,(recipient,name)).fetchone()==(True,)


@live
def test_generated_native_table_family_virtual_storage(native):
    p=native.provider()
    values={'schema':native.schema,'name':'with_virtual','columns':[{'name':'id','cltype':'integer'},
        {'name':'calc','cltype':'integer','colconstype':'g','generated_kind':'v','genexpr':'id*2'}]}
    planned,_=execute(p,request(native,'table','create',values))
    assert planned['provider_payload']['minimum_server_version']==180000
    native.admin.execute(sql.SQL('INSERT INTO {}.with_virtual(id) VALUES(4)').format(sql.Identifier(native.schema)))
    assert native.admin.execute(sql.SQL('SELECT calc FROM {}.with_virtual').format(sql.Identifier(native.schema))).fetchall()==[(8,)]


@live
@pytest.mark.parametrize('parameter,canonical',[
 ('LoG_StaTeMeNt','log_statement'),('sort_mem','work_mem'),('vacuum_mem','maintenance_work_mem'),
 ('ssl_ecdh_curve','ssl_groups'),('a'*60+'.'+'b'*60,'a'*60+'.'+'b'*60)])
def test_parameter_acl_native_case_alias_and_qualified_long_name(native,parameter,canonical):
    p=native.provider();role=native.role()
    _,result=execute(p,request(native,'parameter-acl','grant',{'parameter':parameter,'roles':[{'role':role}],'privileges':[{'privilege':'SET'}]}))
    assert result['native_observation']['rows'][0]['parname']==canonical
    assert native.admin.execute('SELECT parname FROM pg_parameter_acl WHERE parname=%s',(canonical,)).fetchone()==(canonical,)
