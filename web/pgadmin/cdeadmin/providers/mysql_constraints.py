"""Native MySQL CHECK enforcement; other constraint kinds have no toggle."""
from ..sdk.relational import RelationalClientError
from .mysql_tablespaces import identifier

OPERATIONS = frozenset({'enforcement'})


def compile_operation(operation, draft, target):
    if operation not in OPERATIONS or not isinstance(draft, dict) or set(draft) - {'confirmation', 'enforcement'}:
        raise RelationalClientError('Native CHECK enforcement operation is unavailable')
    path = (target or {}).get('display_path', [])
    native = (target or {}).get('native') or (target or {}).get('extensions', {}).get('mysql', {}).get('native', {})
    if not isinstance(path, list) or len(path) != 3 or native.get('constraint_type') != 'CHECK':
        raise RelationalClientError('Exact native CHECK constraint identity is required')
    state = draft.get('enforcement')
    if state not in {'ENFORCED', 'NOT ENFORCED'}:
        raise RelationalClientError('Select native ENFORCED or NOT ENFORCED')
    return {'source': 'ALTER TABLE ' + '.'.join(identifier(name) for name in path[:2]) +
            ' ALTER CHECK ' + identifier(path[2]) + ' ' + state, 'parameters': ()}
