/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Pure pieces of the dashboard viewer: filter values, per-card run state, the
 * cross-filter bookkeeping, bounded concurrency and the lookup from a click
 * to the cross-filters and drill-throughs it triggers. The server is
 * authoritative for resolving a click (bi_dashboard_cross_filter and
 * bi_dashboard_drill); this module only keeps the answers.
 *
 * Card state: idle -> loading -> ready | error. A card that already has a
 * result keeps showing it, marked stale, while a newer run is under way or
 * after filters changed or a refresh failed.
 */

import gettext from 'sources/gettext';
import {parseFilterValue} from './dashboardState';

export const RUN_CONCURRENCY = 4;

export const isBlank = (value) => value === null || value === undefined || value === '' ||
  (Array.isArray(value) && value.length === 0);

const same = (left, right) => JSON.stringify(left) === JSON.stringify(right);

/** Question cards, optionally only those of one tab. */
export function runnableCards(dashboard, tabId) {
  return dashboard.cards.filter((card) => card.type === 'question' && (!tabId || card.tab_id === tabId));
}

/** The filter values a dashboard starts with: each filter's default. */
export function initialValues(dashboard) {
  const values = {};
  for(const filter of dashboard.filters) if('default' in filter && !isBlank(filter.default)) values[filter.id] = filter.default;
  return values;
}

/** Values to send: only filters that have one. */
export function filterPayload(values) {
  return Object.fromEntries(Object.entries(values).filter(([, value]) => !isBlank(value)));
}

/** Required filters that have neither a value nor a default. */
export function missingRequired(dashboard, values) {
  return dashboard.filters.filter((filter) => filter.required && isBlank(values[filter.id]) &&
    !('default' in filter && !isBlank(filter.default)));
}

export function initialViewer(dashboard, {values, tabId} = {}) {
  return {
    values: values ?? initialValues(dashboard),
    exclusions: [],
    tabId: tabId && dashboard.tabs.some((tab) => tab.id === tabId) ? tabId : dashboard.tabs[0]?.id || '',
    cards: {},
    fullscreen: null,
  };
}

// Every card that was ever asked to run is out of date; a card that still has a
// result keeps showing it, flagged, until the new run replaces it.
const markStale = (cards) => Object.fromEntries(Object.entries(cards).map(([id, card]) =>
  [id, {...card, stale: true}]));

/** What a run depends on: the filter values and the cards a cross-filter click spares. */
export const viewerKey = (state) => JSON.stringify([state.values, state.exclusions]);

/** Cards of a tab that were never run, or last ran (or are running) for other filters. */
export function cardsToRun(dashboard, state, tabId) {
  const key = viewerKey(state);
  return runnableCards(dashboard, tabId).filter((card) => state.cards[card.id]?.key !== key);
}

function cleanValues(values) {
  return Object.fromEntries(Object.entries(values).filter(([, value]) => !isBlank(value)));
}

/** Exclusions only hold while the value that caused them is unchanged. */
function keepExclusions(exclusions, before, after) {
  return exclusions.filter((item) => same(before[item.filter_id], after[item.filter_id]));
}

export function viewerReducer(state, action) {
  switch(action.type) {
  case 'init':
    return initialViewer(action.dashboard, action);
  case 'setValues': {
    const values = cleanValues(action.values);
    return {...state, values, exclusions: keepExclusions(state.exclusions, state.values, values),
      cards: markStale(state.cards)};
  }
  case 'crossFilter': {
    // The server returns the complete value set and the cards the click must not filter.
    const values = cleanValues(action.filters);
    const kept = state.exclusions.filter((item) => item.filter_id !== action.filterId);
    return {...state, values, exclusions: [...kept, ...(action.exclude || [])], cards: markStale(state.cards)};
  }
  case 'selectTab':
    return state.tabId === action.tabId ? state : {...state, tabId: action.tabId};
  case 'cardStart': {
    const card = state.cards[action.id] || {};
    return {...state, cards: {...state.cards, [action.id]: {
      ...card, status: 'loading', token: action.token, key: action.key, error: ''}}};
  }
  case 'cardDone': {
    const card = state.cards[action.id];
    if(!card || card.token !== action.token) return state;
    const cache = action.execution.cache;
    return {...state, cards: {...state.cards, [action.id]: {
      status: 'ready', token: action.token, key: card.key, execution: action.execution, error: '', stale: false,
      receivedAt: action.receivedAt,
      cacheHit: Boolean(cache?.hit),
      // The age of a cache hit is how long ago the result was produced.
      producedAt: action.receivedAt - (cache?.hit ? Math.round((cache.age_seconds || 0) * 1000) : 0),
    }}};
  }
  case 'cardDenied': {
    // The runner has no access to the question behind the card: nothing is known about it.
    const card = state.cards[action.id];
    if(!card || card.token !== action.token) return state;
    return {...state, cards: {...state.cards, [action.id]: {
      status: 'denied', token: action.token, key: card.key, error: '', stale: false}}};
  }
  case 'cardFail': {
    const card = state.cards[action.id];
    if(!card || card.token !== action.token) return state;
    return {...state, cards: {...state.cards, [action.id]: {
      ...card, status: 'error', error: action.error, stale: Boolean(card.execution)}}};
  }
  case 'fullscreen':
    return {...state, fullscreen: action.id};
  default:
    return state;
  }
}

