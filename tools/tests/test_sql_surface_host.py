"""Tests for SqlSurfaceHostService, Terminator Parser, Multi-Tag Snippets, Quick Queries,
Universal Object Script Generation, DDN Visual Builder Scene, and Multi-Format Exports (Surface 2).
"""

from __future__ import annotations

import base64
import copy
import io
import json
import zipfile
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
    assert 'FROM "GET_EMP_PROJ"(:EMP_NO) AS "p1"' in sql_proc
    # Firebird 0-arg selectable procedure MUST NOT emit empty `()`
    assert 'CROSS JOIN "ALL_LANGS" AS "p2"' in sql_proc

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
        'surface_id': 'ss-1',
        'sql_source': 'SELECT 1 FROM RDB$DATABASE; SELECT 2 FROM RDB$DATABASE;',
    })
    assert st_multi['result_count'] == 2
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
