/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import {Box, ScrollArea, Stack} from '../../primitives/Layout';
import {Button, IconButton} from '../../primitives/Button';
import {NumberField, TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {Dialog} from '../../overlays/Dialog';
import {StatusBadge} from '../../status/StatusBadge';
import {Banner} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import {Tab} from '../../navigation/TabsAndBreadcrumbs';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
import {Icon, inferActionIconKey} from '../../icons';
import {t_actions} from '../../actions/t_actions';
import {ensureScratchBaseStyles} from '../../base/ScratchBaseStyles';
import {ScratchScrollArea} from '../../base/ScratchScrollArea';

/**
 * Grouped tabbed-menu ribbon for ScratchRobin's four DDN task designers.
 * Replaces flat wrapping button walls with structured category tabs,
 * semantic command icons, `t_actions` status awareness, and standard `[x]` close.
 */
export function DesignerTabbedMenu({
  label = 'Designer menu',
  tabs = [],
  activeTab: controlledTab,
  onTabChange,
  leading = null,
  trailing = null,
  onClose = null,
}) {
  const [internalTab, setInternalTab] = useState(tabs[0]?.id || '');
  const currentId = controlledTab ?? internalTab;
  const active = tabs.find((tab) => tab.id === currentId) || tabs[0] || null;
  const selectTab = (tabId) => {
    if (controlledTab === undefined) setInternalTab(tabId);
    onTabChange?.(tabId);
  };

  return (
    <Box
      component="nav"
      aria-label={label}
      data-cdeadmin-qa-key="designer-tabbed-menu"
      sx={{
        flexShrink: 0,
        borderBottom: '1px solid',
        borderColor: 'divider',
        bgcolor: 'background.paper',
      }}
    >
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 0.75,
          px: 1,
          minHeight: 'var(--cde-tab-height, 32px)',
          borderBottom: '1px solid',
          borderColor: 'divider',
        }}
      >
        {leading && (
          <Box sx={{display: 'flex', alignItems: 'center', gap: 0.75, mr: 0.5}}>
            {leading}
          </Box>
        )}
        <Box
          role="tablist"
          aria-label={`${label} categories`}
          sx={{display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 0.25}}
        >
          {tabs.map((tab) => (
            <Tab
              key={tab.id}
              label={tab.label}
              active={tab.id === active?.id}
              attention={Boolean(tab.attention)}
              dirty={Boolean(tab.dirty)}
              disabled={Boolean(tab.disabled)}
              onActivate={() => selectTab(tab.id)}
            />
          ))}
        </Box>
        {(trailing || onClose) && (
          <Box
            sx={{
              ml: 'auto',
              display: 'flex',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: 0.75,
              py: 0.25,
            }}
          >
            {trailing}
            {onClose && (
              <IconButton
                label={`Close ${label}`}
                data-cdeadmin-qa-key="designer-tabbed-menu-close"
                onClick={onClose}
              >
                ×
              </IconButton>
            )}
          </Box>
        )}
      </Box>
      {active && (
        <Box
          role="tabpanel"
          aria-label={`${active.label} commands`}
          data-cdeadmin-qa-key={`designer-menu-panel.${active.id}`}
          sx={{
            display: 'flex',
            alignItems: 'stretch',
            flexWrap: 'wrap',
            gap: 1,
            px: 1,
            py: 0.5,
            minHeight: 'calc(var(--cde-toolbar-height, 32px) + 6px)',
            bgcolor: 'background.default',
          }}
        >
          {(active.groups || []).map((group, idx) => (
            <Box
              key={group.id || group.label || idx}
              role="group"
              aria-label={group.label || active.label}
              sx={{
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
                gap: 0.25,
                pr: 1.25,
                borderRight:
                  idx < active.groups.length - 1 ? '1px solid' : 'none',
                borderColor: 'divider',
              }}
            >
              {group.label && (
                <Box
                  component="span"
                  sx={{
                    fontSize: '0.6875rem',
                    fontWeight: 600,
                    letterSpacing: '0.03em',
                    textTransform: 'uppercase',
                    color: 'text.secondary',
                    lineHeight: 1.1,
                  }}
                >
                  {group.label}
                </Box>
              )}
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: 0.5,
                }}
              >
                {(group.items || []).map((item, itemIdx) => {
                  if (item.render) {
                    return (
                      <Box key={item.id || itemIdx} sx={{display: 'inline-flex', alignItems: 'center'}}>
                        {item.render()}
                      </Box>
                    );
                  }
                  const resolvedAction =
                    item.actionId && t_actions.has(item.actionId)
                      ? t_actions.resolve(item.actionId)
                      : null;
                  if (resolvedAction && !resolvedAction.visible) {
                    return null;
                  }
                  const buttonLabel = resolvedAction?.text || item.label;
                  const buttonHint = resolvedAction?.hint || item.hint || '';
                  const iconKey =
                    resolvedAction?.icon ||
                    item.icon ||
                    item.iconKey ||
                    inferActionIconKey({name: item.id, label: buttonLabel}) ||
                    'command.default';
                  const isDisabled =
                    Boolean(item.disabled) ||
                    (resolvedAction ? !resolvedAction.enabled : false);
                  return (
                    <Button
                      key={item.id || item.label || itemIdx}
                      size="small"
                      intent={
                        item.intent ||
                        (item.active ? 'primary' : 'neutral')
                      }
                      title={buttonHint || undefined}
                      disabled={isDisabled}
                      onClick={
                        item.onClick ||
                        (resolvedAction
                          ? () => t_actions.execute(resolvedAction.id)
                          : undefined)
                      }
                      data-cdeadmin-qa-key={item.qaKey || item.id || undefined}
                    >
                      <Box component="span" sx={{display: 'inline-flex', alignItems: 'center', gap: 0.5}}>
                        <Icon iconKey={iconKey} decorative size="0.95em" />
                        <span>
                          {buttonLabel}
                          {item.badge !== undefined && item.badge !== null && item.badge !== ''
                            ? ` (${item.badge})`
                            : ''}
                        </span>
                      </Box>
                    </Button>
                  );
                })}
              </Box>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}

DesignerTabbedMenu.propTypes = {
  label: PropTypes.string,
  tabs: PropTypes.arrayOf(
    PropTypes.shape({
      id: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired,
      attention: PropTypes.bool,
      dirty: PropTypes.bool,
      disabled: PropTypes.bool,
      groups: PropTypes.arrayOf(
        PropTypes.shape({
          id: PropTypes.string,
          label: PropTypes.string,
          items: PropTypes.array,
        })
      ),
    })
  ),
  activeTab: PropTypes.string,
  onTabChange: PropTypes.func,
  leading: PropTypes.node,
  trailing: PropTypes.node,
  onClose: PropTypes.func,
};

/**
 * Canonical ScratchRobin tabbed form body for designer dialogs
 * (matching ObjectEditor.jsx and docs/en_US/ui_unified_design.rst).
 */
export function DesignerModalTabs({
  tabs = [],
  activeTab: controlledTab,
  onTabChange,
  formKey = '',
  banner = null,
  minHeight = 280,
}) {
  const [internalTab, setInternalTab] = useState(tabs[0]?.id || '');
  const currentId = controlledTab ?? internalTab;
  const active = tabs.find((t) => t.id === currentId) || tabs[0] || null;
  const selectTab = (id) => {
    if (controlledTab === undefined) setInternalTab(id);
    onTabChange?.(id);
  };

  return (
    <Box sx={{display: 'flex', flexDirection: 'column', minHeight}}>
      {formKey && <FormReference formKey={formKey} />}
      {banner}
      {tabs.length > 1 && (
        <Box
          role="tablist"
          aria-label="Dialog sections"
          sx={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 0.25,
            borderBottom: '1px solid',
            borderColor: 'divider',
            mb: 1.5,
          }}
        >
          {tabs.map((tab) => (
            <Tab
              key={tab.id}
              label={tab.label}
              active={tab.id === active?.id}
              attention={Boolean(tab.attention)}
              dirty={Boolean(tab.dirty)}
              disabled={Boolean(tab.disabled)}
              onActivate={() => selectTab(tab.id)}
            />
          ))}
        </Box>
      )}
      {active && (
        <Box
          role="tabpanel"
          aria-label={active.label}
          sx={{flex: 1, minHeight: 0, pt: tabs.length > 1 ? 0.5 : 0}}
        >
          {typeof active.render === 'function' ? active.render() : active.content}
        </Box>
      )}
    </Box>
  );
}

DesignerModalTabs.propTypes = {
  tabs: PropTypes.arrayOf(
    PropTypes.shape({
      id: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired,
      attention: PropTypes.bool,
      dirty: PropTypes.bool,
      disabled: PropTypes.bool,
      content: PropTypes.node,
      render: PropTypes.func,
    })
  ),
  activeTab: PropTypes.string,
  onTabChange: PropTypes.func,
  formKey: PropTypes.string,
  banner: PropTypes.node,
  minHeight: PropTypes.number,
};

/**
 * Responsive multi-column field layout obeying compact_forms.rst.
 */
export function FormGrid({columns = 2, children, sx = {}}) {
  const template =
    columns === 1
      ? '1fr'
      : `repeat(auto-fit, minmax(${columns >= 3 ? '180px' : '230px'}, 1fr))`;
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: template,
        gap: 1.5,
        alignItems: 'start',
        ...sx,
      }}
    >
      {children}
    </Box>
  );
}

