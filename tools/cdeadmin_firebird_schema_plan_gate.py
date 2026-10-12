#!/usr/bin/env python3
"""Qualify generated schema previews in an owned disposable Firebird 5 DB."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import secrets
import socket
import shutil
import time
import uuid

if __package__:
    from .cdeadmin_firebird_logical_volumes_gate import (
        docker, published_port, _configure_client_library, _route_arguments)
else:
    from cdeadmin_firebird_logical_volumes_gate import (
        docker, published_port, _configure_client_library, _route_arguments)
from pgadmin.cdeadmin.providers.firebird.provider import _resources
from pgadmin.cdeadmin.providers.firebird.identity import catalog_resource_id
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan, _model

OWNER = 'firebird-schema-plan'


def run(root, image, table_only=False, recreate_only=False, column_only=False, package_only=False, routine_only=False, trigger_only=False, constraint_only=False, inspection_only=False, lifecycle_only=False, privileges_only=False, import_order_only=False, external_functions_only=False, grant_plan_only=False):
    import firebird.driver as native
    _configure_client_library(native)
    root.mkdir(parents=True, exist_ok=False)
    fixture = root / 'database'
    fixture.mkdir(mode=0o777)
    fixture.chmod(0o777)
    password = secrets.token_urlsafe(24)
    container = connection = None
    result = {'schema': 'scratchrobin.firebird.schema-plan-gate@1',
              'complete': False, 'scope': 'grant-planning' if grant_plan_only else 'external-function-planning' if external_functions_only else 'import-row-order' if import_order_only else 'privilege-queue' if privileges_only else 'identity-lifecycle' if lifecycle_only else 'statement-inspection' if inspection_only else 'constraint-planning' if constraint_only else 'trigger-planning' if trigger_only else 'routine-planning' if routine_only else 'package-planning' if package_only else 'column-planning' if column_only else 'recreate-empty' if recreate_only else 'table-planning' if table_only else 'combined', 'checks': [], 'owned_container_removed': False,
              'database_removed': False}

    def sql(statement, parameters=()):
        with connection.cursor() as cursor:
            cursor.execute(statement, parameters)
            return cursor.fetchall() if cursor.description else []

    def from_rows(rows):
        snapshot = build_export(rows, endpoint_id='owned', target_id='owned', generation=uuid.uuid4().hex)
        document = read_catalog(snapshot['snapshot']['files']['catalog.ddn'])
        document['_rows'] = rows
        return document

    def capture():
        rows = _resources(connection, {})
        connection.rollback()
        return from_rows(rows)

    def execute(plan):
        (root / 'last-plan.json').write_text(json.dumps(plan, indent=2))
        assert plan['status'] == 'review-ready' and not plan['apply_available']
        # Deliberate test harness execution in an isolated fixture. Product
        # preview has no execution path and does not grant apply authority.
        for phase in ('statements', 'deferred_statements'):
            for operation in plan['operations']:
                for statement in operation.get(phase, []):
                    sql(statement)
        connection.commit()

    try:
        with socket.socket() as port_probe:
            port_probe.bind(('127.0.0.1', 0))
            auxiliary_port = port_probe.getsockname()[1]
        result['auxiliary_event_port'] = auxiliary_port
        container = docker('create', '--name', 'cdeadmin-schema-' + uuid.uuid4().hex[:16],
            '--label', 'cdeadmin-owned-gate=' + OWNER, '--publish', '127.0.0.1::3050',
            '--publish', f'127.0.0.1:{auxiliary_port}:{auxiliary_port}',
            '--env', f'FIREBIRD_CONF_RemoteAuxPort={auxiliary_port}',
            '--mount', 'type=bind,source=' + str(fixture) + ',target=/qualification',
            '--env', 'FIREBIRD_ROOT_PASSWORD', '--env', 'FIREBIRD_DATABASE', image,
            env=dict(os.environ, FIREBIRD_ROOT_PASSWORD=password,
                     FIREBIRD_DATABASE='/qualification/schema.fdb')).decode().strip()
        if not re.fullmatch('[0-9a-f]{64}', container):
            raise RuntimeError('Invalid owned container identity')
        result['container_id'] = container
        docker('start', container)
        route = {'host': '127.0.0.1', 'port': published_port(container), 'user': 'SYSDBA',
                 'database': '/qualification/schema.fdb', 'charset': 'UTF8', 'timeout': 2}
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                connection = native.connect(password=password, **_route_arguments(route, native))
                break
            except native.Error:
                time.sleep(0.25)
        if connection is None:
            raise RuntimeError('Owned Firebird readiness deadline exceeded')
        if table_only or recreate_only or column_only or package_only or routine_only or trigger_only or constraint_only or inspection_only or lifecycle_only or privileges_only or import_order_only or external_functions_only or grant_plan_only:
            from types import SimpleNamespace
            from pgadmin.cdeadmin.providers.firebird.provider import _create_client, FirebirdProvider
            from pgadmin.cdeadmin.security.secrets import SecretLease
            from tools.firebird_table_plan_native import qualify as qualify_tables
            credentials = SimpleNamespace(acquire_secret=lambda *_: SecretLease(password))
            client = _create_client(credentials)
            provider = object.__new__(FirebirdProvider)
            provider.client = client
            provider.attachment_mode = 'network'
            provider.permissions = SimpleNamespace(require=lambda *_: None)
            apply_route = {**route, 'credential_reference_id': 'owned-fixture', 'principal_reference': 'owned-gate'}
            if grant_plan_only:
                from tools.firebird_grant_plan_native import qualify
                result['grant_planning'] = qualify(connection, provider, apply_route, root)
            elif external_functions_only:
                from tools.firebird_external_function_plan_native import qualify
                result['external_function_planning'] = qualify(connection, provider, apply_route, root)
            elif import_order_only:
                from tools.firebird_import_order_native import qualify as qualify_import_order
                result['import_order'] = qualify_import_order(connection, provider, apply_route, root)
            elif privileges_only:
                from tools.firebird_privilege_queue_native import qualify as qualify_privileges
                result['privileges'] = qualify_privileges(connection, provider, apply_route, root)
            elif lifecycle_only:
                from tools.firebird_lifecycle_native import qualify as qualify_lifecycle
                result['lifecycle'] = qualify_lifecycle(connection, provider, apply_route, root)
            elif inspection_only:
                from tools.firebird_statement_inspection_native import qualify as qualify_inspection
                result['statement_inspection'] = qualify_inspection(connection, provider, apply_route, root, credentials)
            elif constraint_only:
                from tools.firebird_constraint_plan_native import qualify as qualify_constraints
                result['constraint_planning'] = qualify_constraints(connection, provider, apply_route, root)
            elif trigger_only:
                from tools.firebird_trigger_plan_native import qualify as qualify_triggers
                result['trigger_planning'] = qualify_triggers(connection, provider, apply_route, root)
            elif routine_only:
                from tools.firebird_routine_plan_native import qualify as qualify_routines
                result['routine_planning'] = qualify_routines(connection, provider, apply_route, root)
            elif package_only:
                from tools.firebird_package_plan_native import qualify as qualify_packages
                result['package_planning'] = qualify_packages(connection, provider, apply_route, root)
            elif column_only:
                from tools.firebird_column_plan_native import qualify as qualify_columns
                result['column_planning'] = qualify_columns(connection, provider, apply_route, root)
            elif recreate_only:
                from tools.firebird_recreate_native import qualify as qualify_recreate
                result['recreate_empty'] = qualify_recreate(client, apply_route, password)
            else:
                result['table_planning'] = qualify_tables(connection, provider, apply_route)
            result['complete'] = True
            return result
        baseline = capture()
        result['engine_version'] = next(row['native']['version'] for row in baseline['rows'].values()
                                        if row['kind'] == 'server')
        authored_rows = deepcopy(baseline['_rows'])
        definitions = [('sequence', 'S:ü"', {'initial_value': '9007199254740993', 'increment': 1, 'description': 'original'}),
                       ('exception', 'E:ü"', {'message': "Quoted 'message';", 'description': 'original'})]
        identities = []
        for kind, name, metadata in definitions:
            identity = catalog_resource_id(kind, [], name)
            identities.append(identity)
            authored_rows.append({'resource_id': identity, 'resource_kind': kind, 'display_name': name,
                                  'display_path': [name], 'native': metadata})
        authored = from_rows(authored_rows)
        create = build_plan(baseline, authored, baseline)
        execute(create)
        actual = capture()
        for identity in identities:
            assert _model(actual['rows'][identity]) == _model(authored['rows'][identity])
        result['checks'].append('native-create-and-exact-discovery')
        assert build_plan(actual, actual, actual)['status'] == 'no-op'
        desired_rows = deepcopy(actual['_rows'])
        for row in desired_rows:
            if row['resource_id'] == identities[0]:
                row['native']['increment'] = -3
            elif row['resource_id'] == identities[1]:
                row['native']['message'] = 'changed'
                row['native']['description'] = None
        desired = from_rows(desired_rows)
        value = sql('SELECT NEXT VALUE FOR "S:ü""" FROM RDB$DATABASE')[0][0]
        connection.rollback()
        assert value == 9007199254740993
        sql('COMMENT ON SEQUENCE "S:ü""" IS \'external comment\'')
        connection.commit()
        current = capture()
        alter = build_plan(actual, desired, current)
        execute(alter)
        final = capture()
        assert _model(final['rows'][identities[0]])['description'] == 'external comment'
        assert _model(final['rows'][identities[0]])['increment'] == '-3'
        assert _model(final['rows'][identities[1]])['message'] == 'changed'
        assert _model(final['rows'][identities[1]])['description'] is None
        assert sql('SELECT GEN_ID("S:ü""", 0) FROM RDB$DATABASE')[0][0] == value
        connection.rollback()
        result['checks'].append('native-alter-independent-merge-comment-removal-and-position-preserved')
        assert build_plan(actual, desired, final)['status'] == 'no-op'
        competing = deepcopy(desired)
        competing['rows'][identities[0]]['native']['increment'] = 5
        assert build_plan(actual, competing, final)['status'] == 'blocked'
        result['checks'].append('converged-noop-and-conflict-refusal')
        sql('CREATE TABLE "Index:ü" ("A" INTEGER, "B" INTEGER, CONSTRAINT "PK:ü" PRIMARY KEY ("A"))')
        sql('CREATE INDEX "Computed:ü" ON "Index:ü" COMPUTED BY ("A" + 1)')
        sql('CREATE INDEX "Partial:ü" ON "Index:ü" ("B") WHERE "B" > 0')
        connection.commit()
        index_base = capture()
        index_rows = deepcopy(index_base['_rows'])
        index_id = catalog_resource_id('index', ['Index:ü'], 'I:ü"')
        index_rows.append({'resource_id': index_id, 'resource_kind': 'index',
            'display_name': 'I:ü"', 'display_path': ['Index:ü', 'I:ü"'], 'native': {
                'unique': 1, 'index_type': 1, 'inactive': 1, 'description': 'original index',
                'expression_source': None, 'condition_source': None,
                'segments': [{'field_name': 'B', 'position': 0}, {'field_name': 'A', 'position': 1}]}})
        expression_definitions = [
            ('Authored computed:ü', '("A" + 7)', None),
            ('Authored partial:ü', None, 'WHERE "B" > 5'),
            ('Authored combined:ü', '("A" + "B")', 'WHERE "B" IS NOT NULL'),
        ]
        expression_ids = []
        for name, expression, condition in expression_definitions:
            identity = catalog_resource_id('index', ['Index:ü'], name)
            expression_ids.append(identity)
            index_rows.append({'resource_id': identity, 'resource_kind': 'index',
                'display_name': name, 'display_path': ['Index:ü', name], 'native': {
                    'unique': 0, 'index_type': 0, 'inactive': 0, 'description': None,
                    'expression_source': expression, 'condition_source': condition,
                    'segments': [] if expression else [{'field_name': 'B', 'position': 0}]}})
        index_desired = from_rows(index_rows)
        index_create = build_plan(index_base, index_desired, index_base)
        execute(index_create)
        index_actual = capture()
        assert _model(index_actual['rows'][index_id]) == _model(index_desired['rows'][index_id])
        for identity in expression_ids:
            assert _model(index_actual['rows'][identity]) == _model(index_desired['rows'][identity]), (
                _model(index_actual['rows'][identity]), _model(index_desired['rows'][identity]))
        result['checks'].append('native-computed-partial-and-combined-index-creation')
        edit_rows = deepcopy(index_actual['_rows'])
        computed_id = catalog_resource_id('index', ['Index:ü'], 'Computed:ü')
        partial_id = catalog_resource_id('index', ['Index:ü'], 'Partial:ü')
        for row in edit_rows:
            if row['resource_id'] == index_id:
                row['native']['inactive'] = 0
            elif row['resource_id'] == computed_id:
                row['native']['inactive'] = 1
            elif row['resource_id'] == partial_id:
                row['native']['description'] = 'partial comment'
        index_edit = from_rows(edit_rows)
        sql('COMMENT ON INDEX "I:ü""" IS \'independent index comment\'')
        connection.commit()
        index_current = capture()
        index_alter = build_plan(index_actual, index_edit, index_current)
        execute(index_alter)
        index_final = capture()
        assert _model(index_final['rows'][index_id])['inactive'] == '0'
        assert _model(index_final['rows'][index_id])['description'] == 'independent index comment'
        assert _model(index_final['rows'][computed_id])['inactive'] == '1'
        assert _model(index_final['rows'][partial_id])['description'] == 'partial comment'
        assert build_plan(index_actual, index_edit, index_final)['status'] == 'no-op'
        constraint = next(row for row in index_final['rows'].values() if row['kind'] == 'constraint'
                          and row['native'].get('constraint_type') == 'PRIMARY KEY' and row['path'][0] == 'Index:ü')
        backing_id = catalog_resource_id('index', ['Index:ü'], constraint['native']['index_name'])
        forbidden = deepcopy(index_final)
        forbidden['rows'][backing_id]['native']['inactive'] = 1
        assert build_plan(index_final, forbidden, index_final)['status'] == 'blocked'
        result['checks'].append('index-create-state-comments-computed-partial-preservation-and-constraint-refusal')
        (root / 'plans.json').write_text(json.dumps({'create': create, 'alter': alter,
            'index_create': index_create, 'index_alter': index_alter}, indent=2))
        role_base = capture()
        role_rows = deepcopy(role_base['_rows'])
        role_name = 'Role:ü"'
        role_id = catalog_resource_id('role', [], role_name)
        role_rows.append({'resource_id': role_id, 'resource_kind': 'role',
            'display_name': role_name, 'display_path': [role_name], 'native': {
                'system_privileges': ['MONITOR_ANY_ATTACHMENT'], 'description': 'original role'}})
        role_desired = from_rows(role_rows)
        role_create = build_plan(role_base, role_desired, role_base)
        execute(role_create)
        role_actual = capture()
        assert _model(role_actual['rows'][role_id]) == _model(role_desired['rows'][role_id])
        edited_roles = deepcopy(role_actual['_rows'])
        for row in edited_roles:
            if row['resource_id'] == role_id:
                row['native']['system_privileges'] = ['READ_RAW_PAGES', 'USE_GSTAT_UTILITY']
        role_edit = from_rows(edited_roles)
        sql('COMMENT ON ROLE "Role:ü\"\"" IS \'external role comment\'')
        sql('CREATE ROLE "Member:ü"')
        sql('GRANT "Role:ü\"\"" TO ROLE "Member:ü"')
        connection.commit()
        role_current = capture()
        role_alter = build_plan(role_actual, role_edit, role_current)
        execute(role_alter)
        role_final = capture()
        assert _model(role_final['rows'][role_id])['system_privileges'] == ['READ_RAW_PAGES', 'USE_GSTAT_UTILITY']
        assert _model(role_final['rows'][role_id])['description'] == 'external role comment'
        assert role_final['rows'][role_id]['native']['memberships'] == role_current['rows'][role_id]['native']['memberships']
        assert role_final['rows'][role_id]['native']['owner'] == role_current['rows'][role_id]['native']['owner']
        assert build_plan(role_actual, role_edit, role_final)['status'] == 'no-op'
        dropped_roles = deepcopy(role_final['_rows'])
        for row in dropped_roles:
            if row['resource_id'] == role_id:
                row['native']['system_privileges'] = []
                row['native']['description'] = None
        role_drop_desired = from_rows(dropped_roles)
        role_drop_privileges = build_plan(role_final, role_drop_desired, role_final)
        execute(role_drop_privileges)
        role_dropped = capture()
        assert _model(role_dropped['rows'][role_id]) == _model(role_drop_desired['rows'][role_id])
        assert role_dropped['rows'][role_id]['native']['memberships'] == role_final['rows'][role_id]['native']['memberships']
        result['checks'].append('native-role-create-replace-drop-privileges-and-membership-owner-preservation')
        (root / 'role-plans.json').write_text(json.dumps({
            'create': role_create, 'alter': role_alter, 'drop_privileges': role_drop_privileges}, indent=2))
        filter_base = capture()
        filter_rows = deepcopy(filter_base['_rows'])
        filter_name = 'Filter:ü"'
        filter_id = catalog_resource_id('blob-filter', [], filter_name)
        filter_rows.append({'resource_id': filter_id, 'resource_kind': 'blob-filter',
            'display_name': filter_name, 'display_path': [filter_name], 'native': {
                'input_subtype': -20, 'output_subtype': -21,
                'module_name': 'not_loaded', 'entrypoint': 'not_invoked',
                'description': 'original filter'}})
        filter_desired = from_rows(filter_rows)
        filter_create = build_plan(filter_base, filter_desired, filter_base)
        execute(filter_create)
        filter_actual = capture()
        assert _model(filter_actual['rows'][filter_id]) == _model(filter_desired['rows'][filter_id])
        filter_receipts = {'create': filter_create}
        for label, comment in [('empty', ''), ('restored', 'restored'), ('removed', None)]:
            edited_filters = deepcopy(filter_actual['_rows'])
            for row in edited_filters:
                if row['resource_id'] == filter_id:
                    row['native']['description'] = comment
            filter_edit = from_rows(edited_filters)
            filter_plan = build_plan(filter_actual, filter_edit, filter_actual)
            execute(filter_plan)
            filter_final = capture()
            assert _model(filter_final['rows'][filter_id]) == _model(filter_edit['rows'][filter_id]), (
                _model(filter_final['rows'][filter_id]), _model(filter_edit['rows'][filter_id]))
            assert filter_final['rows'][filter_id]['native']['owner'] == filter_actual['rows'][filter_id]['native']['owner']
            assert build_plan(filter_actual, filter_edit, filter_final)['status'] == 'no-op'
            filter_receipts[label] = filter_plan
            filter_actual = filter_final
        result['checks'].append('native-filter-declaration-and-exact-empty-null-comments-no-library-invocation')
        (root / 'filter-plans.json').write_text(json.dumps(filter_receipts, indent=2))
        # Verify native empty-comment storage independently of model normalization.
        empty_base = capture()
        names = [('sequence', identities[0], 'S:ü"'),
                 ('exception', identities[1], 'E:ü"'),
                 ('index', index_id, 'I:ü"'),
                 ('role', role_id, role_name),
                 ('blob-filter', filter_id, filter_name)]
        from pgadmin.cdeadmin.providers.firebird.character_metadata import identifier
        for kind, identity, name in names:
            noun = 'FILTER' if kind == 'blob-filter' else kind.upper()
            sql('COMMENT ON ' + noun + ' ' + identifier(name) + " IS ''")
        connection.commit()
        empty_actual = capture()
        empty_rows = deepcopy(empty_base['_rows'])
        selected = {identity for _, identity, _ in names}
        for row in empty_rows:
            if row['resource_id'] in selected:
                row['native']['description'] = ''
        empty_desired = from_rows(empty_rows)
        for _, identity, _ in names:
            assert empty_actual['rows'][identity]['native']['description'] is None
        assert build_plan(empty_base, empty_desired, empty_actual)['status'] == 'no-op'
        result['checks'].append('native-empty-comment-is-null-for-all-five-supported-kinds')
        sql('CREATE DOMAIN "Domain:ü" AS INTEGER DEFAULT-1 CHECK(VALUE < 0)')
        sql('CREATE TABLE "Domain consumer" ("V" "Domain:ü")')
        connection.commit()
        domain_base = capture()
        domain_id = catalog_resource_id('domain', [], 'Domain:ü')
        domain_rows = deepcopy(domain_base['_rows'])
        for row in domain_rows:
            if row['resource_id'] == domain_id:
                row['native'].update(default_source='DEFAULT 3', not_null=1,
                    validation_source='CHECK (VALUE > 2)')
        domain_desired = from_rows(domain_rows)
        sql('COMMENT ON DOMAIN "Domain:ü" IS \'external comment\'')
        connection.commit()
        domain_current = capture()
        domain_alter = build_plan(domain_base, domain_desired, domain_current)
        execute(domain_alter)
        domain_final = capture()
        expected_domain = _model(domain_desired['rows'][domain_id])
        expected_domain['description'] = 'external comment'
        assert _model(domain_final['rows'][domain_id]) == expected_domain
        assert build_plan(domain_base, domain_desired, domain_final)['status'] == 'no-op'
        assert sql('INSERT INTO "Domain consumer" DEFAULT VALUES RETURNING "V"')[0][0] == 3
        connection.rollback()
        try:
            sql('INSERT INTO "Domain consumer" ("V") VALUES (1)')
        except native.DatabaseError:
            connection.rollback()
        else:
            raise AssertionError('Native domain CHECK was not enforced')
        try:
            sql('INSERT INTO "Domain consumer" ("V") VALUES (NULL)')
        except native.DatabaseError:
            connection.rollback()
        else:
            raise AssertionError('Native domain NOT NULL was not enforced')
        domain_removed_rows = deepcopy(domain_final['_rows'])
        for row in domain_removed_rows:
            if row['resource_id'] == domain_id:
                row['native'].update(default_source=None, validation_source=None,
                                     not_null=0, description='')
        domain_removed = from_rows(domain_removed_rows)
        domain_remove = build_plan(domain_final, domain_removed, domain_final)
        execute(domain_remove)
        domain_removed_actual = capture()
        assert _model(domain_removed_actual['rows'][domain_id]) == _model(domain_removed['rows'][domain_id])
        assert sql('INSERT INTO "Domain consumer" DEFAULT VALUES RETURNING "V"')[0][0] is None
        connection.rollback()
        sql('COMMENT ON DOMAIN "Domain:ü" IS \'\'')
        connection.commit()
        assert capture()['rows'][domain_id]['native']['description'] is None
        result['checks'].append('native-domain-default-check-nullability-comment-and-dependent-column-behavior')
        (root / 'domain-plans.json').write_text(json.dumps({
            'alter': domain_alter, 'remove': domain_remove}, indent=2))
        from pgadmin.cdeadmin.workspace import firebird_domain_plan as domain_types
        type_matrix = [
            'SMALLINT', 'INTEGER', 'BIGINT', 'INT128',
            'NUMERIC(4,2)', 'NUMERIC(9,3)', 'NUMERIC(18,4)', 'NUMERIC(38,8)',
            'DECIMAL(4,2)', 'DECIMAL(18,4)', 'DECIMAL(38,8)',
            'CHAR(5) CHARACTER SET UTF8 COLLATE UNICODE_CI',
            'VARCHAR(15) CHARACTER SET UTF8', 'BINARY(5)', 'VARBINARY(12)',
            'BLOB SUB_TYPE 0 SEGMENT SIZE 256',
            'BLOB SUB_TYPE TEXT SEGMENT SIZE 120 CHARACTER SET UTF8',
            'BLOB SUB_TYPE -2 SEGMENT SIZE 80',
            'DATE', 'TIME', 'TIMESTAMP', 'TIME WITH TIME ZONE',
            'TIMESTAMP WITH TIME ZONE', 'BOOLEAN', 'FLOAT', 'DOUBLE PRECISION',
            'DECFLOAT(16)', 'DECFLOAT(34)',
            'INTEGER DEFAULT 7 NOT NULL CHECK (VALUE > 0)',
            "VARCHAR(15) CHARACTER SET UTF8 DEFAULT 'a' NOT NULL CHECK (VALUE <> '') COLLATE UNICODE_CI",
            'INTEGER[-2:3,0:4]', 'NUMERIC(18,4)[-5:5]',
            'VARCHAR(8)[0:3] CHARACTER SET UTF8 COLLATE UNICODE_CI',
            'CHAR(3)[-1:1,4:6] CHARACTER SET UTF8',
            'BOOLEAN[0:1]', 'DATE[2:4]', 'TIMESTAMP[-3:0]',
            'DOUBLE PRECISION[0:2]', 'BINARY(4)[0:1]',
            'SMALLINT[' + ','.join('0:1' for _ in range(16)) + ']',
        ]
        for ordinal, definition in enumerate(type_matrix):
            sql('CREATE DOMAIN "Seed type ' + str(ordinal) + '" AS ' + definition)
        connection.commit()
        type_base = capture()
        type_rows = deepcopy(type_base['_rows'])
        created_types = []
        for ordinal, definition in enumerate(type_matrix):
            seed_id = catalog_resource_id('domain', [], 'Seed type ' + str(ordinal))
            native_type = type_base['rows'][seed_id]['native']
            new_name = 'Created type ' + str(ordinal)
            identity = catalog_resource_id('domain', [], new_name)
            created_types.append(identity)
            type_rows.append({'resource_id': identity, 'resource_kind': 'domain',
                'display_name': new_name, 'display_path': [new_name], 'native': {
                    key: value for key, value in native_type.items()
                    if key in domain_types.FIELDS | domain_types.TYPE_FIELDS}})
        # Omitted authored collation must resolve to the observed charset default.
        next(row for row in type_rows if row['resource_id'] == created_types[12])['native'].pop('collation')
        type_desired = from_rows(type_rows)
        native_current = build_export(type_base['_rows'], endpoint_id='owned', target_id='owned',
            generation=type_base['provenance']['generation'], native_model=True, include_system=True)
        type_plan = build_plan(type_base, type_desired, native_current)
        (root / 'domain-type-plan.json').write_text(json.dumps(type_plan, indent=2))
        execute(type_plan)
        type_actual = capture()
        type_results = []
        for ordinal, (identity, definition) in enumerate(zip(created_types, type_matrix)):
            expected = domain_types.creation_model(type_desired['rows'][identity], native_current)
            actual = domain_types.creation_model(type_actual['rows'][identity], native_current)
            assert actual == expected, (definition, actual, expected)
            assert _model(type_actual['rows'][identity]) == _model(type_desired['rows'][identity])
            seed_id = catalog_resource_id('domain', [], 'Seed type ' + str(ordinal))
            seed_native = type_base['rows'][seed_id]['native']
            actual_native = type_actual['rows'][identity]['native']
            assert {key: seed_native.get(key) for key in domain_types.TYPE_FIELDS} == {
                key: actual_native.get(key) for key in domain_types.TYPE_FIELDS}, definition
            type_results.append({'declaration': definition, 'resource_id': identity, 'descriptor': actual,
                'native_type_facts': {key: actual_native.get(key) for key in domain_types.TYPE_FIELDS}})
        (root / 'domain-type-results.json').write_text(json.dumps(type_results, indent=2))
        result['checks'].append('native-domain-creation-scalar-and-array-definitions-and-exact-native-type-rediscovery')
        # Exercise the product application path, not the gate's SQL loop.
        from types import SimpleNamespace
        from pgadmin.cdeadmin.providers.firebird.provider import _create_client, FirebirdProvider
        from pgadmin.cdeadmin.providers.firebird.schema_application import apply_review
        from pgadmin.cdeadmin.workspace.firebird_schema_apply import SchemaApplications
        from pgadmin.cdeadmin.security.secrets import SecretLease
        client = _create_client(SimpleNamespace(acquire_secret=lambda *_: SecretLease(password)))
        provider = object.__new__(FirebirdProvider)
        provider.client = client
        provider.attachment_mode = 'network'
        provider.permissions = SimpleNamespace(require=lambda *_: None)
        apply_route = {**route, 'credential_reference_id': 'owned-fixture',
                       'principal_reference': 'owned-gate'}
        applications = SchemaApplications(root / 'application-receipts.json')
        def application(baseline, desired, before_apply=None):
            plan = build_plan(baseline, desired, baseline)
            ticket = applications.review(plan, baseline, desired, 1, 'owned-binding', route['database'])
            if before_apply:
                before_apply()
            request = {'review_id': ticket['review_id'], 'review_digest': ticket['review_digest'], 'confirmed': True}
            calls = []
            def dispatch(record):
                calls.append(True)
                return apply_review(provider, apply_route, record)
            receipt = applications.apply(request, 1, 'owned-binding', dispatch)
            again = SchemaApplications(applications.path).apply(request, 1, 'owned-binding', dispatch)
            assert len(calls) == 1 and receipt == again
            return receipt
        apply_base = capture()
        apply_rows = deepcopy(apply_base['_rows'])
        for row in apply_rows:
            if row['resource_id'] == identities[1]:
                row['native']['message'] = 'Applied through product'
        committed = application(apply_base, from_rows(apply_rows))
        (root / 'application-committed.json').write_text(json.dumps(committed, indent=2))
        assert committed['state'] == 'native_commit_returned', committed
        assert committed['outcome']['attachment_released']
        assert all(row['matches_reviewed_properties'] for row in committed['outcome']['rediscovery']['objects'])
        rollback_base = capture()
        rollback_rows = deepcopy(rollback_base['_rows'])
        for row in rollback_rows:
            if row['resource_id'] == created_types[0]:
                row['native']['description'] = 'Must roll back with later failure'
            if row['resource_id'] == domain_id:
                row['native']['default_source'] = 'DEFAULT NONEXISTENT_NATIVE_FUNCTION()'
            if row['resource_id'] == identities[1]:
                row['native']['message'] = 'Must not commit'
        rolled_back = application(rollback_base, from_rows(rollback_rows))
        (root / 'application-rollback.json').write_text(json.dumps(rolled_back, indent=2))
        assert rolled_back['state'] == 'native_rollback_returned', rolled_back
        rollback_actual = capture()
        assert rollback_actual['rows'][identities[1]]['native']['message'] == 'Applied through product'
        assert rollback_actual['rows'][created_types[0]]['native']['description'] is None
        assert rolled_back['outcome']['statements_completed'] >= 1
        drift_base = capture()
        drift_rows = deepcopy(drift_base['_rows'])
        for row in drift_rows:
            if row['resource_id'] == identities[1]:
                row['native']['message'] = 'Not applied after drift'
        def external_change():
            sql('COMMENT ON EXCEPTION "E:ü""" IS \'changed after review\'')
            connection.commit()
        drift = application(drift_base, from_rows(drift_rows), external_change)
        (root / 'application-drift.json').write_text(json.dumps(drift, indent=2))
        assert drift['state'] == 'not_executed' and drift['outcome']['statements_completed'] == 0, drift
        assert capture()['rows'][identities[1]]['native']['message'] == 'Applied through product'
        result['checks'].append('product-schema-application-native-commit-rollback-drift-and-durable-no-replay')
        from tools.firebird_column_order_native import qualify as qualify_order
        ordering = qualify_order(connection, client, apply_route)
        result['column_order'] = ordering
        (root / 'column-order-native.json').write_text(json.dumps(ordering, indent=2))
        result['checks'].append('native-whole-table-column-order-borrowed-rollback-owned-commit-and-drift')
        from tools.firebird_profiler_native import qualify as qualify_profiler
        profiling = qualify_profiler(connection, client, apply_route)
        result['profiling'] = profiling
        (root / 'profiling-native.json').write_text(json.dumps(profiling, indent=2))
        result['checks'].append('native-psql-record-source-profiling-and-user-rollback-preserved')
        from tools.firebird_events_native import qualify as qualify_events
        result['events'] = qualify_events(connection, client, apply_route)
        from tools.firebird_row_sql_native import qualify as qualify_row_sql
        result['row_sql'] = qualify_row_sql(connection)
        from tools.firebird_view_plan_native import qualify as qualify_view_plan
        result['view_plan'] = qualify_view_plan(connection, provider, apply_route)
        from tools.firebird_templates_native import qualify as qualify_templates
        result['object_templates'] = qualify_templates(connection)
        from tools.firebird_metadata_search_native import qualify as qualify_search
        result['metadata_search'] = qualify_search(connection)
        from tools.firebird_blob_editor_native import qualify as qualify_blob_editor
        result['blob_editor'] = qualify_blob_editor(connection)
        from tools.firebird_editor_native import qualify as qualify_editor
        result['editor_formatting'] = qualify_editor(connection, client, apply_route)
        result['checks'].append('native-original-and-whitespace-formatted-source-values-equivalent')
        from tools.firebird_erd_native import qualify as qualify_erd
        result['relational_diagram'] = qualify_erd(connection, root)
        from tools.firebird_table_plan_native import qualify as qualify_tables
        result['table_planning'] = qualify_tables(connection, provider, apply_route)
        result['complete'] = True
    except Exception as error:
        result['error_type'] = type(error).__name__
        raise
    finally:
        if connection is not None:
            connection.close()
        if container:
            label = docker('inspect', '--format', '{{index .Config.Labels "cdeadmin-owned-gate"}}', container).decode().strip()
            if label != OWNER:
                raise RuntimeError('Refusing cleanup of unowned container')
            docker('rm', '--force', '--volumes', container)
            result['owned_container_removed'] = True
        if result['complete']:
            shutil.rmtree(fixture)
            result['database_removed'] = True
        (root / 'result.json').write_text(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--image', default='firebirdsql/firebird:5.0.4')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--table-only', action='store_true')
    modes.add_argument('--recreate-only', action='store_true')
    modes.add_argument('--column-only', action='store_true')
    modes.add_argument('--package-only', action='store_true')
    modes.add_argument('--routine-only', action='store_true')
    modes.add_argument('--trigger-only', action='store_true')
    modes.add_argument('--constraint-only', action='store_true')
    modes.add_argument('--inspection-only', action='store_true')
    modes.add_argument('--lifecycle-only', action='store_true')
    modes.add_argument('--privileges-only', action='store_true')
    modes.add_argument('--import-order-only', action='store_true')
    modes.add_argument('--external-functions-only', action='store_true')
    modes.add_argument('--grant-plan-only', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.output.resolve(), args.image, args.table_only, args.recreate_only, args.column_only, args.package_only, args.routine_only, args.trigger_only, args.constraint_only, args.inspection_only, args.lifecycle_only, args.privileges_only, args.import_order_only, args.external_functions_only, args.grant_plan_only), indent=2))
