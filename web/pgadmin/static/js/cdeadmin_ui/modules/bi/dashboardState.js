/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * The dashboard editor's state and pure reducer. The state keeps the
 * dashboard document exactly as the backend validates it
 * (web/pgadmin/cdeadmin/bi/dashboard_models.py: tabs, cards, filters,
 * cross_filters, drill_throughs, settings) next to the identity of the stored
 * dashboard, so `toDashboard(fromDashboard(record))` is the identity on a
 * backend-normalized document (see dashboardFixtures.js).
 *
 * Editing rules that keep the document valid:
 *   * removing a card removes the filter targets, cross-filters and
 *     drill-throughs that name it; removing a tab removes its cards;
 *   * removing a filter removes the cross-filters that set it and the
 *     drill-through mappings that read it;
 *   * every edit marks the draft dirty; load and saved clear it.
 */

import {
  DEFAULT_SIZE, TEXT_SIZE, compact, moveTo, nextPosition, nudge, place, resizeBy, resizeTo,
} from './dashboardLayout';

export const MAX_CARDS = 100;
export const MAX_TABS = 16;
export const MAX_FILTERS = 32;
export const MAX_LINKS = 64;
export const MAX_TEXT = 20000;
export const UNTITLED_DASHBOARD = 'Untitled dashboard';

export const FILTER_TYPES = Object.freeze(['string', 'integer', 'number', 'boolean', 'date', 'datetime']);
export const WIDGETS_BY_TYPE = Object.freeze({
  string: ['text', 'select', 'multi_select'],
  integer: ['number', 'select', 'multi_select'],
  number: ['number', 'select', 'multi_select'],
  boolean: ['toggle'],
  date: ['date', 'date_range'],
  datetime: ['date', 'date_range'],
});
export const SINGLE_OPERATORS = Object.freeze(['eq', 'ne', 'lt', 'lte', 'gt', 'gte']);
export const MULTIPLE_OPERATORS = Object.freeze(['in', 'not_in']);
export const AUTO_REFRESH_CHOICES = Object.freeze([0, 15, 30, 60, 300, 900, 3600]);

const ID_PATTERN = /^[A-Za-z][A-Za-z0-9_-]{0,127}$/;

export function emptyDashboard(overrides = {}) {
  return {
    dashboardId: null, revision: null, status: 'active',
    name: '', description: '', collectionId: null,
    tabs: [{id: 'main', name: 'Main'}],
    cards: [], filters: [], crossFilters: [], drillThroughs: [],
    settings: {auto_refresh_seconds: 0},
    dirty: false,
    ...overrides,
  };
}

const copy = (value) => value === undefined ? value : JSON.parse(JSON.stringify(value));

/** A stored dashboard (bi_dashboard_get / _create / _update / _revision) as editor state. */
export function fromDashboard(record) {
  const definition = record?.definition || {};
  return emptyDashboard({
    dashboardId: record?.dashboard_id ?? null,
    revision: record?.revision ?? null,
    status: record?.status || 'active',
    name: definition.name || '',
    description: definition.description || '',
    collectionId: definition.collection_id ?? null,
    tabs: copy(definition.tabs?.length ? definition.tabs : [{id: 'main', name: 'Main'}]),
    cards: copy(definition.cards || []),
    filters: copy(definition.filters || []),
    crossFilters: copy(definition.cross_filters || []),
    drillThroughs: copy(definition.drill_throughs || []),
    settings: copy({auto_refresh_seconds: 0, ...(definition.settings || {})}),
    access: record?.access || 'manage', isOwner: record?.is_owner !== false,
  });
}

/** The document the backend validates (contract_version is stamped there, never sent). */
export function toDashboard(state) {
  return {
    name: state.name.trim(),
    description: state.description,
    collection_id: state.collectionId,
    tabs: copy(state.tabs),
    cards: copy(state.cards),
    filters: copy(state.filters),
    cross_filters: copy(state.crossFilters),
    drill_throughs: copy(state.drillThroughs),
    settings: copy(state.settings),
  };
}

// ---------------------------------------------------------------------------
// Identifiers
// ---------------------------------------------------------------------------

/** An identifier of the form prefix_N not in `taken`. */
export function nextId(prefix, taken) {
  const used = new Set(taken);
  for(let index = 1; ; index += 1) {
    const id = `${prefix}_${index}`;
    if(!used.has(id)) return id;
  }
}

/** A portable identifier derived from a display name, unique among `taken`. */
export function slugId(name, taken, fallback = 'item') {
  const base = String(name || '').trim().replace(/[^A-Za-z0-9_-]+/g, '_').replace(/^_+|_+$/g, '');
  const start = /^[A-Za-z]/.test(base) ? base.slice(0, 100) : `${fallback}${base ? `_${base}` : ''}`.slice(0, 100);
  const used = new Set(taken);
  if(!used.has(start)) return start;
  for(let index = 2; ; index += 1) {
    const id = `${start}_${index}`;
    if(!used.has(id)) return id;
  }
}

