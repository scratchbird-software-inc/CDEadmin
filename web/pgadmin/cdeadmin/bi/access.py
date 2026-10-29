##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Central authorization and sharing for BI collections, questions and
dashboards (docs/en_US/bi_permissions.rst).

Every BI entry point asks ``BIAccess.require`` (one function) for the
caller's *effective access* to a resource; nothing else decides who may see
or change BI content.  The rules:

* The owner has ``manage``.  With no grants at all the behaviour is exactly
  the old owner-only behaviour.
* A grant names a pgAdmin ``User`` or ``Role`` (real tables), a level
  (``view`` < ``edit`` < ``manage``) and an endpoint.
* A collection grant flows down the collection tree to the questions,
  dashboards and sub-collections it contains, unless a resource has an
  explicit override (it then keeps only its own grants and its owner).
* Effective access is the maximum of owner, direct and inherited grants.
  Deny is the default: no access answers with the same "unavailable" error
  as a missing resource, so existence is never disclosed.

Sharing never widens run-time data access; see ``execution.py``.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from .models import BIError

LEVELS = ('view', 'edit', 'manage')
RANK = {'view': 1, 'edit': 2, 'manage': 3}
NAMES = {1: 'view', 2: 'edit', 3: 'manage'}
KINDS = ('collection', 'question', 'dashboard')
LABELS = {'collection': 'collection', 'question': 'saved question',
          'dashboard': 'dashboard'}
PRINCIPAL_TYPES = ('user', 'role')
MAX_DEPTH = 24


class BIPermissionDenied(BIError):
    """The caller can see the resource but lacks the needed level."""


def _now():
    return datetime.now(timezone.utc)


def _unavailable(kind):
    return BIError(f'{LABELS[kind]} is unavailable')


# repositories ------------------------------------------------------------
class NullGrantRepository:
    """No sharing store: strictly owner-only (the default)."""

    def for_principal(self, endpoint_id, user_id, role_ids):
        return []

    def overrides(self, endpoint_id):
        return set()

    def list(self, endpoint_id, kind, resource_id):
        return []

    def get(self, grant_id):
        return None

    def find(self, endpoint_id, kind, resource_id, principal_type,
             principal_id):
        return None

    def add(self, **values):
        raise BIError('sharing is not configured')

    set_level = remove = set_override = add

    def purge(self, kind, resource_id):
        return 0

    def audit(self, **event):
        return None

    def audit_list(self, kind, resource_id, limit=100):
        return []


