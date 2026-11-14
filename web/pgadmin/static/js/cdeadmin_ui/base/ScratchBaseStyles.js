/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

const STYLE_ELEMENT_ID = 'sr-base-ui-standardized-styles';

export const SCRATCH_BASE_UI_CSS = `
:root {
  --sr-island-radius: 12px;
  --sr-control-radius: 7px;
  --sr-pill-radius: 999px;
  --sr-surface-card: var(--sr-scheme-island-bg, var(--sr-panel-bg, var(--cde-color-panel, #ffffff)));
  --sr-surface-elevated: var(--sr-scheme-island-bg, var(--sr-panel-bg, var(--cde-color-elevated, #ffffff)));
  --sr-surface-subtle: var(--sr-scheme-drawer-bg, var(--sr-strip-bg, var(--cde-color-workspace, #f1f5f9)));
  --sr-surface-hover: var(--sr-scheme-selection, var(--cde-color-hover, rgba(15, 23, 42, 0.055)));
  --sr-surface-selected: var(--sr-scheme-selection, var(--cde-color-selection, rgba(2, 132, 199, 0.11)));
  --sr-border-default: var(--sr-scheme-border, var(--sr-island-border, var(--cde-color-border, #cbd5e1)));
  --sr-border-subtle: var(--sr-scheme-border, var(--cde-color-subtle-border, #e2e8f0));
  --sr-text-primary: var(--sr-scheme-fg, var(--sr-text-fg, var(--cde-color-text, #0f172a)));
  --sr-text-secondary: var(--sr-scheme-muted, var(--sr-muted-fg, var(--cde-color-secondary-text, #475569)));
  --sr-text-muted: var(--sr-scheme-muted, var(--sr-muted-fg, var(--cde-color-muted-text, #64748b)));
  --sr-accent: var(--sr-scheme-accent, var(--sr-accent-fg, var(--cde-color-primary, #0284c7)));
  --sr-accent-hover: var(--sr-scheme-accent, #0369a1);
  --sr-accent-fg-contrast: #ffffff;
  --sr-danger: var(--sr-scheme-error, var(--cde-color-error, #dc2626));
  --sr-warning: var(--sr-scheme-warning, var(--cde-color-warning, #d97706));
  --sr-success: var(--sr-scheme-success, var(--cde-color-success, #16a34a));
  --sr-info: var(--sr-scheme-accent, var(--cde-color-info, #0284c7));
  --sr-focus-ring: 0 0 0 2px rgba(2, 132, 199, 0.32);
  --sr-popup-shadow: 0 12px 32px rgba(15, 23, 42, 0.14), 0 2px 6px rgba(15, 23, 42, 0.08);
  --sr-tree-guide: rgba(71, 85, 105, 0.78);
  --sr-tree-line: var(--sr-tree-guide);
  --sr-tree-active-line: var(--sr-accent, #0284c7);
  --sr-scrollbar-thumb: rgba(100, 116, 139, 0.44);
  --sr-scrollbar-thumb-hover: rgba(71, 85, 105, 0.68);
  --sr-font-mono: var(--cde-font-mono, 'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace);
}

body,
.sr-bui-dialog-popup,
.sr-popover-popup,
.sr-bui-table-card,
.sr-branched-tree {
  font-family: var(--sr-font-ui, var(--cde-font-sans, inherit));
}

.cm-editor,
.cm-scroller,
code,
pre,
kbd,
.sr-bui-mono {
  font-family: var(--sr-font-mono, var(--cde-font-mono, monospace));
  font-size: var(--sr-mono-font-size, inherit);
  font-variant-ligatures: var(--sr-font-ligatures, normal);
}

[data-cdeadmin-qa-key*="ddn"] svg text,
.ddn-viewer-surface {
  font-family: var(--sr-font-diagram, var(--sr-font-ui, sans-serif));
}

[data-cde-theme="dark"],
[data-theme="dark"],
.sr-shell-root[data-theme="dark"] {
  --sr-surface-card: var(--sr-scheme-island-bg, var(--sr-panel-bg, #151c28));
  --sr-surface-elevated: var(--sr-scheme-island-bg, #1b2434);
  --sr-surface-subtle: var(--sr-scheme-drawer-bg, var(--sr-strip-bg, #101622));
  --sr-surface-hover: var(--sr-scheme-selection, rgba(148, 163, 184, 0.11));
  --sr-surface-selected: var(--sr-scheme-selection, rgba(56, 189, 248, 0.16));
  --sr-border-default: var(--sr-scheme-border, var(--sr-island-border, #2b364a));
  --sr-border-subtle: var(--sr-scheme-border, #222c3d);
  --sr-text-primary: var(--sr-scheme-fg, var(--sr-text-fg, #e2e8f0));
  --sr-text-secondary: var(--sr-scheme-muted, #94a3b8);
  --sr-text-muted: var(--sr-scheme-muted, #64748b);
  --sr-accent: var(--sr-scheme-accent, var(--sr-accent-fg, #38bdf8));
  --sr-accent-hover: #0ea5e9;
  --sr-accent-fg-contrast: #082f49;
  --sr-popup-shadow: 0 16px 38px rgba(2, 6, 23, 0.52), 0 2px 8px rgba(2, 6, 23, 0.36);
  --sr-tree-guide: rgba(148, 163, 184, 0.72);
  --sr-tree-line: var(--sr-tree-guide);
  --sr-tree-active-line: var(--sr-accent, #38bdf8);
  --sr-scrollbar-thumb: rgba(148, 163, 184, 0.38);
  --sr-scrollbar-thumb-hover: rgba(203, 213, 225, 0.62);
}

[data-sr-scheme="high_contrast_light"] {
  --sr-tree-guide: #1e293b;
}

[data-sr-scheme="high_contrast_dark"] {
  --sr-tree-guide: #f1f5f9;
}

/* =========================================================================
   1. Base UI ScrollArea (Invisible at rest, smooth overlay X & Y pills)
   ========================================================================= */
.sr-scroll-root {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.sr-scroll-viewport {
  flex: 1 1 auto;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
  overscroll-behavior: contain;
}

.sr-scroll-viewport::-webkit-scrollbar {
  display: none;
  width: 0;
  height: 0;
}

.sr-scroll-content {
  min-width: 100%;
}

.sr-scroll-fill > .sr-scroll-viewport > .sr-scroll-content {
  min-width: 100%;
  min-height: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.sr-scroll-bar {
  display: flex;
  user-select: none;
  touch-action: none;
  padding: 2px;
  border-radius: var(--sr-pill-radius);
  background: transparent;
  opacity: 0;
  pointer-events: none;
  transition: opacity 200ms ease, background-color 150ms ease;
  z-index: 12;
}

.sr-scroll-bar[data-hovering],
.sr-scroll-bar[data-scrolling] {
  opacity: 1;
  pointer-events: auto;
}

.sr-scroll-bar[data-orientation="vertical"] {
  width: 9px;
  margin: 2px 1px;
}

.sr-scroll-bar[data-orientation="horizontal"] {
  height: 9px;
  flex-direction: column;
  margin: 1px 2px;
}

.sr-scroll-thumb {
  flex: 1;
  border-radius: var(--sr-pill-radius);
  background: var(--sr-scrollbar-thumb);
  transition: background-color 140ms ease;
}

.sr-scroll-thumb:hover,
.sr-scroll-bar[data-scrolling] .sr-scroll-thumb {
  background: var(--sr-scrollbar-thumb-hover);
}

/* =========================================================================
   2. Base UI Buttons, Fields, Select, Checkbox, Switch, Radio, Slider
   ========================================================================= */
.sr-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: var(--cde-control-height, 30px);
  padding: 4px 11px;
  border-radius: var(--sr-control-radius);
  border: 1px solid var(--sr-border-default);
  background: var(--sr-surface-card);
  color: var(--sr-text-primary);
  font-size: 0.8125rem;
  font-weight: 500;
  line-height: 1.25;
  cursor: pointer;
  transition: background-color 120ms ease, border-color 120ms ease, color 120ms ease, box-shadow 120ms ease;
  user-select: none;
  white-space: nowrap;
}

.sr-btn:hover:not(:disabled):not([aria-disabled="true"]) {
  background: var(--sr-surface-hover);
}

.sr-btn:focus-visible {
  outline: none;
  box-shadow: var(--sr-focus-ring);
}

.sr-btn:disabled,
.sr-btn[aria-disabled="true"] {
  opacity: 0.52;
  cursor: not-allowed;
}

.sr-btn-primary {
  background: var(--sr-accent);
  border-color: var(--sr-accent);
  color: var(--sr-accent-fg-contrast);
  font-weight: 600;
}

.sr-btn-primary:hover:not(:disabled):not([aria-disabled="true"]) {
  background: var(--sr-accent-hover);
  border-color: var(--sr-accent-hover);
}

.sr-btn-destructive {
  background: var(--sr-danger);
  border-color: var(--sr-danger);
  color: #ffffff;
  font-weight: 600;
}

.sr-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  min-height: 28px;
  padding: 4px;
  border-radius: var(--sr-control-radius);
  border: 1px solid transparent;
  background: transparent;
  color: var(--sr-text-primary);
  cursor: pointer;
  transition: background-color 120ms ease, border-color 120ms ease, color 120ms ease;
}

.sr-icon-btn:hover:not(:disabled):not([aria-disabled="true"]) {
  background: var(--sr-surface-hover);
  border-color: var(--sr-border-subtle);
}

.sr-icon-btn[data-active="true"],
.sr-icon-btn[aria-pressed="true"] {
  background: var(--sr-surface-selected);
  border-color: var(--sr-accent);
  color: var(--sr-accent);
}

.sr-icon-btn:disabled,
.sr-icon-btn[aria-disabled="true"] {
  opacity: 0.45;
  cursor: not-allowed;
}

.sr-field {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.sr-field:hover,
.sr-field:focus-within {
  z-index: 35;
}

.sr-field-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--sr-text-secondary);
  line-height: 1.25;
}

.sr-input-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: var(--cde-control-height, 30px);
  padding: 0 9px;
  border-radius: var(--sr-control-radius);
  border: 1px solid var(--sr-border-default);
  background: var(--sr-surface-card);
  color: var(--sr-text-primary);
  transition: border-color 120ms ease, box-shadow 120ms ease;
}

.sr-input-wrap:focus-within {
  border-color: var(--sr-accent);
  box-shadow: var(--sr-focus-ring);
}

.sr-input-wrap[data-invalid="true"] {
  border-color: var(--sr-danger);
}

.sr-input-wrap[data-disabled="true"] {
  opacity: 0.56;
  cursor: not-allowed;
  background: var(--sr-surface-subtle);
}

.sr-input {
  flex: 1 1 auto;
  min-width: 0;
  width: 100%;
  border: none;
  outline: none;
  background: transparent;
  color: inherit;
  font-size: 0.8125rem;
  font-family: inherit;
  padding: 5px 0;
}

.sr-input::placeholder {
  color: var(--sr-text-muted);
  opacity: 0.72;
}

.sr-textarea {
  resize: vertical;
  min-height: 68px;
  line-height: 1.45;
}

.sr-field-help {
  font-size: 0.75rem;
  line-height: 1.42;
  margin: 0;
}

.sr-field-help:not([data-error="true"]) {
  position: absolute;
  top: calc(100% + 5px);
  left: 0;
  width: max(100%, min(280px, 82vw));
  max-width: min(420px, 88vw);
  padding: 7px 10px;
  border-radius: var(--sr-control-radius);
  border: 1px solid var(--sr-border-default);
  background: var(--sr-surface-popover, var(--sr-surface-card));
  color: var(--sr-text-primary);
  box-shadow: var(--sr-shadow-popover, 0 8px 24px rgba(15, 23, 42, 0.18));
  pointer-events: none;
  opacity: 0;
  visibility: hidden;
  transform: translateY(-2px);
  transition: opacity 120ms ease, transform 120ms ease, visibility 120ms ease;
  z-index: 50;
}

.sr-field:hover > .sr-field-help:not([data-error="true"]),
.sr-field:focus-within > .sr-field-help:not([data-error="true"]) {
  opacity: 1;
  visibility: visible;
  transform: translateY(0);
}

.sr-field:has(.sr-select-trigger[aria-expanded="true"]) > .sr-field-help:not([data-error="true"]),
.sr-field:has([role="combobox"][aria-expanded="true"]) > .sr-field-help:not([data-error="true"]) {
  opacity: 0;
  visibility: hidden;
}

.sr-field-help[data-error="true"] {
  color: var(--sr-danger);
  font-size: 0.72rem;
  line-height: 1.3;
}

/* Base UI Select */
.sr-select-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  min-height: var(--cde-control-height, 30px);
  padding: 4px 10px;
  border-radius: var(--sr-control-radius);
  border: 1px solid var(--sr-border-default);
  background: var(--sr-surface-card);
  color: var(--sr-text-primary);
  font-size: 0.8125rem;
  text-align: left;
  cursor: pointer;
}

.sr-select-trigger:focus-visible {
  outline: none;
  border-color: var(--sr-accent);
  box-shadow: var(--sr-focus-ring);
}

.sr-select-trigger[data-disabled],
.sr-select-trigger[aria-disabled="true"] {
  opacity: 0.55;
  cursor: not-allowed;
}

.sr-select-popup,
.sr-popover-popup {
  z-index: var(--cde-layer-popover, 2400);
  border-radius: var(--sr-island-radius);
  border: 1px solid var(--sr-border-default);
  background: var(--sr-surface-elevated);
  color: var(--sr-text-primary);
  box-shadow: var(--sr-popup-shadow);
  padding: 4px;
  max-height: min(360px, calc(100vh - 32px));
  overflow: auto;
}

.sr-select-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 0.8125rem;
  cursor: pointer;
  user-select: none;
}

.sr-select-item[data-highlighted] {
  background: var(--sr-surface-hover);
}

.sr-select-item[data-selected] {
  background: var(--sr-surface-selected);
  color: var(--sr-accent);
  font-weight: 600;
}

.sr-select-item[data-disabled] {
  opacity: 0.45;
  cursor: not-allowed;
}

/* Base UI Checkbox & Switch */
.sr-choice-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8125rem;
  color: var(--sr-text-primary);
  cursor: pointer;
  user-select: none;
}

.sr-choice-label[data-disabled="true"] {
  opacity: 0.52;
  cursor: not-allowed;
}

.sr-checkbox-root {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  border-radius: 4px;
  border: 1.5px solid var(--sr-border-default);
  background: var(--sr-surface-card);
  color: var(--sr-accent-fg-contrast);
  cursor: pointer;
  transition: background-color 120ms ease, border-color 120ms ease;
}

.sr-checkbox-root[data-checked],
.sr-checkbox-root[data-indeterminate] {
  background: var(--sr-accent);
  border-color: var(--sr-accent);
}

.sr-checkbox-root:focus-visible {
  outline: none;
  box-shadow: var(--sr-focus-ring);
}

.sr-switch-root {
  position: relative;
  display: inline-flex;
  align-items: center;
  width: 34px;
  height: 19px;
  padding: 2px;
  flex-shrink: 0;
  border-radius: var(--sr-pill-radius);
  border: 1px solid var(--sr-border-default);
  background: var(--sr-surface-subtle);
  cursor: pointer;
  transition: background-color 140ms ease, border-color 140ms ease;
}

.sr-switch-root[data-checked] {
  background: var(--sr-accent);
  border-color: var(--sr-accent);
}

.sr-switch-thumb {
  width: 13px;
  height: 13px;
  border-radius: 50%;
  background: #ffffff;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
  transform: translateX(0);
  transition: transform 140ms ease;
}

.sr-switch-root[data-checked] .sr-switch-thumb {
  transform: translateX(15px);
}

/* Base UI Dialog & AlertDialog */
.sr-dialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: var(--cde-layer-modal-backdrop, 2000);
  background: rgba(15, 23, 42, 0.44);
  backdrop-filter: blur(2px);
}

.sr-dialog-popup {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: var(--cde-layer-dialog, 2100);
  display: flex;
  flex-direction: column;
  max-width: calc(100vw - 40px);
  max-height: calc(100vh - 40px);
  border-radius: var(--sr-island-radius);
  border: 1px solid var(--sr-border-default);
  background: var(--sr-surface-card);
  color: var(--sr-text-primary);
  box-shadow: var(--sr-popup-shadow);
  overflow: hidden;
}

.sr-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--sr-border-subtle);
  font-size: 0.95rem;
  font-weight: 600;
}

.sr-dialog-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 16px;
}

.sr-dialog-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 10px 16px;
  border-top: 1px solid var(--sr-border-subtle);
  background: var(--sr-surface-subtle);
}

/* Base UI Slider */
.sr-slider-control {
  position: relative;
  display: flex;
  align-items: center;
  width: 100%;
  height: 20px;
  cursor: pointer;
  touch-action: none;
}

.sr-slider-track {
  position: relative;
  width: 100%;
  height: 5px;
  border-radius: var(--sr-pill-radius);
  background: var(--sr-border-default);
}

.sr-slider-indicator {
  height: 100%;
  border-radius: var(--sr-pill-radius);
  background: var(--sr-accent);
}

.sr-slider-thumb {
  width: 15px;
  height: 15px;
  border-radius: 50%;
  background: var(--sr-surface-card);
  border: 2px solid var(--sr-accent);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.22);
}

.sr-slider-thumb:focus-visible {
  outline: none;
  box-shadow: var(--sr-focus-ring);
}

/* =========================================================================
   3. ScratchBranchedTree (React Bits Branched Menu Multi-Level Hierarchy)
   ========================================================================= */
.sr-branched-tree {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  height: 100%;
  color: var(--sr-text-primary);
  font-size: 0.8125rem;
  user-select: none;
}

.sr-branched-sticky-ancestors {
  position: sticky;
  top: 0;
  z-index: 6;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  font-size: 0.72rem;
  background: var(--sr-surface-subtle);
  border-bottom: 1px solid var(--sr-border-subtle);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sr-branched-ancestor-crumb {
  border: none;
  background: transparent;
  color: var(--sr-text-secondary);
  padding: 1px 4px;
  border-radius: 4px;
  cursor: pointer;
  font-size: inherit;
}

.sr-branched-ancestor-crumb:hover {
  background: var(--sr-surface-hover);
  color: var(--sr-accent);
}

.sr-branched-canvas {
  position: relative;
  display: inline-block;
  min-width: 100%;
}

.sr-branched-svg {
  position: absolute;
  top: 0;
  left: 0;
  pointer-events: none;
  overflow: visible;
}

.sr-branched-path-structural {
  fill: none;
  stroke: var(--sr-tree-line);
  stroke-width: 2.2px;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.sr-branched-path-active {
  fill: none;
  stroke: var(--sr-tree-active-line);
  stroke-width: 2.5px;
  stroke-linecap: round;
  stroke-linejoin: round;
  transition: d 180ms ease;
}

.sr-branched-row {
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
  height: var(--sr-tree-row-height, 28px);
  padding-right: 12px;
  border-radius: 6px;
  border: none;
  box-shadow: none;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color 110ms ease, color 110ms ease;
}

.sr-branched-row:hover:not([aria-disabled="true"]) {
  background: var(--sr-surface-hover);
}

.sr-branched-row[aria-selected="true"] {
  background: var(--sr-surface-selected);
  color: var(--sr-text-primary);
  border: none;
  box-shadow: none;
  font-weight: 600;
}

.sr-branched-row:focus-visible {
  outline: none;
}

.sr-branched-expander {
  position: relative;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  padding: 0;
  border: 2px solid var(--sr-tree-guide);
  border-radius: 50%;
  background: var(--sr-surface-card);
  color: var(--sr-text-primary);
  cursor: pointer;
  flex-shrink: 0;
  transition: border-color 120ms ease, background-color 120ms ease, color 120ms ease;
}

.sr-branched-expander:hover {
  border-color: var(--sr-accent);
  color: var(--sr-accent);
}

.sr-branched-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 6px;
  border-radius: var(--sr-pill-radius);
  font-size: 0.68rem;
  font-weight: 600;
  line-height: 1.2;
  background: var(--sr-surface-subtle);
  color: var(--sr-text-secondary);
  border: 1px solid var(--sr-border-subtle);
}

.sr-branched-badge[data-delta="add"] {
  color: var(--sr-success);
  border-color: rgba(22, 163, 74, 0.35);
  background: rgba(22, 163, 74, 0.1);
}

.sr-branched-badge[data-delta="modify"] {
  color: var(--sr-warning);
  border-color: rgba(217, 119, 6, 0.35);
  background: rgba(217, 119, 6, 0.1);
}

.sr-branched-badge[data-delta="drop"] {
  color: var(--sr-danger);
  border-color: rgba(220, 38, 38, 0.35);
  background: rgba(220, 38, 38, 0.1);
}

/* =========================================================================
   4. Beautiful UI Table Suite (Records, Faceted Filter, Semantic Diff)
   ========================================================================= */
.sr-bui-card {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  border-radius: var(--sr-island-radius);
  border: 1px solid var(--sr-border-default);
  background: var(--sr-surface-card);
  color: var(--sr-text-primary);
  overflow: hidden;
}

.sr-bui-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--sr-border-subtle);
  background: var(--sr-surface-card);
}

.sr-bui-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  padding: 0 9px;
  border-radius: var(--sr-pill-radius);
  border: 1px dashed var(--sr-border-default);
  background: var(--sr-surface-subtle);
  color: var(--sr-text-secondary);
  font-size: 0.75rem;
  font-weight: 500;
  cursor: pointer;
}

.sr-bui-chip[data-active="true"] {
  border-style: solid;
  border-color: var(--sr-accent);
  background: var(--sr-surface-selected);
  color: var(--sr-accent);
}

.sr-bui-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 0.8125rem;
}

.sr-bui-th {
  position: sticky;
  top: 0;
  z-index: 3;
  padding: 8px 12px;
  text-align: left;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--sr-text-muted);
  background: var(--sr-surface-subtle);
  border-bottom: 1px solid var(--sr-border-default);
  white-space: nowrap;
  user-select: none;
}

.sr-bui-th[data-sortable="true"] {
  cursor: pointer;
}

.sr-bui-th[data-sortable="true"]:hover {
  color: var(--sr-text-primary);
}

.sr-bui-tr {
  transition: background-color 100ms ease;
}

.sr-bui-tr:hover .sr-bui-td {
  background: var(--sr-surface-hover);
}

.sr-bui-tr[data-selected="true"] .sr-bui-td,
.sr-bui-tr[data-inspected="true"] .sr-bui-td {
  background: var(--sr-surface-selected);
}

.sr-bui-tr[data-diff="add"] .sr-bui-td {
  background: rgba(22, 163, 74, 0.06);
}

.sr-bui-tr[data-diff="modify"] .sr-bui-td {
  background: rgba(217, 119, 6, 0.06);
}

.sr-bui-tr[data-diff="drop"] .sr-bui-td {
  background: rgba(220, 38, 38, 0.06);
}

.sr-bui-td {
  padding: 7px 12px;
  border-bottom: 1px solid var(--sr-border-subtle);
  vertical-align: middle;
  color: var(--sr-text-primary);
  background: transparent;
}

.sr-bui-mono {
  font-family: var(--sr-font-mono);
  font-size: 0.775rem;
}

.sr-bui-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  border-radius: var(--sr-pill-radius);
  font-size: 0.71rem;
  font-weight: 600;
  border: 1px solid var(--sr-border-subtle);
  background: var(--sr-surface-subtle);
  color: var(--sr-text-secondary);
}

.sr-bui-pill[data-tone="success"] {
  color: var(--sr-success);
  border-color: rgba(22, 163, 74, 0.32);
  background: rgba(22, 163, 74, 0.1);
}

.sr-bui-pill[data-tone="warning"] {
  color: var(--sr-warning);
  border-color: rgba(217, 119, 6, 0.32);
  background: rgba(217, 119, 6, 0.1);
}

.sr-bui-pill[data-tone="danger"],
.sr-bui-pill[data-tone="error"] {
  color: var(--sr-danger);
  border-color: rgba(220, 38, 38, 0.32);
  background: rgba(220, 38, 38, 0.1);
}

.sr-bui-pill[data-tone="info"] {
  color: var(--sr-info);
  border-color: rgba(2, 132, 199, 0.32);
  background: rgba(2, 132, 199, 0.1);
}

.sr-bui-row-actions {
  opacity: 0;
  transition: opacity 120ms ease;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.sr-bui-tr:hover .sr-bui-row-actions,
.sr-bui-tr:focus-within .sr-bui-row-actions {
  opacity: 1;
}

.sr-bui-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  padding: 7px 12px;
  font-size: 0.76rem;
  color: var(--sr-text-secondary);
  background: var(--sr-surface-subtle);
  border-top: 1px solid var(--sr-border-subtle);
}

/* =========================================================================
   7. PgTree / FileTreeX Auto-Hiding Scrollbars & Branched Active Pill
   ========================================================================= */
.file-tree > div > div {
  scrollbar-width: thin;
  scrollbar-color: transparent transparent;
  transition: scrollbar-color 180ms ease;
}

.file-tree:hover > div > div,
.file-tree:focus-within > div > div {
  scrollbar-color: var(--sr-scrollbar-thumb) transparent;
}

.file-tree > div > div::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.file-tree > div > div::-webkit-scrollbar-track {
  background: transparent;
}

.file-tree > div > div::-webkit-scrollbar-thumb {
  background: transparent;
  border-radius: var(--sr-pill-radius);
}

.file-tree:hover > div > div::-webkit-scrollbar-thumb,
.file-tree:focus-within > div > div::-webkit-scrollbar-thumb {
  background: var(--sr-scrollbar-thumb);
}

.file-tree .file-entry {
  border-radius: 6px;
  transition: background-color 110ms ease, color 110ms ease;
}

.file-tree .file-entry.active {
  background: var(--sr-surface-selected);
  border: none !important;
  box-shadow: none !important;
  outline: none !important;
  font-weight: 600;
}

/* =========================================================================
   8. Beautiful UI Harmonization for PgReactTable & DataGrid Surfaces
   ========================================================================= */
.pgrt {
  scrollbar-width: thin;
  scrollbar-color: transparent transparent;
  transition: scrollbar-color 180ms ease;
  border-radius: var(--sr-island-radius);
}

.pgrt:hover,
.pgrt:focus-within {
  scrollbar-color: var(--sr-scrollbar-thumb) transparent;
}

.pgrt .pgrt-table {
  border-radius: var(--sr-island-radius);
  background: var(--sr-surface-card);
}

.pgrt .pgrt-header-row .pgrt-header-cell {
  background: var(--sr-surface-subtle) !important;
  color: var(--sr-text-secondary) !important;
  font-size: 0.74rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.025em;
  border-bottom: 1px solid var(--sr-border-default) !important;
  border-right: 1px solid var(--sr-border-subtle) !important;
}

.pgrt .pgrt-row-content:hover .pgrd-row-cell {
  background: var(--sr-surface-hover) !important;
}

.pgrt .pgrd-row-cell {
  border-bottom: 1px solid var(--sr-border-subtle) !important;
  border-right: 1px solid transparent !important;
  font-size: 0.8125rem;
}
`;

export function ensureScratchDomCompat(win = typeof window !== 'undefined' ? window : null) {
  if (!win) return;
  if (typeof win.PointerEvent === 'undefined' && typeof win.MouseEvent === 'function') {
    class CompatPointerEvent extends win.MouseEvent {
      constructor(type, params = {}) {
        super(type, params);
        this.pointerId = params.pointerId ?? 0;
        this.pointerType = params.pointerType ?? '';
      }
    }
    win.PointerEvent = CompatPointerEvent;
  }
  if (win.Element && typeof win.Element.prototype.getAnimations !== 'function') {
    win.Element.prototype.getAnimations = () => [];
  }
}

ensureScratchDomCompat();

export function ensureScratchBaseStyles(doc = typeof document !== 'undefined' ? document : null) {
  ensureScratchDomCompat(doc?.defaultView || (typeof window !== 'undefined' ? window : null));
  if (!doc?.head) return;
  if (doc.getElementById(STYLE_ELEMENT_ID)) return;
  const style = doc.createElement('style');
  style.id = STYLE_ELEMENT_ID;
  style.textContent = SCRATCH_BASE_UI_CSS;
  doc.head.appendChild(style);
}
