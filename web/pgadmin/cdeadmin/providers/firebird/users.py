"""Firebird user replacement with secret-safe previews and plugin identity."""
from collections.abc import Mapping

from pgadmin.cdeadmin.navigator import resource_native
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from .character_metadata import identifier, literal, text

OPERATIONS = frozenset({'create_or_alter', 'recreate'})
WARNING = (
    'RECREATE replaces the account in its security database and plugin. '
    'Supply the intended credentials and attributes. Database privileges '
    'are name-based: recreation is not a substitute for revoking grants. '
    'Commit or roll back explicitly; existing connections are not reset.')


def inspected_plugin(target, requested=None):
    """Bind a selected account operation to its observed management plugin."""
    observed = resource_native(target).get('plugin')
    if observed and requested and observed != requested:
        raise RelationalClientError('Cannot redirect the user plugin')
    return observed or requested


def compile_operation(operation, draft, target=None):
    if (not isinstance(operation, str) or operation not in OPERATIONS or
            not isinstance(draft, Mapping)):
        raise RelationalClientError('Unknown Firebird user replacement task')
    key = 'name' if operation == 'create_or_alter' else 'confirmation'
    allowed = {key, 'password', 'plugin', 'first_name', 'middle_name',
               'last_name', 'admin_role', 'active_state', 'tags'}
    if set(draft) - allowed:
        raise RelationalClientError('Unknown Firebird user replacement fields')
    plugin = draft.get('plugin')
    if operation == 'recreate':
        if (not isinstance(target, Mapping) or
                target.get('resource_kind') != 'user'):
            raise RelationalClientError('An inspected user is required')
        name = target.get('display_name')
        if draft.get('confirmation') != name:
            raise RelationalClientError('Confirm the exact user name')
        inspected_plugin = resource_native(target).get('plugin')
        if inspected_plugin:
            if plugin and plugin != inspected_plugin:
                raise RelationalClientError('Cannot redirect the user plugin')
            plugin = inspected_plugin
        if not plugin:
            raise RelationalClientError(
                'The user management plugin is required')
    else:
        name = draft.get('name')
    command = ('CREATE OR ALTER' if operation == 'create_or_alter'
               else 'RECREATE') + ' USER ' + identifier(name)
    clauses, previews = [], []
    password = draft.get('password')
    if password is not None:
        text(password, 'Password')
        if not password:
            raise RelationalClientError('Password must not be empty')
        clauses.append('PASSWORD ' + literal(password))
        previews.append('PASSWORD <redacted>')
    elif operation == 'recreate':
        raise RelationalClientError('Recreation requires a new password')
    for field, keyword in (('first_name', 'FIRSTNAME'),
                           ('middle_name', 'MIDDLENAME'),
                           ('last_name', 'LASTNAME')):
        if field in draft:
            value = text(draft[field], 'User name component')
            clauses.append(keyword + ' ' + literal(value))
            previews.append(keyword + ' <redacted>')
    for field, options in (
        ('admin_role', {'GRANT': 'GRANT ADMIN ROLE',
                        'REVOKE': 'REVOKE ADMIN ROLE'}),
        ('active_state', {'ACTIVE': 'ACTIVE', 'INACTIVE': 'INACTIVE'}),
    ):
        value = draft.get(field, 'UNCHANGED')
        if value == 'UNCHANGED':
            continue
        if not isinstance(value, str) or value not in options:
            raise RelationalClientError('Invalid user ' + field)
        clauses.append(options[value])
        previews.append(options[value])
    tags = draft.get('tags', [])
    if not isinstance(tags, list):
        raise RelationalClientError('User tags must be a list')
    rendered, redacted = [], []
    for tag in tags:
        if (not isinstance(tag, Mapping) or
                set(tag) - {'name', 'value', 'drop'} or
                not isinstance(tag.get('drop', False), bool)):
            raise RelationalClientError('Invalid user tag')
        tag_name = tag.get('name')
        quoted = identifier(tag_name)
        if any(char in tag_name for char in '\r\n='):
            raise RelationalClientError('Tag names cannot contain CR, LF or =')
        if tag.get('drop', False):
            if 'value' in tag:
                raise RelationalClientError('Dropped tags cannot have a value')
            rendered.append('DROP ' + quoted)
            redacted.append('DROP ' + quoted)
        else:
            value = text(tag.get('value'), 'Tag value')
            if '\n' in value or '\r' in value:
                raise RelationalClientError(
                    'Tag values cannot contain CR or LF')
            rendered.append(quoted + ' = ' + literal(value))
            redacted.append(quoted + ' = <redacted>')
    if tags:
        clauses.append('TAGS (' + ', '.join(rendered) + ')')
        previews.append('TAGS (' + ', '.join(redacted) + ')')
    if not clauses:
        raise RelationalClientError('Specify at least one user attribute')
    if plugin:
        clauses.append('USING PLUGIN ' + identifier(plugin))
        previews.append('USING PLUGIN ' + identifier(plugin))
    return {'source': command + ' ' + ' '.join(clauses),
            'preview_source': command + ' ' + ' '.join(previews),
            'parameters': ()}


