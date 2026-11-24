"""Tests for DataSurfaceHostService & SurfaceLayoutStore (Surface 1: Browse & Edit Data)."""

from __future__ import annotations

import copy
from types import SimpleNamespace
import pytest

from pgadmin.cdeadmin.workspace.data_surface_host import (
    DataSurfaceHostService,
    SurfaceLayoutStore,
)


class FakeFirebirdWorkspaceService:
    """Deterministic fake workspace service simulating Firebird always-in-transaction semantics."""

    def __init__(self, rows: list[dict] | None = None, *, incomplete: bool = False):
        self.sessions_opened: list[dict] = []
        self.sessions_closed: list[str] = []
        self.tx_actions: list[tuple[str, str]] = []
        self.applied_plans: list[dict] = []
        self.read_calls = 0
        self.fail_on_apply_call: int | None = None
        self.incomplete = incomplete
        self.columns = [
            {
                'name': 'ID',
                'native_type': 'INTEGER',
                'nullable': False,
                'key': True,
                'editable': False,
                'insertable': True,
                'comment': 'Primary account identifier',
            },
            {
                'name': 'ACCOUNT_NAME',
                'native_type': 'VARCHAR(120)',
                'nullable': False,
                'key': False,
                'editable': True,
                'insertable': True,
                'domain_name': 'DM_NAME',
                'comment': 'Display ledger title',
            },
            {
                'name': 'BALANCE',
                'native_type': 'NUMERIC(14,2)',
                'nullable': True,
                'key': False,
                'editable': True,
                'insertable': True,
            },
            {
                'name': 'IS_ACTIVE',
                'native_type': 'BOOLEAN',
                'nullable': False,
                'key': False,
                'editable': True,
                'insertable': True,
            },
            {
                'name': 'METADATA_JSON',
                'native_type': 'BLOB SUB_TYPE TEXT',
                'nullable': True,
                'key': False,
                'editable': True,
                'insertable': True,
            },
        ]
        self.table_rows = (
            copy.deepcopy(rows)
            if rows is not None
            else [
                {
                    'identity_token': 'pk:1',
                    'values': {
                        'ID': 1,
                        'ACCOUNT_NAME': 'Cash On Hand',
                        'BALANCE': 1250.5,
                        'IS_ACTIVE': True,
                        'METADATA_JSON': '{"currency":"CAD","notes":"Main vault"}',
                    },
                },
                {
                    'identity_token': 'pk:2',
                    'values': {
                        'ID': 2,
                        'ACCOUNT_NAME': 'Accounts Receivable',
                        'BALANCE': 4800.0,
                        'IS_ACTIVE': True,
                        'METADATA_JSON': None,
                    },
                },
                {
                    'identity_token': 'pk:3',
                    'values': {
                        'ID': 3,
                        'ACCOUNT_NAME': 'Dormant Reserve',
                        'BALANCE': None,
                        'IS_ACTIVE': False,
                        'METADATA_JSON': '{"archived":true}',
                    },
                },
            ]
        )
        self._plans: dict[str, dict] = {}
        self._tx_seq = 100

    def open_session(
        self,
        server,
        language_profile,
        database_target_id=None,
        session_purpose=None,
    ):
        sid = f'fb-sess-{len(self.sessions_opened) + 1}'
        self.sessions_opened.append({
            'session_id': sid,
            'language_profile': language_profile,
            'database_target_id': database_target_id,
            'session_purpose': session_purpose,
        })
        return {'session_id': sid}

    def close_session(self, server, session_id, database_target_id=None):
        self.sessions_closed.append(session_id)
        return {'provider_closed': True, 'session_id': session_id}

    def transaction(self, server, session_id, database_target_id=None):
        # Firebird is ALWAYS in a transaction!
        return {
            'session_id': session_id,
            'in_transaction': True,
            'transaction_id': self._tx_seq,
            'provider_payload': {'in_transaction': True, 'autocommit': False},
        }

    def transaction_action(
        self, server, session_id, action, database_target_id=None
    ):
        self.tx_actions.append((session_id, action))
        self._tx_seq += 1
        # Even after commit or rollback, Firebird starts a new transaction immediately
        return {
            'session_id': session_id,
            'in_transaction': True,
            'transaction_id': self._tx_seq,
            'provider_payload': {'in_transaction': True, 'autocommit': False},
        }

    def read_visual_admin_rows(self, server, payload):
        self.read_calls += 1
        limit = int(payload.get('limit') or 200)
        sliced = copy.deepcopy(self.table_rows[:limit])
        return {
            'columns': copy.deepcopy(self.columns),
            'rows': sliced,
            'editable': True,
            'identity_policy': 'primary-key',
            'row_operations': ['insert', 'update', 'delete'],
            'continuation': 'more-cursor-1' if self.incomplete else None,
        }

    def cancel_visual_admin_rows(self, server, payload):
        return {'cancelled': True}

    def validate_visual_admin(self, server, req):
        return {'valid': True, 'issues': []}

    def plan_visual_admin(self, server, req):
        pid = f'plan-{len(self._plans) + 1}'
        op = req['operation_id']
        tname = req['target_resource'].get('display_name', 'ACCOUNT')
        sql = f'-- {op.upper()} {tname}'
        if op == 'update':
            changes = req['draft'].get('changes') or {}
            sets = ', '.join(f'"{k}" = {v!r}' for k, v in changes.items())
            sql = f'UPDATE "{tname}" SET {sets} WHERE ID_TOKEN = {req["draft"]["selector"]["identity_token"]!r}'
        elif op == 'insert':
            vals = req['draft'].get('values') or {}
            cols = ', '.join(f'"{k}"' for k in vals)
            sql = f'INSERT INTO "{tname}" ({cols}) VALUES (...)'
        elif op == 'delete':
            sql = f'DELETE FROM "{tname}" WHERE ID_TOKEN = {req["draft"]["selector"]["identity_token"]!r}'
        plan_obj = {
            'plan_id': pid,
            'plan_digest': f'digest-{pid}',
            'state': 'ready',
            'execution_available': True,
            'statements': [{'sql': sql}],
            '_req': copy.deepcopy(req),
        }
        self._plans[pid] = plan_obj
        return plan_obj

    def apply_visual_admin(self, server, payload):
        call_num = len(self.applied_plans) + 1
        if self.fail_on_apply_call == call_num:
            raise RuntimeError('violation of PRIMARY or UNIQUE KEY constraint')
        plan_obj = self._plans[payload['plan_id']]
        req = plan_obj['_req']
        op = req['operation_id']
        if op == 'update':
            tok = req['draft']['selector']['identity_token']
            for r in self.table_rows:
                if r['identity_token'] == tok:
                    r['values'].update(req['draft']['changes'])
        elif op == 'insert':
            vals = dict(req['draft']['values'])
            new_id = vals.get('ID') or (len(self.table_rows) + 1)
            vals['ID'] = new_id
            self.table_rows.append({
                'identity_token': f'pk:{new_id}',
                'values': vals,
            })
        elif op == 'delete':
            tok = req['draft']['selector']['identity_token']
            self.table_rows = [
                r for r in self.table_rows if r['identity_token'] != tok
            ]
        self.applied_plans.append(req)
        return {'accepted': True}


