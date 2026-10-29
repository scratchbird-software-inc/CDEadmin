##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""The one dashboard document: validation and pure resolution rules.

A dashboard document is what BI dashboards and (converted) monitoring
dashboards share.  Cards are positioned on a 24-column grid inside tabs:

``question``
    A pinned saved-question revision ``{question_id, revision}`` plus an
    optional visualization override.
``text``
    Markdown text.
``metric_panel``
    A monitoring panel bound to a collector channel (see ``dashboard_ddn``).
    It carries no query; live values come from the collector, never from a
    saved question.

Dashboard *filters* map onto question *parameters* or onto a *field* of the
question (builder column or semantic field) as an extra bound filter.
Cross-filters turn a click on a card into a filter value; drill-throughs open
a question or another dashboard with values taken from the clicked row.

Everything here is pure; storage is in ``dashboards.py``.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping

from pgadmin.cdeadmin.semantic_models.models import (
    PARAMETER_TYPES, SemanticModelError, _validate_parameter_value,
)

from .models import (
    BIError, _ident, _list, _map, _text, validate_visualization,
)

DASHBOARD_CONTRACT_VERSION = '1.0.0'
GRID_COLUMNS = 24
MAX_CARDS = 100
MAX_TABS = 16
MAX_FILTERS = 32
MAX_LINKS = 64
CARD_TYPES = frozenset({'question', 'text', 'metric_panel'})
WIDGETS = frozenset({'text', 'select', 'number', 'date', 'date_range',
                     'toggle', 'multi_select'})
FIELD_OPERATORS = frozenset({
    'eq', 'ne', 'lt', 'lte', 'gt', 'gte', 'in', 'not_in', 'between',
})
DASHBOARD_STATUSES = frozenset({'active', 'archived'})
MAX_TEXT = 20000


