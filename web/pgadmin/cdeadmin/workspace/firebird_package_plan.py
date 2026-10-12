"""Package headers and bodies share one reviewed native transaction."""
from ..providers.firebird import packages
from .firebird_view_plan import dependencies

FIELDS = {'header_source', 'body_source', 'sql_security', 'description'}
DERIVED = {'valid_body', 'body_status', 'package_sql_security', 'child_definition_tasks', 'catalog_warnings'}
WARNING = ('Changing a package header replaces its public declarations and can remove omitted members. '
           'Header changes invalidate its body; the listed body action runs in the same transaction. Native dependency checks apply.')


def model(row):
    native = row['native']
    for key in ('header_source', 'body_source', 'sql_security'):
        if key not in native:
            raise ValueError('Exact package metadata is missing: ' + key)
    flag = native['sql_security']
    if type(flag) is bool:
        flag = '1' if flag else '0'
    elif isinstance(flag, str) and flag.upper() in {'TRUE', 'FALSE'}:
        flag = '1' if flag.upper() == 'TRUE' else '0'
    if flag is not None and (type(flag) not in (str, int) or str(flag) not in {'0', '1'}):
        raise ValueError('Package SQL SECURITY requires a native flag or NULL')
    return {'header_source': packages.source(native['header_source'], 'Package header'),
            'body_source': None if native['body_source'] is None else packages.source(native['body_source'], 'Package body'),
            'sql_security': None if flag is None else str(flag)}


def context(current):
    databases = [row for row in current['rows'].values() if row['kind'] == 'database']
    observations = databases[0]['native'].get('catalog_observations', []) if len(databases) == 1 else []
    if not any(item.get('section') == 'package objects' and item.get('available') is True for item in observations):
        raise ValueError('Package planning requires available package objects observation')
    # Package source can refer to any visible schema object, including other
    # package signatures. Imported dependency prose is not authority.
    return sorted(set(dependencies(current)) | {
        key for key, row in current['rows'].items() if row['kind'] == 'package'})


def parts(before, after):
    target = {'resource_kind': 'package', 'display_name': after['name']}
    header_changed = before is None or any(before[key] != after[key] for key in ('header_source', 'sql_security'))
    headers, bodies = [], []
    if header_changed:
        draft = {'header': after['header_source'],
                 'sql_security': {None: 'INHERIT', '0': 'INVOKER', '1': 'DEFINER'}[after['sql_security']]}
        if before is None:
            draft['name'] = after['name']
        headers = packages.compile_operation('create' if before is None else 'alter', draft, target)
    if after['body_source'] is None:
        if before is not None and before['body_source'] is not None:
            bodies = packages.compile_operation('drop_body', {'confirmation': after['name']}, target)
    elif header_changed or before['body_source'] != after['body_source']:
        operation = 'create_body' if before is None or before['body_source'] is None else 'replace_body'
        bodies = packages.compile_operation(operation, {'body': after['body_source']}, target)
    return headers, bodies
