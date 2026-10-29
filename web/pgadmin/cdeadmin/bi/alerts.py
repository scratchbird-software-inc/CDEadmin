##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Threshold alerts and scheduled subscriptions for BI content.

See ``docs/en_US/bi_alerts.rst``.  An *alert* runs a saved question on a
schedule and fires when a condition on the result holds; a *subscription*
delivers a question or dashboard snapshot on a schedule.  Both are stored
as one object (``BIAlert``), scheduled and leased by the report scheduler's
machinery (``alert_scheduler.py``) and evaluated with the owner's delegated
credentials.

Authorization is ``BIAccess`` only: the owner must keep ``view`` on the
resource, or the alert pauses and its delegated credentials are destroyed.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from .alert_delivery import (
    AlertDelivery, Attachment, DELIVERED, Dispatch, FAILED, UNKNOWN,
)
from .alert_models import (
    AlertError, AlertEvaluationError, FAILURE_TEXT, MAX_FAILURES,
    advance, build_preview, clamp_rows, describe_condition,
    evaluate_condition, failure_text, mute_until, number_text,
    schedule_interval_seconds, validate_alert, validate_schedule,
)
from .alert_store import dumps
from .models import BIConflict, BIError

APP_EXTENSION_KEY = 'cdeadmin_bi_alert_service'
MEDIA_TYPES = {
    'csv': 'text/csv', 'json': 'application/json',
    'jsonl': 'application/x-ndjson',
    'xlsx': ('application/vnd.openxmlformats-officedocument.'
             'spreadsheetml.sheet'),
    'svg': 'image/svg+xml', 'pdf': 'application/pdf',
}
DEFAULTS = {
    'max_message_rows': 5,
    'min_interval_seconds': 300,
    'max_alerts_per_user': 50,
    'events_keep': 200,
    'notifications_keep': 200,
    'run_now_min_seconds': 15,
    'max_dashboard_cards': 12,
    'max_result_pages': 20,
    'external_recipients': {},
}
# a pause for these reasons also destroys the delegated credentials
REVOKING = frozenset({
    'resource_unavailable', 'credential_unavailable', 'endpoint_changed',
})
_STATEMENT_START = re.compile(r'^question execution failed', re.I)


def _naive(moment):
    return moment.astimezone(timezone.utc).replace(tzinfo=None) if (
        moment.tzinfo) else moment


def _iso(moment):
    return None if moment is None else moment.replace(
        tzinfo=timezone.utc).isoformat()


def _records(page):
    view = page['view_model']
    rows = view.get('rows', view.get('records', []))
    return [dict(row) for row in rows]