export const isPortableId = (value) => ID_PATTERN.test(String(value));

// ---------------------------------------------------------------------------
// Filters
// ---------------------------------------------------------------------------

export function defaultOperator(widget, multiple = false) {
  if(widget === 'date_range') return 'between';
  return widget === 'multi_select' || multiple ? 'in' : 'eq';
}

/** Make widget, operator and multiple agree (the backend requires it). */
export function normalizeFilter(filter) {
  const widgets = WIDGETS_BY_TYPE[filter.type] || [];
  const widget = widgets.includes(filter.widget) || !widgets.length ? filter.widget : widgets[0];
  let operator = filter.operator;
  let multiple = Boolean(filter.multiple);
  if(widget === 'date_range') {
    operator = 'between';
    multiple = false;
  } else if(widget === 'multi_select') {
    multiple = true;
    if(!MULTIPLE_OPERATORS.includes(operator)) operator = 'in';
  } else {
    multiple = false;
    if(!SINGLE_OPERATORS.includes(operator)) operator = 'eq';
  }
  return {...filter, widget, operator, multiple};
}

export function newFilter({name, type = 'string', widget, taken = []}) {
  const chosen = widget || WIDGETS_BY_TYPE[type][0];
  return normalizeFilter({
    id: slugId(name, taken, 'filter'), name: name.trim(), type, widget: chosen,
    operator: defaultOperator(chosen), multiple: false, required: false,
    allowed_values: [], targets: [],
  });
}

/** Parse the text of one filter value for the filter's type; `undefined` when it does not parse. */
export function parseFilterValue(type, text) {
  const raw = String(text ?? '').trim();
  if(raw === '') return undefined;
  switch(type) {
  case 'integer': return /^-?\d+$/.test(raw) ? Number(raw) : undefined;
  case 'number': return Number.isFinite(Number(raw)) ? Number(raw) : undefined;
  case 'boolean': return raw === 'true' ? true : raw === 'false' ? false : undefined;
  default: return raw;
  }
}

export function formatFilterValue(value) {
  return value === null || value === undefined ? '' : String(value);
}

// ---------------------------------------------------------------------------
// Targets and links
// ---------------------------------------------------------------------------

export function targetIdentity(target) {
  if(target.parameter_id !== undefined) return `p:${target.card_id}:${target.parameter_id}`;
  const field = target.field || {};
  return `f:${target.card_id}:${field.source_id ?? ''}:${field.column ?? field.field ?? ''}`;
}

/** Targets of one card inside a filter, with their index in the filter's list. */
export function cardTargets(filter, cardId) {
  return filter.targets.map((target, index) => ({target, index})).filter((item) => item.target.card_id === cardId);
}

export const DRILL_KINDS = Object.freeze(['question', 'dashboard']);

export const mappingKey = (target) => target.kind === 'dashboard' ? 'filter_mappings' : 'parameter_mappings';
export const mappingTargetKey = (target) => target.kind === 'dashboard' ? 'filter_id' : 'parameter_id';
export const drillMappings = (target) => target[mappingKey(target)] || [];
export const withDrillMappings = (target, list) => ({...target, [mappingKey(target)]: list});

export function sourceKind(from) {
  if('filter_id' in from) return 'filter_id';
  if('value' in from) return 'value';
  return 'column';
}

export function makeSource(kind, content) {
  if(kind === 'value') return {value: content};
  return {[kind]: content};
}

export function newDrill({id, sourceCardId, kind = 'question', target = {}}) {
  const base = kind === 'dashboard' ?
    {kind: 'dashboard', dashboard_id: target.dashboard_id || '', filter_mappings: []} :
    {kind: 'question', question_id: target.question_id || '', revision: target.revision || 1, parameter_mappings: []};
  return {id, source_card_id: sourceCardId, label: '', trigger: {row: true}, target: base};
}

export function newCrossFilter({id, sourceCardId, filterId}) {
  return {id, source_card_id: sourceCardId, source_column: '', filter_id: filterId, exclude_source: true};
}

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

const touch = (state, patch) => ({...state, ...patch, dirty: true});

function dropCards(state, ids) {
  const gone = new Set(ids);
  if(!gone.size) return state;
  return touch(state, {
    cards: state.cards.filter((card) => !gone.has(card.id)),
    filters: state.filters.map((filter) => ({
      ...filter, targets: filter.targets.filter((target) => !gone.has(target.card_id))})),
    crossFilters: state.crossFilters.filter((link) => !gone.has(link.source_card_id)),
    drillThroughs: state.drillThroughs.filter((link) => !gone.has(link.source_card_id)),
  });
}

