"""Exact native statement export; no SQL execution or transaction ownership."""
import hashlib
import json

from ..providers.firebird.privileges import compile_privilege
from ..sdk.relational import RelationalClientError
from . import firebird_view_plan
from . import firebird_routine_plan as routines
from . import firebird_routine_stages as routine_stages
from ..providers.firebird.mappings import identifier

DDL_KINDS = frozenset({'table', 'view', 'domain', 'sequence', 'exception',
    'role', 'blob-filter', 'external-function', 'function', 'procedure',
    'package', 'trigger', 'index', 'constraint', 'collation'})
DEPENDENCY_KINDS = {0: {'table', 'view'}, 1: {'view'}, 5: {'procedure'},
    7: {'exception'}, 9: {'domain'}, 10: {'index'}, 13: {'role'},
    14: {'sequence'}, 15: {'function', 'external-function'},
    16: {'blob-filter'}, 17: {'collation'}, 18: {'package'}, 19: {'package'}}
PRINCIPAL_KINDS = {1: 'VIEW', 2: 'TRIGGER', 5: 'PROCEDURE', 8: 'USER',
                   12: 'GROUP', 13: 'ROLE', 15: 'FUNCTION', 18: 'PACKAGE'}
OBJECT_KINDS = {0: 'TABLE', 5: 'PROCEDURE', 7: 'EXCEPTION',
                14: 'SEQUENCE', 15: 'FUNCTION', 18: 'PACKAGE'}
PRIVILEGES = {'S': 'SELECT', 'I': 'INSERT', 'U': 'UPDATE', 'D': 'DELETE',
              'R': 'REFERENCES', 'X': 'EXECUTE', 'G': 'USAGE'}


def script(statements):
    """SET TERM is an ISQL directive; arbitrary native bodies remain intact."""
    if not isinstance(statements, list) or any(
            not isinstance(value, str) or not value.strip() or '\0' in value
            for value in statements):
        raise ValueError('Native export requires complete nonempty statements')
    joined = '\n'.join(statements)
    if len(joined.encode('utf-8')) > 8 * 1024 * 1024:
        raise ValueError('Native SQL export exceeds 8 MiB')
    nonce = 0
    terminator = '^'
    while terminator in joined:
        nonce += 1
        terminator = '^' + hashlib.sha256((str(nonce) + joined).encode()).hexdigest()[:12] + '^'
    return ('SET AUTODDL OFF;\nSET TERM ' + terminator + ' ;\n\n' +
            '\n\n'.join(value + '\n' + terminator for value in statements) +
            '\n\nSET TERM ; ' + terminator + '\n')


def grant_statement(native, operation='grant'):
    if operation not in {'grant', 'revoke'}:
        raise ValueError('Unknown privilege operation')
    privilege = native.get('privilege')
    principal = PRINCIPAL_KINDS.get(native.get('user_type'))
    if native.get('grantee') == 'PUBLIC' and principal == 'USER':
        principal = 'PUBLIC'
    if not principal or not native.get('grantor'):
        raise ValueError('Grant principal or grantor is unavailable')
    if native.get('grant_option') not in {0, 1, 2}:
        raise ValueError('Grant option is unavailable')
    draft = {'principal_kind': principal, 'principal': native.get('grantee'),
             'grantor': native['grantor'], 'grant_option': operation == 'grant' and native['grant_option'] == 1}
    if operation == 'revoke':
        draft['confirmation'] = native.get('grantee')
    if privilege == 'M' and native.get('object_type') == 13:
        if operation != 'grant':
            raise ValueError('Membership revocation is outside metadata export')
        if principal not in {'USER', 'ROLE'}:
            raise ValueError('Role membership principal is unsupported')
        source = 'GRANT ' + ('DEFAULT ' if native.get('default_role') else '')
        source += identifier(native.get('object_name')) + ' TO ' + principal + ' '
        source += identifier(native.get('grantee'))
        if native['grant_option'] == 2:
            source += ' WITH ADMIN OPTION'
        elif native['grant_option'] != 0:
            raise ValueError('Invalid role membership option')
        return source + ' GRANTED BY USER ' + identifier(native['grantor'])
    if native['grant_option'] == 2:
        raise ValueError('ADMIN OPTION is only valid for membership')
    resolution = native.get('target_resolution', {})
    if resolution.get('state') == 'class-scope':
        value = {'C': 'CREATE', 'L': 'ALTER ANY', 'O': 'DROP ANY'}.get(privilege)
        if not value:
            raise ValueError('Unknown DDL class privilege')
        draft.update(privilege_scope='ddl_class', ddl_class=resolution['ddl_class'],
                     ddl_privileges=[value])
    elif native.get('object_type') == 21:
        value = {'L': 'ALTER', 'O': 'DROP'}.get(privilege)
        if not value:
            raise ValueError('Unsupported database grant')
        draft.update(privilege_scope='database', database_privileges=[value])
    else:
        if resolution.get('state') != 'resolved':
            raise ValueError('Grant target is not uniquely resolved')
        value = PRIVILEGES.get(privilege)
        if not value or native.get('object_type') not in OBJECT_KINDS:
            raise ValueError('Unknown native object privilege')
        draft.update(privilege_scope='object', object_type=OBJECT_KINDS[native['object_type']],
                     object_name=native.get('object_name'), privileges=[value])
        if native.get('field'):
            field = {'U': 'update_columns', 'R': 'reference_columns'}.get(privilege)
            if not field:
                raise ValueError('Unsupported column privilege')
            draft[field] = [{'name': native['field']}]
    return compile_privilege(operation, draft)


