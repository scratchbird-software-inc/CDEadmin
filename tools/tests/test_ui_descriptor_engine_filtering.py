"""Per-engine filtering of offered features (owner direction, 2026-10-29).

Surface every feature and filter per engine: option values and declared
operations carry version gates the resolver evaluates, and option values may
require a resource the connected endpoint must report.
"""
import json
import shutil
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
    UIDescriptorService,
)

DESCRIPTORS = ROOT / 'web/pgadmin/cdeadmin/ui_descriptors'


@pytest.fixture
def gated_service(tmp_path):
    """A copy of the descriptor tree with gates on every value kind."""
    root = tmp_path / 'ui_descriptors'
    shutil.copytree(DESCRIPTORS, root,
                    ignore=shutil.ignore_patterns('__pycache__'))
    sqlite = root / 'sqlite'
    table = json.loads((sqlite / 'forms/table.form.json').read_text())
    module = next(item for item in table['fields']
                  if item['field_id'] == 'module')
    module['options'][0]['version'] = {'minimum': '3.50.0'}
    (sqlite / 'forms/table.form.json').write_text(json.dumps(table))
    options = json.loads((sqlite / 'options.json').read_text())
    options['dialect']['modules'][0]['version'] = {
        'minimum': '3.50.0', 'reason': 'test gate'}
    (sqlite / 'options.json').write_text(json.dumps(options))
    capabilities = json.loads((sqlite / 'capabilities.json').read_text())
    capabilities['kinds'][0]['operations'][1]['version'] = {
        'maximum_exclusive': '3.40.0'}
    (sqlite / 'capabilities.json').write_text(json.dumps(capabilities))
    return UIDescriptorService(root)


def _module_options(bundle):
    for tab in bundle['forms']['table']['tabs']:
        for field in tab['fields']:
            if field['field_id'] == 'module':
                return field['options']
    raise AssertionError('module field missing')


def test_option_value_gates_are_evaluated(gated_service):
    old = gated_service.resolve_for_version('sqlite', '3.45.1')
    new = gated_service.resolve_for_version('sqlite', '3.53.0')
    assert _module_options(old)[0]['available'] is False
    assert 'unavailable_reason' in _module_options(old)[0]
    assert _module_options(new)[0]['available'] is True
    # Ungated values are left untouched.
    assert 'available' not in _module_options(old)[1]
    listed = old['options']['dialect']['modules'][0]
    assert listed['available'] is False
    assert listed['unavailable_reason'] == 'test gate'


def test_declared_kind_operation_gates_are_evaluated(gated_service):
    old = gated_service.resolve_for_version('sqlite', '3.35.0')
    new = gated_service.resolve_for_version('sqlite', '3.53.0')
    assert old['capabilities']['kinds'][0]['operations'][1]['available']
    gated = new['capabilities']['kinds'][0]['operations'][1]
    assert gated['available'] is False
    assert 'Removed in version 3.40.0' in gated['unavailable_reason']


def test_unresolved_bundle_is_not_marked(gated_service):
    bundle = gated_service.engine('sqlite')
    assert 'available' not in _module_options(bundle)[0]


def test_sqlite_modules_are_offered_only_where_registered():
    """Each module choice needs the endpoint to report that module."""
    table = json.loads((DESCRIPTORS / 'sqlite/forms/table.form.json')
                       .read_text())
    module = next(item for item in table['fields']
                  if item['field_id'] == 'module')
    for option in module['options']:
        assert option['requires_resource'] == {
            'resource_kind': 'extension', 'native_name': option['value']}
    options = json.loads((DESCRIPTORS / 'sqlite/options.json').read_text())
    for option in options['dialect']['modules']:
        assert option['requires_resource']['native_name'] == option['value']