def compile_lifecycle_operation(operation, draft, target=None):
    """Compile Firebird CREATE USER / ALTER USER with name components, tags, and comment."""
    if operation not in {'create', 'alter'} or not isinstance(draft, Mapping):
        raise RelationalClientError('Unknown Firebird user lifecycle operation')
    allowed = {
        'name', 'password', 'plugin', 'first_name', 'middle_name', 'last_name',
        'administrator', 'active', 'description', 'tags', 'changes', 'options',
    }
    merged = dict(draft)
    for nested_key in ('options', 'changes'):
        if isinstance(merged.get(nested_key), Mapping):
            nested = dict(merged.pop(nested_key))
            nested.update(merged)
            merged = nested
    if set(merged) - allowed:
        raise RelationalClientError('Unknown Firebird user lifecycle fields')
    if operation == 'create':
        name = merged.get('name')
        plugin = merged.get('plugin') or None
    else:
        if not isinstance(target, Mapping) or target.get('resource_kind') != 'user':
            raise RelationalClientError('An inspected user is required')
        name = target.get('display_name') or merged.get('name')
        plugin = inspected_plugin(target, merged.get('plugin') or None)
    quoted_user = identifier(name)
    clauses, previews = [], []
    password = merged.get('password')
    if operation == 'create':
        if not isinstance(password, str) or not password:
            raise RelationalClientError('user password is required')
        clauses.append('PASSWORD ' + literal(password))
        previews.append("PASSWORD '<redacted>'")
    elif password is not None and password != '':
        text(password, 'Password')
        clauses.append('PASSWORD ' + literal(password))
        previews.append("PASSWORD '<redacted>'")
    for field_name, keyword in (
        ('first_name', 'FIRSTNAME'),
        ('middle_name', 'MIDDLENAME'),
        ('last_name', 'LASTNAME'),
    ):
        if field_name in merged and merged[field_name] is not None:
            val = text(str(merged[field_name]), 'User name component')
            clauses.append(keyword + ' ' + literal(val))
            previews.append(keyword + ' ' + literal(val))
    if operation == 'create':
        if merged.get('administrator'):
            clauses.append('GRANT ADMIN ROLE')
            previews.append('GRANT ADMIN ROLE')
        active_clause = 'ACTIVE' if merged.get('active', True) else 'INACTIVE'
        clauses.append(active_clause)
        previews.append(active_clause)
    else:
        if 'administrator' in merged and merged['administrator'] is not None:
            adm_clause = (
                'GRANT ADMIN ROLE' if merged['administrator']
                else 'REVOKE ADMIN ROLE'
            )
            clauses.append(adm_clause)
            previews.append(adm_clause)
        if 'active' in merged and merged['active'] is not None:
            act_clause = 'ACTIVE' if merged['active'] else 'INACTIVE'
            clauses.append(act_clause)
            previews.append(act_clause)
    tags = merged.get('tags')
    if tags is not None:
        if not isinstance(tags, list):
            raise RelationalClientError('User tags must be a list')
        rendered, redacted = [], []
        for tag in tags:
            if (not isinstance(tag, Mapping) or
                    set(tag) - {'name', 'value', 'drop'} or
                    not isinstance(tag.get('drop', False), bool)):
                raise RelationalClientError('Invalid user tag')
            tag_name = tag.get('name')
            quoted_tag = identifier(tag_name)
            if any(char in tag_name for char in '\r\n='):
                raise RelationalClientError('Tag names cannot contain CR, LF or =')
            if tag.get('drop', False):
                rendered.append('DROP ' + quoted_tag)
                redacted.append('DROP ' + quoted_tag)
            else:
                val = text(str(tag.get('value') or ''), 'Tag value')
                if '\n' in val or '\r' in val:
                    raise RelationalClientError('Tag values cannot contain CR or LF')
                rendered.append(quoted_tag + ' = ' + literal(val))
                redacted.append(quoted_tag + ' = ' + literal(val))
        if rendered:
            clauses.append('TAGS (' + ', '.join(rendered) + ')')
            previews.append('TAGS (' + ', '.join(redacted) + ')')
    plugin_suffix = (' USING PLUGIN ' + identifier(plugin)) if plugin else ''
    statements = []
    preview_statements = []
    if clauses:
        verb = 'CREATE USER ' if operation == 'create' else 'ALTER USER '
        statements.append(verb + quoted_user + ' ' + ' '.join(clauses) + plugin_suffix)
        preview_statements.append(verb + quoted_user + ' ' + ' '.join(previews) + plugin_suffix)
    if 'description' in merged and (operation == 'alter' or merged.get('description')):
        desc = merged.get('description')
        comment_rhs = 'NULL' if desc in (None, '') else literal(text(str(desc), 'Comment'))
        comment_sql = f'COMMENT ON USER {quoted_user}{plugin_suffix} IS {comment_rhs}'
        statements.append(comment_sql)
        preview_statements.append(comment_sql)
    if not statements:
        raise RelationalClientError('user alteration has no changes')
    return {
        'statements': [
            {'source': src, 'preview_source': prev, 'parameters': ()}
            for src, prev in zip(statements, preview_statements)
        ],
    }


