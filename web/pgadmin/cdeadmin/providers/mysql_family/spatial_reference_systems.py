"""MySQL 9.7 spatial reference systems; native IDs and driver-bound attributes."""
from collections.abc import Mapping
from copy import deepcopy
import re

from ...sdk import RelationalClientError

KIND = 'spatial-reference-system'
OPERATIONS = frozenset({'create', 'alter', 'drop'})
FIELDS = ('srs_name', 'srs_id', 'organization', 'organization_coordsys_id', 'definition', 'description')
SELECT = ('SELECT SRS_NAME,SRS_ID,ORGANIZATION,ORGANIZATION_COORDSYS_ID,DEFINITION,DESCRIPTION '
          'FROM information_schema.ST_SPATIAL_REFERENCE_SYSTEMS')


def identity(cursor):
    cursor.execute('SELECT VERSION(),@@server_uuid,CURRENT_USER(),USER(),CURRENT_ROLE()')
    row = cursor.fetchone()
    if (not row or len(row) != 5 or any(not isinstance(value, str) for value in row) or
            row[0].split('-')[0] != '9.7.0' or not row[1]):
        raise RelationalClientError('Exact native MySQL spatial reference execution identity is unavailable')
    return dict(zip(('version', 'server_uuid', 'effective_principal', 'authenticated_principal', 'active_roles'), row))


def bind_review(client, planned):
    payload = planned['provider_payload'];compiled = payload['compiled']
    handle = client._connect({'route': payload['route']});cursor = None
    try:
        cursor = handle.cursor()
        observed = identity(cursor)
        compiled['mysql_spatial_reference']['execution_identity'] = observed
        planned['command_preview']['native_execution_identity'] = dict(observed)
        return planned
    finally:
        if cursor is not None:
            client._safe_close(cursor)
        client._forget_and_close(handle)


def number(value, label, maximum=4294967295):
    if type(value) is int:
        result = value
    elif isinstance(value, str) and re.fullmatch(r'(?:0|[1-9][0-9]*)', value):
        result = int(value)
    else:
        raise RelationalClientError(label + ' requires an exact unsigned decimal integer')
    if not 0 <= result <= maximum:
        raise RelationalClientError(label + ' is outside the native range')
    return result


def text(value, label):
    if not isinstance(value, str) or any(character in value for character in '\x00\r\n'):
        raise RelationalClientError(label + ' must be native text without NUL or newlines')
    return value


def normalized(row):
    value = {key: row.get(key) for key in FIELDS} if isinstance(row, Mapping) else dict(zip(FIELDS, row))
    # Keep exact decimal input/output independent of browser numeric controls.
    if value['organization_coordsys_id'] is not None:
        value['organization_coordsys_id'] = str(value['organization_coordsys_id'])
    return value


def native(target):
    value = (target or {}).get('native')
    if value is None:
        value = ((target or {}).get('extensions') or {}).get('mysql', {}).get('native', {})
    if not isinstance(value, Mapping):
        raise RelationalClientError('Native MySQL spatial reference identity is unavailable')
    if isinstance(value.get('catalog_row'), Mapping):
        return value['catalog_row']
    # The MySQL catalog exposes its definition facet as a native fact snapshot.
    return value['definition'] if isinstance(value.get('definition'), Mapping) else value


def compile_operation(operation, draft, target=None):
    if operation not in OPERATIONS or not isinstance(draft, Mapping):
        raise RelationalClientError('Native MySQL spatial reference operation is unavailable')
    creating = operation == 'create'
    allowed = {'confirmation'} if operation == 'drop' else {
        'srs_id', 'name', 'definition', 'include_organization', 'organization',
        'organization_id', 'include_description', 'description',
        'if_not_exists' if creating else 'confirmation'}
    if set(draft) - allowed:
        raise RelationalClientError('Unknown native spatial reference option')
    old = None if creating else native(target)
    if not creating and (target or {}).get('resource_kind') != KIND:
        raise RelationalClientError('Select an exact MySQL spatial reference system')
    srid = number(draft.get('srs_id') if creating else old.get('srs_id'), 'SRID')
    if not creating and (target.get('resource_id') != KIND + ':' + str(srid) or
            target.get('display_path') != [str(srid)] or target.get('display_name') != str(srid)):
        raise RelationalClientError('Spatial reference metadata disagrees with its native resource address')
    if not creating and (draft.get('confirmation') != (target or {}).get('display_name') or
            draft.get('srs_id', srid) not in (srid, str(srid))):
        raise RelationalClientError('Confirm the exact spatial reference system ID')
    baseline = None if creating else normalized(old)
    if operation == 'drop':
        statement = {'source': 'DROP SPATIAL REFERENCE SYSTEM ' + str(srid), 'parameters': ()}
    else:
        if_not_exists = draft.get('if_not_exists', False)
        if type(if_not_exists) is not bool:
            raise RelationalClientError('IF NOT EXISTS must be boolean')
        source = ('CREATE SPATIAL REFERENCE SYSTEM ' + ('IF NOT EXISTS ' if if_not_exists else '')
                  if creating else 'CREATE OR REPLACE SPATIAL REFERENCE SYSTEM ')
        source += str(srid) + ' NAME %s DEFINITION %s'
        parameters = [text(draft.get('name'), 'SRS name'), text(draft.get('definition'), 'Native WKT definition')]
        for key in ('include_organization', 'include_description'):
            if type(draft.get(key, False)) is not bool:
                raise RelationalClientError(key + ' must be boolean')
        if draft.get('include_organization'):
            source += ' ORGANIZATION %s IDENTIFIED BY ' + str(number(
                draft.get('organization_id'), 'Organization coordinate-system ID'))
            parameters.append(text(draft.get('organization'), 'Organization'))
        elif {'organization', 'organization_id'} & set(draft):
            raise RelationalClientError('Select organization attributes explicitly')
        if draft.get('include_description'):
            source += ' DESCRIPTION %s'
            parameters.append(text(draft.get('description'), 'Description'))
        elif 'description' in draft:
            raise RelationalClientError('Select description explicitly')
        statement = {'source': source, 'parameters': tuple(parameters)}
    return {'statements': [statement], 'mysql_spatial_reference': {
        'operation': operation, 'srs_id': srid, 'draft': dict(draft),
        'target': dict(target) if target else None, 'baseline': baseline},
        'warnings': ['Native MySQL DDL owns its implicit transaction decision. This task uses an independent connection.']}


