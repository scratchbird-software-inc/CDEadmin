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
import {Popover as BasePopover} from '@base-ui/react/popover';
import {Tooltip as BaseTooltip} from '@base-ui/react/tooltip';
import {ensureScratchBaseStyles} from '../base/ScratchBaseStyles';
import {ScratchScrollArea} from '../base/ScratchScrollArea';
import {readBranchedTreePreferences} from './ScratchBranchedTree';
import {Button, IconButton} from '../primitives/Button';
import {Checkbox, Select} from '../primitives/Choice';
import {SearchField} from '../primitives/AdvancedControls';
import {Dialog} from '../overlays/Dialog';
import {EmptyState} from '../feedback/EmptyState';
import {ProgressOverlay} from '../feedback/ProgressOverlay';
import {Badge, EnvironmentIndicator} from '../feedback/Indicators';

const EMPTY_ITEMS = Object.freeze([]);

export function Popover({open, anchorEl, onClose, children, label = 'Details'}) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);

  return (
    <BasePopover.Root
      open={Boolean(open)}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose?.();
      }}
    >
      <BasePopover.Portal>
        <BasePopover.Positioner
          anchor={anchorEl || undefined}
          side="bottom"
          align="start"
          sideOffset={4}
          style={{zIndex: 'var(--cde-layer-popover, 2400)'}}
        >
          <BasePopover.Popup
            aria-label={label}
            className="sr-popover-popup"
            style={{minWidth: 220, maxWidth: 420}}
          >
            {children}
          </BasePopover.Popup>
        </BasePopover.Positioner>
      </BasePopover.Portal>
    </BasePopover.Root>
  );
}

Popover.propTypes = {
  open: PropTypes.bool.isRequired,
  anchorEl: PropTypes.object,
  onClose: PropTypes.func,
  children: PropTypes.node,
  label: PropTypes.string,
};

export function Tooltip({title, children}) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);
  if (!title) return children;

  return (
    <BaseTooltip.Provider delay={450} closeDelay={80}>
      <BaseTooltip.Root>
        <BaseTooltip.Trigger render={children} />
        <BaseTooltip.Portal>
          <BaseTooltip.Positioner sideOffset={6} style={{zIndex: 'var(--cde-layer-tooltip, 3000)'}}>
            <BaseTooltip.Popup
              style={{
                padding: '4px 8px',
                borderRadius: 6,
                border: '1px solid var(--sr-border-default)',
                background: 'var(--sr-surface-elevated)',
                color: 'var(--sr-text-primary)',
                fontSize: '0.75rem',
                boxShadow: 'var(--sr-popup-shadow)',
                pointerEvents: 'none',
              }}
            >
              {title}
            </BaseTooltip.Popup>
          </BaseTooltip.Positioner>
        </BaseTooltip.Portal>
      </BaseTooltip.Root>
    </BaseTooltip.Provider>
  );
}

Tooltip.propTypes = {
  title: PropTypes.node.isRequired,
  children: PropTypes.element.isRequired,
};

export function ListRow({
  label,
  icon,
  trailing,
  selected = false,
  disabled = false,
  status = 'default',
  onSelect,
  onOpen,
}) {
  return (
    <div
      role="option"
      aria-selected={selected}
      aria-disabled={disabled || undefined}
      tabIndex={disabled ? -1 : 0}
      data-status={status}
      onClick={() => !disabled && onSelect?.()}
      onDoubleClick={() => !disabled && onOpen?.()}
      onKeyDown={(event) => {
        if (disabled) return;
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onSelect?.();
        }
      }}
      style={{
        height: 30,
        paddingInline: 8,
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        borderRadius: 6,
        background: selected ? 'var(--sr-surface-selected)' : 'transparent',
        color: disabled
          ? 'var(--sr-text-muted)'
          : status === 'error'
            ? 'var(--sr-danger)'
            : status === 'warning'
              ? 'var(--sr-warning)'
              : 'var(--sr-text-primary)',
        opacity: disabled ? 0.52 : 1,
        cursor: disabled ? 'not-allowed' : 'pointer',
      }}
    >
      {icon ? <span style={{width: 20, display: 'grid', placeItems: 'center'}}>{icon}</span> : null}
      <span
        title={String(label)}
        style={{
          flex: 1,
          minWidth: 0,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          fontSize: '0.8125rem',
        }}
      >
        {label}
      </span>
      {trailing ? <span style={{fontSize: '0.75rem', color: 'var(--sr-text-muted)'}}>{trailing}</span> : null}
    </div>
  );
}

