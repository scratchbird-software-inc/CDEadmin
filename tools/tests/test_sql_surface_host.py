"""Tests for SqlSurfaceHostService, Terminator Parser, Multi-Tag Snippets, Quick Queries,
Universal Object Script Generation, DDN Visual Builder Scene, and Multi-Format Exports (Surface 2).
"""

from __future__ import annotations

import base64
import copy
import io
import json
import sqlite3
import zipfile
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import pytest

from pgadmin.cdeadmin.context_menu import resource_context_actions
from pgadmin.cdeadmin.workspace.data_surface_host import (
    DataSurfaceHostService,
    SurfaceLayoutStore,
)
from pgadmin.cdeadmin.workspace.sql_surface_host import (
    QuickQueryStore,
    SqlSnippetsStore,
    SqlResultSetBuffer,
    SqlSurfaceHostService,
    bind_named_to_positional_if_needed,
    build_visual_query_ddn_scene,
    export_tabular_dataset,
    extract_query_parameters,
    extract_statement_at_cursor,
    generate_universal_object_sql,
    parse_sql_to_visual_model,
    resolve_visual_catalog_object,
    split_sql_statements,
)


from pgadmin.cdeadmin.workspace.surface_effective_sql import build_effective_select


class FakeSqlWorkspaceService:
    """Deterministic fake workspace service for Surface 2 SQL execution & live row editing."""

    def __init__(self):
        self.sessions_opened: list[dict] = []
        self.sessions_closed: list[str] = []
        self.executed: list[dict] = []
        self.tx_actions: list[tuple[str, str]] = []
        self.applied_plans: list[dict] = []
        self._occ_seq = 0
        self._occurrences: dict[str, dict] = {}
        self._plans: dict[str, dict] = {}
        self.fail_next_error: str | None = None

        self.table_columns = [
            {
                'name': 'ID',
                'native_type': 'INTEGER',
                'nullable': False,
                'key': True,
                'editable': False,
                'insertable': True,
            },
            {
                'name': 'TITLE',
                'native_type': 'VARCHAR(100)',
                'nullable': False,
                'key': False,
                'editable': True,
                'insertable': True,
            },
            {
                'name': 'AMOUNT',
                'native_type': 'NUMERIC(12,2)',
                'nullable': True,
                'key': False,
                'editable': True,
                'insertable': True,
            },
        ]
        self.live_rows = [
            {'identity_token': 'pk:1', 'values': {'ID': 1, 'TITLE': 'Alpha', 'AMOUNT': 120.5}},
            {'identity_token': 'pk:2', 'values': {'ID': 2, 'TITLE': 'Beta', 'AMOUNT': None}},
        ]

    def open_session(self, server, language_profile, database_target_id=None, session_purpose=None):
        sid = f'sql-sess-{len(self.sessions_opened) + 1}'
        self.sessions_opened.append({
            'session_id': sid,
            'language_profile': language_profile,
            'database_target_id': database_target_id,
        })
        return {'session_id': sid}

    def close_session(self, server, session_id, database_target_id=None):
        self.sessions_closed.append(session_id)
        return {'closed': True}

    def transaction(self, server, session_id, database_target_id=None):
        return {'session_id': session_id, 'in_transaction': True}

    def transaction_action(self, server, session_id, action, database_target_id=None):
        self.tx_actions.append((session_id, action))
        if action in ('autocommit_on', 'autocommit_off'):
            return {'session_id': session_id, 'provider_payload': {'autocommit': action == 'autocommit_on'}}
        return {'session_id': session_id, 'action': action}

    def execute(self, server, session_id, source, parameters=None,
                database_target_id=None, *, max_rows=None,
                client_sql_dialect=None, plan_mode=False):
        payload = {'session_id': session_id, 'source': source, 'parameters': parameters,
                   'database_target_id': database_target_id, 'max_rows': max_rows,
                   'client_sql_dialect': client_sql_dialect, 'plan_mode': plan_mode}
        self._occ_seq += 1
        occ_id = f'occ-{self._occ_seq}'
        self.executed.append(copy.deepcopy(payload))
        src = str(payload.get('source') or '').strip()

        if self.fail_next_error:
            err = self.fail_next_error
            self.fail_next_error = None
            self._occurrences[occ_id] = {
                'occurrence': {
                    'operation': {'terminal': True},
                    'result': {
                        'extensions': {
                            'firebird': {
                                'payload': {
                                    'error': {
                                        'message': err,
                                        'sqlstate': '42000',
                                    }
                                }
                            }
                        }
                    },
                },
                'rendered_result': None,
            }
            return {'occurrence_id': occ_id}

        if payload.get('plan_mode'):
            self._occurrences[occ_id] = {
                'occurrence': {
                    'operation': {'terminal': True},
                    'result': {
                        'extensions': {
                            'firebird': {
                                'payload': {'query_plan': 'PLAN (LEDGER INDEX (PK_LEDGER))'}
                            }
                        }
                    },
                },
                'rendered_result': None,
            }
            return {'occurrence_id': occ_id}

        if src.upper().startswith('SELECT'):
            self._occurrences[occ_id] = {
                'occurrence': {'operation': {'terminal': True}, 'result': {}},
                'rendered_result': {
                    'columns': [
                        {'name': 'ID', 'native_type': 'INTEGER', 'nullable': False, 'primary_key': True, 'key': 'col_0'},
                        {'name': 'LABEL', 'native_type': 'VARCHAR(64)', 'character_length': 64, 'nullable': True, 'key': 'col_1'},
                    ],
                    'page': {
                        'rows': [
                            {'ID': 10, 'LABEL': 'Row Ten'},
                            {'ID': 20, 'LABEL': 'Row Twenty'},
                        ]
                    },
                },
            }
        else:
            self._occurrences[occ_id] = {
                'occurrence': {'operation': {'terminal': True}, 'result': {'rowcount': 1}},
                'rendered_result': {'rowcount': 1},
            }
        return {'occurrence_id': occ_id}

    def poll(self, server, occ_id, buffer_rows=200, database_target_id=None):
        return self._occurrences[occ_id]

    def read_visual_admin_rows(self, server, request):
        return {
            'editable': True,
            'identity_policy': 'primary-key',
            'row_operations': ['insert', 'update', 'delete'],
            'columns': copy.deepcopy(self.table_columns),
            'rows': copy.deepcopy(self.live_rows),
            'complete': True,
        }

    def validate_visual_admin(self, server, request):
        return {'valid': True, 'errors': []}

    def plan_visual_admin(self, server, request):
        pid = f'plan-{len(self._plans) + 1}'
        op = request['operation_id']
        sql = f'-- {op.upper()} LEDGER'
        plan = {
            'plan_id': pid,
            'plan_digest': f'dg-{pid}',
            'state': 'ready',
            'execution_available': True,
            'statements': [sql],
        }
        self._plans[pid] = {**plan, 'request': copy.deepcopy(request)}
        return plan

    def apply_visual_admin(self, server, request):
        self.applied_plans.append(copy.deepcopy(request))
        return {'applied': True}


def test_terminator_and_firebird_set_term_splitting():
    fb_script = """
    CREATE SEQUENCE GEN_EMP_ID;
    SET TERM ^ ;
    CREATE OR ALTER TRIGGER BI_EMP FOR EMP
    ACTIVE BEFORE INSERT POSITION 0
    AS
    BEGIN
      IF (NEW.ID IS NULL) THEN
        NEW.ID = NEXT VALUE FOR GEN_EMP_ID;
    END^
    SET TERM ; ^
    INSERT INTO EMP (NAME) VALUES ('Ada; Lovelace');
    """
    segs = split_sql_statements(fb_script, ';', 'firebird')
    assert len(segs) == 3
    assert segs[0].sql.startswith('CREATE SEQUENCE GEN_EMP_ID')
    assert 'CREATE OR ALTER TRIGGER BI_EMP' in segs[1].sql
    assert 'NEXT VALUE FOR GEN_EMP_ID;' in segs[1].sql  # inner `;` preserved!
    assert "VALUES ('Ada; Lovelace')" in segs[2].sql

    # Cursor inside the middle trigger statement extracts only that trigger!
    trig_pos = fb_script.index('NEXT VALUE')
    cur_seg = extract_statement_at_cursor(fb_script, trig_pos, ';', 'firebird')
    assert cur_seg is not None
    assert 'CREATE OR ALTER TRIGGER BI_EMP' in cur_seg.sql

    # PostgreSQL dollar-quoted body with internal semicolons stays one statement
    pg_script = """
    CREATE OR REPLACE FUNCTION add_one(x int) RETURNS int AS $body$
    BEGIN
      RETURN x + 1;
    END;
    $body$ LANGUAGE plpgsql;
    SELECT add_one(41);
    """
    pg_segs = split_sql_statements(pg_script, ';', 'postgresql')
    assert len(pg_segs) == 2
    assert '$body$' in pg_segs[0].sql
    assert pg_segs[1].sql.strip() == 'SELECT add_one(41)'

    # SQLite trigger BEGIN...END; keeps inner semicolons intact
    sq_script = """
    CREATE TRIGGER tr_audit AFTER INSERT ON items
    BEGIN
      INSERT INTO log VALUES (NEW.id);
      UPDATE stats SET cnt = cnt + 1;
    END;
    SELECT * FROM items;
    """
    sq_segs = split_sql_statements(sq_script, ';', 'sqlite')
    assert len(sq_segs) == 2
    assert 'UPDATE stats SET cnt = cnt + 1;' in sq_segs[0].sql


