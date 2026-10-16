"""Native server/security/storage DDN plans, with explicit mutation intent."""
from copy import deepcopy
import json
import re

from .firebird_schema_plan import digest
from ..providers.mysql_family.mariadb_server_catalog import SECTIONS
from ..providers.mysql_family.mariadb_catalog import identifier
from ..providers.mysql_roles import account

SPEC = {section: (kind, keys) for section, kind, _sql, keys in SECTIONS}
SUPPORTED = {'user', 'role', 'role-membership', 'privilege', 'plugin', 'server-link',
             'loadable-function', 'system-variable', 'replication-channel'}
VOLATILE = {'component_id', 'component_group_id', 'space', 'file_size', 'allocated_size'}


def state(row):
    if row is None:
        return None
    return {'kind': row['kind'], 'section': row['native'].get('section'),
            'catalog_row': {key: value for key, value in row['native'].get('catalog_row', {}).items()
                            if key not in VOLATILE}}


def root(document):
    rows = [row for row in document['rows'].values() if row['kind'] == 'server']
    if len(rows) != 1 or document['provenance'].get('mapping') != 'scratchrobin.mariadb.catalog@1':
        raise ValueError('A native MariaDB server DDN inventory is required')
    native = rows[0]['native']
    identity = native.get('catalog_row', {})
    uuid = native.get('server_uid')
    if (not isinstance(uuid, str) or not uuid or identity.get('server_uid') != uuid or
            str(identity.get('version', '')).split('-')[0] != '12.2.2' or
            document['provenance'].get('database_target_id') != 'server:' + uuid):
        raise ValueError('Exact MariaDB server identity is unavailable')
    return rows[0], uuid


