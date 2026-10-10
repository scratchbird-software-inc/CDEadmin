"""Owned TiKV helper sessions, exact native observations and bounded pages."""
import base64
import json
import subprocess
import threading

from .client import TiKVBackend
from ..native_distributed import NativeDistributedError, NativeResult
from ..retained_native import RetainedNativeClient


class HelperOwner:
    def __init__(self, process, route):
        self.process, self.route = process, route
        self.observation = {'state': 'opening'}


class TiKVDriverBackend(TiKVBackend):
    @classmethod
    def _route(cls, request):
        route = super()._route(request)
        secure = bool(route.get('tls_ca'))
        if secure != (route['pd_http_scheme'] == 'https'):
            raise NativeDistributedError(
                'TiKV native and PD TLS policies disagree')
        if route.get('tls_certificate') and not secure:
            raise NativeDistributedError('TiKV client certificate needs a CA')
        return route

    def open_session(self, request):
        route = self._route(request)
        process = subprocess.Popen(
            [
                self._validated_helper_path(),
                '--session'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL)
        owner = HelperOwner(process, route)
        try:
            request = self._helper_request(
                route, {'operation': 'get', 'key': ''})
            request['operation'] = 'open'
            self._rpc(owner, request)
        except BaseException:
            process.kill()
            process.wait(timeout=5)
            process.stdin.close()
            process.stdout.close()
            raise
        return owner

    def _rpc(self, owner, request):
        process = owner.process
        payload = json.dumps(request, separators=(',', ':')).encode() + b'\n'
        if len(payload) > 2 * 1024 * 1024:
            raise NativeDistributedError('TiKV request exceeds bounds')
        if process.poll() is not None:
            raise NativeDistributedError(
                'TiKV helper exited; outcome unavailable')
        guard = threading.Lock()
        completed = False

        def expire():
            with guard:
                if not completed and process.poll() is None:
                    process.kill()

        timer = threading.Timer(owner.route['operation_timeout'] + 5, expire)
        timer.daemon = True
        timer.start()
        try:
            process.stdin.write(payload)
            process.stdin.flush()
            line = process.stdout.readline(self.MAX_HELPER_BYTES + 1)
            if not line.endswith(b'\n') or len(line) > self.MAX_HELPER_BYTES:
                raise NativeDistributedError('TiKV helper response incomplete')
            value = json.loads(line)
            if not isinstance(value, dict) or value.get('error'):
                raise NativeDistributedError('TiKV native request failed')
            native = value.get('native')
            if (value.get('provider_finality_only') is not True or
                    not isinstance(native, dict)):
                raise NativeDistributedError('TiKV finality boundary invalid')
            if native.get('helper_protocol') != 'retained-v1':
                raise NativeDistributedError('TiKV helper protocol mismatch')
            native.update(
                provider_finality_only=True,
                automatic_mutation_retry_by_cdeadmin=False,
                client_revision=self.CLIENT_REVISION)
            owner.observation.update(native)
            return self._records(value.get('records')), native
        finally:
            with guard:
                completed = True
            timer.cancel()

    def describe_transaction(self, owner):
        return dict(
            owner.observation,
            driver_session_owned=True,
            transaction_model='rawkv-or-explicit-txnkv',
            automatic_mutation_retry_by_cdeadmin=False,
            configured_transaction_mode=owner.route['transaction_mode'])

    def control_transaction(self, owner, action):
        self._rpc(owner, {'operation': action})

    def iterate(self, owner, command, parameters):
        if not isinstance(command, dict) or parameters:
            raise NativeDistributedError('TiKV requires JSON command')
        operation = command.get('operation')
        if operation in {'begin', 'commit', 'rollback'}:
            rows, native = self._rpc(owner, command)
            yield self._page(rows, native, 0)
            return
        mapping = {'txn_get': 'get', 'txn_set': 'put', 'txn_delete': 'delete',
                   'txn_scan': 'scan', 'scan_all': 'scan'}
        transformed = dict(
            command, operation=mapping.get(
                operation, operation))
        scan = operation in {'scan', 'scan_all', 'txn_scan'}
        limit = command.get(
            'limit', 0 if operation in {
                'scan_all', 'txn_scan'} else 100)
        if scan:
            if type(limit) is not int or not 0 <= limit <= 1000000000:
                raise NativeDistributedError('TiKV scan limit invalid')
            transformed['limit'] = min(limit or 256, 256)
        request = self._helper_request(owner.route, transformed)
        if operation == 'transaction' and 'keys_base64' in command:
            keys = command['keys_base64']
            if not isinstance(keys, list) or len(keys) > self.MAX_RECORDS:
                raise NativeDistributedError('TiKV binary key list invalid')
            if command.get('keys'):
                raise NativeDistributedError(
                    'Choose one TiKV key list encoding')
            request['keys_base64'] = [self._encoded(
                {'key_base64': key}, 'key', True) for key in keys]
        if operation in mapping and operation != 'scan_all':
            request['operation'] = operation
        count = 0
        while True:
            rows, native = self._rpc(owner, request)
            consistency = ('native-transaction-snapshot'
                           if operation == 'txn_scan' else 'raw-live-range')
            native = dict(native, row_offset=count,
                          scan_consistency=consistency if scan else None)
            # Page size by bytes as well as rows; never truncate successful
            # data.
            page, size = [], 0
            for row in rows:
                width = len(json.dumps(row).encode())
                if page and (len(page) >= 256 or size + width > 1048576):
                    yield self._page(page, native, count)
                    count += len(page)
                    page, size = [], 0
                page.append(row)
                size += width
            yield self._page(page, native, count)
            count += len(page)
            if not scan or not rows or (limit and count >= limit):
                return
            if operation == 'txn_scan' and not native.get('more'):
                return
            if operation != 'txn_scan' and len(rows) < request['limit']:
                return
            last = base64.b64decode(rows[-1]['key_base64'], validate=True)
            request['start_key_base64'] = base64.b64encode(
                last + b'\0').decode()
            request['limit'] = min(256, limit - count) if limit else 256

    @staticmethod
    def _page(rows, native, offset):
        return NativeResult(
            'key_value', 'entries', rows, {
                'fields': [
                    'key', 'value', 'key_base64', 'value_base64']}, dict(
                native, row_offset=offset))

    def close_session(self, owner, unknown=False):
        process = owner.process
        try:
            if process.poll() is None:
                if unknown:
                    process.kill()
                else:
                    self._rpc(owner, {'operation': 'close'})
            process.wait(timeout=5)
        except Exception:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            raise
        finally:
            if process.poll() is not None:
                process.stdin.close()
                process.stdout.close()


class TiKVDriver(RetainedNativeClient):
    transaction_actions = ('begin', 'commit', 'rollback')

    def describe_transaction(self, session):
        with session.lock:
            if session.active is None:
                session.observation = self.backend.describe_transaction(
                    session.handle)
            return super().describe_transaction(session)
