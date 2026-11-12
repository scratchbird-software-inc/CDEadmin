/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useId} from 'react';
import PropTypes from 'prop-types';
import {AlertDialog as BaseAlertDialog} from '@base-ui/react/alert-dialog';
import {Popover as BasePopover} from '@base-ui/react/popover';
import {ensureScratchBaseStyles} from './ScratchBaseStyles';
import {ScratchScrollArea} from './ScratchScrollArea';

const DIALOG_WIDTHS = Object.freeze({
  small: 420,
  medium: 640,
  large: 960,
  xlarge: 1120,
});

/**
 * Standardized @base-ui/react AlertDialog for high-consequence confirmations
 * (kill session, drop object, clear redaction, discard unsaved work).
 */
export function ScratchAlertDialog({
  open,
  title,
  description,
  children,
  actions,
  onClose,
  size = 'small',
  busy = false,
}) {
  const titleId = useId();
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);

  return (
    <BaseAlertDialog.Root
      open={Boolean(open)}
      onOpenChange={(nextOpen) => {
        if (!nextOpen && !busy) onClose?.();
      }}
    >
      <BaseAlertDialog.Portal>
        <BaseAlertDialog.Backdrop className="sr-dialog-backdrop" />
        <BaseAlertDialog.Popup
          className="sr-dialog-popup"
          aria-labelledby={titleId}
          aria-busy={busy || undefined}
          style={{width: DIALOG_WIDTHS[size] || DIALOG_WIDTHS.small}}
        >
          <div className="sr-dialog-header">
            <BaseAlertDialog.Title id={titleId} style={{margin: 0, fontSize: 'inherit'}}>
              {title}
            </BaseAlertDialog.Title>
          </div>
          <div className="sr-dialog-body">
            {description && (
              <BaseAlertDialog.Description style={{margin: '0 0 10px 0', color: 'var(--sr-text-secondary)'}}>
                {description}
              </BaseAlertDialog.Description>
            )}
            {children}
          </div>
          {actions && <div className="sr-dialog-footer">{actions}</div>}
        </BaseAlertDialog.Popup>
      </BaseAlertDialog.Portal>
    </BaseAlertDialog.Root>
  );
}

ScratchAlertDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  title: PropTypes.node.isRequired,
  description: PropTypes.node,
  children: PropTypes.node,
  actions: PropTypes.node,
  onClose: PropTypes.func,
  size: PropTypes.oneOf(['small', 'medium', 'large', 'xlarge']),
  busy: PropTypes.bool,
};

/**
 * Standardized @base-ui/react Popover Palette for compact Area 3b popup palettes
 * (Diagram Entity Stencils, UDT & Domains Palette, Layer/Level Selector, Fetch Limits).
 */
export function ScratchPopoverPalette({
  open,
  onOpenChange,
  trigger,
  anchor,
  title,
  side = 'bottom',
  align = 'start',
  width = 280,
  maxHeight = 360,
  children,
}) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);

  return (
    <BasePopover.Root open={open} onOpenChange={onOpenChange}>
      {trigger && <BasePopover.Trigger render={trigger} />}
      <BasePopover.Portal>
        <BasePopover.Positioner anchor={anchor} side={side} align={align} sideOffset={6} style={{zIndex: 'var(--cde-layer-popover, 2400)'}}>
          <BasePopover.Popup
            className="sr-popover-popup"
            aria-label={typeof title === 'string' ? title : 'Palette'}
            style={{width, maxHeight, display: 'flex', flexDirection: 'column', padding: 0, overflow: 'hidden'}}
          >
            {title && (
              <div style={{
                padding: '8px 12px',
                borderBottom: '1px solid var(--sr-border-subtle)',
                fontSize: '0.75rem',
                fontWeight: 700,
                letterSpacing: '0.03em',
                textTransform: 'uppercase',
                color: 'var(--sr-text-secondary)',
              }}>
                <BasePopover.Title style={{margin: 0, fontSize: 'inherit'}}>{title}</BasePopover.Title>
              </div>
            )}
            <ScratchScrollArea style={{flex: '1 1 auto', maxHeight: maxHeight - (title ? 36 : 8)}}>
              <div style={{padding: 8}}>
                {children}
              </div>
            </ScratchScrollArea>
          </BasePopover.Popup>
        </BasePopover.Positioner>
      </BasePopover.Portal>
    </BasePopover.Root>
  );
}

ScratchPopoverPalette.propTypes = {
  open: PropTypes.bool,
  onOpenChange: PropTypes.func,
  trigger: PropTypes.element,
  anchor: PropTypes.any,
  title: PropTypes.node,
  side: PropTypes.oneOf(['top', 'bottom', 'left', 'right']),
  align: PropTypes.oneOf(['start', 'center', 'end']),
  width: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
  maxHeight: PropTypes.number,
  children: PropTypes.node,
};
