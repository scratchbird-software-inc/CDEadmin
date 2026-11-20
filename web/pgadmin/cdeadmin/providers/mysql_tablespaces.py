"""Native InnoDB general/undo and NDB Cluster tablespace lifecycle with bound file paths."""
import json
from ..sdk.relational import RelationalClientError

OPERATIONS = frozenset({'create', 'alter', 'rename', 'drop'})


def identifier(value):
    if not isinstance(value, str) or not value or len(value) > 64 or '\x00' in value:
        raise RelationalClientError('Native tablespace name requires 1 to 64 characters without NUL')
    return '`' + value.replace('`', '``') + '`'


def _bounded_path(datafile, label='datafile'):
    if not isinstance(datafile, str) or not datafile or '\x00' in datafile or len(datafile.encode('utf8')) > 4096:
        raise RelationalClientError(f'Native {label} path requires bounded text without NUL')
    return datafile


def _positive_bytes(val, field_name):
    if type(val) is not int or isinstance(val, bool) or val <= 0 or val > 2**53 - 1:
        raise RelationalClientError(f'{field_name} requires a positive integer byte size')
    return val


def _compile_ndb_tablespace(operation, draft, target, quoted_name):
    subject = 'TABLESPACE ' + quoted_name
    if operation == 'rename':
        raise RelationalClientError('NDB Cluster tablespaces do not support RENAME TABLESPACE')
    if operation == 'drop':
        return {
            'source': f'DROP {subject}',
            'parameters': (),
            'ndb_required': True,
        }
    if operation == 'create':
        datafile = _bounded_path(draft.get('datafile'))
        lg_name = draft.get('logfile_group')
        if not lg_name:
            raise RelationalClientError('NDB Cluster tablespace creation requires USE LOGFILE GROUP')
        quoted_lg = identifier(lg_name)
        for bad in ('file_block_size', 'encryption', 'engine_attribute'):
            if draft.get(bad) not in (None, '', 'UNCHANGED'):
                raise RelationalClientError(f'NDB Cluster tablespace creation does not accept InnoDB {bad.upper()}')
        source = f'CREATE {subject} ADD DATAFILE %s USE LOGFILE GROUP {quoted_lg}'
        preview = f'CREATE {subject} ADD DATAFILE <bound-path> USE LOGFILE GROUP {quoted_lg}'
        params = [datafile]
        for key, clause in (
            ('extent_size', 'EXTENT_SIZE'),
            ('initial_size', 'INITIAL_SIZE'),
            ('autoextend_size', 'AUTOEXTEND_SIZE'),
            ('max_size', 'MAX_SIZE'),
        ):
            val = draft.get(key)
            if val not in (None, ''):
                size_val = _positive_bytes(val, clause)
                source += f' {clause}={size_val}'
                preview += f' {clause}={size_val}'
        nodegroup = draft.get('nodegroup')
        if nodegroup not in (None, ''):
            if type(nodegroup) is not int or isinstance(nodegroup, bool) or not (0 <= nodegroup <= 65535):
                raise RelationalClientError('NODEGROUP requires an integer from 0 to 65535')
            source += f' NODEGROUP={nodegroup}'
            preview += f' NODEGROUP={nodegroup}'
        comment = draft.get('comment')
        if comment not in (None, ''):
            if not isinstance(comment, str) or '\x00' in comment or len(comment) > 2048:
                raise RelationalClientError('COMMENT requires bounded text without NUL')
            source += ' COMMENT=%s'
            preview += ' COMMENT=<bound-value>'
            params.append(comment)
        source += ' ENGINE=NDBCLUSTER'
        preview += ' ENGINE=NDBCLUSTER'
        return {'source': source, 'preview_source': preview, 'parameters': tuple(params), 'ndb_required': True}

    # operation == 'alter'
    change = draft.get('change')
    if change not in {'ADD_DATAFILE', 'DROP_DATAFILE'}:
        raise RelationalClientError('NDB Cluster tablespace alteration requires ADD_DATAFILE or DROP_DATAFILE')
    datafile = _bounded_path(draft.get('datafile'))
    params = [datafile]
    action_sql = 'ADD DATAFILE' if change == 'ADD_DATAFILE' else 'DROP DATAFILE'
    source = f'ALTER {subject} {action_sql} %s'
    preview = f'ALTER {subject} {action_sql} <bound-path>'
    if change == 'ADD_DATAFILE' and draft.get('initial_size') not in (None, ''):
        init_sz = _positive_bytes(draft['initial_size'], 'INITIAL_SIZE')
        source += f' INITIAL_SIZE={init_sz}'
        preview += f' INITIAL_SIZE={init_sz}'
    elif change == 'DROP_DATAFILE' and draft.get('initial_size') not in (None, ''):
        raise RelationalClientError('DROP DATAFILE does not accept INITIAL_SIZE')
    if change == 'ADD_DATAFILE':
        source += ' ENGINE=NDBCLUSTER'
        preview += ' ENGINE=NDBCLUSTER'
    return {'source': source, 'preview_source': preview, 'parameters': tuple(params), 'ndb_required': True}


