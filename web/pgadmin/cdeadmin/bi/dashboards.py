##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Dashboard lifecycle (owner-only, immutable revisions) and card runs."""

from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime, timezone

from .dashboard_models import (
    DASHBOARD_STATUSES, check_mappings, question_references,
    resolve_cross_filter, resolve_drill, resolve_filters, validate_dashboard,
)
from .models import BIConflict, BIError


class DatabaseDashboardRepository:
    """Persist dashboards and their immutable revisions."""

    def __init__(self):
        from pgadmin.model import (
            db, BIDashboard, BIDashboardRevision,
        )
        self.db = db
        self.dashboard = BIDashboard
        self.revision = BIDashboardRevision

    def dashboards(self, user_id, endpoint_id, collection_id=None,
                   every_collection=True):
        query = self.dashboard.query.filter_by(
            user_id=user_id, endpoint_id=endpoint_id)
        if not every_collection:
            query = query.filter_by(collection_id=collection_id)
        return query.order_by(self.dashboard.name).all()

    def in_collection(self, user_id, collection_id):
        # any owner's dashboard keeps a shared collection non-empty
        return self.dashboard.query.filter_by(
            collection_id=collection_id).first() is not None

    def find(self, endpoint_id, dashboard_id):
        return self.dashboard.query.filter_by(
            id=dashboard_id, endpoint_id=endpoint_id).first()

    def dashboards_at(self, endpoint_id):
        return self.dashboard.query.filter_by(
            endpoint_id=endpoint_id).order_by(self.dashboard.name).all()

    def save_owner(self, row):
        self.db.session.add(row)
        self.db.session.commit()

    def get(self, user_id, endpoint_id, dashboard_id):
        return self.dashboard.query.filter_by(
            id=dashboard_id, user_id=user_id, endpoint_id=endpoint_id).first()

    def new(self, **values):
        return self.dashboard(**values)

    def save(self, row, snapshot, actor_user_id=None):
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm.exc import StaleDataError
        try:
            self.db.session.add(row)
            self.db.session.flush()
            self.db.session.add(self.revision(
                id=str(uuid.uuid4()), dashboard_id=row.id,
                revision=row.revision, status=row.status,
                definition=snapshot, created_at=datetime.now(timezone.utc),
                actor_user_id=actor_user_id,
            ))
            self.db.session.commit()
        except StaleDataError as exc:
            self.db.session.rollback()
            raise BIConflict('dashboard revision has changed') from exc
        except IntegrityError as exc:
            self.db.session.rollback()
            raise BIError('dashboard revision already exists') from exc

    def revisions(self, dashboard_id):
        return self.revision.query.filter_by(dashboard_id=dashboard_id
                                             ).order_by(
            self.revision.revision.desc()).all()

    def delete(self, row):
        self.db.session.delete(row)
        self.db.session.commit()


def _now():
    return datetime.now(timezone.utc)


