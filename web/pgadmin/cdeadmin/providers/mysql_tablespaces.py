"""Native InnoDB general/undo tablespace lifecycle with bound file paths."""
import json
from ..sdk.relational import RelationalClientError

OPERATIONS = frozenset({'create', 'alter', 'rename', 'drop'})


def identifier(value):
    if not isinstance(value, str) or not value or len(value) > 64 or '\x00' in value:
        raise RelationalClientError('Native tablespace name requires 1 to 64 characters without NUL')
    return '`' + value.replace('`', '``') + '`'


def compile_operation(operation, draft, target):
    if operation not in OPERATIONS or not isinstance(draft, dict): raise RelationalClientError('Native tablespace operation is unavailable')
    allowed = {'confirmation'} | {'create': {'name','space_type','datafile','file_block_size','autoextend_size','encryption','engine_attribute'},
        'alter': {'change','autoextend_size','encryption','engine_attribute'}, 'rename': {'new_name'}, 'drop': set()}[operation]
    if set(draft) - allowed: raise RelationalClientError('Unknown native tablespace option')
    native = (target or {}).get('native') or (target or {}).get('extensions', {}).get('mysql', {}).get('native', {})
    space_type = draft.get('space_type','General') if operation == 'create' else native.get('space_type')
    if space_type not in {'General','Undo'}: raise RelationalClientError('Only native InnoDB General/Undo spaces are admitted')
    if operation != 'create' and native.get('engine') != 'InnoDB': raise RelationalClientError('Select a native InnoDB tablespace')
    name = draft.get('name') if operation == 'create' else (target or {}).get('display_name')
    quoted = identifier(name)
    subject = ('UNDO ' if space_type == 'Undo' else '') + 'TABLESPACE ' + quoted
    parameters = []
    if operation == 'drop':
        if name.lower() in {'innodb_undo_001','innodb_undo_002'}: raise RelationalClientError('Default native undo spaces cannot be removed')
        return {'source':'DROP '+subject+(' ENGINE=InnoDB' if space_type=='Undo' else ''),'parameters':()}
    if operation == 'rename':
        if space_type != 'General': raise RelationalClientError('Undo tablespace rename is unavailable')
        return {'source':'ALTER '+subject+' RENAME TO '+identifier(draft.get('new_name')),'parameters':()}
    if operation == 'create':
        datafile = draft.get('datafile')
        if not isinstance(datafile,str) or not datafile or '\x00' in datafile or len(datafile.encode('utf8'))>4096:
            raise RelationalClientError('Native datafile path requires bounded text without NUL')
        source = 'CREATE '+subject+' ADD DATAFILE %s'
        parameters.append(datafile)
        if space_type == 'Undo':
            if any(draft.get(key) not in (None,'','UNCHANGED') for key in ('file_block_size','autoextend_size','encryption','engine_attribute')):
                raise RelationalClientError('Undo creation does not accept general-tablespace options')
            return {'source':source+' ENGINE=InnoDB','preview_source':'CREATE '+subject+' ADD DATAFILE <bound-path> ENGINE=InnoDB','parameters':tuple(parameters)}
        block_size=draft.get('file_block_size')
        if block_size not in (None,''):
            if type(block_size) is not int or block_size not in {1024,2048,4096,8192,16384,32768,65536}: raise RelationalClientError('FILE_BLOCK_SIZE must be a native power-of-two byte size')
            source+=' FILE_BLOCK_SIZE='+str(block_size)
        changes=[key for key in ('autoextend_size','encryption','engine_attribute') if draft.get(key) not in (None,'','UNCHANGED')]
    else:
        change=draft.get('change')
        if 'available_tablespace_changes' in native and change not in native['available_tablespace_changes']:
            raise RelationalClientError('Selected change is unavailable for this native tablespace/runtime')
        if space_type=='Undo':
            if change not in {'ACTIVE','INACTIVE'} or any(key in draft for key in ('autoextend_size','encryption','engine_attribute')):
                raise RelationalClientError('Undo alteration requires native ACTIVE or INACTIVE')
            return {'source':'ALTER '+subject+' SET '+change+' ENGINE=InnoDB','parameters':()}
        if change not in {'AUTOEXTEND_SIZE','ENCRYPTION','ENGINE_ATTRIBUTE'}: raise RelationalClientError('Select a native general-tablespace change')
        changes=[change.lower()]
        if any(key in draft for key in {'autoextend_size','encryption','engine_attribute'}-set(changes)):
            raise RelationalClientError('Alter exactly the selected native tablespace setting')
        source='ALTER '+subject
    for key in changes:
        value=draft.get(key)
        if key=='autoextend_size':
            if type(value) is not int or value<0 or value>2**53-1 or value%(4*1024*1024): raise RelationalClientError('AUTOEXTEND_SIZE requires zero or a safe integer multiple of 4 MiB')
            source+=' AUTOEXTEND_SIZE='+str(value)
        elif key=='encryption':
            if value not in {'Y','N'}: raise RelationalClientError('Native encryption state is Y or N')
            source+=" ENCRYPTION='"+value+"'"
        else:
            if not isinstance(value,str) or len(value.encode('utf8'))>65536 or '\x00' in value: raise RelationalClientError('ENGINE_ATTRIBUTE requires bounded JSON text')
            try: json.loads(value)
            except (ValueError,TypeError): raise RelationalClientError('ENGINE_ATTRIBUTE requires valid JSON text') from None
            source+=' ENGINE_ATTRIBUTE=%s'
            parameters.append(value)
    if operation=='create':source+=' ENGINE=InnoDB'
    return {'source':source,'preview_source':source.replace('%s','<bound-value>'),'parameters':tuple(parameters)}


def form(operation,field):
    fields=[]
    if operation=='create':
        fields += [field('name','Tablespace name','text',True),field('space_type','Native InnoDB space type','select',True,default='General',options=('General','Undo')),
                   field('datafile','Native server datafile path','text',True)]
        fields.append({**field('file_block_size','FILE_BLOCK_SIZE (bytes)','integer'), 'visible_when':{'field_id':'space_type','equals':'General'}})
    if operation=='alter':fields.append({**field('change','Native tablespace change','select',True,options=('AUTOEXTEND_SIZE','ENCRYPTION','ENGINE_ATTRIBUTE','ACTIVE','INACTIVE')), 'option_values_path':['available_tablespace_changes']})
    if operation in {'create','alter'}:
        for key,label,control in [('autoextend_size','AUTOEXTEND_SIZE (bytes)','integer'),('encryption','Encryption','select'),('engine_attribute','ENGINE_ATTRIBUTE JSON','multiline')]:
            value=field(key,label,control,default='UNCHANGED' if key=='encryption' else None,options=('UNCHANGED','Y','N') if key=='encryption' else None)
            value['visible_when']={'field_id':'space_type','equals':'General'} if operation=='create' else {'field_id':'change','equals':key.upper()}
            fields.append(value)
    if operation=='rename':fields.append(field('new_name','New native tablespace name','text',True))
    if operation!='create':fields.append(field('confirmation','Confirmation','text',True))
    return {'form_id':'mysql.tablespace.'+operation,'title':operation.title()+' native InnoDB tablespace','fields':fields}