function dropFilter(state, id) {
  return touch(state, {
    filters: state.filters.filter((filter) => filter.id !== id),
    crossFilters: state.crossFilters.filter((link) => link.filter_id !== id),
    drillThroughs: state.drillThroughs.map((drill) => {
      const mappings = drillMappings(drill.target);
      const kept = mappings.filter((mapping) => mapping.from.filter_id !== id);
      return kept.length === mappings.length ? drill :
        {...drill, target: withDrillMappings(drill.target, kept)};
    }),
  });
}

function mapCards(state, id, change) {
  return touch(state, {cards: state.cards.map((card) => card.id === id ? change(card) : card)});
}

function mapFilters(state, id, change) {
  return touch(state, {filters: state.filters.map((filter) => filter.id === id ? change(filter) : filter)});
}

function updateFilter(state, id, patch) {
  return mapFilters(state, id, (filter) => {
    const next = {...filter, ...patch};
    for(const key of Object.keys(next)) if(next[key] === undefined) delete next[key];
    const retyped = patch.type !== undefined && patch.type !== filter.type;
    const rewidgeted = patch.widget !== undefined && patch.widget !== filter.widget;
    if(retyped || rewidgeted) {
      delete next.default;
      next.allowed_values = retyped ? [] : next.allowed_values;
      if(patch.operator === undefined) next.operator = defaultOperator(next.widget);
    }
    return normalizeFilter(next);
  });
}

