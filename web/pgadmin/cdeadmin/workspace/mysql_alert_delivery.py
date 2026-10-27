"""Bounded alert delivery, outside collector and viewer connections."""
import copy
import json
import queue
import threading

from .monitoring_delegation import route_fingerprint


class MySQLAlertDelivery:
    def __init__(self, app):
        self.app = app
        self.queue = queue.Queue(maxsize=64)
        self.stop = threading.Event()
        self.thread = None
        self.lock = threading.Lock()

    def _route(self, owner, route_id):
        from pgadmin.cdeadmin.report_delivery import init_app
        routes = self.app.config.get('CDEADMIN_MYSQL_ALERT_ROUTES', {})
        if not isinstance(routes, dict) or len(routes) > 64:
            raise ValueError('Invalid configured alert routes')
        value = routes.get(route_id)
        if (not isinstance(value, dict) or set(value) - {'label', 'owner_ids', 'profile_id', 'target'} or
                not isinstance(value.get('owner_ids'), (tuple, list)) or
                any(type(item) is not int or item <= 0 for item in value['owner_ids']) or owner not in value['owner_ids']):
            raise PermissionError('Alert route is not authorized')
        service = init_app(self.app)
        profile = service.profiles.get(value.get('profile_id'))
        if profile['kind'] != 'smtp' or 'json' not in profile['allowed_formats']:
            raise ValueError('Alerts require an admitted JSON SMTP profile')
        target = service.profiles.normalize_target(profile, value.get('target'))
        return service, value, target, route_fingerprint({'route': value, 'profile': profile})

    def catalog(self, owner):
        result = []
        routes = self.app.config.get('CDEADMIN_MYSQL_ALERT_ROUTES', {})
        if not isinstance(routes, dict) or len(routes) > 64:
            return result
        for route_id in routes:
            try:
                _service, value, _target, _digest = self._route(owner, route_id)
                result.append({'id': route_id, 'label': str(value.get('label', route_id))[:128]})
            except Exception:
                continue
        return result

    def admit(self, policy):
        return {rule.route_id: self._route(policy.owner_id, rule.route_id)[3]
            for rule in policy.mysql_alert_rules if rule.route_id}

    def submit(self, evaluator, event, route_id, grant, digest):
        with self.lock:
            if self.stop.is_set():
                evaluator.receipt(event, {'state': 'failed', 'reason': 'delivery-worker-stopped'})
                return
            try:
                self.queue.put_nowait((evaluator, event, route_id, grant, digest))
            except queue.Full:
                evaluator.receipt(event, {'state': 'failed', 'reason': 'delivery-queue-full'})
                return
            if self.thread is None:
                self.thread = threading.Thread(target=self._run, name='mysql-alert-delivery', daemon=True)
                self.thread.start()

    def _run(self):
        while not self.stop.is_set():
            try:
                item = self.queue.get(timeout=0.25)
            except queue.Empty:
                continue
            evaluator, event, route_id, grant, expected = item
            started = False
            try:
                with self.app.app_context():
                    grant.require(grant.policy, 'collect')
                    if not evaluator.delivery_admitted(event):
                        evaluator.receipt(event, {'state': 'suppressed', 'reason': 'silenced-or-stopped'})
                        continue
                    service, route, target, current = self._route(grant.policy.owner_id, route_id)
                    if current != expected:
                        raise PermissionError('Alert route changed')
                    payload = {key: copy.deepcopy(value) for key, value in event.items() if key != 'delivery'}
                    payload.update(schema='cdeadmin.mysql-alert.v1', endpoint_id=grant.policy.endpoint_id,
                        target_id=grant.policy.target_id)
                    grant.require(grant.policy, 'collect')
                    evaluator.receipt(event, {'state': 'delivering'})
                    started = True
                    result = service.deliver(grant.policy.owner_id, grant.policy.endpoint_id, {
                        'request_key': event['event_id'], 'result_id': 'mysql-alert:' + event['event_id'],
                        'format': 'json', 'profile_id': route['profile_id'], 'target': target,
                        'content': json.dumps(payload, sort_keys=True, allow_nan=False).encode(),
                        'filename': 'mysql-alert-' + event['event_id'] + '.json', 'media_type': 'application/json'})
                    # Do not expose destination/provider details through collector views.
                    evaluator.receipt(event, {key: result[key] for key in ('state', 'occurrence_id', 'error_type', 'completed_at')})
            except Exception as error:
                evaluator.receipt(event, {'state': 'outcome_unknown' if started else 'failed', 'error_type': type(error).__name__})
            finally:
                self.queue.task_done()
        while True:
            try:
                evaluator, event, *_rest = self.queue.get_nowait()
            except queue.Empty:
                break
            evaluator.receipt(event, {'state': 'suppressed', 'reason': 'delivery-worker-stopped'})
            self.queue.task_done()

    def close(self):
        with self.lock:
            self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=5)
        return self.thread is None or not self.thread.is_alive()
