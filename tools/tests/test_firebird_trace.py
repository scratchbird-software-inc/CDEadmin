"""Native configuration boundaries, private streams and durable no-replay."""
from concurrent.futures import ThreadPoolExecutor
import json
from queue import Queue, Empty
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.firebird import trace_config as config
from pgadmin.cdeadmin.providers.firebird import trace_sessions as streams
from pgadmin.cdeadmin.workspace.firebird_trace_actions import TraceActions


@pytest.mark.parametrize('options', [
    {'log_statement_finish': True}, {'print_plan': True}, {'log_errors': True},
    {'log_context': True}, {'include_filter': 'SQL'}, {'log_connections': 1},
    {'capture_sensitive': 'yes'}, {'enabled': True}, {'log_filename': '/other'},
    {'max_arg_count': True}, {'connection_id': -1}, {'max_sql_length': 4294967296},
    {'include_filter': '\nservices {enabled=true}'}, {'include_filter': '"'},
    {'include_filter': '$(root)'},
])
def test_trace_options_refuse_broad_scope_injection_or_unreviewed_sensitive_capture(options):
    with pytest.raises(ValueError):
        config.render('/owned.fdb', options)


def test_native_scope_and_explicit_zero_meanings_are_preserved():
    source = config.render('/dir/own%_[x]{y} 雪#.fdb', {
        'capture_sensitive': True, 'log_statement_finish': True, 'max_sql_length': 0})
    assert 'database\n{\nenabled = false\n}' in source
    assert 'services\n{\nenabled = false\n}' in source
    assert r'own\%\_\[x\]\{{y\}}' in source
    assert 'max_sql_length = 0' in source
    assert 'capture_sensitive' not in source
    for path in ('', '/has"quote.fdb', '/has\nline.fdb', '/$(root).fdb'):
        with pytest.raises(ValueError):
            config.render(path, {})
    assert config.normalize({})['max_sql_length'] > 0
    assert config.normalize({})['max_arg_count'] > 0


def test_every_declared_native_option_has_a_typed_contract():
    options = {key: True for key in config.BOOLEAN_OPTIONS}
    options.update({key: bounds[1] for key, bounds in config.INTEGER_OPTIONS.items()})
    options.update({key: ('335544344' if key.endswith('gds_codes') else 'SELECT%')
                    for key in config.FILTER_OPTIONS}, capture_sensitive=True)
    source = config.render('/owned.fdb', options)
    assert all(key + ' = ' in source for key in options if key != 'capture_sensitive')
    described = {field['field_id'] for field in config.descriptor()['option_fields']}
    assert described == set(options)


def test_verified_attachment_alias_is_an_exact_alternative_not_a_global_pattern():
    source = config.render('/owned/file.fdb', {}, ['REGISTERED%_ALIAS'])
    assert r'(/owned/file.fdb|REGISTERED\%\_ALIAS)' in source
    with pytest.raises(ValueError):
        config.render('/owned/file.fdb', {}, ['one', 'two', 'three'])
    with pytest.raises(ValueError):
        config.render('/owned/file.fdb', {}, [''])


def test_review_claim_is_cross_instance_serialized_and_never_replays_after_failure(tmp_path):
    path = tmp_path / 'actions.json'
    first, second = TraceActions(path), TraceActions(path)
    review = first.review('owner', 'target', 'start', {'options': {}})
    request = {key: review[key] for key in ('review_id', 'review_digest')}
    request['confirmed'] = True
    execute = Mock(side_effect=RuntimeError('do not expose sensitive exception text'))
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda journal: journal.apply(
            'owner', 'target', request, execute), [first, second]))
    execute.assert_called_once()
    assert all(result['state'] in {'unknown_outcome', 'submitted'} for result in results)
    receipt = TraceActions(path).get('owner', 'target', review['review_id'])
    assert receipt['outcome'] == {'state': 'unknown_outcome', 'error_type': 'RuntimeError'}
    assert 'sensitive exception' not in path.read_text()
    for owner, binding in [('other', 'target'), ('owner', 'other')]:
        with pytest.raises(ValueError):
            first.get(owner, binding, review['review_id'])
    with pytest.raises(ValueError):
        first.apply('owner', 'target', {**request, 'confirmed': False}, execute)
    with pytest.raises(ValueError):
        first.apply('owner', 'target', {**request, 'review_digest': 'wrong'}, execute)