def compile_operation(operation, draft, target):
    if operation not in OPERATIONS or not isinstance(draft, dict):
        raise RelationalClientError('Native tablespace operation is unavailable')
    allowed = {'confirmation'} | {
        'create': {
            'name', 'space_type', 'datafile', 'file_block_size', 'autoextend_size',
            'encryption', 'engine_attribute', 'logfile_group', 'extent_size',
            'initial_size', 'max_size', 'nodegroup', 'comment',
        },
        'alter': {
            'change', 'autoextend_size', 'encryption', 'engine_attribute',
            'datafile', 'initial_size',
        },
        'rename': {'new_name'},
        'drop': set(),
    }[operation]
    if set(draft) - allowed:
        raise RelationalClientError('Unknown native tablespace option')
    native = (target or {}).get('native') or (target or {}).get('extensions', {}).get('mysql', {}).get('native', {})
    engine_name = str(native.get('engine') or '')
    is_ndb_target = engine_name.lower() == 'ndbcluster' or native.get('space_type') == 'NDB'
    space_type = (
        draft.get('space_type', 'General')
        if operation == 'create'
        else ('NDB' if is_ndb_target else native.get('space_type'))
    )
    name = draft.get('name') if operation == 'create' else (target or {}).get('display_name')
    quoted = identifier(name)

    if space_type == 'NDB':
        return _compile_ndb_tablespace(operation, draft, target, quoted)

    if space_type not in {'General', 'Undo'}:
        raise RelationalClientError('Only native InnoDB General/Undo or NDB Cluster spaces are admitted')
    if operation != 'create' and engine_name != 'InnoDB':
        raise RelationalClientError('Select a native InnoDB or NDB Cluster tablespace')

    subject = ('UNDO ' if space_type == 'Undo' else '') + 'TABLESPACE ' + quoted
    parameters = []
    if operation == 'drop':
        if name.lower() in {'innodb_undo_001', 'innodb_undo_002'}:
            raise RelationalClientError('Default native undo spaces cannot be removed')
        return {'source': 'DROP ' + subject + (' ENGINE=InnoDB' if space_type == 'Undo' else ''), 'parameters': ()}
    if operation == 'rename':
        if space_type != 'General':
            raise RelationalClientError('Undo tablespace rename is unavailable')
        return {'source': 'ALTER ' + subject + ' RENAME TO ' + identifier(draft.get('new_name')), 'parameters': ()}
    if operation == 'create':
        for ndb_only in ('logfile_group', 'extent_size', 'initial_size', 'max_size', 'nodegroup', 'comment'):
            if draft.get(ndb_only) not in (None, ''):
                raise RelationalClientError(f'{ndb_only.upper()} applies only to NDB Cluster tablespaces')
        datafile = _bounded_path(draft.get('datafile'))
        source = 'CREATE ' + subject + ' ADD DATAFILE %s'
        parameters.append(datafile)
        if space_type == 'Undo':
            if any(draft.get(key) not in (None, '', 'UNCHANGED') for key in ('file_block_size', 'autoextend_size', 'encryption', 'engine_attribute')):
                raise RelationalClientError('Undo creation does not accept general-tablespace options')
            return {
                'source': source + ' ENGINE=InnoDB',
                'preview_source': 'CREATE ' + subject + ' ADD DATAFILE <bound-path> ENGINE=InnoDB',
                'parameters': tuple(parameters),
            }
        block_size = draft.get('file_block_size')
        if block_size not in (None, ''):
            if type(block_size) is not int or block_size not in {1024, 2048, 4096, 8192, 16384, 32768, 65536}:
                raise RelationalClientError('FILE_BLOCK_SIZE must be a native power-of-two byte size')
            source += ' FILE_BLOCK_SIZE=' + str(block_size)
        changes = [key for key in ('autoextend_size', 'encryption', 'engine_attribute') if draft.get(key) not in (None, '', 'UNCHANGED')]
    else:
        change = draft.get('change')
        if 'available_tablespace_changes' in native and change not in native['available_tablespace_changes']:
            raise RelationalClientError('Selected change is unavailable for this native tablespace/runtime')
        if space_type == 'Undo':
            if change not in {'ACTIVE', 'INACTIVE'} or any(key in draft for key in ('autoextend_size', 'encryption', 'engine_attribute')):
                raise RelationalClientError('Undo alteration requires native ACTIVE or INACTIVE')
            return {'source': 'ALTER ' + subject + ' SET ' + change + ' ENGINE=InnoDB', 'parameters': ()}
        if change not in {'AUTOEXTEND_SIZE', 'ENCRYPTION', 'ENGINE_ATTRIBUTE'}:
            raise RelationalClientError('Select a native general-tablespace change')
        changes = [change.lower()]
        if any(key in draft for key in {'autoextend_size', 'encryption', 'engine_attribute'} - set(changes)):
            raise RelationalClientError('Alter exactly the selected native tablespace setting')
        source = 'ALTER ' + subject
    for key in changes:
        value = draft.get(key)
        if key == 'autoextend_size':
            if type(value) is not int or value < 0 or value > 2**53 - 1 or value % (4 * 1024 * 1024):
                raise RelationalClientError('AUTOEXTEND_SIZE requires zero or a safe integer multiple of 4 MiB')
            source += ' AUTOEXTEND_SIZE=' + str(value)
        elif key == 'encryption':
            if value not in {'Y', 'N'}:
                raise RelationalClientError('Native encryption state is Y or N')
            source += " ENCRYPTION='" + value + "'"
        else:
            if not isinstance(value, str) or len(value.encode('utf8')) > 65536 or '\x00' in value:
                raise RelationalClientError('ENGINE_ATTRIBUTE requires bounded JSON text')
            try:
                json.loads(value)
            except (ValueError, TypeError):
                raise RelationalClientError('ENGINE_ATTRIBUTE requires valid JSON text') from None
            source += ' ENGINE_ATTRIBUTE=%s'
            parameters.append(value)
    if operation == 'create':
        source += ' ENGINE=InnoDB'
    return {'source': source, 'preview_source': source.replace('%s', '<bound-value>'), 'parameters': tuple(parameters)}