ListRow.propTypes = {
  label: PropTypes.node.isRequired,
  icon: PropTypes.node,
  trailing: PropTypes.node,
  selected: PropTypes.bool,
  disabled: PropTypes.bool,
  status: PropTypes.oneOf(['default', 'warning', 'error']),
  onSelect: PropTypes.func,
  onOpen: PropTypes.func,
};

export function TreeRow({
  label,
  level = 1,
  icon,
  expanded = false,
  expandable = false,
  selected = false,
  disabled = false,
  loading = false,
  warning = '',
  checked,
  indeterminate = false,
  isLast = false,
  onToggle,
  onSelect,
  onOpen,
  onCheck,
  onContextMenu,
  trailing,
}) {
  const prefs = readBranchedTreePreferences();
  const depth = Math.max(0, Number(level) - 1);
  const stepX = prefs.stepX || 16;
  const r = Math.min(prefs.radius || 7, Math.floor(stepX * 0.6));
  const rowH = 30;
  const midY = rowH / 2;
  const svgWidth = depth * stepX;

  return (
    <div
      role="treeitem"
      aria-level={level}
      aria-selected={selected}
      aria-expanded={expandable ? expanded : undefined}
      aria-disabled={disabled || undefined}
      aria-busy={loading || undefined}
      data-selected={selected ? 'true' : 'false'}
      tabIndex={disabled ? -1 : 0}
      className="sr-branched-row"
      onClick={() => !disabled && onSelect?.()}
      onDoubleClick={() => !disabled && onOpen?.()}
      onContextMenu={(event) => {
        if (disabled) return;
        event.preventDefault();
        onSelect?.();
        onContextMenu?.(event);
      }}
      onKeyDown={(event) => {
        if (disabled) return;
        if (event.key === 'ArrowRight' && expandable && !expanded) onToggle?.(true);
        else if (event.key === 'ArrowLeft' && expandable && expanded) onToggle?.(false);
        else if (event.key === 'Enter') onOpen?.();
        else if (event.key === ' ') {
          event.preventDefault();
          onSelect?.();
        }
      }}
      style={{
        paddingLeft: depth === 0 ? 4 : 2,
        opacity: disabled ? 0.5 : 1,
        color: warning ? 'var(--sr-warning)' : undefined,
      }}
    >
      {depth > 0 && (
        <svg
          width={svgWidth}
          height={rowH}
          viewBox={`0 0 ${svgWidth} ${rowH}`}
          aria-hidden="true"
          className="sr-branched-guide-svg"
        >
          {Array.from({length: depth}).map((_, col) => {
            const x = col * stepX + Math.round(stepX * 0.5);
            const isConnectorCol = col === depth - 1;
            const stroke = selected ? 'var(--sr-tree-active-line)' : 'var(--sr-tree-line)';
            const strokeWidth = selected ? 1.75 : 1.25;
            if (!isConnectorCol) {
              return (
                <path
                  key={`trunk-${col}`}
                  d={`M ${x} 0 V ${rowH}`}
                  fill="none"
                  stroke="var(--sr-tree-line)"
                  strokeWidth={1.25}
                />
              );
            }
            const endX = svgWidth - 1;
            return (
              <g key={`elbow-${col}`}>
                {!isLast && (
                  <path
                    d={`M ${x} ${midY} V ${rowH}`}
                    fill="none"
                    stroke="var(--sr-tree-line)"
                    strokeWidth={1.25}
                  />
                )}
                <path
                  d={`M ${x} 0 V ${midY - r} Q ${x} ${midY} ${Math.min(endX, x + r)} ${midY} H ${endX}`}
                  fill="none"
                  stroke={stroke}
                  strokeWidth={strokeWidth}
                  strokeLinecap="round"
                />
              </g>
            );
          })}
        </svg>
      )}
      <span style={{width: 18, display: 'inline-grid', placeItems: 'center', flexShrink: 0}}>
        {expandable && (
          <IconButton
            label={`${expanded ? 'Collapse' : 'Expand'} ${label}`}
            onClick={(event) => {
              event.stopPropagation();
              onToggle?.(!expanded);
            }}
            style={{minWidth: 18, minHeight: 18, padding: 0}}
          >
            {expanded ? '▾' : '▸'}
          </IconButton>
        )}
      </span>
      {checked !== undefined && (
        <Checkbox
          label=""
          checked={checked}
          indeterminate={indeterminate}
          onChange={onCheck}
          inputProps={{'aria-label': `Select ${label}`}}
        />
      )}
      {icon && <span style={{width: 18, display: 'inline-grid', placeItems: 'center'}}>{icon}</span>}
      <span
        title={String(label)}
        style={{overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1}}
      >
        {label}
      </span>
      {loading && <span style={{fontSize: '0.72rem', color: 'var(--sr-text-muted)'}}>Loading…</span>}
      {warning && <span aria-label={warning} className="sr-branched-badge" data-delta="modify">!</span>}
      {trailing && <span>{trailing}</span>}
    </div>
  );
}