class DatabaseGrantRepository:
    """Grants, overrides and the audit trail in the application database."""

    def __init__(self):
        from pgadmin.model import (
            db, BIGrant, BIAccessOverride, BIAuditEvent,
        )
        self.db = db
        self.grant = BIGrant
        self.override = BIAccessOverride
        self.event = BIAuditEvent

    @staticmethod
    def _present(row):
        user = row.principal_user_id is not None
        return {
            'grant_id': row.id, 'endpoint_id': row.endpoint_id,
            'resource_type': row.resource_type,
            'resource_id': row.resource_id,
            'principal_type': 'user' if user else 'role',
            'principal_id': (row.principal_user_id if user
                             else row.principal_role_id),
            'level': row.level, 'created_by': row.created_by,
            'created_at': row.created_at, 'updated_at': row.updated_at,
        }

    def for_principal(self, endpoint_id, user_id, role_ids):
        from sqlalchemy import or_
        conditions = [self.grant.principal_user_id == user_id]
        if role_ids:
            conditions.append(self.grant.principal_role_id.in_(
                list(role_ids)))
        rows = self.grant.query.filter(
            self.grant.endpoint_id == endpoint_id, or_(*conditions)).all()
        return [(r.resource_type, r.resource_id, RANK[r.level])
                for r in rows]

    def overrides(self, endpoint_id):
        return {(r.resource_type, r.resource_id)
                for r in self.override.query.filter_by(
                    endpoint_id=endpoint_id).all()}

    def list(self, endpoint_id, kind, resource_id):
        rows = self.grant.query.filter_by(
            endpoint_id=endpoint_id, resource_type=kind,
            resource_id=resource_id).order_by(self.grant.created_at).all()
        return [self._present(r) for r in rows]

    def get(self, grant_id):
        row = self.grant.query.filter_by(id=grant_id).first()
        return self._present(row) if row else None

    def find(self, endpoint_id, kind, resource_id, principal_type,
             principal_id):
        column = (self.grant.principal_user_id if principal_type == 'user'
                  else self.grant.principal_role_id)
        row = self.grant.query.filter(
            self.grant.endpoint_id == endpoint_id,
            self.grant.resource_type == kind,
            self.grant.resource_id == resource_id,
            column == principal_id).first()
        return self._present(row) if row else None

    def add(self, *, endpoint_id, kind, resource_id, principal_type,
            principal_id, level, actor_id):
        from sqlalchemy.exc import IntegrityError
        now = _now()
        row = self.grant(
            id=str(uuid.uuid4()), endpoint_id=endpoint_id,
            resource_type=kind, resource_id=resource_id,
            principal_user_id=principal_id if principal_type == 'user'
            else None,
            principal_role_id=principal_id if principal_type == 'role'
            else None,
            level=level, created_by=actor_id, created_at=now,
            updated_at=now)
        try:
            self.db.session.add(row)
            self.db.session.commit()
        except IntegrityError as exc:
            self.db.session.rollback()
            raise BIError('principal already has a grant on this '
                          'resource') from exc
        return self._present(row)

    def set_level(self, grant_id, level):
        row = self.grant.query.filter_by(id=grant_id).first()
        row.level, row.updated_at = level, _now()
        self.db.session.commit()
        return self._present(row)

    def remove(self, grant_id):
        row = self.grant.query.filter_by(id=grant_id).first()
        if row is not None:
            self.db.session.delete(row)
            self.db.session.commit()

    def set_override(self, *, endpoint_id, kind, resource_id, enabled,
                     actor_id):
        row = self.override.query.filter_by(
            endpoint_id=endpoint_id, resource_type=kind,
            resource_id=resource_id).first()
        if enabled and row is None:
            self.db.session.add(self.override(
                id=str(uuid.uuid4()), endpoint_id=endpoint_id,
                resource_type=kind, resource_id=resource_id,
                created_by=actor_id, created_at=_now()))
        elif not enabled and row is not None:
            self.db.session.delete(row)
        self.db.session.commit()

    def purge(self, kind, resource_id):
        count = self.grant.query.filter_by(
            resource_type=kind, resource_id=resource_id).delete()
        self.override.query.filter_by(
            resource_type=kind, resource_id=resource_id).delete()
        self.db.session.commit()
        return count

    def audit(self, **event):
        self.db.session.add(self.event(
            id=str(uuid.uuid4()), actor_user_id=event.get('actor_id'),
            action=event['action'], endpoint_id=event.get('endpoint_id'),
            resource_type=event['kind'], resource_id=event['resource_id'],
            target_type=event.get('target_type'),
            target_id=event.get('target_id'),
            detail=json.dumps(event.get('detail') or {}, sort_keys=True),
            created_at=_now()))
        self.db.session.commit()

    def audit_list(self, kind, resource_id, limit=100):
        rows = self.event.query.filter_by(
            resource_type=kind, resource_id=resource_id).order_by(
            self.event.created_at.desc()).limit(limit).all()
        return [{'action': r.action, 'actor_user_id': r.actor_user_id,
                 'endpoint_id': r.endpoint_id,
                 'target_type': r.target_type, 'target_id': r.target_id,
                 'detail': json.loads(r.detail or '{}'),
                 'created_at': r.created_at.isoformat()} for r in rows]


