"""The control-plane grid control: typed rows instead of a raw JSON field.

CockroachDB and YugabyteDB partition and split operations took raw JSON; their
descriptors already offer grids. The grid keeps the providers' row and
scalar-list forms, and parses JSON text from older text forms.
"""
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

import pytest  # noqa: E402

from pgadmin.cdeadmin.visual_admin.control_plane import (  # noqa: E402
    ControlPlaneCatalog, ControlPlaneCatalogError, ControlPlaneOperation, field,
)

ONE = [{'field_id': 'value', 'label': 'Value', 'control': 'text'}]
ROWS = [{'field_id': 'partition', 'label': 'Partition', 'control': 'text'},
        {'field_id': 'value', 'label': 'Value', 'control': 'text'}]


def catalog(columns):
    operation = ControlPlaneOperation('table', 'split_at', 'Split', 'admin', 'topology_admin', (
        field('values', 'Values', 'grid', True, columns=columns),), impact_scope='resource')
    return ControlPlaneCatalog('cockroachdb', (operation,))


def errors(columns, value):
    request = {'resource_kind': 'table', 'operation_id': 'split_at', 'target_resource': {},
               'draft': {'values': value}}
    return [item['code'] for item in catalog(columns).validate(request)['errors']]


def test_grid_rows_and_one_column_values_are_admitted():
    assert errors(ROWS, [{'partition': 'p1', 'value': '1'}, {'partition': 'p2'}]) == []
    assert errors(ONE, [{'value': '10'}, '20']) == []
    assert errors(ONE, '[{"value": "10"}]') == []  # JSON text from an older text form


def test_grid_refuses_other_shapes():
    assert errors(ROWS, {'partition': 'p1'}) == ['invalid_type']
    assert errors(ROWS, [{'partition': 'p1', 'invented': 1}]) == ['invalid_row']
    assert errors(ROWS, ['bare']) == ['invalid_row']
    assert errors(ONE, [['nested']]) == ['invalid_row']
    assert errors(ONE, 'not json') == ['invalid_type']
    assert errors(ONE, []) == ['required']


def test_grid_declarations_need_columns_and_requests_are_normalized():
    with pytest.raises(ControlPlaneCatalogError):
        catalog([])
    request = {'resource_kind': 'table', 'operation_id': 'split_at', 'draft': {'values': '["10"]'}}
    assert catalog(ONE).normalized(request)['draft']['values'] == ['10']
    assert request['draft']['values'] == '["10"]'
