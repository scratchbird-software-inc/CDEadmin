/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Pure grid arithmetic for dashboard cards. The document format places a
 * card at {x, y, w, h} on a 24-column grid (dashboard_models.py `_layout`:
 * x 0..23, w 1..24, x + w <= 24, y 0..10000, h 1..100). Cards only collide
 * with cards of the same tab. Moving or resizing a card pushes the cards it
 * lands on downwards; nothing else moves unless `compact` is asked for.
 *
 * Every function takes and returns plain card arrays and never mutates its
 * input, so the reducer can use them directly.
 */

export const GRID_COLUMNS = 24;
export const MAX_Y = 10000;
export const MAX_H = 100;
export const DEFAULT_SIZE = Object.freeze({w: 12, h: 6});
export const TEXT_SIZE = Object.freeze({w: 12, h: 3});

const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
const whole = (value, fallback) => Number.isFinite(Number(value)) ? Math.round(Number(value)) : fallback;

/** A layout forced into the bounds the backend accepts. */
export function clampLayout(layout) {
  const w = clamp(whole(layout?.w, DEFAULT_SIZE.w), 1, GRID_COLUMNS);
  const x = clamp(whole(layout?.x, 0), 0, GRID_COLUMNS - w);
  const h = clamp(whole(layout?.h, DEFAULT_SIZE.h), 1, MAX_H);
  const y = clamp(whole(layout?.y, 0), 0, MAX_Y);
  return {x, y, w, h};
}

export function overlaps(a, b) {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

/**
 * Place `id` at `layout`, then push every card of the same tab that it now
 * overlaps below it (cascading, in reading order). Cards that do not collide
 * keep their position.
 */
export function place(cards, id, layout) {
  const anchor = cards.find((card) => card.id === id);
  if(!anchor) return cards;
  const next = clampLayout(layout);
  const placed = [{...next}];
  const moved = new Map([[id, next]]);
  const others = cards
    .filter((card) => card.id !== id && card.tab_id === anchor.tab_id)
    .sort((left, right) => left.layout.y - right.layout.y || left.layout.x - right.layout.x);
  for(const card of others) {
    const box = {...card.layout};
    let hit = placed.find((item) => overlaps(box, item));
    while(hit) {
      box.y = hit.y + hit.h;
      hit = placed.find((item) => overlaps(box, item));
    }
    box.y = Math.min(box.y, MAX_Y);
    placed.push(box);
    if(box.y !== card.layout.y) moved.set(card.id, box);
  }
  return cards.map((card) => moved.has(card.id) ? {...card, layout: {...moved.get(card.id)}} : card);
}

const layoutOf = (cards, id) => cards.find((card) => card.id === id)?.layout;

export function moveTo(cards, id, x, y) {
  const current = layoutOf(cards, id);
  return current ? place(cards, id, {...current, x, y}) : cards;
}

export function resizeTo(cards, id, w, h) {
  const current = layoutOf(cards, id);
  return current ? place(cards, id, {...current, w, h}) : cards;
}

/** Move by whole cells (keyboard arrows). */
export function nudge(cards, id, dx, dy) {
  const current = layoutOf(cards, id);
  return current ? place(cards, id, {...current, x: current.x + dx, y: current.y + dy}) : cards;
}

/** Resize by whole cells (Shift + arrows). */
export function resizeBy(cards, id, dw, dh) {
  const current = layoutOf(cards, id);
  return current ? place(cards, id, {...current, w: current.w + dw, h: current.h + dh}) : cards;
}

/** Where a new card goes: left edge, just below everything in the tab. */
export function nextPosition(cards, tabId, size = DEFAULT_SIZE) {
  const bottom = cards.filter((card) => card.tab_id === tabId)
    .reduce((max, card) => Math.max(max, card.layout.y + card.layout.h), 0);
  return clampLayout({x: 0, y: bottom, ...size});
}

/** Close vertical gaps in one tab; the order of cards (y, then x) is kept. */
export function compact(cards, tabId) {
  const inTab = cards.filter((card) => card.tab_id === tabId)
    .sort((left, right) => left.layout.y - right.layout.y || left.layout.x - right.layout.x);
  const placed = [];
  const result = new Map();
  for(const card of inTab) {
    const box = {...card.layout, y: 0};
    let hit = placed.find((item) => overlaps(box, item));
    while(hit) {
      box.y = hit.y + hit.h;
      hit = placed.find((item) => overlaps(box, item));
    }
    placed.push(box);
    result.set(card.id, box);
  }
  return cards.map((card) => result.has(card.id) ? {...card, layout: result.get(card.id)} : card);
}

/** Pixel drag distance to whole grid cells. */
export function cellsFromPixels(dx, dy, {columnWidth, rowHeight}) {
  return {
    dx: columnWidth > 0 ? Math.round(dx / columnWidth) : 0,
    dy: rowHeight > 0 ? Math.round(dy / rowHeight) : 0,
  };
}

/** Number of grid rows a tab needs to show all its cards (at least `minimum`). */
export function rowCount(cards, tabId, minimum = 4) {
  return cards.filter((card) => card.tab_id === tabId)
    .reduce((max, card) => Math.max(max, card.layout.y + card.layout.h), minimum);
}

/** Cards of the same tab that overlap each other (should be empty). */
export function collisions(cards) {
  const found = [];
  for(let i = 0; i < cards.length; i += 1) {
    for(let j = i + 1; j < cards.length; j += 1) {
      if(cards[i].tab_id === cards[j].tab_id && overlaps(cards[i].layout, cards[j].layout)) {
        found.push([cards[i].id, cards[j].id]);
      }
    }
  }
  return found;
}
