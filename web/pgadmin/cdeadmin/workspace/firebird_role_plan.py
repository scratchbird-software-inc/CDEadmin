"""Native role definitions; membership and ownership have separate lifecycles."""
from ..providers.relational_admin import FIREBIRD_SYSTEM_PRIVILEGES
from ..providers.firebird.character_metadata import identifier

FIELDS = {'system_privileges', 'description'}
DERIVED = {'system_privileges_hex', 'recreation_requirements',
           'membership_recreation_statements', 'membership_recreation_requirements',
           'membership_recreation_unavailable_reason', 'ddl_unavailable_reason'}


def model(row):
    native = row['native']
    if row['path'][-1] == 'RDB$ADMIN':
        raise ValueError('Built-in RDB$ADMIN requires its separate administration lifecycle')
    if native.get('unknown_system_privilege_bits') not in (None, []):
        raise ValueError('Unknown native role privilege bits prevent exact planning')
    privileges = native.get('system_privileges')
    if (not isinstance(privileges, list) or
            any(not isinstance(value, str) or value not in FIREBIRD_SYSTEM_PRIVILEGES
                for value in privileges) or len(privileges) != len(set(privileges))):
        raise ValueError('Role requires an exact list of known native system privileges')
    return {'system_privileges': [value for value in FIREBIRD_SYSTEM_PRIVILEGES
                                  if value in privileges]}


def context(current):
    databases = [row for row in current['rows'].values() if row['kind'] == 'database']
    observations = databases[0]['native'].get('catalog_observations', []) if len(databases) == 1 else []
    evidence = [item for item in observations if item.get('section') == 'role objects']
    if len(evidence) != 1 or evidence[0].get('available') is not True:
        raise ValueError('Role planning requires available catalog observation: role objects')


def statements(before, after):
    name = identifier(after['name'])
    privileges = after['system_privileges']
    clause = ' SET SYSTEM PRIVILEGES TO ' + ', '.join(privileges) if privileges else ''
    if before is None:
        return ['CREATE ROLE ' + name + clause]
    if before['system_privileges'] != privileges:
        return ['ALTER ROLE ' + name + (clause or ' DROP SYSTEM PRIVILEGES')]
    return []


def security_change(before, after):
    old = before['system_privileges'] if before else []
    new = after['system_privileges']
    return {'added_system_privileges': [value for value in new if value not in old],
            'removed_system_privileges': [value for value in old if value not in new],
            'memberships': 'preserve; not changed by this plan',
            'ownership': 'creating native user' if before is None else 'preserve'}
