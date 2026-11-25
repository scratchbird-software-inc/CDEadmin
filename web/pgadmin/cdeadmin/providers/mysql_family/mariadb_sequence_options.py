"""Exact native MariaDB sequence options shared by administration and DDN."""
import re
from ...sdk import RelationalClientError
TYPES=('TINYINT','SMALLINT','MEDIUMINT','INT','BIGINT')
KEYS={'integer_type','unsigned','start','increment','minimum','maximum','minimum_mode','maximum_mode','cache','cycle_mode','restart','restart_initial','confirmation','comment','or_replace','if_not_exists','temporary'}

def _sql_literal(text):
 if not isinstance(text,str):raise RelationalClientError('Sequence comment must be text')
 return "'" + text.replace("'", "''") + "'"

def clauses(options,alter=False,name=None,allow_empty_for_comment=False):
 if not isinstance(options,dict)or set(options)-KEYS:raise RelationalClientError('Select only typed native sequence options')
 result=[]
 typ=options.get('integer_type','')
 unsigned=options.get('unsigned',False)
 if type(unsigned)is not bool or unsigned and not typ:raise RelationalClientError('Unsigned requires an explicit native integer type')
 if typ:
  if typ not in TYPES:raise RelationalClientError('Select a native sequence integer type')
  result.append('AS '+typ+(' UNSIGNED'if unsigned else' SIGNED'))
 def integer(key,signed=False):
  value=options[key]
  if type(value)is int:value=str(value)
  if not isinstance(value,str)or not re.fullmatch('-?(?:0|[1-9][0-9]{0,19})',value)or not -(2**63)<=int(value)<=(2**63-1 if signed else 2**64-1):raise RelationalClientError('Use exact bounded native decimal text for '+key)
  return value
 for key,prefix in [('start','START WITH '),('increment','INCREMENT BY '),('cache','CACHE ')]:
  if key in options and options[key]not in (None,''):
   if key=='cache' and str(options[key]).strip()=='0':
    result.append('NOCACHE' if not alter else 'CACHE 0')
   else:
    result.append(prefix+integer(key,key in {'increment','cache'}))
 for key in ('minimum','maximum'):
  mode=options.get(key+'_mode','VALUE'if options.get(key)not in(None,'')else'PRESERVE')
  if mode not in {'PRESERVE','VALUE','NATIVE'}:raise RelationalClientError('Select preserve, exact value or native sequence bound')
  if mode=='VALUE':
   if options.get(key)in(None,''):raise RelationalClientError('Supply the exact native sequence bound')
   result.append(('MINVALUE 'if key=='minimum'else'MAXVALUE ')+integer(key))
  elif options.get(key)not in(None,''):raise RelationalClientError('Omit bound value unless VALUE is selected')
  elif mode=='NATIVE':result.append('NO MINVALUE'if key=='minimum'else'NO MAXVALUE')
 cycle=options.get('cycle_mode','PRESERVE')
 if cycle not in {'PRESERVE','CYCLE','NOCYCLE'}:raise RelationalClientError('Select native sequence cycling intent')
 if cycle!='PRESERVE':result.append(cycle)
 initial=options.get('restart_initial',False)
 if type(initial)is not bool:raise RelationalClientError('Use Boolean native restart intent')
 restart=options.get('restart')not in(None,'')
 if initial or restart:
  if not alter or initial and restart or options.get('confirmation')!=name:raise RelationalClientError('Confirm the exact sequence name and select one native restart mode')
  result.append('RESTART'if initial else'RESTART WITH '+integer('restart'))
 elif options.get('confirmation')not in(None,''):raise RelationalClientError('Restart confirmation requires restart intent')
 if not alter and options.get('comment')not in(None,''):
  result.append('COMMENT = '+_sql_literal(options['comment']))
 if alter and typ and len(result)!=1:raise RelationalClientError('Native ALTER SEQUENCE AS cannot combine type and other options; review the native operations separately')
 if alter and not result and not allow_empty_for_comment:raise RelationalClientError('Select at least one native sequence change')
 return ' '.join(result)