export function reduce(state, action) {
  switch(action.type) {
  case 'load':
    return fromDashboard(action.record);
  case 'saved': {
    // `sent` is the document the save request carried. If the draft moved on while the
    // request was in flight, only the stored identity is adopted and the edits stay dirty.
    const loaded = fromDashboard(action.record);
    if(action.sent && JSON.stringify(toDashboard(state)) !== JSON.stringify(action.sent)) {
      return {...state, dashboardId: loaded.dashboardId, revision: loaded.revision,
        status: loaded.status, dirty: true};
    }
    return {...loaded, dirty: false};
  }
  case 'restore': {
    // A past revision becomes an unsaved draft of the stored dashboard.
    const loaded = fromDashboard({definition: action.definition});
    return {...loaded, dashboardId: state.dashboardId, revision: state.revision, status: state.status,
      access: state.access, isOwner: state.isOwner, dirty: true};
  }
  case 'rename':
    return touch(state, {name: action.name});
  case 'describe':
    return touch(state, {description: action.description});
  case 'setCollection':
    return touch(state, {collectionId: action.collectionId});
  case 'setAutoRefresh': {
    const seconds = Math.max(0, Math.min(86400, Math.round(Number(action.seconds) || 0)));
    return touch(state, {settings: {...state.settings, auto_refresh_seconds: seconds}});
  }

  case 'addTab': {
    if(state.tabs.length >= MAX_TABS) return state;
    const id = slugId(action.name, state.tabs.map((tab) => tab.id), 'tab');
    return touch(state, {tabs: [...state.tabs, {id, name: action.name.trim() || id}]});
  }
  case 'renameTab':
    return touch(state, {tabs: state.tabs.map((tab) => tab.id === action.id ?
      {...tab, name: action.name.trim() || tab.name} : tab)});
  case 'removeTab': {
    if(state.tabs.length <= 1 || !state.tabs.some((tab) => tab.id === action.id)) return state;
    const gone = state.cards.filter((card) => card.tab_id === action.id).map((card) => card.id);
    const without = dropCards(state, gone);
    return touch(without, {tabs: state.tabs.filter((tab) => tab.id !== action.id)});
  }

  case 'addQuestionCard': {
    if(state.cards.length >= MAX_CARDS) return state;
    const id = nextId('card', state.cards.map((card) => card.id));
    const card = {
      id, tab_id: action.tabId, type: 'question', title: action.title || '',
      layout: nextPosition(state.cards, action.tabId, DEFAULT_SIZE),
      question: {question_id: action.question.question_id, revision: action.question.revision},
    };
    if(action.visualization) card.visualization = copy(action.visualization);
    return touch(state, {cards: [...state.cards, card]});
  }
  case 'addTextCard': {
    if(state.cards.length >= MAX_CARDS) return state;
    const id = nextId('card', state.cards.map((card) => card.id));
    return touch(state, {cards: [...state.cards, {
      id, tab_id: action.tabId, type: 'text', title: action.title || '',
      layout: nextPosition(state.cards, action.tabId, TEXT_SIZE),
      text: {markdown: String(action.markdown ?? '').slice(0, MAX_TEXT)},
    }]});
  }
  case 'setCardTitle':
    return mapCards(state, action.id, (card) => ({...card, title: action.title.slice(0, 256)}));
  case 'setCardText':
    return mapCards(state, action.id, (card) => card.type === 'text' ?
      {...card, text: {markdown: action.markdown.slice(0, MAX_TEXT)}} : card);
  case 'setCardVisualization':
    // `null` removes the override: the card then shows the question's own visualization.
    return mapCards(state, action.id, (card) => {
      if(card.type !== 'question') return card;
      const {visualization: _removed, ...rest} = card;
      return action.visualization ? {...rest, visualization: copy(action.visualization)} : rest;
    });
  case 'repinCard':
    return mapCards(state, action.id, (card) => card.type === 'question' ?
      {...card, question: {...card.question, revision: action.revision}} : card);
  case 'moveCard':
    return touch(state, {cards: moveTo(state.cards, action.id, action.x, action.y)});
  case 'resizeCard':
    return touch(state, {cards: resizeTo(state.cards, action.id, action.w, action.h)});
  case 'placeCard':
    return touch(state, {cards: place(state.cards, action.id, action.layout)});
  case 'nudgeCard':
    return touch(state, {cards: nudge(state.cards, action.id, action.dx, action.dy)});
  case 'resizeCardBy':
    return touch(state, {cards: resizeBy(state.cards, action.id, action.dw, action.dh)});
  case 'compactTab':
    return touch(state, {cards: compact(state.cards, action.tabId)});
  case 'moveCardToTab': {
    const card = state.cards.find((item) => item.id === action.id);
    if(!card || card.tab_id === action.tabId) return state;
    const moved = state.cards.map((item) => item.id === action.id ?
      {...item, tab_id: action.tabId, layout: nextPosition(state.cards, action.tabId, item.layout)} : item);
    return touch(state, {cards: moved});
  }
  case 'removeCard':
    return dropCards(state, [action.id]);

  case 'addFilter': {
    if(state.filters.length >= MAX_FILTERS) return state;
    const filter = newFilter({...action.filter, taken: state.filters.map((item) => item.id)});
    return touch(state, {filters: [...state.filters, filter]});
  }
  case 'updateFilter':
    return updateFilter(state, action.id, action.patch);
  case 'removeFilter':
    return dropFilter(state, action.id);
  case 'addTarget':
    return mapFilters(state, action.filterId, (filter) => {
      const identity = targetIdentity(action.target);
      return filter.targets.some((target) => targetIdentity(target) === identity) ? filter :
        {...filter, targets: [...filter.targets, copy(action.target)]};
    });
  case 'updateTarget':
    return mapFilters(state, action.filterId, (filter) => {
      const position = cardTargets(filter, action.target.card_id)[action.index];
      if(!position) return filter;
      const identity = targetIdentity(action.target);
      const clash = filter.targets.some((target, index) => index !== position.index &&
        targetIdentity(target) === identity);
      if(clash) return filter;
      return {...filter, targets: filter.targets.map((target, index) =>
        index === position.index ? copy(action.target) : target)};
    });
  case 'removeTarget':
    return mapFilters(state, action.filterId, (filter) => {
      const position = cardTargets(filter, action.cardId)[action.index];
      return position ? {...filter, targets: filter.targets.filter((_target, index) => index !== position.index)} : filter;
    });

  case 'addCrossFilter': {
    if(state.crossFilters.length >= MAX_LINKS) return state;
    const id = nextId('cross', state.crossFilters.map((link) => link.id));
    return touch(state, {crossFilters: [...state.crossFilters, {...copy(action.link), id}]});
  }
  case 'updateCrossFilter':
    return touch(state, {crossFilters: state.crossFilters.map((link) =>
      link.id === action.id ? {...link, ...copy(action.patch)} : link)});
  case 'removeCrossFilter':
    return touch(state, {crossFilters: state.crossFilters.filter((link) => link.id !== action.id)});
  case 'addDrill': {
    if(state.drillThroughs.length >= MAX_LINKS) return state;
    const id = nextId('drill', state.drillThroughs.map((link) => link.id));
    return touch(state, {drillThroughs: [...state.drillThroughs, {...copy(action.drill), id}]});
  }
  case 'updateDrill':
    return touch(state, {drillThroughs: state.drillThroughs.map((link) =>
      link.id === action.id ? {...link, ...copy(action.patch)} : link)});
  case 'removeDrill':
    return touch(state, {drillThroughs: state.drillThroughs.filter((link) => link.id !== action.id)});
  default:
    return state;
  }
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export const questionCards = (state) => state.cards.filter((card) => card.type === 'question');
export const cardsOfTab = (state, tabId) => state.cards.filter((card) => card.tab_id === tabId);

export function cardLabel(card) {
  if(card.title) return card.title;
  if(card.type === 'text') return `Text ${card.id}`;
  if(card.type === 'metric_panel') return card.metric_panel?.panel_id || card.id;
  return card.id;
}
