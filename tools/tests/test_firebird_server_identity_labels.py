"""Same-host endpoints remain visibly distinct by port and registration."""
import ast
from pathlib import Path


def labels(nodes):
    path = Path(__file__).resolve().parents[2] / 'web/pgadmin/browser/server_groups/engine_types/__init__.py'
    node = next(node for node in ast.parse(path.read_text()).body if isinstance(node, ast.FunctionDef) and node.name == 'disambiguate_server_interfaces')
    scope = {'_INTERFACE_LABELS': {'ysql': 'YSQL', 'ycql': 'YCQL'}}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), scope)
    return scope[node.name](nodes, [{'profile_id': name, 'interface_id': name} for name in ('firebird', 'ysql', 'ycql')])


def test_different_firebird_ports_show_exact_port():
    rows = labels([{'label': 'localhost', 'port': port, 'cde_profile_id': 'firebird', '_id': str(i)} for i, port in enumerate((3050, 13050))])
    assert [item['label'] for item in rows] == ['localhost:3050 (firebird)', 'localhost:13050 (firebird)']


def test_duplicate_address_registration_ids_remain_distinct():
    rows = labels([{'label': 'localhost', 'port': 3050, 'cde_profile_id': 'firebird', '_id': str(i)} for i in (7, 27)])
    assert [item['label'] for item in rows] == ['localhost:3050 [registration 7] (firebird)', 'localhost:3050 [registration 27] (firebird)']


def test_existing_distinct_interface_labels_remain_readable():
    rows = labels([{'label': 'localhost', 'port': 5433, 'cde_profile_id': name} for name in ('ysql', 'ycql')])
    assert [item['label'] for item in rows] == ['localhost (YSQL)', 'localhost (YCQL)']