TreeRow.propTypes = {
  label: PropTypes.node.isRequired,
  level: PropTypes.number,
  icon: PropTypes.node,
  expanded: PropTypes.bool,
  expandable: PropTypes.bool,
  selected: PropTypes.bool,
  disabled: PropTypes.bool,
  loading: PropTypes.bool,
  warning: PropTypes.string,
  checked: PropTypes.bool,
  indeterminate: PropTypes.bool,
  onToggle: PropTypes.func,
  onSelect: PropTypes.func,
  onOpen: PropTypes.func,
  onCheck: PropTypes.func,
  onContextMenu: PropTypes.func,
  trailing: PropTypes.node,
};

export function KeyboardShortcutHint({shortcut, disabled = false}) {
  return (
    <kbd
      aria-disabled={disabled || undefined}
      style={{
        minWidth: 42,
        padding: '1px 5px',
        borderRadius: 4,
        border: '1px solid var(--sr-border-subtle)',
        background: 'var(--sr-surface-subtle)',
        textAlign: 'right',
        opacity: disabled ? 0.5 : 1,
        fontFamily: 'var(--sr-font-mono)',
        fontSize: '0.7rem',
        color: 'var(--sr-text-secondary)',
      }}
    >
      {shortcut}
    </kbd>
  );
}

KeyboardShortcutHint.propTypes = {
  shortcut: PropTypes.string.isRequired,
  disabled: PropTypes.bool,
};

export function Pagination({
  page = 1,
  pageSize = 50,
  count,
  loading = false,
  onChange,
  label = 'Result pages',
}) {
  const pages = Number.isFinite(count) ? Math.max(1, Math.ceil(count / pageSize)) : null;
  const start = (page - 1) * pageSize + 1;
  const end = Number.isFinite(count) ? Math.min(count, page * pageSize) : page * pageSize;
  return (
    <nav
      aria-label={label}
      style={{
        minHeight: 'var(--cde-control-height, 30px)',
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        fontSize: '0.78rem',
      }}
    >
      <IconButton
        label="Previous page"
        disabled={loading || page <= 1}
        onClick={() => onChange?.(page - 1)}
      >
        ‹
      </IconButton>
      <span>Page {page}{pages ? ` of ${pages}` : ''}</span>
      <IconButton
        label="Next page"
        disabled={Boolean(loading || (pages && page >= pages))}
        onClick={() => onChange?.(page + 1)}
      >
        ›
      </IconButton>
      <span style={{marginLeft: 6, color: 'var(--sr-text-muted)'}}>
        {Number.isFinite(count) ? `${count ? start : 0}–${end} of ${count}` : `${start}–${end}`}
      </span>
    </nav>
  );
}

Pagination.propTypes = {
  page: PropTypes.number,
  pageSize: PropTypes.number,
  count: PropTypes.number,
  loading: PropTypes.bool,
  onChange: PropTypes.func,
  label: PropTypes.string,
};

export function ColumnPicker({
  open,
  anchorEl,
  columns = [],
  visible = [],
  onChange,
  onReset,
  onClose,
  disabled = false,
}) {
  const [query, setQuery] = useState('');
  const filtered = columns.filter((column) =>
    String(column.label ?? column.name).toLowerCase().includes(query.toLowerCase())
  );
  return (
    <Popover open={open} anchorEl={anchorEl} onClose={onClose} label="Choose visible columns">
      <div style={{width: 300, maxHeight: 380, display: 'flex', flexDirection: 'column', gap: 8, padding: 6}}>
        <SearchField
          label="Filter columns"
          value={query}
          onChange={setQuery}
          disabled={disabled}
        />
        <ScratchScrollArea style={{flex: 1, maxHeight: 240}}>
          <div style={{display: 'flex', flexDirection: 'column', gap: 6, padding: '2px 4px'}}>
            {filtered.map((column) => (
              <Checkbox
                key={column.name}
                label={column.label ?? column.name}
                checked={visible.includes(column.name)}
                disabled={disabled || column.disabled}
                onChange={(checked) =>
                  onChange?.(
                    checked
                      ? [...visible, column.name]
                      : visible.filter((name) => name !== column.name)
                  )
                }
              />
            ))}
          </div>
        </ScratchScrollArea>
        <div style={{paddingTop: 6, borderTop: '1px solid var(--sr-border-subtle)'}}>
          <Button disabled={disabled} onClick={onReset}>Restore default columns</Button>
        </div>
      </div>
    </Popover>
  );
}

