"""One asynchronous script owner with explicit per-statement outcomes."""
import copy
import json

from .error_diagnostics import diagnostic_flag, status_codes
from .materialized_budget import Budget
from .query_dialect import requested_dialect
from .script_cursor import ScriptCursor
from .transaction_sql import starts_transaction, transaction_command


class ScriptExecution:
    def __init__(self, client, query, state, request):
        self.client, self.query, self.state = client, query, state
        self.handle = query.handle
        self.request = request
        self.dialect = requested_dialect(request) or self.handle.sql_dialect
        self.bail = True
        self.autoddl = False
        self.budget = Budget()
        self.current_cursor = None
        self.records = []
        self.failed = False
        self.unknown = False
        self.cancelled = False

    def ddl_transaction(self):
        from firebird.driver import DefaultAction, Isolation, tpb
        if self.state.script_ddl_transaction is None:
            factory = self.handle.transaction_manager
            self.state.script_ddl_transaction = factory(
                tpb(Isolation.READ_COMMITTED_NO_RECORD_VERSION),
                default_action=DefaultAction.ROLLBACK)
        transaction = self.state.script_ddl_transaction
        if not transaction.is_active():
            transaction.begin()
        return transaction

    def cursor(self, request):
        if self.autoddl:
            result = ScriptCursor(self, self.dialect)
        else:
            result = self.client._ordinary_query_cursor(self.handle, request)
            native = getattr(result, 'cursor', result)
            native.shared_materialization_budget = self.budget
        self.current_cursor = result
        return result

    def snapshot(self, *, results=False):
        with self.state.lock:
            return {'entries': [copy.deepcopy(record) if results else {
                key: value for key, value in record.items() if key != 'result'}
                for record in self.records],
                'total_entries': len(self.query.script_plan),
                'had_errors': self.failed,
                'stopped_before_end': any(record['state'] == 'not_run'
                                          for record in self.records),
                'cancel_requested': self.query.cancellation_attempted,
                'unknown_outcome': self.unknown,
                'implicit_user_commit_requested': False}

    def update(self, record, **values):
        with self.state.lock:
            record.update(values)

    def mark_unknown(self):
        with self.state.lock:
            self.unknown = True
            for record in self.records:
                if record['state'] == 'running':
                    record['state'] = 'unknown'
            for index in range(len(self.records), len(self.query.script_plan)):
                entry = self.query.script_plan[index]
                self.records.append({'index': index + 1, 'line': entry.line,
                                     'kind': entry.kind, 'state': 'not_run'})

    def live(self):
        try:
            self.handle.ping()
            return True
        except Exception:
            self.state.attachment_liveness_failed = True
            self.unknown = True
            return False

    def auxiliary_finish(self, action):
        transaction = self.state.script_ddl_transaction
        if transaction is None or not transaction.is_active():
            return None
        receipt = {'action': action, 'scope': 'auxiliary-ddl',
                   'native_call_made': True, 'observation': 'unavailable'}
        try:
            getattr(transaction, action)()
            receipt['observation'] = 'driver method returned'
        except Exception as error:
            receipt['native_status_codes'] = list(status_codes(error))
            self.unknown = True
            if action == 'commit':
                receipt['rollback_after_failed_commit'] = (
                    self.auxiliary_finish('rollback'))
            else:
                self.state.result_cleanup_failed = True
            return receipt
        if not self.live():
            receipt['observation'] = 'attachment liveness unavailable'
        return receipt

    @staticmethod
    def error(error):
        return {'error_type': type(error).__name__,
                'native_status_codes': list(status_codes(error)),
                'native_execution_completed': diagnostic_flag(
                    error, 'native_execution_completed'),
                'message': 'Statement completion is not a rollback receipt. '
                'Prior or procedure work may remain pending. Inspect the '
                'transaction before committing or retrying.'}

    def run(self):
        with self.state.lock:
            self.state.script_context = self
            self.query.script_execution = self
        stop = False
        try:
            for index, entry in enumerate(self.query.script_plan, 1):
                record = {'index': index, 'line': entry.line,
                          'kind': entry.kind, 'state': 'not_run'}
                with self.state.lock:
                    self.records.append(record)
                    self.cancelled |= self.query.cancellation_attempted
                    if stop or self.cancelled:
                        continue
                    record['state'] = 'running'
                self.current_cursor = None
                try:
                    self.budget.reserve(4096, 10)
                    if entry.kind == 'dialect':
                        self.dialect = entry.value
                    elif entry.kind == 'bail':
                        self.bail = entry.value
                    elif entry.kind == 'autoddl':
                        self.autoddl = entry.value
                    elif entry.kind == 'sql':
                        payload = copy.deepcopy(self.request)
                        payload['source'] = entry.source
                        payload['parameters'] = []
                        payload['output_policy'] = {
                            **(payload.get('output_policy') or {}),
                            'client_sql_dialect': self.dialect,
                            'firebird_script': False}
                        token = self.client._execute_sql(self.handle, payload)
                        native = self.client._describe_native_token(token)
                        # Script entries are not separately published tokens.
                        # Keep ownership metadata for cleanup, not row copies.
                        token.rows = []
                        token.columns = ()
                        self.budget.reserve(len(json.dumps(
                            native['schema'], ensure_ascii=True)) * 6)
                        self.update(record, result=native)
                        if (isinstance(self.current_cursor, ScriptCursor) and
                                self.current_cursor.automatic_ddl):
                            self.update(record, ddl_transaction=(
                                self.auxiliary_finish('commit')))
                        if (transaction_command(entry.source) is not None or
                                starts_transaction(entry.source)):
                            self.live()
                    with self.state.lock:
                        record['state'] = ('unknown' if self.unknown else
                                           'succeeded')
                    stop = self.unknown
                except Exception as error:
                    self.failed = True
                    self.cancelled |= 335544794 in status_codes(error)
                    self.update(record, error=self.error(error))
                    # Cleanup uncertainty always overrides BAIL OFF.
                    unsafe = (self.state.result_cleanup_failed or
                              self.budget.failed or not self.live())
                    if (isinstance(self.current_cursor, ScriptCursor) and
                            self.current_cursor.automatic_ddl and not unsafe):
                        self.update(record, ddl_transaction=(
                            self.auxiliary_finish('commit')))
                    if transaction_command(entry.source) is not None:
                        self.unknown = True
                    with self.state.lock:
                        record['state'] = ('unknown' if self.unknown else
                                           'cancelled' if self.cancelled else
                                           'failed')
                    stop = (self.bail or unsafe or self.unknown or
                            self.cancelled)
                except BaseException as error:
                    self.unknown = True
                    self.failed = True
                    self.state.worker_interrupted = True
                    with self.state.lock:
                        record['state'] = 'unknown'
                        record['error'] = self.error(error)
                    stop = True
        finally:
            try:
                cleanup = self.auxiliary_finish('rollback')
            finally:
                with self.state.lock:
                    self.state.script_context = None
        execution_state = ('cancelled' if self.cancelled else
                           'failed' if self.failed or self.unknown else
                           'succeeded')
        return {
            'result_kind': self.client.config.profile.result_kind,
            'schema': {'columns': [
                {'name': name, 'native_type': None}
                for name in ('Entry', 'Line', 'Kind', 'State')]},
            'complete': True, 'stream_reference': None,
            'payload': {
                'rows': [[record['index'], record['line'], record['kind'],
                          record['state']] for record in self.records],
                'rowcount': len(self.records),
                'execution_state': execution_state,
                'execution_outcome_unknown': bool(
                    self.state.worker_interrupted or
                    self.state.attachment_liveness_failed),
                'auxiliary_cleanup': cleanup,
                'script': self.snapshot(results=True),
            },
        }
