/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useId, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {GRID_COLUMNS, cellsFromPixels, clampLayout, rowCount} from './dashboardLayout';

const GAP = 8;
const HIDDEN = {position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)', whiteSpace: 'nowrap'};

const ARROWS = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]};

export function describeLayout(layout) {
  return gettext('column %s, row %s, %s wide, %s high', layout.x + 1, layout.y + 1, layout.w, layout.h);
}

/**
 * The dashboard grid: 24 columns, fixed row height. Shared by the editor
 * (`editable`) and the viewer. In the editor each card gets a Move and a
 * Resize handle: drag with a pointer, or focus the handle and use the arrow
 * keys (one grid cell per press). The same placement can be typed into the
 * card panel, and every change is announced to assistive technology.
 */
export default function LayoutGrid({
  cards, tabId, label, rowHeight = 56, editable = false, onPlace, onNudge, onResizeBy, renderCard,
}) {
  const hintId = useId();
  const [announcement, setAnnouncement] = useState('');
  const cleanup = useRef(null);
  const visible = cards.filter((card) => card.tab_id === tabId);

  useEffect(() => () => cleanup.current?.(), []);

  const startDrag = useCallback((card, mode) => (event) => {
    if(event.button !== undefined && event.button !== 0) return;
    const grid = event.currentTarget.closest('[data-bi-grid]');
    if(!grid) return;
    event.preventDefault();
    const rect = grid.getBoundingClientRect();
    const scale = {columnWidth: (rect.width + GAP) / GRID_COLUMNS, rowHeight: rowHeight + GAP};
    const start = {x: event.clientX, y: event.clientY};
    const origin = {...card.layout};
    let last = '';
    const move = (next) => {
      const {dx, dy} = cellsFromPixels(next.clientX - start.x, next.clientY - start.y, scale);
      const layout = mode === 'move' ?
        {...origin, x: origin.x + dx, y: origin.y + dy} :
        {...origin, w: origin.w + dx, h: origin.h + dy};
      const key = JSON.stringify(clampLayout(layout));
      if(key === last) return;
      last = key;
      onPlace(card.id, layout);
    };
    const stop = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', stop);
      window.removeEventListener('pointercancel', stop);
      cleanup.current = null;
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', stop);
    window.addEventListener('pointercancel', stop);
    cleanup.current = stop;
  }, [onPlace, rowHeight]);

  const keys = (card, mode) => (event) => {
    const step = ARROWS[event.key];
    if(!step) return;
    event.preventDefault();
    const resize = mode === 'resize' || event.shiftKey;
    if(resize) onResizeBy(card.id, step[0], step[1]);
    else onNudge(card.id, step[0], step[1]);
  };

  // Announce the focused card's new placement after each keyboard change.
  const [focused, setFocused] = useState('');
  const placement = cards.find((card) => card.id === focused)?.layout;
  const placementText = placement ? describeLayout(placement) : '';
  useEffect(() => {
    if(placementText) setAnnouncement(placementText);
  }, [placementText]);

  return <Box data-cdeadmin-qa-key="bi.dashboard.grid">
    {editable && <Box id={hintId} sx={HIDDEN}>
      {gettext('Use the arrow keys on Move to move a card and on Resize to resize it, one grid cell at a time. Pointer users can drag the handles.')}
    </Box>}
    <Box role="status" aria-live="polite" sx={HIDDEN}>{announcement}</Box>
    <Box data-bi-grid="true" role="group" aria-label={label}
      sx={{
        position: 'relative', display: 'grid', gap: `${GAP}px`, minWidth: 0,
        gridTemplateColumns: {xs: 'minmax(0, 1fr)', md: `repeat(${GRID_COLUMNS}, minmax(0, 1fr))`},
        gridAutoRows: {xs: 'auto', md: `${rowHeight}px`},
        minHeight: editable ? {md: rowCount(cards, tabId) * (rowHeight + GAP)} : undefined,
      }}>
      {visible.map((card) => {
        const {x, y, w, h} = card.layout;
        const title = card.title || card.id;
        const handles = editable && <>
          <Button size="small" aria-label={gettext('Move %s', title)} aria-describedby={hintId}
            onPointerDown={startDrag(card, 'move')} onKeyDown={keys(card, 'move')}
            onFocus={() => setFocused(card.id)} onBlur={() => setFocused('')}>{gettext('Move')}</Button>
          <Button size="small" aria-label={gettext('Resize %s', title)} aria-describedby={hintId}
            onPointerDown={startDrag(card, 'resize')} onKeyDown={keys(card, 'resize')}
            onFocus={() => setFocused(card.id)} onBlur={() => setFocused('')}>{gettext('Resize')}</Button>
        </>;
        return <Box key={card.id} data-bi-card={card.id}
          sx={{
            minWidth: 0, minHeight: {xs: h * rowHeight, md: 0},
            gridColumn: {xs: '1 / -1', md: `${x + 1} / span ${w}`},
            gridRow: {xs: 'auto', md: `${y + 1} / span ${h}`},
          }}>
          {renderCard(card, {handles})}
        </Box>;
      })}
    </Box>
  </Box>;
}

LayoutGrid.propTypes = {
  cards: PropTypes.array.isRequired,
  tabId: PropTypes.string.isRequired,
  label: PropTypes.string.isRequired,
  rowHeight: PropTypes.number,
  editable: PropTypes.bool,
  onPlace: PropTypes.func,
  onNudge: PropTypes.func,
  onResizeBy: PropTypes.func,
  renderCard: PropTypes.func.isRequired,
};