def test_parameter_extraction_and_binding():
    sql = """
    -- ignore :comment_param
    SELECT id, payload::jsonb
    FROM orders
    WHERE customer_id = :cust_id
      AND status != ':not_a_param'
      AND region = :region
      AND retry_cust = :cust_id
    """
    params = extract_query_parameters(sql)
    assert [p['name'] for p in params] == ['cust_id', 'region']

    rewritten, ordered = bind_named_to_positional_if_needed(
        sql, {'cust_id': 42, 'region': 'NA'}, parameter_shape='array'
    )
    assert ordered == [42, 'NA', 42]
    assert ':not_a_param' in rewritten
    assert '::jsonb' in rewritten


def test_universal_object_sql_generation_and_context_menu():
    svc = FakeSqlWorkspaceService()
    server = SimpleNamespace(id=1, user_id=1)

    tbl = {
        'resource_id': 'table:ACCOUNTS',
        'resource_kind': 'table',
        'display_name': 'ACCOUNTS',
        'extensions': {
            'cdeadmin': {
                'catalog_metadata': {
                    'columns': [
                        {'name': 'ID', 'native_type': 'INTEGER', 'nullable': False, 'primary_key': True},
                        {'name': 'CODE', 'native_type': 'VARCHAR(32)', 'nullable': False},
                    ]
                }
            }
        },
    }

    for kind in (
        'select', 'insert', 'update', 'delete', 'upsert',
        'trigger_bi_id', 'trigger_stub', 'ddl_create', 'ddl_alter',
        'ddl_recreate', 'ddl_drop', 'grants',
    ):
        gen = generate_universal_object_sql(
            svc, server, engine_id='firebird', database_target_id='demo.fdb',
            target_resource=tbl, script_kind=kind,
        )
        assert gen['sql'].strip(), f'Empty script for table/{kind}'
        if kind.startswith('trigger'):
            assert 'SET TERM' in gen['sql']

    for rkind, skinds in [
        ('view', ['select', 'insert', 'ddl_create', 'ddl_alter', 'ddl_drop']),
        ('procedure', ['execute', 'ddl_create', 'ddl_alter', 'ddl_drop']),
        ('package', ['ddl_create', 'package_body', 'ddl_drop']),
        ('sequence', ['select', 'ddl_create', 'ddl_alter', 'ddl_drop']),
        ('domain', ['ddl_create', 'ddl_alter', 'ddl_drop']),
        ('trigger', ['ddl_create', 'ddl_alter', 'ddl_drop']),
        ('exception', ['ddl_create', 'ddl_alter', 'ddl_drop']),
    ]:
        obj = {'resource_id': f'{rkind}:OBJ1', 'resource_kind': rkind, 'display_name': 'OBJ1'}
        for sk in skinds:
            gen = generate_universal_object_sql(
                svc, server, engine_id='firebird', database_target_id='demo.fdb',
                target_resource=obj, script_kind=sk,
            )
            assert 'OBJ1' in gen['sql']

    # Verify Context Menu `Generate SQL` actions never violate `.create` invariant
    actions = resource_context_actions(
        {'engine_id': 'firebird', 'browse_data_kinds': ('table',)},
        tbl,
        {'objects': []},
        database_target_id='demo.fdb',
    )
    gen_actions = [a for a in actions if a.get('menu_group') == 'generate_sql']
    assert len(gen_actions) >= 10
    assert not any(a['command_id'].endswith('.create') for a in actions)


def test_multi_tag_snippets_and_quick_queries_stores(tmp_path):
    s_store = SqlSnippetsStore(tmp_path / 'snippets.db')
    res_fb = s_store.search_snippets(1, engine_id='firebird')
    assert len(res_fb['snippets']) >= 4
    assert any(t['tag'] == 'firebird' for t in res_fb['available_tags'])

    saved = s_store.save_snippet(
        1,
        {
            'title': 'Audit Trigger Snippet',
            'sql_text': 'CREATE TRIGGER tr_aud ...',
            'engine_id': 'firebird',
            'tags': ['Firebird', 'Trigger', 'Audit'],
            'shortcut': 'fbaud',
        },
    )
    assert saved['tags'] == ['audit', 'firebird', 'trigger']

    # AND mode requires both tags; OR mode matches either tag
    and_res = s_store.search_snippets(
        1, engine_id='firebird', selected_tags=['trigger', 'audit'], tag_mode='and'
    )
    assert len(and_res['snippets']) == 1
    or_res = s_store.search_snippets(
        1, engine_id='firebird', selected_tags=['audit', 'cte'], tag_mode='or'
    )
    assert len(or_res['snippets']) >= 2

    # Inline `#audit` search token
    hash_res = s_store.search_snippets(1, engine_id='firebird', search_text='#audit')
    assert len(hash_res['snippets']) == 1

    # Toggle favorite
    fav = s_store.toggle_favorite(1, saved['snippet_id'])
    assert fav['favorite'] is True

    # Quick Queries store persists SQL + terminator + parameters + Surface 1 display_layout
    q_store = QuickQueryStore(tmp_path / 'quick_queries.db')
    qq = q_store.save_quick_query(
        1,
        {
            'server_id': 7,
            'database_target_id': 'demo.fdb',
            'engine_id': 'firebird',
            'name': 'Overdue Invoices',
            'sql_text': 'SELECT * FROM INVOICES WHERE DUE < CURRENT_DATE',
            'terminator': ';',
            'parameters': [{'name': 'min_amt', 'type': 'numeric', 'value': '100'}],
            'display_layout': {'displayMode': 'hybrid', 'booleanFormat': 'true_false'},
        },
    )
    loaded = q_store.get_quick_query(qq['query_id'])
    assert loaded['display_layout']['displayMode'] == 'hybrid'
    assert q_store.get_quick_query(qq['query_id'], user_id=2) is None
    with pytest.raises(ValueError, match='unavailable'):
        q_store.save_quick_query(2, {**qq, 'name': 'Overwrite'})
    assert q_store.get_quick_query(qq['query_id'], user_id=1)['name'] == qq['name']
    assert len(q_store.list_quick_queries(1, server_id=7, database_target_id='demo.fdb')) == 1


def test_multi_format_exports_csv_tsv_xlsx_ods_pdf_and_surface1_sharing(tmp_path):
    cols = [
        {'name': 'ID', 'native_type': 'INTEGER'},
        {'name': 'CUSTOMER', 'native_type': 'VARCHAR(80)'},
        {'name': 'TOTAL', 'native_type': 'NUMERIC(12,2)'},
        {'name': 'NOTES', 'native_type': 'TEXT'},
    ]
    rows = [
        {'values': {'ID': 1, 'CUSTOMER': 'Acme, Inc.', 'TOTAL': 499.95, 'NOTES': None}},
        {'values': {'ID': 2, 'CUSTOMER': 'Globex', 'TOTAL': 1250.0, 'NOTES': 'Priority'}},
    ]

    # 1. CSV with custom semicolon delimiter & NULL token
    csv_out = export_tabular_dataset(
        cols, rows, fmt='csv',
        settings={'delimiter': ';', 'null_string': '<NULL>', 'encoding': 'utf-8-sig'},
        base_filename='orders',
    )
    raw_csv = base64.b64decode(csv_out['content_base64']).decode('utf-8-sig')
    assert 'ID;CUSTOMER;TOTAL;NOTES' in raw_csv
    assert '<NULL>' in raw_csv

    # 2. XLSX valid OpenXML archive with freeze pane & SQL_Metadata sheet
    xlsx_out = export_tabular_dataset(
        cols, rows, fmt='xlsx',
        settings={'sheet_name': 'Ledger', 'freeze_header': True, 'include_sql_sheet': True},
        sql_text='SELECT * FROM ORDERS;',
        base_filename='orders',
    )
    xlsx_bytes = base64.b64decode(xlsx_out['content_base64'])
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes), 'r') as zf:
        names = set(zf.namelist())
        assert '[Content_Types].xml' in names
        assert 'xl/worksheets/sheet1.xml' in names
        assert 'xl/worksheets/sheet2.xml' in names
        sheet_xml = zf.read('xl/worksheets/sheet1.xml').decode('utf-8')
        assert 'Acme, Inc.' in sheet_xml

    # 3. ODS valid OpenDocument spreadsheet archive
    ods_out = export_tabular_dataset(
        cols, rows, fmt='ods',
        settings={'sheet_name': 'LedgerODS', 'include_sql_sheet': True},
        sql_text='SELECT * FROM ORDERS;',
    )
    ods_bytes = base64.b64decode(ods_out['content_base64'])
    with zipfile.ZipFile(io.BytesIO(ods_bytes), 'r') as zf:
        assert zf.read('mimetype').decode('ascii') == 'application/vnd.oasis.opendocument.spreadsheet'
        assert b'Globex' in zf.read('content.xml')

    # 4. PDF valid multi-page PDF 1.4 binary with SQL appendix
    pdf_out = export_tabular_dataset(
        cols, rows, fmt='pdf',
        settings={'page_size': 'a4', 'orientation': 'landscape', 'title': 'Ledger Report', 'include_sql_appendix': True},
        sql_text='SELECT * FROM ORDERS;',
    )
    pdf_bytes = base64.b64decode(pdf_out['content_base64'])
    assert pdf_bytes.startswith(b'%PDF-1.4')
    assert b'%%EOF' in pdf_bytes

    # 5. Surface 1 (`DataSurfaceHostService`) shares `export_formatted`
    from tools.tests.test_data_surface_host import FakeFirebirdWorkspaceService

    ds_host = DataSurfaceHostService(SurfaceLayoutStore(tmp_path / 'layouts.db'))
    fb_ws = FakeFirebirdWorkspaceService()
    srv = SimpleNamespace(id=1, user_id=1)
    ds_host.dispatch(fb_ws, srv, {
        'sub_action': 'open',
        'surface_id': 'ds-exp-1',
        'language_profile': 'firebird-sql',
        'engine_id': 'firebird',
        'target_resource': {'resource_id': 'table:ACCOUNT', 'resource_kind': 'table', 'display_name': 'ACCOUNT'},
    })
    s1_pdf = ds_host.dispatch(fb_ws, srv, {
        'sub_action': 'export_formatted',
        'surface_id': 'ds-exp-1',
        'format': 'pdf',
        'filename': 'accounts',
        'settings': {'title': 'Surface 1 PDF'},
    })
    assert base64.b64decode(s1_pdf['content_base64']).startswith(b'%PDF-1.4')