class DashboardService:
    """Own dashboards.  Every lookup goes through ``bi.access`` (the one
    authorization point) for the endpoint; owner-only when nothing is
    shared."""

    def __init__(self, bi_service, executor=None, repository=None):
        self.bi = bi_service
        self.executor = executor
        self.repository = repository or DatabaseDashboardRepository()
        bi_service.add_collection_guard(self._collection_in_use)
        bi_service.add_question_guard(self._question_in_use)
        bi_service.access.register(
            'dashboard',
            find=lambda ep, rid: self.repository.find(ep, rid),
            rows=lambda ep: self.repository.dashboards_at(ep),
            set_owner=self._set_owner)

    def _set_owner(self, row, new_owner_id):
        row.user_id = new_owner_id
        self.repository.save_owner(row)

    def transfer_owner(self, user_id, endpoint_id, dashboard_id,
                       new_owner_id, confirm=None):
        return self.bi.access.transfer_owner(
            user_id, 'dashboard', endpoint_id, dashboard_id, new_owner_id,
            confirm)

    # guards on the question/collection side -------------------------------
    def _collection_in_use(self, user_id, collection_id):
        return self.repository.in_collection(user_id, collection_id)

    def _question_in_use(self, user_id, endpoint_id, question_id):
        # every owner's dashboards pin it; never name one the caller cannot
        # see
        for row in self.repository.dashboards_at(endpoint_id):
            definition = json.loads(row.definition)
            if any(q == question_id
                   for q, _r in question_references(definition)):
                if self.bi.access.level(user_id, 'dashboard', endpoint_id,
                                        row.id) is not None:
                    return row.name
                return 'owned by another user'
        return None

    # lifecycle -------------------------------------------------------------
    def list(self, user_id, endpoint_id, **filters):
        """Dashboards the caller may view (owned and shared)."""
        scoped = 'collection_id' in filters
        return [self._summary(row, level, owned)
                for row, level, owned in self.bi.access.visible(
                    user_id, 'dashboard', endpoint_id)
                if not scoped or row.collection_id == filters[
                    'collection_id']]

    def get(self, user_id, endpoint_id, dashboard_id):
        row, level = self.bi.access.require(
            user_id, 'dashboard', endpoint_id, dashboard_id)
        return self._present(row, level, user_id)

    def create(self, user_id, endpoint_id, value):
        dashboard = self._admit(user_id, endpoint_id, value)
        now = _now()
        row = self.repository.new(
            id=str(uuid.uuid4()), user_id=user_id, endpoint_id=endpoint_id,
            status='active', revision=1, created_at=now, updated_at=now,
            name=dashboard['name'], collection_id=dashboard['collection_id'],
            definition=json.dumps(dashboard))
        self.repository.save(row, row.definition, actor_user_id=user_id)
        return self._present(row, 'manage', user_id)

    def update(self, user_id, endpoint_id, dashboard_id, expected_revision,
               value):
        row, level = self._required(user_id, endpoint_id, dashboard_id,
                                    'edit', 'change')
        self._check_revision(row, expected_revision)
        dashboard = self._admit(user_id, endpoint_id, value, exclude=row.id,
                                row=row)
        row.name, row.collection_id = (dashboard['name'],
                                       dashboard['collection_id'])
        row.definition = json.dumps(dashboard)
        row.revision += 1
        row.updated_at = _now()
        self.repository.save(row, row.definition, actor_user_id=user_id)
        return self._present(row, level, user_id)

    def set_status(self, user_id, endpoint_id, dashboard_id,
                   expected_revision, status):
        row, level = self._required(user_id, endpoint_id, dashboard_id,
                                    'edit', 'archive or restore')
        self._check_revision(row, expected_revision)
        if status not in DASHBOARD_STATUSES:
            raise BIError('dashboard status is unsupported')
        row.status = status
        row.revision += 1
        row.updated_at = _now()
        self.repository.save(row, row.definition, actor_user_id=user_id)
        return self._present(row, level, user_id)

    def move(self, user_id, endpoint_id, dashboard_id, expected_revision,
             collection_id):
        row, _ = self._required(user_id, endpoint_id, dashboard_id, 'edit',
                                'move')
        value = json.loads(row.definition)
        value['collection_id'] = collection_id
        return self.update(user_id, endpoint_id, dashboard_id,
                           expected_revision, value)

    def clone(self, user_id, endpoint_id, dashboard_id, name):
        row, _ = self._required(user_id, endpoint_id, dashboard_id)
        value = json.loads(row.definition)
        value['name'] = name
        target = value.get('collection_id')
        if target is not None and self.bi.access.level(
                user_id, 'collection', endpoint_id, target) not in (
                'edit', 'manage'):
            value['collection_id'] = None  # the copy goes to the root
        # the copy is admitted like any new dashboard: every pinned
        # question must be viewable by the cloner
        return self.create(user_id, endpoint_id, value)

    def delete(self, user_id, endpoint_id, dashboard_id, expected_revision):
        row, _ = self._required(user_id, endpoint_id, dashboard_id,
                                'manage', 'delete')
        self._check_revision(row, expected_revision)
        self.repository.delete(row)
        self.bi.access.purge('dashboard', dashboard_id)
        return {'dashboard_id': dashboard_id, 'deleted': True}

    def history(self, user_id, endpoint_id, dashboard_id):
        row, _ = self._required(user_id, endpoint_id, dashboard_id)
        return [{'revision': item.revision, 'status': item.status,
                 'created_at': item.created_at.isoformat(),
                 'actor_user_id': getattr(item, 'actor_user_id', None),
                 'actor': self.bi.access.actor_name(
                     user_id, getattr(item, 'actor_user_id', None))}
                for item in self.repository.revisions(row.id)]

    def revision(self, user_id, endpoint_id, dashboard_id, revision):
        row, _ = self._required(user_id, endpoint_id, dashboard_id)
        for item in self.repository.revisions(row.id):
            if item.revision == revision:
                return {'dashboard_id': row.id, 'revision': revision,
                        'status': item.status,
                        'definition': json.loads(item.definition)}
        raise BIError('requested dashboard revision is unavailable')

    # filters / links ---------------------------------------------------------
    def resolve(self, user_id, endpoint_id, dashboard_id, filters=None,
                revision=None):
        dashboard, _definitions = self._loaded(
            user_id, endpoint_id, dashboard_id, revision)
        return resolve_filters(dashboard, filters)

    def cross_filter(self, user_id, endpoint_id, dashboard_id,
                     cross_filter_id, row, filters=None):
        dashboard = self._definition(user_id, endpoint_id, dashboard_id)
        outcome = resolve_cross_filter(dashboard, cross_filter_id, row,
                                       filters)
        resolved = resolve_filters(dashboard, outcome['filters'],
                                   outcome['exclude'])
        outcome['resolved'] = resolved
        return outcome

    def drill(self, user_id, endpoint_id, dashboard_id, drill_id, row,
              filters=None):
        dashboard = self._definition(user_id, endpoint_id, dashboard_id)
        target = resolve_drill(dashboard, drill_id, row, filters)
        if target['kind'] == 'dashboard':
            other = self._definition(user_id, endpoint_id,
                                     target['dashboard_id'])
            target['resolved'] = resolve_filters(other, target['filters'])
        return target

    # execution ---------------------------------------------------------------
    def run_card(self, *, provider, context, endpoint, user_id, dashboard_id,
                 card_id, filters=None, revision=None, page_size=None,
                 bypass_cache=False, exclude=(), security_context=None,
                 principal=None):
        dashboard, _ = self._loaded(user_id, context.endpoint_id,
                                    dashboard_id, revision)
        resolved = resolve_filters(dashboard, filters, exclude)
        return self._run_card(provider, context, endpoint, user_id,
                              dashboard, resolved, card_id, page_size,
                              bypass_cache, security_context, principal)

    def run(self, *, provider, context, endpoint, user_id, dashboard_id,
            filters=None, revision=None, tab_id=None, page_size=None,
            bypass_cache=False, exclude=()):
        """Run every question card (optionally one tab).

        Needs ``view`` on the dashboard.  Each card runs as the RUNNER and
        only when the runner also has ``view`` on the card's question;
        otherwise the card reports ``no_access`` and nothing about the
        question.  A failing card reports its error and does not stop the
        others.
        """
        dashboard, _ = self._loaded(user_id, context.endpoint_id,
                                    dashboard_id, revision)
        if tab_id is not None and tab_id not in {
                t['id'] for t in dashboard['tabs']}:
            raise BIError('tab is unavailable')
        resolved = resolve_filters(dashboard, filters, exclude)
        cards = {}
        for card in dashboard['cards']:
            if tab_id is not None and card['tab_id'] != tab_id:
                continue
            if card['type'] != 'question':
                cards[card['id']] = {'type': card['type'],
                                     'static': {
                                         'text': card.get('text'),
                                         'metric_panel': card.get(
                                             'metric_panel')}}
                continue
            if not self._can_run(user_id, context.endpoint_id, card):
                cards[card['id']] = {'type': 'question', 'no_access': True}
                continue
            try:
                cards[card['id']] = {'type': 'question', 'run': (
                    self._run_card(provider, context, endpoint, user_id,
                                   dashboard, resolved, card['id'],
                                   page_size, bypass_cache))}
            except BIError as exc:
                cards[card['id']] = {'type': 'question', 'error': str(exc)}
        return {'dashboard_id': dashboard_id, 'filters': resolved['filters'],
                'unapplied_filters': resolved['unapplied'], 'cards': cards}

    def _can_run(self, user_id, endpoint_id, card):
        return self.bi.access.level(
            user_id, 'question', endpoint_id,
            card['question']['question_id']) is not None

    def _run_card(self, provider, context, endpoint, user_id, dashboard,
                  resolved, card_id, page_size, bypass_cache,
                  security_context=None, principal=None):
        card = next((c for c in dashboard['cards'] if c['id'] == card_id),
                    None)
        if card is None or card['type'] != 'question':
            raise BIError('card is not a runnable question card')
        if self.executor is None:
            raise BIError('dashboard execution is not initialized')
        if not self._can_run(user_id, context.endpoint_id, card):
            return {'card_id': card_id, 'no_access': True}
        binding = resolved['cards'][card_id]
        extra = binding['extra_filters']
        parameters = dict(binding['parameters'])
        outcome = self.executor.run(
            provider=provider, context=context, endpoint=endpoint,
            user_id=user_id, question_id=card['question']['question_id'],
            revision=card['question']['revision'], parameters=parameters,
            extra_filters=extra, page_size=page_size,
            bypass_cache=bypass_cache,
            **({'security_context': security_context,
                'principal': principal} if principal is not None else {}))
        outcome['card_id'] = card_id
        outcome['visualization'] = card.get('visualization')
        return outcome

    # helpers -----------------------------------------------------------------
    def _admit(self, user_id, endpoint_id, value, exclude=None, row=None):
        dashboard = validate_dashboard(value)
        owner_id = row.user_id if row is not None else user_id
        collection_id = dashboard['collection_id']
        if collection_id is not None and (
                row is None or collection_id != row.collection_id):
            self.bi._collection_row(user_id, collection_id, endpoint_id,
                                    'edit', 'add items to')
        definitions = {}
        for question_id, revision in question_references(dashboard):
            # pinning needs view on the question; the editor never sees
            # raw SQL through this path
            stored = self.bi.stored_for_run(user_id, endpoint_id,
                                            question_id, revision)
            definitions[(question_id, revision)] = stored['definition']
        check_mappings(dashboard, definitions)
        for other in self.repository.dashboards(owner_id, endpoint_id):
            if other.id != exclude and other.name == dashboard['name'] and (
                    other.collection_id == dashboard['collection_id']):
                raise BIError('dashboard name already exists')
        return dashboard

    def _loaded(self, user_id, endpoint_id, dashboard_id, revision):
        if revision is None:
            dashboard = self._definition(user_id, endpoint_id, dashboard_id)
        else:
            dashboard = self.revision(user_id, endpoint_id, dashboard_id,
                                      revision)['definition']
        return dashboard, None

    def _definition(self, user_id, endpoint_id, dashboard_id):
        return self.get(user_id, endpoint_id, dashboard_id)['definition']

    def _required(self, user_id, endpoint_id, dashboard_id, minimum='view',
                  action=None):
        return self.bi.access.require(user_id, 'dashboard', endpoint_id,
                                      dashboard_id, minimum, action)

    @staticmethod
    def _check_revision(row, expected):
        if isinstance(expected, bool) or not isinstance(expected, int):
            raise BIError('expected_revision must be an integer')
        if row.revision != expected:
            raise BIConflict('dashboard revision has changed')

    @staticmethod
    def _summary(row, access='manage', owned=True):
        return {'dashboard_id': row.id, 'name': row.name,
                'collection_id': row.collection_id, 'status': row.status,
                'revision': row.revision, 'access': access,
                'is_owner': owned, 'updated_at': row.updated_at.isoformat()}

    @classmethod
    def _present(cls, row, access='manage', viewer_id=None):
        return cls._summary(row, access, row.user_id == viewer_id) | {
            'definition': copy.deepcopy(json.loads(row.definition))}
