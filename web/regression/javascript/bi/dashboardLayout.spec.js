/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  GRID_COLUMNS, cellsFromPixels, clampLayout, collisions, compact, moveTo, nextPosition, nudge,
  overlaps, resizeBy, resizeTo, rowCount,
} from 'sources/cdeadmin_ui/modules/bi/dashboardLayout';
import {dashboardFixtures} from './dashboardFixtures';

const card = (id, x, y, w, h, tab = 'main') => ({id, tab_id: tab, type: 'text', layout: {x, y, w, h}});
const at = (cards, id) => cards.find((item) => item.id === id).layout;

describe('clampLayout', () => {
  it('keeps a card inside the 24-column grid and the backend bounds', () => {
    expect(clampLayout({x: 30, y: -3, w: 40, h: 500})).toEqual({x: 0, y: 0, w: 24, h: 100});
    expect(clampLayout({x: 20, y: 2, w: 12, h: 3})).toEqual({x: 12, y: 2, w: 12, h: 3});
    expect(clampLayout({x: 1.4, y: 2.6, w: 0, h: 0})).toEqual({x: 1, y: 3, w: 1, h: 1});
    expect(clampLayout({})).toEqual({x: 0, y: 0, w: 12, h: 6});
  });
});

describe('moving and resizing', () => {
  const cards = [card('a', 0, 0, 12, 4), card('b', 12, 0, 12, 4), card('c', 0, 4, 24, 2)];

  it('moves a card and pushes the cards it lands on downwards', () => {
    const moved = moveTo(cards, 'a', 12, 0);
    expect(at(moved, 'a')).toEqual({x: 12, y: 0, w: 12, h: 4});
    expect(at(moved, 'b')).toEqual({x: 12, y: 4, w: 12, h: 4});
    expect(at(moved, 'c')).toEqual({x: 0, y: 8, w: 24, h: 2});
    expect(collisions(moved)).toEqual([]);
  });

  it('leaves cards that are not hit where they are', () => {
    const moved = moveTo(cards, 'b', 12, 1);
    expect(at(moved, 'a')).toEqual(at(cards, 'a'));
    expect(at(moved, 'c').y).toBe(5);
  });

  it('never leaves the grid', () => {
    expect(at(moveTo(cards, 'b', 99, -4), 'b')).toEqual({x: 12, y: 0, w: 12, h: 4});
    expect(at(resizeTo(cards, 'a', 99, 0), 'a')).toEqual({x: 0, y: 0, w: 24, h: 1});
  });

  it('resizing pushes neighbours and keeps tabs apart', () => {
    const tabbed = [...cards, card('d', 0, 0, 24, 8, 'other')];
    const resized = resizeTo(tabbed, 'a', 24, 4);
    expect(at(resized, 'b').y).toBe(4);
    expect(at(resized, 'd')).toEqual({x: 0, y: 0, w: 24, h: 8});
    expect(collisions(resized)).toEqual([]);
  });

  it('keyboard steps move and resize by one cell', () => {
    expect(at(nudge(cards, 'a', 1, 0), 'a').x).toBe(1);
    expect(at(nudge(cards, 'a', -1, 0), 'a').x).toBe(0);
    expect(at(resizeBy(cards, 'c', 0, 1), 'c').h).toBe(3);
    expect(at(resizeBy(cards, 'a', -1, -1), 'a')).toEqual({x: 0, y: 0, w: 11, h: 3});
  });

  it('does not change the input and ignores unknown cards', () => {
    const before = JSON.stringify(cards);
    moveTo(cards, 'a', 12, 0);
    expect(JSON.stringify(cards)).toBe(before);
    expect(moveTo(cards, 'zzz', 1, 1)).toBe(cards);
  });
});

describe('placing new cards and tidying', () => {
  it('puts a new card below everything in its tab', () => {
    const cards = [card('a', 0, 0, 12, 4), card('b', 12, 2, 12, 5)];
    expect(nextPosition(cards, 'main')).toEqual({x: 0, y: 7, w: 12, h: 6});
    expect(nextPosition(cards, 'empty')).toEqual({x: 0, y: 0, w: 12, h: 6});
  });

  it('compacts vertical gaps but keeps reading order', () => {
    const tidy = compact([card('a', 0, 3, 12, 2), card('b', 12, 9, 12, 2), card('c', 0, 12, 12, 2)], 'main');
    expect(at(tidy, 'a').y).toBe(0);
    expect(at(tidy, 'b').y).toBe(0);
    expect(at(tidy, 'c').y).toBe(2);
  });

  it('converts drag distance to whole cells', () => {
    expect(cellsFromPixels(105, -49, {columnWidth: 50, rowHeight: 60})).toEqual({dx: 2, dy: -1});
    expect(cellsFromPixels(105, 10, {columnWidth: 0, rowHeight: 0})).toEqual({dx: 0, dy: 0});
  });

  it('measures rows and overlap', () => {
    expect(rowCount([card('a', 0, 0, 4, 9)], 'main')).toBe(9);
    expect(overlaps({x: 0, y: 0, w: 2, h: 2}, {x: 2, y: 0, w: 2, h: 2})).toBe(false);
    expect(GRID_COLUMNS).toBe(24);
  });
});

describe('backend-normalized layouts', () => {
  it('the fixture board has no collisions and survives a no-op move', () => {
    const {cards} = dashboardFixtures.board;
    expect(collisions(cards)).toEqual([]);
    const same = moveTo(cards, 'detail', cards[1].layout.x, cards[1].layout.y);
    expect(same.map((item) => item.layout)).toEqual(cards.map((item) => item.layout));
  });

  it('every monitoring card layout is already valid', () => {
    for(const card of dashboardFixtures.monitoring.dashboard.cards) {
      expect(clampLayout(card.layout)).toEqual(card.layout);
    }
  });
});
