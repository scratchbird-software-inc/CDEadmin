"""Explicit grant identities and native security-change previews."""
import json
from ..providers.firebird.identity import catalog_resource_id
from ..providers.firebird.mappings import identifier
from .firebird_sql_export import grant_statement, PRINCIPAL_KINDS

INSTRUCTION = 'grant_change'
FIELDS = ('grantee', 'object_name', 'field', 'privilege', 'grantor',
          'grant_option', 'user_type', 'object_type', 'default_role')
CLASSES = dict(zip(range(22, 34), ('TABLE', 'VIEW', 'PROCEDURE', 'FUNCTION',
    'PACKAGE', 'SEQUENCE', 'DOMAIN', 'EXCEPTION', 'ROLE', 'CHARACTER SET', 'COLLATION', 'FILTER')))
KINDS = {0: {'table', 'view'}, 5: {'procedure'}, 7: {'exception'}, 13: {'role'},
         14: {'sequence'}, 15: {'function', 'external-function'}, 18: {'package'}}
CLASS_NAMES = dict(zip(range(21, 34), ('SQL$DATABASE', 'SQL$TABLES', 'SQL$VIEWS',
    'SQL$PROCEDURES', 'SQL$FUNCTIONS', 'SQL$PACKAGES', 'SQL$GENERATORS', 'SQL$DOMAINS',
    'SQL$EXCEPTIONS', 'SQL$ROLES', 'SQL$CHARSETS', 'SQL$COLLATIONS', 'SQL$FILTERS')))


def model(row):
    native = row['native']
    facts = {key: native.get(key) for key in FIELDS}
    if row['kind'] != 'privilege' or row['system'] == 'true' or native.get('catalog_source'):
        raise ValueError('Select a database privilege record')
    for key in ('grantee', 'object_name', 'grantor'):
        identifier(facts[key])
    if facts['field'] is not None:
        identifier(facts['field'])
    if (type(facts['default_role']) is not bool or
            any(type(facts[key]) is not int for key in ('grant_option', 'user_type', 'object_type')) or
            facts['grant_option'] not in {0, 1, 2} or not isinstance(facts['privilege'], str)):
        raise ValueError('Privilege native flags are incomplete')
    identity = [facts[key] if key != 'field' else facts[key] or '' for key in FIELDS]
    expected = catalog_resource_id('privilege', [], json.dumps(identity, ensure_ascii=False, separators=(',', ':')))
    if row['resource_id'] != expected:
        raise ValueError('Privilege native identity differs from its grant facts')
    if facts['default_role'] and not (facts['privilege'] == 'M' and facts['object_type'] == 13):
        raise ValueError('Default-role flag applies only to membership')
    return facts


