##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""In-memory grant store, principal directory and a multi-user BI stack.

The stack keeps everything above the driver real (``BIAccess``, ``BIService``,
``DashboardService``, ``BIExecutor``, semantic compiler, ``ResultService``,
SQLite/DuckDB) and replaces only the persistence of grants and the pgAdmin
user/role directory.  A recording Data Studio captures which workspace
context/endpoint each run used, and a recording semantic service captures the
``security_context`` of every compile.
"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone

from bi_live_harness import LiveStudio, Stack
from test_cdeadmin_bi_dashboards import MemoryDashboards, card

from pgadmin.cdeadmin.bi.access import (
    BIAccess, RANK, PRINCIPAL_TYPES,
)
from pgadmin.cdeadmin.bi.dashboards import DashboardService

OWNER, VIEWER, EDITOR, MANAGER, STRANGER, ANALYST, ADMIN = 1, 2, 3, 4, 5, 6, 7
USERS = {OWNER: 'owner', VIEWER: 'viewer', EDITOR: 'editor',
         MANAGER: 'manager', STRANGER: 'stranger', ANALYST: 'analyst',
         ADMIN: 'admin'}
ROLES = {1: 'Administrator', 10: 'analysts', 20: 'User', 30: 'isolated'}
MEMBERSHIP = {OWNER: {20, 10}, VIEWER: {20}, EDITOR: {20}, MANAGER: {20},
              STRANGER: {30}, ANALYST: {20, 10}, ADMIN: {1}}


class MemoryDirectory:
    """Same visibility rule as ``DatabasePrincipalDirectory``."""

    def __init__(self):
        self.users, self.roles = dict(USERS), dict(ROLES)
        self.membership = copy.deepcopy(MEMBERSHIP)

    def role_ids(self, user_id):
        return set(self.membership.get(user_id, ()))

    def user(self, user_id):
        name = self.users.get(user_id)
        return {'type': 'user', 'id': user_id, 'name': name} if name else None

    def role(self, role_id):
        name = self.roles.get(role_id)
        return {'type': 'role', 'id': role_id, 'name': name} if name else None

    def search(self, caller_id, text='', kinds=PRINCIPAL_TYPES, limit=20):
        mine = self.role_ids(caller_id)
        admin = 1 in mine
        needle = (text or '').strip().lower()
        items = []
        if 'role' in kinds:
            for rid, name in sorted(self.roles.items(),
                                    key=lambda kv: kv[1]):
                if (admin or rid in mine) and needle in name.lower():
                    items.append({'type': 'role', 'id': rid, 'name': name})
        if 'user' in kinds:
            for uid, name in sorted(self.users.items(),
                                    key=lambda kv: kv[1]):
                if uid == caller_id:
                    continue
                if (admin or self.role_ids(uid) & mine) and (
                        needle in name.lower()):
                    items.append({'type': 'user', 'id': uid, 'name': name})
        return items if limit is None else items[:limit]

    def can_see(self, caller_id, principal_type, principal_id):
        return any(i['id'] == principal_id for i in self.search(
            caller_id, '', (principal_type,), None))


