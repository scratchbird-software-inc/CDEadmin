/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Toolbar as BaseToolbar} from '@base-ui/react/toolbar';
import {Collapsible as BaseCollapsible} from '@base-ui/react/collapsible';
import {IconButton} from '../primitives/Button';

export function Toolbar({label = 'Toolbar', children, trailing}) {
  return (
    <BaseToolbar.Root
      aria-label={label}
      style={{
        minHeight: 'var(--cde-toolbar-height, 34px)',
        display: 'flex',
        alignItems: 'center',
        flexWrap: 'wrap',
        flexShrink: 0,
        gap: 4,
        padding: '4px 6px',
        borderBottom: '1px solid var(--sr-border-subtle)',
        minWidth: 0,
      }}
    >
      {children}
      {trailing && <div style={{marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 4}}>{trailing}</div>}
    </BaseToolbar.Root>
  );
}

Toolbar.propTypes = {
  label: PropTypes.string,
  children: PropTypes.node,
  trailing: PropTypes.node,
};

export function StatusBar({status = 'normal', label = 'Surface status', children}) {
  const topBorder = status === 'normal'
    ? 'var(--sr-border-subtle)'
    : status === 'warning'
      ? 'var(--sr-warning)'
      : 'var(--sr-danger)';
  return (
    <div
      role="status"
      aria-label={label}
      data-status={status}
      style={{
        height: 'var(--cde-status-height, 24px)',
        flex: '0 0 auto',
        display: 'flex',
        alignItems: 'center',
        paddingInline: 8,
        gap: 8,
        fontSize: '0.75rem',
        borderTop: `1px solid ${topBorder}`,
      }}
    >
      {children}
    </div>
  );
}

StatusBar.propTypes = {
  status: PropTypes.oneOf(['normal', 'warning', 'disconnected']),
  label: PropTypes.string,
  children: PropTypes.node,
};

export function Splitter({
  orientation = 'vertical',
  value,
  min = 0,
  max = Infinity,
  onChange,
  label = 'Resize panels',
  invert = false,
}) {
  const start = useRef(null);
  const coordinate = (event) => (orientation === 'vertical' ? event.clientX : event.clientY);
  const clamp = (next) => Math.max(min, Math.min(max, next));
  const delta = (next) => (invert ? -next : next);
  const begin = (event) => {
    event.currentTarget.setPointerCapture?.(event.pointerId);
    start.current = {coordinate: coordinate(event), value};
  };
  const move = (event) => {
    if (!start.current) return;
    onChange?.(clamp(start.current.value + delta(coordinate(event) - start.current.coordinate)));
  };
  const end = (event) => {
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    start.current = null;
  };
  const vertical = orientation === 'vertical';
  return (
    <div
      role="separator"
      tabIndex={0}
      aria-label={label}
      aria-orientation={orientation}
      aria-valuenow={Math.round(value)}
      aria-valuemin={min}
      aria-valuemax={Number.isFinite(max) ? max : undefined}
      onPointerDown={begin}
      onPointerMove={move}
      onPointerUp={end}
      onKeyDown={(event) => {
        const decrease = vertical ? event.key === 'ArrowLeft' : event.key === 'ArrowUp';
        const increase = vertical ? event.key === 'ArrowRight' : event.key === 'ArrowDown';
        if (!decrease && !increase) return;
        event.preventDefault();
        const step = event.shiftKey ? 16 : 4;
        onChange?.(clamp(value + delta(increase ? step : -step)));
      }}
      style={{
        position: 'relative',
        flex: '0 0 auto',
        cursor: vertical ? 'col-resize' : 'row-resize',
        width: vertical ? 'calc(var(--cde-resize-handle-size, 8) * 1px)' : '100%',
        height: vertical ? '100%' : 'calc(var(--cde-resize-handle-size, 8) * 1px)',
        outline: 0,
      }}
    />
  );
}

Splitter.propTypes = {
  orientation: PropTypes.oneOf(['vertical', 'horizontal']),
  value: PropTypes.number.isRequired,
  min: PropTypes.number,
  max: PropTypes.number,
  onChange: PropTypes.func,
  label: PropTypes.string,
  invert: PropTypes.bool,
};

export function Drawer({
  open = true,
  label = 'Drawer',
  children,
  height = 240,
  onHeightChange,
}) {
  return (
    <section
      aria-label={label}
      hidden={!open}
      style={{
        height: open ? `min(60vh, ${Math.max(120, height)}px)` : 0,
        display: open ? 'flex' : 'none',
        flexDirection: 'column',
        minHeight: 120,
        borderTop: '1px solid var(--sr-border-default)',
        background: 'var(--sr-surface-card)',
      }}
    >
      <Splitter
        orientation="horizontal"
        value={height}
        min={120}
        max={Math.round((typeof window !== 'undefined' && window.innerHeight ? window.innerHeight : 800) * 0.6)}
        onChange={onHeightChange}
        label={`Resize ${label}`}
      />
      {children}
    </section>
  );
}

Drawer.propTypes = {
  open: PropTypes.bool,
  label: PropTypes.string,
  children: PropTypes.node,
  height: PropTypes.number,
  onHeightChange: PropTypes.func,
};