def test_visual_query_ddn_scene_and_sql_sync():
    vm = {
        'tables': [
            {'id': 't1', 'name': 'CUSTOMERS', 'alias': 'c', 'columns': [{'name': 'ID', 'key': True}]},
            {'id': 't2', 'name': 'ORDERS', 'alias': 'o', 'columns': [{'name': 'CUSTOMER_ID'}]},
            {'id': 't3', 'name': 'SHIPMENTS', 'alias': 's', 'columns': [{'name': 'ORDER_ID'}]},
        ],
        'projections': [
            {'expr': 'c.ID', 'alias': 'CUST_ID'},
            {'expr': 'o.AMOUNT', 'aggregate': 'SUM', 'alias': 'TOTAL_AMT'},
        ],
        'joins': [
            {'join_type': 'INNER', 'left_table': 'c', 'left_column': 'ID', 'right_table': 'o', 'right_column': 'CUSTOMER_ID'},
            {'join_type': 'LEFT', 'left_table': 'o', 'left_column': 'ID', 'right_table': 's', 'right_column': 'ORDER_ID'},
        ],
        'where': ['c.ACTIVE = 1'],
        'group_by': ['c.ID'],
        'limit': 50,
    }
    scene, sql, fanout = build_visual_query_ddn_scene(vm, {}, 'firebird')
    assert len(scene['nodes']) == 3
    assert len(scene['edges']) == 2
    # Verify exact RobinTiledCanvas contract (`loaded_tiles['0:0']`, `name`, `role`, `fields`, `{x, y}` edge points)
    assert '0:0' in scene['loaded_tiles']
    tile0 = scene['loaded_tiles']['0:0']
    assert len(tile0['nodes']) == 3
    assert tile0['nodes'][0]['name'] == 'CUSTOMERS (c)'
    assert tile0['nodes'][0]['role'] == 'TABLE'
    assert tile0['nodes'][0]['fields'][0]['raw_name'] == 'ID'
    assert tile0['nodes'][0]['fields'][0]['is_pk'] is True
    assert isinstance(tile0['edges'][0]['points'][0]['x'], (int, float))
    assert isinstance(tile0['edges'][0]['points'][0]['y'], (int, float))
    assert tile0['edges'][0]['display_label'] == 'INNER: ID = CUSTOMER_ID'
    assert len(fanout) == 1  # two 1:N joins trigger fan-out warning
    assert 'SUM(o.AMOUNT)' in sql
    assert 'FETCH FIRST 50 ROWS ONLY' in sql

    parsed, fidelity = parse_sql_to_visual_model(
        'SELECT c.id FROM customers c INNER JOIN orders o ON c.id = o.customer_id'
    )
    assert fidelity == 'exact'
    assert len(parsed['tables']) == 2
    assert len(parsed['joins']) == 1


def test_visual_builder_selectable_stored_procedures_views_and_fk_auto_joins(tmp_path):
    svc = FakeSqlWorkspaceService()
    srv = SimpleNamespace(id=9, user_id=1)

    catalog = [
        {
            'resource_id': 'table:CUSTOMERS',
            'resource_kind': 'table',
            'display_name': 'CUSTOMERS',
            'display_path': ['CUSTOMERS'],
        },
        {
            'resource_id': 'column:CUSTOMERS.ID',
            'resource_kind': 'column',
            'display_name': 'ID',
            'display_path': ['CUSTOMERS', 'ID'],
            'native': {'field_type': 8, 'primary_key': True, 'not_null': True, 'ordinal_position': 1},
        },
        {
            'resource_id': 'column:CUSTOMERS.NAME',
            'resource_kind': 'column',
            'display_name': 'NAME',
            'display_path': ['CUSTOMERS', 'NAME'],
            'native': {'field_type': 37, 'character_length': 80, 'ordinal_position': 2},
        },
        {
            'resource_id': 'table:ORDERS',
            'resource_kind': 'table',
            'display_name': 'ORDERS',
            'display_path': ['ORDERS'],
            'native': {
                'columns': [
                    {'name': 'ORDER_ID', 'field_type': 8, 'primary_key': True},
                    {'name': 'CUSTOMER_ID', 'field_type': 8, 'referenced_table': 'CUSTOMERS', 'referenced_column': 'ID'},
                ]
            },
        },
        {
            'resource_id': 'procedure:GET_EMP_PROJ',
            'resource_kind': 'procedure',
            'display_name': 'GET_EMP_PROJ',
            'display_path': ['GET_EMP_PROJ'],
            'native': {
                'procedure_type': 1,  # Selectable Firebird procedure (SUSPEND)
                'parameters': [
                    {'name': 'EMP_NO', 'mode': 'input', 'position': 0, 'field_type': 7},
                    {'name': 'PROJ_ID', 'mode': 'output', 'position': 0, 'field_type': 14, 'character_length': 5},
                    {'name': 'PROJ_NAME', 'mode': 'output', 'position': 1, 'field_type': 37, 'character_length': 40},
                ],
            },
        },
        {
            'resource_id': 'procedure:ALL_LANGS',
            'resource_kind': 'procedure',
            'display_name': 'ALL_LANGS',
            'display_path': ['ALL_LANGS'],
            'native': {
                'procedure_type': 1,
                'parameters': [
                    {'name': 'CODE', 'mode': 'output', 'position': 0, 'field_type': 37, 'character_length': 5},
                ],
            },
        },
        {
            'resource_id': 'procedure:LOG_AUDIT_EVENT',
            'resource_kind': 'procedure',
            'display_name': 'LOG_AUDIT_EVENT',
            'display_path': ['LOG_AUDIT_EVENT'],
            'native': {
                'procedure_type': 2,  # Executable-only Firebird procedure
                'parameters': [
                    {'name': 'MSG', 'mode': 'input', 'position': 0, 'field_type': 37, 'character_length': 200},
                ],
            },
        },
    ]

    # 1. Resolve CUSTOMERS from child column resources, then drop ORDERS -> auto-detects FK join!
    cust = resolve_visual_catalog_object(
        svc, srv, 'demo.fdb', {'resource_id': 'table:CUSTOMERS', 'resource_kind': 'table', 'display_name': 'CUSTOMERS'},
        catalog_resources=catalog, existing_tables=[], engine_id='firebird',
    )
    assert [c['name'] for c in cust['object_node']['columns']] == ['ID', 'NAME']

    ords = resolve_visual_catalog_object(
        svc, srv, 'demo.fdb', {'resource_id': 'table:ORDERS', 'resource_kind': 'table', 'display_name': 'ORDERS'},
        catalog_resources=catalog, existing_tables=[cust['object_node']], engine_id='firebird',
    )
    assert len(ords['suggested_joins']) == 1
    assert ords['suggested_joins'][0]['left_column'] == 'ID'
    assert ords['suggested_joins'][0]['right_column'] == 'CUSTOMER_ID'

    # 2. Resolve selectable Firebird procedure with input & RETURNS output parameters
    proc_sel = resolve_visual_catalog_object(
        svc, srv, 'demo.fdb',
        {'resource_id': 'procedure:GET_EMP_PROJ', 'resource_kind': 'procedure', 'display_name': 'GET_EMP_PROJ'},
        catalog_resources=catalog, existing_tables=[], engine_id='firebird',
    )
    pnode = proc_sel['object_node']
    assert pnode['selectable'] is True
    assert [p['name'] for p in pnode['input_parameters']] == ['EMP_NO']
    assert [c['name'] for c in pnode['columns']] == ['PROJ_ID', 'PROJ_NAME']

    # Build scene & SQL for parameterized selectable procedure + 0-arg selectable procedure on Firebird
    proc_zero = resolve_visual_catalog_object(
        svc, srv, 'demo.fdb',
        {'resource_id': 'procedure:ALL_LANGS', 'resource_kind': 'procedure', 'display_name': 'ALL_LANGS'},
        catalog_resources=catalog, existing_tables=[pnode], engine_id='firebird',
    )['object_node']

    scene_proc, sql_proc, _ = build_visual_query_ddn_scene(
        {'tables': [pnode, proc_zero], 'joins': [], 'projections': []},
        {},
        'firebird',
    )
    assert scene_proc['loaded_tiles']['0:0']['nodes'][0]['role'] == 'PROC'
    assert 'GET_EMP_PROJ(:EMP_NO)' in scene_proc['loaded_tiles']['0:0']['nodes'][0]['name']
    assert 'FROM GET_EMP_PROJ(:EMP_NO) AS "p1"' in sql_proc
    # Firebird 0-arg selectable procedure MUST NOT emit empty `()`
    assert 'CROSS JOIN ALL_LANGS AS "p2"' in sql_proc

    # Parse back SQL containing selectable procedure call
    parsed_proc, fid_proc = parse_sql_to_visual_model(sql_proc)
    assert fid_proc == 'exact'
    assert parsed_proc['tables'][0]['name'] == 'GET_EMP_PROJ'
    assert parsed_proc['tables'][0]['resource_kind'] == 'procedure'
    assert parsed_proc['tables'][0]['input_parameters'][0]['expr'] == ':EMP_NO'

    # 3. Executable-only Firebird procedure (`procedure_type == 2`) is cleanly rejected!
    with pytest.raises(ValueError, match='executable-only'):
        resolve_visual_catalog_object(
            svc, srv, 'demo.fdb',
            {'resource_id': 'procedure:LOG_AUDIT_EVENT', 'resource_kind': 'procedure', 'display_name': 'LOG_AUDIT_EVENT'},
            catalog_resources=catalog, existing_tables=[], engine_id='firebird',
        )


