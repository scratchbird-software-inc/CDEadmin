/////////////////////////////////////////////////////////////
//
// ScratchRobin — Colour Schemes & Typography Runtime Authority
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import usePreferences from '../../../../preferences/static/js/store';
import {previewAppearance} from '../foundations/presentation';

export const COLOR_SCHEMES_STORAGE_KEY = 'scratchrobin.appearance.schemes_and_fonts.v1';
export const COLOR_SCHEME_CHANGED_EVENT = 'scratchrobin:scheme-changed';

export const BUILTIN_COLOR_SCHEMES = Object.freeze([
  Object.freeze({
    id: 'light',
    label: 'ScratchRobin Light',
    description: 'Crisp ice-blue backdrop with clean white islands and cobalt accents.',
    builtin: true,
    baseTone: 'light',
    backdropA: '#dce6f2',
    stripB: '#e7eef8',
    tabInactiveBg: '#dbe5f3',
    islandBg: '#ffffff',
    drawerBg: '#f8fafc',
    navBg: '#ffffff',
    vdockBg: '#f8fafc',
    fg: '#0f172a',
    muted: '#52637a',
    border: '#b8c7dc',
    accent: '#0f62fe',
    selection: '#dbeafe',
    success: '#15803d',
    warning: '#b45309',
    error: '#b91c1c',
  }),
  Object.freeze({
    id: 'dark',
    label: 'ScratchRobin Dark',
    description: 'Deep navy-slate backdrop with elevated midnight islands and sky accents.',
    builtin: true,
    baseTone: 'dark',
    backdropA: '#0a0f18',
    stripB: '#101724',
    tabInactiveBg: '#141e30',
    islandBg: '#172030',
    drawerBg: '#141c2b',
    navBg: '#141923',
    vdockBg: '#111620',
    fg: '#f1f5f9',
    muted: '#94a3b8',
    border: '#2c3a50',
    accent: '#60a5fa',
    selection: '#1e3a5f',
    success: '#4ade80',
    warning: '#fbbf24',
    error: '#f87171',
  }),
  Object.freeze({
    id: 'high_contrast_light',
    label: 'High Contrast Light',
    description: 'Maximum legibility pure black-on-white surfaces with strong borders.',
    builtin: true,
    baseTone: 'light',
    backdropA: '#e5e7eb',
    stripB: '#f3f4f6',
    tabInactiveBg: '#e5e7eb',
    islandBg: '#ffffff',
    drawerBg: '#ffffff',
    navBg: '#ffffff',
    vdockBg: '#ffffff',
    fg: '#000000',
    muted: '#262626',
    border: '#000000',
    accent: '#003e73',
    selection: '#bde3ff',
    success: '#006b2d',
    warning: '#8a4b00',
    error: '#b00020',
  }),
  Object.freeze({
    id: 'high_contrast_dark',
    label: 'High Contrast Dark',
    description: 'Pure pitch-black canvas with bright white borders and warm gold focus.',
    builtin: true,
    baseTone: 'dark',
    backdropA: '#000000',
    stripB: '#0d0d0d',
    tabInactiveBg: '#171717',
    islandBg: '#0a0a0a',
    drawerBg: '#111111',
    navBg: '#050505',
    vdockBg: '#080808',
    fg: '#ffffff',
    muted: '#e5e5e5',
    border: '#ffffff',
    accent: '#ffd740',
    selection: '#164e78',
    success: '#6dff8b',
    warning: '#ffd166',
    error: '#ff808f',
  }),
  Object.freeze({
    id: 'nord_light',
    label: 'Nordic Frost',
    description: 'Cool Scandinavian snow storm palette with calm glacier-blue highlights.',
    builtin: true,
    baseTone: 'light',
    backdropA: '#d8dee9',
    stripB: '#e5e9f0',
    tabInactiveBg: '#d8dee9',
    islandBg: '#eceff4',
    drawerBg: '#e5e9f0',
    navBg: '#eceff4',
    vdockBg: '#e5e9f0',
    fg: '#2e3440',
    muted: '#4c566a',
    border: '#b8c2d4',
    accent: '#5e81ac',
    selection: '#cfe0f2',
    success: '#4f7f52',
    warning: '#b4690e',
    error: '#bf616a',
  }),
  Object.freeze({
    id: 'nord_dark',
    label: 'Nordic Aurora',
    description: 'Polar night slate surfaces paired with soft frost-cyan accents.',
    builtin: true,
    baseTone: 'dark',
    backdropA: '#242933',
    stripB: '#2e3440',
    tabInactiveBg: '#333a47',
    islandBg: '#3b4252',
    drawerBg: '#323846',
    navBg: '#2e3440',
    vdockBg: '#292e39',
    fg: '#eceff4',
    muted: '#d8dee9',
    border: '#4c566a',
    accent: '#88c0d0',
    selection: '#434c5e',
    success: '#a3be8c',
    warning: '#ebcb8b',
    error: '#bf616a',
  }),
  Object.freeze({
    id: 'solarized_light',
    label: 'Solarized Parchment',
    description: 'Warm low-glare daylight paper palette tuned for long modelling sessions.',
    builtin: true,
    baseTone: 'light',
    backdropA: '#eee8d5',
    stripB: '#f5efdc',
    tabInactiveBg: '#e9e2cc',
    islandBg: '#fdf6e3',
    drawerBg: '#f7f0dd',
    navBg: '#fdf6e3',
    vdockBg: '#f5efdc',
    fg: '#073642',
    muted: '#586e75',
    border: '#d3cbb7',
    accent: '#268bd2',
    selection: '#e2ecf3',
    success: '#5b8700',
    warning: '#b58900',
    error: '#dc322f',
  }),
  Object.freeze({
    id: 'solarized_dark',
    label: 'Solarized Deep',
    description: 'Deep oceanic teal-slate surfaces with balanced cyan and amber contrast.',
    builtin: true,
    baseTone: 'dark',
    backdropA: '#001e26',
    stripB: '#002731',
    tabInactiveBg: '#04313d',
    islandBg: '#002b36',
    drawerBg: '#073642',
    navBg: '#00252f',
    vdockBg: '#00212b',
    fg: '#fdf6e3',
    muted: '#93a1a1',
    border: '#194b57',
    accent: '#2aa198',
    selection: '#0d4756',
    success: '#859900',
    warning: '#b58900',
    error: '#dc322f',
  }),
  Object.freeze({
    id: 'forest_dark',
    label: 'Emerald Slate',
    description: 'Rich pine-charcoal studio surfaces with crisp emerald highlights.',
    builtin: true,
    baseTone: 'dark',
    backdropA: '#091410',
    stripB: '#0f1f19',
    tabInactiveBg: '#142921',
    islandBg: '#13241d',
    drawerBg: '#0f1d17',
    navBg: '#0d1914',
    vdockBg: '#0c1713',
    fg: '#ecfdf5',
    muted: '#9ca3af',
    border: '#234236',
    accent: '#34d399',
    selection: '#183d2f',
    success: '#4ade80',
    warning: '#fbbf24',
    error: '#f87171',
  }),
  Object.freeze({
    id: 'graphite_dark',
    label: 'Graphite Studio',
    description: 'Neutral carbon-grey engineering workbench with indigo focus rings.',
    builtin: true,
    baseTone: 'dark',
    backdropA: '#111113',
    stripB: '#18181b',
    tabInactiveBg: '#202024',
    islandBg: '#1f1f23',
    drawerBg: '#18181b',
    navBg: '#141417',
    vdockBg: '#141417',
    fg: '#fafafa',
    muted: '#a1a1aa',
    border: '#323238',
    accent: '#818cf8',
    selection: '#2e2e48',
    success: '#4ade80',
    warning: '#facc15',
    error: '#fb7185',
  }),
]);