def _make_server():
    return SimpleNamespace(id=7, user_id=1)


def _target():
    return {
        'resource_id': 'table:ACCOUNT',
        'resource_kind': 'table',
        'display_name': 'ACCOUNT',
        'name': 'ACCOUNT',
    }


def test_host_buffering_smart_sort_filter_and_companion_views(tmp_path):
    store = SurfaceLayoutStore(tmp_path / 'layouts.db')
    host = DataSurfaceHostService(layout_store=store)
    ws = FakeFirebirdWorkspaceService()
    srv = _make_server()

    opened = host.dispatch(
        ws,
        srv,
        {
            'surface_id': 'ds-tab-1',
            'surface_action': 'open',
            'target_resource': _target(),
            'database_target_id': 'frappe_suite.fdb',
            'language_profile': 'firebird-sql',
            'engine_id': 'firebird',
        },
    )

    assert opened['total_buffered_rows'] == 3
    assert opened['complete_in_buffer'] is True
    # Small complete dataset defaults to local host-cached sort
    assert opened['sort_execution'] == 'local'
    # Firebird opened a transaction to read, MUST NOT count as uncommitted activity!
    assert opened['has_uncommitted_activity'] is False
    assert opened['metrics_view']['transaction']['has_uncommitted_activity'] is False
    assert ws.read_calls == 1

    # Companion Fields view includes server + client mapping + domain + comment
    fields_by_name = {f['name']: f for f in opened['fields_grid']}
    assert fields_by_name['ACCOUNT_NAME']['domain_type'] == 'DM_NAME'
    assert fields_by_name['ACCOUNT_NAME']['comment'] == 'Display ledger title'
    assert fields_by_name['BALANCE']['default_alignment'] == 'right'
    assert fields_by_name['METADATA_JSON']['is_complex'] is True

    # Local sort & filter do NOT re-query database (read_calls remains 1!)
    sorted_resp = host.dispatch(
        ws,
        srv,
        {
            'surface_id': 'ds-tab-1',
            'surface_action': 'sort_filter',
            'sorts': [{'column': 'ACCOUNT_NAME', 'direction': 'asc'}],
            'filters': [{'column': 'IS_ACTIVE', 'op': 'eq', 'value': 'True'}],
        },
    )
    assert ws.read_calls == 1
    assert sorted_resp['sql_view']['is_local_sort_or_filter'] is True
    assert [r['values']['ACCOUNT_NAME'] for r in sorted_resp['rows']] == [
        'Accounts Receivable',
        'Cash On Hand',
    ]

    # Column profile computes stats on host
    prof = host.dispatch(
        ws,
        srv,
        {
            'surface_id': 'ds-tab-1',
            'surface_action': 'column_profile',
            'column': 'BALANCE',
        },
    )
    assert prof['total_rows'] == 2
    assert prof['distinct_count'] == 2


