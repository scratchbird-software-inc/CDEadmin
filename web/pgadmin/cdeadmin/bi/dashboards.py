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
        return self.dashboard.query.filter_by(
            user_id=user_id, collection_id=collection_id).first() is not None

    def get(self, user_id, endpoint_id, dashboard_id):
        return self.dashboard.query.filter_by(
            id=dashboard_id, user_id=user_id, endpoint_id=endpoint_id).first()

    def new(self, **values):
        return self.dashboard(**values)

    def save(self, row, snapshot):
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm.exc import StaleDataError
        try:
            self.db.session.add(row)
            self.db.session.flush()
            self.db.session.add(self.revision(
                id=str(uuid.uuid4()), dashboard_id=row.id,
                revision=row.revision, status=row.status,
                definition=snapshot, created_at=datetime.now(timezone.utc),
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
    """Own dashboards.  Every lookup is scoped to the owner and endpoint."""

    def __init__(self, bi_service, executor=None, repository=None):
        self.bi = bi_service
        self.executor = executor
        self.repository = repository or DatabaseDashboardRepository()
        bi_service.add_collection_guard(self._collection_in_use)
        bi_service.add_question_guard(self._question_in_use)

    # guards on the question/collection side -------------------------------
    def _collection_in_use(self, user_id, collection_id):
        return self.repository.in_collection(user_id, collection_id)

    def _question_in_use(self, user_id, endpoint_id, question_id):
        for row in self.repository.dashboards(user_id, endpoint_id):
            definition = json.loads(row.definition)
            if any(q == question_id
                   for q, _r in question_references(definition)):
                return row.name
        return None

    # lifecycle -------------------------------------------------------------
    def list(self, user_id, endpoint_id, **filters):
        scoped = 'collection_id' in filters
        return [self._summary(row) for row in self.repository.dashboards(
            user_id, endpoint_id, filters.get('collection_id'),
            every_collection=not scoped)]

    def get(self, user_id, endpoint_id, dashboard_id):
        return self._present(self._required(user_id, endpoint_id,
                                            dashboard_id))

    def create(self, user_id, endpoint_id, value):
        dashboard = self._admit(user_id, endpoint_id, value)
        now = _now()
        row = self.repository.new(
            id=str(uuid.uuid4()), user_id=user_id, endpoint_id=endpoint_id,
            status='active', revision=1, created_at=now, updated_at=now,
            name=dashboard['name'], collection_id=dashboard['collection_id'],
            definition=json.dumps(dashboard))
        self.repository.save(row, row.definition)
        return self._present(row)

    def update(self, user_id, endpoint_id, dashboard_id, expected_revision,
               value):
        row = self._required(user_id, endpoint_id, dashboard_id)
        self._check_revision(row, expected_revision)
        dashboard = self._admit(user_id, endpoint_id, value, exclude=row.id)
        row.name, row.collection_id = (dashboard['name'],
                                       dashboard['collection_id'])
        row.definition = json.dumps(dashboard)
        row.revision += 1
        row.updated_at = _now()
        self.repository.save(row, row.definition)
        return self._present(row)

    def set_status(self, user_id, endpoint_id, dashboard_id,
                   expected_revision, status):
        row = self._required(user_id, endpoint_id, dashboard_id)
        self._check_revision(row, expected_revision)
        if status not in DASHBOARD_STATUSES:
            raise BIError('dashboard status is unsupported')
        row.status = status
        row.revision += 1
        row.updated_at = _now()
        self.repository.save(row, row.definition)
        return self._present(row)

    def move(self, user_id, endpoint_id, dashboard_id, expected_revision,
             collection_id):
        value = self.get(user_id, endpoint_id, dashboard_id)['definition']
        value['collection_id'] = collection_id
        return self.update(user_id, endpoint_id, dashboard_id,
                           expected_revision, value)

    def clone(self, user_id, endpoint_id, dashboard_id, name):
        value = self.get(user_id, endpoint_id, dashboard_id)['definition']
        value['name'] = name
        return self.create(user_id, endpoint_id, value)

    def delete(self, user_id, endpoint_id, dashboard_id, expected_revision):
        row = self._required(user_id, endpoint_id, dashboard_id)
        self._check_revision(row, expected_revision)
        self.repository.delete(row)
        return {'dashboard_id': dashboard_id, 'deleted': True}

    def history(self, user_id, endpoint_id, dashboard_id):
        row = self._required(user_id, endpoint_id, dashboard_id)
        return [{'revision': item.revision, 'status': item.status,
                 'created_at': item.created_at.isoformat()}
                for item in self.repository.revisions(row.id)]

    def revision(self, user_id, endpoint_id, dashboard_id, revision):
        row = self._required(user_id, endpoint_id, dashboard_id)
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
                 bypass_cache=False, exclude=()):
        dashboard, _ = self._loaded(user_id, context.endpoint_id,
                                    dashboard_id, revision)
        resolved = resolve_filters(dashboard, filters, exclude)
        return self._run_card(provider, context, endpoint, user_id,
                              dashboard, resolved, card_id, page_size,
                              bypass_cache)

    def run(self, *, provider, context, endpoint, user_id, dashboard_id,
            filters=None, revision=None, tab_id=None, page_size=None,
            bypass_cache=False, exclude=()):
        """Run every question card (optionally one tab).

        A failing card reports its error and does not stop the others.
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
            try:
                cards[card['id']] = {'type': 'question', 'run': (
                    self._run_card(provider, context, endpoint, user_id,
                                   dashboard, resolved, card['id'],
                                   page_size, bypass_cache))}
            except BIError as exc:
                cards[card['id']] = {'type': 'question', 'error': str(exc)}
        return {'dashboard_id': dashboard_id, 'filters': resolved['filters'],
                'unapplied_filters': resolved['unapplied'], 'cards': cards}

    def _run_card(self, provider, context, endpoint, user_id, dashboard,
                  resolved, card_id, page_size, bypass_cache):
        card = next((c for c in dashboard['cards'] if c['id'] == card_id),
                    None)
        if card is None or card['type'] != 'question':
            raise BIError('card is not a runnable question card')
        if self.executor is None:
            raise BIError('dashboard execution is not initialized')
        binding = resolved['cards'][card_id]
        extra = binding['extra_filters']
        parameters = dict(binding['parameters'])
        outcome = self.executor.run(
            provider=provider, context=context, endpoint=endpoint,
            user_id=user_id, question_id=card['question']['question_id'],
            revision=card['question']['revision'], parameters=parameters,
            extra_filters=extra, page_size=page_size,
            bypass_cache=bypass_cache)
        outcome['card_id'] = card_id
        outcome['visualization'] = card.get('visualization')
        return outcome

    # helpers -----------------------------------------------------------------
    def _admit(self, user_id, endpoint_id, value, exclude=None):
        dashboard = validate_dashboard(value)
        if dashboard['collection_id'] is not None:
            self.bi._collection_row(user_id, dashboard['collection_id'])
        definitions = {}
        for question_id, revision in question_references(dashboard):
            stored = self.bi.revision(user_id, endpoint_id, question_id,
                                      revision)
            definitions[(question_id, revision)] = stored['definition']
        check_mappings(dashboard, definitions)
        for row in self.repository.dashboards(user_id, endpoint_id):
            if row.id != exclude and row.name == dashboard['name'] and (
                    row.collection_id == dashboard['collection_id']):
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

    def _required(self, user_id, endpoint_id, dashboard_id):
        row = self.repository.get(user_id, endpoint_id, dashboard_id)
        if row is None:
            raise BIError('dashboard is unavailable')
        return row

    @staticmethod
    def _check_revision(row, expected):
        if isinstance(expected, bool) or not isinstance(expected, int):
            raise BIError('expected_revision must be an integer')
        if row.revision != expected:
            raise BIConflict('dashboard revision has changed')

    @staticmethod
    def _summary(row):
        return {'dashboard_id': row.id, 'name': row.name,
                'collection_id': row.collection_id, 'status': row.status,
                'revision': row.revision,
                'updated_at': row.updated_at.isoformat()}

    @classmethod
    def _present(cls, row):
        return cls._summary(row) | {
            'definition': copy.deepcopy(json.loads(row.definition))}
