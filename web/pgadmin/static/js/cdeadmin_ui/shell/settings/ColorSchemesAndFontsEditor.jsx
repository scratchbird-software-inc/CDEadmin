/////////////////////////////////////////////////////////////
//
// ScratchRobin — Colour Schemes & Typography Settings Editor
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Button} from '../../primitives/Button';
import {NumberField, TextField} from '../../primitives/Field';
import {Select, Switch} from '../../primitives/Choice';
import {Slider} from '../../primitives/AdvancedControls';
import {
  BUILTIN_COLOR_SCHEMES,
  DEFAULT_TYPOGRAPHY,
  DIAGRAM_FONT_PRESETS,
  MONO_FONT_PRESETS,
  UI_FONT_PRESETS,
  applySchemeAndTypographyToDOM,
  listAllColorSchemes,
  normalizeCustomScheme,
  normalizeTypography,
  readStoredSchemeAndFontState,
} from '../colorSchemesAndFonts';

const COLOR_TOKEN_FIELDS = Object.freeze([
  ['backdropA', 'Backdrop Colour a (Main Canvas)'],
  ['stripB', 'Strip Colour b (3b1 / 3b2 Track)'],
  ['islandBg', 'Island Surface (3b / 3e)'],
  ['drawerBg', 'Side Drawers (3a / 3c)'],
  ['navBg', 'Top Menu Bar (Area 1)'],
  ['vdockBg', 'Side Dock Island (Area 2)'],
  ['fg', 'Primary Text'],
  ['muted', 'Secondary / Muted Text'],
  ['border', 'Island & Control Border'],
  ['accent', 'Primary Accent'],
  ['selection', 'Active Selection Fill'],
]);

function createBlankDraftScheme(seedScheme = BUILTIN_COLOR_SCHEMES[1]) {
  return {
    id: `custom-${Date.now().toString(36)}`,
    label: 'My Custom Palette',
    baseTone: seedScheme?.baseTone === 'light' ? 'light' : 'dark',
    colors: {...(seedScheme?.colors || BUILTIN_COLOR_SCHEMES[1].colors)},
  };
}