def plan(old, wanted, live, current):
    from .firebird_schema_plan import native_guard, DERIVED, _native_changes
    intent = wanted['native'].get(INSTRUCTION)
    if (not isinstance(intent, dict) or set(intent) != {'operation', 'confirmation', 'allow_cascade'} or
            intent.get('operation') not in {'grant', 'revoke'} or type(intent.get('allow_cascade')) is not bool):
        raise ValueError('Privilege changes require exact grant/revoke intent and cascade policy')
    facts = model(wanted)
    if set(wanted['native']) - set(FIELDS) - DERIVED - {'granted_object', 'target_resolution'}:
        raise ValueError('Unsupported native privilege properties')
    if intent['confirmation'] != facts['grantee']:
        raise ValueError('Confirm the exact privilege grantee')
    if old and (model(old) != facts or _native_changes(old, wanted, DERIVED)):
        raise ValueError('Privilege identity changes require separate revoke and grant reviews')
    if old and (live is None or native_guard(old) != native_guard(live)):
        raise ValueError('Privilege changed since the captured baseline')
    if old is None and live is not None:
        raise ValueError('Privilege appeared outside the baseline; capture it before review')
    operation = intent['operation']
    if operation == 'revoke' and old is None:
        raise ValueError('Revocation requires an observed baseline privilege')
    if operation == 'revoke' and facts['grant_option'] and not intent['allow_cascade']:
        raise ValueError('Revoking grant/admin authority requires explicit cascade acknowledgement')
    databases = [row for row in current['rows'].values() if row['kind'] == 'database']
    observations = databases[0]['native'].get('catalog_observations', []) if len(databases) == 1 else []
    if not any(item.get('section') == 'object privileges' and item.get('available') is True for item in observations):
        raise ValueError('Privilege planning requires available native object privileges')
    # Database identity/dialect and catalog visibility are already checked by
    # every preflight. Its attachment/transaction counters are not grant facts.
    dependencies = [row['resource_id'] for row in current['rows'].values() if row['kind'] == 'privilege']
    native = dict(facts)
    if facts['object_type'] in CLASS_NAMES and (facts['field'] or facts['object_name'] != CLASS_NAMES[facts['object_type']]):
        raise ValueError('Native database/class grant identity is inconsistent')
    principal_kind = {1: 'view', 2: 'trigger', 5: 'procedure', 13: 'role', 15: 'function', 18: 'package'}.get(facts['user_type'])
    if principal_kind:
        principals = [row for row in current['rows'].values() if row['kind'] == principal_kind and
                      row['name'] == facts['grantee'] and not row['native'].get('package')]
        if len(principals) != 1:
            raise ValueError('Privilege principal is not uniquely observed')
        dependencies.append(principals[0]['resource_id'])
    if facts['object_type'] in CLASSES:
        native['target_resolution'] = {'state': 'class-scope', 'ddl_class': CLASSES[facts['object_type']]}
    elif facts['object_type'] != 21:
        targets = [row for row in current['rows'].values() if
            row['kind'] in KINDS.get(facts['object_type'], set()) and row['name'] == facts['object_name'] and
            not row['native'].get('package')]
        if len(targets) != 1:
            raise ValueError('Privilege target is not uniquely observed')
        dependencies.append(targets[0]['resource_id'])
        if facts['field']:
            fields = [row for row in current['rows'].values() if row['kind'] == 'column' and row['path'] == [facts['object_name'], facts['field']]]
            if len(fields) != 1:
                raise ValueError('Privilege column is not uniquely observed')
            dependencies.append(fields[0]['resource_id'])
        native['target_resolution'] = {'state': 'resolved'}
    if operation == 'revoke' and facts['privilege'] == 'M' and facts['object_type'] == 13:
        principal = PRINCIPAL_KINDS.get(facts['user_type'])
        if principal not in {'USER', 'ROLE'} or facts['field']:
            raise ValueError('Unsupported membership principal or column')
        statement = ('REVOKE ' + identifier(facts['object_name']) + ' FROM ' + principal + ' ' +
            identifier(facts['grantee']) + ' GRANTED BY USER ' + identifier(facts['grantor']))
    else:
        statement = grant_statement(native, operation)
    if operation == 'grant' and old is not None:
        return None
    if operation == 'grant':
        for row in current['rows'].values():
            if row['kind'] == 'privilege' and all(row['native'].get(key) == facts[key]
                    for key in FIELDS if key not in {'grant_option', 'default_role'}):
                raise ValueError('A grant with different options exists; revoke it in a separate review')
    return {'resource_id': wanted['resource_id'], 'kind': 'privilege',
        'operation': operation, 'source_location': wanted.get('source_location'),
        'before': model(live) if live else None, 'after': facts if operation == 'grant' else None,
        'statements': [statement], 'deferred_statements': [], 'dependencies': sorted(set(dependencies)),
        'order_dependencies': [], 'native_preconditions': {key: native_guard(current['rows'].get(key)) for key in [wanted['resource_id'], *dependencies]},
        'precondition': 'exact observed privilege catalog', 'permissions': 'Native GRANT/REVOKE authority including explicit grantor',
        'security_changes': {'operation': operation, 'grantee': facts['grantee'], 'cascade_acknowledged': intent['allow_cascade']},
        'transaction': 'Separate native security review; dependent grants may be revoked by native cascade rules'}