def form(operation, field):
    fields = []
    if operation == 'create':
        fields += [
            field('name', 'Tablespace name', 'text', True),
            field('space_type', 'Native space type', 'select', True, default='General', options=('General', 'Undo', 'NDB')),
            field('datafile', 'Native server datafile path', 'text', True),
        ]
        fields.append({**field('logfile_group', 'Logfile group', 'text'), 'visible_when': {'field_id': 'space_type', 'equals': 'NDB'}})
        fields.append({**field('initial_size', 'INITIAL_SIZE (bytes)', 'integer'), 'visible_when': {'field_id': 'space_type', 'equals': 'NDB'}})
        fields.append({**field('extent_size', 'EXTENT_SIZE (bytes)', 'integer'), 'visible_when': {'field_id': 'space_type', 'equals': 'NDB'}})
        fields.append({**field('max_size', 'MAX_SIZE (bytes)', 'integer'), 'visible_when': {'field_id': 'space_type', 'equals': 'NDB'}})
        fields.append({**field('nodegroup', 'NODEGROUP', 'integer'), 'visible_when': {'field_id': 'space_type', 'equals': 'NDB'}})
        fields.append({**field('comment', 'Comment', 'text'), 'visible_when': {'field_id': 'space_type', 'equals': 'NDB'}})
        fields.append({**field('file_block_size', 'FILE_BLOCK_SIZE (bytes)', 'integer'), 'visible_when': {'field_id': 'space_type', 'equals': 'General'}})
    if operation == 'alter':
        fields.append({
            **field(
                'change', 'Native tablespace change', 'select', True,
                options=('AUTOEXTEND_SIZE', 'ENCRYPTION', 'ENGINE_ATTRIBUTE', 'ACTIVE', 'INACTIVE', 'ADD_DATAFILE', 'DROP_DATAFILE'),
            ),
            'option_values_path': ['available_tablespace_changes'],
        })
        fields.append({**field('datafile', 'NDB datafile path', 'text'), 'visible_when': {'field_id': 'change', 'in': ['ADD_DATAFILE', 'DROP_DATAFILE']}})
        fields.append({**field('initial_size', 'INITIAL_SIZE (bytes)', 'integer'), 'visible_when': {'field_id': 'change', 'equals': 'ADD_DATAFILE'}})
    if operation in {'create', 'alter'}:
        for key, label, control in [
            ('autoextend_size', 'AUTOEXTEND_SIZE (bytes)', 'integer'),
            ('encryption', 'Encryption', 'select'),
            ('engine_attribute', 'ENGINE_ATTRIBUTE JSON', 'multiline'),
        ]:
            value = field(key, label, control, default='UNCHANGED' if key == 'encryption' else None, options=('UNCHANGED', 'Y', 'N') if key == 'encryption' else None)
            value['visible_when'] = {'field_id': 'space_type', 'equals': 'General'} if operation == 'create' else {'field_id': 'change', 'equals': key.upper()}
            fields.append(value)
    if operation == 'rename':
        fields.append(field('new_name', 'New native tablespace name', 'text', True))
    if operation != 'create':
        fields.append(field('confirmation', 'Confirmation', 'text', True))
    return {'form_id': 'mysql.tablespace.' + operation, 'title': operation.title() + ' native tablespace', 'fields': fields}