def test_captured_output_is_not_durable_and_process_loss_is_not_a_live_session(tmp_path):
    journal = TraceActions(tmp_path / 'actions.json')
    with pytest.raises(ValueError):
        journal.finish_session('o', 'b', {'trace_id': 't', 'lines': ['private']})
    journal.finish_session(
        'o', 'b', {'trace_id': 't', 'state': 'started', 'cleanup_confirmed': False})
    assert journal.session('o', 'b', 't')['state'] == 'unknown_after_process_loss'
    journal.finish_session(
        'o', 'b', {'trace_id': 't', 'state': 'stopped', 'cleanup_confirmed': True})
    journal.finish_session(
        'o', 'b', {'trace_id': 't', 'state': 'started', 'cleanup_confirmed': False})
    assert journal.session('o', 'b', 't')['state'] == 'stopped'
    assert not journal.session('o', 'b', 't')['output_available']


class Producer:
    def __init__(self):
        self.queue = Queue()
        self.trace = SimpleNamespace(start=Mock(return_value=17))

    def readline_timed(self, _timeout):
        try:
            return self.queue.get(timeout=0.01)
        except Empty:
            return object()

    def is_running(self): return True


def start(manager, owner='owner', binding='target', release=None, on_finish=None):
    producer = Producer()
    controller = SimpleNamespace(trace=SimpleNamespace(
        stop=Mock(), suspend=Mock(), resume=Mock(), sessions={17: SimpleNamespace(flags=['active'])}))
    handles = iter([producer, controller])
    release = release or Mock(return_value=True)
    result = manager.start(owner, binding, {'database': '/owned.fdb'}, {}, 'Owned',
                           lambda: next(handles), release, on_finish)
    return result, producer, controller, release


def test_stream_controls_output_gap_privacy_and_native_release(monkeypatch):
    monkeypatch.setattr(streams, 'MAX_LINES', 2)
    manager = streams.TraceSessions()
    finished = Mock()
    result, producer, controller, release = start(manager, on_finish=finished)
    identity = result['trace_id']
    try:
        for value in ('one', 'two', 'three'):
            producer.queue.put(value)
        deadline = time.monotonic() + 2
        while manager.poll('owner', 'target', identity)['last_sequence'] < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
        page = manager.poll('owner', 'target', identity)
        assert page['delivery_gap'] and [row['text'] for row in page['lines']] == ['two', 'three']
        assert page['next_sequence'] == 3 and page['dropped_lines'] == 1
        assert manager.listing('owner', 'target')['items'][0]['native_list_observation']['present']
        assert manager.listing('other', 'target')['items'] == []
        with pytest.raises(ValueError):
            manager.poll('other', 'target', identity)
        with pytest.raises(ValueError):
            manager.poll('owner', 'target', identity, after=4)
        assert manager.control('owner', 'target', identity, 'suspend')['state'] == 'suspended'
        assert manager.control('owner', 'target', identity, 'resume')['state'] == 'started'
        terminal = manager.control('owner', 'target', identity, 'stop')
        assert terminal['native_stop_acknowledged'] and terminal['cleanup_confirmed']
        controller.trace.stop.assert_called_once_with(session_id=17)
        release.assert_called_once()
        assert manager.control('owner', 'target', identity, 'forget')['state'] == 'forgotten'
    finally:
        assert manager.close()


def test_plugin_error_and_clipped_unicode_are_reported_without_capture_success():
    manager = streams.TraceSessions()
    result, producer, controller, release = start(manager)
    producer.queue.put('雪' * 20000)
    producer.queue.put('Error creating trace session for database')
    item = manager._get('owner', 'target', result['trace_id'])
    assert item.done.wait(2)
    page = manager.poll('owner', 'target', result['trace_id'])
    assert page['state'] == 'plugin_error' and page['plugin_diagnostic_observed']
    assert page['lines'][0]['truncated'] and len(page['lines'][0]['text'].encode()) <= 32768
    assert not page['capture_success_inferred']
    assert manager.close()


def test_idle_expiry_and_failed_cleanup_are_owned_for_explicit_release(monkeypatch):
    monkeypatch.setattr(streams, 'IDLE_SECONDS', -1)
    manager = streams.TraceSessions()
    release = Mock(side_effect=[RuntimeError('failed close'), True])
    result, producer, controller, release = start(manager, release=release)
    item = manager._get('owner', 'target', result['trace_id'])
    assert item.done.wait(2)
    assert item.snapshot()['state'] == 'cleanup_unknown'
    with pytest.raises(ValueError):
        manager.control('owner', 'target', item.identity, 'forget')
    assert manager.control('owner', 'target', item.identity, 'release')['cleanup_confirmed']
    assert controller.trace.stop.call_count == 1
    assert manager.close()


