/////////////////////////////////////////////////////////////
//
// Scratch notebook bar
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// The bar's stylesheet. Every colour, font and size is a --snb-* variable
// with a fallback (CSS system colours for colours), so the host's appearance
// settings decide the look and forced-colours modes still work. No literal
// colours appear here; a test checks it.

import {useInsertionEffect} from 'react';

const v = (name, fallback) => `var(--snb-${name}, ${fallback})`;
const C = {
  background: v('color-background', 'Canvas'),
  panel: v('color-panel', 'Canvas'),
  text: v('color-text', 'CanvasText'),
  muted: v('color-muted', 'GrayText'),
  border: v('color-border', 'GrayText'),
  hover: v('color-hover', 'color-mix(in srgb, Highlight 15%, transparent)'),
  selected: v('color-selected', 'Highlight'),
  selectedText: v('color-selected-text', 'HighlightText'),
  accent: v('color-accent', 'Highlight'),
  focus: v('color-focus', 'Highlight'),
  hint: v('color-hint', 'CanvasText'),
  hintText: v('color-hint-text', 'Canvas'),
};
const S = {
  font: v('font-family', 'inherit'),
  size: v('font-size', '0.875rem'),
  small: v('small-font-size', '0.75rem'),
  tab: v('tab-height', '32px'),
  panel: v('panel-height', '88px'),
  icon: v('icon-size', '16px'),
  largeIcon: v('large-icon-size', '32px'),
  control: v('control-height', '28px'),
  gap: v('gap', '4px'),
  radius: v('radius', '0px'),
  focusWidth: v('focus-width', '2px'),
  focusOffset: v('focus-offset', '1px'),
  motion: v('motion', '150ms'),
};

