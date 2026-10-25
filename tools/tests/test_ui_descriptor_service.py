"""UI descriptor service: family resolution, version gates and the HTTP bundle."""
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.ui_descriptors import (  # noqa: E402
    UIDescriptorError, UIDescriptorService, version_gate_state,
)

BETA_ENGINES = ('postgresql', 'mysql', 'mariadb', 'firebird', 'duckdb', 'sqlite')
FAMILIES = ('table', 'view', 'index', 'routine', 'trigger', 'sequence', 'type',
            'role', 'database', 'server')


@pytest.fixture(scope='module')
def service():
    return UIDescriptorService()


def test_every_beta_engine_has_a_bundle(service):
    assert set(BETA_ENGINES) <= set(service.engine_ids())
    for engine in BETA_ENGINES:
        bundle = service.engine(engine)
        assert bundle['schema'] == 'cdeadmin.ui-bundle.v1'
        assert bundle['capabilities']['engine'] == engine
        assert bundle['kinds'], engine


def test_family_skeletons_cover_the_ten_families(service):
    assert set(FAMILIES) <= set(service.families())
    for family in FAMILIES:
        skeleton = service.families()[family]
        tabs = [tab['tab'] for tab in skeleton['tabs']]
        assert tabs[0] in ('General', 'Connection'), family
        assert len(tabs) == len(set(tabs)), family


@pytest.mark.parametrize('engine', BETA_ENGINES)
def test_resolved_tabs_follow_the_family_order(service, engine):
    bundle = service.engine(engine)
    for family, form in bundle['forms'].items():
        order = form['family_tabs']
        tabs = [tab['tab'] for tab in form['tabs']]
        positions = [order.index(tab) for tab in tabs]
        assert positions == sorted(positions), (engine, family, tabs)
        # every rendered tab either carries fields or is a shell-provided tab
        for tab in form['tabs']:
            assert tab['fields'] or tab['primitive'] in (
                'sql_preview', 'data_grid', 'readonly_grid', 'readonly_groups'), (engine, family, tab['tab'])
        if form['status'] == 'complete':
            assert not form['missing_required_tabs'], (engine, family)


def test_engine_tab_uses_the_engine_title(service):
    form = service.engine('firebird')['forms']['table']
    engine_tab = next(tab for tab in form['tabs'] if tab['tab'] == 'Engine')
    assert engine_tab['title'] == 'Firebird'


def test_no_raw_json_control_reaches_the_shell(service):
    for engine in BETA_ENGINES:
        bundle = service.engine(engine)
        for family, form in bundle['forms'].items():
            for tab in form['tabs']:
                for field in tab['fields']:
                    assert field['control'] != 'json', (engine, family, field['field_id'])
        for op in bundle['operations']:
            for field in op['fields']:
                assert field['control'] != 'json', (engine, op['operation_id'], field['field_id'])


def test_version_gate_state():
    assert version_gate_state(None, '8.0.0') == (True, None)
    assert version_gate_state({'minimum': '8.0.16'}, '8.0.14')[0] is False
    assert version_gate_state({'minimum': '8.0.16'}, '8.0.16')[0] is True
    assert version_gate_state({'maximum_exclusive': '9.0'}, '9.0.0')[0] is False
    assert version_gate_state({'minimum': '8.0.16'}, None) == (True, None)
    assert 'Requires version 8.0.16' in version_gate_state({'minimum': '8.0.16'}, '5.7')[1]


def test_resolve_for_version_marks_but_keeps_gated_fields(service):
    bundle = service.resolve_for_version('mysql', '8.0.14')
    fields = [field for tab in bundle['forms']['table']['tabs'] for field in tab['fields']]
    gated = [field for field in fields if field.get('version')]
    assert gated, 'expected at least one version-gated MySQL table field'
    for field in gated:
        assert 'available' in field
        if not field['available']:
            assert field['unavailable_reason']
    ungated = [field for field in fields if not field.get('version')]
    assert all(field['available'] for field in ungated)


def test_kind_index_points_at_forms_and_operations(service):
    kinds = service.engine('firebird')['kinds']
    assert kinds['table']['family'] == 'table'
    assert 'create' in kinds['table']['tier1']
    database = kinds['database']
    assert any(op['operation_id'] == 'backup_logical' for op in database['operations'])


def test_bundle_carries_option_sources(service):
    bundle = service.engine('mysql')
    assert 'column_types' in bundle['options']['dialect']
    assert bundle['options']['catalog']['tablespaces']['resource_kind'] == 'tablespace'


def test_unknown_engine_raises(service):
    with pytest.raises(UIDescriptorError):
        service.engine('no-such-engine')


def test_http_bundle_endpoint(service):
    flask = pytest.importorskip('flask')
    app = flask.Flask(__name__)
    app.config['TESTING'] = True
    login = ModuleType('pgadmin.user_login_check')
    login.pga_login_required = lambda view: view
    sys.modules['pgadmin.user_login_check'] = login
    try:
        from pgadmin.cdeadmin.ui_descriptors import init_app
        init_app(app)
        client = app.test_client()
        listing = client.get('/cdeadmin/api/ui/descriptors').get_json()
        assert listing['success'] == 1 and 'firebird' in listing['data']['engines']
        bundle = client.get('/cdeadmin/api/ui/descriptors/sqlite?version=3.40.0').get_json()
        assert bundle['success'] == 1 and bundle['data']['observed_version'] == '3.40.0'
        assert client.get('/cdeadmin/api/ui/descriptors/Nope!').status_code == 400
        assert client.get('/cdeadmin/api/ui/descriptors/zzz').status_code == 404
    finally:
        sys.modules.pop('pgadmin.user_login_check', None)
