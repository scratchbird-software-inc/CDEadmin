"""Native table clauses shared by create and add-constraint compilation."""
from ...sdk import RelationalClientError


def constraint(admin, item, source):
    kind = str(item.get('kind', '')).upper()
    for field in ('on_delete', 'on_update'):
        if field not in item:
            continue
        action = item[field]
        if kind != 'FOREIGN KEY' or action not in ('RESTRICT', 'CASCADE', 'SET NULL', 'NO ACTION', 'SET DEFAULT'):
            raise RelationalClientError('Select a native foreign-key action')
        source += ' ' + field.replace('_', ' ').upper() + ' ' + action
    if 'enforced' in item:
        if kind != 'CHECK' or type(item['enforced']) is not bool:
            raise RelationalClientError('CHECK enforcement must be boolean')
        source += ' ENFORCED' if item['enforced'] else ' NOT ENFORCED'
    return source


def temporary(options):
    value = options.get('temporary', False)
    if type(value) is not bool:
        raise RelationalClientError('Temporary must be boolean')
    return value
