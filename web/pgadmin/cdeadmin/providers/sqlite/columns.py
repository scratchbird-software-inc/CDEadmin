"""Native SQLite column declarations for the create-only typed grid."""
from collections.abc import Mapping
from pgadmin.cdeadmin.sdk import RelationalClientError
from .expressions import expression

CONFLICTS = {'ABORT', 'FAIL', 'IGNORE', 'REPLACE', 'ROLLBACK'}


def declaration(adapter, item):
    if not isinstance(item, Mapping):
        raise RelationalClientError('Column definition must be an object')
    for key, default in [('nullable',True),('primary_key',False),('unique',False),('autoincrement',False)]:
        if not isinstance(item.get(key,default), bool):
            raise RelationalClientError(key + ' must be boolean')
    parts = [adapter._quote(item.get('name')), adapter._safe_fragment(item.get('type'),'column type')]
    def constraint(key, enabled, sql):
        policy = item.get(key + '_conflict')
        if policy in (None,'','DEFAULT'):
            policy = None
        elif policy not in CONFLICTS or not enabled:
            raise RelationalClientError('Conflict policy requires its active native constraint')
        if enabled:
            parts.append(sql + (' ON CONFLICT ' + policy if policy else ''))
    constraint('not_null',not item.get('nullable',True),'NOT NULL')
    constraint('unique',item.get('unique',False),'UNIQUE')
    constraint('primary_key',item.get('primary_key',False),'PRIMARY KEY')
    generated = item.get('generated_storage') or 'NONE'
    formula = item.get('generated_expression')
    if generated not in {'NONE','VIRTUAL','STORED'}:
        raise RelationalClientError('Generated storage must be NONE, VIRTUAL or STORED')
    if generated != 'NONE':
        if item.get('primary_key') or item.get('autoincrement') or item.get('default') not in (None,''):
            raise RelationalClientError('Generated columns cannot have DEFAULT, PRIMARY KEY or AUTOINCREMENT')
        parts.append('GENERATED ALWAYS AS (' + expression(formula) + ') ' + generated)
    elif formula:
        raise RelationalClientError('Generated expression requires VIRTUAL or STORED storage')
    if item.get('autoincrement'):
        if not item.get('primary_key') or str(item.get('type')).strip().upper() != 'INTEGER':
            raise RelationalClientError('AUTOINCREMENT requires exact INTEGER PRIMARY KEY')
        parts.append('AUTOINCREMENT')
    if item.get('default') not in (None,''):
        parts.append('DEFAULT (' + expression(item['default']) + ')')
    if item.get('collation'):
        parts.append('COLLATE ' + adapter._quote(item['collation']))
    if item.get('check_expression'):
        parts.append('CHECK (' + expression(item['check_expression']) + ')')
    return ' '.join(parts)