def build_metadata(model):
    rows = model['rows']
    blocks, edges, blockers, prerequisites, requirements = {}, {}, [], [], []
    package_bodies, foreign_keys, routine_bodies = {}, {}, {}
    def problem(row, reason):
        blockers.append({'resource_id': row['resource_id'], 'name': row['name'],
                         'kind': row['kind'], 'reason': str(reason)})
    def matches(name, kinds):
        return [row for row in rows.values() if row['name'] == name and
                row['kind'] in kinds and not row['native'].get('package')]
    def require(row, name, kinds, *, body_only=False):
        if not isinstance(name, str) or not name:
            problem(row, 'Native prerequisite identity is unavailable')
            return
        found = matches(name, kinds)
        if len(found) > 1:
            problem(row, 'Ambiguous prerequisite: ' + name)
        elif not found:
            prerequisites.append({'resource_id': row['resource_id'], 'name': name,
                                  'kinds': sorted(kinds)})
        elif not body_only and found[0]['resource_id'] != row['resource_id'] and found[0]['system'] != 'true':
            edges[row['resource_id']].add(found[0]['resource_id'])
    backing = {row['native'].get('index_name') for row in rows.values()
               if row['kind'] == 'constraint'}
    for identity, row in rows.items():
        kind, native = row['kind'], row['native']
        if row['system'] == 'true' or kind not in DDL_KINDS:
            continue
        if native.get('package') or native.get('constraint_owner'):
            continue
        if kind == 'index' and row['name'] in backing:
            continue
        if kind == 'constraint' and len(row['path']) > 1 and matches(row['path'][-2], {'table'}):
            continue
        statements = native.get('recreation_statements')
        staged = kind == 'table' and 'recreation_deferred_statements' in native
        if staged:
            primary = native.get('recreation_primary_statements')
            deferred = native['recreation_deferred_statements']
            if (not isinstance(primary, list) or not primary or not isinstance(deferred, list) or
                    any(not isinstance(value, str) or not value.strip() for value in primary + deferred) or
                    (any(item.get('constraint_type') == 'FOREIGN KEY' for item in native.get('constraints', [])) and not deferred)):
                problem(row, 'Incomplete staged native table definitions'); continue
            statements = primary
            foreign_keys[identity] = deferred
        if not statements and kind == 'view':
            try:
                definition = dict(firebird_view_plan.model(row), name=row['name'])
                statements = firebird_view_plan.statements(None, definition)
                comments = [('VIEW', identifier(row['name']), native.get('description'))]
                comments.extend(('COLUMN', identifier(row['name']) + '.' + identifier(column['name']),
                                 column.get('description')) for column in native.get('columns') or [])
                for comment_kind, name, value in comments:
                    if value is not None:
                        statements.append('COMMENT ON ' + comment_kind + ' ' + name + " IS '" + str(value).replace("'", "''") + "'")
            except (ValueError, RelationalClientError) as error:
                problem(row, error); continue
        if not statements:
            # Only a native single-statement definition is safe to unwrap.
            # Renderers for multi-statement families publish an exact array.
            if kind in {'constraint', 'view', 'collation'} and native.get('ddl'):
                statements = [native['ddl'].removesuffix(';')]
            else:
                problem(row, native.get('ddl_unavailable_reason') or 'Exact native statement array unavailable')
                continue
        if not isinstance(statements, list) or any(not isinstance(s, str) or not s.strip() for s in statements):
            problem(row, 'Invalid native statements'); continue
        blocks[identity], edges[identity] = statements, set()
        if kind == 'package':
            # Provider arrays contain one header followed by complete body and
            # comment statements. Never split PSQL text at internal semicolons.
            blocks[identity] = statements[:1]
            package_bodies[identity] = statements[1:]
        if native.get('owner'):
            requirements.append({'resource_id': identity, 'execute_as_user': native['owner']})
        for dependency in native.get('dependencies') or []:
            kinds = DEPENDENCY_KINDS.get(dependency.get('object_type_code'))
            if kinds:
                name = dependency.get('package_name') or dependency.get('object_name')
                require(row, name, {'package'} if dependency.get('package_name') else kinds,
                        body_only=kind == 'package' and dependency.get('dependent_type_code') == 19)
            elif dependency.get('object_type_code') not in {3, 4, 8, 11, 12}:
                problem(row, 'Unknown dependency type: ' + str(dependency.get('object_type_code')))
        if kind in {'index', 'constraint'} and len(row['path']) > 1:
            require(row, row['path'][-2], {'table', 'view'})
        if kind == 'trigger' and native.get('relation'):
            require(row, native['relation'], {'table', 'view'})
        if kind == 'table':
            for column in native.get('columns') or []:
                domain = column.get('domain')
                if domain and matches(domain, {'domain'}):
                    require(row, domain, {'domain'})
            for constraint in native.get('constraints') or []:
                if constraint.get('referenced_relation'):
                    require(row, constraint['referenced_relation'], {'table'}, body_only=staged)
    statements, ordered = [], []
    pending = {key: value & blocks.keys() for key, value in edges.items()}
    while pending:
        ready = sorted(key for key, value in pending.items() if not value)
        if not ready:
            candidates = {key for key in pending if key not in routine_bodies and
                rows[key]['kind'] in {'procedure', 'function'} and not rows[key]['native'].get('engine_name')}
            affected = {key for key in candidates if pending[key] & candidates}
            for key in sorted(affected):
                row = rows[key]
                try:
                    definition = {**routines.model(row), 'name': row['name']}
                    primary, body = routine_stages.parts(row['kind'], definition)
                    routine_bodies[key] = body[:1] + blocks[key][1:]
                    blocks[key] = primary
                    pending[key].difference_update(candidates)
                except (ValueError, RelationalClientError) as error:
                    problem(row, error)
                    affected = set()
                    break
            if affected:
                continue
            for key in sorted(pending):
                problem(rows[key], 'Creation dependency cycle requires staged definitions')
            break
        for key in ready:
            ordered.append(key); statements.extend(blocks[key]); del pending[key]
        for value in pending.values():
            value.difference_update(ready)
    for identity in ordered:
        statements.extend(foreign_keys.get(identity, []))
    for identity in ordered:
        statements.extend(routine_bodies.get(identity, []))
        statements.extend(package_bodies.get(identity, []))
    grants, seen_grants, automatic_grants = {}, set(), []
    for row in rows.values():
        native = row['native']
        candidates = ([native] if row['kind'] == 'privilege' else native.get('privileges', []))
        for grant in candidates:
            fingerprint = json.dumps(grant, sort_keys=True, default=str)
            if fingerprint in seen_grants:
                continue
            seen_grants.add(fingerprint)
            if not grant.get('grantor'):
                # Firebird ini.epp creates built-in grants with NULL grantor.
                automatic_grants.append({'name': grant.get('object_name'), 'reason': 'engine-initialized grant'})
                continue
            target_ids = grant.get('target_resolution', {}).get('resource_ids', [])
            targets = [rows[key] for key in target_ids if key in rows]
            if (len(targets) == 1 and grant.get('user_type') == 8 and
                    grant.get('grantee') == grant.get('grantor') == targets[0]['native'].get('owner') and
                    grant.get('grant_option') == 1 and not grant.get('field')):
                # Native CREATE restores these privileges under the owner.
                automatic_grants.append({'name': grant.get('object_name'), 'reason': 'creating-owner grant'})
                continue
            if grant.get('catalog_source') == 'SEC$DB_CREATORS':
                continue  # Server-security authority is not database metadata.
            try:
                statement = grant_statement(grant)
                grants[statement] = True
            except (ValueError, TypeError, RelationalClientError) as error:
                problem(row, error)
    statements.extend(sorted(grants))
    header = {
        'format': 'scratchrobin.firebird.metadata-sql@1',
        'provenance': model['provenance'],
        'external_prerequisites': prerequisites,
        'ownership_requirements': requirements,
        'automatic_grants_restored_by_engine': len(automatic_grants),
        'contains_data': False,
        'staged_routine_signatures': sorted(routine_bodies),
    }
    text = None if blockers else ('-- ScratchRobin native metadata export\n' +
        '-- Review prerequisites and creating users before execution.\n' +
        '-- ' + json.dumps(header, ensure_ascii=True, sort_keys=True, default=str) +
        '\n' + script(statements))
    if text and len(text.encode('utf-8')) > 8 * 1024 * 1024:
        raise ValueError('Native SQL and provenance exceed 8 MiB')
    return {'format': 'scratchrobin.firebird.metadata-sql@1',
            'filename': 'firebird-metadata.sql', 'download_text': text,
            'sha256': hashlib.sha256(text.encode()).hexdigest() if text else None,
            'objects': ordered, 'blockers': blockers,
            'automatic_grants': automatic_grants,
            'external_prerequisites': prerequisites, 'ownership_requirements': requirements,
            'provenance': model['provenance'], 'contains_data': False,
            'native_replay_verified': False}
