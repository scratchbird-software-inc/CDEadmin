/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useInsertionEffect} from 'react';

const STYLE_ELEMENT_ID = 'sr-project-shell-islands-styles';

export const DEFAULT_ISLAND_RADIUS_PX = 12;
export const DEFAULT_PANEL_GAP_PX = 6;

/**
 * Clean-room PostgreSQL-licensed Island Layout & Tabbed-Notebook-Bar (`3a`-`3e`)
 * stylesheet for ScratchRobin:
 *   - Shared rounded corners (`--sr-island-radius: 12px`) across User Dashboard,
 *     Area 2, and all Area 3 sub-islands (`3a`, `3b`, `3c`, `3d`, `3e`).
 *   - Recessed Backdrop Colour `a` (`--sr-backdrop-a`) behind Area 2 & Area 3.
 *   - Strip Background Colour `b` (`--sr-strip-b`) on `3b1` (quick access) and
 *     `3b2` (tab strip), darker inactive tabs, and active folder tab `3b3`
 *     merging seamlessly into the `3b` command-icon panel, with `3b4` close `[x]`.
 *   - Inset short vertical pill resize handles inside `3a` and `3c`.
 *   - Configurable spacing (`--sr-panel-gap`) and per-area zoom (`--sr-zoom-*`).
 */
