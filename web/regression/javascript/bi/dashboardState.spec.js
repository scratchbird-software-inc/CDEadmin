/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  emptyDashboard, fromDashboard, newCrossFilter, newDrill, nextId, normalizeFilter, parseFilterValue,
  reduce, slugId, toDashboard,
} from 'sources/cdeadmin_ui/modules/bi/dashboardState';
import {
  dashboardIssues, hasErrors, infoKey, mappingRows, questionInfo, targetIssue,
} from 'sources/cdeadmin_ui/modules/bi/dashboardMapping';
import {collisions} from 'sources/cdeadmin_ui/modules/bi/dashboardLayout';
import {dashboardFixtures as fixtures} from './dashboardFixtures';

const record = (definition = fixtures.board, extra = {}) => ({
  dashboard_id: 'd1', revision: 3, status: 'active', definition, ...extra});
const loaded = () => fromDashboard(record());
const apply = (state, ...actions) => actions.reduce(reduce, state);
const filterOf = (state, id) => state.filters.find((filter) => filter.id === id);

describe('document round trip', () => {
  it('toDashboard(fromDashboard(x)) is the backend document, without contract_version', () => {
    const {contract_version: _version, ...document} = fixtures.board;
    expect(toDashboard(loaded())).toEqual(document);
  });

  it('round-trips the converted monitoring dashboards (metric panels, settings.monitoring, several tabs)', () => {
    for(const converted of [fixtures.monitoring, fixtures.fleet]) {
      const {contract_version: _version, ...document} = converted.dashboard;
      const state = fromDashboard(record(converted.dashboard));
      expect(toDashboard(state)).toEqual(document);
      expect(state.settings.monitoring.channel).toMatch(/observations$/);
    }
  });

  it('a loaded dashboard is clean and does not share objects with the record', () => {
    const state = loaded();
    expect(state).toMatchObject({dashboardId: 'd1', revision: 3, dirty: false, name: 'Sales board'});
    const changed = reduce(state, {type: 'moveCard', id: 'detail', x: 0, y: 20});
    expect(fixtures.board.cards[1].layout.x).toBe(12);
    expect(changed.dirty).toBe(true);
  });

  it('trims the name and keeps the collection', () => {
    const state = apply(emptyDashboard({collectionId: 'c1'}), {type: 'rename', name: '  Board  '});
    expect(toDashboard(state)).toMatchObject({name: 'Board', collection_id: 'c1', tabs: [{id: 'main', name: 'Main'}]});
  });
});

