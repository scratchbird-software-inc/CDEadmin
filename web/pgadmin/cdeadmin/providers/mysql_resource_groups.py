"""Structured native MySQL resource-group operations and exact thread identities."""
import re
from ..sdk.relational import RelationalClientError

OPERATIONS = frozenset({'create', 'alter', 'assign', 'drop'})


def identifier(value):
    if not isinstance(value, str) or not value or '\x00' in value or len(value) > 64:
        raise RelationalClientError('Resource-group name requires 1 to 64 characters without NUL')
    return '`' + value.replace('`', '``') + '`'


def compile_operation(operation, draft, target):
    if operation not in OPERATIONS or not isinstance(draft, dict):
        raise RelationalClientError('MySQL resource-group operation is unavailable')
    allowed = {'confirmation'} | {'create': {'name', 'resource_type', 'vcpu', 'priority', 'enabled'},
        'alter': {'vcpu', 'priority', 'state', 'force'}, 'assign': {'thread_ids'}, 'drop': {'force'}}[operation]
    if set(draft) - allowed: raise RelationalClientError('Unknown resource-group option')
    name = draft.get('name') if operation == 'create' else (target or {}).get('display_name')
    quoted = identifier(name)
    if operation == 'drop' and name.lower() in {'usr_default', 'sys_default'}:
        raise RelationalClientError('Native default resource groups cannot be removed')
    force = draft.get('force', False)
    if type(force) is not bool: raise RelationalClientError('Resource-group FORCE must be boolean')
    if operation == 'drop': return {'source': 'DROP RESOURCE GROUP ' + quoted + (' FORCE' if force else ''), 'parameters': ()}
    if operation == 'assign':
        values = draft.get('thread_ids')
        if not isinstance(values, list) or not 1 <= len(values) <= 256:
            raise RelationalClientError('Select 1 to 256 distinct native performance_schema thread IDs')
        exact = []
        for value in values:
            if type(value) is int and 1 <= value <= 2**53-1:
                exact.append(str(value))
            elif isinstance(value, str) and re.fullmatch(r'[1-9][0-9]{0,19}', value) and int(value) <= 2**64-1:
                exact.append(value)
            else:
                raise RelationalClientError('Native thread IDs require exact positive decimal strings or safe JSON integers')
        if len(set(exact)) != len(exact): raise RelationalClientError('Native thread IDs must be distinct')
        return {'source': 'SET RESOURCE GROUP ' + quoted + ' FOR ' + ','.join(exact), 'parameters': ()}
    source = ('CREATE' if operation == 'create' else 'ALTER') + ' RESOURCE GROUP ' + quoted
    if operation == 'create':
        resource_type = draft.get('resource_type', 'USER')
        if resource_type not in {'USER', 'SYSTEM'}: raise RelationalClientError('Native resource-group type is USER or SYSTEM')
        source += ' TYPE=' + resource_type
    vcpu = draft.get('vcpu', '')
    if not isinstance(vcpu, str) or len(vcpu) > 4096: raise RelationalClientError('VCPU selection must be bounded numeric ranges')
    if vcpu.strip():
        values = []
        for value in vcpu.split(','):
            if not re.fullmatch(r'\s*\d+(?:\s*-\s*\d+)?\s*', value): raise RelationalClientError('VCPU selection accepts numbers and ranges separated by commas')
            bounds = [int(part) for part in value.split('-')]
            if any(part > 65535 for part in bounds) or bounds[0] > bounds[-1]: raise RelationalClientError('Invalid VCPU range')
            values.append('-'.join(str(part) for part in bounds))
        source += ' VCPU=' + ','.join(values)
    priority = draft.get('priority')
    if priority not in (None, ''):
        if type(priority) is not int or not -20 <= priority <= 19: raise RelationalClientError('Native thread priority must be an integer from -20 to 19')
        source += ' THREAD_PRIORITY=' + str(priority)
    if operation == 'create':
        enabled = draft.get('enabled', True)
        if type(enabled) is not bool: raise RelationalClientError('Resource-group enabled state must be boolean')
        source += ' ENABLE' if enabled else ' DISABLE'
    else:
        state = draft.get('state', 'UNCHANGED')
        if state not in {'UNCHANGED', 'ENABLE', 'DISABLE'}: raise RelationalClientError('Invalid resource-group state')
        if force and state != 'DISABLE': raise RelationalClientError('FORCE alteration requires explicit DISABLE')
        if state != 'UNCHANGED': source += ' ' + state
        if not vcpu.strip() and priority in (None, '') and state == 'UNCHANGED': raise RelationalClientError('Select a native resource-group change')
        if force: source += ' FORCE'
    return {'source': source, 'parameters': ()}


def form(operation, field):
    fields = []
    if operation == 'create':
        fields += [field('name', 'Resource-group name', 'text', True),
                   field('resource_type', 'Native group type', 'select', True, default='USER', options=('USER', 'SYSTEM'))]
    if operation in {'create', 'alter'}:
        fields += [field('vcpu', 'VCPU numbers/ranges', 'text', default='', help_text='Comma-separated native CPU numbers or ranges; blank preserves native selection.'),
                   field('priority', 'Native thread priority', 'integer', help_text='USER: 0 to 19; SYSTEM: -20 to 0. Blank preserves the native value.')]
        if operation == 'create': fields.append(field('enabled', 'Enabled', 'boolean', default=True))
        else: fields.append(field('state', 'Enabled state', 'select', default='UNCHANGED', options=('UNCHANGED', 'ENABLE', 'DISABLE')))
    if operation in {'alter', 'drop'}: fields.append(field('force', 'Force assigned threads to default group', 'boolean', default=False))
    if operation != 'create': fields.append(field('confirmation', 'Confirmation', 'text', True))
    return {'form_id': 'mysql.resource-group.' + operation, 'title': operation.title() + ' MySQL resource group', 'fields': fields}
