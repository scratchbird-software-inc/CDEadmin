"""Opt-in worker ownership; native backends retain transaction authority."""
import copy
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, wait

from .native_distributed import NativeDistributedClient, NativeDistributedError


class Session:
    def __init__(self):
        self.worker = ThreadPoolExecutor(max_workers=1,
                                         thread_name_prefix='native-session')
        self.lock = threading.RLock()
        self.handle = None
        self.active = None
        self.blocked = False
        self.observation = {}


class Operation:
    def __init__(self, session, iterator):
        self.session, self.iterator = session, iterator
        self.reference = str(uuid.uuid4())
        self.final = None
        self.cancelled = False
        self.future = session.worker.submit(next, iterator, None)


class RetainedNativeClient(NativeDistributedClient):
    """An engine opts in with iterate/close_session/control callbacks."""
    transaction_actions = ()

    def open_session(self, request):
        session = Session()
        try:
            session.handle = session.worker.submit(
                self.backend.open_session, request).result()
            session.observation = session.worker.submit(
                self.backend.describe_transaction, session.handle).result()
        except BaseException:
            session.worker.shutdown(wait=True)
            raise
        self._sessions.append(session)
        return session

    def _idle(self, session):
        if session not in self._sessions:
            raise NativeDistributedError('Native session unavailable')
        if session.blocked:
            raise NativeDistributedError(
                'Native outcome unknown; close session')
        if session.active is not None:
            raise NativeDistributedError('Native execution is active')

    def runtime_identity(self, request, handle=None):
        if handle is None:
            return super().runtime_identity(request)
        with handle.lock:
            self._idle(handle)
            return handle.worker.submit(
                self.backend.runtime_identity, request, handle.handle).result()

    def describe_transaction(self, session):
        with session.lock:
            value = copy.deepcopy(session.observation)
            return dict(value, outcome_unknown=session.blocked,
                        session_reuse_blocked=session.blocked,
                        driver_observation_only=True,
                        finality_interpreted_by_common_code=False)

    def control_transaction(self, session, action):
        with session.lock:
            self._idle(session)
            if action not in self.transaction_actions:
                raise NativeDistributedError('Native decision unavailable')
            try:
                session.worker.submit(self.backend.control_transaction,
                                      session.handle, action).result()
                session.observation = session.worker.submit(
                    self.backend.describe_transaction, session.handle).result()
            except Exception:
                session.blocked = True
                raise NativeDistributedError(
                    'Native transaction outcome unknown') from None

    def execute(self, session, request):
        source = request.get('source')
        if not isinstance(source, str) or not source.strip() or len(
                source.encode()) > self.MAX_SOURCE_BYTES:
            raise NativeDistributedError('Native command source invalid')
        try:
            command = json.loads(source)
        except json.JSONDecodeError:
            command = source
        with session.lock:
            self._idle(session)
            parameters = copy.deepcopy(request.get('parameters'))
            iterator = self.backend.iterate(
                session.handle, command, parameters)
            token = Operation(session, iterator)
            session.active = token
            self._results.append(token)
            return token

    def describe_result(self, token):
        if token not in self._results:
            raise NativeDistributedError('Native result token unavailable')
        session = token.session
        with session.lock:
            if token.final is not None:
                return copy.deepcopy(token.final)
            payload = dict(has_page=False, cancelled=token.cancelled,
                           outcome_unknown=session.blocked,
                           session_reuse_blocked=session.blocked)
            schema, complete = {}, False
            try:
                if not wait([token.future], timeout=0.05).done:
                    return dict(result_kind=self.profile.result_kind,
                                schema={}, payload=payload,
                                stream_reference=token.reference,
                                complete=False)
                page = token.future.result()
                if token.cancelled:
                    # Close generators on the same worker/context as iteration.
                    session.worker.submit(
                        getattr(
                            token.iterator,
                            'close',
                            lambda: None)).result()
                    complete = True
                elif page is None:
                    complete = True
                else:
                    schema = page.schema
                    payload.update({page.records_field: page.records,
                                    'native': page.native, 'has_page': True})
                    payload.update({key: page.native[key] for key in (
                        'row_offset', 'result_set_index', 'result_set_end')
                        if key in page.native})
                    token.future = session.worker.submit(
                        next, token.iterator, None)
            except Exception as exc:
                session.blocked = True
                complete = True
                payload.update(error={'type': type(exc).__name__},
                               outcome_unknown=True,
                               session_reuse_blocked=True)
            result = dict(result_kind=self.profile.result_kind, schema=schema,
                          payload=payload, stream_reference=token.reference,
                          complete=complete)
            if complete:
                token.final = copy.deepcopy(result)
                session.active = None
            return result

    def cancel(self, token):
        with token.session.lock:
            if token not in self._results or token.final is not None:
                return False
            token.cancelled = True
            token.session.blocked = True
            return True

    def close_session(self, session):
        with session.lock:
            token = session.active
            if token is not None:
                self.cancel(token)
                if not wait([token.future], timeout=5).done:
                    raise NativeDistributedError(
                        'Native worker still owns session')
                try:
                    token.future.result()
                except Exception:
                    pass
                session.worker.submit(
                    getattr(
                        token.iterator,
                        'close',
                        lambda: None)).result()
            try:
                session.worker.submit(self.backend.close_session,
                                      session.handle, session.blocked).result()
            except Exception:
                session.blocked = True
                raise NativeDistributedError('Native cleanup failed') from None
            session.worker.shutdown(wait=True)
            self._sessions.remove(session)
            self._results = [
                t for t in self._results if t.session is not session]
            return dict(connection_released=True,
                        outcome_unknown=session.blocked)

    def close(self):
        failed = False
        for session in list(self._sessions):
            try:
                self.close_session(session)
            except Exception:
                failed = True
        if failed:
            raise NativeDistributedError('Native cleanup incomplete')
        super().close()