def test_large_incomplete_dataset_defaults_to_server_sort(tmp_path):
    store = SurfaceLayoutStore(tmp_path / 'layouts.db')
    host = DataSurfaceHostService(layout_store=store)
    ws = FakeFirebirdWorkspaceService(incomplete=True)
    srv = _make_server()

    opened = host.dispatch(
        ws,
        srv,
        {
            'surface_id': 'ds-large',
            'surface_action': 'open',
            'target_resource': _target(),
            'language_profile': 'firebird-sql',
            'engine_id': 'firebird',
            'max_rows': 3,
        },
    )
    assert opened['complete_in_buffer'] is False
    assert opened['retrieval_limited'] is True
    assert opened['sort_execution'] == 'server'


def test_firebird_batch_staging_commit_rollback_and_activity_tracking(tmp_path):
    store = SurfaceLayoutStore(tmp_path / 'layouts.db')
    host = DataSurfaceHostService(layout_store=store)
    ws = FakeFirebirdWorkspaceService()
    srv = _make_server()

    host.dispatch(
        ws,
        srv,
        {
            'surface_id': 'ds-fb-tx',
            'surface_action': 'open',
            'target_resource': _target(),
            'database_target_id': 'frappe_suite.fdb',
            'language_profile': 'firebird-sql',
            'engine_id': 'firebird',
        },
    )

    # Stage an update (Accept row with autocommit=False)
    staged = host.dispatch(
        ws,
        srv,
        {
            'surface_id': 'ds-fb-tx',
            'surface_action': 'stage_row',
            'op': 'update',
            'base_row_index': 0,
            'identity_token': 'pk:1',
            'changes': {'BALANCE': 9999.25},
        },
    )
    assert staged['has_uncommitted_activity'] is True
    assert staged['metrics_view']['transaction']['staged_total'] == 1
    assert staged['rows'][0]['stage_state'] == 'updated'
    assert staged['rows'][0]['values']['BALANCE'] == 9999.25
    assert len(staged['sql_view']['staged_sql']) == 1
    assert 'UPDATE "ACCOUNT"' in staged['sql_view']['staged_sql'][0]['sql']

    # Re-opening on tab switch preserves staged mutations without wiping!
    reopened = host.dispatch(
        ws,
        srv,
        {
            'surface_id': 'ds-fb-tx',
            'surface_action': 'open',
            'target_resource': _target(),
        },
    )
    assert reopened['has_uncommitted_activity'] is True
    assert reopened['rows'][0]['values']['BALANCE'] == 9999.25
    assert ws.read_calls == 1

    # Commit batch flushes DML, executes Firebird COMMIT, and resets activity to False!
    committed = host.dispatch(
        ws,
        srv,
        {
            'surface_id': 'ds-fb-tx',
            'surface_action': 'commit_batch',
        },
    )
    assert committed['has_uncommitted_activity'] is False
    assert committed['metrics_view']['transaction']['staged_total'] == 0
    assert committed['rows'][0]['values']['BALANCE'] == 9999.25
    assert ('fb-sess-1', 'commit') in ws.tx_actions

    # Stage another update + insert, then Rollback -> resets activity to False!
    host.dispatch(
        ws,
        srv,
        {
            'surface_id': 'ds-fb-tx',
            'surface_action': 'stage_row',
            'op': 'insert',
            'changes': {'ID': 4, 'ACCOUNT_NAME': 'Temp Draft', 'IS_ACTIVE': True},
        },
    )
    rolled = host.dispatch(
        ws,
        srv,
        {
            'surface_id': 'ds-fb-tx',
            'surface_action': 'rollback_batch',
        },
    )
    assert rolled['has_uncommitted_activity'] is False
    assert rolled['metrics_view']['transaction']['staged_total'] == 0
    assert len(rolled['rows']) == 3
    assert ('fb-sess-1', 'rollback') in ws.tx_actions