def form(operation, field):
    if not isinstance(operation, str) or operation not in OPERATIONS:
        raise RelationalClientError('Unknown Firebird user replacement form')
    fields = []
    if operation == 'create_or_alter':
        fields.append(field('name', 'User name', 'text', True))
    fields.extend([
        field('password', 'New password', 'password', operation == 'recreate',
              'Required for recreation and creation by password plugins. '
              'Omit to retain an existing password when altering.',
              sensitive=True),
        field('plugin', 'User management plugin', 'text', False,
              'Recreation uses the inspected plugin; no redirection.'),
    ])
    for name in ('first_name', 'middle_name', 'last_name'):
        fields.append(field(name, name.replace('_', ' ').title(),
                            'text', False))
    fields.extend([
        field('admin_role', 'Security database administrator role', 'select',
              False, default='UNCHANGED',
              options=('UNCHANGED', 'GRANT', 'REVOKE')),
        field('active_state', 'Account state', 'select', False,
              default='UNCHANGED',
              options=('UNCHANGED', 'ACTIVE', 'INACTIVE')),
        field('tags', 'User tags', 'json', False,
              'Entries with name/value, or name/drop:true. Values are '
              'redacted in previews. CR/LF cannot be encoded safely by the '
              'native user-management attribute protocol.', [],
              sensitive=True),
    ])
    if operation == 'recreate':
        fields.append(field('confirmation', 'Confirm user name', 'text', True,
                            WARNING))
    return {'form_id': 'firebird.user.' + operation,
            'title': 'Create or alter user' if operation == 'create_or_alter'
            else 'Recreate user', 'fields': fields}