export const NOTEBOOKBAR_CSS = `
.snb-bar { font-family: ${S.font}; font-size: ${S.size}; color: ${C.text};
  background: ${C.background}; border-bottom: 1px solid ${C.border};
  display: flex; flex-direction: column; min-width: 0; position: relative; }
.snb-bar button, .snb-bar select { font: inherit; color: inherit; }
.snb-strip { display: flex; align-items: stretch; min-height: ${S.tab};
  gap: ${S.gap}; min-width: 0; }
.snb-start, .snb-end { display: flex; align-items: center; gap: ${S.gap};
  flex: 0 0 auto; padding: 0 ${S.gap}; }
.snb-end { margin-inline-start: auto; }
.snb-quick { display: flex; align-items: center; gap: 2px; flex: 0 0 auto;
  padding-inline-end: ${S.gap}; border-inline-end: 1px solid ${C.border}; }
.snb-tabs { display: flex; align-items: stretch; min-width: 0; flex: 0 1 auto;
  overflow-x: auto; scrollbar-width: thin; }
.snb-tab { border: 0; background: transparent; padding: 0 calc(${S.gap} * 3);
  min-height: ${S.tab}; cursor: pointer; white-space: nowrap; position: relative;
  border-radius: ${S.radius} ${S.radius} 0 0; }
.snb-tab:hover { background: ${C.hover}; }
.snb-tab[aria-selected="true"] { background: ${C.panel}; font-weight: 600;
  box-shadow: inset 0 -3px 0 ${C.accent}; }
.snb-tab.snb-contextual { font-style: italic; }
.snb-panel { background: ${C.panel}; min-height: ${S.panel}; display: flex;
  align-items: stretch; gap: ${S.gap}; padding: ${S.gap}; min-width: 0;
  overflow: hidden; border-top: 1px solid ${C.border}; }
.snb-bar.snb-collapsed .snb-panel { display: none; }
.snb-bar.snb-collapsed.snb-peek .snb-panel { display: flex; position: absolute;
  top: 100%; inset-inline: 0; z-index: 1000; border-bottom: 1px solid ${C.border}; }
.snb-group { display: flex; flex-direction: column; flex: 0 0 auto;
  padding: 0 ${S.gap}; border-inline-end: 1px solid ${C.border}; }
.snb-group-body { display: flex; align-items: center; gap: 2px; flex: 1 1 auto; }
.snb-group-label { font-size: ${S.small}; color: ${C.muted}; text-align: center;
  white-space: nowrap; padding-top: 2px; }
.snb-stack { display: flex; flex-direction: column; justify-content: center;
  gap: 2px; align-self: stretch; }
.snb-control { border: 1px solid transparent; background: transparent;
  border-radius: ${S.radius}; min-height: ${S.control}; display: inline-flex;
  align-items: center; gap: ${S.gap}; padding: 0 ${S.gap}; cursor: pointer;
  white-space: nowrap; position: relative;
  transition: background-color ${S.motion}; }
.snb-control:hover:not([aria-disabled="true"]) { background: ${C.hover}; }
.snb-control[aria-pressed="true"] { background: ${C.selected};
  color: ${C.selectedText}; }
.snb-control[aria-disabled="true"] { color: ${C.muted}; cursor: default; }
.snb-control .snb-icon { width: ${S.icon}; height: ${S.icon}; display: inline-flex;
  align-items: center; justify-content: center; flex: 0 0 auto; }
.snb-control .snb-icon > svg { width: 100%; height: 100%; }
.snb-large { flex-direction: column; justify-content: center; min-width: 52px;
  align-self: stretch; padding: 2px ${S.gap}; font-size: ${S.small}; }
.snb-large .snb-icon { width: ${S.largeIcon}; height: ${S.largeIcon}; }
.snb-split { display: inline-flex; align-items: stretch; }
.snb-split.snb-large-split { flex-direction: column; align-self: stretch; }
.snb-split > .snb-control:first-child { border-start-end-radius: 0;
  border-end-end-radius: 0; }
.snb-arrow { min-width: 16px; padding: 0 2px; }
.snb-arrow::after { content: ""; border: 4px solid transparent;
  border-top-color: currentColor; margin-top: 4px; }
.snb-swatch { display: block; height: 4px; width: 100%; margin-top: -2px; }
.snb-select { min-height: ${S.control}; border: 1px solid ${C.border};
  background: ${C.panel}; border-radius: ${S.radius}; padding: 0 ${S.gap}; }
.snb-gallery { display: flex; align-items: stretch; gap: 2px; max-width: 360px;
  overflow: hidden; border: 1px solid ${C.border}; }
.snb-gallery-item { border: 1px solid transparent; background: transparent;
  min-width: 56px; display: flex; flex-direction: column; align-items: center;
  justify-content: center; gap: 2px; cursor: pointer; padding: 2px;
  font-size: ${S.small}; }
.snb-gallery-item:hover { background: ${C.hover}; }
.snb-gallery-item[aria-checked="true"] { border-color: ${C.accent}; }
.snb-separator { width: 1px; align-self: stretch; background: ${C.border};
  margin: 2px ${S.gap}; }
.snb-overflow { align-self: stretch; }
.snb-popup { position: fixed; z-index: 2000; min-width: 160px; max-height: 60vh;
  overflow: auto; background: ${C.panel}; color: ${C.text};
  border: 1px solid ${C.border}; padding: 2px 0; font-family: ${S.font};
  font-size: ${S.size}; }
.snb-popup-item { display: flex; align-items: center; gap: ${S.gap}; width: 100%;
  border: 0; background: transparent; text-align: start; padding: 4px 12px;
  min-height: ${S.control}; cursor: pointer; }
.snb-popup-item:hover, .snb-popup-item:focus { background: ${C.hover}; }
.snb-popup-item[aria-disabled="true"] { color: ${C.muted}; cursor: default; }
.snb-popup-separator { height: 1px; background: ${C.border}; margin: 2px 0; }
.snb-palette { display: grid; grid-template-columns: repeat(8, 20px); gap: 4px;
  padding: 6px; }
.snb-palette button { width: 20px; height: 20px; padding: 0;
  border: 1px solid ${C.border}; cursor: pointer; }
.snb-popup .snb-overflow-group { padding: 4px; border-bottom: 1px solid ${C.border}; }
.snb-hint { position: absolute; inset-inline-end: -2px; bottom: -4px; z-index: 3;
  background: ${C.hint}; color: ${C.hintText}; font-size: ${S.small};
  line-height: 1; padding: 2px 3px; border-radius: 2px; pointer-events: none;
  font-weight: 600; }
.snb-bar :is(button, select, [tabindex]):focus-visible {
  outline: ${S.focusWidth} solid ${C.focus}; outline-offset: ${S.focusOffset}; }
.snb-popup :is(button, [tabindex]):focus-visible {
  outline: ${S.focusWidth} solid ${C.focus}; outline-offset: -${S.focusWidth}; }
@media (forced-colors: active) {
  .snb-tab[aria-selected="true"], .snb-control[aria-pressed="true"] {
    forced-color-adjust: none; background: Highlight; color: HighlightText; }
  .snb-hint { forced-color-adjust: none; background: CanvasText; color: Canvas; }
}
@media (prefers-reduced-motion: reduce) {
  .snb-control { transition: none; }
}
`;

const STYLE_ATTRIBUTE = 'data-scratch-notebookbar';

/** Insert the stylesheet once per document (unless the host bundles it). */
export function useNotebookBarStyles(inject=true) {
  useInsertionEffect(() => {
    if(!inject || typeof document === 'undefined' ||
        document.head.querySelector(`style[${STYLE_ATTRIBUTE}]`)) return;
    const style = document.createElement('style');
    style.setAttribute(STYLE_ATTRIBUTE, '');
    style.textContent = NOTEBOOKBAR_CSS;
    document.head.appendChild(style);
  }, [inject]);
}
