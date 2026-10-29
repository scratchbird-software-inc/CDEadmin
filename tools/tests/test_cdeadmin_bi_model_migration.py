##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Migration of model-embedded visualizations and dashboards into BI
questions and dashboards: dry run, idempotency, loss reporting, layout and
cross-filter conversion, and the workspace actions that expose it."""

from __future__ import annotations

import copy
import json
import unittest
from types import SimpleNamespace

import bi_live_harness as harness
from bi_live_harness import Stack

from pgadmin.cdeadmin.bi.dashboard_models import (
    resolve_cross_filter, resolve_filters, validate_dashboard,
)
from pgadmin.cdeadmin.bi.dashboards import DashboardService
from pgadmin.cdeadmin.bi.model_migration import (
    MARKER_RE, ModelMigration, convert_dashboard, convert_visualization,
    marker_text,
)
from pgadmin.cdeadmin.bi.models import validate_question
from pgadmin.cdeadmin.semantic_models import (
    SemanticModelError, validate_model,
)
from test_cdeadmin_bi_dashboards import MemoryDashboards

OWNER = 1
OTHER = 2


def legacy_model(**extra):
    """A model with the content the retired workspace could author."""
    model = {
        'name': 'Sales cube',
        'sources': [{'id': 'sales', 'resource_id': 'table:sales',
                     'relation': ['sales'], 'alias': 'sales'}],
        'dimensions': [{
            'id': 'region', 'name': 'Region',
            'field': {'source_id': 'sales', 'field': 'region'},
            'hierarchies': [{'id': 'geo', 'name': 'Geography', 'levels': [{
                'id': 'region_level', 'name': 'Region',
                'field': {'source_id': 'sales', 'field': 'region'}}]}]}],
        'measures': [
            {'id': 'revenue', 'name': 'Revenue', 'aggregation': 'sum',
             'field': {'source_id': 'sales', 'field': 'amount'}},
            {'id': 'orders', 'name': 'Orders', 'aggregation': 'count',
             'field': None}],
        'parameters': [{'id': 'floor', 'name': 'Floor', 'type': 'integer',
                        'required': False, 'default': 0}],
        'visualizations': [
            {'id': 'by_region', 'name': 'Revenue by region',
             'chart_type': 'bar',
             'query': {'axes': {'rows': ['region_level'], 'columns': [],
                                'pages': []},
                       'measures': ['revenue', 'orders'],
                       'filters': [{'field': {'source_id': 'sales',
                                              'field': 'amount'},
                                    'operator': 'gte',
                                    'parameter_id': 'floor'}],
                       'order_by': [{'id': 'revenue', 'direction': 'desc'}],
                       'limit': 20},
             'encodings': {'x': 'region_level', 'y': 'revenue'}},
            {'id': 'total', 'name': 'Total revenue', 'chart_type': 'metric',
             'query': {'axes': {'rows': [], 'columns': [], 'pages': []},
                       'measures': ['revenue'], 'filters': []},
             'encodings': {'y': 'revenue'}},
        ],
        'dashboards': [{
            'id': 'overview', 'name': 'Overview', 'cross_filtering': True,
            'tiles': [
                {'visualization_id': 'by_region',
                 'layout': {'x': 0, 'y': 0, 'width': 6, 'height': 4}},
                {'visualization_id': 'total',
                 'layout': {'x': 6, 'y': 0, 'width': 6, 'height': 4}}]}],
        'schedules': [{'id': 'daily', 'name': 'Daily', 'expression':
                       '0 8 * * *', 'timezone': 'UTC', 'enabled': False}],
        'reports': [{'id': 'morning', 'name': 'Morning', 'dashboard_id':
                     'overview', 'schedule_id': 'daily',
                     'export_formats': ['csv']}],
    }
    model.update(extra)
    return model


def windowed(model):
    """Add a visualization the saved-question contract cannot hold."""
    model = copy.deepcopy(model)
    model['visualizations'].append({
        'id': 'running', 'name': 'Running revenue', 'chart_type': 'line',
        'query': {'axes': {'rows': ['region_level'], 'columns': [],
                           'pages': []},
                  'measures': ['revenue'],
                  'windows': [{'id': 'run', 'measure_id': 'revenue',
                               'operation': 'running_sum',
                               'order_by': {'level_id': 'region_level',
                                            'direction': 'asc'}}],
                  'order_by': [{'id': 'run', 'direction': 'asc'}],
                  'totals': True},
        'encodings': {'x': 'region_level', 'y': 'run'}})
    model['dashboards'].append({
        'id': 'trend', 'name': 'Trend', 'tiles': [
            {'visualization_id': 'running', 'layout': {}}]})
    return model


class World:
    def __init__(self, model=None):
        self.stack = Stack('sqlite', 'migration')
        self.endpoint = self.stack.ctx.endpoint_id
        self.repo = MemoryDashboards()
        self.dashboards = DashboardService(
            self.stack.bi, self.stack.executor, repository=self.repo)
        self.semantic = self.stack.bi.semantic
        self.model = self.semantic.create(
            OWNER, self.endpoint, model or legacy_model())
        self.migration = ModelMigration(
            self.semantic, self.stack.bi, self.dashboards)

    def run(self, user=OWNER, **options):
        return self.migration.run(
            user, self.endpoint, self.model['model_id'], **options)

    def counts(self):
        return (len(self.stack.bi.repository.questions(OWNER, self.endpoint)),
                len(self.repo.dashboards(OWNER, self.endpoint)),
                len(self.stack.bi.repository.collections(OWNER)))


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.model = validate_model(legacy_model())
        self.model['_id'] = 'm-1'
        self.reference = {'id': 'm-1', 'revision': 3}

    def chart(self, name):
        return next(c for c in self.model['visualizations']
                    if c['id'] == name)

    def test_visualization_becomes_a_valid_semantic_question(self):
        question, losses, _notes = convert_visualization(
            self.model, self.chart('by_region'), reference=self.reference)
        validated = validate_question(question)
        self.assertEqual(losses, [])
        self.assertEqual(validated['semantic_model'], self.reference)
        builder = validated['query']['builder']
        self.assertEqual(builder['group_by'], ['region_level'])
        self.assertEqual([a['measure_id'] for a in builder['aggregations']],
                         ['revenue', 'orders'])
        self.assertEqual(builder['order_by'],
                         [{'id': 'revenue', 'direction': 'desc'}])
        self.assertEqual(builder['limit'], 20)
        self.assertEqual(validated['visualization'],
                         {'type': 'bar', 'settings': {
                             'x': 'region_level', 'y': ['revenue']}})
        # the filter's parameter is declared on the question
        self.assertEqual([p['id'] for p in validated['parameters']],
                         ['floor'])
        self.assertTrue(MARKER_RE.search(validated['description']))

    def test_unsupported_features_are_reported_as_losses(self):
        model = validate_model(windowed(legacy_model()))
        model['_id'] = 'm-1'
        chart = next(c for c in model['visualizations']
                     if c['id'] == 'running')
        question, losses, _ = convert_visualization(
            model, chart, reference=self.reference)
        text = ' '.join(losses)
        self.assertIn('analytical window', text)
        self.assertIn('rollup totals', text)
        self.assertIn("ordering by 'run'", text)
        validate_question(question)  # still a valid (reduced) question

    def test_legacy_layout_scales_to_the_24_column_grid(self):
        question_pins = {'by_region': ('q1', 1), 'total': ('q2', 1)}
        document, _l, _n = convert_dashboard(
            self.model, self.model['dashboards'][0], question_pins)
        layouts = [c['layout'] for c in document['cards']]
        self.assertEqual(layouts[0], {'x': 0, 'y': 0, 'w': 12, 'h': 4})
        self.assertEqual(layouts[1], {'x': 12, 'y': 0, 'w': 12, 'h': 4})
        validate_dashboard(document)

    def test_missing_layout_flows_two_per_row(self):
        model = copy.deepcopy(self.model)
        for tile in model['dashboards'][0]['tiles']:
            tile['layout'] = {}
        document, _l, _n = convert_dashboard(
            model, model['dashboards'][0],
            {'by_region': ('q1', 1), 'total': ('q2', 1)})
        self.assertEqual([c['layout']['x'] for c in document['cards']],
                         [0, 12])

    def test_cross_filtering_becomes_dashboard_cross_filters(self):
        document, _l, notes = convert_dashboard(
            self.model, self.model['dashboards'][0],
            {'by_region': ('q1', 1), 'total': ('q2', 1)})
        validated = validate_dashboard(document)
        self.assertEqual(len(validated['filters']), 1)
        flt = validated['filters'][0]
        self.assertEqual([t['card_id'] for t in flt['targets']],
                         [c['id'] for c in validated['cards']])
        self.assertTrue(notes)
        link = validated['cross_filters'][0]
        self.assertEqual(link['source_column'], 'region_level')
        outcome = resolve_cross_filter(
            validated, link['id'], {'region_level': 'east'})
        resolved = resolve_filters(validated, outcome['filters'],
                                   outcome['exclude'])
        bound = resolved['cards'][validated['cards'][1]['id']]
        self.assertEqual(bound['extra_filters'], [{
            'operator': 'eq', 'value': 'east',
            'field': {'source_id': 'sales', 'field': 'region'}}])

    def test_independent_tiles_make_no_cross_filters(self):
        model = copy.deepcopy(self.model)
        model['dashboards'][0]['cross_filtering'] = False
        document, _l, _n = convert_dashboard(
            model, model['dashboards'][0],
            {'by_region': ('q1', 1), 'total': ('q2', 1)})
        self.assertEqual((document['filters'], document['cross_filters']),
                         ([], []))


class MigrationTests(unittest.TestCase):
    def test_dry_run_converts_and_validates_but_persists_nothing(self):
        world = World()
        before = world.counts()
        report = world.run(dry_run=True)
        self.assertTrue(report['dry_run'])
        self.assertEqual(world.counts(), before)
        self.assertEqual([q['action'] for q in report['questions']],
                         ['create', 'create'])
        self.assertEqual([d['action'] for d in report['dashboards']],
                         ['create'])
        self.assertEqual(report['collection']['action'], 'create')
        self.assertEqual(report['collection']['name'],
                         'Migrated: Sales cube')
        self.assertFalse(
            report['subscription_conversion']['available'])
        self.assertIn('alerts/subscriptions',
                      report['subscription_conversion']['todo'])

    def test_dry_run_is_the_default_when_called_without_options(self):
        world = World()
        self.assertTrue(world.run()['dry_run'])
        self.assertEqual(world.counts(), (0, 0, 0))

    def test_apply_creates_questions_dashboards_and_a_collection(self):
        world = World()
        report = world.run(dry_run=False)
        self.assertEqual(world.counts(), (2, 1, 1))
        collection = report['collection']['collection_id']
        for item in report['questions']:
            stored = world.stack.bi.get_question(
                OWNER, world.endpoint, item['question_id'])
            self.assertEqual(stored['definition']['collection_id'],
                             collection)
            self.assertEqual(
                stored['definition']['semantic_model'],
                {'id': world.model['model_id'],
                 'revision': world.model['revision']})
        dashboard = world.dashboards.get(
            OWNER, world.endpoint,
            report['dashboards'][0]['dashboard_id'])['definition']
        pins = {c['question']['question_id'] for c in dashboard['cards']}
        self.assertEqual(
            pins, {q['question_id'] for q in report['questions']})

    def test_migrated_question_returns_the_legacy_query_rows(self):
        world = World()
        report = world.run(dry_run=False)
        question_id = report['questions'][0]['question_id']
        outcome = world.stack.run(question_id=question_id,
                                  parameters={'floor': 0})
        view = outcome['page']['view_model']
        rows = view.get('rows', view.get('records', []))
        revenue = {r['region_level']: r['revenue'] for r in rows}
        self.assertEqual(revenue, {'east': 40, 'west': 65})

    def test_second_run_is_idempotent(self):
        world = World()
        first = world.run(dry_run=False)
        counts = world.counts()
        second = world.run(dry_run=False)
        self.assertEqual(world.counts(), counts)
        self.assertEqual([q['action'] for q in second['questions']],
                         ['exists', 'exists'])
        self.assertEqual([d['action'] for d in second['dashboards']],
                         ['exists'])
        self.assertEqual(second['collection']['action'], 'exists')
        self.assertEqual(
            [q['question_id'] for q in first['questions']],
            [q['question_id'] for q in second['questions']])
        # a dry run after the fact reports the same
        third = world.run(dry_run=True)
        self.assertEqual(third['summary'], {'exists': 3})

    def test_renamed_copy_is_still_found_by_its_marker(self):
        world = World()
        first = world.run(dry_run=False)
        question_id = first['questions'][0]['question_id']
        stored = world.stack.bi.get_question(OWNER, world.endpoint,
                                             question_id)
        edited = copy.deepcopy(stored['definition'])
        edited['name'] = 'Renamed by the user'
        world.stack.bi.update_question(
            OWNER, world.endpoint, question_id, stored['revision'], edited)
        counts = world.counts()
        again = world.run(dry_run=False)
        self.assertEqual(world.counts(), counts)
        self.assertEqual(again['questions'][0]['action'], 'exists')
        self.assertEqual(again['questions'][0]['name'],
                         'Renamed by the user')

    def test_model_json_is_never_modified(self):
        world = World()
        before = world.semantic.get(OWNER, world.endpoint,
                                    world.model['model_id'])
        world.run(dry_run=False)
        after = world.semantic.get(OWNER, world.endpoint,
                                   world.model['model_id'])
        self.assertEqual(before, after)
        self.assertEqual(after['definition']['reports'][0]['id'], 'morning')
        self.assertEqual(len(after['definition']['dashboards']), 1)
        # and it still validates exactly as before
        validate_model(after['definition'])

    def test_reports_and_schedules_are_listed_as_kept(self):
        report = World().run()
        self.assertEqual(
            [(r['id'], r['state']) for r in report['reports']],
            [('morning', 'kept-in-model')])
        self.assertEqual(
            [(s['id'], s['state']) for s in report['schedules']],
            [('daily', 'kept-in-model')])

    def test_lossy_visualizations_need_accept_loss(self):
        world = World(windowed(legacy_model()))
        report = world.run(dry_run=False)
        by_id = {q['visualization_id']: q for q in report['questions']}
        self.assertEqual(by_id['running']['action'], 'skipped')
        self.assertEqual(by_id['running']['fidelity'], 'lossy')
        self.assertTrue(by_id['running']['losses'])
        self.assertEqual(by_id['by_region']['action'], 'create')
        trend = next(d for d in report['dashboards']
                     if d['model_dashboard_id'] == 'trend')
        self.assertEqual(trend['action'], 'blocked')
        self.assertIn('running', trend['reason'])
        self.assertEqual(world.counts()[:2], (2, 1))

        accepted = world.run(dry_run=False, accept_loss=True)
        by_id = {q['visualization_id']: q for q in accepted['questions']}
        self.assertEqual(by_id['running']['action'], 'create')
        self.assertEqual(by_id['by_region']['action'], 'exists')
        self.assertEqual(
            next(d for d in accepted['dashboards']
                 if d['model_dashboard_id'] == 'trend')['action'], 'create')
        self.assertEqual(world.counts()[:2], (3, 2))

    def test_name_collision_gets_a_migrated_suffix(self):
        world = World()
        collection = world.stack.bi.create_collection(
            OWNER, {'name': 'Migrated: Sales cube'}, world.endpoint)
        world.stack.bi.create_question(OWNER, world.endpoint, {
            'name': 'Total revenue',
            'collection_id': collection['collection_id'],
            'query': {'kind': 'builder', 'builder': {
                'source': {'relation': ['sales']}, 'columns': ['region']}}})
        report = world.run(dry_run=False)
        names = {q['visualization_id']: q['name']
                 for q in report['questions']}
        self.assertEqual(names['total'], 'Total revenue (migrated)')
        self.assertEqual(report['collection']['action'], 'exists')

    def test_explicit_collection_is_used_and_checked(self):
        world = World()
        folder = world.stack.bi.create_collection(
            OWNER, {'name': 'Mine'}, world.endpoint)['collection_id']
        report = world.run(dry_run=False, collection_id=folder)
        self.assertEqual(report['collection']['action'], 'given')
        stored = world.stack.bi.get_question(
            OWNER, world.endpoint, report['questions'][0]['question_id'])
        self.assertEqual(stored['definition']['collection_id'], folder)
        with self.assertRaises(Exception):
            world.run(user=OWNER, dry_run=False, collection_id='missing')

    def test_another_user_cannot_migrate_the_model(self):
        world = World()
        with self.assertRaises(SemanticModelError):
            world.run(user=OTHER, dry_run=False)
        self.assertEqual(world.counts(), (0, 0, 0))

    def test_model_without_embedded_content_has_nothing_to_do(self):
        model = legacy_model()
        for key in ('visualizations', 'dashboards', 'schedules', 'reports'):
            model[key] = []
        report = World(model).run(dry_run=False)
        self.assertEqual((report['questions'], report['dashboards']),
                         ([], []))

    def test_invalid_visualization_is_an_error_item_not_a_failure(self):
        world = World()
        original = convert_visualization

        import pgadmin.cdeadmin.bi.model_migration as module

        def broken(model, chart, **options):
            if chart['id'] == 'total':
                raise KeyError('boom')
            return original(model, chart, **options)

        module.convert_visualization = broken
        try:
            report = world.run(dry_run=False)
        finally:
            module.convert_visualization = original
        actions = {q['visualization_id']: q['action']
                   for q in report['questions']}
        self.assertEqual(actions, {'by_region': 'create', 'total': 'error'})
        self.assertEqual(report['dashboards'][0]['action'], 'blocked')


class MarkerTests(unittest.TestCase):
    def test_marker_round_trip(self):
        text = f'Migrated. {marker_text("abc", "dashboard", "d-1")} tail'
        self.assertEqual(MARKER_RE.search(text).groups(),
                         ('abc', 'dashboard', 'd-1'))


class WorkspaceActionTests(unittest.TestCase):
    """The semantic_model_* actions the Models view calls."""

    def setUp(self):
        from pgadmin.cdeadmin.workspace import ProviderWorkspaceService
        self.world = World()
        service = ProviderWorkspaceService.__new__(ProviderWorkspaceService)
        service.semantic_model_service = self.world.semantic
        service.bi_service = self.world.stack.bi
        self.world.stack.bi.dashboards = self.world.dashboards
        service.report_delivery_service = None
        service.report_scheduler_service = None
        context = self.world.stack.ctx
        provider = self.world.stack.provider
        service.endpoint_service = SimpleNamespace(
            workspace=lambda _server: (context, {'route': {}}, None),
            provider_registry=SimpleNamespace(resolve=lambda _c:
                                              SimpleNamespace(
                                                  instance=provider)))
        self.service = service
        self.server = SimpleNamespace(user_id=OWNER)

    def act(self, action, **request):
        return self.service.semantic_model_action(
            self.server, action, request)

    def test_migrate_defaults_to_a_dry_run(self):
        report = self.act('semantic_model_migrate',
                          model_id=self.world.model['model_id'])
        self.assertTrue(report['dry_run'])
        self.assertEqual(self.world.counts(), (0, 0, 0))

    def test_migrate_apply_through_the_action(self):
        report = self.act('semantic_model_migrate', dry_run=False,
                          model_id=self.world.model['model_id'])
        self.assertEqual(report['summary'], {'create': 3})
        self.assertEqual(self.world.counts(), (2, 1, 1))

    def test_migrate_rejects_non_boolean_flags(self):
        from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceError
        with self.assertRaises(ProviderWorkspaceError):
            self.act('semantic_model_migrate', dry_run='no',
                     model_id=self.world.model['model_id'])

    def test_capabilities_action_carries_the_designer_catalog(self):
        catalog = self.act('semantic_model_capabilities')
        self.assertTrue(catalog['capabilities']['designer'])
        self.assertIn('analytical_profile', catalog['capabilities'])
        self.assertEqual(catalog['delegations'], [])
        self.assertFalse(catalog['delivery']['automatic_scheduling'])
        # the payload is plain JSON
        json.dumps(catalog)


if __name__ == '__main__':
    unittest.main()
