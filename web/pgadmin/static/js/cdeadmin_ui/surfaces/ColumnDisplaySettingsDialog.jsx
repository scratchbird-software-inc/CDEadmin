/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Button} from '../primitives/Button';
import {Dialog} from '../overlays/Dialog';
import {
  DEFAULT_MAX_COL_WIDTH,
  DEFAULT_MIN_COL_WIDTH,
  FIELD_FONTS,
  FIELD_FONT_SIZES,
} from './dataEditSurfaceHelpers';

const TEXT_COLOR_SWATCHES = [
  '#0f172a',
  '#1d4ed8',
  '#047857',
  '#b45309',
  '#b91c1c',
  '#6d28d9',
];

const BG_COLOR_SWATCHES = [
  '#f8fafc',
  '#eff6ff',
  '#ecfdf5',
  '#fffbeb',
  '#fef2f2',
  '#f5f3ff',
];

function cleanColumnDraft(entry = {}) {
  const out = {...entry};
  for (const k of [
    'font',
    'fontSize',
    'color',
    'bgColor',
    'hAlign',
    'vAlign',
    'wrapMode',
  ]) {
    if (out[k] === '' || out[k] === null) {
      delete out[k];
    }
  }
  for (const numKey of ['maxWrapLines', 'minWidth', 'maxWidth']) {
    if (out[numKey] === '' || out[numKey] === null || out[numKey] === undefined) {
      delete out[numKey];
    } else {
      const parsed = Number(out[numKey]);
      if (!Number.isFinite(parsed) || parsed <= 0) {
        delete out[numKey];
      } else {
        out[numKey] = Math.round(parsed);
      }
    }
  }
  if (
    typeof out.minWidth === 'number' &&
    typeof out.maxWidth === 'number' &&
    out.maxWidth < out.minWidth
  ) {
    out.maxWidth = out.minWidth;
  }
  if (typeof out.width === 'number') {
    const lo = typeof out.minWidth === 'number' ? out.minWidth : DEFAULT_MIN_COL_WIDTH;
    const hi = typeof out.maxWidth === 'number' ? out.maxWidth : DEFAULT_MAX_COL_WIDTH;
    out.width = Math.max(lo, Math.min(hi, out.width));
  }
  return out;
}

