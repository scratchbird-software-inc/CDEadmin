"""Exact MySQL role membership identities and native default-role statements."""
from ..sdk.relational import RelationalClientError

OPERATIONS = frozenset({'grant', 'revoke', 'set_default'})


def account(user, host):
    if not isinstance(user, str) or not isinstance(host, str) or not host or '\x00' in user + host:
        raise RelationalClientError('MySQL account requires separate native user and host values')
    # Account names accept quoted identifiers. Backtick escaping is independent
    # of NO_BACKSLASH_ESCAPES and ANSI_QUOTES; an anonymous user is literal ''.
    return (('`' + user.replace('`', '``') + '`') if user else "''") + '@`' + host.replace('`', '``') + '`'


def compile_operation(operation, draft, target):
    if operation not in OPERATIONS or not isinstance(draft, dict):
        raise RelationalClientError('MySQL role operation is unavailable')
    allowed = {'member_user', 'member_host', 'confirmation'} | (
        {'admin_option'} if operation == 'grant' else {'mode'} if operation == 'set_default' else set())
    if set(draft) - allowed:
        raise RelationalClientError('Unknown MySQL role membership option')
    native = (target or {}).get('native', {})
    if not native:
        native = (target or {}).get('extensions', {}).get('mysql', {}).get('native', {})
    role = account(native.get('user'), native.get('host'))
    member = account(draft.get('member_user'), draft.get('member_host', '%'))
    if operation == 'grant':
        option = draft.get('admin_option', False)
        if type(option) is not bool:raise RelationalClientError('Admin option must be boolean')
        source = f'GRANT {role} TO {member}' + (' WITH ADMIN OPTION' if option else '')
    elif operation == 'revoke':
        source = f'REVOKE {role} FROM {member}'
    else:
        mode = draft.get('mode', 'SELECTED')
        if mode not in {'SELECTED', 'ALL', 'NONE'}:raise RelationalClientError('Default role mode is invalid')
        source = f'SET DEFAULT ROLE {role if mode == "SELECTED" else mode} TO {member}'
    return {'source': source, 'parameters': ()}


def form(operation, field):
    fields = [field('member_user', 'Recipient user', 'text', False,
                    'Enter the exact username separately from its host; blank selects the anonymous account.', default=''),
              field('member_host', 'Recipient host', 'text', True, default='%')]
    if operation == 'grant':
        fields.append(field('admin_option', 'Allow role delegation', 'boolean', default=False))
    if operation == 'set_default':
        fields.append(field('mode', 'Default role set', 'select', True, default='SELECTED',
                            options=('SELECTED', 'ALL', 'NONE'),
                            help_text='Replaces the existing default role set. Does not grant membership.'))
    if operation in {'revoke', 'set_default'}:
        fields.append(field('confirmation', 'Confirmation', 'text', True))
    return {'form_id': 'mysql.role.' + operation,
            'title': {'grant': 'Grant MySQL role membership', 'revoke': 'Revoke MySQL role membership',
                      'set_default': 'Replace MySQL default role set'}[operation], 'fields': fields}
