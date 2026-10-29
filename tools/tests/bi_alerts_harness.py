##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Fakes and a ready-made stack for the BI alert and subscription tests.

Everything above the driver is real: ``BIAccess`` / ``BIService`` /
``DashboardService`` / ``BIExecutor`` over SQLite or DuckDB, the real
``ReportDeliveryService`` (with recording transports), the real
``WebhookChannel`` (with a stubbed resolver and transport) and the real
``BIAlertService``.  Only the persistence of alerts, the scheduler's database
and the clock are replaced.
"""

from __future__ import annotations

import socket
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from bi_permissions_harness import OWNER, SharedStack
from test_cdeadmin_report_delivery import (
    MemoryRepository as DeliveryRepository, SuccessfulAdapter, s3_profile,
    smtp_profile,
)

from pgadmin.cdeadmin.bi.alerts import BIAlertService
from pgadmin.cdeadmin.bi.webhook import WebhookChannel
from pgadmin.cdeadmin.report_delivery import ReportDeliveryService
from pgadmin.cdeadmin.report_scheduler.models import (
    ReportSchedulerAccessError, ReportSchedulerConflict,
    ReportSchedulerError,
)

HOOK_HOST = 'hooks.example.com'
HOOK_SECRET = 'whsec_0123456789abcdef0123456789abcdef'
EVERY_HOUR = {'expression': '0 * * * *', 'timezone': 'UTC'}


class AlertClock:
    """A settable UTC clock (aware datetimes, like ``datetime.now(utc)``)."""

    def __init__(self):
        self.now = datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)

    def naive(self):
        return self.now.replace(tzinfo=None)


class MemoryAlertRepository:
    """Same contract as ``DatabaseAlertRepository``."""

    def __init__(self):
        self.alerts, self.event_rows, self.note_rows = {}, [], []

    def new(self, **values):
        return SimpleNamespace(**values)

    def add(self, row):
        for other in self.alerts.values():
            if (other.user_id, other.endpoint_id, other.kind,
                    other.name) == (row.user_id, row.endpoint_id, row.kind,
                                    row.name):
                from pgadmin.cdeadmin.bi.models import BIError
                raise BIError('an alert or subscription with this name '
                              'already exists')
        self.alerts[row.id] = row
        return row

    def get(self, alert_id):
        if not isinstance(alert_id, str):
            return None
        return self.alerts.get(alert_id)

    def list(self, endpoint_id, *, resource_type=None, resource_id=None,
             user_id=None, kind=None):
        rows = [r for r in self.alerts.values()
                if r.endpoint_id == endpoint_id and
                (resource_type is None or r.resource_type == resource_type)
                and (resource_id is None or r.resource_id == resource_id)
                and (user_id is None or r.user_id == user_id)
                and (kind is None or r.kind == kind)]
        return sorted(rows, key=lambda r: r.name)

    def count(self, user_id, endpoint_id):
        return sum(1 for r in self.alerts.values()
                   if (r.user_id, r.endpoint_id) == (user_id, endpoint_id))

    def save(self, row):
        self.alerts[row.id] = row
        return row

    def update_state(self, alert_id, **values):
        row = self.alerts[alert_id]
        for key, value in values.items():
            setattr(row, key, value)

    def delete(self, row):
        self.alerts.pop(row.id, None)
        self.event_rows = [e for e in self.event_rows
                           if e.alert_id != row.id]

    def add_event(self, **values):
        row = SimpleNamespace(id=str(uuid.uuid4()), **values)
        self.event_rows.append(row)
        return row

    def events(self, alert_id, limit=50):
        rows = [e for e in self.event_rows if e.alert_id == alert_id]
        return list(reversed(rows))[:limit]

    def prune_events(self, alert_id, keep):
        rows = [e for e in self.event_rows if e.alert_id == alert_id]
        drop = rows[:-keep] if keep else rows
        self.event_rows = [e for e in self.event_rows if e not in drop]
        return len(drop)

    def add_notification(self, **values):
        row = SimpleNamespace(id=str(uuid.uuid4()), **values)
        self.note_rows.append(row)
        return row

    def _mine(self, user_id, endpoint_id):
        return [n for n in self.note_rows
                if (n.user_id, n.endpoint_id) == (user_id, endpoint_id)]

    def notifications(self, user_id, endpoint_id, *, unread_only=False,
                      limit=50):
        rows = [n for n in self._mine(user_id, endpoint_id)
                if not unread_only or n.read_at is None]
        return list(reversed(rows))[:limit]

    def unread_count(self, user_id, endpoint_id):
        return sum(1 for n in self._mine(user_id, endpoint_id)
                   if n.read_at is None)

    def mark_read(self, user_id, endpoint_id, ids, now):
        count = 0
        for note in self._mine(user_id, endpoint_id):
            if note.read_at is None and (ids is None or note.id in ids):
                note.read_at = now
                count += 1
        return count

    def prune_notifications(self, user_id, endpoint_id, keep):
        mine = self._mine(user_id, endpoint_id)
        drop = mine[:-keep] if keep else mine
        self.note_rows = [n for n in self.note_rows if n not in drop]
        return len(drop)


class FakeScheduler:
    """The scheduler's surface that ``BIAlertService`` uses."""

    def __init__(self, stack, clock):
        self.stack, self.clock = stack, clock
        self.available = True
        self.delegations = {}
        self.runtime_error = None
        self.enqueued, self.occurrences = [], {}
        self.repository = SimpleNamespace(enqueue=self._enqueue)

    def delegation_for(self, alert_id):
        return self.delegations.get(alert_id)

    def authorize_alert(self, server, alert, expires_in_days):
        if server is None or server.user_id != alert.user_id:
            raise ReportSchedulerAccessError('only the owner can authorize')
        row = SimpleNamespace(
            id=str(uuid.uuid4()), alert=alert, alert_id=alert.id,
            state='active', user_id=alert.user_id,
            endpoint_id=alert.endpoint_id,
            expires_at=self.clock.naive() + timedelta(days=expires_in_days))
        self.delegations[alert.id] = row
        return row

    def revoke_alert(self, alert_id):
        row = self.delegations.get(alert_id)
        if row is not None:
            row.state = 'revoked'
        return row

    def runtime(self, delegation):
        if self.runtime_error is not None:
            raise self.runtime_error
        if delegation.state != 'active' or (
                delegation.expires_at <= self.clock.naive()):
            raise ReportSchedulerAccessError('delegation is inactive')
        return (self.stack.provider, self.stack.ctx,
                self.stack.endpoint_for(delegation.user_id))

    def _enqueue(self, delegation_id, scheduled_for):
        key = (delegation_id, scheduled_for)
        if key in self.enqueued:
            return None, False
        self.enqueued.append(key)
        occurrence = SimpleNamespace(id=f'occ-{len(self.enqueued)}',
                                     delegation_id=delegation_id)
        self.occurrences[occurrence.id] = occurrence
        return occurrence, True

    def claim(self, worker_id, occurrence_id=None):
        return self.occurrences[occurrence_id], 'token'