class DatabasePrincipalDirectory:
    """Users and roles from pgAdmin's own tables (no new identity system).

    A caller sees the roles they belong to and the active users who share
    one of those roles; an Administrator sees every role and active user.
    Email addresses are never returned by ``search``/``user``; ``email`` is
    for server-side delivery only and its result is never sent to a client.
    """

    ADMIN_ROLE = 'Administrator'

    def __init__(self):
        from pgadmin.model import db, User, Role
        self.db = db
        self.user_model = User
        self.role_model = Role

    def role_ids(self, user_id):
        user = self.user_model.query.filter_by(id=user_id).first()
        return {r.id for r in user.roles} if user else set()

    def user(self, user_id):
        row = self.user_model.query.filter_by(id=user_id).first()
        if row is None or not row.active:
            return None
        return {'type': 'user', 'id': row.id, 'name': row.username}

    def role(self, role_id):
        row = self.role_model.query.filter_by(id=role_id).first()
        return ({'type': 'role', 'id': row.id, 'name': row.name}
                if row else None)

    def email(self, user_id):
        """The delivery address of an active user (server-side use only)."""
        row = self.user_model.query.filter_by(id=user_id).first()
        if row is None or not row.active:
            return None
        return row.email or None

    def _caller(self, caller_id):
        caller = self.user_model.query.filter_by(id=caller_id).first()
        if caller is None:
            return None, set(), False
        roles = {r.id for r in caller.roles}
        return caller, roles, any(
            r.name == self.ADMIN_ROLE for r in caller.roles)

    def can_see(self, caller_id, principal_type, principal_id):
        found = [item for item in self.search(
            caller_id, '', (principal_type,), limit=None)
            if item['id'] == principal_id]
        return bool(found)

    def search(self, caller_id, text='', kinds=PRINCIPAL_TYPES, limit=20):
        caller, roles, admin = self._caller(caller_id)
        if caller is None:
            return []
        needle = (text or '').strip().lower()
        items = []
        if 'role' in kinds:
            for row in self.role_model.query.order_by(
                    self.role_model.name).all():
                if (admin or row.id in roles) and (
                        not needle or needle in row.name.lower()):
                    items.append({'type': 'role', 'id': row.id,
                                  'name': row.name})
        if 'user' in kinds:
            for row in self.user_model.query.order_by(
                    self.user_model.username).all():
                if not row.active or row.id == caller_id:
                    continue
                if not admin and not ({r.id for r in row.roles} & roles):
                    continue
                if not needle or needle in row.username.lower():
                    items.append({'type': 'user', 'id': row.id,
                                  'name': row.username})
        return items if limit is None else items[:limit]


class NullDirectory:
    def role_ids(self, user_id):
        return set()

    def user(self, user_id):
        return None

    def role(self, role_id):
        return None

    def email(self, user_id):
        return None

    def can_see(self, caller_id, principal_type, principal_id):
        return False

    def search(self, caller_id, text='', kinds=PRINCIPAL_TYPES, limit=20):
        return []


# authorization -----------------------------------------------------------
class _Kind:
    def __init__(self, find, rows, set_owner):
        self.find, self.rows, self.set_owner = find, rows, set_owner


class _Snapshot:
    """One caller's grants at one endpoint, evaluated in memory."""

    def __init__(self, access, user_id, endpoint_id):
        self.access = access
        self.user_id = user_id
        self.endpoint_id = endpoint_id
        roles = access.directory.role_ids(user_id)
        self.direct = {}
        for kind, resource_id, rank in access.grants.for_principal(
                endpoint_id, user_id, roles):
            key = (kind, resource_id)
            self.direct[key] = max(self.direct.get(key, 0), rank)
        self.overrides = access.grants.overrides(endpoint_id)
        self._collections = None

    def collection(self, collection_id):
        if self._collections is None:
            self._collections = {
                row.id: row for row in self.access.kinds['collection'].rows(
                    self.endpoint_id)}
        return self._collections.get(collection_id)

    def evaluate(self, kind, row):
        """``(owner, direct, inherited, via_collection_id)`` ranks."""
        if kind != 'collection' and row.endpoint_id != self.endpoint_id:
            return 0, 0, 0, None
        key = (kind, row.id)
        owner = RANK['manage'] if row.user_id == self.user_id else 0
        direct = self.direct.get(key, 0)
        inherited, via = 0, None
        if key not in self.overrides:
            parent_id = (row.parent_id if kind == 'collection'
                         else row.collection_id)
            seen = set()
            while parent_id is not None and parent_id not in seen and (
                    len(seen) < MAX_DEPTH):
                seen.add(parent_id)
                parent = self.collection(parent_id)
                if parent is None:
                    break
                rank = self.direct.get(('collection', parent_id), 0)
                if parent.user_id == self.user_id:
                    # the owner of a folder manages what is filed in it
                    rank = RANK['manage']
                if rank > inherited:
                    inherited, via = rank, parent_id
                if ('collection', parent_id) in self.overrides:
                    break
                parent_id = parent.parent_id
        return owner, direct, inherited, via

    def rank(self, kind, row):
        return max(self.evaluate(kind, row)[:3])


