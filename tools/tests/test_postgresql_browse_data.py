"""Browse data for PostgreSQL (owner direction 2026-11-06).

View/Edit Data became Browse data: the Query Tool opens holding SELECT of
every column of the relation, read from the catalog by OID and quoted only
where PostgreSQL needs it (pgAdmin's Driver.qtIdent). Nothing is run.
"""
import inspect
import pathlib
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import jinja2
import pytest
from flask import Flask

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT / 'web') not in sys.path:
    sys.path.insert(0, str(ROOT / 'web'))

import pgadmin.tools.sqleditor as editor  # noqa: E402
from pgadmin.utils.driver.psycopg3 import Driver  # noqa: E402

TEMPLATE = (ROOT / 'web/pgadmin/tools/sqleditor/templates/sqleditor/sql/'
            'default/browse_data_columns.sql')


@pytest.fixture
def route(monkeypatch):
    app = Flask(__name__)
    conn = Mock(connected=Mock(return_value=True))
    managers = {}

    def connection_manager(sid):
        managers.setdefault(sid, Mock(connection=Mock(return_value=conn)))
        return managers[sid]

    monkeypatch.setattr(editor, 'get_driver', lambda _name: SimpleNamespace(
        connection_manager=connection_manager, qtIdent=Driver.qtIdent))
    # The message is translated in the app; the bare Flask app has no Babel.
    monkeypatch.setattr(editor, 'gettext', lambda text: text)
    rendered = []
    monkeypatch.setattr(editor, 'render_template', lambda name, **kwargs:
                        rendered.append((name, kwargs)) or 'catalog query')

    def call(sid=3, did=5, obj_id=16384):
        with app.test_request_context('/'):
            return inspect.unwrap(editor.browse_data_sql)(sid, did, obj_id)
    return call, conn, managers, rendered


def rows(*columns, schema='public', relation='assets'):
    return {'rows': [{'nspname': schema, 'relname': relation, 'attname': name}
                     for name in columns]}


def test_lists_every_column_quoting_only_names_that_need_it(route):
    call, conn, managers, rendered = route
    conn.execute_dict.return_value = (True, rows(
        'asset_id', 'Tag', 'serial number', 'select', 'amount',
        schema='Sales', relation='asset list'))
    response = call()
    assert response.status_code == 200
    assert response.get_json() == (
        'SELECT asset_id, "Tag", "serial number", "select", amount\n'
        'FROM "Sales"."asset list"')
    managers[3].connection.assert_called_once_with(did=5)
    assert rendered == [('sqleditor/sql/default/browse_data_columns.sql',
                         {'obj_id': 16384})]
    conn.execute_dict.assert_called_once_with('catalog query')


def test_relation_without_columns_selects_star(route):
    call, conn, _managers, _rendered = route
    conn.execute_dict.return_value = (True, rows(None))
    assert call().get_json() == 'SELECT *\nFROM public.assets'


def test_missing_relation_is_gone(route):
    call, conn, _managers, _rendered = route
    conn.execute_dict.return_value = (True, {'rows': []})
    response = call()
    assert response.status_code == 410
    assert response.get_json()['errormsg'] == \
        'The specified object could not be found.'


def test_catalog_error_is_reported(route):
    call, conn, _managers, _rendered = route
    conn.execute_dict.return_value = (False, 'permission denied')
    response = call()
    assert response.status_code == 500
    assert response.get_json()['errormsg'] == 'permission denied'


def test_closed_connection_runs_nothing(route):
    call, conn, _managers, _rendered = route
    conn.connected.return_value = False
    assert call().status_code == 500
    conn.execute_dict.assert_not_called()


def test_route_requires_the_query_tool_permission():
    source = inspect.getsource(editor.browse_data_sql)
    decorators = source.split('def browse_data_sql', 1)[0]
    assert '@permissions_required(AllPermissionTypes.tools_query_tool)' in \
        decorators
    assert '@pga_login_required' in decorators
    assert 'sqleditor.browse_data_sql' in \
        editor.SqlEditorModule.get_exposed_url_endpoints(None)


def test_template_reads_user_columns_in_table_order():
    sql = jinja2.Template(TEMPLATE.read_text()).render(obj_id=16384)
    normalized = ' '.join(sql.split())
    assert 'WHERE r.oid = 16384::oid' in normalized
    assert 'a.attnum > 0 AND NOT a.attisdropped' in normalized
    assert normalized.endswith('ORDER BY a.attnum;')
    assert jinja2.Template(TEMPLATE.read_text()).render(obj_id=0).strip() == ''
