/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useState} from 'react';
import PropTypes from 'prop-types';
import {IconButton} from '../primitives/Button';
import {StatusDot} from '../feedback/Indicators';

export function Tab({
  label,
  active = false,
  dirty = false,
  attention = false,
  disabled = false,
  closable = false,
  icon,
  onActivate,
  onClose,
  onDragStart,
}) {
  return (
    <div
      role="tab"
      aria-selected={active}
      aria-disabled={disabled || undefined}
      tabIndex={active && !disabled ? 0 : -1}
      draggable={!disabled && Boolean(onDragStart)}
      onDragStart={onDragStart}
      onClick={() => !disabled && onActivate?.()}
      onMouseDown={(event) => {
        if (event.button === 1 && closable && !disabled) {
          event.preventDefault();
          onClose?.();
        }
      }}
      onKeyDown={(event) => {
        if (!disabled && (event.key === 'Enter' || event.key === ' ')) {
          event.preventDefault();
          onActivate?.();
        }
        if (!disabled && closable && event.key === 'Delete' && event.shiftKey) {
          onClose?.();
        }
      }}
      style={{
        height: 'var(--cde-tab-height, 30px)',
        minWidth: 96,
        maxWidth: 240,
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        paddingInline: 10,
        borderTopLeftRadius: 8,
        borderTopRightRadius: 8,
        borderBottom: active ? '2px solid var(--sr-accent)' : '2px solid transparent',
        background: active ? 'var(--sr-surface-card)' : 'transparent',
        color: disabled ? 'var(--sr-text-muted)' : 'var(--sr-text-primary)',
        fontWeight: active ? 600 : 500,
        fontSize: '0.8125rem',
        cursor: disabled ? 'not-allowed' : 'pointer',
      }}
    >
      {attention && <StatusDot status="warning" label="Attention required" />}
      {icon}
      <span
        title={String(label)}
        style={{
          flex: 1,
          minWidth: 0,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {label}{dirty ? ' •' : ''}
      </span>
      {closable && (
        <IconButton
          label={`Close ${label}`}
          disabled={disabled}
          onClick={(event) => {
            event.stopPropagation();
            onClose?.();
          }}
          style={{minWidth: 18, minHeight: 18, padding: 1}}
        >
          ×
        </IconButton>
      )}
    </div>
  );
}

Tab.propTypes = {
  label: PropTypes.node.isRequired,
  active: PropTypes.bool,
  dirty: PropTypes.bool,
  attention: PropTypes.bool,
  disabled: PropTypes.bool,
  closable: PropTypes.bool,
  icon: PropTypes.node,
  onActivate: PropTypes.func,
  onClose: PropTypes.func,
  onDragStart: PropTypes.func,
};

export function Breadcrumbs({items = [], onNavigate, maxItems = 6}) {
  const [expanded, setExpanded] = useState(false);
  const shouldCollapse = !expanded && items.length > maxItems;
  const visibleItems = shouldCollapse
    ? [items[0], {__ellipsis: true, id: '__ellipsis__'}, ...items.slice(-(maxItems - 2))]
    : items;

  return (
    <nav
      aria-label="Current location"
      style={{
        minHeight: 26,
        display: 'flex',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: 4,
        fontSize: '0.78rem',
      }}
    >
      {visibleItems.map((item, idx) => {
        const isLast = idx === visibleItems.length - 1;
        return (
          <span key={item.id ?? item.label} style={{display: 'inline-flex', alignItems: 'center', gap: 4}}>
            {idx > 0 && <span aria-hidden="true" style={{color: 'var(--sr-text-muted)'}}>/</span>}
            {item.__ellipsis ? (
              <button
                type="button"
                aria-label="Show full path"
                onClick={() => setExpanded(true)}
                className="sr-branched-ancestor-crumb"
              >
                …
              </button>
            ) : isLast ? (
              <span aria-current="page" style={{fontWeight: 600, color: 'var(--sr-text-primary)'}}>
                {item.label}
              </span>
            ) : (
              <button
                type="button"
                onClick={() => onNavigate?.(item)}
                className="sr-branched-ancestor-crumb"
              >
                {item.label}
              </button>
            )}
          </span>
        );
      })}
    </nav>
  );
}

Breadcrumbs.propTypes = {
  items: PropTypes.array,
  onNavigate: PropTypes.func,
  maxItems: PropTypes.number,
};