def address(row, uuid):
    section = row['native'].get('section')
    if section not in SPEC or row['kind'] != ('role' if section == 'accounts' and row['native'].get('catalog_row', {}).get('is_role') == 'Y' else SPEC[section][0]) or row['native'].get('server_uid') != uuid:
        raise ValueError('Server object kind, section or native UUID changed')
    values = row['native'].get('catalog_row', {})
    keys = [values.get(key) for key in SPEC[section][1]]
    if any(not isinstance(value, (str, int)) or type(value) is bool for value in keys):
        raise ValueError('Native object identity is unavailable')
    expected = 'mariadb-server:' + json.dumps([uuid, section, keys], ensure_ascii=False, separators=(',', ':'))
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
    from ..providers.mysql_family.provider import MARIADB_ADMINISTRATION
    from ..providers.mariadb_grants import scoped_statement
    kind, facts = row['kind'], row['native']['catalog_row']
    secret_free(row)
    intent = row['native'].get('mariadb_change')
    if not isinstance(intent, dict) or set(intent) - {'action', 'draft', 'confirmation'}:
        raise ValueError('Explicit bounded mariadb_change instructions are required')
    action, draft = intent.get('action'), deepcopy(intent.get('draft', {}))
    if not isinstance(action, str) or not isinstance(draft, dict) or kind not in SUPPORTED:
        raise ValueError('Native MariaDB server operation is unavailable')
    secret_free(draft)
    if row.get('system') != 'false' or row['native'].get('system_object') is not False:
        raise ValueError('Built-in or unclassified server objects are not migration targets')
    if action in {'drop', 'revoke', 'rename', 'reset', 'set_default'} and intent.get('confirmation') != row['name']:
        raise ValueError('Confirm the exact native object label')
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
        raise ValueError('DDN accounts are created locked and credential-free; configure authentication separately')
    if kind == 'role':
        if facts.get('host') != '' or action not in {'create', 'drop', 'set_default'}:
            raise ValueError('MariaDB roles have no account-host suffix')
        if action in {'create', 'drop'} and not draft:
            return {'source': ('CREATE ROLE ' if action == 'create' else 'DROP ROLE ') + identifier(facts['user']), 'parameters': []}
        if action == 'set_default' and set(draft) == {'member_user', 'member_host', 'mode'} and draft['mode'] in {'SELECTED', 'NONE'}:
            return {'source': 'SET DEFAULT ROLE ' + (identifier(facts['user']) if draft['mode'] == 'SELECTED' else 'NONE') +
                ' FOR ' + account(draft['member_user'], draft['member_host']), 'parameters': []}
        raise ValueError('Invalid native role instructions')
    if kind == 'role-membership':
        if action not in {'grant', 'revoke'} or set(draft) - ({'admin_option'} if action == 'grant' else {'admin_option_only'}):
            raise ValueError('Native role membership identity is immutable')
        option = draft.get('admin_option', False)
        if type(option) is not bool or type(draft.get('admin_option_only', False)) is not bool:
            raise ValueError('Invalid native role admin option')
        member = identifier(facts['user']) if facts['host'] == '' else account(facts['user'], facts['host'])
        return {'source': ('GRANT ' if action == 'grant' else 'REVOKE ADMIN OPTION FOR ' if draft.get('admin_option_only') else 'REVOKE ') + identifier(facts['role']) +
                (' TO ' if action == 'grant' else ' FROM ') + member + (' WITH ADMIN OPTION' if option else ''), 'parameters': []}
    if kind == 'privilege':
        if action not in {'grant', 'revoke'} or set(draft) - ({'grant_option'} if action == 'grant' else {'grant_option_only'}):
            raise ValueError('Exact native grant/revoke intent is required')
        option = draft.get('grant_option', False)
        if type(option) is not bool or type(draft.get('grant_option_only', False)) is not bool:
            raise ValueError('Invalid native grant option')
        return scoped_statement(facts, row['native']['section'], action, option, draft.get('grant_option_only', False))
    names = {'plugin': 'plugin_name', 'server-link': 'server_name', 'loadable-function': 'name',
             'system-variable': 'variable_name', 'replication-channel': 'connection_name'}
    name = facts[names[kind]]
    target = {'resource_kind': kind, 'display_name': name, 'display_path': [name],
              'native': {**facts, **({'registration_origin': 'mysql.func'} if kind == 'loadable-function' else {})}}
    if action == 'create' and draft.get('name') != name:
        raise ValueError('Creation draft differs from the native DDN target identity')
    if kind == 'server-link' and action == 'create' and ('password' in draft or 'change_password' in draft):
        raise ValueError('Configure remote credentials separately')
    request = {'resource_kind': kind, 'operation_id': action, 'draft': draft, 'target_resource': target}
    errors = MARIADB_ADMINISTRATION.validate(request)['errors']
    if errors:
        raise ValueError('Native server operation options are invalid: ' + str(errors))
    statements = MARIADB_ADMINISTRATION._compile(request)['statements']
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
        intent = after['native'].get('mariadb_change')
        if before is not None and state(before) == state(after) and not intent:
            continue
        try:
            address(after, uuid)
            if before is not None and before.get('system') != 'false':
                raise ValueError('Native system objects are not migration targets')
            if not observations.get(after['native']['section']):
                raise ValueError('Native catalog section is unavailable; absence is not authoritative')
            if after['kind'] == 'privilege' and not observations.get('accounts'):
                raise ValueError('Separate native account identities are unavailable')
            if (before is None) != (current is None) or before is not None and state(before) != state(current):
                conflicts.append({'resource_id': key, 'reason': 'Native server object changed since baseline'})
                continue
            if before is not None and state(before) != state(after):
                raise ValueError('Keep captured native facts immutable and express changes in mariadb_change')
            if after['kind'] == 'privilege':
                from ..providers.mariadb_grants import resolve
                resolved = resolve(after['native']['catalog_row']['grantee'],
                    [row['native']['catalog_row'] for row in live['rows'].values() if row['kind'] in {'user', 'role'}])
                if not resolved['grantee_identity_available'] or any(
                        after['native']['catalog_row'].get(key) != value for key, value in resolved.items()):
                    raise ValueError('Grant identity must match a separately observed native account or role')
            if after['kind'] == 'user' and intent.get('action') in {'create','alter'} and not observations.get('account-lock-state'):
                raise ValueError('Native account-lock state is unavailable')
            statement = compile_operation(after)
            action = intent['action']
            if (action in {'create', 'grant'}) != (before is None) and action not in {'grant', 'set_default'}:
                raise ValueError('Native operation disagrees with baseline presence')
            guards = [key]
            if after['kind'] == 'role' and action == 'set_default':
                account_pair = tuple(intent['draft'][field] for field in ('member_user', 'member_host'))
                guards = [uid for uid, row in baseline['rows'].items() if row['kind'] == 'user' and
                          tuple(row['native']['catalog_row'][field] for field in ('user', 'host')) == account_pair]
                if len(guards) != 1:
                    raise ValueError('Default-role recipient must be separately visible')
                guards.append(key)
            if after['kind'] in {'privilege', 'role-membership'}:
                facts = after['native']['catalog_row']
                pair = (facts['grantee_user'], facts['grantee_host']) if after['kind'] == 'privilege' else (facts['user'], facts['host'])
                recipients = [uid for uid, row in baseline['rows'].items() if row['kind'] in {'user', 'role'} and
                    (row['native']['catalog_row']['user'], row['native']['catalog_row']['host']) == pair]
                if len(recipients) != 1:
                    raise ValueError('Native recipient is unavailable')
                guards.extend(recipients)
                if after['kind'] == 'role-membership':
                    roles = [uid for uid, row in baseline['rows'].items() if row['kind'] == 'role' and row['native']['catalog_row']['user'] == facts['role']]
                    if len(roles) != 1:
                        raise ValueError('Native role is unavailable')
                    guards.extend(roles)
            operations.append({'resource_id': key, 'kind': after['kind'], 'operation': action,
                'name': after['name'], **statement, 'baseline_sha256': digest(state(before)),
                'desired_sha256': digest(after), 'guard_ids': sorted(guards),
                'guard_sha256': digest({uid: state(baseline['rows'][uid]) for uid in guards if uid in baseline['rows']})})
        except (ValueError, KeyError, TypeError) as error:
            blockers.append({'resource_id': key, 'reason': str(error)})
    return {'format': 'scratchrobin.mariadb.server-plan@1', 'server_uid': uuid, 'operations': operations,
            'execution_sha256': digest(operations), 'blockers': blockers, 'conflicts': conflicts,
            'ready_for_review': not blockers and not conflicts and 1 <= len(operations) <= 32,
            'ignored_missing_selections': sorted(set(baseline['rows']) - set(desired['rows'])),
            'warnings': ['Server operations have native, non-atomic effects. No automatic replay or multi-statement rollback is available.',
                         'Advisory locks coordinate ScratchRobin only. External administration requires an exclusive maintenance window.',
                         'Account creation is locked and credential-free. Configure authentication separately through native account administration.']}