class BIAlertService:
    def __init__(self, bi, repository, *, executor=None, dashboards=None,
                 delivery=None, webhook=None, scheduler=None, worker=None,
                 config=None, clock=None):
        self.bi = bi
        self.repository = repository
        self.executor = executor if executor is not None else getattr(
            bi, 'executor', None)
        self.dashboards = dashboards if dashboards is not None else getattr(
            bi, 'dashboards', None)
        self.delivery = delivery
        self.webhook = webhook
        self.scheduler = scheduler
        self.worker = worker
        self.config = {**DEFAULTS, **(config or {})}
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.channels = AlertDelivery(
            bi, repository, delivery=delivery, webhook=webhook,
            external=self.config['external_recipients'],
            policy_bound=self._policy_bound, clock=self.clock,
            notify_keep=self.config['notifications_keep'])

    # ------------------------------------------------------------------
    # small helpers
    # ------------------------------------------------------------------
    def _now(self):
        return _naive(self.clock())

    @property
    def message_rows(self):
        return clamp_rows(self.config['max_message_rows'])

    def _level(self, user_id, alert):
        return self.bi.access.level(user_id, alert.resource_type,
                                    alert.endpoint_id, alert.resource_id)

    def _reachable(self, user_id, endpoint_id, alert_id, *, manage=False):
        """The alert when the caller owns it (or manages its resource)."""
        row = self.repository.get(alert_id)
        if row is None or row.endpoint_id != endpoint_id:
            raise AlertError('alert is unavailable')
        if row.user_id == user_id:
            return row
        if self._level(user_id, row) == 'manage':
            return row
        raise AlertError('alert is unavailable')

    def _owner_only(self, user_id, row, action):
        if row.user_id != user_id:
            raise AlertError(f'only the owner can {action} this alert')

    def _resource(self, user_id, endpoint_id, rtype, rid, minimum='view'):
        return self.bi.access.require(user_id, rtype, endpoint_id, rid,
                                      minimum, 'use alerts on')

    # ------------------------------------------------------------------
    # catalog and previews
    # ------------------------------------------------------------------
    def catalog(self, user_id=None):
        profiles = []
        if self.delivery is not None:
            profiles = self.delivery.profiles.catalog()['profiles']
        return {
            'schema': 'cdeadmin.bi-alerts.catalog.v1',
            'scheduling': bool(self.scheduler is not None and
                               self.scheduler.available),
            'channels': {
                'in_app': True,
                'email': [p for p in profiles if p['kind'] == 'smtp'],
                's3': [p for p in profiles if p['kind'] == 's3'],
                'webhook': (self.webhook.catalog()
                            if self.webhook is not None else []),
            },
            'external_recipients': self.channels.external_configured,
            'limits': {
                'max_message_rows': self.message_rows,
                'min_interval_seconds': self.config['min_interval_seconds'],
                'max_alerts_per_user': self.config['max_alerts_per_user'],
                'max_dashboard_cards': self.config['max_dashboard_cards'],
            },
        }

    def schedule_preview(self, value, count=5):
        schedule = validate_schedule(value)
        if isinstance(count, bool) or not isinstance(count, int) or not (
                1 <= count <= 20):
            raise AlertError('count must be 1 to 20')
        from pgadmin.cdeadmin.report_scheduler.service import (
            ReportSchedulerService,
        )
        runs = ReportSchedulerService.next_instants(
            schedule, self._now(), count)
        return {'schedule': schedule, 'next_runs': [_iso(r) for r in runs],
                'interval_seconds': schedule_interval_seconds(schedule)}

    # ------------------------------------------------------------------
    # admission
    # ------------------------------------------------------------------
    def _admit(self, user_id, endpoint_id, definition, existing=None):
        """Every static rule an alert definition must satisfy."""
        resource = definition['resource']
        row, level = self._resource(user_id, endpoint_id, resource['type'],
                                    resource['id'])
        if getattr(row, 'status', 'active') != 'active':
            raise AlertError('archived content cannot be scheduled')
        revision = definition['revision'] or row.revision
        if resource['type'] == 'question':
            stored = self.bi.stored_for_run(user_id, endpoint_id,
                                            resource['id'], revision)
            if stored['status'] != 'active':
                raise AlertError('archived content cannot be scheduled')
            if stored['definition']['query']['kind'] == 'sql':
                self.bi.assert_raw_sql_allowed(
                    user_id, endpoint_id,
                    also_users=(stored['owner_id'],)
                    if stored['owner_id'] != user_id else ())
            policy = self._policy(stored['definition'])
            self._check_condition_column(definition, policy)
            self._check_format(definition, [policy])
        else:
            dash = self.dashboards.revision(user_id, endpoint_id,
                                            resource['id'], revision)
            policies = []
            for card in dash['definition']['cards']:
                if card['type'] != 'question':
                    continue
                stored = self.bi.stored_for_run(
                    user_id, endpoint_id, card['question']['question_id'],
                    card['question']['revision'])
                policies.append(self._policy(stored['definition']))
            self._check_format(definition, policies)
        interval = schedule_interval_seconds(definition['schedule'])
        if interval < self.config['min_interval_seconds']:
            raise AlertError(
                'the schedule runs more often than every '
                f"{self.config['min_interval_seconds'] // 60} minutes"
                if self.config['min_interval_seconds'] >= 60 else
                'the schedule runs too often')
        self._check_channels(user_id, endpoint_id, definition, level,
                             row, revision)
        return row, revision

    @staticmethod
    def _policy(question):
        from .execution import BIExecutor
        return BIExecutor._normalized(question)['result_policy']

    @staticmethod
    def _check_condition_column(definition, policy):
        condition = definition.get('condition')
        if condition and condition['type'] == 'metric' and condition[
                'metric']['kind'] == 'column' and condition['metric'][
                'column'] in policy['redact_columns']:
            raise AlertError(
                'the condition column is redacted by the question\'s result '
                'policy')

    @staticmethod
    def _check_format(definition, policies):
        if definition['kind'] != 'subscription' or not definition['format']:
            return
        fmt = definition['format']
        if not any(p['export']['enabled'] and fmt in p['export']['formats']
                   for p in policies):
            raise AlertError(
                'no result policy allows exporting this content as ' + fmt)

    def _check_channels(self, user_id, endpoint_id, definition, level, row,
                        revision):
        probe = SimpleNamespace(
            id='draft', user_id=user_id, endpoint_id=endpoint_id,
            kind=definition['kind'], resource_type=definition['resource'][
                'type'], resource_id=definition['resource']['id'],
            resource_revision=revision)
        directory = self.bi.access.directory
        for channel in definition['channels']:
            kind = channel['type']
            if kind in ('s3', 'webhook') and level != 'manage':
                raise AlertError(
                    'manage access is required to deliver outside the '
                    'application')
            if kind == 's3' or kind == 'email':
                self._check_profile(channel, definition)
            if kind == 'webhook':
                if self.webhook is None:
                    raise AlertError('webhook delivery is not configured')
                from .webhook import WebhookError
                try:
                    self.webhook.check_url(channel['url'])
                except WebhookError as exc:
                    raise AlertError(str(exc)) from None
            for recipient in channel.get('recipients', ()):
                if recipient['type'] == 'email':
                    if level != 'manage':
                        raise AlertError(
                            'manage access is required to send to external '
                            'email addresses')
                    if not self.channels.external_allowed(
                            recipient['address']):
                        raise AlertError(
                            'an external recipient is not on the server '
                            'allow-list')
                    continue
                uid = recipient['user_id']
                if uid == user_id:
                    continue
                if not directory.can_see(user_id, 'user', uid):
                    raise AlertError('recipient is unavailable')
                code = self.channels.user_code(probe, uid)
                if code == 'recipient_not_authorized':
                    raise AlertError(
                        'a recipient does not have view access to this '
                        'content')
                if code == 'row_policy_bound':
                    raise AlertError(
                        'this content is limited by a row policy, so it can '
                        'only be delivered to its owner')
                if code:
                    raise AlertError('recipient is unavailable')

    def _check_profile(self, channel, definition):
        if self.delivery is None:
            raise AlertError('report delivery is not configured')
        want = 'smtp' if channel['type'] == 'email' else 's3'
        try:
            profile = self.delivery.profiles.get(channel['profile_id'])
        except Exception:
            raise AlertError('delivery profile is unavailable') from None
        if profile['kind'] != want:
            raise AlertError('delivery profile does not match the channel')
        if definition['kind'] == 'alert':
            fmts = ['json']
        else:
            fmts = [definition['format']] if definition['format'] else []
        for fmt in fmts:
            if fmt not in profile['allowed_formats']:
                raise AlertError(
                    f'the delivery profile does not admit {fmt} exports')

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def create(self, user_id, endpoint_id, value, server=None):
        if self.scheduler is None or not self.scheduler.available:
            raise AlertError(
                'unattended scheduling is not configured (the report worker '
                'key authority is required); use the test action instead')
        definition = validate_alert(value, user_id)
        if self.repository.count(user_id, endpoint_id) >= self.config[
                'max_alerts_per_user']:
            raise AlertError('the per-user alert limit is reached')
        _row, revision = self._admit(user_id, endpoint_id, definition)
        definition['revision'] = revision
        now = self._now()
        alert = self.repository.new(
            id=str(uuid.uuid4()), user_id=user_id, endpoint_id=endpoint_id,
            kind=definition['kind'], name=definition['name'],
            resource_type=definition['resource']['type'],
            resource_id=definition['resource']['id'],
            resource_revision=revision, status='active', pause_reason=None,
            paused_at=None, muted_until=None, breach_state='unknown',
            pending_notify=False, last_value=None, last_evaluated_at=None,
            last_fired_at=None, consecutive_failures=0, schedule_anchor=now,
            revision=1, definition=dumps(definition), created_at=now,
            updated_at=now)
        self.repository.add(alert)
        try:
            self.scheduler.authorize_alert(
                server, alert, definition['expires_in_days'])
        except Exception:
            self.repository.delete(alert)
            raise
        return self._present(alert, user_id)

    def update(self, user_id, endpoint_id, alert_id, expected_revision, value):
        alert = self._reachable(user_id, endpoint_id, alert_id)
        self._owner_only(user_id, alert, 'change')
        if isinstance(expected_revision, bool) or not isinstance(
                expected_revision, int):
            raise AlertError('expected_revision must be an integer')
        if alert.revision != expected_revision:
            raise BIConflict('alert revision has changed')
        definition = validate_alert(value, user_id)
        old = json.loads(alert.definition)
        if (definition['kind'], definition['resource']) != (
                old['kind'], old['resource']):
            raise AlertError('the kind and resource of an alert cannot '
                             'change; create a new one')
        _row, revision = self._admit(user_id, endpoint_id, definition,
                                     existing=alert)
        definition['revision'] = revision
        reset = (definition.get('condition') != old.get('condition') or
                 revision != alert.resource_revision or
                 definition['parameters'] != old['parameters'] or
                 definition['filters'] != old['filters'])
        alert.name = definition['name']
        alert.resource_revision = revision
        alert.definition = dumps(definition)
        alert.revision += 1
        alert.updated_at = self._now()
        if definition['schedule'] != old['schedule']:
            alert.schedule_anchor = alert.updated_at
        if reset:
            alert.breach_state, alert.pending_notify = 'unknown', False
            alert.last_value = None
        self.repository.save(alert)
        return self._present(alert, user_id)

    def delete(self, user_id, endpoint_id, alert_id):
        alert = self._reachable(user_id, endpoint_id, alert_id)
        if self.scheduler is not None:
            self.scheduler.revoke_alert(alert.id)
        self.repository.delete(alert)
        return {'alert_id': alert_id, 'deleted': True}

    def get(self, user_id, endpoint_id, alert_id):
        return self._present(self._reachable(user_id, endpoint_id, alert_id),
                             user_id)

    def list(self, user_id, endpoint_id, resource_type=None,
             resource_id=None, kind=None):
        if (resource_type is None) != (resource_id is None):
            raise AlertError('give both resource_type and resource_id')
        manage = False
        if resource_type is not None:
            if resource_type not in ('question', 'dashboard'):
                raise AlertError('resource_type must be question or '
                                 'dashboard')
            _row, level = self._resource(user_id, endpoint_id,
                                         resource_type, resource_id)
            manage = level == 'manage'
        rows = self.repository.list(
            endpoint_id, resource_type=resource_type,
            resource_id=resource_id, kind=kind)
        return [self._present(r, user_id, listing=True) for r in rows
                if r.user_id == user_id or manage]

    # ------------------------------------------------------------------
    # state controls
    # ------------------------------------------------------------------
    def mute(self, user_id, endpoint_id, alert_id, until=None,
             duration_minutes=None):
        alert = self._reachable(user_id, endpoint_id, alert_id)
        end = mute_until(self._now(), until, duration_minutes)
        self.repository.update_state(alert.id, muted_until=end,
                                     updated_at=self._now())
        return self.get(user_id, endpoint_id, alert_id)

    def unmute(self, user_id, endpoint_id, alert_id):
        alert = self._reachable(user_id, endpoint_id, alert_id)
        self.repository.update_state(alert.id, muted_until=None,
                                     updated_at=self._now())
        return self.get(user_id, endpoint_id, alert_id)

    def rearm(self, user_id, endpoint_id, alert_id):
        """Forget an ongoing breach so the next breaching run fires again."""
        alert = self._reachable(user_id, endpoint_id, alert_id)
        self.repository.update_state(
            alert.id, breach_state='ok', pending_notify=False,
            updated_at=self._now())
        return self.get(user_id, endpoint_id, alert_id)

    def pause(self, user_id, endpoint_id, alert_id):
        alert = self._reachable(user_id, endpoint_id, alert_id)
        self._pause(alert, 'user_paused', revoke=False)
        return self.get(user_id, endpoint_id, alert_id)

    def resume(self, user_id, endpoint_id, alert_id, server=None,
               reset=False):
        """Owner-only: re-check everything and authorize unattended runs."""
        alert = self._reachable(user_id, endpoint_id, alert_id)
        self._owner_only(user_id, alert, 'resume')
        if self.scheduler is None or not self.scheduler.available:
            raise AlertError('unattended scheduling is not configured')
        definition = json.loads(alert.definition)
        self._admit(user_id, endpoint_id, definition, existing=alert)
        delegation = self.scheduler.delegation_for(alert.id)
        now = self._now()
        if delegation is None or delegation.state != 'active' or (
                delegation.expires_at <= now):
            if server is None:
                raise AlertError('resuming needs the owner session to '
                                 'authorize unattended runs again')
            self.scheduler.authorize_alert(
                server, alert, definition['expires_in_days'])
        values = dict(status='active', pause_reason=None, paused_at=None,
                      consecutive_failures=0, schedule_anchor=now,
                      updated_at=now)
        if reset:
            values.update(breach_state='unknown', pending_notify=False,
                          last_value=None)
        self.repository.update_state(alert.id, **values)
        return self.get(user_id, endpoint_id, alert_id)

    def _pause(self, alert, reason, *, revoke):
        now = self._now()
        self.repository.update_state(
            alert.id, status='paused', pause_reason=reason, paused_at=now,
            updated_at=now)
        if (revoke or reason in REVOKING) and self.scheduler is not None:
            self.scheduler.revoke_alert(alert.id)
        self._event(alert, 'system', 'paused', fired=False,
                    error_class=reason, error_message=failure_text(reason))

    # ------------------------------------------------------------------
    # history and notifications
    # ------------------------------------------------------------------
    def history(self, user_id, endpoint_id, alert_id, limit=50):
        alert = self._reachable(user_id, endpoint_id, alert_id)
        if isinstance(limit, bool) or not isinstance(limit, int) or not (
                1 <= limit <= 200):
            limit = 50
        editor = self._level(user_id, alert) in ('edit', 'manage')
        return [self._present_event(e, editor)
                for e in self.repository.events(alert.id, limit)]

    @staticmethod
    def _present_event(event, editor):
        out = {
            'event_id': event.id, 'trigger': event.trigger,
            'outcome': event.outcome, 'fired': bool(event.fired),
            'suppressed': event.suppressed,
            'resource_revision': event.resource_revision,
            'value': json.loads(event.value) if event.value else None,
            'deliveries': json.loads(event.deliveries or '[]'),
            'error_class': event.error_class,
            'error_text': failure_text(event.error_class)
            if event.error_class else None,
            'created_at': _iso(event.created_at),
        }
        # the detail line can quote validation text of the question; only
        # people who may edit the content see it
        out['error_detail'] = event.error_message if editor else None
        return out

    def notifications(self, user_id, endpoint_id, unread_only=False,
                      limit=50):
        if isinstance(limit, bool) or not isinstance(limit, int) or not (
                1 <= limit <= 200):
            limit = 50
        rows = self.repository.notifications(
            user_id, endpoint_id, unread_only=bool(unread_only), limit=limit)
        return {
            'unread': self.repository.unread_count(user_id, endpoint_id),
            'items': [{
                'notification_id': r.id, 'alert_id': r.alert_id,
                'kind': r.kind, 'resource_type': r.resource_type,
                'resource_id': r.resource_id, 'title': r.title,
                'body': r.body, 'data': json.loads(r.data or '{}'),
                'created_at': _iso(r.created_at),
                'read_at': _iso(r.read_at),
            } for r in rows],
        }

    def mark_read(self, user_id, endpoint_id, ids=None):
        if ids is not None and (not isinstance(ids, list) or len(ids) > 200
                                or not all(isinstance(i, str) for i in ids)):
            raise AlertError('ids must be an array of notification ids')
        count = self.repository.mark_read(user_id, endpoint_id, ids,
                                          self._now())
        return {'marked': count,
                'unread': self.repository.unread_count(user_id, endpoint_id)}

    # ------------------------------------------------------------------
    # presentation
    # ------------------------------------------------------------------
    def _present(self, alert, viewer_id, listing=False):
        definition = json.loads(alert.definition)
        now = self._now()
        owner = alert.user_id == viewer_id
        level = self._level(viewer_id, alert)
        if not owner and level != 'manage':
            definition['channels'] = [{'type': c['type']}
                                      for c in definition['channels']]
        delegation = (self.scheduler.delegation_for(alert.id)
                      if self.scheduler is not None else None)
        next_runs = []
        if alert.status == 'active' and not listing:
            try:
                from pgadmin.cdeadmin.report_scheduler.service import (
                    ReportSchedulerService,
                )
                next_runs = [_iso(r) for r in
                             ReportSchedulerService.next_instants(
                                 definition['schedule'], now, 3)]
            except Exception:
                next_runs = []
        muted = alert.muted_until is not None and now < alert.muted_until
        last = json.loads(alert.last_value) if alert.last_value else None
        return {
            'alert_id': alert.id, 'kind': alert.kind, 'name': alert.name,
            'resource': {'type': alert.resource_type,
                         'id': alert.resource_id,
                         'revision': alert.resource_revision},
            'status': alert.status, 'pause_reason': alert.pause_reason,
            'pause_text': failure_text(alert.pause_reason)
            if alert.pause_reason else None,
            'paused_at': _iso(alert.paused_at),
            'muted': muted,
            'muted_until': _iso(alert.muted_until) if muted else None,
            'breach_state': alert.breach_state,
            'pending_notify': bool(alert.pending_notify),
            'last_value': last, 'last_evaluated_at': _iso(
                alert.last_evaluated_at),
            'last_fired_at': _iso(alert.last_fired_at),
            'consecutive_failures': alert.consecutive_failures,
            'revision': alert.revision,
            'is_owner': owner, 'access': level,
            'definition': definition,
            'delegation': None if delegation is None else {
                'state': delegation.state,
                'expires_at': _iso(delegation.expires_at),
                'unattended': delegation.state == 'active' and (
                    delegation.expires_at > now)},
            'next_runs': next_runs,
            'created_at': _iso(alert.created_at),
            'updated_at': _iso(alert.updated_at),
        }

    # ------------------------------------------------------------------
    # evaluation
    # ------------------------------------------------------------------
    def test(self, user_id, endpoint_id, *, runtime, value=None,
             alert_id=None):
        """Dry run with the caller's own session: nothing is sent or kept."""
        if alert_id is not None:
            alert = self._reachable(user_id, endpoint_id, alert_id)
            self._owner_only(user_id, alert, 'test')
            definition = json.loads(alert.definition)
        else:
            definition = validate_alert(value, user_id)
            _row, revision = self._admit(user_id, endpoint_id, definition)
            definition['revision'] = revision
            alert = SimpleNamespace(
                id='draft', user_id=user_id, endpoint_id=endpoint_id,
                kind=definition['kind'], name=definition['name'],
                resource_type=definition['resource']['type'],
                resource_id=definition['resource']['id'],
                resource_revision=revision, breach_state='unknown',
                pending_notify=False, last_value=None, muted_until=None,
                definition=dumps(definition))
        report = self._execute(alert, definition, runtime, 'test',
                               live=False)
        report['dry_run'] = True
        return report

    def run_now(self, user_id, endpoint_id, alert_id):
        """Run one real evaluation now, through the shared lease path."""
        alert = self._reachable(user_id, endpoint_id, alert_id)
        self._owner_only(user_id, alert, 'run')
        if self.scheduler is None or self.worker is None:
            raise AlertError('unattended scheduling is not configured')
        if alert.status != 'active':
            raise AlertError('the alert is paused; resume it first')
        delegation = self.scheduler.delegation_for(alert.id)
        now = self._now()
        if delegation is None or delegation.state != 'active' or (
                delegation.expires_at <= now):
            raise AlertError('the delegation is not active; resume the '
                             'alert to authorize it again')
        gap = self.config['run_now_min_seconds']
        if alert.last_evaluated_at is not None and (
                now - alert.last_evaluated_at).total_seconds() < gap:
            raise AlertError(f'wait {gap} seconds between runs')
        occurrence, created = self.scheduler.repository.enqueue(
            delegation.id, now)
        if not created:
            raise AlertError('a run is already scheduled for this instant')
        claim = self.scheduler.claim(f'run-now:{user_id}', occurrence.id)
        if claim is None:
            raise AlertError('the run could not be claimed')
        occurrence, token = claim
        state = self.worker.run_claimed(occurrence, token)
        events = self.repository.events(alert.id, 1)
        return {'state': state, 'event': self._present_event(
            events[0], True) if events else None,
            'alert': self.get(user_id, endpoint_id, alert_id)}

    def run_delegated(self, delegation, *, trigger='schedule',
                      delivering=None, heartbeat=None):
        """One claimed occurrence: the owner's delegated, unattended run."""
        from pgadmin.cdeadmin.report_scheduler.models import (
            ReportSchedulerAccessError, ReportSchedulerConflict,
            ReportSchedulerError,
        )
        alert = delegation.alert
        if alert.status != 'active':
            return {'state': 'cancelled', 'phase': 'alert-paused'}
        if self._level(alert.user_id, alert) is None:
            self._pause(alert, 'resource_unavailable', revoke=True)
            return {'state': 'cancelled',
                    'phase': 'paused:resource_unavailable',
                    'error_code': 'resource_unavailable'}
        try:
            runtime = self.scheduler.runtime(delegation)
        except ReportSchedulerConflict:
            self._pause(alert, 'endpoint_changed', revoke=True)
            return {'state': 'cancelled', 'phase': 'paused:endpoint_changed',
                    'error_code': 'endpoint_changed'}
        except (ReportSchedulerAccessError, ReportSchedulerError):
            expired = delegation.state != 'active' or (
                delegation.expires_at <= self._now())
            reason = 'delegation_expired' if expired else (
                'credential_unavailable')
            self._pause(alert, reason, revoke=not expired)
            return {'state': 'cancelled', 'phase': 'paused:' + reason,
                    'error_code': reason}
        definition = json.loads(alert.definition)
        try:
            report = self._execute(
                alert, definition, runtime, trigger, live=True,
                delivering=delivering, heartbeat=heartbeat)
        except AlertEvaluationError as exc:
            return self._failed(alert, trigger, exc.code, str(exc))
        except Exception:
            return self._failed(alert, trigger, 'worker_error', None)
        return self._outcome(report)

    @staticmethod
    def _outcome(report):
        results = report.get('deliveries', [])
        attempted = [d for d in results if d['state'] in (
            DELIVERED, FAILED, UNKNOWN)]
        ids = [d['delivery_id'] for d in results if d.get('delivery_id')]
        if attempted and all(d['state'] == FAILED for d in attempted):
            return {'state': 'failed', 'phase': 'delivery-failed',
                    'delivery_ids': ids, 'error_code': 'delivery_failed'}
        if any(d['state'] == UNKNOWN for d in attempted):
            return {'state': 'outcome_unknown', 'phase': 'delivery-unknown',
                    'delivery_ids': ids, 'error_code': 'delivery_failed'}
        return {'state': 'delivered', 'phase': 'complete',
                'delivery_ids': ids}

    def _failed(self, alert, trigger, code, detail):
        failures = (alert.consecutive_failures or 0) + 1
        self.repository.update_state(
            alert.id, consecutive_failures=failures,
            last_evaluated_at=self._now())
        text = self._safe_detail(code, detail)
        self._event(alert, trigger, 'error', fired=False, error_class=code,
                    error_message=text)
        if failures >= MAX_FAILURES:
            self._pause(alert, 'repeated_failures', revoke=False)
        return {'state': 'failed', 'phase': 'evaluation-failed',
                'error_code': code}

    @staticmethod
    def _safe_detail(code, detail):
        if not detail or code in ('execution_failed', 'worker_error'):
            return failure_text(code)
        text = ' '.join(str(detail).split())
        if _STATEMENT_START.match(text):
            return failure_text('execution_failed')
        return text[:300]

    def _event(self, alert, trigger, outcome, *, fired, suppressed=None,
               value=None, deliveries=None, error_class=None,
               error_message=None):
        row = self.repository.add_event(
            alert_id=alert.id, trigger=trigger, outcome=outcome,
            fired=fired, suppressed=suppressed,
            resource_revision=alert.resource_revision,
            value=dumps(value) if value is not None else None,
            deliveries=dumps(deliveries or []), error_class=error_class,
            error_message=(error_message or '')[:300] or None,
            created_at=self._now())
        self.repository.prune_events(alert.id, self.config['events_keep'])
        return row

    # -- the core ----------------------------------------------------------
    def _execute(self, alert, definition, runtime, trigger, *, live,
                 delivering=None, heartbeat=None):
        if definition['kind'] == 'alert':
            return self._execute_alert(alert, definition, runtime, trigger,
                                       live, delivering, heartbeat)
        return self._execute_subscription(alert, definition, runtime,
                                          trigger, live, delivering,
                                          heartbeat)

    def _previous(self, alert):
        if not alert.last_value:
            return None
        return json.loads(alert.last_value).get('value')

    def _execute_alert(self, alert, definition, runtime, trigger, live,
                       delivering, heartbeat):
        owner = alert.user_id
        condition = definition['condition']
        result = self._fetch_question(
            runtime, owner, alert.endpoint_id, alert.resource_id,
            alert.resource_revision, definition['parameters'])
        try:
            if heartbeat:
                heartbeat()
            self._check_result_columns(condition, result)
            outcome = evaluate_condition(
                condition, columns=result['columns'], rows=result['rows'],
                row_count=result['row_count'],
                previous=self._previous(alert))
            now = self._now()
            muted = bool(alert.muted_until and now < alert.muted_until)
            adv = advance(
                breach_state=alert.breach_state,
                pending_notify=bool(alert.pending_notify),
                breached=outcome['breached'], fire_on=definition['fire_on'],
                muted=muted)
            name = self._resource_name(alert)
            preview = build_preview(result['columns'], result['rows'],
                                    self.message_rows)
            message = self._alert_message(
                alert, definition, name, outcome, adv, preview, now)
            title, text = self._alert_text(alert, definition, name,
                                           outcome, preview)
            dispatch = Dispatch(alert, definition, str(uuid.uuid4()), title,
                                text, message,
                                stamp=now.strftime('%Y%m%dT%H%M%S'))
            value = {'value': outcome['value'],
                     'previous': outcome['previous'],
                     'change': outcome['change'],
                     'detail': outcome['detail'],
                     'row_count': result['row_count']}
            label = ('breach' if outcome['breached'] else 'ok') if outcome[
                'breached'] is not None else outcome['detail']
            report = {
                'outcome': {**value, 'breached': outcome['breached'],
                            'label': label,
                            'condition': describe_condition(condition)},
                'would_fire': adv['fire'], 'fire': adv['fire'],
                'reason': adv['reason'], 'suppressed': adv['suppressed'],
                'breach_state_after': adv['breach_state'],
                'message': {'title': title, 'text': text,
                            'preview': preview},
                'columns': result['columns'],
                'row_count': result['row_count'],
                'truncated': result['truncated'],
                'resource_revision': result['revision'],
            }
            if not live:
                report['deliveries'] = self.channels.run(dispatch,
                                                         send=False)
                return report
            values = dict(
                breach_state=adv['breach_state'],
                pending_notify=adv['pending_notify'],
                last_evaluated_at=now, consecutive_failures=0,
                last_value=dumps({'value': outcome['value'],
                                  'at': _iso(now)}))
            if alert.muted_until and not muted:
                values['muted_until'] = None
            if adv['fire']:
                values['last_fired_at'] = now
            self.repository.update_state(alert.id, **values)
            deliveries = []
            if adv['fire']:
                if delivering:
                    delivering()
                deliveries = self.channels.run(dispatch, send=True)
            failed = [d for d in deliveries if d['state'] in (FAILED,
                                                              UNKNOWN)]
            self._event(
                alert, trigger, label, fired=adv['fire'],
                suppressed=adv['suppressed'], value=value,
                deliveries=deliveries,
                error_class='delivery_failed' if failed else None,
                error_message=failure_text('delivery_failed')
                if failed else None)
            report['deliveries'] = deliveries
            return report
        finally:
            self._release(runtime, owner, alert.endpoint_id,
                          [result['result_id']])

    @staticmethod
    def _check_result_columns(condition, result):
        if condition['type'] != 'metric':
            return
        metric = condition['metric']
        if metric['kind'] == 'row_count':
            if result['truncated']:
                raise AlertEvaluationError('result_truncated')
            return
        if metric['column'] in result['redacted']:
            raise AlertEvaluationError('column_redacted')
        if metric['column'] not in result['columns']:
            raise AlertEvaluationError('column_missing')
        if result['truncated'] and metric['aggregate'] != 'first':
            raise AlertEvaluationError('result_truncated')

    def _resource_name(self, alert):
        try:
            row = self.bi.access.kinds[alert.resource_type].find(
                alert.endpoint_id, alert.resource_id)
            return row.name if row is not None else alert.resource_id
        except Exception:
            return alert.resource_id

    def _alert_message(self, alert, definition, name, outcome, adv, preview,
                       now):
        return {
            'schema': 'cdeadmin.bi-alert.v1',
            'event': 'alert.fired',
            'alert': {'id': alert.id, 'name': alert.name},
            'resource': {'type': alert.resource_type,
                         'id': alert.resource_id, 'name': name,
                         'revision': alert.resource_revision},
            'evaluated_at': _iso(now),
            'condition': describe_condition(definition['condition']),
            'value': outcome['value'], 'previous': outcome['previous'],
            'change': outcome['change'], 'reason': adv['reason'],
            'preview': preview,
        }

    @staticmethod
    def _alert_text(alert, definition, name, outcome, preview):
        title = f'Alert "{alert.name}" fired'
        lines = [f'{title} on "{name}".',
                 'Condition: ' + describe_condition(definition['condition']),
                 'Value: ' + number_text(outcome['value'])]
        if outcome['previous'] is not None:
            lines.append('Previous: ' + number_text(outcome['previous']))
        if outcome['change'] is not None:
            lines.append('Change: ' + number_text(outcome['change']))
        if preview['rows']:
            lines.append('')
            lines.append(' | '.join(preview['columns']))
            for row in preview['rows']:
                lines.append(' | '.join(
                    '' if row[c] is None else str(row[c])
                    for c in preview['columns']))
            if preview['truncated']:
                lines.append(f"... {preview['row_count'] - preview['shown']}"
                             ' more rows not shown')
        return title, '\n'.join(lines)

    # -- running questions ---------------------------------------------------
    def _fetch_question(self, runtime, owner, endpoint_id, question_id,
                        revision, parameters):
        provider, context, endpoint = runtime
        if self.executor is None:
            raise AlertEvaluationError('execution_failed')
        try:
            out = self.executor.run(
                provider=provider, context=context, endpoint=endpoint,
                user_id=owner, question_id=question_id, revision=revision,
                parameters=parameters or None, page_size=500,
                bypass_cache=True)
        except BIError as exc:
            raise self._classify(exc) from None
        return self._collect(out, owner, endpoint_id)

    def _classify(self, exc):
        message = str(exc)
        if 'archived' in message:
            return AlertEvaluationError('archived')
        if message.endswith('is unavailable'):
            return AlertEvaluationError('resource_unavailable')
        if _STATEMENT_START.match(message):
            return AlertEvaluationError('execution_failed')
        return AlertEvaluationError('execution_failed', message[:300])

    def _collect(self, out, owner, endpoint_id):
        page = out['page']
        result_id = out['result']['result_id']
        rows = _records(page)
        cursor = page['page']['next_cursor']
        pages = 1
        try:
            while cursor and pages < self.config['max_result_pages']:
                more = self.executor.page(owner, endpoint_id, result_id,
                                          cursor=cursor, page_size=500)
                rows.extend(_records(more))
                cursor = more['page']['next_cursor']
                pages += 1
        except BIError as exc:
            self._release_ids(owner, endpoint_id, [result_id])
            raise self._classify(exc) from None
        source = page['page']['source_count']
        truncated = bool(cursor) or len(rows) < source or bool(
            page['page'].get('provider_continuation'))
        columns = [c['name'] for c in
                   out['result'].get('schema', {}).get('columns', [])]
        if not columns and rows:
            columns = list(rows[0])
        return {'columns': columns, 'rows': rows, 'row_count': source,
                'truncated': truncated, 'result_id': result_id,
                'redacted': list(out.get('redacted_columns') or []),
                'revision': out.get('revision'), 'out': out}

    def _release_ids(self, owner, endpoint_id, ids):
        for result_id in ids:
            try:
                self.executor.invalidate(user_id=owner,
                                         endpoint_id=endpoint_id,
                                         result_id=result_id)
            except Exception:
                pass

    def _release(self, runtime, owner, endpoint_id, ids):
        self._release_ids(owner, endpoint_id, ids)

    # -- subscriptions ------------------------------------------------------------
    def _execute_subscription(self, alert, definition, runtime, trigger,
                              live, delivering, heartbeat):
        owner = alert.user_id
        fmt = definition['format']
        cap = self.message_rows
        results, items, attachments = [], [], []
        try:
            if alert.resource_type == 'question':
                result = self._fetch_question(
                    runtime, owner, alert.endpoint_id, alert.resource_id,
                    alert.resource_revision, definition['parameters'])
                results.append(result)
                sources = [('question', self._resource_name(alert), result, None)]
            else:
                sources = self._fetch_dashboard(
                    alert, definition, runtime, results)
            if heartbeat:
                heartbeat()
            for key, title, result, code in sources:
                items.append(self._snapshot_item(
                    alert, definition, key, title, result, code, fmt, cap,
                    attachments))
            if not any(item['status'] == 'ok' for item in items):
                raise AlertEvaluationError('no_card_data')
            if fmt and not attachments:
                raise AlertEvaluationError('no_exportable_card' if
                                           alert.resource_type ==
                                           'dashboard' else
                                           'export_not_permitted')
            now = self._now()
            name = self._resource_name(alert)
            title = f'Subscription "{alert.name}": {name}'
            message = {
                'schema': 'cdeadmin.bi-subscription.v1',
                'event': 'subscription.snapshot',
                'alert': {'id': alert.id, 'name': alert.name},
                'resource': {'type': alert.resource_type,
                             'id': alert.resource_id, 'name': name,
                             'revision': alert.resource_revision},
                'evaluated_at': _iso(now),
                'items': [{k: v for k, v in item.items()
                           if k != 'attachment'} for item in items],
            }
            text = '\n'.join([title] + [
                f"- {i['title']}: " + (
                    f"{i['row_count']} rows" if i['status'] == 'ok'
                    else 'not included (' + str(i['code']) + ')')
                for i in items])
            dispatch = Dispatch(alert, definition, str(uuid.uuid4()), title,
                                text, message, attachments=attachments,
                                stamp=now.strftime('%Y%m%dT%H%M%S'))
            report = {
                'message': {'title': title, 'text': text},
                'items': message['items'],
                'attachments': [{
                    'name': a.name, 'filename': a.filename,
                    'format': a.format, 'bytes': len(a.content)}
                    for a in attachments],
                'fire': True,
            }
            if not live:
                report['deliveries'] = self.channels.run(dispatch,
                                                         send=False)
                return report
            self.repository.update_state(
                alert.id, last_evaluated_at=now, consecutive_failures=0,
                last_fired_at=now)
            if delivering:
                delivering()
            deliveries = self.channels.run(dispatch, send=True)
            failed = [d for d in deliveries if d['state'] in (FAILED,
                                                              UNKNOWN)]
            self._event(
                alert, trigger, 'delivered', fired=True,
                value={'items': len(items), 'attachments': len(attachments)},
                deliveries=deliveries,
                error_class='delivery_failed' if failed else None,
                error_message=failure_text('delivery_failed')
                if failed else None)
            report['deliveries'] = deliveries
            return report
        finally:
            self._release(runtime, owner, alert.endpoint_id,
                          [r['result_id'] for r in results])

    def _fetch_dashboard(self, alert, definition, runtime, results):
        provider, context, endpoint = runtime
        try:
            ran = self.dashboards.run(
                provider=provider, context=context, endpoint=endpoint,
                user_id=alert.user_id, dashboard_id=alert.resource_id,
                filters=definition['filters'] or None,
                revision=alert.resource_revision, page_size=500,
                bypass_cache=True)
            board = self.dashboards.revision(
                alert.user_id, alert.endpoint_id, alert.resource_id,
                alert.resource_revision)['definition']
        except BIError as exc:
            raise self._classify(exc) from None
        titles = {c['id']: (c.get('title') or c['id'])
                  for c in board['cards']}
        sources = []
        for card_id, card in ran['cards'].items():
            if card.get('type') != 'question':
                continue
            if len(sources) >= self.config['max_dashboard_cards']:
                break
            title = titles.get(card_id, card_id)
            run = card.get('run')
            if run is None:
                # a card the owner cannot run, or that failed, is reported
                # by code only; its native error text is never kept
                code = 'no_access' if card.get('no_access') else (
                    'card_failed')
                sources.append((card_id, title, None, code))
                continue
            collected = self._collect(run, alert.user_id, alert.endpoint_id)
            results.append(collected)
            sources.append((card_id, title, collected, None))
        return sources

    def _snapshot_item(self, alert, definition, key, title, result, code, fmt,
                       cap, attachments):
        if result is None:
            return {'name': key, 'title': title, 'status': 'error',
                    'code': code, 'row_count': None, 'preview': None}
        preview = build_preview(result['columns'], result['rows'], cap)
        item = {'name': key, 'title': title, 'status': 'ok', 'code': None,
                'row_count': result['row_count'], 'preview': preview}
        if not fmt:
            return item
        export = result['out']['export']
        if not (export['enabled'] and fmt in export['formats']):
            item.update(status='skipped', code='export_not_permitted')
            return item
        try:
            exported = self.executor.export(
                alert.user_id, alert.endpoint_id, result['result_id'], fmt)
        except BIError:
            item.update(status='skipped', code='export_not_permitted')
            return item
        safe = re.sub(r'[^A-Za-z0-9._-]+', '-', str(key))[:60] or 'item'
        attachments.append(Attachment(
            name=safe, filename=f'cdeadmin-{alert.id[:8]}-{safe}.{fmt}',
            media_type=MEDIA_TYPES[fmt], format=fmt,
            content=exported['content'], result_id=result['result_id']))
        item['bytes'] = len(exported['content'])
        return item

    # ------------------------------------------------------------------
    # row-policy guard
    # ------------------------------------------------------------------
    def _policy_bound(self, alert):
        """Is the content limited by a semantic row/tenant policy?"""
        try:
            if alert.resource_type == 'question':
                return self._question_bound(
                    alert.user_id, alert.endpoint_id, alert.resource_id,
                    alert.resource_revision)
            board = self.dashboards.revision(
                alert.user_id, alert.endpoint_id, alert.resource_id,
                alert.resource_revision)['definition']
            return any(
                self._question_bound(
                    alert.user_id, alert.endpoint_id,
                    card['question']['question_id'],
                    card['question']['revision'])
                for card in board['cards'] if card['type'] == 'question')
        except Exception:
            return True  # fail closed

    def _question_bound(self, user_id, endpoint_id, question_id, revision):
        stored = self.bi.stored_for_run(user_id, endpoint_id, question_id,
                                        revision)
        definition = stored['definition']
        if definition.get('semantic_model') is None:
            return False
        model = self.bi._semantic_definition(
            stored['owner_id'], endpoint_id, definition['semantic_model'])
        security = model.get('security') or {}
        return bool(security.get('row_filters') or
                    security.get('tenant_filter'))

    # ------------------------------------------------------------------
    # workspace actions
    # ------------------------------------------------------------------
    ACTIONS = frozenset({
        'bi_alert_catalog', 'bi_alert_schedule_preview', 'bi_alert_list',
        'bi_alert_get', 'bi_alert_create', 'bi_alert_update',
        'bi_alert_delete', 'bi_alert_test', 'bi_alert_run_now',
        'bi_alert_mute', 'bi_alert_unmute', 'bi_alert_rearm',
        'bi_alert_pause', 'bi_alert_resume', 'bi_alert_history',
        'bi_notification_list', 'bi_notification_read',
    })

    def handle(self, action, request, *, user_id, endpoint_id, server=None,
               runtime=None):
        """Dispatch one ``bi_alert_*`` / ``bi_notification_*`` action.

        ``runtime`` is a zero-argument callable returning the caller's own
        ``(provider, context, endpoint)``; it is only called for a dry run.
        """
        aid = request.get('alert_id')
        if action == 'bi_alert_catalog':
            return self.catalog(user_id)
        if action == 'bi_alert_schedule_preview':
            return self.schedule_preview(request.get('schedule'),
                                         request.get('count', 5))
        if action == 'bi_alert_list':
            return {'items': self.list(
                user_id, endpoint_id, request.get('resource_type'),
                request.get('resource_id'), request.get('kind'))}
        if action == 'bi_alert_get':
            return self.get(user_id, endpoint_id, aid)
        if action == 'bi_alert_create':
            return self.create(user_id, endpoint_id, request.get('alert'),
                               server)
        if action == 'bi_alert_update':
            return self.update(user_id, endpoint_id, aid,
                               request.get('expected_revision'),
                               request.get('alert'))
        if action == 'bi_alert_delete':
            return self.delete(user_id, endpoint_id, aid)
        if action == 'bi_alert_test':
            return self.test(user_id, endpoint_id, runtime=runtime(),
                             value=request.get('alert'), alert_id=aid)
        if action == 'bi_alert_run_now':
            return self.run_now(user_id, endpoint_id, aid)
        if action == 'bi_alert_mute':
            return self.mute(user_id, endpoint_id, aid,
                             request.get('until'),
                             request.get('duration_minutes'))
        if action == 'bi_alert_unmute':
            return self.unmute(user_id, endpoint_id, aid)
        if action == 'bi_alert_rearm':
            return self.rearm(user_id, endpoint_id, aid)
        if action == 'bi_alert_pause':
            return self.pause(user_id, endpoint_id, aid)
        if action == 'bi_alert_resume':
            return self.resume(user_id, endpoint_id, aid, server,
                               bool(request.get('reset')))
        if action == 'bi_alert_history':
            return {'items': self.history(user_id, endpoint_id, aid,
                                          request.get('limit', 50))}
        if action == 'bi_notification_list':
            return self.notifications(user_id, endpoint_id,
                                      request.get('unread_only', False),
                                      request.get('limit', 50))
        if action == 'bi_notification_read':
            return self.mark_read(user_id, endpoint_id, request.get('ids'))
        raise AlertError('BI action is unavailable')