describe('cards and tabs', () => {
  it('adds a question card pinned to a revision below the others, and a text card', () => {
    const state = apply(loaded(),
      {type: 'addQuestionCard', tabId: 'main', question: {question_id: 'q9', revision: 4}, title: 'New'},
      {type: 'addTextCard', tabId: 'main', markdown: 'Hello'});
    const [question, text] = state.cards.slice(-2);
    expect(question).toMatchObject({id: 'card_1', type: 'question', title: 'New', question: {question_id: 'q9', revision: 4}});
    expect(question.layout).toEqual({x: 0, y: 12, w: 12, h: 6});
    expect(text).toMatchObject({id: 'card_2', type: 'text', text: {markdown: 'Hello'}});
    expect(text.layout.y).toBe(18);
    expect(collisions(state.cards)).toEqual([]);
  });

  it('keeps the title, text and visualization override on the right card only', () => {
    const state = apply(loaded(),
      {type: 'setCardTitle', id: 'detail', title: 'Detail rows'},
      {type: 'setCardVisualization', id: 'detail', visualization: {type: 'bar', settings: {x: 'region', y: ['amount']}}},
      {type: 'setCardText', id: 'note', markdown: '# Changed'},
      {type: 'setCardText', id: 'detail', markdown: 'ignored'});
    expect(state.cards.find((card) => card.id === 'detail')).toMatchObject({
      title: 'Detail rows', visualization: {type: 'bar', settings: {x: 'region', y: ['amount']}}});
    expect(state.cards.find((card) => card.id === 'detail').text).toBeUndefined();
    expect(state.cards.find((card) => card.id === 'note').text.markdown).toBe('# Changed');
    const cleared = reduce(state, {type: 'setCardVisualization', id: 'detail', visualization: null});
    expect('visualization' in cleared.cards.find((card) => card.id === 'detail')).toBe(false);
  });

  it('re-pins a question card to another revision', () => {
    const state = reduce(loaded(), {type: 'repinCard', id: 'detail', revision: 5});
    expect(state.cards.find((card) => card.id === 'detail').question).toEqual({question_id: 'q-detail', revision: 5});
  });

  it('removing a card removes every filter target, cross-filter and drill-through that names it', () => {
    const state = reduce(loaded(), {type: 'removeCard', id: 'detail'});
    expect(state.cards.map((card) => card.id)).toEqual(['by_region', 'floor', 'note']);
    expect(filterOf(state, 'region').targets).toEqual([{card_id: 'by_region', parameter_id: 'region'}]);
    expect(filterOf(state, 'products').targets).toEqual([]);
    expect(state.crossFilters).toEqual([]);
    expect(state.drillThroughs.map((drill) => drill.id)).toEqual(['to_board']);
  });

  it('tabs: add, rename, remove with their cards, and never the last tab', () => {
    let state = apply(loaded(), {type: 'addTab', name: 'Second page'}, {type: 'addTab', name: 'Second page'});
    expect(state.tabs.map((tab) => tab.id)).toEqual(['main', 'Second_page', 'Second_page_2']);
    state = apply(state, {type: 'renameTab', id: 'Second_page', name: 'Detail'},
      {type: 'moveCardToTab', id: 'detail', tabId: 'Second_page'});
    expect(state.tabs[1].name).toBe('Detail');
    expect(state.cards.find((card) => card.id === 'detail')).toMatchObject({tab_id: 'Second_page', layout: {x: 12, y: 0}});
    state = reduce(state, {type: 'removeTab', id: 'Second_page'});
    expect(state.cards.some((card) => card.id === 'detail')).toBe(false);
    expect(state.crossFilters).toEqual([]);
    const single = reduce(emptyDashboard(), {type: 'removeTab', id: 'main'});
    expect(single.tabs).toHaveLength(1);
  });

  it('moving, resizing and keyboard steps go through the layout and mark the draft dirty', () => {
    const state = apply(loaded(),
      {type: 'nudgeCard', id: 'floor', dx: 1, dy: 0},
      {type: 'resizeCardBy', id: 'floor', dw: 2, dh: 1});
    expect(state.cards.find((card) => card.id === 'floor').layout).toEqual({x: 1, y: 6, w: 14, h: 7});
    expect(state.dirty).toBe(true);
    expect(collisions(state.cards)).toEqual([]);
  });

  it('auto-refresh is bounded by the format', () => {
    expect(reduce(loaded(), {type: 'setAutoRefresh', seconds: 999999}).settings.auto_refresh_seconds).toBe(86400);
    expect(reduce(loaded(), {type: 'setAutoRefresh', seconds: -4}).settings.auto_refresh_seconds).toBe(0);
  });
});