export const UI_FONT_PRESETS = Object.freeze([
  {
    id: 'default',
    label: 'System & Inter Default',
    value: '-apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif',
  },
  {
    id: 'atkinson',
    label: 'Atkinson Hyperlegible (High Legibility)',
    value: '"Atkinson Hyperlegible", "Inter", "Segoe UI", sans-serif',
  },
  {
    id: 'ibm_plex',
    label: 'IBM Plex Sans',
    value: '"IBM Plex Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  },
  {
    id: 'source_sans',
    label: 'Source Sans 3',
    value: '"Source Sans 3", "Source Sans Pro", "Segoe UI", sans-serif',
  },
  {
    id: 'ubuntu',
    label: 'Ubuntu Sans',
    value: '"Ubuntu Sans", Ubuntu, "Liberation Sans", sans-serif',
  },
  {
    id: 'roboto',
    label: 'Roboto',
    value: 'Roboto, "Helvetica Neue", Arial, sans-serif',
  },
  {
    id: 'serif_editorial',
    label: 'IBM Plex Serif / Editorial',
    value: '"IBM Plex Serif", Georgia, Cambria, serif',
  },
]);

export const MONO_FONT_PRESETS = Object.freeze([
  {
    id: 'default_mono',
    label: 'Fira Code / System Mono Default',
    value: '"Fira Code", SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace',
  },
  {
    id: 'jetbrains_mono',
    label: 'JetBrains Mono',
    value: '"JetBrains Mono", "Fira Code", Consolas, monospace',
  },
  {
    id: 'ibm_plex_mono',
    label: 'IBM Plex Mono',
    value: '"IBM Plex Mono", Menlo, Consolas, monospace',
  },
  {
    id: 'source_code_pro',
    label: 'Source Code Pro',
    value: '"Source Code Pro", SFMono-Regular, Menlo, Consolas, monospace',
  },
  {
    id: 'cascadia_code',
    label: 'Cascadia Code',
    value: '"Cascadia Code", "Cascadia Mono", Consolas, monospace',
  },
  {
    id: 'ubuntu_mono',
    label: 'Ubuntu Mono',
    value: '"Ubuntu Mono", "Liberation Mono", monospace',
  },
]);

export const DIAGRAM_FONT_PRESETS = Object.freeze([
  {
    id: 'inherit_ui',
    label: 'Match Interface (UI) Font',
    value: '',
  },
  {
    id: 'ibm_plex_diagram',
    label: 'IBM Plex Sans (Technical Diagramming)',
    value: '"IBM Plex Sans", "Inter", sans-serif',
  },
  {
    id: 'atkinson_diagram',
    label: 'Atkinson Hyperlegible (High Clarity Labels)',
    value: '"Atkinson Hyperlegible", sans-serif',
  },
  {
    id: 'jetbrains_diagram',
    label: 'JetBrains Mono (Strict Schema Identifiers)',
    value: '"JetBrains Mono", "Fira Code", monospace',
  },
]);

export const DEFAULT_TYPOGRAPHY = Object.freeze({
  ui_font_family: UI_FONT_PRESETS[0].value,
  mono_font_family: MONO_FONT_PRESETS[0].value,
  diagram_font_family: '',
  ui_font_size: 14,
  mono_font_size: 13,
  line_height: 1.45,
  mono_ligatures: true,
});

export function normalizeTypography(raw = {}) {
  const src = raw && typeof raw === 'object' ? raw : {};
  return {
    ui_font_family:
      String(src.ui_font_family ?? DEFAULT_TYPOGRAPHY.ui_font_family).trim() ||
      DEFAULT_TYPOGRAPHY.ui_font_family,
    mono_font_family:
      String(src.mono_font_family ?? DEFAULT_TYPOGRAPHY.mono_font_family).trim() ||
      DEFAULT_TYPOGRAPHY.mono_font_family,
    diagram_font_family: String(
      src.diagram_font_family ?? DEFAULT_TYPOGRAPHY.diagram_font_family
    ).trim(),
    ui_font_size: Math.max(11, Math.min(24, Number(src.ui_font_size) || 14)),
    mono_font_size: Math.max(10, Math.min(24, Number(src.mono_font_size) || 13)),
    line_height: Math.max(1.1, Math.min(2.2, Number(src.line_height) || 1.45)),
    mono_ligatures: src.mono_ligatures !== false,
  };
}

function withColorsAlias(scheme) {
  if (!scheme) return scheme;
  if (scheme.colors && scheme.colors.backdropA) return scheme;
  return {
    ...scheme,
    colors: {
      backdropA: scheme.backdropA,
      stripB: scheme.stripB,
      tabInactiveBg: scheme.tabInactiveBg,
      islandBg: scheme.islandBg,
      drawerBg: scheme.drawerBg,
      navBg: scheme.navBg,
      vdockBg: scheme.vdockBg,
      fg: scheme.fg,
      muted: scheme.muted,
      border: scheme.border,
      accent: scheme.accent,
      selection: scheme.selection,
      success: scheme.success,
      warning: scheme.warning,
      error: scheme.error,
    },
  };
}

function sanitizeHex(val, fallback) {
  const s = String(val || '').trim();
  return /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(s) ? s : fallback;
}

export function normalizeCustomScheme(raw = {}) {
  const c = raw?.colors && typeof raw.colors === 'object' ? raw.colors : raw;
  const baseTone = raw.baseTone === 'dark' ? 'dark' : 'light';
  const fallback = baseTone === 'dark' ? BUILTIN_COLOR_SCHEMES[1] : BUILTIN_COLOR_SCHEMES[0];
  const rawId = String(raw.id || '').trim() || `custom_${Date.now()}`;
  const id = rawId.startsWith('custom')
    ? rawId.replace(/[^a-z0-9_-]/gi, '_').toLowerCase()
    : `custom_${rawId.replace(/[^a-z0-9_-]/gi, '_').toLowerCase()}`;
  return withColorsAlias({
    id,
    label: String(raw.label || 'Custom Scheme').trim().slice(0, 48) || 'Custom Scheme',
    description: String(raw.description || 'User-defined custom colour scheme.').trim().slice(0, 140),
    builtin: false,
    baseTone,
    backdropA: sanitizeHex(c.backdropA ?? raw.backdropA, fallback.backdropA),
    stripB: sanitizeHex(c.stripB ?? raw.stripB, fallback.stripB),
    tabInactiveBg: sanitizeHex(c.tabInactiveBg ?? raw.tabInactiveBg, fallback.tabInactiveBg),
    islandBg: sanitizeHex(c.islandBg ?? raw.islandBg, fallback.islandBg),
    drawerBg: sanitizeHex(c.drawerBg ?? raw.drawerBg, fallback.drawerBg),
    navBg: sanitizeHex(c.navBg ?? raw.navBg ?? c.islandBg ?? raw.islandBg, fallback.navBg),
    vdockBg: sanitizeHex(c.vdockBg ?? raw.vdockBg ?? c.drawerBg ?? raw.drawerBg, fallback.vdockBg),
    fg: sanitizeHex(c.fg ?? raw.fg, fallback.fg),
    muted: sanitizeHex(c.muted ?? raw.muted, fallback.muted),
    border: sanitizeHex(c.border ?? raw.border, fallback.border),
    accent: sanitizeHex(c.accent ?? raw.accent, fallback.accent),
    selection: sanitizeHex(c.selection ?? raw.selection, fallback.selection),
    success: sanitizeHex(c.success ?? raw.success, fallback.success),
    warning: sanitizeHex(c.warning ?? raw.warning, fallback.warning),
    error: sanitizeHex(c.error ?? raw.error, fallback.error),
  });
}

export function hasStoredSchemeOrTypography() {
  if (typeof window === 'undefined') return false;
  try {
    return Boolean(window.localStorage?.getItem(COLOR_SCHEMES_STORAGE_KEY));
  } catch {
    return false;
  }
}

export function readStoredSchemeAndFontState() {
  const defaults = {
    activeSchemeId: 'light',
    customSchemes: [],
    enabledSchemeIds: BUILTIN_COLOR_SCHEMES.map((s) => s.id),
    typography: {...DEFAULT_TYPOGRAPHY},
  };
  if (typeof window === 'undefined') return defaults;
  try {
    const raw = window.localStorage?.getItem(COLOR_SCHEMES_STORAGE_KEY);
    if (!raw) {
      const legacyTone = window.theme === 'dark' ? 'dark' : 'light';
      return {...defaults, activeSchemeId: legacyTone};
    }
    const parsed = JSON.parse(raw) || {};
    const customSchemes = Array.isArray(parsed.customSchemes)
      ? parsed.customSchemes.map(normalizeCustomScheme)
      : [];
    const enabledSchemeIds =
      Array.isArray(parsed.enabledSchemeIds) && parsed.enabledSchemeIds.length > 0
        ? parsed.enabledSchemeIds.map(String)
        : defaults.enabledSchemeIds;
    return {
      activeSchemeId: String(parsed.activeSchemeId || 'light'),
      customSchemes,
      enabledSchemeIds,
      typography: {
        ...DEFAULT_TYPOGRAPHY,
        ...(parsed.typography || {}),
      },
    };
  } catch {
    return defaults;
  }
}

export function listAllColorSchemes(customSchemes = null) {
  const customs = Array.isArray(customSchemes)
    ? customSchemes.map(normalizeCustomScheme)
    : readStoredSchemeAndFontState().customSchemes;
  return [...BUILTIN_COLOR_SCHEMES.map(withColorsAlias), ...customs];
}

export function listToggleableColorSchemes(state = null) {
  const resolved = state || readStoredSchemeAndFontState();
  const all = listAllColorSchemes(resolved.customSchemes);
  const enabledSet = new Set(resolved.enabledSchemeIds || []);
  // Always ensure active scheme + at least light & dark remain reachable
  enabledSet.add(resolved.activeSchemeId);
  const filtered = all.filter((s) => enabledSet.has(s.id));
  return filtered.length > 0 ? filtered : [BUILTIN_COLOR_SCHEMES[0], BUILTIN_COLOR_SCHEMES[1]];
}

export function resolveColorSchemeById(schemeId, customSchemes = null) {
  const all = listAllColorSchemes(customSchemes);
  return all.find((s) => s.id === schemeId) || BUILTIN_COLOR_SCHEMES[0];
}

export function applySchemeAndTypographyToDOM(partial = {}, {persistLocal = true, syncPreferences = false} = {}) {
  const current = readStoredSchemeAndFontState();
  const next = {
    activeSchemeId: partial.activeSchemeId ?? current.activeSchemeId,
    customSchemes: Array.isArray(partial.customSchemes)
      ? partial.customSchemes.map(normalizeCustomScheme)
      : current.customSchemes,
    enabledSchemeIds: Array.isArray(partial.enabledSchemeIds)
      ? partial.enabledSchemeIds.map(String)
      : current.enabledSchemeIds,
    typography: {
      ...current.typography,
      ...(partial.typography || {}),
    },
  };

  if (persistLocal && typeof window !== 'undefined') {
    try {
      window.localStorage?.setItem(COLOR_SCHEMES_STORAGE_KEY, JSON.stringify(next));
    } catch {
      // Ignore storage quota errors.
    }
  }

  const scheme = resolveColorSchemeById(next.activeSchemeId, next.customSchemes);
  const typo = next.typography;
  const uiFont = String(typo.ui_font_family || DEFAULT_TYPOGRAPHY.ui_font_family).trim();
  const monoFont = String(typo.mono_font_family || DEFAULT_TYPOGRAPHY.mono_font_family).trim();
  const diagramFont = String(typo.diagram_font_family || '').trim() || uiFont;
  const uiSize = Math.max(11, Math.min(24, Number(typo.ui_font_size) || 14));
  const monoSize = Math.max(10, Math.min(24, Number(typo.mono_font_size) || 13));
  const lineHeight = Math.max(1.1, Math.min(2.2, Number(typo.line_height) || 1.45));
  const ligatures = typo.mono_ligatures !== false ? 'normal' : 'none';

  if (typeof window !== 'undefined') {
    window.theme = scheme.baseTone;
  }

  if (typeof document !== 'undefined' && document.documentElement) {
    const root = document.documentElement;
    if (root.getAttribute('data-cde-theme') !== scheme.baseTone) {
      root.setAttribute('data-cde-theme', scheme.baseTone);
    }
    if (root.getAttribute('data-sr-scheme') !== scheme.id) {
      root.setAttribute('data-sr-scheme', scheme.id);
    }

    const cssVars = {
      '--sr-scheme-backdrop-a': scheme.backdropA,
      '--sr-scheme-strip-b': scheme.stripB,
      '--sr-scheme-tab-inactive-bg': scheme.tabInactiveBg,
      '--sr-scheme-island-bg': scheme.islandBg,
      '--sr-scheme-drawer-bg': scheme.drawerBg,
      '--sr-scheme-nav-bg': scheme.navBg,
      '--sr-scheme-vdock-bg': scheme.vdockBg,
      '--sr-scheme-fg': scheme.fg,
      '--sr-scheme-muted': scheme.muted,
      '--sr-scheme-border': scheme.border,
      '--sr-scheme-accent': scheme.accent,
      '--sr-scheme-selection': scheme.selection,
      '--sr-scheme-success': scheme.success,
      '--sr-scheme-warning': scheme.warning,
      '--sr-scheme-error': scheme.error,
      '--sr-island-border': scheme.border,
      // Bridge into global CDEadmin tokens so dialogs, trees, tables & editors match
      '--cde-color-canvas': scheme.islandBg,
      '--cde-color-panel': scheme.drawerBg,
      '--cde-color-navigation': scheme.navBg,
      '--cde-color-workspace': scheme.backdropA,
      '--cde-color-elevated': scheme.islandBg,
      '--cde-color-text': scheme.fg,
      '--cde-color-text-muted': scheme.muted,
      '--cde-color-border': scheme.border,
      '--cde-color-primary': scheme.accent,
      '--cde-color-focus': scheme.accent,
      '--cde-color-selection': scheme.selection,
      '--cde-color-hover': scheme.selection,
      '--cde-color-success': scheme.success,
      '--cde-color-warning': scheme.warning,
      '--cde-color-error': scheme.error,
      // Typography variables
      '--cde-font-sans': uiFont,
      '--cde-font-mono': monoFont,
      '--sr-font-ui': uiFont,
      '--sr-font-mono': monoFont,
      '--sr-font-diagram': diagramFont,
      '--sr-ui-font-size': `${uiSize}px`,
      '--sr-mono-font-size': `${monoSize}px`,
      '--sr-line-height': String(lineHeight),
      '--sr-font-ligatures': ligatures,
    };

    Object.entries(cssVars).forEach(([k, v]) => {
      root.style.setProperty(k, v);
    });
  }

  // Notify MUI / Theme presentation bridge so CodeMirror & legacy views match immediately
  if (typeof window !== 'undefined') {
    try {
      previewAppearance({
        theme: scheme.baseTone,
        accessibility_ui_font_family: uiFont,
        accessibility_monospace_font_family: monoFont,
        accessibility_line_height: lineHeight,
        accessibility_color_canvas: scheme.islandBg,
        accessibility_color_panel: scheme.drawerBg,
        accessibility_color_text: scheme.fg,
        accessibility_color_muted_text: scheme.muted,
        accessibility_color_primary: scheme.accent,
        accessibility_color_focus: scheme.accent,
        accessibility_color_border: scheme.border,
        accessibility_color_selection: scheme.selection,
      });
    } catch {
      // Safe no-op in isolated component unit tests.
    }

    window.dispatchEvent(
      new CustomEvent(COLOR_SCHEME_CHANGED_EVENT, {
        detail: {scheme, state: next},
      })
    );
  }

  if (syncPreferences) {
    try {
      const store = usePreferences.getState?.();
      const updates = [];
      const pushPref = (mod, name, val) => {
        const pref = store?.getPreferences?.(mod, name);
        if (pref) {
          updates.push({
            category_id: pref.cid,
            id: pref.id,
            mid: pref.mid,
            name: pref.name,
            value: val,
          });
        }
      };
      pushPref('misc', 'theme', scheme.baseTone);
      pushPref('misc', 'accessibility_ui_font_family', uiFont);
      pushPref('misc', 'accessibility_monospace_font_family', monoFont);
      if (updates.length > 0 && typeof store?.setPreferences === 'function') {
        void store.setPreferences(updates).catch(() => {});
      }
    } catch {
      // Offline / unit-test safe.
    }
  }

  return {scheme, state: next};
}
