"""security.json: principals and grants are declared, referenced and resolved (Decision 21).

The Security Manager tool carries no engine branches; this file proves the
declarations it will read are well formed, that every reference resolves in the
engine's own folder, and that the validator refuses a broken declaration.
"""
import copy
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
sys.path.insert(0, str(ROOT / 'tools'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.ui_descriptors import UIDescriptorService  # noqa: E402
import validate_ui_descriptors as validator  # noqa: E402

DESCRIPTORS = ROOT / 'web/pgadmin/cdeadmin/ui_descriptors'
FIRST_SLICE = ('firebird', 'mysql', 'postgresql')
NO_PRINCIPALS = ('sqlite', 'duckdb')


def check(engine_dir):
    errors = []
    caps = json.loads((engine_dir / 'capabilities.json').read_text(encoding='utf-8'))
    schemas = validator.SchemaSet(DESCRIPTORS / 'schema')
    validator.check_security_descriptor(engine_dir.name, engine_dir, caps, schemas, errors)
    return errors


@pytest.fixture
def engine_copy(tmp_path):
    def make(engine, mutate):
        target = tmp_path / engine
        shutil.copytree(DESCRIPTORS / engine, target)
        document = json.loads((target / 'security.json').read_text(encoding='utf-8'))
        changed = copy.deepcopy(document)
        document = mutate(changed) or changed
        (target / 'security.json').write_text(json.dumps(document), encoding='utf-8')
        return target
    return make


@pytest.mark.parametrize('engine', FIRST_SLICE + NO_PRINCIPALS)
def test_shipped_descriptors_validate_and_resolve(engine):
    assert check(DESCRIPTORS / engine) == []


@pytest.mark.parametrize('engine', FIRST_SLICE + NO_PRINCIPALS)
def test_the_resolved_bundle_carries_the_declaration(engine):
    bundle = UIDescriptorService().engine(engine)
    assert bundle['security']['engine'] == engine
    assert isinstance(bundle['security']['principals'], list)


def test_engines_without_a_declaration_resolve_to_an_empty_security_block():
    service = UIDescriptorService()
    declared = {p.parent.name for p in DESCRIPTORS.glob('*/security.json')}
    undeclared = [e for e in service.engine_ids() if e not in declared]
    assert undeclared, 'every engine already declares security.json'
    assert service.engine(undeclared[0])['security'] == {}


@pytest.mark.parametrize('engine', NO_PRINCIPALS)
def test_embedded_engines_declare_no_principals_with_a_reason(engine):
    document = json.loads((DESCRIPTORS / engine / 'security.json').read_text(encoding='utf-8'))
    assert document['principals'] == []
    assert document['reason']
    assert 'grants' not in document and 'membership' not in document


def test_the_same_concept_is_named_per_engine_without_a_shared_lowest_denominator():
    labels = {}
    for engine in FIRST_SLICE:
        doc = json.loads((DESCRIPTORS / engine / 'security.json').read_text(encoding='utf-8'))
        labels[engine] = {p['kind']: (p['label'], p['scope']) for p in doc['principals']}
    # PostgreSQL has one principal object; it never offers a separate user.
    assert labels['postgresql'] == {'role': ('Role', 'server')}
    # Firebird users are server-wide while its roles live in each database.
    assert labels['firebird'] == {'user': ('User', 'server'), 'role': ('Role', 'database')}
    assert labels['mysql']['user'] == ('User', 'server')


def test_features_are_declared_only_where_the_engine_supports_them():
    docs = {e: json.loads((DESCRIPTORS / e / 'security.json').read_text(encoding='utf-8'))
            for e in FIRST_SLICE}
    assert docs['firebird']['grants']['granted_by'] is True
    assert 'granted_by' not in docs['mysql']['grants']
    assert 'granted_by' not in docs['postgresql']['grants']
    assert docs['postgresql']['grants']['default_privileges'] == 'default-privileges'
    assert 'default_privileges' not in docs['firebird']['grants']
    # PostgreSQL system attributes are role-form fields, not grants.
    assert 'system_privileges' not in docs['postgresql']['grants']
    assert docs['firebird']['grants']['column_privileges']['table'] == ['UPDATE', 'REFERENCES']
    assert 'SELECT' in docs['postgresql']['grants']['column_privileges']['table']
    assert docs['postgresql']['membership']['inherit_option'] is True
    assert 'inherit_option' not in docs['firebird']['membership']
    assert docs['mysql']['principals'][0]['identity'] == ['name', 'host']


def test_an_unknown_principal_kind_is_refused(engine_copy):
    def mutate(doc):
        doc['principals'][0]['kind'] = 'warlock'
    errors = check(engine_copy('firebird', mutate))
    assert any("'warlock' is not in capabilities.json" in e for e in errors), errors


def test_a_principal_outside_the_role_family_is_refused(engine_copy):
    def mutate(doc):
        doc['principals'][0]['kind'] = 'table'
    errors = check(engine_copy('firebird', mutate))
    assert any("not 'role'" in e for e in errors), errors


def test_an_identity_field_the_form_lacks_is_refused(engine_copy):
    def mutate(doc):
        doc['principals'][0]['identity'] = ['name', 'nonexistent']
    errors = check(engine_copy('firebird', mutate))
    assert any("identity field 'nonexistent'" in e for e in errors), errors


def test_a_variant_value_the_form_does_not_offer_is_refused(engine_copy):
    def mutate(doc):
        doc['principals'][0]['variant']['value'] = 'wizard'
    errors = check(engine_copy('mysql', mutate))
    assert any("variant value 'wizard'" in e for e in errors), errors


def test_an_option_source_options_json_does_not_define_is_refused(engine_copy):
    def mutate(doc):
        doc['grants']['object_privileges'] = 'no_such_list'
    errors = check(engine_copy('postgresql', mutate))
    assert any('dialect.no_such_list' in e for e in errors), errors


def test_a_column_privilege_the_engine_does_not_grant_is_refused(engine_copy):
    def mutate(doc):
        doc['grants']['column_privileges']['view'] = ['SELECT', 'REFERENCES']
    errors = check(engine_copy('mysql', mutate))
    assert any('view.REFERENCES is not a grantable privilege' in e for e in errors), errors


def test_a_grant_kind_without_grant_and_revoke_is_refused(engine_copy):
    def mutate(doc):
        doc['grants']['grant_kind'] = 'user'
    errors = check(engine_copy('firebird', mutate))
    assert any("grant kind 'user' declares no grant operation" in e for e in errors), errors
    assert any("grant kind 'user' declares no revoke operation" in e for e in errors), errors


def test_membership_must_name_a_declared_principal(engine_copy):
    def mutate(doc):
        doc['membership']['kind'] = 'group'
    errors = check(engine_copy('firebird', mutate))
    assert any("membership kind 'group'" in e for e in errors), errors


def test_an_empty_principal_list_needs_a_reason(engine_copy):
    def mutate(doc):
        doc.pop('reason')
    errors = check(engine_copy('sqlite', mutate))
    assert any('needs a reason' in e for e in errors), errors


def test_an_empty_principal_list_cannot_still_declare_grants(engine_copy):
    def mutate(doc):
        doc['grants'] = {'grant_kind': 'privilege'}
    errors = check(engine_copy('duckdb', mutate))
    assert any('engine has no principals' in e for e in errors), errors


def test_the_declaration_must_belong_to_its_folder(engine_copy):
    def mutate(doc):
        doc['engine'] = 'mysql'
    errors = check(engine_copy('firebird', mutate))
    assert any('does not match its folder' in e for e in errors), errors


def test_unknown_keys_are_refused_so_a_field_cannot_hide_in_the_descriptor(engine_copy):
    def mutate(doc):
        doc['principals'][0]['raw_json'] = {'anything': True}
    errors = check(engine_copy('firebird', mutate))
    assert errors, 'additionalProperties must reject undeclared keys'


def test_a_declared_principal_list_needs_a_status(engine_copy):
    def mutate(doc):
        doc.pop('status')
    errors = check(engine_copy('mysql', mutate))
    assert any('status (draft or complete) is required' in e for e in errors), errors


def test_status_only_takes_the_two_declared_values(engine_copy):
    def mutate(doc):
        doc['status'] = 'done'
    assert check(engine_copy('mysql', mutate))


def test_only_engines_with_live_verified_operations_are_complete():
    states = {e: json.loads((DESCRIPTORS / e / 'security.json').read_text(encoding='utf-8')).get('status')
              for e in FIRST_SLICE}
    # PostgreSQL has no privilege operation yet, and MySQL's operations have not
    # been round-tripped through the descriptor-driven manager.
    assert states == {'firebird': 'complete', 'mysql': 'draft', 'postgresql': 'draft'}


def test_grants_carry_their_own_status_separate_from_principals():
    for engine in FIRST_SLICE:
        doc = json.loads((DESCRIPTORS / engine / 'security.json').read_text(encoding='utf-8'))
        assert doc['grants']['status'] in ('draft', 'complete')
    fb = json.loads((DESCRIPTORS / 'firebird' / 'security.json').read_text(encoding='utf-8'))
    assert fb['grants']['status'] == 'complete'


def test_declared_grants_need_a_status(engine_copy):
    def mutate(doc):
        doc['grants'].pop('status')
    errors = check(engine_copy('mysql', mutate))
    assert any('grants.status' in e for e in errors), errors


def test_a_listing_may_not_name_its_object_two_ways(engine_copy):
    def both(doc):
        doc['grants']['listing']['object_field'] = 'x'
    assert any('both object_field and object_fields' in e for e in check(engine_copy('mysql', both)))


def test_a_listing_must_name_its_object(engine_copy):
    def neither(doc):
        doc['grants']['listing'].pop('object_fields')
    assert any('needs object_field or object_fields' in e for e in check(engine_copy('mysql', neither)))


def test_mysql_declares_a_composite_listing_without_privilege_codes():
    doc = json.loads((DESCRIPTORS / 'mysql' / 'security.json').read_text(encoding='utf-8'))
    listing = doc['grants']['listing']
    assert listing['object_fields'] == ['database', 'table_name']
    assert 'privilege_codes' not in listing