class MemoryGrants:
    """Same contract as ``DatabaseGrantRepository``."""

    def __init__(self):
        self.rows, self.override_rows, self.events = {}, set(), []

    @staticmethod
    def _out(row):
        return copy.deepcopy(row)

    def for_principal(self, endpoint_id, user_id, role_ids):
        return [(r['resource_type'], r['resource_id'], RANK[r['level']])
                for r in self.rows.values()
                if r['endpoint_id'] == endpoint_id and (
                    (r['principal_type'] == 'user' and
                     r['principal_id'] == user_id) or
                    (r['principal_type'] == 'role' and
                     r['principal_id'] in role_ids))]

    def overrides(self, endpoint_id):
        return {(k, r) for e, k, r in self.override_rows
                if e == endpoint_id}

    def list(self, endpoint_id, kind, resource_id):
        return [self._out(r) for r in self.rows.values()
                if (r['endpoint_id'], r['resource_type'],
                    r['resource_id']) == (endpoint_id, kind, resource_id)]

    def get(self, grant_id):
        row = self.rows.get(grant_id)
        return self._out(row) if row else None

    def find(self, endpoint_id, kind, resource_id, principal_type,
             principal_id):
        for r in self.list(endpoint_id, kind, resource_id):
            if (r['principal_type'], r['principal_id']) == (
                    principal_type, principal_id):
                return r
        return None

    def add(self, *, endpoint_id, kind, resource_id, principal_type,
            principal_id, level, actor_id):
        now = datetime.now(timezone.utc)
        row = {'grant_id': str(uuid.uuid4()), 'endpoint_id': endpoint_id,
               'resource_type': kind, 'resource_id': resource_id,
               'principal_type': principal_type,
               'principal_id': principal_id, 'level': level,
               'created_by': actor_id, 'created_at': now,
               'updated_at': now}
        self.rows[row['grant_id']] = row
        return self._out(row)

    def set_level(self, grant_id, level):
        self.rows[grant_id]['level'] = level
        return self._out(self.rows[grant_id])

    def remove(self, grant_id):
        self.rows.pop(grant_id, None)

    def set_override(self, *, endpoint_id, kind, resource_id, enabled,
                     actor_id):
        key = (endpoint_id, kind, resource_id)
        (self.override_rows.add if enabled
         else self.override_rows.discard)(key)

    def purge(self, kind, resource_id):
        gone = [k for k, r in self.rows.items()
                if (r['resource_type'], r['resource_id']) == (
                    kind, resource_id)]
        for key in gone:
            del self.rows[key]
        self.override_rows = {o for o in self.override_rows
                              if o[1:] != (kind, resource_id)}
        return len(gone)

    def audit(self, **event):
        self.events.append(dict(event, created_at=datetime.now(
            timezone.utc).isoformat()))

    def audit_list(self, kind, resource_id, limit=100):
        return [dict(e, actor_user_id=e['actor_id'])
                for e in reversed(self.events)
                if (e['kind'], e['resource_id']) == (kind, resource_id)]


class RecordingStudio(LiveStudio):
    """Records the workspace context/endpoint every session was opened for."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sessions = []

    def open_session(self, context, endpoint, language):
        self.sessions.append({'context': context, 'endpoint': endpoint})
        return super().open_session(context, endpoint, language)


class SharedStack(Stack):
    """A ``Stack`` with grants, a user directory and a dashboard service."""

    def __init__(self, engine='sqlite', label='perm'):
        super().__init__(engine, label)
        self.endpoint_id = self.ctx.endpoint_id
        self.grants = MemoryGrants()
        self.directory = MemoryDirectory()
        self.bi.access.grants = self.grants
        self.bi.access.directory = self.directory
        self.studio = RecordingStudio(self.connection, self.results,
                                      self.provider)
        self.executor.studio = self.studio
        self.dashboards = DashboardService(self.bi, self.executor,
                                           repository=MemoryDashboards())
        self.security_contexts = []
        semantic = self.bi.semantic
        # the shared in-memory fake lists nothing; the raw-SQL policy scan
        # needs the real "models of this user at this endpoint"
        semantic.repository.list = lambda user_id, endpoint_id: [
            r for r in semantic.repository.rows.values()
            if r.user_id == user_id and r.endpoint_id == endpoint_id]
        original = semantic.compile

        def recording(provider, model, query, security_context=None):
            self.security_contexts.append(copy.deepcopy(security_context))
            return original(provider, model, query,
                            security_context=security_context)
        semantic.compile = recording

    def endpoint_for(self, user_id):
        """A distinct endpoint object per runner (their own credentials)."""
        return {'route': {'credential_owner': user_id}}

    def run_as(self, user_id, **request):
        return self.executor.run(
            provider=self.provider, context=self.ctx,
            endpoint=self.endpoint_for(user_id), user_id=user_id, **request)

    def run_dashboard(self, user_id, dashboard_id, **request):
        return self.dashboards.run(
            provider=self.provider, context=self.ctx,
            endpoint=self.endpoint_for(user_id), user_id=user_id,
            dashboard_id=dashboard_id, **request)

    def share(self, actor, kind, resource_id, principal_id, level,
              principal_type='user'):
        return self.bi.access.add_grant(
            actor, kind, self.endpoint_id, resource_id, principal_type,
            principal_id, level)

    def q(self, user_id, question):
        return self.create(question, user_id)['question_id']


def board(question_ids, name='Board', **extra):
    """A one-tab dashboard with a card per question id."""
    return {'name': name, 'tabs': [{'id': 'main', 'name': 'Main'}],
            'cards': [card(f'c{i}', qid, x=0, y=i * 6)
                      for i, qid in enumerate(question_ids)], **extra}