def test_partial_batch_commit_failure_preserves_dirty_tx_and_jumpback_coords(tmp_path):
    store = SurfaceLayoutStore(tmp_path / 'layouts.db')
    host = DataSurfaceHostService(layout_store=store)
    ws = FakeFirebirdWorkspaceService()
    ws.fail_on_apply_call = 2  # 1st row applies on session, 2nd row fails!
    srv = _make_server()

    host.dispatch(
        ws,
        srv,
        {
            'surface_id': 'ds-partial',
            'surface_action': 'open',
            'target_resource': _target(),
            'language_profile': 'firebird-sql',
            'engine_id': 'firebird',
        },
    )
    host.dispatch(
        ws,
        srv,
        {
            'surface_id': 'ds-partial',
            'surface_action': 'stage_row',
            'op': 'update',
            'base_row_index': 0,
            'identity_token': 'pk:1',
            'changes': {'ACCOUNT_NAME': 'Updated First'},
        },
    )
    host.dispatch(
        ws,
        srv,
        {
            'surface_id': 'ds-partial',
            'surface_action': 'stage_row',
            'op': 'update',
            'base_row_index': 1,
            'identity_token': 'pk:2',
            'changes': {'ACCOUNT_NAME': 'Updated First'},
        },
    )

    with pytest.raises(RuntimeError, match='UNIQUE KEY'):
        host.dispatch(
            ws,
            srv,
            {'surface_id': 'ds-partial', 'surface_action': 'commit_batch'},
        )

    # Even if user reverts the remaining staged row-1, row-0 already mutated the Firebird tx!
    after_revert = host.dispatch(
        ws,
        srv,
        {
            'surface_id': 'ds-partial',
            'surface_action': 'revert_row',
            'row_key': 'row-1',
        },
    )
    assert after_revert['metrics_view']['transaction']['staged_total'] == 0
    assert after_revert['has_uncommitted_activity'] is True
    err_msgs = [m for m in after_revert['messages'] if m['severity'] == 'error']
    assert len(err_msgs) == 1
    assert err_msgs[0]['row_index'] == 1
    assert err_msgs[0]['column_name'] == 'ACCOUNT_NAME'


def test_specific_layout_and_shareable_templates(tmp_path):
    store = SurfaceLayoutStore(tmp_path / 'layouts.db')
    host = DataSurfaceHostService(layout_store=store)
    ws = FakeFirebirdWorkspaceService()
    srv = _make_server()

    host.dispatch(
        ws,
        srv,
        {
            'surface_id': 'ds-layout',
            'surface_action': 'open',
            'target_resource': _target(),
            'database_target_id': 'frappe_suite.fdb',
            'language_profile': 'firebird-sql',
            'engine_id': 'firebird',
        },
    )

    host.dispatch(
        ws,
        srv,
        {
            'surface_id': 'ds-layout',
            'surface_action': 'save_layout',
            'scope': 'specific',
            'layout': {'displayMode': 'hybrid', 'booleanFormat': 'YN'},
        },
    )
    host.dispatch(
        ws,
        srv,
        {
            'surface_id': 'ds-layout',
            'surface_action': 'save_layout',
            'scope': 'template',
            'template_name': 'Compact Accounting Grid',
            'layout': {'displayMode': 'mini_forms', 'booleanFormat': 'TF'},
        },
    )

    tpls = host.dispatch(ws, srv, {'surface_action': 'list_templates'})['templates']
    assert len(tpls) == 1
    assert tpls[0]['name'] == 'Compact Accounting Grid'

    # Opening a new surface for the same object restores saved_specific_layout
    fresh = host.dispatch(
        ws,
        srv,
        {
            'surface_id': 'ds-layout-2',
            'surface_action': 'open',
            'target_resource': _target(),
            'database_target_id': 'frappe_suite.fdb',
            'language_profile': 'firebird-sql',
            'engine_id': 'firebird',
        },
    )
    assert fresh['saved_specific_layout']['displayMode'] == 'hybrid'
    assert fresh['saved_specific_layout']['booleanFormat'] == 'YN'