FormGrid.propTypes = {
  columns: PropTypes.number,
  children: PropTypes.node,
  sx: PropTypes.object,
};

/**
 * Typed tabular record editor replacing raw JSON textareas and CSV strings
 * (ui_unified_design.rst Principle 3: json is not a user-facing control).
 */
export function TypedRowsEditor({
  label,
  columns = [],
  rows = [],
  onChange,
  addLabel = 'Add row',
  emptyText = 'No entries configured.',
  disabled = false,
  reorderable = false,
}) {
  const makeDefaultRow = () => {
    const next = {};
    for (const col of columns) {
      if (col.default !== undefined) next[col.key] = col.default;
      else if (col.type === 'boolean') next[col.key] = false;
      else if (col.type === 'number') next[col.key] = 0;
      else if (col.type === 'select') next[col.key] = col.options?.[0]?.value ?? '';
      else next[col.key] = '';
    }
    return next;
  };

  const updateCell = (idx, key, val) => {
    onChange?.(rows.map((r, i) => (i === idx ? {...r, [key]: val} : r)));
  };
  const removeRow = (idx) => {
    onChange?.(rows.filter((_, i) => i !== idx));
  };
  const moveRow = (idx, delta) => {
    const target = idx + delta;
    if (target < 0 || target >= rows.length) return;
    const copy = rows.slice();
    [copy[idx], copy[target]] = [copy[target], copy[idx]];
    onChange?.(copy);
  };

  ensureScratchBaseStyles();
  return (
    <Box
      role="group"
      aria-label={label}
      className="sr-bui-table-card"
    >
      <Box
        className="sr-bui-toolbar"
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 1,
        }}
      >
        <Box component="span" className="sr-bui-toolbar-title">
          {label}
        </Box>
        <Button
          size="small"
          intent="neutral"
          disabled={disabled}
          onClick={() => onChange?.([...rows, makeDefaultRow()])}
        >
          + {addLabel}
        </Button>
      </Box>
      {rows.length === 0 ? (
        <Box sx={{fontSize: '0.75rem', color: 'text.secondary', px: 1.5, py: 1}}>
          {emptyText}
        </Box>
      ) : (
        <ScratchScrollArea orientation="both" style={{width: '100%'}}>
          <Box
            component="table"
            className="sr-bui-table"
            aria-label={label}
            sx={{width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem'}}
          >
            <Box component="thead">
              <Box component="tr">
                {columns.map((col) => (
                  <Box
                    key={col.key}
                    component="th"
                    className="sr-bui-th"
                    scope="col"
                    sx={{
                      textAlign: 'left',
                      minWidth: col.minWidth || 110,
                    }}
                  >
                    {col.label}
                  </Box>
                ))}
                <Box
                  component="th"
                  className="sr-bui-th"
                  scope="col"
                  sx={{
                    width: reorderable ? 88 : 40,
                  }}
                />
              </Box>
            </Box>
            <Box component="tbody">
              {rows.map((row, idx) => (
                <Box key={idx} component="tr" className="sr-bui-tr">
                  {columns.map((col) => (
                    <Box
                      key={col.key}
                      component="td"
                      className="sr-bui-td"
                      sx={{verticalAlign: 'middle'}}
                    >
                      {col.type === 'select' ? (
                        <Select
                          aria-label={`${col.label} row ${idx + 1}`}
                          size="small"
                          fullWidth
                          disabled={disabled}
                          value={row[col.key] ?? ''}
                          options={col.options || []}
                          onChange={(val) => updateCell(idx, col.key, val)}
                        />
                      ) : col.type === 'boolean' ? (
                        <Checkbox
                          label={col.checkboxLabel || ''}
                          checked={Boolean(row[col.key])}
                          disabled={disabled}
                          onChange={(checked) => updateCell(idx, col.key, checked)}
                        />
                      ) : col.type === 'number' ? (
                        <NumberField
                          aria-label={`${col.label} row ${idx + 1}`}
                          size="small"
                          fullWidth
                          disabled={disabled}
                          value={row[col.key] ?? ''}
                          onChange={(e) =>
                            updateCell(
                              idx,
                              col.key,
                              e.target.value === '' ? '' : Number(e.target.value)
                            )
                          }
                        />
                      ) : (
                        <TextField
                          aria-label={`${col.label} row ${idx + 1}`}
                          size="small"
                          fullWidth
                          disabled={disabled}
                          placeholder={col.placeholder || ''}
                          value={row[col.key] ?? ''}
                          onChange={(e) => updateCell(idx, col.key, e.target.value)}
                        />
                      )}
                    </Box>
                  ))}
                  <Box
                    component="td"
                    className="sr-bui-td"
                    sx={{
                      whiteSpace: 'nowrap',
                      verticalAlign: 'middle',
                    }}
                  >
                    {reorderable && (
                      <>
                        <IconButton
                          label={`Move row ${idx + 1} up`}
                          disabled={disabled || idx === 0}
                          onClick={() => moveRow(idx, -1)}
                        >
                          ↑
                        </IconButton>
                        <IconButton
                          label={`Move row ${idx + 1} down`}
                          disabled={disabled || idx === rows.length - 1}
                          onClick={() => moveRow(idx, 1)}
                        >
                          ↓
                        </IconButton>
                      </>
                    )}
                    <IconButton
                      label={`Remove row ${idx + 1}`}
                      disabled={disabled}
                      onClick={() => removeRow(idx)}
                    >
                      ×
                    </IconButton>
                  </Box>
                </Box>
              ))}
            </Box>
          </Box>
        </ScratchScrollArea>
      )}
    </Box>
  );
}