@pytest.mark.parametrize('uses_cte', [False, True])
def test_generated_select_replays_parameterized_join_filters_and_sort(uses_cte):
    with sqlite3.connect(':memory:') as conn:
        conn.executescript("""
            CREATE TABLE a (id INTEGER, label TEXT, n INTEGER);
            CREATE TABLE b (id INTEGER, n INTEGER);
            INSERT INTO a VALUES
                (1, 'A_100% O''Brien', 2), (2, 'a_100% o''brien', 3),
                (3, 'A_100% O''Brien', 9), (4, 'Ar100X O''Brien', 9),
                (5, NULL, 9);
            INSERT INTO b VALUES (1, NULL), (2, 4), (3, 7), (4, 10), (5, 12);
        """)
        source = """
            SELECT a.id, a.label, a.n, b.n
            FROM a JOIN b ON b.id = a.id
            WHERE a.n >= :threshold
            ORDER BY a.id
        """.strip()
        if uses_cte:
            source = 'WITH selected AS (SELECT * FROM a) ' + source.replace('FROM a JOIN', 'FROM selected a JOIN')
        fields = ['id', 'label', 'n', 'n (2)']
        parameters = {'threshold': 3}
        baseline = conn.execute(source, parameters).fetchall()
        result = SqlResultSetBuffer(
            0, 'Joined result', source,
            columns=[{'name': name, 'native_type': 'dynamic'} for name in fields],
            raw_rows=[{'values': dict(zip(fields, row))} for row in baseline],
            filters=[{'column': 'label', 'op': 'contains', 'value': "_100% O'Brien"}],
            sorts=[{'column': 'n (2)', 'dir': 'desc'}],
        )
        SqlSurfaceHostService._recompute_rs_view(result)
        effective = build_effective_select(result, 'sqlite')
        actual = conn.execute(effective['sql'], parameters)
        assert [column[0] for column in actual.description] == fields
        assert actual.fetchall() == [baseline[index] for index in result.view_indices]
        assert 'ESCAPE' in effective['sql']


@pytest.mark.parametrize('source, adjustment, expected', [
    ('UPDATE a SET n = 2 RETURNING n', {}, 'wrappable SELECT'),
    ('SELECT n FROM a FOR UPDATE', {}, 'wrappable SELECT'),
    ('SELECT n FROM a', {'sorts': [{'column': 'other'}]}, 'active result column'),
    ('SELECT n FROM a', {'sorts': [{'column': 'n'}]}, 'numeric-looking'),
])
def test_effective_query_reports_unsupported_shapes(source, adjustment, expected):
    result = SqlResultSetBuffer(
        0, 'Result', source, columns=[{'name': 'n', 'client_type': 'text'}],
        raw_rows=[{'values': {'n': '10'}}], **adjustment,
    )
    response = build_effective_select(result, 'sqlite')
    assert not response['sql']
    assert expected in response['reason']


def test_effective_query_bindings_follow_the_selected_result(tmp_path):
    host = SqlSurfaceHostService(
        snippets_store=SqlSnippetsStore(tmp_path / 'snippets.db'),
        quick_query_store=QuickQueryStore(tmp_path / 'queries.db'),
        layout_store=SurfaceLayoutStore(tmp_path / 'layouts.db'),
    )
    workspace = FakeSqlWorkspaceService()
    server = SimpleNamespace(id=5, user_id=1)
    scope = {'surface_id': 'effective-test', 'engine_id': 'firebird',
             'language_profile': 'firebird-sql', 'database_target_id': 'owned.fdb'}
    original = host.dispatch(workspace, server, {
        **scope, 'sub_action': 'execute', 'mode': 'script',
        'sql_source': 'SELECT :left_id FROM RDB$DATABASE; SELECT :right_id FROM RDB$DATABASE;',
        'parameters': {'left_id': 100, 'right_id': 200}, 'client_sql_dialect': 3,
    })
    assert original['sql_view']['effective_query']['parameters'] == [
        {'name': 'left_id', 'value': '100', 'type': 'integer', 'isNull': False},
    ]
    selected = host.dispatch(workspace, server, {
        **scope, 'sub_action': 'select_result', 'result_index': 1,
    })
    query = selected['sql_view']['effective_query']
    assert query['sql'] == 'SELECT :right_id FROM RDB$DATABASE'
    assert query['parameters'] == [
        {'name': 'right_id', 'value': '200', 'type': 'integer', 'isNull': False},
    ]
    assert query['client_sql_dialect'] == 3


def test_mysql_surface_binds_authored_and_native_names_on_the_retained_session(tmp_path):
    class MySQLWorkspace(FakeSqlWorkspaceService):
        def language_tool_action(self, server, action, data):
            assert action == 'source_format_context'
            assert data['session_id'] == self.sessions_opened[0]['session_id']
            return {'context': {'engine': 'mysql', 'sql_mode': 'ANSI_QUOTES', 'version': '9.7.0'}}

    host = SqlSurfaceHostService(
        snippets_store=SqlSnippetsStore(tmp_path / 'snippets.db'),
        quick_query_store=QuickQueryStore(tmp_path / 'queries.db'),
        layout_store=SurfaceLayoutStore(tmp_path / 'layouts.db'),
    )
    workspace = MySQLWorkspace()
    scope = {'surface_id': 'mysql-bindings', 'engine_id': 'mysql',
             'language_profile': 'mysql-sql', 'database_target_id': 'fixture'}
    server = SimpleNamespace(id=5, user_id=1)
    source = """SELECT :amount, :amount, %(label)s, ':literal', "column:identifier" /* :comment */"""
    probe = host.dispatch(workspace, server, {
        **scope, 'sub_action': 'check_parameters', 'sql_source': source,
    })
    assert [(item['name'], item['token']) for item in probe['parameters']] == [
        ('amount', ':amount'), ('label', '%(label)s'),
    ]
    state = host.dispatch(workspace, server, {
        **scope, 'sub_action': 'execute', 'sql_source': source,
        'parameters': {'amount': 42, 'label': 'bound value', 'other_statement': 7},
    })
    assert len(workspace.executed) == 1
    assert workspace.executed[0]['source'] == source.replace(':amount', '%(amount)s')
    assert workspace.executed[0]['parameters'] == {'amount': 42, 'label': 'bound value'}
    assert state['sql_view']['effective_query']['sql'] == source
    assert state['sql_view']['effective_query']['parameters'] == [
        {'name': 'amount', 'value': '42', 'type': 'integer', 'isNull': False},
        {'name': 'label', 'value': 'bound value', 'type': 'text', 'isNull': False},
    ]


