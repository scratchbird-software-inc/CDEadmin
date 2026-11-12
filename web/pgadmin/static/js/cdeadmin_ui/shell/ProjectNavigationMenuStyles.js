/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useInsertionEffect} from 'react';

const STYLE_ELEMENT_ID = 'sr-base-ui-navigation-menu-styles';

/**
 * Base UI NavigationMenu stylesheet for ScratchRobin Area 1 (Main Menu).
 * Follows https://base-ui.com/react/components/navigation-menu anatomy,
 * CSS custom properties (`--positioner-width`, `--positioner-height`,
 * `--popup-width`, `--popup-height`, `--transform-origin`, `--available-height`),
 * and state attributes (`[data-popup-open]`, `[data-open]`, `[data-closed]`,
 * `[data-starting-style]`, `[data-ending-style]`, `[data-activation-direction]`,
 * `[data-instant]`).
 */
export const PROJECT_NAVIGATION_MENU_CSS = `
.sr-nav-bar,
.sr-nav-positioner {
  --sr-nav-bg: var(--sr-scheme-nav-bg, #ffffff);
  --sr-nav-fg: var(--sr-scheme-fg, #111827);
  --sr-nav-muted: var(--sr-scheme-muted, #64748b);
  --sr-nav-border: var(--sr-scheme-border, #e2e8f0);
  --sr-nav-hover-bg: var(--sr-scheme-selection, #f1f5f9);
  --sr-nav-active-bg: var(--sr-scheme-selection, #e8eef6);
  --sr-nav-accent: var(--sr-scheme-accent, #0f62fe);
  --sr-nav-accent-soft: rgba(15, 98, 254, 0.1);
  --sr-nav-popup-bg: var(--sr-scheme-island-bg, #ffffff);
  --sr-nav-popup-border: var(--sr-scheme-border, #dbe3ee);
  --sr-nav-popup-shadow:
    0 14px 32px -8px rgba(15, 23, 42, 0.16),
    0 4px 12px -2px rgba(15, 23, 42, 0.08);
  --sr-nav-icon-bg: var(--sr-scheme-drawer-bg, #f1f5f9);
  --sr-nav-icon-fg: var(--sr-scheme-fg, #1e293b);
  --sr-nav-kbd-bg: var(--sr-scheme-drawer-bg, #f8fafc);
  --sr-nav-kbd-border: var(--sr-scheme-border, #cbd5e1);
  --sr-nav-divider: var(--sr-scheme-border, #e2e8f0);
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

.sr-nav-bar[data-tone="dark"],
.sr-nav-positioner[data-tone="dark"] {
  --sr-nav-bg: var(--sr-scheme-nav-bg, #141923);
  --sr-nav-fg: var(--sr-scheme-fg, #f1f5f9);
  --sr-nav-muted: var(--sr-scheme-muted, #94a3b8);
  --sr-nav-border: var(--sr-scheme-border, #263042);
  --sr-nav-hover-bg: var(--sr-scheme-selection, #1e2636);
  --sr-nav-active-bg: var(--sr-scheme-selection, #263248);
  --sr-nav-accent: var(--sr-scheme-accent, #60a5fa);
  --sr-nav-accent-soft: rgba(96, 165, 250, 0.16);
  --sr-nav-popup-bg: var(--sr-scheme-island-bg, #18202e);
  --sr-nav-popup-border: var(--sr-scheme-border, #2d3a50);
  --sr-nav-popup-shadow:
    0 18px 38px -8px rgba(0, 0, 0, 0.55),
    0 6px 16px -4px rgba(0, 0, 0, 0.38);
  --sr-nav-icon-bg: var(--sr-scheme-drawer-bg, #222c3f);
  --sr-nav-icon-fg: var(--sr-scheme-fg, #e2e8f0);
  --sr-nav-kbd-bg: var(--sr-scheme-backdrop-a, #111722);
  --sr-nav-kbd-border: var(--sr-scheme-border, #334155);
  --sr-nav-divider: var(--sr-scheme-border, #283449);
}

.sr-nav-bar {
  box-sizing: border-box;
  min-height: calc(var(--cde-menu-row-height, 38px) * var(--sr-area1-zoom, 1));
  padding: 3px 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  background-color: var(--sr-nav-bg);
  color: var(--sr-nav-fg);
  border-bottom: 1px solid var(--sr-nav-border);
  font-size: calc(var(--cde-menu-font-size, 0.875rem) * var(--sr-area1-zoom, 1));
  position: relative;
  z-index: 1200;
  user-select: none;
}

.sr-nav-root {
  display: flex;
  align-items: center;
  min-width: 0;
}

.sr-nav-root--main {
  flex: 1 1 auto;
}

.sr-nav-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  align-items: center;
  gap: 3px;
  flex-wrap: wrap;
}

.sr-nav-item {
  display: inline-flex;
  align-items: center;
  position: relative;
}

/* System Icon (Index 0) */
.sr-nav-system-btn {
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 30px;
  padding: 0;
  margin-right: 2px;
  border: 1px solid var(--sr-nav-border);
  border-radius: 7px;
  background-color: var(--sr-nav-icon-bg);
  color: var(--sr-nav-fg);
  cursor: pointer;
  transition: background-color 140ms ease, border-color 140ms ease, transform 120ms ease;
}

.sr-nav-system-btn:hover {
  background-color: var(--sr-nav-active-bg);
  border-color: var(--sr-nav-accent);
}

.sr-nav-system-btn:focus-visible {
  outline: 2px solid var(--sr-nav-accent);
  outline-offset: 1px;
}

/* Base UI NavigationMenu Trigger */
.sr-nav-trigger {
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  height: 30px;
  padding: 0 10px;
  margin: 0;
  border: 1px solid transparent;
  border-radius: 6px;
  background-color: transparent;
  color: var(--sr-nav-fg);
  font-family: inherit;
  font-size: var(--cde-menu-font-size, 0.84375rem);
  font-weight: 500;
  line-height: 1;
  letter-spacing: -0.005em;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color 140ms ease, color 140ms ease, border-color 140ms ease;
}

.sr-nav-trigger:hover {
  background-color: var(--sr-nav-hover-bg);
}

.sr-nav-trigger[data-popup-open] {
  background-color: var(--sr-nav-active-bg);
  color: var(--sr-nav-fg);
}

.sr-nav-trigger:focus-visible {
  outline: 2px solid var(--sr-nav-accent);
  outline-offset: 1px;
}

.sr-nav-trigger--utility {
  height: 28px;
  padding: 0 9px;
  font-size: 0.78125rem;
  font-weight: 600;
  border-color: var(--sr-nav-border);
  background-color: var(--sr-nav-icon-bg);
}

.sr-nav-trigger--utility:hover {
  background-color: var(--sr-nav-hover-bg);
  border-color: var(--sr-nav-muted);
}

.sr-nav-chevron {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--sr-nav-muted);
  transition: transform 200ms cubic-bezier(0.22, 1, 0.36, 1);
}

.sr-nav-chevron[data-popup-open],
.sr-nav-trigger[data-popup-open] .sr-nav-chevron {
  transform: rotate(180deg);
  color: var(--sr-nav-fg);
}

/* Right-aligned Utility Controls */
.sr-nav-utilities {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.sr-nav-tone-btn {
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--sr-nav-border);
  border-radius: 6px;
  background-color: var(--sr-nav-icon-bg);
  color: var(--sr-nav-fg);
  font-family: inherit;
  font-size: 0.78125rem;
  font-weight: 600;
  line-height: 1;
  cursor: pointer;
  transition: background-color 140ms ease, border-color 140ms ease;
}

.sr-nav-tone-btn:hover {
  background-color: var(--sr-nav-hover-bg);
  border-color: var(--sr-nav-muted);
}

.sr-nav-tone-btn:focus-visible {
  outline: 2px solid var(--sr-nav-accent);
  outline-offset: 1px;
}

/* Base UI Positioner, Popup, Arrow & Viewport */
.sr-nav-positioner {
  box-sizing: border-box;
  width: var(--positioner-width);
  height: var(--positioner-height);
  max-width: var(--available-width);
  z-index: 1500;
  transition-property: top, left, right, bottom, width, height;
  transition-duration: 240ms;
  transition-timing-function: cubic-bezier(0.22, 1, 0.36, 1);
}

.sr-nav-positioner[data-instant] {
  transition: none;
}

.sr-nav-popup {
  position: relative;
  box-sizing: border-box;
  width: var(--popup-width, auto);
  height: var(--popup-height, auto);
  border-radius: 10px;
  background-color: var(--sr-nav-popup-bg);
  color: var(--sr-nav-fg);
  border: 1px solid var(--sr-nav-popup-border);
  box-shadow: var(--sr-nav-popup-shadow);
  transform-origin: var(--transform-origin);
  transition-property: opacity, transform, width, height;
  transition-duration: 220ms;
  transition-timing-function: cubic-bezier(0.22, 1, 0.36, 1);
}

.sr-nav-popup[data-starting-style],
.sr-nav-popup[data-ending-style] {
  opacity: 0;
  transform: scale(0.95);
}

.sr-nav-popup[data-ending-style] {
  transition-duration: 150ms;
  transition-timing-function: ease;
}

.sr-nav-viewport {
  position: relative;
  overflow: hidden;
  width: 100%;
  height: 100%;
  border-radius: 9px;
}

.sr-nav-arrow {
  display: flex;
  transition: left 240ms cubic-bezier(0.22, 1, 0.36, 1);
}

.sr-nav-arrow[data-side="bottom"] {
  top: -8px;
}

.sr-nav-arrow[data-side="top"] {
  bottom: -8px;
  transform: rotate(180deg);
}

.sr-nav-arrow-fill {
  fill: var(--sr-nav-popup-bg);
}

.sr-nav-arrow-stroke {
  fill: var(--sr-nav-popup-border);
}

/* Base UI NavigationMenu Content */
.sr-nav-content {
  box-sizing: border-box;
  padding: 8px;
  min-width: 280px;
  max-width: min(640px, calc(100vw - 32px));
  max-height: min(74vh, var(--available-height, 560px));
  overflow-y: auto;
  transition:
    opacity 180ms cubic-bezier(0.22, 1, 0.36, 1),
    transform 180ms cubic-bezier(0.22, 1, 0.36, 1);
}

.sr-nav-content--compact {
  min-width: 210px;
  padding: 6px;
}

.sr-nav-content[data-starting-style],
.sr-nav-content[data-ending-style] {
  opacity: 0;
}

.sr-nav-content[data-starting-style][data-activation-direction="left"] {
  transform: translateX(-18px);
}

.sr-nav-content[data-starting-style][data-activation-direction="right"] {
  transform: translateX(18px);
}

.sr-nav-content[data-ending-style][data-activation-direction="left"] {
  transform: translateX(18px);
}

.sr-nav-content[data-ending-style][data-activation-direction="right"] {
  transform: translateX(-18px);
}

.sr-nav-section-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sr-nav-section-grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(230px, 1fr));
  gap: 4px;
}

@media (max-width: 620px) {
  .sr-nav-section-grid {
    grid-template-columns: 1fr;
  }
}

.sr-nav-separator {
  height: 1px;
  margin: 5px 4px;
  background-color: var(--sr-nav-divider);
  grid-column: 1 / -1;
}

.sr-nav-heading {
  padding: 4px 10px 6px;
  font-size: 0.6875rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--sr-nav-muted);
}

/* Base UI NavigationMenu Link Card / Menu Row */
.sr-nav-card-link {
  box-sizing: border-box;
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: var(--sr-nav-fg);
  font-family: inherit;
  text-align: left;
  text-decoration: none;
  cursor: pointer;
  transition: background-color 120ms ease, border-color 120ms ease;
}

.sr-nav-card-link--compact {
  align-items: center;
  padding: 6px 10px;
}

.sr-nav-card-link:hover:not(:disabled) {
  background-color: var(--sr-nav-hover-bg);
}

.sr-nav-card-link:focus-visible {
  outline: 2px solid var(--sr-nav-accent);
  outline-offset: -2px;
  background-color: var(--sr-nav-hover-bg);
}

.sr-nav-card-link[data-checked="true"] {
  background-color: var(--sr-nav-accent-soft);
}

.sr-nav-card-link:disabled {
  opacity: 0.44;
  cursor: not-allowed;
}

.sr-nav-card-icon {
  box-sizing: border-box;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background-color: var(--sr-nav-icon-bg);
  color: var(--sr-nav-icon-fg);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 1px;
}

.sr-nav-card-link--compact .sr-nav-card-icon {
  width: 22px;
  height: 22px;
  margin-top: 0;
}

.sr-nav-card-body {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sr-nav-card-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.sr-nav-card-title {
  font-size: 0.84375rem;
  font-weight: 500;
  line-height: 1.25;
  color: var(--sr-nav-fg);
}

.sr-nav-card-desc {
  font-size: 0.75rem;
  line-height: 1.35;
  color: var(--sr-nav-muted);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.sr-nav-card-meta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  padding-left: 8px;
  flex-shrink: 0;
}

.sr-nav-check-badge {
  width: 18px;
  height: 18px;
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--sr-nav-accent);
}

.sr-nav-shortcut {
  padding: 1px 5px;
  border-radius: 4px;
  border: 1px solid var(--sr-nav-kbd-border);
  background-color: var(--sr-nav-kbd-bg);
  color: var(--sr-nav-muted);
  font-size: 0.6875rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.sr-nav-submenu-children {
  margin: 4px 0 4px 20px;
  padding-left: 8px;
  border-left: 2px solid var(--sr-nav-divider);
}
`;

export function useProjectNavigationMenuStyles() {
  useInsertionEffect(() => {
    if (typeof document === 'undefined') return;
    if (document.getElementById(STYLE_ELEMENT_ID)) return;
    const styleEl = document.createElement('style');
    styleEl.id = STYLE_ELEMENT_ID;
    styleEl.textContent = PROJECT_NAVIGATION_MENU_CSS;
    document.head.appendChild(styleEl);
  }, []);
}