class BIAccess:
    """The single authorization point of the BI module."""

    def __init__(self, grants=None, directory=None):
        self.grants = grants or NullGrantRepository()
        self.directory = directory or NullDirectory()
        self.kinds = {}

    def register(self, kind, *, find, rows, set_owner):
        """``find(endpoint_id, id)``, ``rows(endpoint_id)``, owner setter."""
        self.kinds[kind] = _Kind(find, rows, set_owner)

    @property
    def shared(self):
        return not isinstance(self.grants, NullGrantRepository)

    def snapshot(self, user_id, endpoint_id):
        return _Snapshot(self, user_id, endpoint_id)

    # the one decision ------------------------------------------------------
    def _row(self, kind, endpoint_id, resource_id):
        if resource_id is None or kind not in self.kinds:
            return None
        return self.kinds[kind].find(endpoint_id, resource_id)

    def level(self, user_id, kind, endpoint_id, resource_id):
        """Effective level name, or ``None`` (no access / does not exist)."""
        row = self._row(kind, endpoint_id, resource_id)
        if row is None:
            return None
        rank = self.snapshot(user_id, endpoint_id).rank(kind, row)
        return NAMES.get(rank)

    def require(self, user_id, kind, endpoint_id, resource_id,
                minimum='view', action=None):
        """Return ``(row, level)`` or raise.

        No view access always raises the uniform "unavailable" error, the
        same as a missing id, so existence is not disclosed.  A caller who
        can view but not do ``action`` gets ``BIPermissionDenied``.
        """
        row = self._row(kind, endpoint_id, resource_id)
        if row is None:
            raise _unavailable(kind)
        rank = self.snapshot(user_id, endpoint_id).rank(kind, row)
        if rank < RANK['view']:
            raise _unavailable(kind)
        if rank < RANK[minimum]:
            raise BIPermissionDenied(
                f'{minimum} access is required to '
                f'{action or "change"} this {LABELS[kind]}')
        return row, NAMES[rank]

    def require_target(self, user_id, endpoint_id, collection_id,
                       minimum='edit'):
        """Placing an item in a collection needs ``edit`` on it."""
        if collection_id is None:
            return None
        return self.require(user_id, 'collection', endpoint_id,
                            collection_id, minimum, 'add items to')[0]

    def visible(self, user_id, kind, endpoint_id, minimum='view'):
        """``[(row, level, is_owner)]`` the caller may see, name-ordered."""
        snap = self.snapshot(user_id, endpoint_id)
        found = []
        for row in self.kinds[kind].rows(endpoint_id):
            rank = snap.rank(kind, row)
            if rank >= RANK[minimum]:
                found.append((row, NAMES[rank], row.user_id == user_id))
        return sorted(found, key=lambda item: item[0].name)

    def effective_access(self, user_id, kind, endpoint_id, resource_id):
        row = self._row(kind, endpoint_id, resource_id)
        if row is None:
            raise _unavailable(kind)
        owner, direct, inherited, via = self.snapshot(
            user_id, endpoint_id).evaluate(kind, row)
        rank = max(owner, direct, inherited)
        if rank < RANK['view']:
            raise _unavailable(kind)
        return {
            'resource_type': kind, 'resource_id': resource_id,
            'endpoint_id': endpoint_id, 'level': NAMES[rank],
            'is_owner': row.user_id == user_id,
            'sources': {
                'owner': NAMES.get(owner), 'direct': NAMES.get(direct),
                'inherited': NAMES.get(inherited),
                'inherited_from': via},
        }

    # grants ---------------------------------------------------------------
    def _principal(self, actor_id, principal_type, principal_id):
        if principal_type not in PRINCIPAL_TYPES or isinstance(
                principal_id, bool) or not isinstance(principal_id, int):
            raise BIError('principal must be a user or role id')
        if not self.directory.can_see(actor_id, principal_type,
                                      principal_id):
            raise BIError('principal is unavailable')
        return (self.directory.user(principal_id)
                if principal_type == 'user'
                else self.directory.role(principal_id))

    @staticmethod
    def _level(level):
        if level not in LEVELS:
            raise BIError('access level must be view, edit or manage')
        return level

    def _name(self, principal_type, principal_id):
        found = (self.directory.user(principal_id)
                 if principal_type == 'user'
                 else self.directory.role(principal_id))
        return found['name'] if found else None

    def _present_grant(self, item):
        return {'grant_id': item['grant_id'],
                'principal_type': item['principal_type'],
                'principal_id': item['principal_id'],
                'principal_name': self._name(item['principal_type'],
                                             item['principal_id']),
                'level': item['level'],
                'created_at': item['created_at'].isoformat()
                if item.get('created_at') else None}

    def list_grants(self, actor_id, kind, endpoint_id, resource_id):
        row, _ = self.require(actor_id, kind, endpoint_id, resource_id,
                              'manage', 'manage sharing of')
        snap = self.snapshot(actor_id, endpoint_id)
        key = (kind, resource_id)
        inherit = key not in snap.overrides
        inherited = []
        if inherit:
            parent_id = (row.parent_id if kind == 'collection'
                         else row.collection_id)
            seen = set()
            while parent_id is not None and parent_id not in seen and (
                    len(seen) < MAX_DEPTH):
                seen.add(parent_id)
                parent = snap.collection(parent_id)
                if parent is None:
                    break
                seeable = snap.rank('collection', parent) >= RANK['view']
                for item in self.grants.list(endpoint_id, 'collection',
                                             parent_id):
                    inherited.append(self._present_grant(item) | {
                        'collection_id': parent_id if seeable else None,
                        'collection_name': parent.name if seeable
                        else None})
                if ('collection', parent_id) in snap.overrides:
                    break
                parent_id = parent.parent_id
        owner = self.directory.user(row.user_id)
        return {
            'resource_type': kind, 'resource_id': resource_id,
            'endpoint_id': endpoint_id, 'inherit': inherit,
            'owner': {'user_id': row.user_id,
                      'name': owner['name'] if owner else None,
                      'is_you': row.user_id == actor_id},
            'direct': [self._present_grant(i) for i in self.grants.list(
                endpoint_id, kind, resource_id)],
            'inherited': inherited,
        }

    def add_grant(self, actor_id, kind, endpoint_id, resource_id,
                  principal_type, principal_id, level):
        row, _ = self.require(actor_id, kind, endpoint_id, resource_id,
                              'manage', 'manage sharing of')
        self._level(level)
        self._principal(actor_id, principal_type, principal_id)
        if principal_type == 'user' and principal_id == row.user_id:
            raise BIError('the owner already has full access')
        if self.grants.find(endpoint_id, kind, resource_id, principal_type,
                            principal_id):
            raise BIError('principal already has a grant on this resource; '
                          'update it instead')
        created = self.grants.add(
            endpoint_id=endpoint_id, kind=kind, resource_id=resource_id,
            principal_type=principal_type, principal_id=principal_id,
            level=level, actor_id=actor_id)
        self._audit(actor_id, 'grant.add', endpoint_id, kind, resource_id,
                    principal_type, principal_id, {'level': level})
        return self._present_grant(created)

    def _owned_grant(self, kind, endpoint_id, resource_id, grant_id):
        grant = self.grants.get(grant_id)
        if grant is None or (grant['endpoint_id'], grant['resource_type'],
                             grant['resource_id']) != (
                endpoint_id, kind, resource_id):
            raise BIError('grant is unavailable')
        return grant

    def update_grant(self, actor_id, kind, endpoint_id, resource_id,
                     grant_id, level):
        self.require(actor_id, kind, endpoint_id, resource_id, 'manage',
                     'manage sharing of')
        self._level(level)
        grant = self._owned_grant(kind, endpoint_id, resource_id, grant_id)
        updated = self.grants.set_level(grant_id, level)
        self._audit(actor_id, 'grant.update', endpoint_id, kind,
                    resource_id, grant['principal_type'],
                    grant['principal_id'],
                    {'from': grant['level'], 'to': level})
        return self._present_grant(updated)

    def remove_grant(self, actor_id, kind, endpoint_id, resource_id,
                     grant_id):
        self.require(actor_id, kind, endpoint_id, resource_id, 'manage',
                     'manage sharing of')
        grant = self._owned_grant(kind, endpoint_id, resource_id, grant_id)
        self.grants.remove(grant_id)
        self._audit(actor_id, 'grant.remove', endpoint_id, kind,
                    resource_id, grant['principal_type'],
                    grant['principal_id'], {'level': grant['level']})
        return {'grant_id': grant_id, 'removed': True}

    def set_inherit(self, actor_id, kind, endpoint_id, resource_id,
                    inherit):
        self.require(actor_id, kind, endpoint_id, resource_id, 'manage',
                     'manage sharing of')
        if not isinstance(inherit, bool):
            raise BIError('inherit must be true or false')
        self.grants.set_override(
            endpoint_id=endpoint_id, kind=kind, resource_id=resource_id,
            enabled=not inherit, actor_id=actor_id)
        self._audit(actor_id, 'inherit.set', endpoint_id, kind,
                    resource_id, None, None, {'inherit': inherit})
        return {'resource_type': kind, 'resource_id': resource_id,
                'inherit': inherit}

    def transfer_owner(self, actor_id, kind, endpoint_id, resource_id,
                       new_owner_id, confirm=None):
        row, _ = self.require(actor_id, kind, endpoint_id, resource_id,
                              'manage', 'transfer ownership of')
        if confirm != row.name:
            raise BIError('type the exact name of the resource to confirm '
                          'the ownership transfer')
        if new_owner_id == row.user_id:
            raise BIError('that user already owns this resource')
        self._principal(actor_id, 'user', new_owner_id)
        previous = row.user_id
        self.kinds[kind].set_owner(row, new_owner_id)
        # the new owner needs no grant of their own; the previous owner
        # keeps working access instead of losing the resource outright
        existing = self.grants.find(endpoint_id, kind, resource_id, 'user',
                                    new_owner_id)
        if existing:
            self.grants.remove(existing['grant_id'])
        if not self.grants.find(endpoint_id, kind, resource_id, 'user',
                                previous):
            self.grants.add(
                endpoint_id=endpoint_id, kind=kind, resource_id=resource_id,
                principal_type='user', principal_id=previous, level='edit',
                actor_id=actor_id)
        self._audit(actor_id, 'owner.transfer', endpoint_id, kind,
                    resource_id, 'user', new_owner_id,
                    {'previous_owner': previous})
        return {'resource_type': kind, 'resource_id': resource_id,
                'owner_user_id': new_owner_id, 'previous_owner': previous,
                'previous_owner_level': 'edit'}

    def purge(self, kind, resource_id):
        """Drop grants/overrides of a deleted resource."""
        return self.grants.purge(kind, resource_id)

    def search_principals(self, actor_id, text='', kinds=None, limit=20):
        kinds = tuple(kinds or PRINCIPAL_TYPES)
        if any(k not in PRINCIPAL_TYPES for k in kinds):
            raise BIError('principal kinds are user and role')
        if isinstance(limit, bool) or not isinstance(limit, int) or not (
                1 <= limit <= 50):
            limit = 20
        return self.directory.search(actor_id, str(text or '')[:64], kinds,
                                     limit)

    def audit_trail(self, actor_id, kind, endpoint_id, resource_id):
        self.require(actor_id, kind, endpoint_id, resource_id, 'manage',
                     'view the audit trail of')
        return self.grants.audit_list(kind, resource_id)

    def actor_name(self, viewer_id, user_id):
        """A user's name when the viewer may see them, otherwise ``None``."""
        if user_id is None:
            return None
        if user_id == viewer_id:
            found = self.directory.user(user_id)
            return found['name'] if found else None
        if not self.directory.can_see(viewer_id, 'user', user_id):
            return None
        return self._name('user', user_id)

    def _audit(self, actor_id, action, endpoint_id, kind, resource_id,
               target_type, target_id, detail):
        self.grants.audit(
            actor_id=actor_id, action=action, endpoint_id=endpoint_id,
            kind=kind, resource_id=resource_id, target_type=target_type,
            target_id=target_id, detail=detail)