def test_mysql_script_distributes_positional_bindings_by_statement(tmp_path):
    class MySQLWorkspace(FakeSqlWorkspaceService):
        def language_tool_action(self, server, action, data):
            assert action == 'source_format_context'
            assert data['session_id'] == self.sessions_opened[0]['session_id']
            return {'context': {'engine': 'mysql', 'sql_mode': '', 'version': '9.7.0'}}

    host = SqlSurfaceHostService(
        snippets_store=SqlSnippetsStore(tmp_path / 'snippets.db'),
        quick_query_store=QuickQueryStore(tmp_path / 'queries.db'),
        layout_store=SurfaceLayoutStore(tmp_path / 'layouts.db'),
    )
    workspace = MySQLWorkspace()
    server = SimpleNamespace(id=5, user_id=1)
    scope = {'surface_id': 'mysql-script', 'engine_id': 'mysql',
             'language_profile': 'mysql-sql', 'database_target_id': 'fixture'}
    source = "SELECT ?, '? %s'; SELECT 7; SELECT %s, ? /* ? */;"
    request = {**scope, 'mode': 'script', 'sql_source': source}
    probe = host.dispatch(workspace, server, {**request, 'sub_action': 'check_parameters'})
    assert [(item['name'], item['token']) for item in probe['parameters']] == [
        ('param_1', '?'), ('param_2', '%s'), ('param_3', '?'),
    ]
    for values in ([], [11, None], [11, None, 'last', 'extra']):
        with pytest.raises(ValueError, match='one value per positional'):
            host.dispatch(workspace, server, {
                **request, 'sub_action': 'execute', 'parameters': values,
            })
        assert workspace.executed == []

    host.dispatch(workspace, server, {
        **request, 'sub_action': 'execute', 'parameters': [11, None, 'last'],
    })
    assert [(call['source'], call['parameters']) for call in workspace.executed] == [
        ("SELECT %s, '? %s'", [11]), ('SELECT 7', []),
        ('SELECT %s, %s /* ? */', [None, 'last']),
    ]
    selected = host.dispatch(workspace, server, {
        **scope, 'sub_action': 'select_result', 'result_index': 2,
    })
    assert selected['sql_view']['effective_query']['parameters'] == [
        {'name': 'param_1', 'value': '', 'type': 'json', 'isNull': True},
        {'name': 'param_2', 'value': 'last', 'type': 'text', 'isNull': False},
    ]


def test_postgresql_auto_commit_tracks_native_policy_and_preserves_active_work(tmp_path):
    class TransactionWorkspace(FakeSqlWorkspaceService):
        autocommit = True
        active = False

        def transaction(self, server, session_id, database_target_id=None):
            return {'provider_payload': {
                'autocommit': self.autocommit,
                'transaction_status': 2 if self.active else 0,
            }}

        def transaction_action(self, server, session_id, action, database_target_id=None):
            self.tx_actions.append((session_id, action))
            if action in ('autocommit_on', 'autocommit_off'):
                if self.active:
                    raise RuntimeError('Complete the native transaction first.')
                self.autocommit = action == 'autocommit_on'
            elif action == 'rollback':
                self.active = False
            return self.transaction(server, session_id, database_target_id)

        def execute(self, server, session_id, source, **options):
            self.active |= not self.autocommit or source == 'BEGIN'
            return super().execute(server, session_id, source, **options)

    host = SqlSurfaceHostService(
        snippets_store=SqlSnippetsStore(tmp_path / 'snippets.db'),
        quick_query_store=QuickQueryStore(tmp_path / 'queries.db'),
        layout_store=SurfaceLayoutStore(tmp_path / 'layouts.db'),
    )
    workspace = TransactionWorkspace()
    owner = SimpleNamespace(id=5, user_id=1)
    scope = {'surface_id': 'auto-commit', 'engine_id': 'postgresql',
             'language_profile': 'postgresql-sql', 'database_target_id': 'test-db'}

    def action(name, **request):
        return host.dispatch(workspace, owner, {**scope, 'sub_action': name, **request})

    state = action('execute', sql_source='SELECT 1')
    assert workspace.tx_actions == [('sql-sess-1', 'autocommit_off')]
    assert state['has_uncommitted_activity'] and not state['autocommit']
    with pytest.raises(RuntimeError, match='native transaction first'):
        action('set_options', autocommit=True)
    assert not action('read_window')['autocommit']
    action('rollback_batch')
    assert action('set_options', autocommit=True)['autocommit']
    assert action('execute', sql_source='BEGIN')['has_uncommitted_activity']
    assert [name for _, name in workspace.tx_actions] == [
        'autocommit_off', 'autocommit_on', 'rollback', 'autocommit_on',
    ]


@pytest.mark.parametrize('engine, options, expected', [
    ('postgresql', {'access': 'read_only', 'isolation': 'serializable'},
     ['SET TRANSACTION ISOLATION LEVEL SERIALIZABLE, READ ONLY']),
    ('mysql', {'access': 'read_only', 'isolation': 'read_committed'},
     ['SET TRANSACTION ISOLATION LEVEL READ COMMITTED', 'START TRANSACTION READ ONLY']),
    ('mariadb', {'access': 'read_write', 'isolation': 'repeatable_read'},
     ['SET TRANSACTION ISOLATION LEVEL REPEATABLE READ', 'START TRANSACTION READ WRITE']),
    ('sqlite', {'mode': 'immediate'}, ['BEGIN IMMEDIATE TRANSACTION']),
])
def test_sql_surface_starts_native_transaction_and_refuses_a_second_start(
    tmp_path, engine, options, expected,
):
    class TransactionWorkspace(FakeSqlWorkspaceService):
        def transaction(self, server, session_id, database_target_id=None):
            active = len(self.executed) == len(expected)
            return {'provider_payload': {
                'transaction_status': 2 if active else 0, 'autocommit': engine != 'postgresql',
                'in_transaction': active, 'session_reuse_blocked': False,
            }}

        def poll(self, server, occurrence_id, **options):
            return {'occurrence': {
                'operation': {'terminal': True},
                'result': {'complete': True, 'extensions': {engine: {'payload': {}}}},
            }}

    host = SqlSurfaceHostService(
        snippets_store=SqlSnippetsStore(tmp_path / 'snippets.db'),
        quick_query_store=QuickQueryStore(tmp_path / 'queries.db'),
        layout_store=SurfaceLayoutStore(tmp_path / 'layouts.db'),
    )
    workspace = TransactionWorkspace()
    owner = SimpleNamespace(id=5, user_id=1)
    request = {
        'surface_id': 'native-start', 'engine_id': engine, 'language_profile': f'{engine}-sql',
        'database_target_id': 'test-db', 'sub_action': 'start_transaction',
    }
    with pytest.raises(ValueError, match='Invalid native transaction options'):
        host.dispatch(workspace, owner, {**request, 'transaction_options': {**options, 'other': 'value'}})
    assert not workspace.executed

    response = host.dispatch(workspace, owner, {**request, 'transaction_options': options})
    assert response['has_uncommitted_activity']
    assert [call['source'] for call in workspace.executed] == expected
    with pytest.raises(ValueError, match='complete pending work'):
        host.dispatch(workspace, owner, {**request, 'transaction_options': options})
    assert len(workspace.executed) == len(expected)


@pytest.mark.parametrize('engine', ['firebird', 'postgresql', 'sqlite', 'duckdb', 'mysql', 'mariadb'])
def test_sql_editor_format_uses_retained_non_executing_language_tools(tmp_path, engine):
    class FormattingWorkspace(FakeSqlWorkspaceService):
        def __init__(self):
            super().__init__()
            self.language_calls = []

        def language_tool_action(self, server, action, data):
            self.language_calls.append((action, data))
            if action == 'source_format_context':
                return {'context': {'engine': engine}}
            return {'grammar_valid': True}

    host = SqlSurfaceHostService(
        snippets_store=SqlSnippetsStore(tmp_path / 'snippets.db'),
        quick_query_store=QuickQueryStore(tmp_path / 'queries.db'),
        layout_store=SurfaceLayoutStore(tmp_path / 'layouts.db'),
    )
    workspace = FormattingWorkspace()
    owner = SimpleNamespace(id=5, user_id=1)
    scope = {'surface_id': 'format', 'engine_id': engine,
             'language_profile': f'{engine}-sql', 'database_target_id': 'test-db',
             'client_sql_dialect': 1}
    source = 'select 1'
    assert host.dispatch(workspace, owner, {
        **scope, 'sub_action': 'format_context', 'sql_source': source,
    }) == {'context': {'engine': engine}}
    assert host.dispatch(workspace, owner, {
        **scope, 'sub_action': 'validate_format', 'sql_source': source, 'script': True,
    }) == {'grammar_valid': True}
    first, second = workspace.language_calls
    assert (first[0], second[0]) == ('source_format_context', 'source_validate')
    assert first[1]['session_id'] == second[1]['session_id']
    assert first[1]['database_target_id'] == second[1]['database_target_id'] == 'test-db'
    assert first[1]['source'] == source
    assert second[1]['script'] is True
    assert second[1].get('client_sql_dialect') == (1 if engine == 'firebird' else None)
    assert workspace.executed == []


def test_sql_editor_lists_the_data_viewer_shared_templates(tmp_path):
    layouts = SurfaceLayoutStore(tmp_path / 'layouts.db')
    host = SqlSurfaceHostService(
        snippets_store=SqlSnippetsStore(tmp_path / 'snippets.db'),
        quick_query_store=QuickQueryStore(tmp_path / 'queries.db'),
        layout_store=layouts,
    )
    viewer = DataSurfaceHostService(layouts)
    workspace = FakeSqlWorkspaceService()
    reader = SimpleNamespace(id=5, user_id=2)
    request = {'sub_action': 'list_templates'}
    assert host.dispatch(workspace, reader, request) == {'templates': []}

    layout = {'displayMode': 'mini_forms', 'formColOrder': ['TITLE', 'ID']}
    saved = layouts.save_template(1, 'data-edit-surface', 'Shared rows', layout)
    layouts.save_template(1, 'unrelated-surface', 'Other template', {})
    response = host.dispatch(workspace, reader, request)

    assert response == viewer.dispatch(workspace, reader, request)
    assert len(response['templates']) == 1
    assert response['templates'][0]['template_id'] == saved['template_id']
    assert response['templates'][0]['layout'] == layout
    assert not workspace.sessions_opened