/**
 * Run `worker` over `items` with at most `limit` in flight. `cancelled` is
 * polled before each item is taken, so a superseded run stops starting work.
 */
export async function runBounded(items, limit, worker, cancelled = () => false) {
  let next = 0;
  const lane = async () => {
    while(next < items.length && !cancelled()) {
      const item = items[next];
      next += 1;
      try { await worker(item); } catch { /* the worker reports its own failures */ }
    }
  };
  await Promise.all(Array.from({length: Math.min(Math.max(1, limit), items.length)}, lane));
}

/**
 * What a click on card `cardId` can do. Every cross-filter of the card applies
 * to any click; a drill-through applies when it triggers on the whole row or
 * on the clicked column.
 */
export function cardLinks(dashboard, cardId, column) {
  return {
    cross: dashboard.cross_filters.filter((link) => link.source_card_id === cardId),
    drills: dashboard.drill_throughs.filter((drill) => drill.source_card_id === cardId &&
      (drill.trigger.row || (column !== undefined && drill.trigger.column === column))),
  };
}

/** Choices shown when one click could do several things. */
export function linkChoices(dashboard, links, row) {
  const filterName = (id) => dashboard.filters.find((filter) => filter.id === id)?.name || id;
  return [
    ...links.cross.map((link) => ({
      kind: 'cross', id: link.id,
      label: gettext('Filter %s to %s', filterName(link.filter_id), String(row?.[link.source_column] ?? '')),
    })),
    ...links.drills.map((drill) => ({
      kind: 'drill', id: drill.id,
      label: drill.label || (drill.target.kind === 'dashboard' ?
        gettext('Open another dashboard') : gettext('Open a question')),
    })),
  ];
}

/** The column key a chart mark stands for (series y of the dataset, else x). */
export function markColumn(settings, datasetIndex) {
  const y = settings?.y;
  if(Number.isInteger(datasetIndex) && Array.isArray(y) && y[datasetIndex] !== undefined) return y[datasetIndex];
  return settings?.x;
}

export function refreshLabel(seconds) {
  if(!seconds) return gettext('Off');
  if(seconds < 60) return gettext('Every %s seconds', seconds);
  if(seconds < 3600) return gettext('Every %s minutes', Math.round(seconds / 60));
  return gettext('Every %s hours', Math.round(seconds / 3600));
}

export function formatClock(milliseconds) {
  const date = new Date(milliseconds);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString();
}

// ---------------------------------------------------------------------------
// Filter bar drafts: what each widget holds while being edited
// ---------------------------------------------------------------------------

export function draftFromValue(filter, value) {
  switch(filter.widget) {
  case 'date_range':
    return Array.isArray(value) ? [String(value[0] ?? ''), String(value[1] ?? '')] : ['', ''];
  case 'multi_select':
    return Array.isArray(value) ? value.map(String) : [];
  case 'toggle':
    return value === true ? 'true' : value === false ? 'false' : 'any';
  default:
    return isBlank(value) ? '' : String(value);
  }
}

const typed = (filter, text) => {
  const known = filter.allowed_values.find((item) => String(item) === text);
  return known !== undefined ? known : parseFilterValue(filter.type, text);
};

/** The value a draft stands for: {value} (undefined when empty) or {error}. */
export function valueFromDraft(filter, draft) {
  switch(filter.widget) {
  case 'date_range': {
    const [from, to] = draft;
    if(!from && !to) return {value: undefined};
    return from && to ? {value: [from, to]} : {error: gettext('Choose both dates.')};
  }
  case 'multi_select': {
    if(!draft.length) return {value: undefined};
    const values = draft.map((item) => typed(filter, item));
    return values.every((item) => item !== undefined) ? {value: values} : {error: gettext('A chosen value is not valid.')};
  }
  case 'toggle':
    return {value: draft === 'true' ? true : draft === 'false' ? false : undefined};
  case 'select':
    return draft === '' ? {value: undefined} : {value: typed(filter, draft)};
  default: {
    if(!String(draft).trim()) return {value: undefined};
    const value = parseFilterValue(filter.type, draft);
    return value === undefined ? {error: gettext('Enter a valid %s.', filter.type)} : {value};
  }
  }
}

export function draftsFromValues(dashboard, values) {
  return Object.fromEntries(dashboard.filters.map((filter) => [filter.id, draftFromValue(filter, values[filter.id])]));
}

/** Values and per-filter errors for a set of drafts. */
export function valuesFromDrafts(dashboard, drafts) {
  const values = {};
  const errors = {};
  for(const filter of dashboard.filters) {
    const result = valueFromDraft(filter, drafts[filter.id]);
    if(result.error) errors[filter.id] = result.error;
    else if(!isBlank(result.value)) values[filter.id] = result.value;
  }
  return {values, errors};
}
