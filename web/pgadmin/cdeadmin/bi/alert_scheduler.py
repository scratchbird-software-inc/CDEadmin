##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""BI alerts on the report scheduler's cron, lease and credential machinery.

Nothing is re-implemented.  ``BIAlertScheduler`` is the report scheduler
service pointed at the alert tables (they have the same shape), with its own
resolver id and envelope schema.  ``BIAlertWorker`` is the report worker with
a different body for one claimed occurrence.
"""

from __future__ import annotations

import json
import uuid

from pgadmin.cdeadmin.report_scheduler.models import (
    ReportSchedulerAccessError, ReportSchedulerConflict, ReportSchedulerError,
)
from pgadmin.cdeadmin.report_scheduler.service import (
    DatabaseReportSchedulerRepository, ReportSchedulerService, _now,
)
from pgadmin.cdeadmin.report_scheduler.worker import ReportSchedulerWorker

BI_RESOLVER_ID = 'cdeadmin.delegated-bi-alert-worker'
BI_AAD_SCHEMA = 'cdeadmin.bi-alert-credential.v1'
BI_MODELS = {
    'credential': 'BIAlertCredential',
    'delegation': 'BIAlertDelegation',
    'occurrence': 'BIAlertOccurrence',
}


class BIAlertScheduler(ReportSchedulerService):
    """The report scheduler, serving alert delegations."""

    resolver_id = BI_RESOLVER_ID
    aad_schema = BI_AAD_SCHEMA
    credential_model = 'BIAlertCredential'

    def __init__(self, endpoint_service, security_service, key_ring, *,
                 lease_seconds=300, max_lateness_seconds=3600,
                 repository=None, on_expired=None):
        super().__init__(
            endpoint_service, security_service, None, None,
            key_ring=key_ring,
            repository=repository or DatabaseReportSchedulerRepository(
                BI_MODELS),
            lease_seconds=lease_seconds,
            max_lateness_seconds=max_lateness_seconds)
        self.on_expired = on_expired

    # delegation -------------------------------------------------------------
    def delegation_for(self, alert_id):
        return self.repository.delegation.query.filter_by(
            alert_id=alert_id).first()

    def authorize_alert(self, server, alert, expires_in_days):
        """Capture the owner's credentials for unattended runs."""
        self._require_authority(expires_in_days)
        if server.user_id != alert.user_id:
            raise ReportSchedulerAccessError(
                'only the alert owner can authorize unattended runs')
        endpoint = server.endpoint_profile
        if endpoint is None or endpoint.id != alert.endpoint_id:
            raise ReportSchedulerAccessError(
                'the alert belongs to another endpoint')

        def create(now):
            from pgadmin.model import BIAlertDelegation
            row = BIAlertDelegation(
                id=str(uuid.uuid4()), alert_id=alert.id,
                user_id=alert.user_id, endpoint_id=endpoint.id,
                state='active', credential_generation=1, created_at=now)
            row.endpoint = endpoint
            return row

        return self._delegate(
            server, lambda: self.delegation_for(alert.id), create,
            lambda _row: None, expires_in_days)

    def revoke_alert(self, alert_id):
        row = self.delegation_for(alert_id)
        if row is not None and row.state == 'active':
            self.repository.revoke(row, _now())
        return row

    def runtime(self, delegation):
        """``(provider, context, endpoint)`` built from delegated authority."""
        context, endpoint = self.delegated_workspace(delegation)
        binding = self.endpoint_service.provider_registry.resolve(context)
        return binding.instance, context, endpoint

    # hooks of the shared enqueue loop -------------------------------------------
    def _schedule_for(self, row):
        alert = row.alert
        if alert is None or alert.status != 'active':
            raise ReportSchedulerError('alert is not active')
        return json.loads(alert.definition)['schedule']

    @staticmethod
    def _schedule_base(row, latest):
        anchor = row.alert.schedule_anchor
        if latest is not None and latest.scheduled_for > anchor:
            return latest.scheduled_for
        return anchor

    def _expired(self, row):
        if self.on_expired is not None:
            self.on_expired(row.alert)


class BIAlertWorker(ReportSchedulerWorker):
    """Runs claimed alert occurrences; claim, lease and recovery are shared."""

    def __init__(self, scheduler, alerts, *, poll_interval=0.1,
                 max_polls=600):
        super().__init__(scheduler, None, None, None, None,
                         poll_interval=poll_interval, max_polls=max_polls)
        self.alerts = alerts

    def _execute(self, occurrence, token):
        delegation = occurrence.delegation
        trigger = 'run_now' if (occurrence.claimed_by or '').startswith(
            'run-now:') else 'schedule'
        self.scheduler.transition(
            occurrence.id, token, 'executing', 'executing',
            progress=json.dumps({'completed': 0, 'total': 1}))

        def delivering():
            self._require_not_cancelled(occurrence.id)
            self.scheduler.transition(
                occurrence.id, token, 'delivering', 'delivering',
                progress=json.dumps({'completed': 0, 'total': 1}))

        def heartbeat(progress=None):
            self.scheduler.heartbeat(occurrence.id, token, progress or {
                'completed': 0, 'total': 1})

        self._require_not_cancelled(occurrence.id)
        outcome = self.alerts.run_delegated(
            delegation, trigger=trigger, delivering=delivering,
            heartbeat=heartbeat)
        values = {}
        if outcome.get('delivery_ids'):
            values['delivery_occurrence_ids'] = json.dumps(
                outcome['delivery_ids'])
        if outcome.get('error_code'):
            values['error_type'] = outcome['error_code']
        self.scheduler.transition(
            occurrence.id, token, outcome['state'], outcome['phase'],
            progress=json.dumps({'completed': 1, 'total': 1}), **values)
        return outcome['state']


__all__ = (
    'BIAlertScheduler', 'BIAlertWorker', 'ReportSchedulerAccessError',
    'ReportSchedulerConflict',
)