def _int(value, label, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not (
            low <= value <= high):
        raise BIError(f'{label} must be an integer from {low} to {high}')
    return value


def _layout(value):
    item = _map(value, 'card.layout')
    x = _int(item.get('x'), 'layout.x', 0, GRID_COLUMNS - 1)
    w = _int(item.get('w'), 'layout.w', 1, GRID_COLUMNS)
    if x + w > GRID_COLUMNS:
        raise BIError(f'card exceeds the {GRID_COLUMNS}-column grid')
    return {'x': x, 'y': _int(item.get('y'), 'layout.y', 0, 10000),
            'w': w, 'h': _int(item.get('h'), 'layout.h', 1, 100)}


def _metric_panel(value):
    item = _map(value, 'card.metric_panel')
    columns, rows = [], []
    for raw in _list(item.get('columns', []), 'metric_panel.columns', 16):
        column = _map(raw, 'metric_panel column')
        columns.append({'id': _text(column.get('id'), 'column.id', 128),
                        'label': str(column.get('label', column.get('id')))[
                            :1024]})
    for raw in _list(item.get('rows', []), 'metric_panel.rows', 4096):
        row = _map(raw, 'metric_panel row')
        entry = {'id': _text(row.get('id'), 'row.id', 2048)}
        for name in ('measure', 'value', 'unit', 'rate'):
            entry[name] = str(row.get(name, ''))[:4096]
        rows.append(entry)
    return {'panel_id': _text(item.get('panel_id'), 'metric_panel.panel_id',
                              2048),
            'columns': columns, 'rows': rows}


def _card(raw, tab_ids):
    item = _map(raw, 'card')
    kind = item.get('type')
    if kind not in CARD_TYPES:
        raise BIError('card.type must be question, text or metric_panel')
    tab_id = item.get('tab_id')
    if tab_id not in tab_ids:
        raise BIError('card.tab_id names an unknown tab')
    card = {'id': _ident(item.get('id'), 'card.id'), 'tab_id': tab_id,
            'type': kind, 'layout': _layout(item.get('layout')),
            'title': str(item.get('title') or '')[:256]}
    if kind == 'question':
        question = _map(item.get('question'), 'card.question')
        card['question'] = {
            'question_id': _text(question.get('question_id'),
                                 'card.question.question_id', 36),
            'revision': _int(question.get('revision'),
                             'card.question.revision', 1, 10 ** 9),
        }
        if item.get('visualization') is not None:
            card['visualization'] = validate_visualization(
                item['visualization'])
    elif kind == 'text':
        text = _map(item.get('text'), 'card.text')
        body = text.get('markdown')
        if not isinstance(body, str) or len(body) > MAX_TEXT:
            raise BIError('card.text.markdown must be text up to '
                          f'{MAX_TEXT} characters')
        card['text'] = {'markdown': body}
    else:
        card['metric_panel'] = _metric_panel(item.get('metric_panel'))
    return card


def _filter(raw, cards):
    item = _map(raw, 'filter')
    fid = _ident(item.get('id'), 'filter.id')
    ftype = item.get('type', 'string')
    if ftype not in PARAMETER_TYPES or ftype == 'array':
        raise BIError('filter.type is unsupported (use multiple for lists)')
    widget = item.get('widget', 'text')
    if widget not in WIDGETS:
        raise BIError('filter.widget is unsupported')
    multiple = bool(item.get('multiple', widget == 'multi_select'))
    operator = item.get('operator')
    if operator is None:
        operator = ('between' if widget == 'date_range' else
                    'in' if multiple else 'eq')
    if operator not in FIELD_OPERATORS:
        raise BIError('filter.operator is unsupported')
    if operator in {'in', 'not_in'}:
        multiple = True
    elif multiple:
        raise BIError('a multiple filter needs the in or not_in operator')
    allowed = _list(item.get('allowed_values', []),
                    'filter.allowed_values', 500)
    entry = {'id': fid, 'name': _text(item.get('name', fid), 'filter.name',
                                      256),
             'type': ftype, 'widget': widget, 'multiple': multiple,
             'operator': operator, 'required': bool(item.get('required',
                                                             False)),
             'allowed_values': allowed, 'targets': []}
    try:
        for value in allowed:
            _validate_parameter_value(value, ftype)
    except SemanticModelError as exc:
        raise BIError(str(exc)) from exc
    if 'default' in item:
        _check_value(entry, item['default'])
        entry['default'] = item['default']
    seen = set()
    for raw_target in _list(item.get('targets', []), 'filter.targets', 128):
        target = _map(raw_target, 'filter target')
        card_id = target.get('card_id')
        card = cards.get(card_id)
        if card is None or card['type'] != 'question':
            raise BIError('filter target must name a question card')
        normalized = {'card_id': card_id}
        if (target.get('parameter_id') is None) == (
                target.get('field') is None):
            raise BIError('filter target maps to exactly one of '
                          'parameter_id or field')
        if target.get('parameter_id') is not None:
            normalized['parameter_id'] = _ident(target['parameter_id'],
                                                'target.parameter_id')
            identity = (card_id, 'p', normalized['parameter_id'])
        else:
            field = _map(target['field'], 'target.field')
            if 'column' in field:
                normalized['field'] = {'column': _text(
                    field['column'], 'target.field.column', 512)}
            else:
                normalized['field'] = {
                    'source_id': _ident(field.get('source_id'),
                                        'target.field.source_id'),
                    'field': _text(field.get('field'), 'target.field.field',
                                   512)}
            identity = (card_id, 'f', tuple(sorted(
                normalized['field'].items())))
        if identity in seen:
            raise BIError('a filter cannot target the same parameter or '
                          'field of a card twice')
        seen.add(identity)
        entry['targets'].append(normalized)
    return entry


def _check_value(filter_def, value):
    """Validate a filter value against its declared type and domain."""
    kind = filter_def['type']
    try:
        if filter_def['operator'] == 'between':
            if not isinstance(value, list) or len(value) != 2:
                raise BIError(f"filter {filter_def['id']!r} needs a "
                              'two-value range')
            members = value
        elif filter_def['multiple']:
            if not isinstance(value, list) or not value:
                raise BIError(f"filter {filter_def['id']!r} needs a "
                              'non-empty list')
            members = value
        else:
            members = [value]
        for member in members:
            _validate_parameter_value(member, kind)
            allowed = filter_def['allowed_values']
            if allowed and member not in allowed:
                raise BIError(f"filter {filter_def['id']!r} value is not "
                              'allowed')
    except SemanticModelError as exc:
        raise BIError(str(exc)) from exc


def _source(value, label):
    item = _map(value, label)
    given = [k for k in ('column', 'value', 'filter_id') if k in item]
    if len(given) != 1:
        raise BIError(f'{label} needs exactly one of column, value, '
                      'filter_id')
    key = given[0]
    return {key: (_text(item[key], label + '.' + key, 512)
                  if key != 'value' else item[key])}


def validate_dashboard(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize a dashboard document (structure only)."""
    item = _map(value, 'dashboard')
    tabs = []
    for raw in _list(item.get('tabs') or [{'id': 'main', 'name': 'Main'}],
                     'dashboard.tabs', MAX_TABS):
        tab = _map(raw, 'tab')
        tabs.append({'id': _ident(tab.get('id'), 'tab.id'),
                     'name': _text(tab.get('name'), 'tab.name', 256)})
    tab_ids = [t['id'] for t in tabs]
    if not tabs or len(set(tab_ids)) != len(tab_ids):
        raise BIError('dashboard tabs need unique identifiers')
    cards = {}
    for raw in _list(item.get('cards', []), 'dashboard.cards', MAX_CARDS):
        card = _card(raw, set(tab_ids))
        if card['id'] in cards:
            raise BIError('card identifiers must be unique')
        cards[card['id']] = card
    filters, seen = [], set()
    for raw in _list(item.get('filters', []), 'dashboard.filters',
                     MAX_FILTERS):
        entry = _filter(raw, cards)
        if entry['id'] in seen:
            raise BIError('filter identifiers must be unique')
        seen.add(entry['id'])
        filters.append(entry)
    by_filter = {f['id']: f for f in filters}
    cross, ids = [], set()
    for raw in _list(item.get('cross_filters', []),
                     'dashboard.cross_filters', MAX_LINKS):
        link = _map(raw, 'cross_filter')
        cid = _ident(link.get('id'), 'cross_filter.id')
        source = cards.get(link.get('source_card_id'))
        if cid in ids or source is None or source['type'] != 'question':
            raise BIError('cross_filter needs a unique id and a question '
                          'source card')
        if link.get('filter_id') not in by_filter:
            raise BIError('cross_filter targets an unknown filter')
        ids.add(cid)
        cross.append({
            'id': cid, 'source_card_id': source['id'],
            'source_column': _text(link.get('source_column'),
                                   'cross_filter.source_column', 512),
            'filter_id': link['filter_id'],
            'exclude_source': bool(link.get('exclude_source', True)),
        })
    drills, ids = [], set()
    for raw in _list(item.get('drill_throughs', []),
                     'dashboard.drill_throughs', MAX_LINKS):
        link = _map(raw, 'drill_through')
        did = _ident(link.get('id'), 'drill_through.id')
        source = cards.get(link.get('source_card_id'))
        if did in ids or source is None or source['type'] != 'question':
            raise BIError('drill_through needs a unique id and a question '
                          'source card')
        ids.add(did)
        trigger = _map(link.get('trigger', {}), 'drill_through.trigger')
        target = _map(link.get('target'), 'drill_through.target')
        drill = {'id': did, 'source_card_id': source['id'],
                 'label': str(link.get('label') or '')[:256],
                 'trigger': ({'column': _text(trigger['column'],
                                              'trigger.column', 512)}
                             if 'column' in trigger else {'row': True})}
        if target.get('kind') == 'question':
            drill['target'] = {
                'kind': 'question',
                'question_id': _text(target.get('question_id'),
                                     'drill target.question_id', 36),
                'revision': _int(target.get('revision'),
                                 'drill target.revision', 1, 10 ** 9),
                'parameter_mappings': [
                    {'parameter_id': _ident(m.get('parameter_id'),
                                            'mapping.parameter_id'),
                     'from': _source(m.get('from'), 'mapping.from')}
                    for m in (_map(r, 'mapping') for r in _list(
                        target.get('parameter_mappings', []),
                        'drill target.parameter_mappings', 64))],
            }
        elif target.get('kind') == 'dashboard':
            drill['target'] = {
                'kind': 'dashboard',
                'dashboard_id': _text(target.get('dashboard_id'),
                                      'drill target.dashboard_id', 36),
                'filter_mappings': [
                    {'filter_id': _ident(m.get('filter_id'),
                                         'mapping.filter_id'),
                     'from': _source(m.get('from'), 'mapping.from')}
                    for m in (_map(r, 'mapping') for r in _list(
                        target.get('filter_mappings', []),
                        'drill target.filter_mappings', 64))],
            }
        else:
            raise BIError('drill_through target.kind must be question or '
                          'dashboard')
        for mapping in drill['target'].get('filter_mappings', []) + (
                drill['target'].get('parameter_mappings', [])):
            ref = mapping['from'].get('filter_id')
            if ref is not None and ref not in by_filter:
                raise BIError('drill_through maps from an unknown filter')
        drills.append(drill)
    settings = _map(item.get('settings', {}), 'dashboard.settings')
    refresh = settings.get('auto_refresh_seconds', 0)
    normalized_settings = {
        'auto_refresh_seconds': _int(refresh, 'settings.auto_refresh_seconds',
                                     0, 86400)}
    if settings.get('monitoring') is not None:
        monitoring = _map(settings['monitoring'], 'settings.monitoring')
        normalized_settings['monitoring'] = {
            'module': _text(monitoring.get('module'), 'monitoring.module',
                            256),
            'channel': _text(monitoring.get('channel'), 'monitoring.channel',
                             256),
            'columns': _int(monitoring.get('columns', 2),
                            'monitoring.columns', 1, 4),
            'entry': _text(monitoring.get('entry', 'dashboard.ddn'),
                           'monitoring.entry', 256),
            'view': _text(monitoring.get('view', 'dashboard'),
                          'monitoring.view', 256),
        }
    collection_id = item.get('collection_id')
    if collection_id is not None and not isinstance(collection_id, str):
        raise BIError('dashboard.collection_id must be a string or null')
    return {
        'contract_version': DASHBOARD_CONTRACT_VERSION,
        'name': _text(item.get('name'), 'dashboard.name', 256),
        'description': str(item.get('description') or '')[:4096],
        'collection_id': collection_id,
        'tabs': tabs, 'cards': list(cards.values()), 'filters': filters,
        'cross_filters': cross, 'drill_throughs': drills,
        'settings': normalized_settings,
    }


def question_references(dashboard):
    """Return the ``(question_id, revision)`` pins a dashboard uses."""
    pins = {(c['question']['question_id'], c['question']['revision'])
            for c in dashboard['cards'] if c['type'] == 'question'}
    for drill in dashboard['drill_throughs']:
        target = drill['target']
        if target['kind'] == 'question':
            pins.add((target['question_id'], target['revision']))
    return sorted(pins)


def check_mappings(dashboard, definitions):
    """Check filter targets against the pinned question definitions.

    ``definitions`` maps ``(question_id, revision)`` to the stored question
    document.  Parameter targets must exist and agree with the filter type;
    field targets are refused for raw SQL questions and must use the shape of
    the question kind.
    """
    cards = {c['id']: c for c in dashboard['cards']}
    for flt in dashboard['filters']:
        for target in flt['targets']:
            card = cards[target['card_id']]
            pin = (card['question']['question_id'],
                   card['question']['revision'])
            question = definitions[pin]
            kind = question['query']['kind']
            if 'parameter_id' in target:
                parameters = {p['id']: p for p in question['parameters']}
                declared = parameters.get(target['parameter_id'])
                if declared is None:
                    raise BIError(
                        f"filter {flt['id']!r} targets unknown parameter "
                        f"{target['parameter_id']!r} of card {card['id']!r}")
                compatible = declared['type'] == flt['type'] or (
                    declared['type'] == 'array' and (
                        flt['multiple'] or flt['operator'] == 'between'))
                if not compatible:
                    raise BIError(
                        f"filter {flt['id']!r} type {flt['type']} does not "
                        f"match parameter {declared['id']!r} type "
                        f"{declared['type']}")
            elif kind == 'sql':
                raise BIError(
                    f"filter {flt['id']!r} cannot map to a field of raw SQL "
                    f"card {card['id']!r}; map it to a parameter")
            elif kind == 'builder' and 'column' not in target['field']:
                raise BIError(f"filter {flt['id']!r} needs a column field "
                              'for a builder question')
            elif kind == 'semantic' and 'source_id' not in target['field']:
                raise BIError(f"filter {flt['id']!r} needs a source_id and "
                              'field for a semantic question')


def resolve_filters(dashboard, values=None, skip=()):
    """Resolve dashboard filter values into per-card bindings.

    Returns ``{'filters': {id: value}, 'cards': {card_id: {'parameters',
    'extra_filters'}}, 'unapplied': [ids]}``.  A filter with no value (and no
    default) is skipped unless required.  Values are only checked and
    carried; they are bound by the executor, never put into SQL text.
    ``skip`` lists ``(card_id, filter_id)`` pairs whose targets are left out
    (a cross-filter does not filter the card that was clicked).
    """
    skip = {(item['card_id'], item['filter_id']) if isinstance(item, dict)
            else tuple(item) for item in skip or ()}
    values = dict(values or {})
    by_filter = {f['id']: f for f in dashboard['filters']}
    unknown = sorted(set(values) - set(by_filter))
    if unknown:
        raise BIError('unknown dashboard filter: ' + ', '.join(unknown))
    resolved, unapplied = {}, []
    for flt in dashboard['filters']:
        if flt['id'] in values and values[flt['id']] is not None:
            value = values[flt['id']]
        elif 'default' in flt:
            value = flt['default']
        elif flt['required']:
            raise BIError(f"filter {flt['id']!r} requires a value")
        else:
            unapplied.append(flt['id'])
            continue
        _check_value(flt, value)
        resolved[flt['id']] = value
    cards = {c['id']: {'parameters': {}, 'extra_filters': []}
             for c in dashboard['cards'] if c['type'] == 'question'}
    for flt in dashboard['filters']:
        if flt['id'] not in resolved:
            continue
        value = resolved[flt['id']]
        for target in flt['targets']:
            if (target['card_id'], flt['id']) in skip:
                continue
            card = cards[target['card_id']]
            if 'parameter_id' in target:
                card['parameters'][target['parameter_id']] = value
                continue
            entry = {'operator': flt['operator'], 'value': value}
            if 'column' in target['field']:
                entry['column'] = target['field']['column']
            else:
                entry['field'] = dict(target['field'])
            card['extra_filters'].append(entry)
    return {'filters': resolved, 'cards': cards, 'unapplied': unapplied}


def _row_value(row, column):
    if not isinstance(row, Mapping) or column not in row:
        raise BIError(f'clicked row has no column {column!r}')
    return row[column]


def resolve_cross_filter(dashboard, cross_filter_id, row, current=None):
    """Return the dashboard filter values after a click on a card."""
    link = next((c for c in dashboard['cross_filters']
                 if c['id'] == cross_filter_id), None)
    if link is None:
        raise BIError('cross-filter is unavailable')
    flt = next(f for f in dashboard['filters'] if f['id'] == link[
        'filter_id'])
    value = _row_value(row, link['source_column'])
    if flt['multiple'] and not isinstance(value, list):
        value = [value]
    _check_value(flt, value)
    return {'filters': {**(current or {}), flt['id']: value},
            'exclude': [{'card_id': link['source_card_id'],
                         'filter_id': flt['id']}]
            if link['exclude_source'] else []}


def resolve_drill(dashboard, drill_id, row, current=None):
    """Resolve a drill-through click into a target run request."""
    drill = next((d for d in dashboard['drill_throughs']
                  if d['id'] == drill_id), None)
    if drill is None:
        raise BIError('drill-through is unavailable')
    current = dict(current or {})
    if 'column' in drill['trigger']:
        _row_value(row, drill['trigger']['column'])

    def value_of(source):
        if 'column' in source:
            return _row_value(row, source['column'])
        if 'value' in source:
            return copy.deepcopy(source['value'])
        if source['filter_id'] not in current:
            raise BIError(f"filter {source['filter_id']!r} has no current "
                          'value')
        return copy.deepcopy(current[source['filter_id']])

    target = drill['target']
    if target['kind'] == 'question':
        return {'kind': 'question', 'question_id': target['question_id'],
                'revision': target['revision'],
                'parameters': {m['parameter_id']: value_of(m['from'])
                               for m in target['parameter_mappings']}}
    return {'kind': 'dashboard', 'dashboard_id': target['dashboard_id'],
            'filters': {m['filter_id']: value_of(m['from'])
                        for m in target['filter_mappings']}}