TypedRowsEditor.propTypes = {
  label: PropTypes.string.isRequired,
  columns: PropTypes.arrayOf(
    PropTypes.shape({
      key: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired,
      type: PropTypes.oneOf(['text', 'number', 'select', 'boolean']),
      options: PropTypes.array,
      placeholder: PropTypes.string,
      minWidth: PropTypes.number,
      default: PropTypes.any,
      checkboxLabel: PropTypes.string,
    })
  ),
  rows: PropTypes.array,
  onChange: PropTypes.func,
  addLabel: PropTypes.string,
  emptyText: PropTypes.string,
  disabled: PropTypes.bool,
  reorderable: PropTypes.bool,
};

/**
 * Typed key/value dictionary editor backed by TypedRowsEditor.
 */
export function KeyValuePairsEditor({
  label,
  value = {},
  onChange,
  keyLabel = 'Key',
  valueLabel = 'Value',
  keyPlaceholder = '',
  valuePlaceholder = '',
  disabled = false,
}) {
  const externalRows = useMemo(
    () =>
      Object.entries(value || {}).map(([k, v]) => ({
        key: k,
        value: typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v ?? ''),
      })),
    [value]
  );
  const [draftRows, setDraftRows] = useState(externalRows);
  useEffect(() => {
    setDraftRows((prev) => {
      const pendingBlank = prev.filter((r) => !String(r.key || '').trim());
      return pendingBlank.length ? [...externalRows, ...pendingBlank] : externalRows;
    });
  }, [externalRows]);
  const handleChange = (nextRows) => {
    setDraftRows(nextRows);
    const out = {};
    for (const r of nextRows) {
      const k = String(r.key || '').trim();
      if (!k) continue;
      const raw = String(r.value ?? '');
      if (raw === 'true') out[k] = true;
      else if (raw === 'false') out[k] = false;
      else if (raw !== '' && !Number.isNaN(Number(raw)) && /^-?\d+(\.\d+)?$/.test(raw)) {
        out[k] = Number(raw);
      } else {
        out[k] = raw;
      }
    }
    onChange?.(out);
  };
  return (
    <TypedRowsEditor
      label={label}
      rows={draftRows}
      disabled={disabled}
      addLabel={`Add ${keyLabel.toLowerCase()}`}
      columns={[
        {key: 'key', label: keyLabel, placeholder: keyPlaceholder, minWidth: 140},
        {key: 'value', label: valueLabel, placeholder: valuePlaceholder, minWidth: 180},
      ]}
      onChange={handleChange}
    />
  );
}