def test_export_formatted_selection_scope_slices_rows_and_columns(tmp_path):
    import base64

    store = SurfaceLayoutStore(tmp_path / 'layouts.db')
    host = DataSurfaceHostService(layout_store=store)
    ws = FakeFirebirdWorkspaceService()
    srv = _make_server()

    host.dispatch(
        ws,
        srv,
        {
            'surface_id': 'ds-export-sel',
            'surface_action': 'open',
            'target_resource': _target(),
            'database_target_id': 'frappe_suite.fdb',
            'language_profile': 'firebird-sql',
            'engine_id': 'firebird',
        },
    )

    # 1. Row x Column intersection selection payload
    res_slice = host.dispatch(
        ws,
        srv,
        {
            'surface_id': 'ds-export-sel',
            'surface_action': 'export_formatted',
            'format': 'csv',
            'filename': 'account_slice',
            'settings': {
                'scope': 'selection',
                'selected_column_names': ['ACCOUNT_NAME', 'BALANCE'],
                'selected_rows_payload': [
                    {'values': {'ACCOUNT_NAME': 'Cash On Hand', 'BALANCE': 1500.5}},
                ],
            },
        },
    )
    csv_text = base64.b64decode(res_slice['content_base64']).decode('utf-8')
    assert csv_text.splitlines() == [
        'ACCOUNT_NAME,BALANCE',
        'Cash On Hand,1500.5',
    ]

    # 2. Full-column selection across all filtered host-buffered rows (no selected_rows_payload)
    res_cols = host.dispatch(
        ws,
        srv,
        {
            'surface_id': 'ds-export-sel',
            'surface_action': 'export_formatted',
            'format': 'csv',
            'filename': 'account_cols',
            'settings': {
                'scope': 'selection',
                'selected_column_names': ['ACCOUNT_NAME'],
            },
        },
    )
    col_csv = base64.b64decode(res_cols['content_base64']).decode('utf-8')
    lines = col_csv.splitlines()
    assert lines[0] == 'ACCOUNT_NAME'
    assert len(lines) == 4


def test_column_comment_enrichment_from_child_resources_and_128_char_cap(tmp_path):
    store = SurfaceLayoutStore(tmp_path / 'layouts.db')
    host = DataSurfaceHostService(layout_store=store)
    srv = _make_server()
    huge_blob_comment = 'B' * 400

    class ChildCommentWorkspace(FakeFirebirdWorkspaceService):
        def inspect_resource(self, _server, _req):
            return {'resource_id': 'table:ACCOUNT', 'extensions': {'firebird': {'native': {}}}}

        def list_resources(self, _server, _req):
            return {
                'items': [
                    {
                        'resource_id': 'column:ACCOUNT:BALANCE',
                        'resource_kind': 'column',
                        'display_name': 'BALANCE',
                        'extensions': {
                            'firebird': {
                                'native': {
                                    'description': huge_blob_comment,
                                }
                            }
                        },
                    }
                ]
            }

    ws = ChildCommentWorkspace()
    opened = host.dispatch(
        ws,
        srv,
        {
            'surface_id': 'ds-blob-comment',
            'surface_action': 'open',
            'target_resource': _target(),
            'database_target_id': 'frappe_suite.fdb',
            'language_profile': 'firebird-sql',
            'engine_id': 'firebird',
        },
    )
    cols_by_name = {c['name']: c for c in opened['columns']}
    assert cols_by_name['BALANCE']['comment'] == 'B' * 128
    assert len(cols_by_name['BALANCE']['comment']) == 128


