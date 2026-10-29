/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  RUN_CONCURRENCY, cardLinks, cardsToRun, draftsFromValues, filterPayload, initialValues, initialViewer,
  linkChoices, markColumn, missingRequired, refreshLabel, runBounded, runnableCards, valuesFromDrafts,
  viewerReducer,
} from 'sources/cdeadmin_ui/modules/bi/dashboardViewer';
import {lossLines, snapshotFromText} from 'sources/cdeadmin_ui/modules/bi/dashboardImport';
import {parseInline, parseMarkdown, safeHref} from 'sources/cdeadmin_ui/modules/bi/markdown';
import {dashboardFixtures as fixtures} from './dashboardFixtures';

const board = fixtures.board;
const execution = (cache) => ({cache, columns: [], rows: []});

describe('initial values and payload', () => {
  it('starts from each filter default and omits blanks', () => {
    const values = initialValues(board);
    expect(values.floor).toBe(0);
    expect(filterPayload({a: '', b: [], c: null, d: 0, e: 'x'})).toEqual({d: 0, e: 'x'});
  });

  it('reports required filters that have no value and no default', () => {
    const dashboard = {...board, filters: [{id: 'r', name: 'R', required: true}, {id: 's', name: 'S', required: true, default: 'a'}]};
    expect(missingRequired(dashboard, {}).map((filter) => filter.id)).toEqual(['r']);
    expect(missingRequired(dashboard, {r: 'x'})).toEqual([]);
  });

  it('only question cards run', () => {
    expect(runnableCards(board).map((card) => card.id)).toEqual(['by_region', 'detail', 'floor']);
  });
});

describe('viewer reducer', () => {
  const start = () => initialViewer(board);

  it('a cross-filter outcome replaces the values and records the exclusions', () => {
    const outcome = fixtures.cross.outcome;
    const next = viewerReducer(start(), {type: 'crossFilter', filterId: 'region', ...outcome});
    expect(next.values).toEqual(outcome.filters);
    expect(next.exclusions).toEqual(outcome.exclude);
  });

  it('an exclusion lapses when the filter it protects changes', () => {
    const crossed = viewerReducer(start(), {type: 'crossFilter', filterId: 'region', ...fixtures.cross.outcome});
    expect(viewerReducer(crossed, {type: 'setValues', values: {...crossed.values}}).exclusions).toHaveLength(1);
    expect(viewerReducer(crossed, {type: 'setValues', values: {...crossed.values, region: 'east'}}).exclusions).toEqual([]);
  });

  it('keeps the old result visible and stale while filters change', () => {
    let state = start();
    const key = JSON.stringify([state.values, state.exclusions]);
    state = viewerReducer(state, {type: 'cardStart', id: 'floor', token: 1, key});
    state = viewerReducer(state, {type: 'cardDone', id: 'floor', token: 1, execution: execution(), receivedAt: 1000});
    expect(state.cards.floor).toMatchObject({status: 'ready', stale: false});
    state = viewerReducer(state, {type: 'setValues', values: {region: 'east'}});
    expect(state.cards.floor).toMatchObject({status: 'ready', stale: true});
    expect(cardsToRun(board, state, 'main').map((card) => card.id)).toEqual(['by_region', 'detail', 'floor']);
  });

  it('ignores a result from a superseded run', () => {
    let state = viewerReducer(start(), {type: 'cardStart', id: 'floor', token: 2, key: 'k'});
    state = viewerReducer(state, {type: 'cardDone', id: 'floor', token: 1, execution: execution(), receivedAt: 1});
    expect(state.cards.floor.status).toBe('loading');
    state = viewerReducer(state, {type: 'cardFail', id: 'floor', token: 1, error: 'old'});
    expect(state.cards.floor.status).toBe('loading');
  });

  it('a failed refresh keeps the previous result, flagged stale', () => {
    let state = viewerReducer(start(), {type: 'cardStart', id: 'floor', token: 1, key: 'k'});
    state = viewerReducer(state, {type: 'cardDone', id: 'floor', token: 1, execution: execution(), receivedAt: 5});
    state = viewerReducer(state, {type: 'cardStart', id: 'floor', token: 2, key: 'k2'});
    state = viewerReducer(state, {type: 'cardFail', id: 'floor', token: 2, error: 'boom'});
    expect(state.cards.floor).toMatchObject({status: 'error', error: 'boom', stale: true});
    expect(state.cards.floor.execution).toBeTruthy();
  });

  it('a cache hit reports when the result was produced', () => {
    let state = viewerReducer(start(), {type: 'cardStart', id: 'floor', token: 1, key: 'k'});
    state = viewerReducer(state, {type: 'cardDone', id: 'floor', token: 1, receivedAt: 100000,
      execution: execution({hit: true, age_seconds: 30})});
    expect(state.cards.floor).toMatchObject({cacheHit: true, producedAt: 70000});
  });

  it('selects tabs and full screen without touching results', () => {
    const state = viewerReducer(viewerReducer(start(), {type: 'selectTab', tabId: 'main'}), {type: 'fullscreen', id: 'detail'});
    expect(state.fullscreen).toBe('detail');
  });
});