export default function ColumnDisplaySettingsDialog({
  open,
  columns = [],
  initialColumnName = '',
  layout,
  objectLabel = '',
  canPersistObjectLayout = false,
  templates = [],
  onClose,
  onApplyLayout,
  onSaveObjectLayout,
  onSaveTemplate,
  onRequestTemplates,
}) {
  const [selectedCol, setSelectedCol] = useState(
    initialColumnName || columns[0]?.name || ''
  );
  const [colPrefsDraft, setColPrefsDraft] = useState(
    () => ({...(layout?.gridColPrefs || {})})
  );
  const [persistToDb, setPersistToDb] = useState(Boolean(canPersistObjectLayout));
  const [templateName, setTemplateName] = useState('');
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [saving, setSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    setSelectedCol(initialColumnName || columns[0]?.name || '');
    setColPrefsDraft({...(layout?.gridColPrefs || {})});
    setPersistToDb(Boolean(canPersistObjectLayout));
    setStatusMessage('');
    setError('');
    onRequestTemplates?.();
  }, [open, initialColumnName]);

  if (!open) return null;

  const activePrefs = colPrefsDraft[selectedCol] || {};

  const updateCurrentCol = (patch) => {
    if (!selectedCol) return;
    setColPrefsDraft((prev) => ({
      ...prev,
      [selectedCol]: {...(prev[selectedCol] || {}), ...patch},
    }));
  };

  const resetCurrentCol = () => {
    if (!selectedCol) return;
    setColPrefsDraft((prev) => {
      const next = {...prev};
      const pinned = next[selectedCol]?.pinned;
      if (pinned) {
        next[selectedCol] = {pinned: true};
      } else {
        delete next[selectedCol];
      }
      return next;
    });
  };

  const buildNextLayout = () => {
    const cleanedGridPrefs = {};
    const nextFormFieldPrefs = {...(layout?.formFieldPrefs || {})};
    for (const [colName, rawPrefs] of Object.entries(colPrefsDraft)) {
      const cleaned = cleanColumnDraft(rawPrefs);
      if (Object.keys(cleaned).length > 0) {
        cleanedGridPrefs[colName] = cleaned;
        nextFormFieldPrefs[colName] = {
          ...(nextFormFieldPrefs[colName] || {}),
          font: cleaned.font,
          fontSize: cleaned.fontSize,
          color: cleaned.color,
          bgColor: cleaned.bgColor,
          hAlign: cleaned.hAlign,
          vAlign: cleaned.vAlign,
          wrapMode: cleaned.wrapMode,
          maxWrapLines: cleaned.maxWrapLines,
          minWidth: cleaned.minWidth,
          maxWidth: cleaned.maxWidth,
        };
      } else if (nextFormFieldPrefs[colName]) {
        const fp = {...nextFormFieldPrefs[colName]};
        for (const k of [
          'font',
          'fontSize',
          'color',
          'bgColor',
          'hAlign',
          'vAlign',
          'wrapMode',
          'maxWrapLines',
          'minWidth',
          'maxWidth',
        ]) {
          delete fp[k];
        }
        nextFormFieldPrefs[colName] = fp;
      }
    }
    return {
      ...layout,
      gridColPrefs: cleanedGridPrefs,
      formFieldPrefs: nextFormFieldPrefs,
    };
  };

  const handleSaveAndApply = async () => {
    setSaving(true);
    setError('');
    try {
      const nextLayout = buildNextLayout();
      onApplyLayout?.(nextLayout);
      if (persistToDb && canPersistObjectLayout && onSaveObjectLayout) {
        await onSaveObjectLayout(nextLayout);
      }
      onClose();
    } catch (failure) {
      setError(failure?.message || String(failure));
    } finally {
      setSaving(false);
    }
  };

  const handleSaveAsTemplate = async () => {
    const cleanName = templateName.trim();
    if (!cleanName) {
      setError(gettext('Enter a template name first.'));
      return;
    }
    if (!onSaveTemplate) return;
    setSaving(true);
    setError('');
    try {
      const nextLayout = buildNextLayout();
      onApplyLayout?.(nextLayout);
      await onSaveTemplate(cleanName, nextLayout);
      setStatusMessage(
        gettext('Saved template "%s" to UserConfigurationDatabase.', cleanName)
      );
      setTemplateName('');
      onRequestTemplates?.();
    } catch (failure) {
      setError(failure?.message || String(failure));
    } finally {
      setSaving(false);
    }
  };

  const handleApplySelectedTemplate = () => {
    const tpl = (templates || []).find(
      (item) => String(item.template_id) === String(selectedTemplateId)
    );
    if (!tpl?.layout) return;
    setColPrefsDraft({...(tpl.layout.gridColPrefs || {})});
    onApplyLayout?.({...layout, ...tpl.layout});
    setStatusMessage(gettext('Applied template "%s".', tpl.name));
  };

  const previewWrap = activePrefs.wrapMode || 'none';
  const previewMaxLines =
    previewWrap === 'clamp'
      ? Math.max(1, Math.min(50, Number(activePrefs.maxWrapLines) || 3))
      : previewWrap === 'wrap' && Number(activePrefs.maxWrapLines) >= 1
        ? Math.max(1, Math.min(50, Number(activePrefs.maxWrapLines)))
        : null;

  return (
    <Dialog
      open={open}
      title={gettext('Column Display Settings — %s', selectedCol || gettext('Result Set'))}
      size="medium"
      onClose={onClose}
      actions={
        <>
          <Button onClick={resetCurrentCol}>
            {gettext('Reset Column')}
          </Button>
          <Button onClick={onClose}>{gettext('Cancel')}</Button>
          <Button intent="primary" disabled={saving} onClick={handleSaveAndApply}>
            {persistToDb && canPersistObjectLayout
              ? gettext('Apply & Save Preferences')
              : gettext('Apply')}
          </Button>
        </>
      }
    >
      <div
        data-cdeadmin-qa-key="column-display-settings-dialog"
        style={{display: 'grid', gap: 12, fontSize: '0.82rem'}}
      >
        {/* Column selector */}
        <div className="sr-field">
          <label className="sr-field-label" htmlFor="col-display-target-select">
            {gettext('Result-Set Column')}
          </label>
          <select
            id="col-display-target-select"
            className="sr-input"
            value={selectedCol}
            onChange={(ev) => setSelectedCol(ev.target.value)}
          >
            {columns.map((col) => (
              <option key={col.name} value={col.name}>
                {col.label || col.name}
                {col.native_type ? ` (${col.native_type})` : ''}
              </option>
            ))}
          </select>
        </div>

        {/* Row 1: Font family + Font size */}
        <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10}}>
          <div className="sr-field">
            <label className="sr-field-label" htmlFor="col-display-font">
              {gettext('Font Family')}
            </label>
            <select
              id="col-display-font"
              className="sr-input"
              value={activePrefs.font || ''}
              onChange={(ev) => updateCurrentCol({font: ev.target.value})}
            >
              <option value="">{gettext('Default (Field-type / Theme)')}</option>
              <option value="system">{gettext('System UI')}</option>
              <option value="sans">{gettext('Sans-serif')}</option>
              <option value="serif">{gettext('Serif')}</option>
              <option value="mono">{gettext('Monospace')}</option>
            </select>
          </div>

          <div className="sr-field">
            <label className="sr-field-label" htmlFor="col-display-font-size">
              {gettext('Font Size')}
            </label>
            <select
              id="col-display-font-size"
              className="sr-input"
              value={activePrefs.fontSize || ''}
              onChange={(ev) => updateCurrentCol({fontSize: ev.target.value})}
            >
              <option value="">{gettext('Default')}</option>
              <option value="xs">{gettext('Compact (12px)')}</option>
              <option value="sm">{gettext('Standard (13px)')}</option>
              <option value="md">{gettext('Medium (14px)')}</option>
              <option value="lg">{gettext('Large (15px)')}</option>
            </select>
          </div>
        </div>

        {/* Row 2: Text Colour + Background Colour */}
        <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10}}>
          <div className="sr-field">
            <label className="sr-field-label" htmlFor="col-display-color">
              {gettext('Text Colour')}
            </label>
            <div style={{display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap'}}>
              <input
                id="col-display-color"
                aria-label={gettext('Text Colour')}
                type="color"
                value={
                  /^#[0-9a-fA-F]{6}$/.test(activePrefs.color || '')
                    ? activePrefs.color
                    : '#0f172a'
                }
                onChange={(ev) => updateCurrentCol({color: ev.target.value})}
                style={{width: 34, height: 28, padding: 1, cursor: 'pointer'}}
              />
              {TEXT_COLOR_SWATCHES.map((hex) => (
                <button
                  key={hex}
                  type="button"
                  title={hex}
                  aria-label={`${gettext('Text colour')} ${hex}`}
                  onClick={() => updateCurrentCol({color: hex})}
                  style={{
                    width: 18,
                    height: 18,
                    borderRadius: 4,
                    background: hex,
                    border:
                      activePrefs.color === hex
                        ? '2px solid var(--sr-accent, #0284c7)'
                        : '1px solid rgba(128,128,128,0.4)',
                    cursor: 'pointer',
                  }}
                />
              ))}
              {activePrefs.color && (
                <button
                  type="button"
                  className="sr-btn"
                  style={{fontSize: '0.72rem', padding: '1px 6px', minHeight: 22}}
                  onClick={() => updateCurrentCol({color: ''})}
                >
                  {gettext('Default')}
                </button>
              )}
            </div>
          </div>

          <div className="sr-field">
            <label className="sr-field-label" htmlFor="col-display-bg-color">
              {gettext('Cell Background Colour')}
            </label>
            <div style={{display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap'}}>
              <input
                id="col-display-bg-color"
                aria-label={gettext('Cell Background Colour')}
                type="color"
                value={
                  /^#[0-9a-fA-F]{6}$/.test(activePrefs.bgColor || '')
                    ? activePrefs.bgColor
                    : '#ffffff'
                }
                onChange={(ev) => updateCurrentCol({bgColor: ev.target.value})}
                style={{width: 34, height: 28, padding: 1, cursor: 'pointer'}}
              />
              {BG_COLOR_SWATCHES.map((hex) => (
                <button
                  key={hex}
                  type="button"
                  title={hex}
                  aria-label={`${gettext('Background colour')} ${hex}`}
                  onClick={() => updateCurrentCol({bgColor: hex})}
                  style={{
                    width: 18,
                    height: 18,
                    borderRadius: 4,
                    background: hex,
                    border:
                      activePrefs.bgColor === hex
                        ? '2px solid var(--sr-accent, #0284c7)'
                        : '1px solid rgba(128,128,128,0.4)',
                    cursor: 'pointer',
                  }}
                />
              ))}
              {activePrefs.bgColor && (
                <button
                  type="button"
                  className="sr-btn"
                  style={{fontSize: '0.72rem', padding: '1px 6px', minHeight: 22}}
                  onClick={() => updateCurrentCol({bgColor: ''})}
                >
                  {gettext('Default')}
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Row 3: Horizontal & Vertical Alignment */}
        <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10}}>
          <div className="sr-field">
            <label className="sr-field-label" htmlFor="col-display-halign">
              {gettext('Horizontal Alignment')}
            </label>
            <select
              id="col-display-halign"
              className="sr-input"
              value={activePrefs.hAlign || ''}
              onChange={(ev) => updateCurrentCol({hAlign: ev.target.value})}
            >
              <option value="">{gettext('Default (By Data Type)')}</option>
              <option value="left">{gettext('Left')}</option>
              <option value="center">{gettext('Center')}</option>
              <option value="right">{gettext('Right')}</option>
            </select>
          </div>

          <div className="sr-field">
            <label className="sr-field-label" htmlFor="col-display-valign">
              {gettext('Vertical Alignment')}
            </label>
            <select
              id="col-display-valign"
              className="sr-input"
              value={activePrefs.vAlign || 'middle'}
              onChange={(ev) => updateCurrentCol({vAlign: ev.target.value})}
            >
              <option value="top">{gettext('Top')}</option>
              <option value="middle">{gettext('Middle')}</option>
              <option value="bottom">{gettext('Bottom')}</option>
            </select>
          </div>
        </div>

        {/* Row 4: Wrap Mode + Max Displayed Lines in Wrap */}
        <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10}}>
          <div className="sr-field">
            <label className="sr-field-label" htmlFor="col-display-wrap">
              {gettext('Text Wrap')}
            </label>
            <select
              id="col-display-wrap"
              className="sr-input"
              value={activePrefs.wrapMode || 'none'}
              onChange={(ev) => {
                const mode = ev.target.value;
                updateCurrentCol({
                  wrapMode: mode,
                  maxWrapLines:
                    mode === 'clamp' && !activePrefs.maxWrapLines
                      ? 3
                      : activePrefs.maxWrapLines,
                });
              }}
            >
              <option value="none">{gettext('No Wrap (Single Line Ellipsis)')}</option>
              <option value="wrap">{gettext('Wrap Text')}</option>
              <option value="clamp">{gettext('Wrap up to Max Displayed Lines')}</option>
            </select>
          </div>

          <div className="sr-field">
            <label className="sr-field-label" htmlFor="col-display-max-wrap-lines">
              {gettext('Max Displayed Lines in Wrap')}
            </label>
            <input
              id="col-display-max-wrap-lines"
              type="number"
              className="sr-input"
              min={1}
              max={50}
              disabled={(activePrefs.wrapMode || 'none') === 'none'}
              placeholder={
                activePrefs.wrapMode === 'clamp' ? '3' : gettext('Unlimited')
              }
              value={activePrefs.maxWrapLines ?? ''}
              onChange={(ev) =>
                updateCurrentCol({
                  maxWrapLines:
                    ev.target.value === '' ? '' : Number(ev.target.value),
                })
              }
            />
          </div>
        </div>

        {/* Row 5: Minimum Width + Maximum Width */}
        <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10}}>
          <div className="sr-field">
            <label className="sr-field-label" htmlFor="col-display-min-width">
              {gettext('Minimum Width (px)')}
            </label>
            <input
              id="col-display-min-width"
              type="number"
              className="sr-input"
              min={32}
              max={1600}
              placeholder={String(DEFAULT_MIN_COL_WIDTH)}
              value={activePrefs.minWidth ?? ''}
              onChange={(ev) =>
                updateCurrentCol({
                  minWidth: ev.target.value === '' ? '' : Number(ev.target.value),
                })
              }
            />
          </div>

          <div className="sr-field">
            <label className="sr-field-label" htmlFor="col-display-max-width">
              {gettext('Maximum Width (px)')}
            </label>
            <input
              id="col-display-max-width"
              type="number"
              className="sr-input"
              min={48}
              max={3200}
              placeholder={String(DEFAULT_MAX_COL_WIDTH)}
              value={activePrefs.maxWidth ?? ''}
              onChange={(ev) =>
                updateCurrentCol({
                  maxWidth: ev.target.value === '' ? '' : Number(ev.target.value),
                })
              }
            />
          </div>
        </div>

        {/* Live sample preview */}
        <div
          data-cdeadmin-qa-key="column-display-live-preview"
          style={{
            padding: '8px 10px',
            borderRadius: 6,
            border: '1px solid var(--sr-border-default, rgba(128,128,128,0.28))',
            background: activePrefs.bgColor || 'var(--sr-surface-card, #ffffff)',
            color: activePrefs.color || 'var(--sr-text-primary, inherit)',
            fontFamily: FIELD_FONTS[activePrefs.font],
            fontSize: FIELD_FONT_SIZES[activePrefs.fontSize] || '0.8125rem',
            textAlign: activePrefs.hAlign || 'left',
          }}
        >
          <div
            style={{
              fontSize: '0.68rem',
              opacity: 0.68,
              marginBottom: 3,
              textAlign: 'left',
            }}
          >
            {gettext('Live Preview')} ·{' '}
            {gettext(
              'Min %spx / Max %spx',
              activePrefs.minWidth || DEFAULT_MIN_COL_WIDTH,
              activePrefs.maxWidth || DEFAULT_MAX_COL_WIDTH
            )}
          </div>
          <div
            style={{
              whiteSpace: previewWrap === 'none' ? 'nowrap' : 'pre-wrap',
              overflow: 'hidden',
              textOverflow: previewWrap === 'none' ? 'ellipsis' : 'clip',
              display: previewMaxLines !== null ? '-webkit-box' : 'block',
              WebkitLineClamp: previewMaxLines ?? undefined,
              WebkitBoxOrient: previewMaxLines !== null ? 'vertical' : undefined,
              wordBreak: previewWrap !== 'none' ? 'break-word' : undefined,
            }}
          >
            {gettext(
              'Sample value for %s — revisiting this table or view restores your preferred display settings.',
              selectedCol || 'column'
            )}
          </div>
        </div>

        {/* Persistence & Template section */}
        {canPersistObjectLayout && (
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              cursor: 'pointer',
              fontWeight: 500,
            }}
          >
            <input
              type="checkbox"
              checked={persistToDb}
              onChange={(ev) => setPersistToDb(ev.target.checked)}
            />
            <span>
              {objectLabel
                ? gettext(
                  'Save in UserConfigurationDatabase for %s (auto-apply on revisit)',
                  objectLabel
                )
                : gettext(
                  'Save in UserConfigurationDatabase for this table/view (auto-apply on revisit)'
                )}
            </span>
          </label>
        )}

        {(onSaveTemplate || templates.length > 0) && (
          <div
            style={{
              borderTop: '1px solid var(--sr-border-subtle, rgba(128,128,128,0.22))',
              paddingTop: 10,
              display: 'grid',
              gap: 8,
            }}
          >
            {onSaveTemplate && (
              <div style={{display: 'flex', gap: 8, alignItems: 'center'}}>
                <input
                  type="text"
                  className="sr-input"
                  aria-label={gettext('Save preferences as template name')}
                  placeholder={gettext('Template name (save preferences as template)…')}
                  value={templateName}
                  onChange={(ev) => setTemplateName(ev.target.value)}
                  style={{flex: 1}}
                />
                <Button
                  size="small"
                  disabled={saving}
                  onClick={handleSaveAsTemplate}
                >
                  {gettext('Save as Template')}
                </Button>
              </div>
            )}

            {templates.length > 0 && (
              <div style={{display: 'flex', gap: 8, alignItems: 'center'}}>
                <select
                  className="sr-input"
                  aria-label={gettext('Apply saved template')}
                  value={selectedTemplateId}
                  onChange={(ev) => setSelectedTemplateId(ev.target.value)}
                  style={{flex: 1}}
                >
                  <option value="">{gettext('Select a saved template…')}</option>
                  {templates.map((tpl) => (
                    <option key={tpl.template_id} value={tpl.template_id}>
                      {tpl.name}
                    </option>
                  ))}
                </select>
                <Button
                  size="small"
                  disabled={!selectedTemplateId}
                  onClick={handleApplySelectedTemplate}
                >
                  {gettext('Apply Template')}
                </Button>
              </div>
            )}
          </div>
        )}

        {statusMessage && (
          <div
            role="status"
            style={{
              padding: '6px 10px',
              borderRadius: 6,
              background: 'rgba(16, 185, 129, 0.12)',
              color: '#065f46',
            }}
          >
            {statusMessage}
          </div>
        )}
        {error && (
          <div
            role="alert"
            style={{
              padding: '6px 10px',
              borderRadius: 6,
              background: 'rgba(239, 68, 68, 0.12)',
              color: '#991b1b',
            }}
          >
            {error}
          </div>
        )}
      </div>
    </Dialog>
  );
}

ColumnDisplaySettingsDialog.propTypes = {
  open: PropTypes.bool,
  columns: PropTypes.arrayOf(PropTypes.object),
  initialColumnName: PropTypes.string,
  layout: PropTypes.object,
  objectLabel: PropTypes.string,
  canPersistObjectLayout: PropTypes.bool,
  templates: PropTypes.arrayOf(PropTypes.object),
  onClose: PropTypes.func.isRequired,
  onApplyLayout: PropTypes.func,
  onSaveObjectLayout: PropTypes.func,
  onSaveTemplate: PropTypes.func,
  onRequestTemplates: PropTypes.func,
};