export function ColorSchemesAndFontsEditor({
  subView = 'schemes',
  hideTabs = false,
  globalSettings = {},
  onChangeGlobal,
  onNavigateSubView,
}) {
  const initialStored = useMemo(() => readStoredSchemeAndFontState(), []);
  const [activeSubView, setActiveSubView] = useState(subView);

  useEffect(() => {
    setActiveSubView(subView);
  }, [subView]);

  const switchSubView = (nextView) => {
    setActiveSubView(nextView);
    onNavigateSubView?.(nextView);
  };

  const [activeSchemeId, setActiveSchemeId] = useState(
    () => globalSettings.active_color_scheme || initialStored.activeSchemeId || 'light'
  );
  const [customSchemes, setCustomSchemes] = useState(() =>
    Array.isArray(globalSettings.custom_color_schemes) &&
    globalSettings.custom_color_schemes.length > 0
      ? globalSettings.custom_color_schemes
      : initialStored.customSchemes || []
  );
  const [enabledSchemeIds, setEnabledSchemeIds] = useState(() =>
    Array.isArray(globalSettings.enabled_scheme_ids) &&
    globalSettings.enabled_scheme_ids.length > 0
      ? globalSettings.enabled_scheme_ids
      : initialStored.enabledSchemeIds || BUILTIN_COLOR_SCHEMES.map((s) => s.id)
  );
  const [typography, setTypography] = useState(() =>
    normalizeTypography(globalSettings.typography || initialStored.typography)
  );
  const [draftScheme, setDraftScheme] = useState(() =>
    createBlankDraftScheme(BUILTIN_COLOR_SCHEMES[1])
  );
  const [editingCustom, setEditingCustom] = useState(false);

  useEffect(() => {
    if (globalSettings.active_color_scheme) {
      setActiveSchemeId(globalSettings.active_color_scheme);
    }
    if (Array.isArray(globalSettings.custom_color_schemes)) {
      setCustomSchemes(globalSettings.custom_color_schemes);
    }
    if (Array.isArray(globalSettings.enabled_scheme_ids) && globalSettings.enabled_scheme_ids.length > 0) {
      setEnabledSchemeIds(globalSettings.enabled_scheme_ids);
    }
    if (globalSettings.typography) {
      setTypography(normalizeTypography(globalSettings.typography));
    }
  }, [
    globalSettings.active_color_scheme,
    globalSettings.custom_color_schemes,
    globalSettings.enabled_scheme_ids,
    globalSettings.typography,
  ]);

  const allSchemes = useMemo(() => listAllColorSchemes(customSchemes), [customSchemes]);

  const commitSchemeAndTypography = (nextPatch = {}) => {
    const nextActive = nextPatch.activeSchemeId ?? activeSchemeId;
    const nextCustom = nextPatch.customSchemes ?? customSchemes;
    const nextEnabled = nextPatch.enabledSchemeIds ?? enabledSchemeIds;
    const nextTypo = normalizeTypography(nextPatch.typography ?? typography);

    setActiveSchemeId(nextActive);
    setCustomSchemes(nextCustom);
    setEnabledSchemeIds(nextEnabled);
    setTypography(nextTypo);

    applySchemeAndTypographyToDOM(
      {
        activeSchemeId: nextActive,
        customSchemes: nextCustom,
        enabledSchemeIds: nextEnabled,
        typography: nextTypo,
      },
      {persistLocal: true, syncPreferences: true}
    );

    onChangeGlobal?.({
      active_color_scheme: nextActive,
      custom_color_schemes: nextCustom,
      enabled_scheme_ids: nextEnabled,
      typography: nextTypo,
    });
  };

  const handleToggleSchemeInMenu = (schemeId, enabled) => {
    const nextSet = new Set(enabledSchemeIds);
    if (enabled) {
      nextSet.add(schemeId);
    } else if (schemeId !== 'light' && schemeId !== 'dark') {
      nextSet.delete(schemeId);
    }
    nextSet.add('light');
    nextSet.add('dark');
    commitSchemeAndTypography({enabledSchemeIds: [...nextSet]});
  };

  const handleSaveDraftCustomScheme = () => {
    const normalized = normalizeCustomScheme(draftScheme);
    if (!normalized) return;
    const withoutPrev = customSchemes.filter((c) => c.id !== normalized.id);
    const nextCustom = [...withoutPrev, normalized];
    const nextEnabled = [...new Set([...enabledSchemeIds, normalized.id])];
    commitSchemeAndTypography({
      activeSchemeId: normalized.id,
      customSchemes: nextCustom,
      enabledSchemeIds: nextEnabled,
    });
    setEditingCustom(false);
  };

  const handleDeleteCustomScheme = (schemeId) => {
    const nextCustom = customSchemes.filter((c) => c.id !== schemeId);
    const nextEnabled = enabledSchemeIds.filter((id) => id !== schemeId);
    const nextActive = activeSchemeId === schemeId ? 'light' : activeSchemeId;
    commitSchemeAndTypography({
      activeSchemeId: nextActive,
      customSchemes: nextCustom,
      enabledSchemeIds: nextEnabled,
    });
  };

  const subViewTabsBar = hideTabs ? null : (
    <div
      role="tablist"
      aria-label={gettext('Colour Schemes & Typography Sections')}
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 6,
        paddingBottom: 8,
        borderBottom: '1px solid var(--sr-border-subtle)',
      }}
    >
      {[
        ['schemes', gettext('Colour Schemes')],
        ['fonts', gettext('Fonts & Typography')],
      ].map(([key, label]) => {
        const selected = activeSubView === key;
        return (
          <Button
            key={key}
            role="tab"
            aria-selected={selected}
            intent={selected ? 'primary' : 'neutral'}
            data-cdeadmin-qa-key={`appearance-tab-${key}`}
            onClick={() => switchSubView(key)}
          >
            {label}
          </Button>
        );
      })}
    </div>
  );

  if (activeSubView === 'fonts') {
    const uiPresetMatch =
      UI_FONT_PRESETS.find((p) => p.value === typography.ui_font_family)?.value || '__custom__';
    const monoPresetMatch =
      MONO_FONT_PRESETS.find((p) => p.value === typography.mono_font_family)?.value || '__custom__';
    const diagramPresetMatch =
      DIAGRAM_FONT_PRESETS.find((p) => p.value === typography.diagram_font_family)?.value ||
      '__custom__';

    return (
      <div
        data-cdeadmin-qa-key="settings-fonts-editor"
        style={{display: 'flex', flexDirection: 'column', gap: 14}}
      >
        {subViewTabsBar}
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
          <div>
            <div style={{fontWeight: 700, fontSize: '0.92rem'}}>
              {gettext('Fonts & Typography')}
            </div>
            <div style={{fontSize: '0.78rem', color: 'var(--sr-text-secondary)'}}>
              {gettext(
                'Configure UI, SQL/Code monospace, and DDN diagram font families, sizes, line height, and ligatures.'
              )}
            </div>
          </div>
          <Button
            intent="neutral"
            data-cdeadmin-qa-key="fonts-reset-defaults"
            onClick={() => commitSchemeAndTypography({typography: DEFAULT_TYPOGRAPHY})}
          >
            {gettext('Reset Default Fonts')}
          </Button>
        </div>

        {/* UI Font */}
        <div
          style={{
            padding: 12,
            borderRadius: 10,
            border: '1px solid var(--sr-border-default)',
            background: 'var(--sr-surface-subtle)',
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
          }}
        >
          <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10}}>
            <Select
              label={gettext('Interface (UI) Font Preset')}
              value={uiPresetMatch}
              options={[
                ...UI_FONT_PRESETS,
                {value: '__custom__', label: gettext('Custom CSS Font Stack…')},
              ]}
              onChange={(val) => {
                if (val && val !== '__custom__') {
                  commitSchemeAndTypography({
                    typography: {...typography, ui_font_family: val},
                  });
                }
              }}
            />
            <TextField
              label={gettext('Interface Font CSS Stack')}
              value={typography.ui_font_family}
              inputProps={{'data-cdeadmin-qa-key': 'font-ui-family'}}
              onChange={(e) =>
                commitSchemeAndTypography({
                  typography: {...typography, ui_font_family: e.target.value},
                })
              }
            />
          </div>

          <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10}}>
            <Select
              label={gettext('SQL / Code / Grid Monospace Preset')}
              value={monoPresetMatch}
              options={[
                ...MONO_FONT_PRESETS,
                {value: '__custom__', label: gettext('Custom Monospace Stack…')},
              ]}
              onChange={(val) => {
                if (val && val !== '__custom__') {
                  commitSchemeAndTypography({
                    typography: {...typography, mono_font_family: val},
                  });
                }
              }}
            />
            <TextField
              label={gettext('Monospace Font CSS Stack')}
              value={typography.mono_font_family}
              inputProps={{'data-cdeadmin-qa-key': 'font-mono-family'}}
              onChange={(e) =>
                commitSchemeAndTypography({
                  typography: {...typography, mono_font_family: e.target.value},
                })
              }
            />
          </div>

          <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10}}>
            <Select
              label={gettext('Diagram & DDN Canvas Font Preset')}
              value={diagramPresetMatch}
              options={[
                ...DIAGRAM_FONT_PRESETS,
                {value: '__custom__', label: gettext('Custom Diagram Stack…')},
              ]}
              onChange={(val) => {
                if (val && val !== '__custom__') {
                  commitSchemeAndTypography({
                    typography: {...typography, diagram_font_family: val},
                  });
                }
              }}
            />
            <TextField
              label={gettext('Diagram Font CSS Stack')}
              value={typography.diagram_font_family}
              inputProps={{'data-cdeadmin-qa-key': 'font-diagram-family'}}
              onChange={(e) =>
                commitSchemeAndTypography({
                  typography: {...typography, diagram_font_family: e.target.value},
                })
              }
            />
          </div>
        </div>

        {/* Sizes & Line Height */}
        <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10}}>
          <NumberField
            label={gettext('UI Font Size (px, 11–24)')}
            min={11}
            max={24}
            value={typography.ui_font_size}
            inputProps={{'data-cdeadmin-qa-key': 'font-ui-size'}}
            onChange={(e) =>
              commitSchemeAndTypography({
                typography: {
                  ...typography,
                  ui_font_size: Math.max(11, Math.min(24, Number(e.target.value) || 14)),
                },
              })
            }
          />
          <NumberField
            label={gettext('Monospace Font Size (px, 10–24)')}
            min={10}
            max={24}
            value={typography.mono_font_size}
            inputProps={{'data-cdeadmin-qa-key': 'font-mono-size'}}
            onChange={(e) =>
              commitSchemeAndTypography({
                typography: {
                  ...typography,
                  mono_font_size: Math.max(10, Math.min(24, Number(e.target.value) || 13)),
                },
              })
            }
          />
          <div>
            <Slider
              label={gettext('Base Line Height (%s)', typography.line_height)}
              min={1.1}
              max={2.0}
              step={0.05}
              value={typography.line_height}
              onChange={(val) =>
                commitSchemeAndTypography({
                  typography: {...typography, line_height: Number(val)},
                })
              }
            />
          </div>
        </div>

        <Switch
          label={gettext('Enable Programming Ligatures in SQL & Code Editors (calt / liga)')}
          checked={Boolean(typography.mono_ligatures)}
          data-cdeadmin-qa-key="font-mono-ligatures"
          onChange={(checked) =>
            commitSchemeAndTypography({
              typography: {...typography, mono_ligatures: Boolean(checked)},
            })
          }
        />

        {/* Live Specimen Preview */}
        <div
          style={{
            padding: 12,
            borderRadius: 10,
            border: '1px solid var(--sr-border-default)',
            background: 'var(--sr-surface-card)',
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
          }}
        >
          <div style={{fontSize: '0.75rem', fontWeight: 700, color: 'var(--sr-text-secondary)'}}>
            {gettext('Live Typography Specimen')}
          </div>
          <div
            style={{
              fontFamily: typography.ui_font_family,
              fontSize: `${typography.ui_font_size}px`,
              lineHeight: typography.line_height,
            }}
          >
            <strong>Data Navigator</strong> — Firebird 5.0 · <code>SYSDBA</code> · 128,450 rows
            fetched in 0.042 s
          </div>
          <pre
            style={{
              margin: 0,
              padding: '8px 10px',
              borderRadius: 8,
              background: 'var(--sr-surface-subtle)',
              border: '1px solid var(--sr-border-subtle)',
              fontFamily: typography.mono_font_family,
              fontSize: `${typography.mono_font_size}px`,
              lineHeight: typography.line_height,
              fontVariantLigatures: typography.mono_ligatures ? 'normal' : 'none',
              overflowX: 'auto',
            }}
          >
            {'SELECT c.customer_id, c.total_balance >= 1000.00 AS is_vip -- 0O 1lI != >= ->\nFROM sales.customers c WHERE c.status <> \'ARCHIVED\' ROWS 1 TO 250;'}
          </pre>
        </div>
      </div>
    );
  }

  return (
    <div
      data-cdeadmin-qa-key="settings-schemes-editor"
      style={{display: 'flex', flexDirection: 'column', gap: 14}}
    >
      {subViewTabsBar}
      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8}}>
        <div>
          <div style={{fontWeight: 700, fontSize: '0.92rem'}}>
            {gettext('Colour Schemes & Top-Bar Scheme Toggle')}
          </div>
          <div style={{fontSize: '0.78rem', color: 'var(--sr-text-secondary)'}}>
            {gettext(
              'Choose from 10 curated palettes or create custom colour schemes. Any scheme switched ON for the Top Bar appears in Area 1’s scheme selector.'
            )}
          </div>
        </div>
        <Button
          intent="primary"
          data-cdeadmin-qa-key="scheme-new-custom"
          onClick={() => {
            const current = allSchemes.find((s) => s.id === activeSchemeId) || BUILTIN_COLOR_SCHEMES[1];
            setDraftScheme(createBlankDraftScheme(current));
            setEditingCustom((prev) => !prev);
          }}
        >
          {editingCustom ? gettext('Hide Custom Builder') : gettext('+ New Custom Scheme')}
        </Button>
      </div>

      {editingCustom && (
        <div
          data-cdeadmin-qa-key="scheme-custom-builder"
          style={{
            padding: 12,
            borderRadius: 10,
            border: '2px solid var(--sr-accent)',
            background: 'var(--sr-surface-subtle)',
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
          }}
        >
          <div style={{fontWeight: 700, fontSize: '0.84rem'}}>
            {gettext('Custom Colour Scheme Builder')}
          </div>
          <div style={{display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 10}}>
            <TextField
              label={gettext('Scheme Display Name')}
              value={draftScheme.label}
              inputProps={{'data-cdeadmin-qa-key': 'scheme-custom-name'}}
              onChange={(e) => setDraftScheme((p) => ({...p, label: e.target.value}))}
            />
            <Select
              label={gettext('Base Contrast Tone')}
              value={draftScheme.baseTone}
              options={[
                {value: 'light', label: gettext('Light Base Tone')},
                {value: 'dark', label: gettext('Dark Base Tone')},
              ]}
              onChange={(val) => setDraftScheme((p) => ({...p, baseTone: val || 'dark'}))}
            />
          </div>
          <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8}}>
            {COLOR_TOKEN_FIELDS.map(([tokenKey, tokenLabel]) => (
              <div
                key={tokenKey}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '4px 8px',
                  borderRadius: 8,
                  background: 'var(--sr-surface-card)',
                  border: '1px solid var(--sr-border-subtle)',
                }}
              >
                <input
                  type="color"
                  aria-label={tokenLabel}
                  value={
                    /^#[0-9a-fA-F]{6}$/.test(draftScheme.colors[tokenKey] || '')
                      ? draftScheme.colors[tokenKey]
                      : '#28749e'
                  }
                  onChange={(e) =>
                    setDraftScheme((p) => ({
                      ...p,
                      colors: {...p.colors, [tokenKey]: e.target.value},
                    }))
                  }
                  style={{
                    width: 28,
                    height: 28,
                    padding: 0,
                    border: 'none',
                    borderRadius: 6,
                    cursor: 'pointer',
                    background: 'transparent',
                  }}
                />
                <div style={{flex: 1, minWidth: 0}}>
                  <div style={{fontSize: '0.72rem', fontWeight: 600}}>{tokenLabel}</div>
                  <input
                    type="text"
                    value={draftScheme.colors[tokenKey] || ''}
                    data-cdeadmin-qa-key={`scheme-custom-color-${tokenKey}`}
                    onChange={(e) =>
                      setDraftScheme((p) => ({
                        ...p,
                        colors: {...p.colors, [tokenKey]: e.target.value},
                      }))
                    }
                    style={{
                      width: '100%',
                      fontSize: '0.74rem',
                      fontFamily: 'var(--sr-font-mono, monospace)',
                      border: '1px solid var(--sr-border-default)',
                      borderRadius: 4,
                      padding: '2px 6px',
                      background: 'var(--sr-surface-subtle)',
                      color: 'var(--sr-text-primary)',
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
          <div style={{display: 'flex', justifyContent: 'flex-end', gap: 8}}>
            <Button intent="neutral" onClick={() => setEditingCustom(false)}>
              {gettext('Cancel')}
            </Button>
            <Button
              intent="primary"
              data-cdeadmin-qa-key="scheme-save-custom"
              onClick={handleSaveDraftCustomScheme}
            >
              {gettext('Save & Activate Custom Scheme')}
            </Button>
          </div>
        </div>
      )}

      {/* Visual Grid of Built-in & Custom Schemes */}
      <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(235px, 1fr))', gap: 10}}>
        {allSchemes.map((scheme) => {
          const isActive = scheme.id === activeSchemeId;
          const inToggle =
            enabledSchemeIds.includes(scheme.id) ||
            scheme.id === 'light' ||
            scheme.id === 'dark';
          return (
            <div
              key={scheme.id}
              data-cdeadmin-qa-key={`scheme-card-${scheme.id}`}
              style={{
                borderRadius: 10,
                border: isActive
                  ? '2px solid var(--sr-accent)'
                  : '1px solid var(--sr-border-default)',
                background: 'var(--sr-surface-card)',
                padding: 10,
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
              }}
            >
              {/* Miniature Shell Island Mock Preview */}
              <div
                style={{
                  height: 62,
                  borderRadius: 8,
                  background: scheme.colors.backdropA,
                  padding: 5,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 4,
                  border: `1px solid ${scheme.colors.border}`,
                }}
              >
                <div
                  style={{
                    height: 11,
                    borderRadius: 4,
                    background: scheme.colors.navBg,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '0 5px',
                  }}
                >
                  <span
                    style={{
                      width: 24,
                      height: 4,
                      borderRadius: 2,
                      background: scheme.colors.fg,
                      opacity: 0.65,
                    }}
                  />
                  <span
                    style={{
                      width: 12,
                      height: 5,
                      borderRadius: 3,
                      background: scheme.colors.accent,
                    }}
                  />
                </div>
                <div style={{flex: 1, display: 'flex', gap: 4}}>
                  <div
                    style={{
                      width: 14,
                      borderRadius: 4,
                      background: scheme.colors.vdockBg,
                    }}
                  />
                  <div style={{flex: 1, display: 'flex', flexDirection: 'column', gap: 3}}>
                    <div
                      style={{
                        height: 10,
                        borderRadius: 4,
                        background: scheme.colors.stripB,
                      }}
                    />
                    <div
                      style={{
                        flex: 1,
                        borderRadius: 4,
                        background: scheme.colors.islandBg,
                        display: 'flex',
                        alignItems: 'center',
                        padding: '0 6px',
                        gap: 4,
                      }}
                    >
                      <span
                        style={{
                          width: 14,
                          height: 5,
                          borderRadius: 2,
                          background: scheme.colors.accent,
                        }}
                      />
                      <span
                        style={{
                          width: 32,
                          height: 4,
                          borderRadius: 2,
                          background: scheme.colors.fg,
                          opacity: 0.7,
                        }}
                      />
                    </div>
                  </div>
                </div>
              </div>

              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                <div>
                  <div style={{fontWeight: 700, fontSize: '0.82rem'}}>{scheme.label}</div>
                  <div style={{fontSize: '0.7rem', color: 'var(--sr-text-secondary)'}}>
                    {scheme.builtin ? gettext('Built-in') : gettext('Custom')} ·{' '}
                    {scheme.baseTone === 'dark' ? gettext('Dark') : gettext('Light')}
                  </div>
                </div>
                {isActive && (
                  <span
                    style={{
                      fontSize: '0.68rem',
                      fontWeight: 700,
                      padding: '2px 7px',
                      borderRadius: 999,
                      background: 'var(--sr-accent-subtle)',
                      color: 'var(--sr-accent)',
                    }}
                  >
                    {gettext('Active')}
                  </span>
                )}
              </div>

              <Switch
                label={gettext('Show in Top Bar Toggle')}
                checked={inToggle}
                disabled={scheme.id === 'light' || scheme.id === 'dark'}
                data-cdeadmin-qa-key={`scheme-toggle-enabled-${scheme.id}`}
                onChange={(checked) => handleToggleSchemeInMenu(scheme.id, checked)}
              />

              <div style={{display: 'flex', gap: 6, marginTop: 'auto'}}>
                <Button
                  intent={isActive ? 'neutral' : 'primary'}
                  data-cdeadmin-qa-key={`scheme-apply-${scheme.id}`}
                  onClick={() => commitSchemeAndTypography({activeSchemeId: scheme.id})}
                >
                  {isActive ? gettext('Applied') : gettext('Apply')}
                </Button>
                <Button
                  intent="neutral"
                  onClick={() => {
                    setDraftScheme({
                      id: scheme.builtin ? `custom-${scheme.id}` : scheme.id,
                      label: scheme.builtin ? `${scheme.label} (Copy)` : scheme.label,
                      baseTone: scheme.baseTone,
                      colors: {...scheme.colors},
                    });
                    setEditingCustom(true);
                  }}
                >
                  {scheme.builtin ? gettext('Clone') : gettext('Edit')}
                </Button>
                {!scheme.builtin && (
                  <Button
                    intent="danger"
                    data-cdeadmin-qa-key={`scheme-delete-${scheme.id}`}
                    onClick={() => handleDeleteCustomScheme(scheme.id)}
                  >
                    {gettext('Delete')}
                  </Button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

ColorSchemesAndFontsEditor.propTypes = {
  subView: PropTypes.oneOf(['schemes', 'fonts']),
  hideTabs: PropTypes.bool,
  globalSettings: PropTypes.object,
  onChangeGlobal: PropTypes.func,
  onNavigateSubView: PropTypes.func,
};