def test_sql_editor_cancel_interrupts_an_editable_row_read_without_sql_fallback(tmp_path):
    class CancellableWorkspace(FakeSqlWorkspaceService):
        def __init__(self):
            super().__init__()
            self.ready = Event()
            self.interrupted = Event()

        def read_cancellable_surface_rows(self, server, request, execution):
            with execution.cancellable_row_read(self.interrupted.set):
                self.ready.set()
                assert self.interrupted.wait(3)
                raise RuntimeError('Native read interrupted')

    host = SqlSurfaceHostService(
        snippets_store=SqlSnippetsStore(tmp_path / 'snippets.db'),
        quick_query_store=QuickQueryStore(tmp_path / 'queries.db'),
        layout_store=SurfaceLayoutStore(tmp_path / 'layouts.db'),
    )
    workspace = CancellableWorkspace()
    owner = SimpleNamespace(id=5, user_id=1)
    scope = {'surface_id': 'cancel-row', 'database_target_id': 'target',
             'engine_id': 'postgresql', 'language_profile': 'postgresql-sql',
             'execution_id': 'current-row-read'}
    resource = {'resource_id': 'table:item', 'resource_kind': 'table',
                'display_name': 'item', 'display_path': ['public', 'item']}
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(host.dispatch, workspace, owner, {
            **scope, 'sub_action': 'execute', 'sql_source': 'SELECT * FROM public.item',
            'catalog_resources': [resource],
        })
        assert workspace.ready.wait(3)
        cancel = host.dispatch(workspace, owner, {**scope, 'sub_action': 'cancel'})
        assert cancel == {'cancel_status': 'requested', 'occurrence_id': None}
        result = running.result(timeout=3)
    assert result['last_execution_cancelled'] and not result['last_execution_had_error']
    assert result['result_count'] == 0 and not workspace.executed