describe('filters and mapping', () => {
  it('adds a filter whose widget, operator and flags are consistent', () => {
    const state = reduce(loaded(), {type: 'addFilter', filter: {name: 'Order date', type: 'date'}});
    expect(filterOf(state, 'Order_date')).toEqual({
      id: 'Order_date', name: 'Order date', type: 'date', widget: 'date', operator: 'eq', multiple: false,
      required: false, allowed_values: [], targets: []});
  });

  it('changing the widget keeps widget, operator and multiple in agreement and drops the default', () => {
    const state = apply(loaded(),
      {type: 'updateFilter', id: 'window', patch: {widget: 'date'}},
      {type: 'updateFilter', id: 'products', patch: {widget: 'select'}});
    expect(filterOf(state, 'window')).toMatchObject({widget: 'date', operator: 'eq', multiple: false});
    expect(filterOf(state, 'products')).toMatchObject({widget: 'select', operator: 'eq', multiple: false});
    const range = reduce(state, {type: 'updateFilter', id: 'window', patch: {widget: 'date_range'}});
    expect(filterOf(range, 'window')).toMatchObject({operator: 'between', multiple: false});
    expect(normalizeFilter({type: 'string', widget: 'multi_select', operator: 'eq'})).toMatchObject({
      operator: 'in', multiple: true});
    const retyped = reduce(loaded(), {type: 'updateFilter', id: 'floor', patch: {type: 'string'}});
    expect('default' in filterOf(retyped, 'floor')).toBe(false);
    expect(filterOf(retyped, 'floor').widget).toBe('text');
  });

  it('sets and clears the default, and the required flag', () => {
    const set = reduce(loaded(), {type: 'updateFilter', id: 'region', patch: {default: 'east', required: true}});
    expect(filterOf(set, 'region')).toMatchObject({default: 'east', required: true});
    const cleared = reduce(set, {type: 'updateFilter', id: 'region', patch: {default: undefined}});
    expect('default' in filterOf(cleared, 'region')).toBe(false);
  });

  it('maps a filter to a parameter or a field of each card, once per target', () => {
    let state = apply(loaded(),
      {type: 'addTarget', filterId: 'window', target: {card_id: 'detail', field: {column: 'sold_on'}}},
      {type: 'addTarget', filterId: 'window', target: {card_id: 'detail', field: {column: 'sold_on'}}},
      {type: 'addTarget', filterId: 'window', target: {card_id: 'floor', parameter_id: 'floor'}});
    expect(filterOf(state, 'window').targets).toEqual([
      {card_id: 'detail', field: {column: 'sold_on'}}, {card_id: 'floor', parameter_id: 'floor'}]);
    state = apply(state,
      {type: 'updateTarget', filterId: 'window', index: 0, target: {card_id: 'detail', field: {column: 'shipped_on'}}},
      {type: 'removeTarget', filterId: 'window', cardId: 'floor', index: 0});
    expect(filterOf(state, 'window').targets).toEqual([{card_id: 'detail', field: {column: 'shipped_on'}}]);
    // A second mapping of the same card is addressed by its position among that card's mappings.
    const two = apply(state, {type: 'addTarget', filterId: 'window', target: {card_id: 'detail', field: {column: 'billed_on'}}},
      {type: 'removeTarget', filterId: 'window', cardId: 'detail', index: 1});
    expect(filterOf(two, 'window').targets).toEqual([{card_id: 'detail', field: {column: 'shipped_on'}}]);
  });

  it('refuses an update that would duplicate another mapping', () => {
    const state = apply(loaded(),
      {type: 'addTarget', filterId: 'region', target: {card_id: 'detail', field: {column: 'product'}}},
      {type: 'updateTarget', filterId: 'region', index: 1, target: {card_id: 'detail', field: {column: 'region'}}});
    expect(filterOf(state, 'region').targets[2]).toEqual({card_id: 'detail', field: {column: 'product'}});
  });

  it('removing a filter removes the cross-filters that set it and the drill mappings that read it', () => {
    const state = reduce(loaded(), {type: 'removeFilter', id: 'region'});
    expect(state.crossFilters).toEqual([]);
    expect(state.drillThroughs.find((drill) => drill.id === 'to_board').target.filter_mappings).toEqual([]);
    expect(state.drillThroughs.find((drill) => drill.id === 'to_floor').target.parameter_mappings).toHaveLength(1);
  });

  it('describes a mapping row per question card, unmapped ones flagged', () => {
    const state = loaded();
    const infos = {
      [infoKey(state.cards[0].question)]: questionInfo(fixtures.questions['q-by-region']),
      [infoKey(state.cards[1].question)]: questionInfo(fixtures.questions['q-detail']),
      [infoKey(state.cards[2].question)]: questionInfo(fixtures.questions['q-floor']),
    };
    const rows = mappingRows(state, filterOf(state, 'region'), infos);
    expect(rows.map((row) => [row.card.id, row.unmapped])).toEqual([
      ['by_region', false], ['detail', false], ['floor', true]]);
    expect(rows[0].info.parameters).toEqual([{id: 'region', type: 'string', required: true}]);
    expect(rows[1].info.columns).toEqual(['amount', 'product', 'region']);
  });
});

