/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useInsertionEffect} from 'react';

const STYLE_ELEMENT_ID = 'sr-vertical-dock-styles';

/**
 * Clean-room PostgreSQL-licensed Vertical Rightward-Expanding Dock stylesheet
 * for ScratchRobin Area 2 (Side Menu Application Launcher).
 *
 * Matches the light/dark surface palette of `ProjectNavigationMenuStyles.js`
 * while keeping the Area 2 layout footprint fixed (`52px`) and allowing
 * hovered icons, floating right-side labels, and the bottom-aligned Settings
 * popup to expand smoothly to the right without shifting Area 3.
 */
export const PROJECT_VERTICAL_DOCK_CSS = `
.sr-vdock-rail {
  --sr-vdock-bg: var(--sr-scheme-vdock-bg, #f8fafc);
  --sr-vdock-fg: var(--sr-scheme-fg, #0f172a);
  --sr-vdock-muted: var(--sr-scheme-muted, #64748b);
  --sr-vdock-border: var(--sr-scheme-border, #e2e8f0);
  --sr-vdock-tile-bg: var(--sr-scheme-island-bg, #ffffff);
  --sr-vdock-tile-border: var(--sr-scheme-border, #dbe3ee);
  --sr-vdock-tile-hover-bg: var(--sr-scheme-island-bg, #ffffff);
  --sr-vdock-tile-hover-border: var(--sr-scheme-accent, #93c5fd);
  --sr-vdock-tile-active-bg: var(--sr-scheme-selection, #eff6ff);
  --sr-vdock-tile-active-border: var(--sr-scheme-accent, #2563eb);
  --sr-vdock-tile-active-fg: var(--sr-scheme-accent, #1d4ed8);
  --sr-vdock-accent: var(--sr-scheme-accent, #0f62fe);
  --sr-vdock-shadow-rest: 0 1px 2px rgba(15, 23, 42, 0.06);
  --sr-vdock-shadow-hover:
    0 14px 28px -6px rgba(15, 23, 42, 0.2),
    0 4px 10px -2px rgba(15, 23, 42, 0.1);
  --sr-vdock-tooltip-bg: #0f172a;
  --sr-vdock-tooltip-fg: #f8fafc;
  --sr-vdock-tooltip-border: #1e293b;
  --sr-vdock-popup-bg: var(--sr-scheme-island-bg, #ffffff);
  --sr-vdock-popup-border: var(--sr-scheme-border, #dbe3ee);

  box-sizing: border-box;
  width: var(--sr-vdock-rail-width, var(--cde-activity-bar-width, 52px));
  flex: 0 0 var(--sr-vdock-rail-width, var(--cde-activity-bar-width, 52px));
  min-height: 0;
  padding: 8px 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  background-color: var(--sr-vdock-bg);
  color: var(--sr-vdock-fg);
  border: 1px solid var(--sr-island-border, var(--sr-vdock-border));
  border-radius: var(--sr-island-radius, 12px);
  box-shadow: var(--sr-island-shadow, none);
  position: relative;
  z-index: 1150;
  overflow: visible;
  user-select: none;
  font-family: var(
    --sr-font-ui,
    var(
      --cde-font-sans,
      -apple-system,
      BlinkMacSystemFont,
      "Inter",
      "Segoe UI",
      Roboto,
      sans-serif
    )
  );
}

.sr-vdock-rail[data-tone="dark"] {
  --sr-vdock-bg: var(--sr-scheme-vdock-bg, #111620);
  --sr-vdock-fg: var(--sr-scheme-fg, #f1f5f9);
  --sr-vdock-muted: var(--sr-scheme-muted, #94a3b8);
  --sr-vdock-border: var(--sr-scheme-border, #263042);
  --sr-vdock-tile-bg: var(--sr-scheme-island-bg, #18202e);
  --sr-vdock-tile-border: var(--sr-scheme-border, #2b374c);
  --sr-vdock-tile-hover-bg: var(--sr-scheme-selection, #1f2a3d);
  --sr-vdock-tile-hover-border: var(--sr-scheme-accent, #60a5fa);
  --sr-vdock-tile-active-bg: var(--sr-scheme-selection, #1e2f4d);
  --sr-vdock-tile-active-border: var(--sr-scheme-accent, #60a5fa);
  --sr-vdock-tile-active-fg: var(--sr-scheme-accent, #93c5fd);
  --sr-vdock-accent: var(--sr-scheme-accent, #60a5fa);
  --sr-vdock-shadow-rest: 0 1px 3px rgba(0, 0, 0, 0.3);
  --sr-vdock-shadow-hover:
    0 16px 32px -6px rgba(0, 0, 0, 0.6),
    0 6px 14px -3px rgba(0, 0, 0, 0.42);
  --sr-vdock-tooltip-bg: #1e293b;
  --sr-vdock-tooltip-fg: #f8fafc;
  --sr-vdock-tooltip-border: #334155;
  --sr-vdock-popup-bg: var(--sr-scheme-island-bg, #18202e);
  --sr-vdock-popup-border: var(--sr-scheme-border, #2d3a50);
}

.sr-vdock-zone {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  overflow: visible;
  position: relative;
}

.sr-vdock-zone--top {
  flex: 0 0 auto;
}

.sr-vdock-zone--apps {
  flex: 1 1 auto;
  min-height: 0;
  gap: 5px;
  padding: 2px 0;
  overflow: visible;
}

.sr-vdock-zone--bottom {
  margin-top: auto;
  flex: 0 0 auto;
  justify-content: flex-end;
}

.sr-vdock-divider {
  width: 34px;
  height: 1px;
  margin: 7px 0 7px 9px;
  background-color: var(--sr-vdock-border);
  flex: 0 0 auto;
}

/* Slot wrapper keeps layout left-anchored while allowing rightward expansion */
.sr-vdock-slot {
  position: relative;
  width: 100%;
  display: flex;
  padding-left: 8px;
  box-sizing: border-box;
  overflow: visible;
  transition: height 170ms cubic-bezier(0.22, 1.18, 0.36, 1);
}

.sr-vdock-slot[data-anchor="top"] {
  align-items: flex-start;
}

.sr-vdock-slot[data-anchor="middle"] {
  align-items: center;
}

.sr-vdock-slot[data-anchor="bottom"] {
  align-items: flex-end;
}

/* Magnifying Dock Tile Button (expands rightward from its left anchor) */
.sr-vdock-btn {
  box-sizing: border-box;
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  margin: 0;
  flex: 0 0 auto;
  border-radius: 10px;
  border: 1px solid var(--sr-vdock-tile-border);
  background-color: var(--sr-vdock-tile-bg);
  color: var(--sr-vdock-fg);
  box-shadow: var(--sr-vdock-shadow-rest);
  cursor: pointer;
  transform-origin: left center;
  will-change: width, height, transform;
  transition:
    width 170ms cubic-bezier(0.22, 1.2, 0.36, 1),
    height 170ms cubic-bezier(0.22, 1.2, 0.36, 1),
    transform 170ms cubic-bezier(0.22, 1.2, 0.36, 1),
    background-color 140ms ease,
    border-color 140ms ease,
    color 140ms ease,
    box-shadow 160ms ease;
}

.sr-vdock-slot[data-anchor="top"] .sr-vdock-btn {
  transform-origin: left top;
}

.sr-vdock-slot[data-anchor="bottom"] .sr-vdock-btn {
  transform-origin: left bottom;
}

.sr-vdock-btn[data-magnified="true"] {
  background-color: var(--sr-vdock-tile-hover-bg);
  border-color: var(--sr-vdock-tile-hover-border);
  box-shadow: var(--sr-vdock-shadow-hover);
  z-index: 20;
}

.sr-vdock-btn[data-active="true"] {
  background-color: var(--sr-vdock-tile-active-bg);
  border-color: var(--sr-vdock-tile-active-border);
  color: var(--sr-vdock-tile-active-fg);
}

.sr-vdock-btn:focus-visible {
  outline: 2px solid var(--sr-vdock-accent);
  outline-offset: 2px;
}

.sr-vdock-btn:disabled,
.sr-vdock-btn[data-disabled="true"] {
  cursor: not-allowed;
  color: var(--sr-vdock-muted);
  opacity: 0.55;
}

.sr-vdock-icon-wrap {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  will-change: width, height;
  transition:
    width 170ms cubic-bezier(0.22, 1.2, 0.36, 1),
    height 170ms cubic-bezier(0.22, 1.2, 0.36, 1);
}

@media (prefers-reduced-motion: reduce) {
  .sr-vdock-slot,
  .sr-vdock-btn,
  .sr-vdock-icon-wrap,
  .sr-vdock-tooltip {
    transition: none !important;
  }
}

/* Floating Rightward Label Pill (appears to the right of the magnified tile) */
.sr-vdock-tooltip {
  position: absolute;
  top: 50%;
  padding: 5px 10px;
  border-radius: 7px;
  background-color: var(--sr-vdock-tooltip-bg);
  color: var(--sr-vdock-tooltip-fg);
  border: 1px solid var(--sr-vdock-tooltip-border);
  box-shadow: var(--sr-vdock-shadow-hover);
  font-size: calc(0.78125rem * var(--sr-vdock-zoom, 1));
  font-weight: 500;
  line-height: 1.2;
  white-space: nowrap;
  pointer-events: none;
  z-index: 40;
  opacity: 0;
  transform: translate3d(-4px, -50%, 0);
  transition: opacity 130ms ease, transform 150ms cubic-bezier(0.22, 1, 0.36, 1);
}

.sr-vdock-slot[data-anchor="bottom"] .sr-vdock-tooltip {
  top: auto;
  bottom: 8px;
  transform: translate3d(-4px, 0, 0);
}

.sr-vdock-tooltip[data-visible="true"] {
  opacity: 1;
  transform: translate3d(0, -50%, 0);
}

.sr-vdock-slot[data-anchor="bottom"] .sr-vdock-tooltip[data-visible="true"] {
  transform: translate3d(0, 0, 0);
}

/* Bottom-Aligned Settings Gear Popup (Base UI card styling) */
.sr-vdock-settings-popup {
  position: absolute;
  left: calc(100% + 14px);
  bottom: 0;
  min-width: 224px;
  padding: 6px;
  border-radius: 10px;
  background-color: var(--sr-vdock-popup-bg);
  color: var(--sr-vdock-fg);
  border: 1px solid var(--sr-vdock-popup-border);
  box-shadow: var(--sr-vdock-shadow-hover);
  z-index: 1500;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sr-vdock-settings-item {
  box-sizing: border-box;
  width: 100%;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 7px 10px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--sr-vdock-fg);
  font-family: inherit;
  font-size: 0.84375rem;
  font-weight: 500;
  text-align: left;
  cursor: pointer;
  transition: background-color 120ms ease;
}

.sr-vdock-settings-item:hover:not(:disabled) {
  background-color: rgba(148, 163, 184, 0.16);
}

.sr-vdock-settings-item:focus-visible {
  outline: 2px solid var(--sr-vdock-accent);
  outline-offset: -2px;
}

.sr-vdock-settings-item:disabled {
  opacity: 0.44;
  cursor: not-allowed;
}
`;

export function useProjectVerticalDockStyles() {
  useInsertionEffect(() => {
    if (typeof document === 'undefined') return;
    if (document.getElementById(STYLE_ELEMENT_ID)) return;
    const styleEl = document.createElement('style');
    styleEl.id = STYLE_ELEMENT_ID;
    styleEl.textContent = PROJECT_VERTICAL_DOCK_CSS;
    document.head.appendChild(styleEl);
  }, []);
}