describe('bounded concurrency', () => {
  it('never exceeds the limit and visits every item', async () => {
    let active = 0;
    let peak = 0;
    const seen = [];
    await runBounded([1, 2, 3, 4, 5, 6, 7, 8, 9], RUN_CONCURRENCY, async (item) => {
      active += 1;
      peak = Math.max(peak, active);
      await Promise.resolve();
      await Promise.resolve();
      seen.push(item);
      active -= 1;
    });
    expect(peak).toBeLessThanOrEqual(RUN_CONCURRENCY);
    expect(seen).toHaveLength(9);
  });

  it('stops starting work once cancelled and survives a failing worker', async () => {
    const seen = [];
    let cancelled = false;
    await runBounded([1, 2, 3, 4], 1, async (item) => {
      seen.push(item);
      if(item === 1) throw new Error('x');
      cancelled = true;
    }, () => cancelled);
    expect(seen).toEqual([1, 2]);
  });
});

describe('clicks', () => {
  it('finds the cross-filters and drill-throughs a click triggers', () => {
    const links = cardLinks(board, 'detail', 'region');
    expect(links.cross.map((link) => link.id)).toEqual(['click_region']);
    expect(links.drills.every((drill) => drill.source_card_id === 'detail')).toBe(true);
    expect(cardLinks(board, 'note', 'x')).toEqual({cross: [], drills: []});
    expect(linkChoices(board, links, {region: 'west'})[0]).toMatchObject({kind: 'cross', id: 'click_region'});
  });

  it('chart marks map to the plotted column', () => {
    expect(markColumn({x: 'region', y: ['amount', 'cost']}, 1)).toBe('cost');
    expect(markColumn({x: 'region', y: ['amount']}, 4)).toBe('region');
  });

  it('labels refresh intervals', () => {
    expect([0, 30, 120, 7200].map(refreshLabel)).toEqual(['Off', 'Every 30 seconds', 'Every 2 minutes', 'Every 2 hours']);
  });
});

describe('filter drafts', () => {
  it('round-trips the default values', () => {
    const drafts = draftsFromValues(board, initialValues(board));
    expect(valuesFromDrafts(board, drafts)).toEqual({values: initialValues(board), errors: {}});
  });

  it('reports incomplete ranges and invalid numbers', () => {
    const range = {widget: 'date_range', type: 'date', id: 'w', allowed_values: []};
    const number = {widget: 'number', type: 'integer', id: 'n', allowed_values: []};
    const result = valuesFromDrafts({filters: [range, number]}, {w: ['2026-01-01', ''], n: 'abc'});
    expect(Object.keys(result.errors)).toEqual(['w', 'n']);
    expect(valuesFromDrafts({filters: [range]}, {w: ['2026-01-01', '2026-02-01']}).values).toEqual({
      w: ['2026-01-01', '2026-02-01']});
  });
});

describe('markdown is text, never markup', () => {
  it('keeps script tags as text and drops unsafe links', () => {
    const blocks = parseMarkdown('<script>alert(1)</script>\n\n[x](javascript:alert(1))');
    expect(blocks[0].children).toEqual([{type: 'text', value: '<script>alert(1)</script>'}]);
    expect(JSON.stringify(blocks[1])).not.toContain('"link"');
    expect(safeHref('javascript:alert(1)')).toBeNull();
    expect(safeHref(' https://example.org/a ')).toBe('https://example.org/a');
    expect(safeHref('mailto:a@b.c')).toBe('mailto:a@b.c');
    expect(safeHref('data:text/html,x')).toBeNull();
  });

  it('parses nested emphasis and links without looping', () => {
    expect(parseInline('a **b _c_ d** [e](https://x.y) `f`')).toEqual([
      {type: 'text', value: 'a '},
      {type: 'strong', children: [{type: 'text', value: 'b '}, {type: 'em', children: [{type: 'text', value: 'c'}]},
        {type: 'text', value: ' d'}]},
      {type: 'text', value: ' '},
      {type: 'link', href: 'https://x.y', children: [{type: 'text', value: 'e'}]},
      {type: 'text', value: ' '},
      {type: 'code', value: 'f'},
    ]);
  });

  it('turns images into their alt text and parses common blocks', () => {
    expect(parseInline('![logo](http://x/y.png)')).toEqual([{type: 'text', value: 'logo'}]);
    const blocks = parseMarkdown('# T\n\n- a\n- b\n\n1. c\n\n> q\n\n```\ncode\n```\n\n---');
    expect(blocks.map((block) => block.type)).toEqual(['heading', 'list', 'list', 'quote', 'code', 'rule']);
    expect(blocks[1].ordered).toBe(false);
    expect(blocks[2].ordered).toBe(true);
  });
});

describe('monitoring import input', () => {
  it('wraps DDN text in a snapshot and accepts a snapshot file', () => {
    expect(snapshotFromText('a.ddn', 'dashboard x {}')).toEqual({
      format: 'ddn-source-workspace@1', entry: 'dashboard.ddn', files: {'dashboard.ddn': 'dashboard x {}'}});
    const snapshot = {format: 'ddn-source-workspace@1', entry: 'dashboard.ddn', files: {'dashboard.ddn': 'x'}};
    expect(snapshotFromText('s.json', JSON.stringify(snapshot))).toEqual(snapshot);
    expect(() => snapshotFromText('s.json', '{nope')).toThrow(/not a valid DDN snapshot/);
    expect(() => snapshotFromText('s.json', '{"a":1}')).toThrow(/not a DDN snapshot/);
    expect(() => snapshotFromText('a.ddn', '  ')).toThrow(/empty/);
  });

  it('turns loss entries into report lines', () => {
    expect(lossLines([{code: 'x', severity: 'error', detail: 'bad'}, {code: 'y', severity: 'info'}])).toEqual([
      {severity: 'error', text: 'bad'}, {severity: 'warning', text: 'y'}]);
  });
});