export const PROJECT_SHELL_ISLANDS_CSS = `
:root {
  --sr-island-radius: ${DEFAULT_ISLAND_RADIUS_PX}px;
  --sr-panel-gap: ${DEFAULT_PANEL_GAP_PX}px;
  --sr-island-border: #b8c7dc;
}

html[data-cde-theme="dark"],
html[data-theme="dark"] {
  --sr-island-border: #2c3a50;
}

.sr-shell-backdrop {
  --sr-backdrop-a: var(--sr-scheme-backdrop-a, #dce6f2);
  --sr-strip-b: var(--sr-scheme-strip-b, #e7eef8);
  --sr-tab-inactive-bg: var(--sr-scheme-tab-inactive-bg, #dbe5f3);
  --sr-tab-inactive-hover-bg: var(--sr-scheme-selection, #cfdcf0);
  --sr-island-bg: var(--sr-scheme-island-bg, #ffffff);
  --sr-island-drawer-bg: var(--sr-scheme-drawer-bg, #f8fafc);
  --sr-island-fg: var(--sr-scheme-fg, #0f172a);
  --sr-island-muted: var(--sr-scheme-muted, #52637a);
  --sr-island-border: var(--sr-scheme-border, #b8c7dc);
  --sr-island-accent: var(--sr-scheme-accent, #0f62fe);
  --sr-island-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
  --sr-resize-pill: #94a3b8;

  box-sizing: border-box;
  height: 100%;
  width: 100%;
  min-height: 0;
  min-width: 0;
  padding: var(--sr-panel-gap, 6px);
  gap: var(--sr-panel-gap, 6px);
  display: flex;
  flex-direction: row;
  align-items: stretch;
  background-color: var(--sr-backdrop-a);
  color: var(--sr-island-fg);
  font-family: var(--sr-font-ui, var(--cde-font-sans, sans-serif));
  font-size: var(--sr-ui-font-size, 14px);
  line-height: var(--sr-line-height, 1.45);
}

.sr-shell-backdrop[data-tone="dark"] {
  --sr-backdrop-a: var(--sr-scheme-backdrop-a, #0a0f18);
  --sr-strip-b: var(--sr-scheme-strip-b, #101724);
  --sr-tab-inactive-bg: var(--sr-scheme-tab-inactive-bg, #141e30);
  --sr-tab-inactive-hover-bg: var(--sr-scheme-selection, #1b2840);
  --sr-island-bg: var(--sr-scheme-island-bg, #172030);
  --sr-island-drawer-bg: var(--sr-scheme-drawer-bg, #141c2b);
  --sr-island-fg: var(--sr-scheme-fg, #f1f5f9);
  --sr-island-muted: var(--sr-scheme-muted, #94a3b8);
  --sr-island-border: var(--sr-scheme-border, #2c3a50);
  --sr-island-accent: var(--sr-scheme-accent, #60a5fa);
  --sr-island-shadow: 0 2px 8px rgba(0, 0, 0, 0.36);
  --sr-resize-pill: #475569;
}

/* Area 3 Outer Column & Sub-Rows */
.sr-area3-outer {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sr-panel-gap, 6px);
}

.sr-area3-lower-row {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: row;
  gap: var(--sr-panel-gap, 6px);
}

.sr-area3-center-right-col {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sr-panel-gap, 6px);
}

.sr-area3-work-and-right-row {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: row;
  gap: var(--sr-panel-gap, 6px);
}

/* Shared Island Card Frame (3a, 3b, 3c, 3d, 3e) */
.sr-island {
  box-sizing: border-box;
  border: 1px solid var(--sr-island-border);
  border-radius: var(--sr-island-radius, 12px);
  background-color: var(--sr-island-bg);
  color: var(--sr-island-fg);
  box-shadow: var(--sr-island-shadow);
  overflow: hidden;
  position: relative;
}

.sr-island-3a,
.sr-island-3c {
  background-color: var(--sr-island-drawer-bg);
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.sr-island-3a {
  padding-right: 10px;
}

.sr-island-3c {
  padding-left: 10px;
}

.sr-island-3e {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background-color: var(--sr-island-bg);
}

.sr-island-3d {
  flex: 0 0 auto;
  min-height: calc(28px * var(--sr-zoom-3d, 1));
  display: flex;
  align-items: center;
  padding: 0 12px;
  font-size: calc(0.8125rem * var(--sr-zoom-3d, 1));
  background-color: var(--sr-island-drawer-bg);
}

.sr-island-3d > [role="status"] {
  border-top: none !important;
  height: auto !important;
  min-height: calc(26px * var(--sr-zoom-3d, 1));
  width: 100%;
  padding: 0 !important;
  font-size: inherit;
}

/* Inset Short Vertical Line Resize Handle on 3a (right edge) & 3c (left edge) */
.sr-drawer-resize-handle {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 10px;
  height: 84px;
  cursor: col-resize;
  z-index: 30;
  outline: none;
  touch-action: none;
  display: flex;
  align-items: center;
  justify-content: center;
}

.sr-drawer-resize-handle--left {
  right: 1px;
}

.sr-drawer-resize-handle--right {
  left: 1px;
}

.sr-drawer-resize-handle::after {
  content: "";
  width: 3px;
  height: 48px;
  border-radius: 999px;
  background-color: var(--sr-resize-pill);
  opacity: 0.85;
  transition:
    background-color 140ms ease,
    height 140ms ease,
    opacity 140ms ease;
}

.sr-drawer-resize-handle:hover::after,
.sr-drawer-resize-handle:focus-visible::after,
.sr-drawer-resize-handle[data-dragging="true"]::after {
  background-color: var(--sr-island-accent);
  height: 58px;
  opacity: 1;
}

/* ==========================================================================
   Area 3b — Tabbed-Notebook-Bar (3b1 Quick Access, 3b2 Strip, 3b3 Active Tab,
   3b4 Close Button, and 3b Command Icon Body)
   ========================================================================== */
.sr-island-3b {
  flex: 0 0 auto;
  overflow: hidden;
  --snb-color-background: var(--sr-strip-b);
  --snb-color-panel: var(--sr-island-bg);
  --snb-color-text: var(--sr-island-fg);
  --snb-color-muted: var(--sr-island-muted);
  --snb-color-border: var(--sr-island-border);
  --snb-radius: 8px;
  --snb-font-size: calc(0.84375rem * var(--sr-zoom-3b, 1));
  --snb-small-font-size: calc(0.74rem * var(--sr-zoom-3b, 1));
  --snb-tab-height: calc(30px * var(--sr-zoom-3b, 1));
  --snb-panel-height: calc(68px * var(--sr-zoom-3b, 1));
  --snb-control-height: calc(28px * var(--sr-zoom-3b, 1));
  --snb-icon-size: calc(17px * var(--sr-zoom-3b, 1));
  --snb-large-icon-size: calc(28px * var(--sr-zoom-3b, 1));
}

.sr-island-3b .snb-bar {
  border-bottom: none;
  background: transparent;
}

/* 3b1 + 3b2 + 3b4 Strip (Background Colour b) */
.sr-island-3b .snb-strip {
  background-color: var(--sr-strip-b);
  border-bottom: none;
  box-shadow: inset 0 -1px 0 0 var(--sr-island-border);
  padding: 4px 6px 0 6px;
  gap: 6px;
  align-items: flex-end;
}

/* 3b1 — Quick Access (New / Save / Undo / Redo) */
.sr-island-3b .snb-quick {
  background-color: var(--sr-strip-b);
  padding: 1px 8px 3px 2px;
  margin-bottom: 1px;
  gap: 3px;
  border-inline-end: 1px solid var(--sr-island-border);
}

.sr-island-3b .snb-quick .snb-control {
  min-height: calc(25px * var(--sr-zoom-3b, 1));
  padding: 0 5px;
  border-radius: 6px;
}

.sr-island-3b .snb-quick .snb-control .snb-label {
  display: none;
}

/* 3b2 — Tab Strip Track & Inactive Tabs (slightly darker than 3b3) */
.sr-island-3b .snb-tabs {
  flex: 1 1 auto;
  gap: 4px;
  align-items: flex-end;
  margin-bottom: 0;
}

.sr-island-3b .snb-tab {
  min-height: calc(28px * var(--sr-zoom-3b, 1));
  padding: 0 14px;
  margin-bottom: 1px;
  border-radius: 9px 9px 0 0;
  border: 1px solid transparent;
  border-bottom: none;
  background-color: var(--sr-tab-inactive-bg);
  color: var(--sr-island-muted);
  font-weight: 500;
  box-shadow: none;
  transition: background-color 120ms ease, color 120ms ease;
}

.sr-island-3b .snb-tab:hover:not([aria-selected="true"]) {
  background-color: var(--sr-tab-inactive-hover-bg);
  color: var(--sr-island-fg);
}

/* 3b3 — Active Tab (lighter surface, seamlessly opens into 3b icon area) */
.sr-island-3b .snb-tab[aria-selected="true"] {
  background-color: var(--sr-island-bg);
  color: var(--sr-island-fg);
  font-weight: 600;
  border: 1px solid var(--sr-island-border);
  border-bottom: none;
  border-radius: 10px 10px 0 0;
  margin-bottom: 0;
  padding-bottom: 1px;
  z-index: 2;
  box-shadow: none;
}

/* 3b4 — Right-aligned Close Button [x] */
.sr-island-3b .snb-end {
  padding: 0 2px 2px 4px;
  margin-bottom: 1px;
  margin-inline-start: auto;
}

/* 3b — Compact Pure Icon-Only Command Body */
.sr-island-3b .snb-panel {
  background-color: var(--sr-island-bg);
  border-top: none;
  padding: 4px 10px;
  min-height: calc(36px * var(--sr-zoom-3b, 1));
  align-items: center;
}

.sr-island-3b .snb-group {
  flex-direction: row;
  align-items: center;
  padding: 0 6px;
}

.sr-island-3b .snb-group-label,
.sr-island-3b .snb-panel .snb-control .snb-label {
  display: none !important;
}

.sr-island-3b .snb-panel .snb-stack {
  flex-direction: row;
  align-items: center;
  gap: 3px;
}

.sr-island-3b .snb-panel .snb-control {
  min-width: calc(28px * var(--sr-zoom-3b, 1));
  min-height: calc(28px * var(--sr-zoom-3b, 1));
  justify-content: center;
  padding: 0 5px;
  border-radius: var(--sr-control-radius, 7px);
}

.sr-3b-extras-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px 4px 10px;
  background-color: var(--sr-island-bg);
}

/* ==========================================================================
   Multi-Application Tab Strip inside 3e (matches 3b2 / 3b3 visual language)
   ========================================================================== */
.sr-area3-app-tabs {
  min-height: calc(32px * var(--sr-zoom-3e, 1));
  padding: 4px 8px 0 8px;
  gap: 4px;
  display: flex;
  align-items: flex-end;
  background-color: var(--sr-strip-b);
  border-bottom: none;
  box-shadow: inset 0 -1px 0 0 var(--sr-island-border);
  overflow-x: auto;
  flex-shrink: 0;
}

.sr-area3-app-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: calc(27px * var(--sr-zoom-3e, 1));
  padding: 0 12px;
  margin-bottom: 1px;
  cursor: pointer;
  flex-shrink: 0;
  max-width: 280px;
  border-radius: 9px 9px 0 0;
  border: 1px solid transparent;
  border-bottom: none;
  background-color: var(--sr-tab-inactive-bg);
  color: var(--sr-island-muted);
  font-size: calc(0.825rem * var(--sr-zoom-3e, 1));
  font-weight: 500;
  user-select: none;
}

.sr-area3-app-tab:hover:not([data-tab-active="true"]) {
  background-color: var(--sr-tab-inactive-hover-bg);
  color: var(--sr-island-fg);
}

.sr-area3-app-tab[data-tab-active="true"] {
  background-color: var(--sr-island-bg);
  color: var(--sr-island-fg);
  font-weight: 600;
  border: 1px solid var(--sr-island-border);
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 1px;
  z-index: 2;
}

/* Per-Area Zoom Scaling for 3a, 3c, 3e Content Surfaces */
.sr-zoom-surface {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  zoom: var(--sr-surface-zoom, 1);
}
`;

export function useProjectShellStyles(inject = true) {
  useInsertionEffect(() => {
    if (!inject || typeof document === 'undefined') return;
    if (document.getElementById(STYLE_ELEMENT_ID)) return;
    const styleEl = document.createElement('style');
    styleEl.id = STYLE_ELEMENT_ID;
    styleEl.textContent = PROJECT_SHELL_ISLANDS_CSS;
    document.head.appendChild(styleEl);
  }, [inject]);
}