describe('mapping rules mirror the server', () => {
  const infos = () => {
    const state = loaded();
    return {state, infos: {
      [infoKey(state.cards[0].question)]: questionInfo(fixtures.questions['q-by-region']),
      [infoKey(state.cards[1].question)]: questionInfo(fixtures.questions['q-detail']),
      [infoKey(state.cards[2].question)]: questionInfo(fixtures.questions['q-floor']),
    }};
  };

  it('accepts the stored board without errors', () => {
    const {state, infos: known} = infos();
    expect(hasErrors(dashboardIssues(state, known))).toBe(false);
  });

  it('flags an undeclared parameter, a type mismatch and a field on a raw SQL card', () => {
    const {state, infos: known} = infos();
    const region = filterOf(state, 'region');
    const byRegion = known[infoKey(state.cards[0].question)];
    const floor = known[infoKey(state.cards[2].question)];
    expect(targetIssue(region, {card_id: 'by_region', parameter_id: 'nope'}, byRegion)).toMatch(/not declared/);
    expect(targetIssue(filterOf(state, 'floor'), {card_id: 'by_region', parameter_id: 'region'}, byRegion)).toMatch(/does not match/);
    expect(targetIssue(region, {card_id: 'floor', field: {column: 'x'}}, floor)).toMatch(/raw SQL/);
    expect(targetIssue(region, {card_id: 'by_region', field: {column: ''}}, byRegion)).toMatch(/Choose a column/);
    expect(targetIssue(region, {card_id: 'by_region', parameter_id: 'region'}, undefined)).toBe('');
  });

  it('an array parameter accepts a multiple or range filter', () => {
    const {state} = infos();
    const info = questionInfo({query: {kind: 'sql', sql: 'x'}, parameters: [{id: 'ids', type: 'array'}]});
    expect(targetIssue(filterOf(state, 'products'), {card_id: 'c', parameter_id: 'ids'}, info)).toBe('');
    expect(targetIssue(filterOf(state, 'region'), {card_id: 'c', parameter_id: 'ids'}, info)).toMatch(/does not match/);
  });

  it('warns about cards a filter skips, filters nothing uses, and required filters without a default', () => {
    const {state, infos: known} = infos();
    const edited = apply(state, {type: 'updateFilter', id: 'region', patch: {required: true}});
    const messages = dashboardIssues(edited, known).map((issue) => issue.message);
    expect(messages).toContain('Sales by region is not filtered by Region.'.replace('Sales by region', 'floor'));
    expect(messages.some((text) => /Filter Window is not mapped to any card/.test(text))).toBe(true);
    expect(messages.some((text) => /Required filter Region has no default/.test(text))).toBe(true);
  });

  it('errors for an empty name, a cross-filter without a column and a drill without a target', () => {
    const base = apply(emptyDashboard(),
      {type: 'addQuestionCard', tabId: 'main', question: {question_id: 'q1', revision: 1}},
      {type: 'addFilter', filter: {name: 'F', type: 'string'}});
    const withLinks = apply(base,
      {type: 'addCrossFilter', link: newCrossFilter({id: '', sourceCardId: 'card_1', filterId: 'F'})},
      {type: 'addDrill', drill: newDrill({id: '', sourceCardId: 'card_1'})});
    const issues = dashboardIssues(withLinks, {});
    expect(issues.filter((issue) => issue.level === 'error').map((issue) => issue.path)).toEqual([
      'name', 'cross_filters.cross_1', 'drill_throughs.drill_1']);
  });
});