KeyValuePairsEditor.propTypes = {
  label: PropTypes.string.isRequired,
  value: PropTypes.object,
  onChange: PropTypes.func,
  keyLabel: PropTypes.string,
  valueLabel: PropTypes.string,
  keyPlaceholder: PropTypes.string,
  valuePlaceholder: PropTypes.string,
  disabled: PropTypes.bool,
};

/**
 * Shared Checkpoint History, Visual Diff & Restore/Branch Dialog
 * across ERD, Cube, BI and Screen Mesh designers.
 */
export function DesignCheckpointHistoryDrawer({
  open,
  onClose,
  client,
  projectId,
  designId,
  currentVersion,
  activeVersion,
  onOpenVersion,
  onRestored,
}) {
  const [versions, setVersions] = useState([]);
  const [baseVer, setBaseVer] = useState('');
  const [targetVer, setTargetVer] = useState('');
  const [diffResult, setDiffResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('history');

  useEffect(() => {
    if (!open || !client || !projectId || !designId) return;
    let active = true;
    setBusy(true);
    setError('');
    Promise.resolve(client.listVersions?.(projectId, designId))
      .then((list) => {
        if (!active) return;
        const items = Array.isArray(list) ? list : list?.versions || [];
        setVersions(items);
        if (items.length >= 2) {
          setBaseVer(String(items[items.length - 2].version));
          setTargetVer(String(items[items.length - 1].version));
        } else if (items.length === 1) {
          setBaseVer(String(items[0].version));
          setTargetVer(String(items[0].version));
        }
      })
      .catch((err) => active && setError(err?.message || String(err)))
      .finally(() => active && setBusy(false));
    return () => {
      active = false;
    };
  }, [open, client, projectId, designId]);

  const runCompare = async () => {
    if (!baseVer || !targetVer) return;
    setBusy(true);
    setError('');
    try {
      if (typeof client.diffDesignVersions === 'function') {
        const res = await client.diffDesignVersions(projectId, designId, {
          baseVersion: Number(baseVer),
          targetVersion: Number(targetVer),
        });
        setDiffResult(res);
      } else {
        const [a, b] = await Promise.all([
          client.openSession(projectId, designId, {version: Number(baseVer)}),
          client.openSession(projectId, designId, {version: Number(targetVer)}),
        ]);
        const aLines = String(a?.design?.version?.ddn_text || '').split('\n');
        const bLines = String(b?.design?.version?.ddn_text || '').split('\n');
        const unified = [
          `--- v${baseVer}`,
          `+++ v${targetVer}`,
          ...aLines.filter((l) => !bLines.includes(l)).map((l) => `- ${l}`),
          ...bLines.filter((l) => !aLines.includes(l)).map((l) => `+ ${l}`),
        ].join('\n');
        setDiffResult({
          base_version: Number(baseVer),
          target_version: Number(targetVer),
          unified_diff: unified || '-- Identical DDN text.',
          added_elements: [],
          removed_elements: [],
          modified_elements: [],
        });
      }
      setTab('diff');
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const restoreAsDraft = async (ver) => {
    setBusy(true);
    setError('');
    try {
      const snap = await client.openSession(projectId, designId, {
        version: Number(ver),
      });
      const head = versions.reduce(
        (m, item) => Math.max(m, Number(item.version) || 0),
        Number(currentVersion) || 1
      );
      const saved = await client.saveVersion(projectId, designId, {
        expected_head_version: head,
        ddn_text: snap?.design?.version?.ddn_text || '',
        status: 'draft',
        note: `Branched draft from checkpoint v${ver}`,
      });
      const newVer = saved?.design?.version?.version ?? head + 1;
      onRestored?.(newVer);
      onClose?.();
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const versionOptions = versions.map((v) => ({
    value: String(v.version),
    label: `v${v.version} (${v.status})${v.note ? ` — ${v.note}` : ''}`,
  }));

  return (
    <Dialog
      open={Boolean(open)}
      onClose={onClose}
      title="Checkpoints, Directed Save Points & Version Diff"
      size="large"
      busy={busy}
      actions={<Button onClick={onClose}>Close</Button>}
    >
      <DesignerModalTabs
        formKey="design-checkpoints-diff"
        activeTab={tab}
        onTabChange={setTab}
        banner={error ? <Banner status="error">{error}</Banner> : null}
        tabs={[
          {
            id: 'history',
            label: `Checkpoints (${versions.length})`,
            render: () =>
              versions.length === 0 ? (
                <EmptyState message="No checkpoints recorded yet." />
              ) : (
                <ScrollArea label="Checkpoints list" sx={{maxHeight: 380}}>
                  <Box className="sr-bui-table-card">
                    <Box
                      component="table"
                      className="sr-bui-table"
                      aria-label="Design checkpoints"
                      sx={{width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem'}}
                    >
                      <Box component="thead">
                        <Box component="tr">
                          {['Version', 'Status', 'Parent', 'Summary / Note', 'Created', 'Actions'].map(
                            (h) => (
                              <Box
                                key={h}
                                component="th"
                                className="sr-bui-th"
                                sx={{textAlign: 'left'}}
                              >
                                {h}
                              </Box>
                            )
                          )}
                        </Box>
                      </Box>
                      <Box component="tbody">
                        {versions
                          .slice()
                          .reverse()
                          .map((item) => (
                            <Box key={item.version} component="tr" className="sr-bui-tr">
                              <Box component="td" className="sr-bui-td">
                                <strong>v{item.version}</strong>
                                {Number(item.version) === Number(activeVersion)
                                  ? ' (Active)'
                                  : ''}
                                {Number(item.version) === Number(currentVersion)
                                  ? ' · Loaded'
                                  : ''}
                              </Box>
                              <Box component="td" className="sr-bui-td">
                                <StatusBadge
                                  status={
                                    item.status === 'accepted'
                                      ? 'success'
                                      : item.status === 'in_review'
                                        ? 'warning'
                                        : 'info'
                                  }
                                  label={item.status}
                                />
                              </Box>
                              <Box component="td" className="sr-bui-td">
                                {(item.parent_version ?? item.base_version)
                                  ? `v${item.parent_version ?? item.base_version}`
                                  : '—'}
                              </Box>
                              <Box component="td" className="sr-bui-td">
                                {item.note || '—'}
                              </Box>
                              <Box
                                component="td"
                                className="sr-bui-td"
                                sx={{fontSize: '0.75rem', color: 'text.secondary'}}
                              >
                                {item.created_at || item.saved_at || '—'}
                              </Box>
                              <Box
                                component="td"
                                className="sr-bui-td"
                                sx={{whiteSpace: 'nowrap'}}
                              >
                                <Stack direction="row" gap="compact">
                                  <Button
                                    size="small"
                                    onClick={() => {
                                      onOpenVersion?.(Number(item.version));
                                      onClose?.();
                                    }}
                                  >
                                    Inspect
                                  </Button>
                                  <Button
                                    size="small"
                                    onClick={() => restoreAsDraft(item.version)}
                                  >
                                    Branch Draft
                                  </Button>
                                </Stack>
                              </Box>
                            </Box>
                          ))}
                      </Box>
                    </Box>
                  </Box>
                </ScrollArea>
              ),
          },
          {
            id: 'diff',
            label: 'Compare Checkpoints (DDN Diff)',
            render: () => (
              <Stack gap="standard">
                <FormGrid columns={3}>
                  <Select
                    label="Base Checkpoint"
                    value={baseVer}
                    options={versionOptions}
                    onChange={setBaseVer}
                  />
                  <Select
                    label="Target Checkpoint"
                    value={targetVer}
                    options={versionOptions}
                    onChange={setTargetVer}
                  />
                  <Box sx={{pt: 2.25}}>
                    <Button intent="primary" disabled={busy || !baseVer || !targetVer} onClick={runCompare}>
                      Compare Versions
                    </Button>
                  </Box>
                </FormGrid>
                {diffResult && (
                  <Stack gap="compact">
                    <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap'}}>
                      <StatusBadge
                        status="success"
                        label={`+${(diffResult.added_elements || []).length} added`}
                      />
                      <StatusBadge
                        status="warning"
                        label={`~${(diffResult.modified_elements || []).length} modified`}
                      />
                      <StatusBadge
                        status="error"
                        label={`-${(diffResult.removed_elements || []).length} removed`}
                      />
                    </Box>
                    <Box sx={{minHeight: 220}}>
                      <CodeEditor
                        label="Checkpoint DDN Diff"
                        value={diffResult.unified_diff || '-- No DDN differences.'}
                        readonly
                        language="sql"
                      />
                    </Box>
                  </Stack>
                )}
              </Stack>
            ),
          },
        ]}
      />
    </Dialog>
  );
}

DesignCheckpointHistoryDrawer.propTypes = {
  open: PropTypes.bool,
  onClose: PropTypes.func,
  client: PropTypes.object,
  projectId: PropTypes.string,
  designId: PropTypes.string,
  currentVersion: PropTypes.number,
  activeVersion: PropTypes.number,
  onOpenVersion: PropTypes.func,
  onRestored: PropTypes.func,
};

/**
 * Shared "Where Used in Designs / Impact Explorer" dialog across all 4 designers.
 */
export function WhereUsedDialog({
  open,
  onClose,
  client,
  projectId,
  initialTargetRef = '',
  designId = '',
}) {
  const [targetRef, setTargetRef] = useState(initialTargetRef);
  const [results, setResults] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setTargetRef(initialTargetRef || '');
  }, [initialTargetRef]);

  const runSearch = async (queryRef = targetRef) => {
    if (!client || !projectId) return;
    setBusy(true);
    setError('');
    try {
      if (typeof client.queryWhereUsed === 'function') {
        const data = await client.queryWhereUsed(projectId, {
          targetRef: queryRef,
          designId,
          includeSuspect: true,
        });
        setResults(Array.isArray(data) ? data : data?.usages || []);
      } else if (typeof client.queryScreenMeshUsage === 'function') {
        const data = await client.queryScreenMeshUsage(projectId, {
          targetRef: queryRef,
          includeSuspect: true,
        });
        setResults(Array.isArray(data) ? data : data?.usages || []);
      }
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (open && projectId) {
      runSearch(initialTargetRef || '');
    }
  }, [open, projectId, initialTargetRef]);

  return (
    <Dialog
      open={Boolean(open)}
      onClose={onClose}
      title="Where Used Across Designs (ERD · Cubes · BI · Screen Meshes)"
      size="large"
      busy={busy}
      actions={<Button onClick={onClose}>Close</Button>}
    >
      <Stack gap="standard">
        <FormReference formKey="design-where-used" />
        {error && <Banner status="error">{error}</Banner>}
        <FormGrid columns={2}>
          <TextField
            label="Filter by Catalog Table / Column / Cube / Design Ref"
            placeholder="e.g. main.work_orders or cube:operations"
            value={targetRef}
            onChange={(e) => setTargetRef(e.target.value)}
          />
          <Box sx={{pt: 2.25}}>
            <Button intent="primary" onClick={() => runSearch(targetRef)}>
              Search Cross-Design References
            </Button>
          </Box>
        </FormGrid>
        {results.length === 0 ? (
          <EmptyState message="No cross-design references matched this filter." />
        ) : (
          <ScrollArea label="Cross-design usage results" sx={{maxHeight: 340}}>
            <Box className="sr-bui-table-card">
              <Box
                component="table"
                className="sr-bui-table"
                aria-label="Where used results"
                sx={{width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem'}}
              >
                <Box component="thead">
                  <Box component="tr">
                    {['Design Kind', 'Design Title', 'Element', 'Target Reference', 'Validity'].map(
                      (h) => (
                        <Box
                          key={h}
                          component="th"
                          className="sr-bui-th"
                          sx={{textAlign: 'left'}}
                        >
                          {h}
                        </Box>
                      )
                    )}
                  </Box>
                </Box>
                <Box component="tbody">
                  {results.map((item, idx) => (
                    <Box key={item.binding_id || idx} component="tr" className="sr-bui-tr">
                      <Box component="td" className="sr-bui-td">
                        <strong>{item.design_kind || item.kind || 'design'}</strong>
                      </Box>
                      <Box component="td" className="sr-bui-td">
                        {item.design_title || item.title || item.design_id}
                      </Box>
                      <Box component="td" className="sr-bui-td">
                        {item.element_label || item.element_id || '—'}
                      </Box>
                      <Box component="td" className="sr-bui-td">
                        <code>{item.target_ref || '—'}</code>
                      </Box>
                      <Box component="td" className="sr-bui-td">
                        <StatusBadge
                          status={
                            item.validity === 'suspect'
                              ? 'warning'
                              : item.validity === 'valid'
                                ? 'success'
                                : 'info'
                          }
                          label={item.validity || 'referenced'}
                        />
                      </Box>
                    </Box>
                  ))}
                </Box>
              </Box>
            </Box>
          </ScrollArea>
        )}
      </Stack>
    </Dialog>
  );
}

WhereUsedDialog.propTypes = {
  open: PropTypes.bool,
  onClose: PropTypes.func,
  client: PropTypes.object,
  projectId: PropTypes.string,
  initialTargetRef: PropTypes.string,
  designId: PropTypes.string,
};