@pytest.mark.parametrize('cancel_before_occurrence', [False, True])
def test_sql_editor_cancel_targets_active_run_and_stops_script(tmp_path, cancel_before_occurrence):
    class CancellableWorkspace(FakeSqlWorkspaceService):
        def __init__(self):
            super().__init__()
            self.ready = Event()
            self.release = Event()
            self.cancel_calls = []

        def execute(self, server, **request):
            occurrence = super().execute(server, **request)
            if cancel_before_occurrence:
                self.ready.set()
                assert self.release.wait(3)
            return occurrence

        def poll(self, server, occurrence_id, **options):
            if not cancel_before_occurrence:
                self.ready.set()
                assert self.release.wait(3)
            assert self.cancel_calls
            return {
                'occurrence': {
                    'operation': {'terminal': True},
                    'result': {'extensions': {'firebird': {'payload': {
                        'execution_state': 'cancelled',
                    }}}},
                },
            }

        def cancel(self, server, occurrence_id, database_target_id=None):
            self.cancel_calls.append((occurrence_id, database_target_id))
            self.release.set()
            return {'occurrence_id': occurrence_id, 'operation': {'terminal': False}}

    host = SqlSurfaceHostService(
        snippets_store=SqlSnippetsStore(tmp_path / 'snippets.db'),
        quick_query_store=QuickQueryStore(tmp_path / 'queries.db'),
        layout_store=SurfaceLayoutStore(tmp_path / 'layouts.db'),
    )
    workspace = CancellableWorkspace()
    owner = SimpleNamespace(id=5, user_id=1)
    scope = {
        'surface_id': 'cancel-surface', 'database_target_id': 'owned.fdb',
        'engine_id': 'firebird', 'language_profile': 'firebird-sql',
        'execution_id': 'active-run',
    }
    cancel = {**scope, 'sub_action': 'cancel'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        running = pool.submit(host.dispatch, workspace, owner, {
            **scope, 'sub_action': 'execute', 'mode': 'script',
            'sql_source': 'SELECT 1; SELECT 2;',
        })
        try:
            assert workspace.ready.wait(3)
            for actor, request in (
                (SimpleNamespace(id=5, user_id=9), cancel),
                (SimpleNamespace(id=9, user_id=1), cancel),
                (owner, {**cancel, 'database_target_id': 'other.fdb'}),
                (owner, {**cancel, 'execution_id': 'stale-run'}),
            ):
                assert host.dispatch(workspace, actor, request) == {'cancel_status': 'idle'}
            receipt = pool.submit(host.dispatch, workspace, owner, cancel).result(timeout=2)
            assert receipt['cancel_status'] == ('pending' if cancel_before_occurrence else 'requested')
        finally:
            workspace.release.set()
        result = running.result(timeout=3)

    assert result['last_execution_cancelled']
    assert not result['last_execution_had_error']
    assert len(workspace.executed) == 1
    assert len(workspace.cancel_calls) == 1
    assert workspace.cancel_calls[0][1] == 'owned.fdb'
    assert host.dispatch(workspace, owner, cancel) == {'cancel_status': 'idle'}


def test_sql_surface_host_end_to_end_lifecycle_and_live_editing(tmp_path):
    host = SqlSurfaceHostService(
        snippets_store=SqlSnippetsStore(tmp_path / 'snips.db'),
        quick_query_store=QuickQueryStore(tmp_path / 'qq.db'),
        layout_store=SurfaceLayoutStore(tmp_path / 'lay.db'),
    )
    ws = FakeSqlWorkspaceService()
    srv = SimpleNamespace(id=5, user_id=1)
    ledger_res = {
        'resource_id': 'table:LEDGER',
        'resource_kind': 'table',
        'display_name': 'LEDGER',
        'name': 'LEDGER',
    }

    # 1. Open bound SQL surface with `Generate SQL -> insert` (does NOT auto-execute!)
    st = host.dispatch(ws, srv, {
        'sub_action': 'open',
        'surface_id': 'ss-1',
        'engine_id': 'firebird',
        'language_profile': 'firebird-sql',
        'database_target_id': 'demo.fdb',
        'target_resource': ledger_res,
        'generate_sql_kind': 'insert',
        'resources': [ledger_res],
    })
    assert 'INSERT INTO' in st['sql_source']
    assert len(ws.executed) == 0

    # 2. Check parameters for parameterized query
    chk = host.dispatch(ws, srv, {
        'sub_action': 'check_parameters',
        'surface_id': 'ss-1',
        'sql_source': 'SELECT * FROM LEDGER WHERE ID = :target_id',
    })
    assert len(chk['parameters']) == 1
    assert chk['parameters'][0]['token'] == ':target_id'

    # 3. Multi-statement script execution produces 2 result sets & selects between them
    st_multi = host.dispatch(ws, srv, {
        'sub_action': 'execute',
        'mode': 'script',
        'client_sql_dialect': 1,
        'surface_id': 'ss-1',
        'sql_source': 'SELECT 1 FROM RDB$DATABASE; SELECT 2 FROM RDB$DATABASE;',
    })
    assert st_multi['result_count'] == 2
    assert [call['client_sql_dialect'] for call in ws.executed[-2:]] == [1, 1]
    assert st_multi['active_result']['columns'][0]['key'] is True
    assert st_multi['active_result']['columns'][1]['key'] is False
    assert st_multi['active_result']['columns'][1]['max_length'] == 64
    st_sel = host.dispatch(ws, srv, {
        'sub_action': 'select_result',
        'surface_id': 'ss-1',
        'result_index': 1,
    })
    assert st_sel['active_result_index'] == 1

    # 4. Single-table `SELECT * FROM LEDGER` resolves live editable row identity!
    st_live = host.dispatch(ws, srv, {
        'sub_action': 'execute',
        'mode': 'statement',
        'surface_id': 'ss-1',
        'sql_source': 'SELECT * FROM LEDGER',
        'resources': [ledger_res],
    })
    assert st_live['active_result']['editable'] is True
    object_key = st_live['object_layout_key']
    assert object_key == '5:demo.fdb:table:LEDGER'
    layout = {'displayMode': 'mini_forms'}
    host.dispatch(ws, srv, {
        'sub_action': 'save_object_layout',
        'surface_id': 'ss-1',
        'object_layout_key': object_key,
        'layout': layout,
    })
    assert host.layout_store.get_specific_layout(1, 'data-edit-surface', object_key) == layout
    selected = host.dispatch(ws, srv, {
        'sub_action': 'select_result', 'surface_id': 'ss-1', 'result_index': 0,
    })
    assert selected['saved_specific_layout'] == layout
    defaults = {'integer': {'font': 'mono', 'hAlign': 'right'}}
    host.dispatch(ws, srv, {
        'sub_action': 'save_field_type_defaults', 'field_type_defaults': defaults,
    })
    viewer = DataSurfaceHostService(host.layout_store)
    assert viewer.dispatch(ws, srv, {'sub_action': 'get_field_type_defaults'}) == {
        'field_type_defaults': defaults,
    }
    other_user = SimpleNamespace(id=5, user_id=2)
    assert host.dispatch(ws, other_user, {'sub_action': 'get_field_type_defaults'}) == {
        'field_type_defaults': {},
    }
    assert len(st_live['active_result']['rows']) == 2

    # Stage update -> uncommitted activity true -> commit flushes batch & clears dirty state
    st_staged = host.dispatch(ws, srv, {
        'sub_action': 'stage_row',
        'surface_id': 'ss-1',
        'op': 'update',
        'base_row_index': 0,
        'changes': {'TITLE': 'Alpha Updated'},
    })
    assert st_staged['has_uncommitted_activity'] is True
    assert st_staged['staged_count'] == 1
    assert st_staged['active_result']['rows'][0]['values']['TITLE'] == 'Alpha Updated'

    st_committed = host.dispatch(ws, srv, {
        'sub_action': 'commit_batch',
        'surface_id': 'ss-1',
    })
    assert st_committed['has_uncommitted_activity'] is False
    assert st_committed['staged_count'] == 0
    assert len(ws.applied_plans) == 1

    # 5. Error execution logs diagnostic into `messages` with line number & `last_execution_had_error`
    ws.fail_next_error = 'Dynamic SQL Error: Table UNKNOWN not found'
    st_err = host.dispatch(ws, srv, {
        'sub_action': 'execute',
        'mode': 'statement',
        'surface_id': 'ss-1',
        'sql_source': 'SELECT * FROM UNKNOWN',
    })
    assert st_err['last_execution_had_error'] is True
    assert any('UNKNOWN' in m['message'] for m in st_err['messages'])

    # 6. Close surface releases host session
    closed = host.dispatch(ws, srv, {'sub_action': 'close_surface', 'surface_id': 'ss-1'})
    assert closed['closed'] is True
    assert len(ws.sessions_closed) == 1


@pytest.mark.parametrize('clause', [
    'WHERE c.ID = 1', 'GROUP BY c.ID', 'ORDER BY c.ID',
    'FETCH FIRST 2 ROWS ONLY', 'LIMIT 2',
])
def test_visual_conversion_reports_unmodeled_clauses_as_lossy(clause):
    model, fidelity = parse_sql_to_visual_model('SELECT c.ID FROM CUSTOMERS c ' + clause)
    assert model is not None
    assert fidelity == 'lossy'


@pytest.mark.parametrize('source', ['', '/* SUSPEND */', 'BEGIN /* SUSPEND */ EXIT; END'])
def test_executable_routine_metadata_cannot_be_overridden_by_source_text(source):
    with pytest.raises(ValueError, match='executable-only'):
        resolve_visual_catalog_object(None, None, 'owned.fdb', {
            'resource_id': 'procedure:LOG_ONLY', 'resource_kind': 'procedure',
            'display_name': 'LOG_ONLY', 'native': {
                'procedure_type': 2, 'source': source,
                'parameters': [{'name': 'OUT_ID', 'mode': 'output', 'field_type': 8}],
            },
        }, engine_id='firebird')


def test_join_execution_uses_public_api_and_rendered_column_keys(tmp_path):
    from inspect import signature
    from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService

    class RenderedJoinWorkspace(FakeSqlWorkspaceService):
        def poll(self, server, occ_id, buffer_rows=200, database_target_id=None):
            return {
                'occurrence': {'operation': {'terminal': True}, 'result': {}},
                'rendered_result': {
                    'view_model': {
                        'columns': [
                            {'name': 'CUSTOMER_ID', 'key': 'col_0', 'native_type': 'INTEGER'},
                            {'name': 'CUSTOMER_ID', 'key': 'col_1', 'native_type': 'INTEGER'},
                        ],
                        'rows': [{'col_0': 7, 'col_1': 107}],
                    },
                    'page': {'next_cursor': None},
                },
            }

    host = SqlSurfaceHostService(
        snippets_store=SqlSnippetsStore(tmp_path/'snips.db'),
        quick_query_store=QuickQueryStore(tmp_path/'queries.db'),
        layout_store=SurfaceLayoutStore(tmp_path/'layout.db'),
    )
    workspace = RenderedJoinWorkspace()
    server = SimpleNamespace(id=1, user_id=1)
    sql = 'select * from "ASSETS" a join "CUSTOMERS" b on a."CUSTOMER_ID"=b."CUSTOMER_ID"'
    state = host.dispatch(workspace, server, {
        'sub_action': 'execute', 'surface_id': 'join-contract',
        'engine_id': 'firebird', 'language_profile': 'firebird-sql',
        'database_target_id': 'owned.fdb', 'sql_source': sql,
    })
    call = workspace.executed[0]
    signature(ProviderWorkspaceService.execute).bind(workspace, server, **call)
    assert call['source'] == sql
    assert call['database_target_id'] == 'owned.fdb'
    assert state['result_count'] == 1
    result = state['active_result']
    assert [c['name'] for c in result['columns']] == ['CUSTOMER_ID', 'CUSTOMER_ID (2)']
    assert result['rows'][0]['values'] == {'CUSTOMER_ID': 7, 'CUSTOMER_ID (2)': 107}


def test_rejected_visual_join_draft_keeps_the_last_valid_surface(tmp_path):
    host = SqlSurfaceHostService(
        snippets_store=SqlSnippetsStore(tmp_path/'snips.db'),
        quick_query_store=QuickQueryStore(tmp_path/'queries.db'),
        layout_store=SurfaceLayoutStore(tmp_path/'layout.db'),
    )
    workspace = FakeSqlWorkspaceService()
    server = SimpleNamespace(id=1, user_id=1)
    base = {'surface_id':'join-review', 'engine_id':'firebird', 'language_profile':'firebird-sql'}
    model = {'tables':[{'id':'a','name':'ASSETS','alias':'a'},
                       {'id':'b','name':'CUSTOMERS','alias':'b'}],
             'joins':[{'join_type':'INNER','left_table':'b','left_column':'CUSTOMER_ID',
                       'right_table':'a','right_column':'CUSTOMER_ID'}]}
    accepted = host.dispatch(workspace, server, {**base,'sub_action':'visual_builder_scene','model':model})
    invalid = copy.deepcopy(model)
    invalid['tables'][1]['alias'] = 'a'
    with pytest.raises(ValueError, match='unique alias'):
        host.dispatch(workspace, server, {**base,'sub_action':'visual_builder_scene','model':invalid})
    current = host.dispatch(workspace, server, {**base,'sub_action':'read_window'})
    assert current['sql_source'] == accepted['sql_text']
    assert [t['alias'] for t in current['visual_builder']['model']['tables']] == ['a','b']


def test_firebird_surface_native_prepare_and_start_use_distinct_receipts(tmp_path):
    host = SqlSurfaceHostService(
        snippets_store=SqlSnippetsStore(tmp_path / 'snippets.db'),
        quick_query_store=QuickQueryStore(tmp_path / 'queries.db'),
        layout_store=SurfaceLayoutStore(tmp_path / 'layouts.db'),
    )
    server = SimpleNamespace(id=12, user_id=1)
    calls = []

    def execute(_server, **request):
        calls.append(request)
        return {'occurrence_id': 'native-control'}

    def poll(_server, _occurrence, **_request):
        payload = (
            {'query_plan': {'statement_execution_requested': False, 'columns': [{'name': 'ID'}]}}
            if calls[-1].get('plan_mode')
            else {'transaction_action': {'action': 'begin', 'native_call_made': True}}
        )
        return {'occurrence': {'operation': {'terminal': True},
                               'result': {'extensions': {'native': {'payload': payload}}}}}

    workspace = SimpleNamespace(
        open_session=lambda *_args, **_kwargs: {'session_id': 'retained'},
        execute=execute, poll=poll, transaction=lambda *_args: {'state': 'active'},
    )
    scope = {'surface_id': 'surface', 'language_profile': 'firebird-sql',
             'engine_id': 'firebird', 'database_target_id': 'test'}
    prepared = host.dispatch(workspace, server, {
        **scope, 'sub_action': 'prepare_statement',
        'sql_source': 'SELECT ID FROM ITEMS WHERE ID = ?;',
    })
    assert prepared['prepared_statement']['columns'] == [{'name': 'ID'}]
    assert calls[0]['plan_mode'] is True and calls[0]['parameters'] == []

    with pytest.raises(ValueError, match='exactly one statement'):
        host.dispatch(workspace, server, {
            **scope, 'sub_action': 'prepare_statement', 'sql_source': 'SELECT 1; SELECT 2;',
        })
    assert len(calls) == 1

    start = {**scope, 'sub_action': 'start_transaction',
             'transaction_options': {'access': 'read_only', 'isolation': 'snapshot', 'wait': 'no_wait'}}
    state = host.dispatch(workspace, server, start)
    assert calls[1]['source'] == 'SET TRANSACTION READ ONLY SNAPSHOT NO WAIT'
    assert calls[1]['session_id'] == calls[0]['session_id']
    assert state['has_uncommitted_activity'] is True
    with pytest.raises(ValueError, match='pending work'):
        host.dispatch(workspace, server, start)
    assert len(calls) == 2
    with pytest.raises(ValueError, match='integer 1, 2 or 3'):
        host.dispatch(workspace, server, {
            **scope, 'sub_action': 'execute', 'sql_source': 'SELECT 1 FROM RDB$DATABASE',
            'client_sql_dialect': True,
        })
    assert len(calls) == 2


def test_columnar_pages_survive_empty_terminal_result_and_respect_buffer_limit(tmp_path):
    host = SqlSurfaceHostService(
        snippets_store=SqlSnippetsStore(tmp_path / 'snippets.db'),
        quick_query_store=QuickQueryStore(tmp_path / 'queries.db'),
        layout_store=SurfaceLayoutStore(tmp_path / 'layouts.db'),
    )
    columns = [{'key': '0', 'name': 'VALUE', 'native_type': 'INTEGER'}]

    def frame(values, *, terminal=False):
        return {
            'occurrence': {'operation': {'terminal': terminal}},
            'rendered_result': {'view_model': {
                'family': 'columnar', 'columns': [] if terminal else columns,
                'rows': [{'0': value} for value in values],
            }},
        }

    frames = iter([frame([42]), frame([43, 44]), frame([], terminal=True)])

    def execute(_server, **request):
        assert 'max_rows' not in request
        return {'occurrence_id': 'stream'}

    workspace = SimpleNamespace(
        open_session=lambda *_args, **_kwargs: {'session_id': 'duck'},
        execute=execute, poll=lambda *_args, **_kwargs: next(frames),
    )
    state = host.dispatch(workspace, SimpleNamespace(id=45, user_id=1), {
        'surface_id': 'duck-test', 'language_profile': 'duckdb-sql', 'engine_id': 'duckdb',
        'database_target_id': 'fixture', 'sub_action': 'execute', 'sql_source': 'SELECT 42',
        'max_rows': 2,
    })
    assert [row['values']['VALUE'] for row in state['active_result']['rows']] == [42, 43]
    assert state['retrieval_limited'] is True

    # Selection-scoped export_formatted slices columns & rows cleanly on SqlSurfaceHostService
    exp = host.dispatch(workspace, SimpleNamespace(id=45, user_id=1), {
        'surface_id': 'duck-test',
        'sub_action': 'export_formatted',
        'format': 'csv',
        'filename': 'duck_slice',
        'settings': {
            'scope': 'selection',
            'selected_column_names': ['VALUE'],
            'selected_rows_payload': [{'values': {'VALUE': 43}}],
        },
    })
    decoded = base64.b64decode(exp['content_base64']).decode('utf-8')
    assert decoded.splitlines() == ['VALUE', '43']


def test_visual_builder_recursive_cte_and_window_analytics_compile_and_execute_live_sqlite(tmp_path):
    import sqlite3

    visual_model = {
        'active_stage': '__final__',
        'ctes': [
            {
                'id': 'c_org',
                'name': 'org_tree',
                'columns': 'emp_id, emp_name, dept, salary, depth',
                'recursive': True,
                'union_mode': 'UNION ALL',
                'materialized': '',
                'anchor': {
                    'tables': [
                        {
                            'id': 'e0',
                            'name': 'employees',
                            'alias': 'e0',
                            'columns': [
                                {'name': 'id', 'type': 'INTEGER'},
                                {'name': 'name', 'type': 'TEXT'},
                                {'name': 'manager_id', 'type': 'INTEGER'},
                                {'name': 'dept', 'type': 'TEXT'},
                                {'name': 'salary', 'type': 'INTEGER'},
                            ],
                        }
                    ],
                    'joins': [],
                    'projections': [
                        {'expr': 'e0.id', 'alias': 'emp_id'},
                        {'expr': 'e0.name', 'alias': 'emp_name'},
                        {'expr': 'e0.dept', 'alias': 'dept'},
                        {'expr': 'e0.salary', 'alias': 'salary'},
                        {'expr': '0', 'alias': 'depth'},
                    ],
                    'where': ['e0.manager_id IS NULL'],
                },
                'recursive_branch': {
                    'tables': [
                        {
                            'id': 'r1',
                            'resource_kind': 'cte-self',
                            'name': 'org_tree',
                            'alias': 'r1',
                        },
                        {
                            'id': 'e1',
                            'name': 'employees',
                            'alias': 'e1',
                        },
                    ],
                    'joins': [
                        {
                            'join_type': 'INNER',
                            'left_table': 'r1',
                            'left_column': 'emp_id',
                            'right_table': 'e1',
                            'right_column': 'manager_id',
                        }
                    ],
                    'projections': [
                        {'expr': 'e1.id'},
                        {'expr': 'e1.name'},
                        {'expr': 'e1.dept'},
                        {'expr': 'e1.salary'},
                        {'expr': 'r1.depth + 1'},
                    ],
                    'where': ['r1.depth < 5'],
                },
            }
        ],
        'tables': [
            {
                'id': 'c1',
                'resource_kind': 'cte',
                'name': 'org_tree',
                'alias': 'c1',
            }
        ],
        'joins': [],
        'projections': [
            {'expr': 'c1.emp_name', 'alias': 'emp_name'},
            {'expr': 'c1.dept', 'alias': 'dept'},
            {'expr': 'c1.depth', 'alias': 'depth'},
            {'expr': 'c1.salary', 'alias': 'salary'},
            {
                'expr': 'c1.salary',
                'alias': 'dept_rank',
                'aggregate': 'WINDOW',
                'window': {
                    'function': 'ROW_NUMBER',
                    'window_ref': 'w_dept',
                },
            },
            {
                'expr': 'c1.salary',
                'alias': 'running_payroll',
                'aggregate': 'WINDOW',
                'window': {
                    'function': 'SUM',
                    'argument': 'c1.salary',
                    'partition_by': ['c1.dept'],
                    'order_by': ['c1.salary DESC'],
                    'frame_mode': 'ROWS',
                    'frame_start': 'UNBOUNDED PRECEDING',
                    'frame_end': 'CURRENT ROW',
                },
            },
            {
                'expr': 'c1.salary',
                'alias': 'prev_salary',
                'aggregate': 'WINDOW',
                'window': {
                    'function': 'LAG',
                    'argument': 'c1.salary',
                    'offset': 1,
                    'default_expr': '0',
                    'window_ref': 'w_dept',
                },
            },
        ],
        'windows': [
            {
                'name': 'w_dept',
                'partition_by': ['c1.dept'],
                'order_by': ['c1.salary DESC'],
            }
        ],
        'order_by': ['c1.dept ASC', 'dept_rank ASC'],
    }

    # Check Recursive Step canvas scene renders CTE_SELF role
    rec_scene, _, _ = build_visual_query_ddn_scene(
        {**visual_model, 'active_stage': 'cte:c_org:recursive'}, {}, 'sqlite'
    )
    assert any(n['role'] == 'CTE_SELF' for n in rec_scene['nodes'])

    # Check Final SELECT canvas scene renders CTE + WINDOW cards and compiles executable SQL
    final_scene, sql_out, warnings = build_visual_query_ddn_scene(visual_model, {}, 'sqlite')
    assert warnings == []
    assert any(n['role'] == 'CTE' for n in final_scene['nodes'])
    assert any(n['role'] == 'WINDOW' for n in final_scene['nodes'])
    assert 'WITH RECURSIVE' in sql_out
    assert 'ROW_NUMBER() OVER "w_dept"' in sql_out
    assert 'ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW' in sql_out
    assert 'LAG(c1.salary, 1, 0) OVER "w_dept"' in sql_out
    assert 'WINDOW "w_dept" AS (PARTITION BY c1.dept ORDER BY c1.salary DESC)' in sql_out

    # Execute compiled SQL live on SQLite
    with sqlite3.connect(':memory:') as conn:
        conn.executescript(
            """
            CREATE TABLE employees (id INTEGER PRIMARY KEY, name TEXT, manager_id INTEGER, dept TEXT, salary INTEGER);
            INSERT INTO employees VALUES
              (1, 'Ada', NULL, 'Core', 200),
              (2, 'Grace', 1, 'Core', 160),
              (3, 'Linus', 2, 'Core', 140),
              (4, 'Barbara', 1, 'Data', 180);
            """
        )
        rows = conn.execute(sql_out).fetchall()
    assert rows == [
        ('Ada', 'Core', 0, 200, 1, 200, 0),
        ('Grace', 'Core', 1, 160, 2, 360, 200),
        ('Linus', 'Core', 2, 140, 3, 500, 160),
        ('Barbara', 'Data', 1, 180, 1, 180, 0),
    ]

    # Verify SqlSurfaceHostService preserves exact CTE + Window model across visual_builder_from_sql round-trips
    host = SqlSurfaceHostService(
        snippets_store=SqlSnippetsStore(tmp_path / 'snips.db'),
        quick_query_store=QuickQueryStore(tmp_path / 'qq.db'),
        layout_store=SurfaceLayoutStore(tmp_path / 'lay.db'),
    )
    workspace = FakeSqlWorkspaceService()
    server = SimpleNamespace(id=1, user_id=1)
    base = {'surface_id': 'cte-win-rt', 'engine_id': 'sqlite', 'language_profile': 'sqlite-sql'}
    saved = host.dispatch(workspace, server, {**base, 'sub_action': 'visual_builder_scene', 'model': visual_model})
    resynced = host.dispatch(workspace, server, {**base, 'sub_action': 'visual_builder_from_sql', 'sql_text': saved['sql_text']})
    assert resynced['fidelity'] == 'exact'
    assert len(resynced['model']['ctes']) == 1
    assert resynced['model']['ctes'][0]['recursive'] is True
    assert len(resynced['model']['windows']) == 1