def test_services_trace_and_system_audit_config_contracts(tmp_path):
    with pytest.raises(ValueError, match='service_scope_confirmed'):
        config.render_services({'log_services': True})
    with pytest.raises(ValueError, match='sensitive-capture'):
        config.render_services({'service_scope_confirmed': True, 'log_service_query': True})
    svc_cfg = config.render_services({
        'service_scope_confirmed': True,
        'capture_sensitive': True,
        'log_services': True,
        'log_service_query': True,
        'include_filter': 'Database Stats',
    })
    assert 'database\n{\nenabled = false\n}' in svc_cfg
    assert 'services\n{\nenabled = true' in svc_cfg
    assert 'log_service_query = true' in svc_cfg
    assert 'include_filter = "Database Stats"' in svc_cfg

    audit_dir = tmp_path / 'audit'
    audit_dir.mkdir()
    db_log = audit_dir / 'db_audit.log'
    svc_log = audit_dir / 'svc_audit.log'
    rendered_audit = config.render_system_audit({
        'database': '/owned/db.fdb',
        'database_log_filename': str(db_log),
        'database_max_log_size': 50,
        'database_options': {'log_connections': True, 'log_transactions': True},
        'enable_services': True,
        'services_log_filename': str(svc_log),
        'services_max_log_size': 25,
        'service_options': {'service_scope_confirmed': True, 'log_services': True},
    }, audit_dir)
    assert f'log_filename = "{db_log}"' in rendered_audit
    assert f'log_filename = "{svc_log}"' in rendered_audit
    assert 'max_log_size = 50' in rendered_audit

    for bad_path in (
        str(tmp_path / 'outside.log'),
        str(audit_dir / r'sub\1.log'),
        'relative.log',
        str(audit_dir / 'bad{brace}.log'),
    ):
        with pytest.raises(ValueError):
            config.render_system_audit({
                'all_databases': True,
                'database_log_filename': bad_path,
            }, audit_dir)

    db_log.write_text('line1\nline2\n' + ('x' * 33000) + '\n', encoding='utf-8')
    tail = config.read_audit_log_tail(str(db_log), audit_dir)
    assert tail['present'] and len(tail['lines']) == 3
    assert tail['lines'][2]['truncated'] is True
    assert tail['output_persisted'] is False


def test_external_native_session_inventory_and_reviewed_controls():
    import datetime
    manager = streams.TraceSessions()
    result, _producer, _controller, _release = start(manager)
    try:
        server = SimpleNamespace(trace=SimpleNamespace(
            sessions={
                17: SimpleNamespace(id=17, name='Owned', user='SYSDBA',
                                    timestamp=datetime.datetime(2026, 11, 18, 12, 0, 0),
                                    flags=['active', ' trace']),
                23: SimpleNamespace(id=23, name='ExtCli', user='SYSDBA',
                                    timestamp=datetime.datetime(2026, 11, 18, 12, 5, 0),
                                    flags=['active', ' trace']),
                31: SimpleNamespace(id=31, name='Audit', user='SYSDBA',
                                    timestamp=datetime.datetime(2026, 11, 18, 11, 0, 0),
                                    flags=['active', ' audit']),
            },
            suspend=Mock(return_value='Trace session ID 23 paused'),
            resume=Mock(return_value='Trace session ID 23 resumed'),
            stop=Mock(return_value='Trace session ID 23 stopped'),
        ))
        listing = {row['native_session_id']: row
                   for row in manager.list_native_sessions('owner', 'target', server)['items']}
        assert listing[17]['managed_by_workspace'] is True
        assert listing[17]['managed_trace_id'] == result['trace_id']
        assert listing[23]['managed_by_workspace'] is False
        assert listing[31]['system_audit'] is True

        # Managed and system-audit sessions refuse external session controls.
        with pytest.raises(ValueError, match='managed by this workspace'):
            manager.observe_external_target('owner', 'target', server, 17)
        with pytest.raises(ValueError, match='System audit'):
            manager.observe_external_target('owner', 'target', server, 31)

        observed = manager.observe_external_target('owner', 'target', server, 23)
        assert manager.control_external('owner', 'target', server, observed, 'suspend_external')['state'] == 'suspended'
        assert manager.control_external('owner', 'target', server, observed, 'resume_external')['state'] == 'started'

        # Reused numeric ID with different start timestamp is rejected pre-dispatch.
        stale = {**observed, 'started_at': '2026-11-18T12:06:00'}
        rejected = manager.control_external('owner', 'target', server, stale, 'stop_external')
        assert rejected['state'] == 'rejected' and rejected['native_dispatched'] is False
        server.trace.stop.assert_not_called()

        stopped = manager.control_external('owner', 'target', server, observed, 'stop_external')
        assert stopped['state'] == 'stopped' and stopped['native_acknowledged'] is True
        server.trace.stop.assert_called_once_with(session_id=23)
    finally:
        assert manager.close()