export function DropZone({
  label = 'Drop items',
  validate = () => ({valid: true}),
  onDrop,
  children,
}) {
  const [state, setState] = useState({kind: 'idle', reason: ''});
  const inspect = (event) => {
    event.preventDefault();
    const result = validate(event.dataTransfer) || {};
    setState({
      kind: result.valid === false ? 'drag_invalid' : 'drag_valid',
      reason: String(result.reason || ''),
    });
    if (result.valid !== false && event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy';
    }
    return result;
  };
  return (
    <div
      role="group"
      aria-label={label}
      tabIndex={0}
      data-drop-state={state.kind}
      onDragEnter={inspect}
      onDragOver={inspect}
      onDragLeave={() => setState({kind: 'idle', reason: ''})}
      onKeyDown={(event) => event.key === 'Escape' && setState({kind: 'idle', reason: ''})}
      onDrop={(event) => {
        const result = inspect(event);
        if (result.valid !== false) onDrop?.(event.dataTransfer, event);
        setState({kind: 'idle', reason: ''});
      }}
      style={{
        minHeight: 64,
        margin: 4,
        padding: 8,
        borderRadius: 'var(--sr-island-radius, 12px)',
        border: `2px ${state.kind === 'drag_invalid' ? 'dashed' : 'solid'} ${
          state.kind === 'drag_invalid'
            ? 'var(--sr-danger)'
            : state.kind === 'drag_valid'
              ? 'var(--sr-accent)'
              : 'var(--sr-border-default)'
        }`,
        background: state.kind === 'drag_valid' ? 'var(--sr-surface-selected)' : 'transparent',
        cursor: state.kind === 'drag_invalid' ? 'not-allowed' : 'default',
      }}
    >
      {children}
      {state.reason && (
        <div role="alert" style={{color: 'var(--sr-danger)', fontSize: '0.78rem', marginTop: 4}}>
          {state.reason}
        </div>
      )}
    </div>
  );
}

DropZone.propTypes = {
  label: PropTypes.string,
  validate: PropTypes.func,
  onDrop: PropTypes.func,
  children: PropTypes.node,
};

function CollapsibleSection({
  title,
  children,
  defaultExpanded = true,
  disabled = false,
  locked = false,
  kind = 'section',
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  return (
    <BaseCollapsible.Root
      open={expanded}
      onOpenChange={(nextOpen) => {
        if (!disabled && !locked) setExpanded(nextOpen);
      }}
      disabled={disabled || locked}
      render={<section data-section-kind={kind} style={{borderBottom: '1px solid var(--sr-border-subtle)'}} />}
    >
      <h3
        style={{
          margin: 0,
          minHeight: 30,
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          fontSize: '0.76rem',
          fontWeight: 600,
          color: 'var(--sr-text-secondary)',
        }}
      >
        <IconButton
          label={`${expanded ? 'Collapse' : 'Expand'} ${title}`}
          disabled={disabled || locked}
          onClick={() => setExpanded((value) => !value)}
          style={{minWidth: 22, minHeight: 22, padding: 2}}
        >
          {expanded ? '▾' : '▸'}
        </IconButton>
        {title}
      </h3>
      {expanded && (
        <BaseCollapsible.Panel>
          <div style={{padding: kind === 'inspector' ? 12 : 0, paddingBottom: 12}}>
            {children}
          </div>
        </BaseCollapsible.Panel>
      )}
    </BaseCollapsible.Root>
  );
}

CollapsibleSection.propTypes = {
  title: PropTypes.node.isRequired,
  children: PropTypes.node,
  defaultExpanded: PropTypes.bool,
  disabled: PropTypes.bool,
  locked: PropTypes.bool,
  kind: PropTypes.string,
};

export function InspectorSection(props) {
  return <CollapsibleSection kind="inspector" {...props} />;
}

export function FormSection(props) {
  return <CollapsibleSection kind="form" {...props} />;
}

export function ToolboxItem({label, icon, payload, onInsert, disabled = false}) {
  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled || undefined}
      draggable={!disabled}
      onDoubleClick={() => !disabled && onInsert?.(payload)}
      onKeyDown={(event) => {
        if (!disabled && (event.key === 'Enter' || event.key === ' ')) {
          event.preventDefault();
          onInsert?.(payload);
        }
      }}
      onDragStart={(event) => {
        if (disabled) return;
        event.dataTransfer.effectAllowed = 'copy';
        event.dataTransfer.setData('application/x-cdeadmin-toolbox-item', JSON.stringify(payload));
      }}
      style={{
        height: 30,
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        paddingInline: 8,
        borderRadius: 6,
        fontSize: '0.8125rem',
        opacity: disabled ? 0.5 : 1,
        cursor: disabled ? 'not-allowed' : 'grab',
      }}
    >
      <span aria-hidden="true" style={{opacity: 0.45, fontSize: '0.75rem'}}>⋮⋮</span>
      {icon && <span style={{width: 18, display: 'grid', placeItems: 'center'}}>{icon}</span>}
      <span>{label}</span>
    </div>
  );
}

ToolboxItem.propTypes = {
  label: PropTypes.node.isRequired,
  icon: PropTypes.node,
  payload: PropTypes.object.isRequired,
  onInsert: PropTypes.func,
  disabled: PropTypes.bool,
};