ColumnPicker.propTypes = {
  open: PropTypes.bool.isRequired,
  anchorEl: PropTypes.object,
  columns: PropTypes.array,
  visible: PropTypes.array,
  onChange: PropTypes.func,
  onReset: PropTypes.func,
  onClose: PropTypes.func,
  disabled: PropTypes.bool,
};

function EntityPicker({
  kind,
  open,
  title,
  items = EMPTY_ITEMS,
  selected = EMPTY_ITEMS,
  multiple = false,
  loading = false,
  error = '',
  state = 'default',
  onClose,
  onConfirm,
}) {
  const [query, setQuery] = useState('');
  const [choice, setChoice] = useState(selected);
  useEffect(() => {
    if (open) setChoice(selected);
  }, [open, selected]);
  const filtered = items.filter((item) =>
    `${item.label} ${item.path || ''} ${item.type || ''}`.toLowerCase().includes(query.toLowerCase())
  );
  const toggle = (item) =>
    setChoice((current) =>
      multiple
        ? current.some((value) => value.id === item.id)
          ? current.filter((value) => value.id !== item.id)
          : [...current, item]
        : [item]
    );
  const noun = kind === 'asset'
    ? 'project assets'
    : kind === 'credential'
      ? 'credential references'
      : 'resources';

  return (
    <Dialog
      open={open}
      title={title}
      size="medium"
      onClose={onClose}
      actions={(
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            intent="primary"
            disabled={!choice.length}
            onClick={() => onConfirm?.(multiple ? choice : choice[0])}
          >
            Select
          </Button>
        </>
      )}
    >
      <div
        data-picker-kind={kind}
        style={{height: 380, position: 'relative', display: 'flex', flexDirection: 'column', gap: 8}}
      >
        <SearchField label={`Filter ${noun}`} value={query} onChange={setQuery} />
        {(error || ['permission', 'disconnected'].includes(state)) && (
          <EmptyState
            message={
              error ||
              (state === 'permission'
                ? 'You do not have permission to view these items.'
                : 'The live provider connection is disconnected.')
            }
            role="alert"
          />
        )}
        {!error && !loading && state !== 'permission' && state !== 'disconnected' && !filtered.length && (
          <EmptyState message={`No matching ${noun}`} />
        )}
        <ScratchScrollArea style={{flex: 1}}>
          <div role="listbox" aria-multiselectable={multiple || undefined}>
            {filtered.map((item) => (
              <ListRow
                key={item.id}
                label={item.label}
                selected={choice.some((value) => value.id === item.id)}
                trailing={<Badge label={item.type || kind} />}
                onSelect={() => toggle(item)}
                onOpen={() => {
                  toggle(item);
                  if (!multiple) onConfirm?.(item);
                }}
              />
            ))}
          </div>
        </ScratchScrollArea>
        <ProgressOverlay message={loading ? `Loading ${kind}s` : ''} />
      </div>
    </Dialog>
  );
}

EntityPicker.propTypes = {
  kind: PropTypes.oneOf(['asset', 'resource', 'credential']).isRequired,
  open: PropTypes.bool.isRequired,
  title: PropTypes.string.isRequired,
  items: PropTypes.array,
  selected: PropTypes.array,
  multiple: PropTypes.bool,
  loading: PropTypes.bool,
  error: PropTypes.string,
  state: PropTypes.oneOf(['default', 'permission', 'disconnected']),
  onClose: PropTypes.func,
  onConfirm: PropTypes.func,
};

export function ResourcePicker(props) {
  return <EntityPicker kind="resource" title="Select provider resource" {...props} />;
}

export function AssetPicker(props) {
  return <EntityPicker kind="asset" title="Select project asset" {...props} />;
}

export function SecretPicker(props) {
  return <EntityPicker kind="credential" title="Select credential reference" {...props} />;
}