class FakeWorker:
    def __init__(self, service, scheduler):
        self.service, self.scheduler = service, scheduler
        self.runs = []

    def run_claimed(self, occurrence, token):
        delegation = next(d for d in self.scheduler.delegations.values()
                          if d.id == occurrence.delegation_id)
        outcome = self.service.run_delegated(delegation, trigger='run_now')
        self.runs.append(outcome)
        return outcome['state']


class StubResolver:
    """Records lookups; ``answers`` maps a host to a list (or a callable)."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, host, port, type=None):
        self.calls.append(host)
        answer = self.answers[host]
        if callable(answer):
            answer = answer(len(self.calls))
        return [(socket.AF_INET6 if ':' in ip else socket.AF_INET,
                 socket.SOCK_STREAM, 6, '', (ip, port)) for ip in answer]


class StubTransport:
    """A webhook transport that records posts and answers with a status."""

    def __init__(self, status=200):
        self.status, self.posts, self.error = status, [], None

    def post(self, **kwargs):
        self.posts.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.status


class AlertStack:
    """Wiring shared by every alert test."""

    def __init__(self, engine='sqlite', *, config=None, external=None,
                 webhook_answers=None):
        self.s = SharedStack(engine, f'alerts-{engine}')
        self.ep = self.s.endpoint_id
        self.clock = AlertClock()
        self.repo = MemoryAlertRepository()
        self.scheduler = FakeScheduler(self.s, self.clock)
        self.smtp, self.s3 = SuccessfulAdapter(), SuccessfulAdapter()
        mail = {**smtp_profile(), 'allowed_formats': ['json', 'csv', 'xlsx'],
                'allowed_domains': ['corp.example', 'partner.example']}
        archive = {**s3_profile(), 'allowed_formats': ['json', 'csv']}
        self.delivery = ReportDeliveryService(
            {'mail': mail, 'archive': archive}, DeliveryRepository(),
            adapters={'smtp': self.smtp, 's3': self.s3})
        self.resolver = StubResolver(webhook_answers or {
            HOOK_HOST: ['93.184.216.34']})
        self.transport = StubTransport()
        self.webhook = WebhookChannel(
            {HOOK_HOST: {'secret': HOOK_SECRET, 'key_id': 'k1'}},
            resolver=self.resolver, transport=self.transport,
            clock=lambda: self.clock.now.timestamp())
        self.service = BIAlertService(
            self.s.bi, self.repo, executor=self.s.executor,
            dashboards=self.s.dashboards, delivery=self.delivery,
            webhook=self.webhook, scheduler=self.scheduler,
            config={'external_recipients': external or {}, **(config or {})},
            clock=self.clock)
        self.worker = FakeWorker(self.service, self.scheduler)
        self.service.worker = self.worker

    # helpers ---------------------------------------------------------------
    def create(self, definition, user=OWNER):
        return self.service.create(user, self.ep, definition,
                                   SimpleNamespace(user_id=user))

    def run(self, alert_id, trigger='schedule'):
        delegation = self.scheduler.delegation_for(alert_id)
        return self.service.run_delegated(delegation, trigger=trigger)

    def events(self, alert_id):
        return list(reversed(self.repo.events(alert_id, 200)))

    def notes(self, user):
        return self.repo.note_rows and [
            n for n in self.repo.note_rows if n.user_id == user] or []

    def runtime(self, user=OWNER):
        return (self.s.provider, self.s.ctx, self.s.endpoint_for(user))


def alert_definition(question_id, condition, *, name='Revenue watch',
                     channels=None, **extra):
    value = {
        'kind': 'alert', 'name': name,
        'resource': {'type': 'question', 'id': question_id},
        'schedule': dict(EVERY_HOUR), 'condition': condition,
        'channels': channels if channels is not None else [
            {'type': 'in_app', 'recipients': [{'type': 'self'}]}],
    }
    value.update(extra)
    return value


def subscription_definition(resource_type, resource_id, *, name='Digest',
                            fmt=None, channels=None, **extra):
    value = {
        'kind': 'subscription', 'name': name,
        'resource': {'type': resource_type, 'id': resource_id},
        'schedule': dict(EVERY_HOUR), 'format': fmt,
        'channels': channels if channels is not None else [
            {'type': 'in_app', 'recipients': [{'type': 'self'}]}],
    }
    value.update(extra)
    return value


def rows_over(count):
    return {'type': 'metric', 'metric': {'kind': 'row_count'},
            'operator': '>', 'value': count}


def column_metric(column, aggregate, operator, value, against='constant'):
    return {'type': 'metric', 'against': against,
            'metric': {'kind': 'column', 'column': column,
                       'aggregate': aggregate},
            'operator': operator, 'value': value}


__all__ = (
    'AlertClock', 'AlertStack', 'EVERY_HOUR', 'FakeScheduler', 'HOOK_HOST',
    'HOOK_SECRET', 'MemoryAlertRepository', 'ReportSchedulerAccessError',
    'ReportSchedulerConflict', 'ReportSchedulerError', 'StubResolver',
    'StubTransport', 'alert_definition', 'column_metric', 'rows_over',
    'subscription_definition',
)
