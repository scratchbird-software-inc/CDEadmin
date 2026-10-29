##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Copy model-embedded visualizations and dashboards into BI objects.

Semantic models used to carry their own charts and dashboards
(``model.visualizations`` / ``model.dashboards``).  The BI module owns that
job now: a visualization becomes a saved *semantic* question pinned to the
model revision, and a model dashboard becomes a BI dashboard of question
cards.  The conversion is a *copy*: the model JSON is never modified, because
model reports and schedules (kept running by ``report_scheduler``) still
reference the embedded dashboards and visualizations.

The helper is idempotent.  Every created object carries a marker in its
description::

    [migrated-from-semantic-model <model_id> <visualization|dashboard> <id>]

A second run finds the markers and reports ``exists`` instead of creating a
duplicate (the BI copy may have been edited since; it is never overwritten).
``dry_run`` performs the whole conversion and validation and persists
nothing.

Conversion is lossless for the saved-question contract, which can express
group-by levels, measures, field filters, ordering and a limit.  Everything
else a cube query can carry (time-intelligence operations, analytical
windows, rollup totals, drill modes) is reported as a *loss*; a lossy
visualization is only migrated when the caller sets ``accept_loss``.

Reports and schedules are not migrated.  Converting them to BI
subscriptions is a documented TODO (docs/en_US/bi_models_view.rst): the
alerts/subscriptions branch has not merged.
"""

from __future__ import annotations

import copy
import json
import re

from pgadmin.cdeadmin.semantic_models.models import SemanticModelError

from .dashboard_models import check_mappings, validate_dashboard
from .models import BIError, validate_question

MARKER = 'migrated-from-semantic-model'
MARKER_RE = re.compile(
    r'\[' + MARKER + r' ([^\s\]]+) (visualization|dashboard) ([^\s\]]+)\]')
GRID_COLUMNS = 24
LEGACY_COLUMNS = 12
SUBSCRIPTION_TODO = (
    'Converting reports and schedules to BI subscriptions needs the '
    'alerts/subscriptions branch, which has not merged. Reports and '
    'schedules stay in the model and keep running through report_scheduler.')


def marker_text(model_id, kind, item_id):
    return f'[{MARKER} {model_id} {kind} {item_id}]'


def _describe(model, kind, item):
    return (f'Migrated from semantic model "{model["name"]}" '
            f'({kind} "{item["name"]}"). '
            f'{marker_text(model["_id"], kind, item["id"])}')[:4096]


def _clip(name):
    return str(name)[:256]


# --------------------------------------------------------------------------
# pure conversion
# --------------------------------------------------------------------------
def _levels(query):
    axes = query.get('axes') or {}
    ordered = []
    for axis in ('pages', 'rows', 'columns'):
        for item in axes.get(axis) or []:
            if item not in ordered:
                ordered.append(item)
    return ordered


def _question_parameters(model, query, filters):
    values = query.get('parameters') or {}
    wanted = set(values)
    wanted.update(item['parameter_id'] for item in filters
                  if item.get('parameter_id') is not None)
    wanted.update(item['id'] for item in model.get('parameters', [])
                  if item.get('required') and 'default' not in item)
    result = []
    for item in model.get('parameters', []):
        if item['id'] not in wanted:
            continue
        entry = {key: copy.deepcopy(item[key]) for key in (
            'id', 'name', 'type', 'required', 'allowed_values')
            if key in item}
        if item['id'] in values:
            entry['default'] = copy.deepcopy(values[item['id']])
        elif 'default' in item:
            entry['default'] = copy.deepcopy(item['default'])
        result.append(entry)
    return result


def convert_visualization(model, chart, *, reference, collection_id=None):
    """Return ``(question, losses, notes)`` for one model visualization.

    ``model`` is a validated model carrying ``_id`` (the stored model id)
    and ``reference`` is the ``{id, revision}`` pin.  The question is the
    unvalidated document; the caller passes it to ``validate_question``.
    """
    query = chart.get('query') or {}
    losses, notes = [], []
    levels = _levels(query)
    axes = query.get('axes') or {}
    if axes.get('columns') or axes.get('pages'):
        notes.append('Pivot columns and pages axes become grouping columns '
                     'of a flat result.')
    measures = list(query.get('measures') or [])
    filters = copy.deepcopy(query.get('filters') or [])
    cross = copy.deepcopy(query.get('cross_filters') or [])
    if cross:
        filters.extend(cross)
        notes.append('Cross-filters stored on the query became ordinary '
                     'filters.')
    drill = query.get('drill') or {}
    if drill.get('mode', 'summary') != 'summary':
        losses.append(f'drill mode {drill["mode"]!r} is not part of a '
                      'saved question')
    if drill.get('detail_fields'):
        losses.append('drill-through detail fields')
    if query.get('time_intelligence'):
        losses.append('time-intelligence operation '
                      f'{query["time_intelligence"].get("operation")!r}')
    if query.get('windows'):
        losses.append(f'{len(query["windows"])} analytical window '
                      'column(s)')
    if query.get('totals'):
        losses.append('rollup totals')
    outputs = set(levels) | set(measures)
    order_by = []
    for entry in query.get('order_by') or []:
        if entry.get('id') in outputs:
            order_by.append({'id': entry['id'],
                             'direction': entry.get('direction', 'asc')})
        else:
            losses.append(f'ordering by {entry.get("id")!r}, which is not a '
                          'selected level or measure')
    parameters = _question_parameters(model, query, filters)
    if query.get('parameters'):
        notes.append('Parameter values set on the visualization are stored '
                     'as question parameter defaults.')
    encodings = chart.get('encodings') or {}
    settings = {}
    if encodings.get('x'):
        settings['x'] = encodings['x']
    if encodings.get('y'):
        settings['y'] = [encodings['y']]
    question = {
        'name': _clip(chart['name']),
        'description': _describe(model, 'visualization', chart),
        'collection_id': collection_id,
        'semantic_model': copy.deepcopy(reference),
        'parameters': parameters,
        'visualization': {'type': chart.get('chart_type', 'table'),
                          'settings': settings},
        'query': {'kind': 'semantic', 'builder': {
            'group_by': levels,
            'aggregations': [{'measure_id': item} for item in measures],
            'filters': filters, 'order_by': order_by,
            'limit': query.get('limit', 500)}},
    }
    return question, losses, notes


def _layout(tile, index):
    legacy = tile.get('layout') or {}
    numbers = all(isinstance(legacy.get(key), (int, float)) and
                  not isinstance(legacy.get(key), bool)
                  for key in ('x', 'y', 'width', 'height'))
    if not numbers:
        return {'x': (index % 2) * 12, 'y': (index // 2) * 6, 'w': 12,
                'h': 6}
    scale = GRID_COLUMNS // LEGACY_COLUMNS
    x = min(max(int(legacy['x']) * scale, 0), GRID_COLUMNS - 1)
    w = min(max(int(legacy['width']) * scale, 1), GRID_COLUMNS - x)
    return {'x': x, 'y': min(max(int(legacy['y']), 0), 10000), 'w': w,
            'h': min(max(int(legacy['height']), 1), 100)}


def _dimension_references(model):
    """Map every dimension and level id to ``(name, value_type, field)``."""
    found = {}
    for dimension in model.get('dimensions', []):
        time = dimension.get('time_intelligence') or {}
        kind = time.get('value_type', 'string')
        kind = kind if kind in ('date', 'datetime') else 'string'
        found[dimension['id']] = (dimension['name'], kind,
                                  dimension['field'])
        for hierarchy in dimension.get('hierarchies', []):
            for level in hierarchy.get('levels', []):
                found[level['id']] = (
                    f'{dimension["name"]} / {level["name"]}', kind,
                    level['field'])
    return found


def convert_dashboard(model, dashboard, pins, *, collection_id=None):
    """Return ``(document, losses, notes)`` for one model dashboard.

    ``pins`` maps visualization id to the ``(question_id, revision)`` its
    question was created with.  Tiles whose visualization has no pin are
    reported by the caller before this is called.
    """
    losses, notes = [], []
    cards, used = [], set()
    visualizations = {item['id']: item
                      for item in model.get('visualizations', [])}
    for index, tile in enumerate(dashboard.get('tiles', [])):
        viz_id = tile['visualization_id']
        question_id, revision = pins[viz_id]
        card_id = f'card_{viz_id}'[:120]
        suffix = 2
        while card_id in used:
            card_id = f'card_{viz_id}'[:112] + f'_{suffix}'
            suffix += 1
        used.add(card_id)
        cards.append({
            'id': card_id, 'tab_id': 'main', 'type': 'question',
            'layout': _layout(tile, index),
            'title': _clip(visualizations[viz_id]['name']),
            'question': {'question_id': question_id, 'revision': revision},
            '_viz': viz_id})
    filters, links = [], []
    if dashboard.get('cross_filtering', True) and len(cards) > 1:
        references = _dimension_references(model)
        by_field = {}
        for card in cards:
            encoding = (visualizations[card['_viz']].get('encodings') or {}
                        ).get('x')
            reference = references.get(encoding)
            if reference is None:
                continue
            name, value_type, field = reference
            key = (field['source_id'], field['field'])
            if key not in by_field:
                by_field[key] = {
                    'id': f'xf_{len(by_field) + 1}',
                    'name': _clip(f'Selected {name}'), 'type': value_type,
                    'widget': 'date' if value_type != 'string' else 'text',
                    'operator': 'eq', 'targets': [
                        {'card_id': target['id'], 'field': {
                            'source_id': field['source_id'],
                            'field': field['field']}}
                        for target in cards]}
            links.append({
                'id': f'click_{card["id"]}'[:128],
                'source_card_id': card['id'], 'source_column': encoding,
                'filter_id': by_field[key]['id'],
                'exclude_source': False})
        filters = list(by_field.values())
        if filters:
            notes.append('Clicking a chart value now filters the other '
                         'cards through dashboard cross-filters; values '
                         'are compared as text unless the dimension is a '
                         'date or datetime.')
    for card in cards:
        card.pop('_viz')
    document = {
        'name': _clip(dashboard['name']),
        'description': _describe(model, 'dashboard', dashboard),
        'collection_id': collection_id,
        'tabs': [{'id': 'main', 'name': 'Main'}], 'cards': cards,
        'filters': filters, 'cross_filters': links,
    }
    return document, losses, notes


# --------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------
class ModelMigration:
    """Plan or apply the copy for one stored model."""

    def __init__(self, semantic_service, bi_service, dashboard_service=None):
        self.semantic = semantic_service
        self.bi = bi_service
        self.dashboards = dashboard_service

    # discovery of earlier runs --------------------------------------------
    @staticmethod
    def _markers(rows):
        found = {}
        for row in rows:
            try:
                text = json.loads(row.definition).get('description') or ''
            except (TypeError, ValueError):
                continue
            for match in MARKER_RE.finditer(text):
                found[match.groups()] = row
        return found

    def _collection(self, user_id, endpoint_id, model, collection_id,
                    dry_run):
        if collection_id is not None:
            self.bi.access.require(user_id, 'collection', endpoint_id,
                                   collection_id, 'edit', 'add items to')
            return collection_id, {'action': 'given',
                                   'collection_id': collection_id}
        name = _clip(f'Migrated: {model["name"]}')
        for row in self.bi.repository.collections(user_id):
            if row.parent_id is None and row.name == name:
                return row.id, {'action': 'exists', 'collection_id': row.id,
                                'name': name}
        if dry_run:
            return None, {'action': 'create', 'collection_id': None,
                          'name': name}
        created = self.bi.create_collection(
            user_id, {'name': name, 'parent_id': None,
                      'description': 'Created by the semantic model '
                                     'migration.'}, endpoint_id)
        return created['collection_id'], {
            'action': 'create', 'collection_id': created['collection_id'],
            'name': name}

    @staticmethod
    def _unique(name, used):
        candidate, count = name, 1
        while candidate in used:
            count += 1
            tag = ' (migrated)' if count == 2 else f' (migrated {count - 1})'
            candidate = _clip(name[:256 - len(tag)] + tag)
        used.add(candidate)
        return candidate

    def run(self, user_id, endpoint_id, model_id, *, dry_run=True,
            accept_loss=False, collection_id=None):
        record = self.semantic.get(user_id, endpoint_id, model_id)
        model = copy.deepcopy(record['definition'])
        model['_id'] = model_id
        reference = {'id': model_id, 'revision': record['revision']}
        target_id, target = self._collection(
            user_id, endpoint_id, model, collection_id, dry_run)
        question_rows = self.bi.repository.questions(user_id, endpoint_id)
        question_markers = self._markers(question_rows)
        used_questions = {row.name for row in question_rows
                          if row.collection_id == target_id}
        dashboard_rows = self.dashboards.repository.dashboards(
            user_id, endpoint_id) if self.dashboards is not None else []
        dashboard_markers = self._markers(dashboard_rows)
        used_dashboards = {row.name for row in dashboard_rows
                           if row.collection_id == target_id}

        questions, pins, definitions = [], {}, {}
        for chart in model.get('visualizations', []):
            item = {'visualization_id': chart['id'], 'name': chart['name'],
                    'question_id': None, 'revision': None}
            questions.append(item)
            key = (model_id, 'visualization', chart['id'])
            if key in question_markers:
                row = question_markers[key]
                item.update(action='exists', fidelity='exact', losses=[],
                            notes=[], question_id=row.id,
                            revision=row.revision, name=row.name)
                pins[chart['id']] = (row.id, row.revision)
                definitions[pins[chart['id']]] = json.loads(row.definition)
                continue
            try:
                document, losses, notes = convert_visualization(
                    model, chart, reference=reference,
                    collection_id=target_id)
                document['name'] = self._unique(document['name'],
                                                used_questions)
                validated = validate_question(document)
            except (BIError, SemanticModelError, KeyError) as exc:
                item.update(action='error', fidelity=None, losses=[],
                            notes=[], error=str(exc))
                continue
            item.update(name=validated['name'], losses=losses, notes=notes,
                        fidelity='lossy' if losses else 'exact')
            if losses and not accept_loss:
                item.update(action='skipped', reason=(
                    'lossy conversion; accept the losses to migrate it'))
                continue
            if dry_run:
                item['action'] = 'create'
                pins[chart['id']] = (f'dry-run-{len(pins) + 1}', 1)
                definitions[pins[chart['id']]] = validated
                continue
            try:
                created = self.bi.create_question(user_id, endpoint_id,
                                                  validated)
            except (BIError, SemanticModelError) as exc:
                item.update(action='error', error=str(exc))
                continue
            item.update(action='create', question_id=created['question_id'],
                        revision=created['revision'])
            pins[chart['id']] = (created['question_id'],
                                 created['revision'])
            definitions[pins[chart['id']]] = validated
        by_viz = {item['visualization_id']: item for item in questions}

        dashboards = []
        for dashboard in model.get('dashboards', []):
            item = {'model_dashboard_id': dashboard['id'],
                    'name': dashboard['name'], 'dashboard_id': None,
                    'tiles': len(dashboard.get('tiles', []))}
            dashboards.append(item)
            key = (model_id, 'dashboard', dashboard['id'])
            if key in dashboard_markers:
                row = dashboard_markers[key]
                item.update(action='exists', dashboard_id=row.id,
                            name=row.name, losses=[], notes=[])
                continue
            blockers = []
            for tile in dashboard.get('tiles', []):
                state = by_viz.get(tile['visualization_id'])
                if tile['visualization_id'] not in pins:
                    why = (state or {}).get('action', 'missing')
                    blockers.append(
                        f'visualization {tile["visualization_id"]!r} is '
                        f'not available ({why})')
            if blockers:
                item.update(action='blocked', losses=[], notes=[],
                            reason='; '.join(blockers))
                continue
            if self.dashboards is None:
                item.update(action='blocked', losses=[], notes=[],
                            reason='dashboards are not initialized')
                continue
            try:
                document, losses, notes = convert_dashboard(
                    model, dashboard, pins, collection_id=target_id)
                document['name'] = self._unique(document['name'],
                                                used_dashboards)
                validated = validate_dashboard(document)
                check_mappings(validated, definitions)
            except (BIError, SemanticModelError, KeyError) as exc:
                item.update(action='error', losses=[], notes=[],
                            error=str(exc))
                continue
            item.update(name=validated['name'], losses=losses, notes=notes)
            if dry_run:
                item['action'] = 'create'
                continue
            try:
                created = self.dashboards.create(user_id, endpoint_id,
                                                 validated)
            except (BIError, SemanticModelError) as exc:
                item.update(action='error', error=str(exc))
                continue
            item.update(action='create', dashboard_id=created['dashboard_id'])

        counts = {}
        for group in (questions, dashboards):
            for item in group:
                counts[item['action']] = counts.get(item['action'], 0) + 1
        return {
            'model_id': model_id, 'model_revision': record['revision'],
            'dry_run': bool(dry_run), 'accept_loss': bool(accept_loss),
            'collection': target, 'questions': questions,
            'dashboards': dashboards,
            'reports': [{'id': item['id'], 'name': item['name'],
                         'dashboard_id': item.get('dashboard_id'),
                         'schedule_id': item.get('schedule_id'),
                         'state': 'kept-in-model'}
                        for item in model.get('reports', [])],
            'schedules': [{'id': item['id'], 'name': item['name'],
                           'enabled': item.get('enabled', False),
                           'state': 'kept-in-model'}
                          for item in model.get('schedules', [])],
            'subscription_conversion': {
                'available': False, 'todo': SUBSCRIPTION_TODO},
            'summary': counts,
        }