export function ConnectionSelector({
  connections = [],
  value = '',
  onChange,
  state = 'disconnected',
  environment = 'unknown',
  label = 'Connection',
  disabled = false,
}) {
  const options = connections.map((item) => ({
    value: item.id,
    label: `${item.provider ? `${item.provider}: ` : ''}${item.label}`,
  }));
  return (
    <div style={{display: 'flex', alignItems: 'center', gap: 6}}>
      <Select
        label={label}
        options={options}
        value={value}
        onChange={onChange}
        disabled={disabled}
        sx={{minWidth: 180, maxWidth: 360}}
      />
      <Badge
        status={
          state === 'connected'
            ? 'success'
            : ['connecting', 'warning', 'production'].includes(state)
              ? 'warning'
              : state === 'readonly'
                ? 'info'
                : 'error'
        }
        label={state}
      />
      <EnvironmentIndicator environment={environment} />
    </div>
  );
}

ConnectionSelector.propTypes = {
  connections: PropTypes.array,
  value: PropTypes.any,
  onChange: PropTypes.func,
  state: PropTypes.oneOf([
    'connected', 'connecting', 'disconnected', 'readonly', 'production', 'warning',
  ]),
  environment: PropTypes.string,
  label: PropTypes.string,
  disabled: PropTypes.bool,
};

export function CommandPalette({
  open,
  commands = EMPTY_ITEMS,
  resources = EMPTY_ITEMS,
  assets = EMPTY_ITEMS,
  recent = EMPTY_ITEMS,
  settings = EMPTY_ITEMS,
  onClose,
  onInvoke,
  loading = false,
}) {
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const groups = useMemo(
    () =>
      [
        ['Commands', commands],
        ['Resources', resources],
        ['Project Assets', assets],
        ['Recent', recent],
        ['Settings', settings],
      ]
        .map(([name, values]) => [
          name,
          values.filter((item) =>
            `${item.label} ${item.description || ''}`.toLowerCase().includes(query.toLowerCase())
          ),
        ])
        .filter(([, values]) => values.length),
    [commands, resources, assets, recent, settings, query]
  );
  const flat = groups.flatMap(([, values]) => values);
  useEffect(() => setActive(0), [query, open]);
  const invoke = (item) => {
    if (item && !item.disabled) {
      onInvoke?.(item);
      onClose?.();
    }
  };
  return (
    <Dialog open={open} title="Command palette" size="medium" onClose={onClose}>
      <div
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown') {
            event.preventDefault();
            setActive((value) => Math.min(flat.length - 1, value + 1));
          }
          if (event.key === 'ArrowUp') {
            event.preventDefault();
            setActive((value) => Math.max(0, value - 1));
          }
          if (event.key === 'Enter') {
            event.preventDefault();
            invoke(flat[active]);
          }
        }}
        style={{width: '100%', maxHeight: 520, position: 'relative', display: 'flex', flexDirection: 'column', gap: 8}}
      >
        <SearchField
          autoFocus
          label="Search commands, resources, assets, and settings"
          value={query}
          onChange={setQuery}
          loading={loading}
        />
        {!loading && !flat.length && <EmptyState message="No matching commands or items" />}
        <ScratchScrollArea style={{maxHeight: 420}}>
          <div role="listbox">
            {groups.map(([group, values]) => (
              <div key={group} style={{marginBottom: 6}}>
                <h3 style={{margin: 0, padding: '4px 8px', fontSize: '0.68rem', textTransform: 'uppercase', color: 'var(--sr-text-muted)'}}>
                  {group}
                </h3>
                {values.map((item) => {
                  const index = flat.indexOf(item);
                  return (
                    <ListRow
                      key={`${group}-${item.id}`}
                      label={item.label}
                      selected={active === index}
                      disabled={item.disabled}
                      trailing={item.shortcut}
                      onSelect={() => setActive(index)}
                      onOpen={() => invoke(item)}
                    />
                  );
                })}
              </div>
            ))}
          </div>
        </ScratchScrollArea>
        <ProgressOverlay message={loading ? 'Searching' : ''} />
      </div>
    </Dialog>
  );
}

CommandPalette.propTypes = {
  open: PropTypes.bool.isRequired,
  commands: PropTypes.array,
  resources: PropTypes.array,
  assets: PropTypes.array,
  recent: PropTypes.array,
  settings: PropTypes.array,
  onClose: PropTypes.func,
  onInvoke: PropTypes.func,
  loading: PropTypes.bool,
};