def init_app(app, bi_service, endpoint_service, report_scheduler,
             delivery_service):
    """Install the alert service next to the report scheduler."""
    existing = app.extensions.get(APP_EXTENSION_KEY)
    if existing is not None:
        return existing
    from .alert_scheduler import BIAlertScheduler, BIAlertWorker
    from .alert_store import DatabaseAlertRepository
    from .webhook import WebhookChannel
    config = {
        'max_message_rows': app.config.get('CDEADMIN_BI_ALERT_MESSAGE_ROWS',
                                           DEFAULTS['max_message_rows']),
        'min_interval_seconds': app.config.get(
            'CDEADMIN_BI_ALERT_MIN_INTERVAL_SECONDS',
            DEFAULTS['min_interval_seconds']),
        'max_alerts_per_user': app.config.get(
            'CDEADMIN_BI_ALERT_MAX_PER_USER',
            DEFAULTS['max_alerts_per_user']),
        'external_recipients': app.config.get(
            'CDEADMIN_BI_EXTERNAL_RECIPIENTS', {}),
    }
    webhook = WebhookChannel(
        app.config.get('CDEADMIN_BI_WEBHOOK_HOSTS', {}),
        timeout=app.config.get('CDEADMIN_BI_WEBHOOK_TIMEOUT', 5))
    repository = DatabaseAlertRepository()
    service = BIAlertService(
        bi_service, repository, delivery=delivery_service, webhook=webhook,
        config=config)
    if report_scheduler is not None:
        def expired(alert):
            service._pause(alert, 'delegation_expired', revoke=False)

        scheduler = BIAlertScheduler(
            endpoint_service, report_scheduler.security_service,
            report_scheduler.key_ring,
            lease_seconds=report_scheduler.lease_seconds,
            max_lateness_seconds=report_scheduler.max_lateness_seconds,
            on_expired=expired)
        service.scheduler = scheduler
        service.worker = BIAlertWorker(scheduler, service)
        from pgadmin.cdeadmin.report_scheduler import register_companion
        register_companion(app, 'bi_alerts', service.worker.run_once)
    app.extensions[APP_EXTENSION_KEY] = service
    return service


__all__ = ('BIAlertService', 'FAILURE_TEXT', 'init_app')