describe('cross-filter and drill-through definitions', () => {
  it('adds, edits and removes a cross-filter in the exact server shape', () => {
    let state = apply(loaded(), {type: 'addCrossFilter', link: newCrossFilter({
      id: '', sourceCardId: 'by_region', filterId: 'floor'})});
    expect(state.crossFilters[1]).toEqual({id: 'cross_1', source_card_id: 'by_region', source_column: '',
      filter_id: 'floor', exclude_source: true});
    state = reduce(state, {type: 'updateCrossFilter', id: 'cross_1', patch: {source_column: 'amount', exclude_source: false}});
    expect(state.crossFilters[1]).toMatchObject({source_column: 'amount', exclude_source: false});
    expect(toDashboard(state).cross_filters[1]).toEqual({id: 'cross_1', source_card_id: 'by_region',
      source_column: 'amount', filter_id: 'floor', exclude_source: false});
    expect(reduce(state, {type: 'removeCrossFilter', id: 'cross_1'}).crossFilters).toHaveLength(1);
  });

  it('edits a question drill-through: trigger, pinned target and value sources', () => {
    let state = apply(loaded(), {type: 'addDrill', drill: newDrill({id: '', sourceCardId: 'by_region'})});
    const added = state.drillThroughs[2];
    expect(added).toEqual({id: 'drill_1', source_card_id: 'by_region', label: '', trigger: {row: true},
      target: {kind: 'question', question_id: '', revision: 1, parameter_mappings: []}});
    state = reduce(state, {type: 'updateDrill', id: 'drill_1', patch: {
      label: 'Open floor', trigger: {column: 'amount'},
      target: {kind: 'question', question_id: 'q-floor', revision: 1, parameter_mappings: [
        {parameter_id: 'floor', from: {column: 'amount'}},
        {parameter_id: 'floor', from: {value: 7}},
        {parameter_id: 'floor', from: {filter_id: 'floor'}}]}}});
    expect(toDashboard(state).drill_throughs[2]).toEqual({
      id: 'drill_1', source_card_id: 'by_region', label: 'Open floor', trigger: {column: 'amount'},
      target: {kind: 'question', question_id: 'q-floor', revision: 1, parameter_mappings: [
        {parameter_id: 'floor', from: {column: 'amount'}},
        {parameter_id: 'floor', from: {value: 7}},
        {parameter_id: 'floor', from: {filter_id: 'floor'}}]}});
  });

  it('a dashboard drill-through keeps filter_mappings and the target dashboard', () => {
    const drill = newDrill({id: '', sourceCardId: 'detail', kind: 'dashboard', target: {dashboard_id: 'd-other'}});
    expect(drill.target).toEqual({kind: 'dashboard', dashboard_id: 'd-other', filter_mappings: []});
  });

  it('identifier helpers produce portable ids', () => {
    expect(nextId('card', ['card_1', 'card_2'])).toBe('card_3');
    expect(slugId('2nd Region!', [], 'filter')).toBe('filter_2nd_Region');
    expect(slugId('Region', ['Region'])).toBe('Region_2');
  });

  it('parses filter values by type', () => {
    expect(parseFilterValue('integer', '12')).toBe(12);
    expect(parseFilterValue('integer', '1.5')).toBeUndefined();
    expect(parseFilterValue('number', '1.5')).toBe(1.5);
    expect(parseFilterValue('boolean', 'true')).toBe(true);
    expect(parseFilterValue('string', '  ')).toBeUndefined();
  });
});

describe('saving', () => {
  it('adopts the stored document when nothing changed while the request ran', () => {
    const draft = reduce(loaded(), {type: 'rename', name: 'Renamed'});
    const sent = toDashboard(draft);
    const saved = reduce(draft, {type: 'saved', sent, record: record({...fixtures.board, name: 'Renamed'}, {revision: 4})});
    expect(saved).toMatchObject({revision: 4, name: 'Renamed', dirty: false});
  });

  it('keeps edits made while the save was in flight, dirty, on the new revision', () => {
    const draft = reduce(loaded(), {type: 'rename', name: 'Renamed'});
    const sent = toDashboard(draft);
    const later = reduce(draft, {type: 'rename', name: 'Renamed again'});
    const saved = reduce(later, {type: 'saved', sent, record: record({...fixtures.board, name: 'Renamed'}, {revision: 4})});
    expect(saved).toMatchObject({revision: 4, name: 'Renamed again', dirty: true});
  });

  it('restoring a revision is an unsaved draft of the stored dashboard', () => {
    const restored = reduce(loaded(), {type: 'restore', definition: {...fixtures.board, name: 'Old name'}});
    expect(restored).toMatchObject({dashboardId: 'd1', revision: 3, name: 'Old name', dirty: true});
  });

  it('load replaces the draft with the stored revision', () => {
    const dirty = reduce(loaded(), {type: 'rename', name: 'Edited'});
    expect(reduce(dirty, {type: 'load', record: record(fixtures.board, {revision: 9})})).toMatchObject({
      revision: 9, name: 'Sales board', dirty: false});
  });
});
