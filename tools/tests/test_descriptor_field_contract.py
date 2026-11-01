"""Visual administration admits what an engine's own UI descriptors send.

Live, 2026-10-31: 13 of 15 YugabyteDB form round trips failed through the
UI's validation path (unknown fields such as row-policy roles, or a required
name in an alter that sends only what changed), although the provider's
direct administration path accepted the same drafts.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'web'), str(ROOT / 'tools')]

from pgadmin.cdeadmin.ui_descriptors.field_contract import (  # noqa: E402
    DescriptorFieldContract, descriptor_field_contract)
from ui_descriptor_roundtrip import backend_draft, resolved_form  # noqa: E402

LEGACY = [{'field_id': 'legacy_only', 'label': 'Legacy only',
           'control': 'text', 'required': True}]


def contract(engine, kind, operation, legacy=LEGACY):
    return descriptor_field_contract(engine, {
        'resource_kind': kind, 'operation_id': operation,
        'legacy_fields': legacy, 'draft': {}})


def ids(result):
    return {field['field_id'] for field in result['fields']}


def test_descriptor_fields_are_admitted_beside_the_catalog_fields():
    result = contract('yugabytedb', 'row-policy', 'create')
    assert {'name', 'table', 'roles', 'using', 'with_check',
            'comment', 'legacy_only'} <= ids(result)
    assert result['authority'] == 'ui_descriptors/yugabytedb'
    required = {f['field_id'] for f in result['fields'] if f['required']}
    assert {'name', 'table'} <= required
    # Replaced catalog fields stay admitted but are no longer required.
    assert 'legacy_only' not in required


def test_an_alter_requires_nothing_it_did_not_change():
    result = contract('yugabytedb', 'index', 'alter')
    assert not [f for f in result['fields'] if f['required']]
    # A field fixed at creation is not part of an alter.
    form = resolved_form('yugabytedb', 'index')
    fixed = {f.get('backend_field_id') or f['field_id']
             for tab in form['tabs'] for f in tab['fields']
             if f.get('editable_after_create') is False}
    assert fixed and not (fixed - {'legacy_only'}) & ids(result) - {
        f['field_id'] for f in LEGACY}


def test_mapped_targets_admit_their_backend_roots():
    # constraints[kind=...] grids share one list; dotted ids share an object.
    for engine, root, control in (('dolt', 'constraints', 'grid'),
                                  ('xtdb', 'options', 'keyvalue')):
        result = contract(engine, 'table', 'create')
        by_id = {field['field_id']: field for field in result['fields']}
        assert by_id[root]['control'] == control
        assert not any('[' in name or '.' in name for name in by_id)
    # A catalog field that already describes the root keeps its schema.
    legacy = [{'field_id': 'constraints', 'label': 'Constraints',
               'control': 'json', 'required': False, 'json_type': 'array'}]
    result = contract('dolt', 'table', 'create', legacy=legacy)
    assert next(f for f in result['fields']
                if f['field_id'] == 'constraints') == legacy[0]


def test_runtime_choices_are_left_to_the_native_compiler():
    result = contract('vitess', 'vindex', 'create')
    vindex_type = next(f for f in result['fields']
                       if f['field_id'] == 'vindex_type')
    assert vindex_type['control'] == 'text'
    assert 'option_values_path' not in vindex_type


def test_operation_dialogs_admit_a_typed_confirmation():
    engine = json.loads((ROOT / 'web/pgadmin/cdeadmin/ui_descriptors/'
                         'yugabytedb/operations.json').read_text())
    typed = next(item for item in engine['operations']
                 if item.get('confirmation') == 'typed_name')
    result = contract('yugabytedb', typed['resource_kind'],
                      typed['operation_id'], legacy=[])
    assert 'confirmation' in ids(result)


def test_operations_the_descriptors_do_not_cover_keep_the_catalog():
    assert contract('yugabytedb', 'no-such-kind', 'create') is None
    assert DescriptorFieldContract().admin_operation_field_contract(
        {'resource_kind': 'table', 'operation_id': 'create'}) is None


def yugabytedb_provider():
    from pgadmin.cdeadmin.providers.yugabytedb.provider import (
        PROFILE, create_provider)
    return create_provider(SimpleNamespace(
        endpoint_id=str(uuid.uuid4()), session_namespace='fc',
        pool_namespace='fc', cache_namespace='fc',
        provider_id=PROFILE.provider_id, profile_id=PROFILE.profile_id,
        profile_version=PROFILE.exact_version, provider_version='0.2.0',
        mode='legacy_native', runtime_verification_state='unverified',
        verified_runtime_family=None, declared_runtime_family=None,
        target_adapter_id=None, effective_permissions=frozenset()),
        SimpleNamespace(acquire_secret=None, require=lambda *_a: None))


def test_the_ui_draft_passes_visual_administration():
    provider = yugabytedb_provider()
    form = resolved_form('yugabytedb', 'engine_object:row-policy')
    draft = backend_draft(form, {
        'name': 'p', 'table': 'public.t', 'policy_type': 'PERMISSIVE',
        'command': 'ALL', 'roles': [{'role': 'reader'}], 'using': 'v = 1'})
    assert draft['roles'] == ['reader']
    result = provider.validate_visual_admin({
        'resource_kind': 'row-policy', 'operation_id': 'create',
        'target_resource': None, 'draft': draft})
    assert result['errors'] == [], result['errors']


def test_an_alter_admits_the_columns_grid_diff():
    names = ids(contract('yugabytedb', 'table', 'alter', legacy=[]))
    assert {'add_columns', 'drop_columns', 'rename_columns',
            'alter_columns'} <= names


def test_variant_fields_neither_require_nor_fill_in():
    # One form serves type and domain; a domain's base type is required
    # only for that variant, and no hidden default reaches the compiler.
    result = contract('yugabytedb', 'type', 'create', legacy=[])
    by_id = {field['field_id']: field for field in result['fields']}
    assert by_id['base_type']['required'] is False
    assert not [field for field in result['fields'] if 'default' in field]


def test_a_create_sends_the_editor_defaults():
    # The editor opens a create on its defaults (initialDraft), so a routine
    # whose language the user never touched is still sent with one.
    form = resolved_form('yugabytedb', 'routine')
    draft = backend_draft(form, {
        'variant': 'function', 'name': 'f', 'parent': 'public',
        'returns': 'integer', 'body': 'SELECT 1'})
    assert draft['language']
    result = yugabytedb_provider().validate_visual_admin({
        'resource_kind': 'function', 'operation_id': 'create',
        'target_resource': None, 'draft': draft})
    assert result['errors'] == [], result['errors']


def test_an_edit_reaches_the_compiler_with_the_target_record():
    # The UI's target is a provider resource, whose native record sits under
    # extensions; the YSQL compiler reads it to know the type is an enum.
    native = {'type_kind': 'ENUM', 'parent': 'public',
              'enum_values': ['one', 'two'], 'comment': None}
    target = {'resource_id': 'type:public.t', 'resource_kind': 'type',
              'display_name': 't', 'display_path': ['public', 't'],
              'extensions': {'yugabytedb': {'provider_owned': True,
                                            'native': native}}}
    request = {'resource_kind': 'type', 'operation_id': 'alter',
               'target_resource': target,
               'draft': {'enum_values': ['one', 'two', 'three']}}
    provider = yugabytedb_provider()
    assert provider.validate_visual_admin(request)['errors'] == []
    # A target without the record is still refused, not guessed at.
    del target['extensions']
    assert 'only an enum has values' in str(
        provider.validate_visual_admin(request)['errors'])


def test_added_columns_admit_the_editor_column_fields():
    # Live, CockroachDB 2026-10-31: the catalog's add_columns rows refused
    # the editor's column fields ("Add columns item 1 has unsupported
    # fields"). The rows stay checked field by field, now over both sets.
    legacy = [{'field_id': 'add_columns', 'label': 'Add columns',
               'control': 'json', 'required': False, 'json_type': 'array',
               'array_editor': {'item_kind': 'object', 'fields': [
                   {'field_id': 'name', 'label': 'Name', 'control': 'text',
                    'required': True}]}}]
    result = contract('cockroachdb', 'table', 'alter', legacy=legacy)
    add = next(f for f in result['fields'] if f['field_id'] == 'add_columns')
    children = {child['field_id']: child
                for child in add['array_editor']['fields']}
    assert children['name']['required'] is True
    form = resolved_form('cockroachdb', 'table')
    grid = next(f for tab in form['tabs'] for f in tab['fields']
                if f['field_id'] == 'columns')
    assert {column['field_id'] for column in grid['columns']} <= set(children)


def test_a_wrapped_choice_is_admitted_as_a_list():
    # A MySQL-dialect trigger fires on one event, which the editor sends as
    # a one-item list (live, Dolt 2026-10-31: "Events must be text").
    result = contract('dolt', 'trigger', 'create', legacy=[])
    events = next(f for f in result['fields'] if f['field_id'] == 'events')
    assert (events['control'], events['json_type'],
            events['array_editor']) == ('json', 'array',
                                        {'item_kind': 'string'})
