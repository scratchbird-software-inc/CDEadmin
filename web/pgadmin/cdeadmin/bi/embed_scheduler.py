##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Run-as delegation of an embed on the report scheduler's credential code.

Nothing is re-implemented.  ``BIEmbedScheduler`` is the report scheduler
service pointed at the embed delegation tables (shaped like the alert ones),
with its own resolver id and envelope schema, so an envelope captured for an
embed never decrypts for an alert or a report and the other way round.  It
never enqueues or claims anything: an embed is not scheduled, it is called
by a verified token, and ``runtime`` rebuilds the owner's generation-bound
endpoint from the delegated envelopes for that call only.
"""

from __future__ import annotations

import uuid

from pgadmin.cdeadmin.report_scheduler.models import (
    ReportSchedulerAccessError,
)
from pgadmin.cdeadmin.report_scheduler.service import (
    DatabaseReportSchedulerRepository, ReportSchedulerService, _now,
)

EMBED_RESOLVER_ID = 'cdeadmin.delegated-bi-embed-worker'
EMBED_AAD_SCHEMA = 'cdeadmin.bi-embed-credential.v1'


class EmbedDelegationRepository(DatabaseReportSchedulerRepository):
    """The shared repository without the occurrence table (no scheduling)."""

    def __init__(self):
        import pgadmin.model as model_module
        self.db = model_module.db
        self.credential = model_module.BIEmbedCredential
        self.delegation = model_module.BIEmbedDelegation
        self.occurrence = None

    def revoke(self, row, now):
        row.state = 'revoked'
        row.revoked_at = now
        row.updated_at = now
        for credential in list(row.credentials):
            self.db.session.delete(credential)
        self.db.session.commit()

    def expire(self, row, now):
        row.state = 'expired'
        row.updated_at = now
        for credential in list(row.credentials):
            self.db.session.delete(credential)
        self.db.session.commit()


class BIEmbedScheduler(ReportSchedulerService):
    """The report scheduler's credential machinery, serving embeds."""

    resolver_id = EMBED_RESOLVER_ID
    aad_schema = EMBED_AAD_SCHEMA
    credential_model = 'BIEmbedCredential'

    def __init__(self, endpoint_service, security_service, key_ring, *,
                 repository=None):
        super().__init__(
            endpoint_service, security_service, None, None,
            key_ring=key_ring,
            repository=repository or EmbedDelegationRepository())

    def delegation_for(self, embed_id):
        return self.repository.delegation.query.filter_by(
            embed_id=embed_id).first()

    def authorize_embed(self, server, embed, expires_in_days):
        """Capture the owner's credentials for token-called runs."""
        self._require_authority(expires_in_days)
        if server.user_id != embed.user_id:
            raise ReportSchedulerAccessError(
                'only the embed owner can authorize embedded runs')
        endpoint = server.endpoint_profile
        if endpoint is None or endpoint.id != embed.endpoint_id:
            raise ReportSchedulerAccessError(
                'the embed belongs to another endpoint')

        def create(now):
            from pgadmin.model import BIEmbedDelegation
            row = BIEmbedDelegation(
                id=str(uuid.uuid4()), embed_id=embed.id,
                user_id=embed.user_id, endpoint_id=endpoint.id,
                state='active', credential_generation=1, created_at=now)
            row.endpoint = endpoint
            return row

        return self._delegate(
            server, lambda: self.delegation_for(embed.id), create,
            lambda _row: None, expires_in_days)

    def revoke_embed(self, embed_id):
        row = self.delegation_for(embed_id)
        if row is not None and row.state == 'active':
            self.repository.revoke(row, _now())
        return row

    def runtime(self, delegation):
        """``(provider, context, endpoint)`` built from delegated authority."""
        context, endpoint = self.delegated_workspace(delegation)
        binding = self.endpoint_service.provider_registry.resolve(context)
        return binding.instance, context, endpoint


__all__ = ('BIEmbedScheduler', 'EmbedDelegationRepository')
