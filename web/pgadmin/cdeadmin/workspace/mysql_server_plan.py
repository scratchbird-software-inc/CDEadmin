"""Native server/security/storage DDN plans, with explicit mutation intent."""
from copy import deepcopy
import json
import re

from .firebird_schema_plan import digest
from ..providers.mysql_family.mysql_server_catalog import SECTIONS
from ..providers.mysql_family.mysql_catalog import identifier
from ..providers.mysql_roles import account

SPEC = {section: (kind, keys) for section, kind, _sql, keys in SECTIONS}
SUPPORTED = {'user', 'role-membership', 'default-role', 'privilege', 'plugin', 'component', 'server-link', 'spatial-reference-system',
             'tablespace', 'resource-group', 'system-variable', 'replication-channel'}
VOLATILE = {'component_id', 'component_group_id', 'space', 'file_size', 'allocated_size', 'udf_usage_count'}


def spatial_selection(*documents):
    from ..providers.mysql_family.mysql_server_catalog import spatial_ids
    values = [row['native']['catalog_row']['srs_id'] for document in documents
        for row in document['rows'].values() if row['kind'] == 'spatial-reference-system']
    if any(type(value) is not int for value in values):
        raise ValueError('DDN spatial reference identities must be native unsigned integers')
    return spatial_ids(list(set(values)))


def state(row):
    if row is None:
        return None
    return {'kind': row['kind'], 'section': row['native'].get('section'),
            'catalog_row': {key: value for key, value in row['native'].get('catalog_row', {}).items()
                            if key not in VOLATILE},
            **({'failover_configuration':{key:row['native'][key] for key in ('failover_sources','failover_managed') if key in row['native']}} if row['kind']=='replication-channel' else {})}


def root(document):
    rows = [row for row in document['rows'].values() if row['kind'] == 'server']
    if len(rows) != 1 or document['provenance'].get('mapping') != 'scratchrobin.mysql.catalog@1':
        raise ValueError('A native MySQL server DDN inventory is required')
    native = rows[0]['native']
    identity = native.get('catalog_row', {})
    uuid = native.get('server_uuid')
    if (not isinstance(uuid, str) or not uuid or identity.get('server_uuid') != uuid or
            str(identity.get('version', '')).split('-')[0] != '9.7.0' or
            document['provenance'].get('database_target_id') != 'server:' + uuid):
        raise ValueError('Exact MySQL server identity is unavailable')
    return rows[0], uuid


def address(row, uuid):
    section = row['native'].get('section')
    if section not in SPEC or row['kind'] != SPEC[section][0] or row['native'].get('server_uuid') != uuid:
        raise ValueError('Server object kind, section or native UUID changed')
    values = row['native'].get('catalog_row', {})
    keys = [values.get(key) for key in SPEC[section][1]]
    if any(not isinstance(value, (str, int)) or type(value) is bool for value in keys):
        raise ValueError('Native object identity is unavailable')
    expected = 'mysql-server:' + json.dumps([uuid, section, keys], ensure_ascii=False, separators=(',', ':'))
    if row['resource_id'] != expected:
        raise ValueError('Server object ID disagrees with its native address')


