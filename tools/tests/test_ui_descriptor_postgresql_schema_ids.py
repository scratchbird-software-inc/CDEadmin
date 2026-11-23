"""PostgreSQL descriptors are legacy_preserved: every field id must be a
BaseUISchema id in the pgAdmin ``*.ui.js`` sources (the shell will route
these forms to the existing SQL templates in phase 5). This gate catches
drift when a ui.js schema renames or drops a field.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORMS = ROOT / 'web/pgadmin/cdeadmin/ui_descriptors/postgresql/forms'
SOURCES = (
    ROOT / 'web/pgadmin/browser/server_groups/servers',
    ROOT / 'web/pgadmin/browser/static/js',
    ROOT / 'web/pgadmin/static/js',
)
# Descriptor-only ids the shell owns (never sent to pgAdmin).
SHELL_IDS = {'variant'}
# Ids the provider-native route compiles that the inherited dialogs never
# had (M7 and the 2026-11-11 form close-outs): revocation grids, storage
# parameter resets and foreign option grids. They are sent to the provider,
# never to a pgAdmin template, so they are not ui.js ids.
PROVIDER_TREE_IDS = {
    # Native pg_attribute.attgenerated storage kind (s/v), absent from the inherited editor.
    'generated_kind',
    'revoke', 'reset_fillfactor', 'reset_toast_tuple_target',
    'reset_parallel_workers', 'add_options', 'set_options', 'drop_options',
    'revoke_membership', 'revoke_members', 'reset_variables', 'admin_only',
    'reset_parameters', 'no_minimum', 'no_maximum', 'owned_by_none',
    # PG18 temporal/enforcement constraint fields and engine_object provider-native compiler fields:
    'without_overlaps_column', 'local_period_column', 'referenced_period_column',
    'not_enforced', 'conenforced',
    'action', 'add_mappings', 'add_schemas', 'add_tables', 'alter_mappings',
    'argument_types', 'castmethod', 'data_type', 'default', 'drop_mappings',
    'drop_schemas', 'drop_tables', 'family', 'from_sql_args', 'from_sql_function',
    'function', 'functions', 'handler', 'index_method', 'kind', 'language',
    'members', 'method_type', 'no_handler', 'no_validator', 'number',
    'operand_types', 'operators', 'option', 'refresh_version', 'replace',
    'server', 'sort_family', 'source_encoding', 'storage_type', 'strategy',
    'support', 'target_encoding', 'to_sql_args', 'to_sql_function', 'type_name',
    # Remaining 15 PostgreSQL engine_object provider-native compiler fields:
    'contype', 'coordinator_reference', 'decision', 'default_privileges',
    'default_revoke', 'elements', 'enforcement', 'expected_database',
    'expected_owner', 'expected_xid', 'fdwname', 'fk_columns',
    'generated_action', 'grant_option_only', 'grantees', 'kinds',
    'large_object_data_base64', 'left_type', 'not_null_column', 'not_valid',
    'object_type', 'owner_kind', 'owner_mode', 'owners', 'parameter',
    'privilege', 'remote_schema', 'remote_table', 'reset_options',
    'right_type', 'roles', 'schemas', 'scope', 'table', 'table_schema',
    'target', 'validate', 'with_grant',
}


def schema_ids():
    ids = set()
    for root in SOURCES:
        for path in root.rglob('*.ui.js'):
            ids |= set(re.findall(r"\bid:\s*['\"]([A-Za-z0-9_]+)['\"]", path.read_text(encoding='utf-8')))
    return ids


def test_every_postgresql_field_id_is_a_ui_schema_id():
    ids = schema_ids()
    assert len(ids) > 300, 'pgAdmin ui.js schema ids were not found'
    unknown = []
    for path in sorted(FORMS.glob('*.form.json')):
        form = json.loads(path.read_text(encoding='utf-8'))
        for field in form['fields']:
            if field['field_id'] not in ids and field['field_id'] not in SHELL_IDS \
                    and field['field_id'] not in PROVIDER_TREE_IDS:
                unknown.append(f"{form['family']}.{field['field_id']}")
            if field['field_id'] in SHELL_IDS:
                assert field.get('ui_only') is True, f"{form['family']}.{field['field_id']} must be ui_only"
            for column in field.get('columns', []):
                if column['field_id'] not in ids and column['field_id'] not in PROVIDER_TREE_IDS:
                    unknown.append(f"{form['family']}.{field['field_id']}.{column['field_id']}")
    assert unknown == [], unknown
