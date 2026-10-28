##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Dashboard document, lifecycle, filter resolution, live card execution,
monitoring-dashboard conversion and the migration."""

from __future__ import annotations

import base64
import copy
import importlib.util
import json
import shutil
import unittest
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import bi_live_harness as harness
from bi_live_harness import ROOT, Stack, duckdb

from pgadmin.cdeadmin.bi import BIConflict, BIError
from pgadmin.cdeadmin.bi import dashboard_ddn
from pgadmin.cdeadmin.bi.dashboard_models import (
    check_mappings, resolve_cross_filter, resolve_drill, resolve_filters,
    validate_dashboard,
)
from pgadmin.cdeadmin.bi.dashboards import DashboardService
from pgadmin.cdeadmin.workspace import ProviderWorkspaceService
from test_cdeadmin_bi_execution import (
    LiveExecutionTests, region_question, sql_question,
)

try:
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    MIGRATION_DEPENDENCIES = True
except ImportError:  # pragma: no cover
    MIGRATION_DEPENDENCIES = False

ENGINES = ['sqlite'] + (['duckdb'] if duckdb is not None else [])
FIXTURES = ROOT / 'tools/tests/fixtures/cdeadmin_bi/monitoring_dashboards.json'


class MemoryDashboards:
    def __init__(self):
        self.rows, self.snaps = {}, {}

    def dashboards(self, user_id, endpoint_id, collection_id=None,
                   every_collection=True):
        return sorted([
            r for r in self.rows.values()
            if r.user_id == user_id and r.endpoint_id == endpoint_id and (
                every_collection or r.collection_id == collection_id)
        ], key=lambda r: r.name)

    def in_collection(self, user_id, collection_id):
        return any(r.collection_id == collection_id and r.user_id == user_id
                   for r in self.rows.values())

    def get(self, user_id, endpoint_id, dashboard_id):
        r = self.rows.get(dashboard_id)
        if r and r.user_id == user_id and r.endpoint_id == endpoint_id:
            return r
        return None

    @staticmethod
    def new(**values):
        return SimpleNamespace(**values)

    def save(self, row, snapshot):
        self.rows[row.id] = row
        self.snaps.setdefault(row.id, []).append(SimpleNamespace(
            revision=row.revision, status=row.status, definition=snapshot,
            created_at=datetime.now(timezone.utc)))

    def revisions(self, dashboard_id):
        return sorted(self.snaps.get(dashboard_id, []),
                      key=lambda s: s.revision, reverse=True)

    def delete(self, row):
        self.rows.pop(row.id)


def detail_by_region():
    return {
        'name': 'Detail',
        'query': {'kind': 'builder', 'builder': {
            'source': {'relation': ['sales']},
            'columns': ['region', 'product', 'amount'],
            'order_by': [{'column': 'amount', 'direction': 'desc'}],
            'limit': 50}},
    }


def floor_sql_question():
    return sql_question(
        'SELECT region, SUM(amount) AS revenue FROM sales '
        'WHERE amount >= {{floor}} GROUP BY region ORDER BY region',
        [{'id': 'floor', 'type': 'integer', 'default': 0}])


def card(cid, qid, revision=1, x=0, y=0, tab='main', **extra):
    return {'id': cid, 'tab_id': tab, 'type': 'question',
            'layout': {'x': x, 'y': y, 'w': 12, 'h': 6},
            'question': {'question_id': qid, 'revision': revision}, **extra}


class World:
    """A stack plus three stored questions and a dashboard service."""

    def __init__(self, engine='sqlite'):
        self.stack = Stack(engine, 'dash')
        self.endpoint_id = self.stack.ctx.endpoint_id
        self.repo = MemoryDashboards()
        self.dashboards = DashboardService(
            self.stack.bi, self.stack.executor, repository=self.repo)
        self.by_region = self.stack.create(region_question())['question_id']
        self.detail = self.stack.create(detail_by_region())['question_id']
        self.floor = self.stack.create(floor_sql_question())['question_id']

    def document(self, **overrides):
        value = {
            'name': 'Sales board',
            'tabs': [{'id': 'main', 'name': 'Main'}],
            'cards': [
                card('by_region', self.by_region, x=0),
                card('detail', self.detail, x=12),
                card('floor', self.floor, x=0, y=6),
                {'id': 'note', 'tab_id': 'main', 'type': 'text',
                 'layout': {'x': 12, 'y': 6, 'w': 12, 'h': 2},
                 'text': {'markdown': '# Sales'}},
            ],
            'filters': [
                {'id': 'region', 'name': 'Region', 'type': 'string',
                 'widget': 'select', 'allowed_values': ['east', 'west'],
                 'targets': [
                     {'card_id': 'by_region', 'parameter_id': 'region'},
                     {'card_id': 'detail', 'field': {'column': 'region'}}]},
                {'id': 'floor', 'name': 'Minimum', 'type': 'integer',
                 'widget': 'number', 'default': 0,
                 'targets': [{'card_id': 'floor', 'parameter_id': 'floor'}]},
            ],
            'cross_filters': [
                {'id': 'click_region', 'source_card_id': 'detail',
                 'source_column': 'region', 'filter_id': 'region'}],
            'drill_throughs': [
                {'id': 'to_floor', 'source_card_id': 'detail',
                 'trigger': {'column': 'amount'},
                 'target': {'kind': 'question', 'question_id': self.floor,
                            'revision': 1, 'parameter_mappings': [
                                {'parameter_id': 'floor',
                                 'from': {'column': 'amount'}}]}}],
        }
        value.update(overrides)
        return value

    def create(self, user_id=1, **overrides):
        return self.dashboards.create(user_id, self.endpoint_id,
                                      self.document(**overrides))


class DocumentValidationTests(unittest.TestCase):
    def test_minimal_document_gets_defaults(self):
        item = validate_dashboard({'name': 'Empty'})
        self.assertEqual(item['tabs'], [{'id': 'main', 'name': 'Main'}])
        self.assertEqual(item['cards'], [])
        self.assertEqual(item['settings'], {'auto_refresh_seconds': 0})
        self.assertEqual(item['contract_version'], '1.0.0')

    def test_structure_is_rejected_when_inconsistent(self):
        world = World()
        good = world.document()
        cases = {
            'off grid': lambda d: d['cards'][0]['layout'].update(
                x=20, w=10),
            'unknown tab': lambda d: d['cards'][0].update(tab_id='nope'),
            'duplicate card': lambda d: d['cards'][1].update(id='by_region'),
            'duplicate tab': lambda d: d.update(tabs=[
                {'id': 'main', 'name': 'a'}, {'id': 'main', 'name': 'b'}]),
            'unpinned revision': lambda d: d['cards'][0]['question'].update(
                revision=0),
            'bad type': lambda d: d['cards'][0].update(type='iframe'),
            'huge text': lambda d: d['cards'][3]['text'].update(
                markdown='x' * 20001),
            'filter to text card': lambda d: d['filters'][0]['targets'].append(
                {'card_id': 'note', 'parameter_id': 'x'}),
            'both param and field': lambda d: d['filters'][0]['targets'][
                0].update(field={'column': 'c'}),
            'neither': lambda d: d['filters'][0]['targets'].append(
                {'card_id': 'floor'}),
            'duplicate target': lambda d: d['filters'][0]['targets'].append(
                {'card_id': 'by_region', 'parameter_id': 'region'}),
            'array filter type': lambda d: d['filters'][0].update(
                type='array'),
            'default outside domain': lambda d: d['filters'][0].update(
                default='north'),
            'cross filter bad filter': lambda d: d['cross_filters'][0].update(
                filter_id='ghost'),
            'cross filter from text': lambda d: d['cross_filters'][0].update(
                source_card_id='note'),
            'drill bad kind': lambda d: d['drill_throughs'][0][
                'target'].update(kind='url'),
            'drill unknown filter': lambda d: d['drill_throughs'][0][
                'target']['parameter_mappings'][0].update(
                    {'from': {'filter_id': 'ghost'}}),
            'drill ambiguous source': lambda d: d['drill_throughs'][0][
                'target']['parameter_mappings'][0].update(
                    {'from': {'column': 'a', 'value': 1}}),
            'monitoring columns': lambda d: d.update(settings={
                'monitoring': {'module': 'm', 'channel': 'c',
                               'columns': 9}}),
        }
        for label, mutate in cases.items():
            with self.subTest(label):
                doc = copy.deepcopy(good)
                mutate(doc)
                with self.assertRaises(BIError):
                    validate_dashboard(doc)
        validate_dashboard(good)

    def test_filter_operator_follows_widget(self):
        world = World()
        doc = world.document()
        doc['filters'].append({'id': 'when', 'name': 'When', 'type': 'date',
                               'widget': 'date_range', 'targets': []})
        doc['filters'].append({'id': 'many', 'name': 'Many',
                               'type': 'string', 'widget': 'multi_select',
                               'targets': []})
        item = validate_dashboard(doc)
        operators = {f['id']: (f['operator'], f['multiple'])
                     for f in item['filters']}
        self.assertEqual(operators['when'], ('between', False))
        self.assertEqual(operators['many'], ('in', True))
        self.assertEqual(operators['region'], ('eq', False))


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.world = World()
        self.ep = self.world.endpoint_id

    def test_create_pins_revisions_and_is_owner_only(self):
        created = self.world.create()
        self.assertEqual(created['revision'], 1)
        did = created['dashboard_id']
        got = self.world.dashboards.get(1, self.ep, did)
        self.assertEqual(len(got['definition']['cards']), 4)
        for call in (
                lambda: self.world.dashboards.get(2, self.ep, did),
                lambda: self.world.dashboards.update(
                    2, self.ep, did, 1, self.world.document()),
                lambda: self.world.dashboards.delete(2, self.ep, did, 1),
                lambda: self.world.dashboards.history(2, self.ep, did),
                lambda: self.world.dashboards.resolve(2, self.ep, did),
                lambda: self.world.dashboards.get(1, 'other-endpoint', did)):
            with self.assertRaisesRegex(BIError, 'unavailable'):
                call()
        self.assertEqual(self.world.dashboards.list(2, self.ep), [])
        self.assertEqual(len(self.world.dashboards.list(1, self.ep)), 1)

    def test_cards_may_only_pin_the_owners_existing_revisions(self):
        # question 3 belongs to user 1; user 2 cannot pin it
        with self.assertRaisesRegex(BIError, 'unavailable'):
            self.world.create(user_id=2)
        bad = self.world.document()
        bad['cards'][0]['question']['revision'] = 9
        with self.assertRaisesRegex(BIError, 'revision is unavailable'):
            self.world.dashboards.create(1, self.ep, bad)

    def test_filter_mappings_are_checked_against_the_pinned_question(self):
        base = self.world.document()
        cases = {
            'unknown parameter': lambda d: d['filters'][0]['targets'][
                0].update(parameter_id='ghost'),
            'type mismatch': lambda d: d['filters'][1].update(type='string',
                                                              default='0'),
            'field on raw sql': lambda d: d['filters'][1]['targets'].append(
                {'card_id': 'floor', 'field': {'column': 'amount'}}),
            'semantic shape on builder': lambda d: d['filters'][0][
                'targets'][1].update(field={'source_id': 's', 'field': 'f'}),
        }
        for label, mutate in cases.items():
            with self.subTest(label):
                doc = copy.deepcopy(base)
                mutate(doc)
                with self.assertRaises(BIError):
                    self.world.dashboards.create(1, self.ep, doc)

    def test_revisions_are_immutable_and_optimistic(self):
        did = self.world.create()['dashboard_id']
        updated = self.world.dashboards.update(
            1, self.ep, did, 1, self.world.document(name='Sales board 2'))
        self.assertEqual(updated['revision'], 2)
        with self.assertRaises(BIConflict):
            self.world.dashboards.update(1, self.ep, did, 1,
                                         self.world.document())
        history = self.world.dashboards.history(1, self.ep, did)
        self.assertEqual([h['revision'] for h in history], [2, 1])
        first = self.world.dashboards.revision(1, self.ep, did, 1)
        self.assertEqual(first['definition']['name'], 'Sales board')
        with self.assertRaises(BIError):
            self.world.dashboards.revision(1, self.ep, did, 7)
        archived = self.world.dashboards.set_status(1, self.ep, did, 2,
                                                    'archived')
        self.assertEqual((archived['status'], archived['revision']),
                         ('archived', 3))
        with self.assertRaises(BIError):
            self.world.dashboards.set_status(1, self.ep, did, 3, 'deleted')
        self.assertEqual(self.world.dashboards.revision(
            1, self.ep, did, 1)['status'], 'active')

    def test_names_collections_clone_move_delete(self):
        first = self.world.create()
        with self.assertRaisesRegex(BIError, 'already exists'):
            self.world.create()
        folder = self.world.stack.bi.create_collection(
            1, {'name': 'Boards'})['collection_id']
        moved = self.world.dashboards.move(
            1, self.ep, first['dashboard_id'], 1, folder)
        self.assertEqual(moved['collection_id'], folder)
        cloned = self.world.dashboards.clone(
            1, self.ep, first['dashboard_id'], 'Copy')
        self.assertEqual(cloned['definition']['name'], 'Copy')
        self.assertEqual(len(self.world.dashboards.list(
            1, self.ep, collection_id=folder)), 2)
        self.assertEqual(len(self.world.dashboards.list(
            1, self.ep, collection_id=None)), 0)
        with self.assertRaisesRegex(BIError, 'unavailable'):
            self.world.dashboards.create(
                1, self.ep, self.world.document(
                    name='Ghost', collection_id='nope'))
        # a collection holding a dashboard cannot be deleted
        with self.assertRaisesRegex(BIError, 'empty'):
            self.world.stack.bi.delete_collection(1, folder)
        self.world.dashboards.delete(1, self.ep, first['dashboard_id'], 2)
        with self.assertRaisesRegex(BIError, 'empty'):
            self.world.stack.bi.delete_collection(1, folder)
        self.world.dashboards.delete(1, self.ep, cloned['dashboard_id'], 1)
        self.world.stack.bi.delete_collection(1, folder)

    def test_a_question_in_use_cannot_be_deleted(self):
        self.world.create()
        with self.assertRaisesRegex(BIError, 'used by dashboard'):
            self.world.stack.bi.delete_question(
                1, self.ep, self.world.detail, 1)
        spare = self.world.stack.create(
            {**region_question(), 'name': 'Spare'})['question_id']
        self.world.stack.bi.delete_question(1, self.ep, spare, 1)


class FilterResolutionTests(unittest.TestCase):
    def setUp(self):
        self.world = World()
        self.document = validate_dashboard(self.world.document())

    def test_values_map_to_parameters_and_field_filters(self):
        resolved = resolve_filters(self.document, {'region': 'west'})
        self.assertEqual(resolved['filters'], {'region': 'west', 'floor': 0})
        self.assertEqual(resolved['cards']['by_region'], {
            'parameters': {'region': 'west'}, 'extra_filters': []})
        self.assertEqual(resolved['cards']['detail'], {
            'parameters': {}, 'extra_filters': [
                {'operator': 'eq', 'value': 'west', 'column': 'region'}]})
        self.assertEqual(resolved['cards']['floor']['parameters'],
                         {'floor': 0})
        self.assertNotIn('note', resolved['cards'])
        self.assertEqual(resolved['unapplied'], [])

    def test_missing_values_default_skip_or_fail(self):
        resolved = resolve_filters(self.document)
        self.assertEqual(resolved['unapplied'], ['region'])
        self.assertEqual(resolved['cards']['by_region']['parameters'], {})
        self.assertEqual(resolved['cards']['detail']['extra_filters'], [])
        required = copy.deepcopy(self.document)
        required['filters'][0]['required'] = True
        with self.assertRaisesRegex(BIError, 'requires a value'):
            resolve_filters(required)
        resolve_filters(required, {'region': 'east'})

    def test_values_are_checked_and_unknown_filters_refused(self):
        for values in ({'region': 'north'}, {'region': 5},
                       {'floor': 'ten'}, {'floor': True},
                       {'ghost': 1}, {'region': ['east']}):
            with self.subTest(values=values):
                with self.assertRaises(BIError):
                    resolve_filters(self.document, values)

    def test_multiple_and_range_filters(self):
        doc = copy.deepcopy(self.document)
        doc['filters'][0].update(multiple=True, operator='in')
        resolved = resolve_filters(doc, {'region': ['east', 'west']})
        self.assertEqual(resolved['cards']['detail']['extra_filters'][0][
            'operator'], 'in')
        with self.assertRaises(BIError):
            resolve_filters(doc, {'region': 'east'})
        with self.assertRaises(BIError):
            resolve_filters(doc, {'region': ['east', 'north']})
        ranged = copy.deepcopy(self.document)
        ranged['filters'][1].update(widget='date_range', operator='between',
                                    type='integer')
        ranged['filters'][1].pop('default')
        ok = resolve_filters(ranged, {'floor': [1, 9]})
        self.assertEqual(ok['cards']['floor']['parameters'],
                         {'floor': [1, 9]})
        with self.assertRaises(BIError):
            resolve_filters(ranged, {'floor': [1]})

    def test_semantic_field_targets_keep_their_shape(self):
        doc = copy.deepcopy(self.document)
        doc['filters'][0]['targets'] = [
            {'card_id': 'detail', 'field': {'source_id': 'src',
                                            'field': 'region'}}]
        resolved = resolve_filters(doc, {'region': 'east'})
        self.assertEqual(resolved['cards']['detail']['extra_filters'], [{
            'operator': 'eq', 'value': 'east',
            'field': {'source_id': 'src', 'field': 'region'}}])

    def test_cross_filter_sets_the_filter_and_spares_the_source(self):
        outcome = resolve_cross_filter(
            self.document, 'click_region',
            {'region': 'east', 'amount': 30}, {'floor': 5})
        self.assertEqual(outcome['filters'], {'floor': 5, 'region': 'east'})
        self.assertEqual(outcome['exclude'], [
            {'card_id': 'detail', 'filter_id': 'region'}])
        resolved = resolve_filters(self.document, outcome['filters'],
                                   outcome['exclude'])
        # the clicked card keeps its own rows; its sibling is filtered
        self.assertEqual(resolved['cards']['detail']['extra_filters'], [])
        self.assertEqual(resolved['cards']['by_region']['parameters'],
                         {'region': 'east'})
        with self.assertRaises(BIError):
            resolve_cross_filter(self.document, 'click_region', {'x': 1})
        with self.assertRaises(BIError):
            resolve_cross_filter(self.document, 'click_region',
                                 {'region': 'north'})
        with self.assertRaises(BIError):
            resolve_cross_filter(self.document, 'ghost', {})

    def test_drill_through_to_question_and_dashboard(self):
        target = resolve_drill(self.document, 'to_floor',
                               {'region': 'east', 'amount': 20})
        self.assertEqual(target, {
            'kind': 'question', 'question_id': self.world.floor,
            'revision': 1, 'parameters': {'floor': 20}})
        with self.assertRaises(BIError):
            resolve_drill(self.document, 'to_floor', {'region': 'east'})
        with self.assertRaises(BIError):
            resolve_drill(self.document, 'ghost', {})
        doc = copy.deepcopy(self.document)
        doc['drill_throughs'][0]['target'] = {
            'kind': 'dashboard', 'dashboard_id': 'other',
            'filter_mappings': [
                {'filter_id': 'region', 'from': {'column': 'region'}},
                {'filter_id': 'floor', 'from': {'filter_id': 'floor'}}]}
        hop = resolve_drill(doc, 'to_floor',
                            {'region': 'west', 'amount': 1}, {'floor': 4})
        self.assertEqual(hop, {'kind': 'dashboard', 'dashboard_id': 'other',
                               'filters': {'region': 'west', 'floor': 4}})

    def test_service_resolves_against_a_pinned_revision(self):
        did = self.world.create()['dashboard_id']
        service, ep = self.world.dashboards, self.world.endpoint_id
        before = service.resolve(1, ep, did, {'region': 'east'})
        self.assertIn('detail', before['cards'])
        changed = self.world.document(cards=[
            card('by_region', self.world.by_region)], filters=[
            {'id': 'region', 'name': 'Region', 'type': 'string',
             'targets': [{'card_id': 'by_region',
                          'parameter_id': 'region'}]}],
            cross_filters=[], drill_throughs=[])
        service.update(1, ep, did, 1, changed)
        self.assertNotIn('detail', service.resolve(
            1, ep, did, {'region': 'east'})['cards'])
        self.assertIn('detail', service.resolve(
            1, ep, did, {'region': 'east'}, revision=1)['cards'])
        hop = service.cross_filter  # still guarded by the current document
        with self.assertRaises(BIError):
            hop(1, ep, did, 'click_region', {'region': 'east'})


class DashboardLiveTests(unittest.TestCase):
    @staticmethod
    def rows(card_outcome):
        return LiveExecutionTests._records(card_outcome['run'])

    def each(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                yield World(engine)

    def run_board(self, world, did, **options):
        stack = world.stack
        return world.dashboards.run(
            provider=stack.provider, context=stack.ctx,
            endpoint=stack.endpoint, user_id=1, dashboard_id=did, **options)

    def test_filters_drive_every_card(self):
        for world in self.each():
            did = world.create()['dashboard_id']
            out = self.run_board(world, did,
                                 filters={'region': 'west', 'floor': 20})
            cards = out['cards']
            self.assertEqual(
                [(r['region'], r['amount'])
                 for r in self.rows(cards['detail'])],
                [('west', 40), ('west', 20), ('west', 5)])
            self.assertEqual(len(self.rows(cards['detail'])), 3)
            self.assertEqual(len(self.rows(cards['by_region'])), 3)
            self.assertEqual(
                {r['region']: r['revenue']
                 for r in self.rows(cards['floor'])},
                {'east': 30, 'west': 60})
            self.assertEqual(cards['note']['static']['text'],
                             {'markdown': '# Sales'})
            self.assertEqual(out['filters'], {'region': 'west', 'floor': 20})
            # filter values only ever travelled as bound parameters
            for call in world.stack.studio.calls:
                self.assertNotIn('west', call['source'])
                self.assertNotIn('20', call['source'].split('WHERE')[-1][:6])

    def test_a_failing_card_does_not_stop_the_board(self):
        for world in self.each():
            did = world.create()['dashboard_id']
            out = self.run_board(world, did)  # region unset: by_region needs it
            self.assertIn('required parameter', out['cards']['by_region'][
                'error'])
            self.assertEqual(len(self.rows(out['cards']['detail'])), 5)
            self.assertEqual(out['unapplied_filters'], ['region'])

    def test_cards_hit_the_cache_and_filters_change_the_key(self):
        for world in self.each():
            did = world.create()['dashboard_id']
            calls = world.stack.studio.calls
            self.run_board(world, did, filters={'region': 'west'})
            first = len(calls)
            again = self.run_board(world, did, filters={'region': 'west'})
            self.assertEqual(len(calls), first)
            self.assertTrue(again['cards']['detail']['run']['cache']['hit'])
            self.run_board(world, did, filters={'region': 'east'})
            self.assertGreater(len(calls), first)
            self.run_board(world, did, filters={'region': 'east'},
                           bypass_cache=True)

    def test_cross_filter_click_then_run_with_exclusion(self):
        for world in self.each():
            did = world.create()['dashboard_id']
            ep = world.endpoint_id
            click = world.dashboards.cross_filter(
                1, ep, did, 'click_region', {'region': 'east', 'amount': 30})
            out = self.run_board(world, did, filters=click['filters'],
                                 exclude=click['exclude'])
            self.assertEqual(len(self.rows(out['cards']['detail'])), 5)
            self.assertEqual(
                {r['region'] for r in self.rows(out['cards']['by_region'])},
                {'east'})
            card_only = world.dashboards.run_card(
                provider=world.stack.provider, context=world.stack.ctx,
                endpoint=world.stack.endpoint, user_id=1, dashboard_id=did,
                card_id='detail', filters=click['filters'])
            self.assertEqual(
                {r['region'] for r in LiveExecutionTests._records(
                    card_only)}, {'east'})
            with self.assertRaises(BIError):
                world.dashboards.run_card(
                    provider=world.stack.provider, context=world.stack.ctx,
                    endpoint=world.stack.endpoint, user_id=1,
                    dashboard_id=did, card_id='note')

    def test_drill_through_target_runs_with_row_values(self):
        for world in self.each():
            did = world.create()['dashboard_id']
            target = world.dashboards.drill(
                1, world.endpoint_id, did, 'to_floor',
                {'region': 'west', 'amount': 25})
            stack = world.stack
            outcome = stack.run(question_id=target['question_id'],
                                revision=target['revision'],
                                parameters=target['parameters'])
            self.assertEqual(
                {r['region']: r['revenue'] for r in
                 LiveExecutionTests._records(outcome)},
                {'east': 30, 'west': 40})

    def test_cards_stay_on_their_pinned_question_revision(self):
        for world in self.each():
            did = world.create()['dashboard_id']
            changed = region_question()
            changed['query']['builder']['limit'] = 1
            world.stack.bi.update_question(
                1, world.endpoint_id, world.by_region, 1, changed)
            out = self.run_board(world, did, filters={'region': 'west'})
            self.assertEqual(out['cards']['by_region']['run']['revision'], 1)
            self.assertEqual(len(self.rows(out['cards']['by_region'])), 3)

    def test_injection_through_a_dashboard_filter(self):
        for world in self.each():
            doc = world.document()
            doc['filters'][0].pop('allowed_values')
            did = world.dashboards.create(1, world.endpoint_id, doc)[
                'dashboard_id']
            attack = "west'; DROP TABLE sales; --"
            out = self.run_board(world, did, filters={'region': attack})
            self.assertEqual(self.rows(out['cards']['by_region']), [])
            self.assertEqual(self.rows(out['cards']['detail']), [])
            self.assertEqual(world.stack.connection.execute(
                'SELECT COUNT(*) FROM sales').fetchone()[0], 5)
            for call in world.stack.studio.calls:
                self.assertNotIn('DROP', call['source'])

    def test_another_user_cannot_run_the_board(self):
        world = World()
        did = world.create()['dashboard_id']
        stack = world.stack
        with self.assertRaisesRegex(BIError, 'unavailable'):
            world.dashboards.run(
                provider=stack.provider, context=stack.ctx,
                endpoint=stack.endpoint, user_id=2, dashboard_id=did)


class WorkspaceRouteTests(unittest.TestCase):
    """The ``bi_*`` workspace actions reach the same services."""

    def setUp(self):
        self.world = World()
        stack = self.world.stack
        stack.bi.executor = stack.executor
        stack.bi.dashboards = self.world.dashboards
        self.service = object.__new__(ProviderWorkspaceService)
        self.service.bi_service = stack.bi
        self.service.endpoint_service = SimpleNamespace(
            workspace=lambda server: (stack.ctx, stack.endpoint, None),
            provider_registry=SimpleNamespace(
                resolve=lambda ctx: SimpleNamespace(instance=stack.provider)))
        self.server = SimpleNamespace(user_id=1)

    def act(self, action, **request):
        return self.service.bi_action(self.server, action, request)

    def test_execute_page_export_cache_and_invalidate(self):
        question = region_question(
            export={'enabled': True, 'formats': ['csv']},
            redact_columns=['notes'])
        question['name'] = 'Workspace sales'
        created = self.act('bi_question_create', question=question)
        qid = created['question_id']
        out = self.act('bi_question_execute', question_id=qid,
                       parameters={'region': 'west'}, page_size=2)
        self.assertEqual(out['page']['page']['page_size'], 2)
        again = self.act('bi_question_execute', question_id=qid,
                         parameters={'region': 'west'}, page_size=2)
        self.assertTrue(again['cache']['hit'])
        rid = out['result']['result_id']
        page = self.act('bi_question_page', result_id=rid,
                        cursor=out['page']['page']['next_cursor'])
        self.assertEqual(page['page']['page_size'], 1)
        exported = self.act('bi_question_export', result_id=rid, format='csv')
        self.assertEqual(exported['media_type'], 'text/csv')
        content = base64.b64decode(exported['content_base64'])
        self.assertNotIn(b'private-', content)
        self.assertEqual(len(self.act('bi_cache_info')['items']), 1)
        self.assertEqual(self.act('bi_cache_invalidate',
                                  question_id=qid)['released'], 1)
        with self.assertRaises(BIError):
            self.act('bi_question_page', result_id=rid)
        self.server = SimpleNamespace(user_id=2)
        with self.assertRaises(BIError):
            self.act('bi_question_execute', question_id=qid,
                     parameters={'region': 'west'})

    def test_conversion_and_dashboard_actions(self):
        converted = self.act('bi_sql_to_question',
                             sql='SELECT region FROM sales LIMIT 3')
        self.assertEqual(converted['fidelity'], 'exact')
        created = self.act('bi_dashboard_create',
                           dashboard=self.world.document())
        did = created['dashboard_id']
        self.assertEqual(len(self.act('bi_dashboard_list')['items']), 1)
        resolved = self.act('bi_dashboard_resolve', dashboard_id=did,
                            filters={'region': 'east'})
        self.assertIn('detail', resolved['cards'])
        board = self.act('bi_dashboard_run', dashboard_id=did,
                         filters={'region': 'east'}, tab_id='main')
        self.assertEqual(set(board['cards']),
                         {'by_region', 'detail', 'floor', 'note'})
        one = self.act('bi_dashboard_card_run', dashboard_id=did,
                       card_id='detail', filters={'region': 'east'})
        self.assertEqual(one['card_id'], 'detail')
        click = self.act('bi_dashboard_cross_filter', dashboard_id=did,
                         cross_filter_id='click_region',
                         row={'region': 'west'})
        self.assertEqual(click['filters'], {'region': 'west'})
        drill = self.act('bi_dashboard_drill', dashboard_id=did,
                         drill_id='to_floor', row={'amount': 10})
        self.assertEqual(drill['parameters'], {'floor': 10})
        self.assertEqual(self.act('bi_dashboard_history',
                                  dashboard_id=did)['items'][0]['revision'], 1)
        snapshot = json.loads(FIXTURES.read_text())['sqlite_database'][
            'snapshot']
        imported = self.act('bi_dashboard_from_ddn', snapshot=snapshot)
        self.assertEqual(imported['loss'], [])
        exported = self.act('bi_dashboard_to_ddn',
                            dashboard=imported['dashboard'])
        self.assertEqual(exported['snapshot']['files'], snapshot['files'])
        self.act('bi_dashboard_delete', dashboard_id=did, expected_revision=1)
        with self.assertRaisesRegex(Exception, 'unavailable'):
            self.act('bi_dashboard_get', dashboard_id=did)
        with self.assertRaisesRegex(Exception, 'unavailable'):
            self.act('bi_dashboard_nonsense')


@unittest.skipUnless(MIGRATION_DEPENDENCIES,
                     'SQLAlchemy and Alembic are required')
class MigrationTests(unittest.TestCase):
    @staticmethod
    def load(name):
        path = ROOT / f'web/migrations/versions/{name}_.py'
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_chain_and_round_trip(self):
        first = self.load('cde_bi_saved_questions_v1')
        second = self.load('cde_bi_dashboards_v1')
        self.assertEqual(second.down_revision, first.revision)
        self.assertEqual(first.down_revision, 'cde_registration_aliases_v1')
        engine = sa.create_engine('sqlite:///:memory:')
        with engine.connect() as connection:
            metadata = sa.MetaData()
            sa.Table('user', metadata,
                     sa.Column('id', sa.Integer(), primary_key=True))
            sa.Table('cde_endpoint', metadata,
                     sa.Column('id', sa.String(36), primary_key=True))
            metadata.create_all(connection)
            operations = Operations(MigrationContext.configure(connection))
            first.op = second.op = operations
            first.upgrade()
            second.upgrade()
            names = sa.inspect(connection).get_table_names()
            self.assertIn('cde_bi_dashboard', names)
            self.assertIn('cde_bi_dashboard_revision', names)
            connection.execute(sa.text('PRAGMA foreign_keys=ON'))
            connection.execute(sa.text('INSERT INTO user (id) VALUES (1)'))
            endpoint = str(uuid.uuid4())
            connection.execute(sa.text(
                'INSERT INTO cde_endpoint (id) VALUES (:i)'), {'i': endpoint})
            now = datetime.now(timezone.utc)
            dashboard = sa.Table('cde_bi_dashboard', sa.MetaData(),
                                 autoload_with=connection)
            revision = sa.Table('cde_bi_dashboard_revision', sa.MetaData(),
                                autoload_with=connection)
            did = str(uuid.uuid4())
            row = dict(id=did, user_id=1, endpoint_id=endpoint, name='d',
                       status='active', revision=1, definition='{}',
                       created_at=now, updated_at=now)
            connection.execute(dashboard.insert().values(**row))
            snap = dict(id=str(uuid.uuid4()), dashboard_id=did, revision=1,
                        status='active', definition='{}', created_at=now)
            connection.execute(revision.insert().values(**snap))
            with self.assertRaises(sa.exc.IntegrityError):
                connection.execute(revision.insert().values(
                    **{**snap, 'id': str(uuid.uuid4())}))
            with self.assertRaises(sa.exc.IntegrityError):
                connection.execute(dashboard.insert().values(
                    **{**row, 'id': str(uuid.uuid4()), 'status': 'weird'}))
            connection.execute(dashboard.delete())
            self.assertEqual(connection.execute(
                sa.select(sa.func.count()).select_from(revision)).scalar(), 0)
            second.downgrade()
            self.assertNotIn('cde_bi_dashboard',
                             sa.inspect(connection).get_table_names())
            self.assertIn('cde_bi_saved_question',
                          sa.inspect(connection).get_table_names())

    def test_models_mirror_the_migration(self):
        source = (ROOT / 'web/pgadmin/model/__init__.py').read_text()
        for needle in ("__tablename__ = 'cde_bi_dashboard'",
                       "__tablename__ = 'cde_bi_dashboard_revision'",
                       'dashboard revisions are immutable',
                       "name='uq_cde_bi_dashboard_revision'",
                       "name='ck_cde_bi_dashboard_status'"):
            self.assertIn(needle, source)
        self.assertIn('SCHEMA_VERSION = 59', source)


class MonitoringConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        loaded = json.loads(FIXTURES.read_text(encoding='utf-8'))
        cls.escapes = loaded.pop('escapes')
        cls.fixtures = loaded

    def test_every_encoder_fixture_round_trips_byte_for_byte(self):
        for name, fixture in self.fixtures.items():
            with self.subTest(name):
                converted = dashboard_ddn.ddn_to_dashboard(fixture['snapshot'])
                self.assertEqual(converted['loss'], [])
                back = dashboard_ddn.dashboard_to_ddn(converted['dashboard'])
                self.assertEqual(back['loss'], [])
                self.assertEqual(
                    back['snapshot']['files']['dashboard.ddn'],
                    fixture['snapshot']['files']['dashboard.ddn'])
                self.assertEqual(back['snapshot']['view'],
                                 fixture['snapshot']['view'])

    def test_document_shape_matches_the_documented_mapping(self):
        fixture = self.fixtures['sqlite_database']['snapshot']
        document = dashboard_ddn.ddn_to_dashboard(fixture)['dashboard']
        self.assertEqual(document['settings']['monitoring'], {
            'module': 'scratchrobin.sqlite.monitoring',
            'channel': 'scratchrobin.sqlite.monitoring.observations',
            'columns': 2, 'entry': 'dashboard.ddn', 'view': 'dashboard'})
        self.assertEqual([t['id'] for t in document['tabs']], ['dashboard'])
        self.assertEqual(document['name'], 'SQLite database dashboard')
        cards = document['cards']
        self.assertEqual([c['metric_panel']['panel_id'] for c in cards],
                         ['availability', 'storage', 'database',
                          'limitations'])
        self.assertEqual([(c['layout']['x'], c['layout']['y'],
                           c['layout']['w'], c['layout']['h'])
                          for c in cards],
                         [(0, 0, 12, 8), (12, 0, 12, 8),
                          (0, 8, 12, 8), (12, 8, 12, 8)])
        first = cards[0]['metric_panel']['rows'][0]
        self.assertEqual(first, {'id': 'availability_0',
                                 'measure': 'Collector',
                                 'value': 'collecting', 'unit': '',
                                 'rate': ''})
        self.assertTrue(all(c['type'] == 'metric_panel' for c in cards))

    def test_paged_fleet_becomes_tabs(self):
        fixture = self.fixtures['sqlite_engine_fleet']['snapshot']
        document = dashboard_ddn.ddn_to_dashboard(fixture)['dashboard']
        self.assertEqual([t['id'] for t in document['tabs']],
                         ['dashboard', 'dashboard_page_2'])
        counts = {t['id']: sum(1 for c in document['cards']
                               if c['tab_id'] == t['id'])
                  for t in document['tabs']}
        self.assertEqual(counts, {'dashboard': 12, 'dashboard_page_2': 3})

    def test_converted_dashboards_pass_the_production_validator(self):
        if shutil.which('node') is None:
            self.skipTest('node is required')
        try:
            from pgadmin.cdeadmin.workspace.dashboard_validation import (
                validate_dashboard as publish_validate,
            )
        except Exception as exc:  # pragma: no cover
            self.skipTest(f'validator unavailable: {exc}')
        for name, fixture in self.fixtures.items():
            with self.subTest(name):
                document = dashboard_ddn.ddn_to_dashboard(
                    fixture['snapshot'])['dashboard']
                snapshot = dashboard_ddn.dashboard_to_ddn(document)[
                    'snapshot']
                checked = publish_validate(
                    snapshot, fixture['scope'], engine=fixture['engine'])
                self.assertEqual(checked['format'], 'ddn-source-workspace@1')

    def test_bi_content_that_ddn_cannot_hold_is_reported(self):
        fixture = self.fixtures['sqlite_database']['snapshot']
        document = dashboard_ddn.ddn_to_dashboard(fixture)['dashboard']
        world = World()
        document['cards'].append(card('q', world.by_region, x=0, y=16,
                                      tab='dashboard'))
        document['cards'].append({
            'id': 'note', 'tab_id': 'dashboard', 'type': 'text',
            'layout': {'x': 12, 'y': 16, 'w': 12, 'h': 2},
            'text': {'markdown': 'hi'}})
        document['cards'][1]['layout'].update(x=0, y=40)
        document['filters'] = [{
            'id': 'region', 'name': 'Region', 'type': 'string',
            'targets': [{'card_id': 'q', 'parameter_id': 'region'}]}]
        converted = dashboard_ddn.dashboard_to_ddn(document)
        codes = [i['code'] for i in converted['loss']]
        self.assertEqual(codes.count('card_not_representable'), 2)
        self.assertIn('interaction_dropped', codes)
        self.assertIn('layout_normalized', codes)
        # the four monitoring panels survive
        again = dashboard_ddn.ddn_to_dashboard(converted['snapshot'])
        self.assertEqual(len(again['dashboard']['cards']), 4)
        with self.assertRaisesRegex(BIError, 'lose content'):
            dashboard_ddn.dashboard_to_ddn(document, strict=True)

    def test_conversion_refuses_what_it_cannot_represent(self):
        fixture = copy.deepcopy(self.fixtures['sqlite_database']['snapshot'])
        with self.assertRaisesRegex(BIError, 'legacy'):
            dashboard_ddn.ddn_to_dashboard({**fixture,
                                            'format': 'ddn-source-workspace'})
        with self.assertRaisesRegex(BIError, 'monitoring'):
            dashboard_ddn.dashboard_to_ddn({'name': 'BI only'})
        with self.assertRaisesRegex(BIError, 'metric_panel'):
            dashboard_ddn.dashboard_to_ddn({
                'name': 'x', 'settings': {'monitoring': {
                    'module': 'scratchrobin.sqlite.monitoring',
                    'channel': 'scratchrobin.sqlite.monitoring.'
                               'observations'}}})
        broken = copy.deepcopy(fixture)
        broken['files']['dashboard.ddn'] = broken['files'][
            'dashboard.ddn'].replace('data "observations"', 'data "other"')
        with self.assertRaisesRegex(BIError, 'not a monitoring dashboard'):
            dashboard_ddn.ddn_to_dashboard(broken)
        wide = copy.deepcopy(fixture)
        wide['files']['dashboard.ddn'] = wide['files']['dashboard.ddn'].replace(
            '                columns 2\n', '                columns 7\n')
        with self.assertRaisesRegex(BIError, 'columns'):
            dashboard_ddn.ddn_to_dashboard(wide)

    def test_unknown_declarations_and_orphans_are_loss_not_silence(self):
        fixture = copy.deepcopy(self.fixtures['sqlite_database']['snapshot'])
        text = fixture['files']['dashboard.ddn']
        text += ('\nelement "extra" as "record"\n    with\n'
                 '        id "extra"\n        title "Extra"\n')
        text = text.replace('panel "limitations"', 'panel "limitations"')
        fixture['files']['dashboard.ddn'] = text
        loss = dashboard_ddn.ddn_to_dashboard(fixture)['loss']
        self.assertEqual([i['code'] for i in loss], ['declaration_dropped'])
        # remove the composed reference to one panel: its rows are orphaned
        trimmed = copy.deepcopy(self.fixtures['sqlite_database']['snapshot'])
        marker = '                    item\n                        target\n' \
                 '                            id "limitations"'
        head, _, _ = trimmed['files']['dashboard.ddn'].partition(marker)
        trimmed['files']['dashboard.ddn'] = head
        loss = dashboard_ddn.ddn_to_dashboard(trimmed)['loss']
        self.assertIn('observations_unreferenced',
                      [i['code'] for i in loss])

    def test_writer_matches_the_javascript_encoder_on_escapes(self):
        # quotes, newlines, tabs, defaults, overlong ids and 1100-char titles
        fixture = self.escapes
        files = dashboard_ddn.dashboard_panel_files(
            fixture['panels'], fixture['title'], fixture['module'])
        self.assertEqual(files, fixture['files'])
        text = files['dashboard.ddn']
        self.assertIn('item "line1\\nline2"', text)
        self.assertIn('panel_long_1', text)
        parsed = dashboard_ddn.parse_declarations(text)
        data = next(d for d in parsed if d['kind'] == 'data')
        self.assertEqual(data['props']['rows'][0][2], 'A "quoted"\tname')
        self.assertEqual(data['props']['rows'][1][3], 'Unavailable')
        with self.assertRaises(BIError):
            dashboard_ddn.dashboard_panel_files([{
                'id': 'p', 'title': 't',
                'rows': [{'id': 'Bad Id', 'measure': 'm'}]}], 'T', 'm.x')


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