def form(operation, field):
    fields = []
    if operation != 'drop':
        if operation == 'create':
            fields.append(field('srs_id', 'Exact native SRID', 'text', True))
            fields.append(field('if_not_exists', 'IF NOT EXISTS', 'boolean', default=False))
        fields.extend([field('name', 'Spatial reference name', 'text', True),
            field('definition', 'Native WKT definition', 'multiline', True),
            field('include_organization', 'Specify organization', 'boolean', default=False),
            {**field('organization', 'Organization', 'text'), 'submit_unchanged': True,
             'visible_when': {'field_id': 'include_organization', 'equals': True}},
            {**field('organization_id', 'Exact organization coordinate-system ID', 'text'),
             'visible_when': {'field_id': 'include_organization', 'equals': True}},
            field('include_description', 'Specify description', 'boolean', default=False),
            {**field('description', 'Description', 'multiline'), 'submit_unchanged': True,
             'visible_when': {'field_id': 'include_description', 'equals': True}}])
    if operation != 'create':
        fields.append(field('confirmation', 'Exact spatial reference system ID', 'text', True))
    initial = {'name': 'srs_name', 'definition': 'definition', 'organization': 'organization',
        'organization_id': 'organization_coordsys_id', 'description': 'description',
        'include_organization': 'has_organization', 'include_description': 'has_description'}
    for item in fields:
        if item['field_id'] in initial:
            item['submit_unchanged'] = True
            if operation == 'alter':
                item['initial_value_path'] = (['definition', 'definition']
                    if item['field_id'] == 'definition' else [initial[item['field_id']]])
    return {'form_id': 'mysql.spatial-reference-system.' + operation,
            'title': ('Replace' if operation == 'alter' else operation.title()) + ' native MySQL spatial reference system',
            'fields': fields}


def apply(client, request, connection=None):
    if connection is not None:
        raise RelationalClientError('MySQL spatial reference DDL requires an independently owned connection')
    payload = request.get('provider_payload') or {}
    compiled = payload['compiled'];intent = compiled['mysql_spatial_reference']
    checked = deepcopy(compiled)
    expected_identity = checked['mysql_spatial_reference'].pop('execution_identity', None)
    if compile_operation(intent['operation'], intent['draft'], intent['target']) != checked:
        raise RelationalClientError('Reviewed spatial reference operation changed')
    if not isinstance(expected_identity, Mapping):
        raise RelationalClientError('Review the native MySQL instance and principal before dispatch')
    handle = client._connect({'route': payload['route']});cursor = None
    dispatched = acknowledged = False
    try:
        handle.autocommit = True
        # Collect warnings during completion, before another C-cursor execute
        # can clear the server diagnostics.
        handle.raise_on_warnings = False
        handle.get_warnings = True
        cursor = handle.cursor()
        observed_identity = identity(cursor)
        instance_uuid = observed_identity['server_uuid']
        expected = native(intent['target']).get('server_uuid') if intent['target'] else None
        # Server DDN targets retain the UUID outside catalog_row.
        if intent['target'] and not expected:
            expected = (intent['target'].get('native') or {}).get('server_uuid')
        if observed_identity != expected_identity or expected is not None and expected != instance_uuid:
            raise RelationalClientError('MySQL spatial reference execution identity changed')
        def current():
            cursor.execute(SELECT + ' WHERE SRS_ID=%s', (intent['srs_id'],))
            row = cursor.fetchone()
            return normalized(row) if row else None
        before = current()
        if intent['baseline'] is not None and before != intent['baseline']:
            raise RelationalClientError('Native spatial reference definition changed since review')
        statement = compiled['statements'][0];dispatched = True
        cursor.execute(statement['source'], statement['parameters'] or None)
        acknowledged = True
        warnings = [{'level': level, 'code': code, 'message': message}
                    for level, code, message in (cursor.warnings or ())]
        after = current()
        return {'accepted': True, 'commit_requested': False, 'rollback_requested': False,
                'staged_in_provider_session': False, 'native_implicit_commit': True,
                'driver_observation_only': True, 'transaction_finality_interpreted_by_common_code': False,
                'native_warnings': warnings,
                'spatial_reference_observation': {'native_acknowledged': True,
                    'before': before, 'after': after, 'server_uuid': instance_uuid,
                    'execution_identity': observed_identity},
                'automatic_retry': False}
    except Exception as error:
        failure = error if isinstance(error, RelationalClientError) else RelationalClientError(
            'Native MySQL spatial reference operation failed (' + type(error).__name__ + ')')
        failure.native_dispatched = dispatched;failure.native_acknowledged = acknowledged
        failure.errno = getattr(error, 'errno', None);failure.sqlstate = getattr(error, 'sqlstate', None)
        failure.native_status_codes = (failure.errno,) if type(failure.errno) is int else ()
        failure.automatic_retry = False
        raise failure from None
    finally:
        if cursor is not None:
            client._safe_close(cursor)
        client._forget_and_close(handle)
