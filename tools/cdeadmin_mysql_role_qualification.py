"""Native role edge/default-role qualification; credentials never enter evidence."""
import argparse,json,secrets,sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import config  # noqa: F401 - initialize application configuration before providers
import mysql.connector
from pgadmin.cdeadmin.providers.mysql_roles import account
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION
parser=argparse.ArgumentParser(description='Qualify MySQL role plans on an isolated native 9.7 server')
parser.add_argument('--connection-json',required=True,help='Private JSON file of mysql.connector connection options')
parser.add_argument('--output-root',type=Path,required=True)
options=parser.parse_args()
base=options.output_root;base.mkdir(parents=True,exist_ok=True)
connection_options=json.loads(Path(options.connection_json).read_text())
conn=mysql.connector.connect(**{**connection_options,'autocommit':True})
cur=conn.cursor();token=secrets.token_hex(4);role='sr_r_'+token+'@`\\é';member='sr_u_'+token+"@'`\\";host='%'
proof={'passed':False};statements={};target={'resource_kind':'role','display_name':role+'@'+host,'native':{'user':role,'host':host}}
try:
 cur.execute('SELECT VERSION()');assert str(cur.fetchone()[0]).split('-')[0]=='9.7.0'
 cur.execute('CREATE ROLE '+account(role,host));cur.execute('CREATE USER '+account(member,host)+' IDENTIFIED BY %s',(secrets.token_urlsafe(30),))
 for mode in ('','NO_BACKSLASH_ESCAPES,ANSI_QUOTES'):
  conn.sql_mode=mode
  for operation,draft in [('grant',{'admin_option':True}),('set_default',{'mode':'SELECTED'}),('set_default',{'mode':'ALL'}),('set_default',{'mode':'NONE'}),('revoke',{})]:
   request={'resource_kind':'role','operation_id':operation,'target_resource':target,'draft':{'member_user':member,'member_host':host,**draft},'_provider_route':{'host':connection_options.get('host','localhost'),'port':connection_options.get('port',3306)}}
   assert not MYSQL_ADMINISTRATION.validate(request)['errors']
   planned=MYSQL_ADMINISTRATION.plan(request);source=planned['command_preview']['statements'][0]['source'];cur.execute(source)
   from tools.mysql_task_evidence import record
   record(proof,request)
   statements.setdefault(operation,source)
   if operation=='grant':
    cur.execute('SELECT WITH_ADMIN_OPTION FROM mysql.role_edges WHERE FROM_USER=%s AND FROM_HOST=%s AND TO_USER=%s AND TO_HOST=%s',(role,host,member,host));assert cur.fetchone()[0]=='Y'
   if operation=='set_default':
    cur.execute('SELECT DEFAULT_ROLE_USER FROM mysql.default_roles WHERE USER=%s AND HOST=%s',(member,host));rows=cur.fetchall();assert rows==([] if draft['mode']=='NONE' else [(role,)])
   if operation=='revoke':
    cur.execute('SELECT COUNT(*) FROM mysql.role_edges WHERE FROM_USER=%s AND TO_USER=%s',(role,member));assert cur.fetchone()[0]==0
 # Prove that the schema does not admit MariaDB-only admin-option revocation.
 try:cur.execute('REVOKE ADMIN OPTION FOR '+account(role,host)+' FROM '+account(member,host))
 except mysql.connector.Error as error:assert error.errno==1064
 else:raise AssertionError('Unexpected MySQL syntax acceptance')
 proof.update(passed=True,statements=statements,checks=['native generated-operation plans','exact user/host with @ quote backtick and backslash','default sql_mode and NO_BACKSLASH_ESCAPES/ANSI_QUOTES','grant WITH ADMIN OPTION','SELECTED/ALL/NONE default replacement','membership revoke','MariaDB-only revoke syntax refused'])
finally:
 cur.execute('DROP USER IF EXISTS '+account(member,host));cur.execute('DROP ROLE IF EXISTS '+account(role,host));cur.close();conn.close();proof['temporary_accounts_removed']=True
 (base/'summary.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False))
