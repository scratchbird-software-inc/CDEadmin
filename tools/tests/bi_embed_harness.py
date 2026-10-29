##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Fakes and a ready-made stack for the BI embedding tests.

Everything above the driver is real: ``BIAccess`` / ``BIService`` /
``DashboardService`` / ``BIExecutor`` over SQLite or DuckDB, the real
``BIEmbedService``, token code, the real unauthenticated blueprint and the
real ``WorkerKeyRing``.  Only the persistence of embeds, the scheduler's
database and the clock are replaced, and a Flask application mimics the two
things pgAdmin adds around every response (security headers and a session
that tries to set a cookie).
"""

from __future__ import annotations

import base64
import importlib.util
import os
import secrets
import sys
import types
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from bi_live_harness import ROOT
from bi_permissions_harness import OWNER, SharedStack

from pgadmin.cdeadmin.bi import embed_tokens as tokens
from pgadmin.cdeadmin.bi.embeds import BIEmbedService
from pgadmin.cdeadmin.bi.models import BIError
from pgadmin.cdeadmin.report_scheduler.crypto import WorkerKeyRing
from pgadmin.cdeadmin.report_scheduler.models import (
    ReportSchedulerAccessError,
)

ORIGINS = ['https://app.example.com', 'https://portal.example.org:8443']
NOT_FOUND = b'{"success":0,"errormsg":"Not found"}'


class EmbedClock:
    """A settable UTC clock (aware datetimes, like ``datetime.now(utc)``)."""

    def __init__(self):
        self.now = datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)

    def naive(self):
        return self.now.replace(tzinfo=None)

    def epoch(self):
        return int(self.now.timestamp())


class MemoryEmbedRepository:
    """Same contract as ``DatabaseEmbedRepository``."""

    def __init__(self):
        self.rows, self.key_rows = {}, []
        self.used, self.counters = {}, {}

    @staticmethod
    def new(**values):
        return SimpleNamespace(**values)

    def add(self, row):
        for other in self.rows.values():
            if (other.user_id, other.endpoint_id, other.name) == (
                    row.user_id, row.endpoint_id, row.name):
                raise BIError('an embed with this name already exists')
        self.rows[row.id] = row
        return row

    def get(self, embed_id):
        if not isinstance(embed_id, str) or len(embed_id) != 36:
            return None
        return self.rows.get(embed_id)

    def list(self, endpoint_id, *, resource_type=None, resource_id=None,
             user_id=None):
        return sorted([
            r for r in self.rows.values() if r.endpoint_id == endpoint_id
            and (resource_type is None or r.resource_type == resource_type)
            and (resource_id is None or r.resource_id == resource_id)
            and (user_id is None or r.user_id == user_id)],
            key=lambda r: r.name)

    def count(self, user_id, endpoint_id):
        return sum(1 for r in self.rows.values()
                   if (r.user_id, r.endpoint_id) == (user_id, endpoint_id))

    def save(self, row):
        for other in self.rows.values():
            if other is not row and (other.user_id, other.endpoint_id,
                                     other.name) == (
                    row.user_id, row.endpoint_id, row.name):
                raise BIError('an embed with this name already exists')
        self.rows[row.id] = row
        return row

    def delete(self, row):
        self._forget(row.id)
        self.rows.pop(row.id, None)

    def _forget(self, embed_id):
        self.key_rows = [k for k in self.key_rows if k.embed_id != embed_id]
        self.used = {k: v for k, v in self.used.items() if k[0] != embed_id}
        self.counters = {k: v for k, v in self.counters.items()
                         if k[0] != embed_id}

    def purge_resource(self, resource_type, resource_id):
        gone = [r.id for r in self.rows.values()
                if (r.resource_type, r.resource_id) == (
                    resource_type, resource_id)]
        for embed_id in gone:
            self._forget(embed_id)
            del self.rows[embed_id]
        return gone

    def keys(self, embed_id):
        return [k for k in self.key_rows if k.embed_id == embed_id]

    def install_key(self, embed_id, *, kid, key_id, encrypted_value, now):
        self.key_rows = [k for k in self.key_rows
                         if not (k.embed_id == embed_id and
                                 k.slot == 'previous')]
        for key in self.key_rows:
            if key.embed_id == embed_id:
                key.slot = 'previous'
        self.key_rows.append(SimpleNamespace(
            id=str(uuid.uuid4()), embed_id=embed_id, kid=kid,
            slot='current', key_id=key_id, encrypted_value=encrypted_value,
            created_at=now))

    def drop_previous(self, embed_id):
        before = len(self.key_rows)
        self.key_rows = [k for k in self.key_rows
                         if not (k.embed_id == embed_id and
                                 k.slot == 'previous')]
        return before - len(self.key_rows)

    def drop_keys(self, embed_id):
        before = len(self.key_rows)
        self.key_rows = [k for k in self.key_rows if k.embed_id != embed_id]
        return before - len(self.key_rows)

    def save_keys(self):
        return None

    def all_keys(self):
        return list(self.key_rows)

    def consume_jti(self, embed_id, jti, expires_at, now):
        self.used = {k: v for k, v in self.used.items() if v >= now}
        if (embed_id, jti) in self.used:
            return False
        self.used[(embed_id, jti)] = expires_at
        return True

    def jti_consumed(self, embed_id, jti, now):
        return self.used.get((embed_id, jti), datetime.min) >= now

    def bump(self, embed_id, day, *, views=0, card_runs=0, errors=0):
        row = self.counters.setdefault((embed_id, day), [0, 0, 0])
        row[0] += views
        row[1] += card_runs
        row[2] += errors

    def stats(self, embed_id, since_day):
        return [{'day': day, 'views': v, 'card_runs': c, 'errors': e}
                for (eid, day), (v, c, e) in sorted(self.counters.items())
                if eid == embed_id and day >= since_day]


class FakeScheduler:
    """The scheduler surface ``BIEmbedService`` uses."""

    def __init__(self, stack, ring, clock):
        self.stack, self.key_ring, self.clock = stack, ring, clock
        self.delegations = {}
        self.runtime_error = None
        self.runtimes = []

    def delegation_for(self, embed_id):
        return self.delegations.get(embed_id)

    def authorize_embed(self, server, embed, expires_in_days):
        if server is None or server.user_id != embed.user_id:
            raise ReportSchedulerAccessError('only the owner can authorize')
        row = SimpleNamespace(
            id=str(uuid.uuid4()), embed_id=embed.id, state='active',
            user_id=embed.user_id, endpoint_id=embed.endpoint_id,
            expires_at=self.clock.naive() + timedelta(days=expires_in_days))
        self.delegations[embed.id] = row
        return row

    def revoke_embed(self, embed_id):
        row = self.delegations.get(embed_id)
        if row is not None:
            row.state = 'revoked'
        return row

    def runtime(self, delegation):
        if self.runtime_error is not None:
            raise self.runtime_error
        if delegation.state != 'active' or (
                delegation.expires_at <= self.clock.naive()):
            raise ReportSchedulerAccessError('delegation is inactive')
        self.runtimes.append(delegation.id)
        endpoint = {'route': {'credential_owner': delegation.user_id,
                              'delegated': delegation.id}}
        return self.stack.provider, self.stack.ctx, endpoint


def security_headers():
    """pgAdmin's real ``SecurityHeaders`` over a stand-in ``config``."""
    config = types.ModuleType('config')
    config.X_FRAME_OPTIONS = 'SAMEORIGIN'
    config.STRICT_TRANSPORT_SECURITY_ENABLED = False
    config.STRICT_TRANSPORT_SECURITY = ''
    config.CONTENT_SECURITY_POLICY = "default-src 'self'; frame-ancestors 'self'"
    config.X_CONTENT_TYPE_OPTIONS = 'nosniff'
    config.X_XSS_PROTECTION = '1; mode=block'
    config.WEB_SERVER = 'Python'
    config.CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
    previous = sys.modules.get('config')
    sys.modules['config'] = config
    try:
        spec = importlib.util.spec_from_file_location(
            'embed_test_security_headers',
            ROOT / 'web/pgadmin/utils/security_headers.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            del sys.modules['config']
        else:
            sys.modules['config'] = previous
    return module.SecurityHeaders


class EmbedStack:
    """Wiring shared by every embedding test."""

    def __init__(self, engine='sqlite', *, config=None, enabled=True,
                 ring=True):
        from flask import Flask, request, session
        from pgadmin.cdeadmin.bi import embed_public

        self.s = SharedStack(engine, f'embed-{engine}')
        self.ep = self.s.endpoint_id
        self.clock = EmbedClock()
        self.mono = [1000.0]
        self.ring = WorkerKeyRing(
            {'ring1': base64.b64encode(os.urandom(32)).decode('ascii')},
            'ring1') if ring else WorkerKeyRing()
        self.repo = MemoryEmbedRepository()
        self.scheduler = FakeScheduler(self.s, self.ring, self.clock)
        settings = {'enabled': enabled, 'ip_rate': (1000, 1000.0),
                    'embed_rate': (1000, 1000.0)}
        settings.update(config or {})
        self.service = BIEmbedService(
            self.s.bi, self.repo, executor=self.s.executor,
            dashboards=self.s.dashboards, scheduler=self.scheduler,
            key_ring=self.ring, config=settings, clock=self.clock,
            monotonic=lambda: self.mono[0])
        self.seen_cookies = []
        app = Flask('embed-test')
        app.secret_key = 'test-secret'
        guard = security_headers()

        @app.before_request
        def a_session_that_wants_a_cookie():
            self.seen_cookies.append(dict(request.cookies))
            session['paranoid'] = 'token'

        @app.after_request
        def application_headers(response):
            guard.set_response_headers(response)
            return response

        self.app = app
        embed_public.register(app, self.service)
        self.client = app.test_client()

    # management helpers -------------------------------------------------------
    def definition(self, resource_type, resource_id, **extra):
        value = {
            'name': 'Embed ' + resource_id[:6],
            'resource': {'type': resource_type, 'id': resource_id,
                         'revision': None},
            'parameters': [], 'claims': [], 'origins': list(ORIGINS),
            'max_token_lifetime_seconds': 600,
        }
        value.update(extra)
        return value

    def create(self, resource_type, resource_id, user=OWNER, *,
               enable=True, **extra):
        made = self.service.create(
            user, self.ep, self.definition(resource_type, resource_id,
                                           **extra))
        embed, secret = made['embed'], made['secret']
        if enable:
            embed = self.service.enable(
                user, self.ep, embed['embed_id'],
                SimpleNamespace(user_id=user))
        return embed, secret

    def token(self, embed_id, secret, *, params=None, claims=None,
              ttl=300, kid=None, **payload):
        now = self.clock.epoch()
        body = {'aud': embed_id, 'iat': now, 'exp': now + ttl}
        if params is not None:
            body['params'] = params
        if claims is not None:
            body['claims'] = claims
        body.update(payload)
        return tokens.sign(secret['secret'], kid or secret['kid'], body)

    # http helpers -----------------------------------------------------------
    def get(self, embed_id, path, token, **kwargs):
        return self.client.get(
            f'/cdeadmin/embed/{embed_id}{path}',
            headers={'Authorization': f'Bearer {token}'}, **kwargs)

    def post(self, embed_id, path, token, body=None, **kwargs):
        return self.client.post(
            f'/cdeadmin/embed/{embed_id}{path}', json=body or {},
            headers={'Authorization': f'Bearer {token}'}, **kwargs)

    def frame(self, embed_id, token):
        return self.client.get(
            f'/cdeadmin/embed/{embed_id}/frame', query_string={'token': token})


def rows_of(response):
    return response.get_json()['data']['rows']


def random_id():
    return str(uuid.uuid4())


__all__ = (
    'EmbedClock', 'EmbedStack', 'FakeScheduler', 'MemoryEmbedRepository',
    'NOT_FOUND', 'ORIGINS', 'OWNER', 'rows_of', 'secrets',
)