def secret_free(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if re.search(r'(^|_)(password|secret|token|dsn|authentication_string|private_key)($|_)', key.lower()) and key not in {'password_expired', 'password_lifetime'}:
                raise ValueError('Credentials are not admitted in DDN migration instructions')
            secret_free(item)
    elif isinstance(value, list):
        for item in value:
            secret_free(item)


def compile_operation(row):
    from ..providers.mysql_family.provider import MYSQL_ADMINISTRATION
    kind, facts = row['kind'], row['native']['catalog_row']
    intent = row['native'].get('mysql_change')
    if not isinstance(intent, dict) or set(intent) - {'action', 'draft', 'confirmation'}:
        raise ValueError('Explicit bounded mysql_change instructions are required')
    action, draft = intent.get('action'), deepcopy(intent.get('draft', {}))
    if not isinstance(action, str) or not isinstance(draft, dict) or kind not in SUPPORTED:
        raise ValueError('Native server operation is unavailable')
    secret_free(draft)
    if row.get('system') != 'false' or row['native'].get('system_object') is not False:
        raise ValueError('Built-in or unclassified server objects are not migration targets')
    if action in {'drop', 'revoke', 'rename', 'reset', 'reset_persist', 'set_default'} and intent.get('confirmation') != row['name']:
        raise ValueError('Confirm the exact native object label')
    if kind == 'spatial-reference-system':
        from ..providers.mysql_family import spatial_reference_systems as srs
        from ..sdk import RelationalClientError
        try:
            srid = srs.number(facts['srs_id'], 'Native SRID')
            if row['name'] != str(srid) or (action == 'create' and srs.number(draft.get('srs_id'), 'Draft SRID') != srid):
                raise ValueError('Spatial reference instructions differ from the exact native SRID')
            if action != 'create':
                if intent.get('confirmation') != row['name']:
                    raise ValueError('Confirm the exact native spatial reference ID')
                draft.setdefault('confirmation', str(srid))
            target = {'resource_id':srs.KIND+':'+str(srid),'resource_kind':srs.KIND,
                'display_name':str(srid),'display_path':[str(srid)],'native':{'catalog_row':facts}}
            statement = srs.compile_operation(action, draft, None if action == 'create' else target)['statements'][0]
        except RelationalClientError as error:
            raise ValueError(str(error)) from None
        return {'source':statement['source'],'parameters':list(statement['parameters'])}
    if kind == 'server-link':
        from ..providers.mysql_family import foreign_servers
        from ..sdk import RelationalClientError
        name = facts['server_name']
        if action == 'create':
            if draft.get('name') != name or ('wrapper' in facts and draft.get('wrapper') != facts['wrapper']):
                raise ValueError('Foreign-server creation differs from the native DDN identity or wrapper')
            target = None
        else:
            if intent.get('confirmation') != row['name']:
                raise ValueError('Confirm the exact native foreign server')
            draft.setdefault('confirmation', name)
            target = {'resource_id': foreign_servers.address(name), 'resource_kind': kind,
                'display_name': name, 'display_path': [name], 'native': facts}
        try:
            compiled = foreign_servers.compile_operation(action, draft, target)
        except RelationalClientError as error:
            raise ValueError(str(error)) from None
        statement = compiled['statements'][0]
        return {'source': statement['source'], 'parameters': list(statement['parameters'])}
    if kind == 'user':
        name = account(facts['user'], facts['host'])
        if action == 'create' and not draft:
            return {'source': 'CREATE USER ' + name + ' ACCOUNT LOCK', 'parameters': []}
        if action == 'drop' and not draft:
            return {'source': 'DROP USER ' + name, 'parameters': []}
        if action == 'alter' and set(draft) == {'active'} and type(draft['active']) is bool:
            return {'source': 'ALTER USER ' + name + ' ACCOUNT ' + ('UNLOCK' if draft['active'] else 'LOCK'), 'parameters': []}
        if action == 'rename' and set(draft) == {'new_user', 'new_host'}:
            return {'source': 'RENAME USER ' + name + ' TO ' + account(draft['new_user'], draft['new_host']), 'parameters': []}
        raise ValueError('DDN account creation is locked and credential-free; authentication is configured separately')
    if kind in {'role-membership', 'default-role'}:
        role_user, role_host = ((facts['from_user'], facts['from_host']) if kind == 'role-membership'
                                else (facts['default_role_user'], facts['default_role_host']))
        member_user, member_host = ((facts['to_user'], facts['to_host']) if kind == 'role-membership'
                                    else (facts['user'], facts['host']))
        if set(draft) - ({'admin_option'} if action == 'grant' else {'mode'} if action == 'set_default' else set()):
            raise ValueError('Role instructions cannot change the captured recipient')
        if kind == 'default-role' and action != 'set_default' or kind == 'role-membership' and action not in {'grant', 'revoke'}:
            raise ValueError('Native role operation differs from its metadata kind')
        from ..providers.mysql_roles import compile_operation as role_operation
        return role_operation(action, {**draft, 'member_user': member_user, 'member_host': member_host},
                              {'native': {'user': role_user, 'host': role_host}})
    if kind == 'privilege':
        privilege = facts.get('privilege_type')
        if (action not in {'grant', 'revoke'} or set(draft) - {'grant_option'} or
                not isinstance(privilege, str) or not re.fullmatch(r'[A-Z][A-Z0-9_ ]{0,127}', privilege)):
            raise ValueError('Exact native global privilege and grant/revoke intent are required')
        option = draft.get('grant_option', False)
        if type(option) is not bool or action == 'revoke' and option:
            raise ValueError('Invalid native grant option')
        from ..providers.mysql_grants import scoped_statement
        return scoped_statement(facts, row['native']['section'], action, option)
    names = {'plugin': 'plugin_name', 'component': 'component_urn', 'tablespace': 'name',
             'resource-group': 'resource_group_name', 'system-variable': 'variable_name',
             'replication-channel': 'channel_name'}
    name = facts[names[kind]]
    target = {'display_name': name or 'Default channel', 'display_path': [name or 'Default channel'],
              'native': {**facts, 'channel_name': name if kind == 'replication-channel' else None,
                         **({'engine': 'InnoDB'} if kind == 'tablespace' else {})}}
    if action == 'create':
        identity = 'name' if kind in {'plugin', 'tablespace', 'resource-group', 'replication-channel'} else None
        if identity and draft.get(identity) != name or kind == 'component' and draft.get('urns') != [name]:
            raise ValueError('Creation draft differs from the DDN target identity')
    if kind=='replication-channel':
        from ..providers.mysql_family.mysql_failover import OPERATIONS
        if action in OPERATIONS:
            if intent.get('confirmation')!=row['name']:raise ValueError('Confirm the native failover channel label')
            draft.setdefault('confirmation',row['name']);target.update(resource_kind=kind,display_name=row['name'])
            target['native']['server_uuid']=row['native']['server_uuid']
    request = {'resource_kind': kind, 'operation_id': action, 'draft': draft, 'target_resource': target}
    errors = MYSQL_ADMINISTRATION.validate(request)['errors']
    if errors:
        raise ValueError('Native server operation options are invalid: ' + str(errors))
    statements = MYSQL_ADMINISTRATION._compile(request)['statements']
    if len(statements) != 1:
        raise ValueError('One native statement per reviewed server object is required')
    statement = statements[0]
    return {'source': statement['source'], 'parameters': list(statement.get('parameters') or ())}


def plan(baseline, desired, live):
    server, uuid = root(live)
    for document in (baseline, desired):
        if root(document)[1] != uuid or any(document['provenance'].get(key) != live['provenance'].get(key)
                for key in ('endpoint_id', 'database_target_id')):
            raise ValueError('Server DDN belongs to another endpoint or instance')
    observations = {row['section']: row['available'] for row in server['native']['catalog_observations']}
    operations, blockers, conflicts = [], [], []
    for key, after in sorted(desired['rows'].items()):
        if after['kind'] == 'server':
            continue
        before, current = baseline['rows'].get(key), live['rows'].get(key)
        intent = after['native'].get('mysql_change')
        if before is not None and state(before) == state(after) and not intent:
            continue
        try:
            address(after, uuid)
            if before is not None and before.get('system') != 'false':
                raise ValueError('Native system objects are not migration targets')
            failover=after['kind']=='replication-channel' and isinstance(intent,dict) and intent.get('action') in {'add_failover_source','remove_failover_source','add_managed_failover','remove_managed_failover'}
            if not failover and not observations.get(after['native']['section']):
                raise ValueError('Native catalog section is unavailable; absence is not authoritative')
            if after['kind'] == 'spatial-reference-system':
                observed_scope = next(item for item in server['native']['catalog_observations'] if item['section']=='spatial-reference-systems')
                if after['native']['catalog_row']['srs_id'] not in observed_scope.get('selected_ids', []):
                    raise ValueError('Exact SRID was not observed in this native capture')
            if failover:
                required=['failover_sources']+(['failover_managed'] if 'managed' in intent['action'] else [])
                if not all(observations.get('replication-'+key) for key in required):
                    raise ValueError('The native failover configuration sections for this change must be visible')
            if after['kind'] == 'privilege' and not observations.get('accounts'):
                raise ValueError('Separate native account identities are unavailable')
            if (before is None) != (current is None) or before is not None and state(before) != state(current):
                conflicts.append({'resource_id': key, 'reason': 'Native server object changed since baseline'})
                continue
            if before is not None and state(before) != state(after):
                raise ValueError('Keep captured native facts immutable and express changes in mysql_change')
            statement = compile_operation(after)
            action = intent['action']
            if (action in {'create', 'grant'}) != (before is None) and action not in {'grant', 'set_default'}:
                raise ValueError('Native operation disagrees with baseline presence')
            guards = [key]
            if after['kind'] == 'default-role':
                account_pair = tuple(after['native']['catalog_row'][field] for field in ('user', 'host'))
                guards = [uid for uid, row in baseline['rows'].items() if row['kind'] == 'default-role' and
                          tuple(row['native']['catalog_row'][field] for field in ('user', 'host')) == account_pair]
            operations.append({'resource_id': key, 'kind': after['kind'], 'operation': action,
                'name': after['name'], **statement, 'baseline_sha256': digest(state(before)),
                **({'execution_identity':deepcopy(server['native']['catalog_row'])} if after['kind']=='spatial-reference-system' else {}),
                'desired_sha256': digest(after), 'guard_ids': sorted(guards),
                'guard_sha256': digest({uid: state(baseline['rows'][uid]) for uid in guards if uid in baseline['rows']})})
        except (ValueError, KeyError, TypeError) as error:
            blockers.append({'resource_id': key, 'reason': str(error)})
    return {'format': 'scratchrobin.mysql.server-plan@1', 'server_uuid': uuid, 'operations': operations,
            'execution_sha256': digest(operations), 'blockers': blockers, 'conflicts': conflicts,
            'ready_for_review': not blockers and not conflicts and 1 <= len(operations) <= 32,
            'ignored_missing_selections': sorted(set(baseline['rows']) - set(desired['rows'])),
            'warnings': ['Server operations have native, non-atomic effects. No automatic replay or multi-statement rollback is available.',
                         'Advisory locks coordinate ScratchRobin only. External administration requires an exclusive maintenance window.',
                         'Account creation is locked and credential-free. Configure authentication separately through native account administration.']}
