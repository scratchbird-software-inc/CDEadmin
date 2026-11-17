"""Native all-channel replication and server reset commands; no loop emulation."""
import re
from .mariadb_server_diagnostics import form, target_uid
from . import mariadb_reviewed_server as lifecycle
from ...sdk import RelationalClientError
KEY='mariadb_all_channels'
OPERATIONS={op:(title,'')for op,title in (
 ('start_all_replicas','Start all replication connections'),('stop_all_replicas','Stop all replication connections'),
 ('reset_binary_logs','Reset native binary logs'),('reset_query_cache','Reset query cache'),
 ('reset_default_replica','Reset default replication connection'))}
INSPECTIONS=set()
WARNINGS=('START/STOP ALL SLAVES dispatches one native statement, not one command per channel. Acknowledgement is not replication health or catch-up proof.',
 'RESET MASTER removes binary-log history globally; replicas and backups may require it. Native reset is irreversible and does not reset gtid_slave_pos.',
 'RESET SLAVE affects only the default connection; ALL also removes its connection configuration. No passwords are returned.',
 'Native global effects cannot be rolled back. Independent connection, no original-session settlement, no replay.')

def compile_operation(operation,draft,target):
 target_uid(target)
 if operation not in OPERATIONS or not isinstance(draft,dict):raise RelationalClientError('Select a native replication/reset operation')
 allowed={'confirmation'}
 if operation in {'start_all_replicas','stop_all_replicas'}:allowed.add('threads')
 if operation=='reset_binary_logs':allowed|={'next_log_number','history_loss_confirmed'}
 if operation=='reset_default_replica':allowed|={'remove_configuration','configuration_loss_confirmed'}
 if set(draft)-allowed or draft.get('confirmation')!=target.get('display_name'):raise RelationalClientError('Confirm the exact server and native reset fields')
 if operation in {'start_all_replicas','stop_all_replicas'}:
  threads=draft.get('threads','ALL')
  if threads not in {'ALL','IO_THREAD','SQL_THREAD'}:raise RelationalClientError('Select native replication threads')
  sql=('START'if operation=='start_all_replicas'else'STOP')+' ALL SLAVES'+(''if threads=='ALL'else' '+threads)
 elif operation=='reset_binary_logs':
  if draft.get('history_loss_confirmed')is not True:raise RelationalClientError('Confirm irreversible binary-log history loss')
  number=draft.get('next_log_number','');sql='RESET MASTER'
  if number:
   if not isinstance(number,str)or not re.fullmatch('[1-9][0-9]{0,9}',number)or int(number)>2147483647:raise RelationalClientError('Use an exact positive native binary-log number through 2147483647')
   sql+=' TO '+number
 elif operation=='reset_default_replica':
  remove=draft.get('remove_configuration',False)
  if type(remove)is not bool or type(draft.get('configuration_loss_confirmed',False))is not bool:raise RelationalClientError('Use Boolean reset choices')
  if remove and draft.get('configuration_loss_confirmed')is not True:raise RelationalClientError('Confirm default connection configuration loss')
  # Explicit empty connection prevents an inherited default_master_connection from redirecting reset.
  sql="RESET SLAVE ''"+(' ALL'if remove else'')
 else:sql='RESET QUERY CACHE'
 return lifecycle.pack(__import__(__name__,fromlist=['']),operation,draft,target,sql,implicit_commit=True)

def observe(cursor,intent):
 cursor.execute('SHOW ALL SLAVES STATUS');columns=[v[0]for v in cursor.description or ()];rows=cursor.fetchall()
 if len(rows)>20000:raise RelationalClientError('Replication inventory exceeds the native observation budget')
 selected=('Connection_name','Master_Host','Master_Port','Master_User','Using_Gtid')
 if any(key not in columns for key in selected):raise RelationalClientError('Native replication topology columns unavailable')
 # Dynamic health/counters deliberately excluded from review equality; topology is rechecked before dispatch.
 result={'connections':sorted([[row[columns.index(key)]for key in selected]for row in rows],key=lambda row:row[0]),'replication_health_attested':False}
 if intent['operation']=='reset_binary_logs':
  cursor.execute('SHOW BINARY LOGS');result['binary_log_names']=[row[0]for row in cursor.fetchall()]
  cursor.execute('SELECT @@GLOBAL.log_bin,@@GLOBAL.gtid_slave_pos');row=cursor.fetchone();result.update(log_bin=bool(row[0]),gtid_slave_pos=row[1])
 if intent['operation']=='reset_query_cache':
  cursor.execute('SELECT @@GLOBAL.query_cache_size,@@GLOBAL.query_cache_type');result['query_cache_settings']=list(cursor.fetchone())
 return result

def reported_success(intent,columns,rows):return True
def bind_review(client,planned):return lifecycle.bind_review(__import__(__name__,fromlist=['']),client,planned)
def apply(client,request,connection=None):return lifecycle.apply(__import__(__name__,fromlist=['']),client,request,connection)
