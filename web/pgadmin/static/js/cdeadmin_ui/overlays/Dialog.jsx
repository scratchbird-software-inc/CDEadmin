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
import {Dialog as BaseDialog} from '@base-ui/react/dialog';
import {ensureScratchBaseStyles} from '../base/ScratchBaseStyles';
import {ScratchScrollArea} from '../base/ScratchScrollArea';

const WIDTHS = Object.freeze({
  small: 420,
  medium: 640,
  large: 960,
  xlarge: 1120,
});

export function Dialog({
  open,
  title,
  children,
  actions,
  onClose,
  size = 'small',
  busy = false,
  validationError = '',
  defaultAction,
  onKeyDown,
  ...props
}) {
  const titleId = useId();
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);

  return (
    <BaseDialog.Root
      open={Boolean(open)}
      onOpenChange={(nextOpen) => {
        if (!nextOpen && !busy) {
          onClose?.();
        }
      }}
    >
      <BaseDialog.Portal>
        <BaseDialog.Backdrop className="sr-dialog-backdrop" />
        <BaseDialog.Popup
          {...props}
          aria-labelledby={titleId}
          aria-busy={busy || undefined}
          className={['sr-dialog-popup', props.className].filter(Boolean).join(' ')}
          style={{
            width: WIDTHS[size] || WIDTHS.small,
            ...props.style,
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && defaultAction && !busy && enterSubmits(event)) {
              event.preventDefault();
              defaultAction();
            }
            onKeyDown?.(event);
          }}
        >
          <div className="sr-dialog-header">
            <BaseDialog.Title id={titleId} style={{margin: 0, fontSize: 'inherit', fontWeight: 600}}>
              {title}
            </BaseDialog.Title>
            {onClose && (
              <BaseDialog.Close
                aria-label="Close dialog"
                disabled={busy}
                className="sr-icon-btn"
                style={{width: 26, height: 26, minWidth: 26, minHeight: 26}}
              >
                ×
              </BaseDialog.Close>
            )}
          </div>
          <ScratchScrollArea className="sr-dialog-body" style={{padding: 0}}>
            <div style={{padding: 16}}>
              {validationError && (
                <div
                  role="alert"
                  style={{
                    marginBottom: 10,
                    padding: '6px 10px',
                    borderRadius: 7,
                    border: '1px solid rgba(220, 38, 38, 0.35)',
                    background: 'rgba(220, 38, 38, 0.08)',
                    color: 'var(--sr-danger)',
                    fontSize: '0.8125rem',
                  }}
                >
                  {validationError}
                </div>
              )}
              {children}
            </div>
          </ScratchScrollArea>
          {actions && <div className="sr-dialog-footer">{actions}</div>}
        </BaseDialog.Popup>
      </BaseDialog.Portal>
    </BaseDialog.Root>
  );
}

Dialog.propTypes = {
  open: PropTypes.bool.isRequired,
  title: PropTypes.node.isRequired,
  children: PropTypes.node,
  actions: PropTypes.node,
  onClose: PropTypes.func,
  size: PropTypes.oneOf(['small', 'medium', 'large', 'xlarge']),
  busy: PropTypes.bool,
  validationError: PropTypes.node,
  defaultAction: PropTypes.func,
  onKeyDown: PropTypes.func,
  className: PropTypes.string,
  style: PropTypes.object,
};

/**
 * Whether Enter in a dialog or form runs its default action. Not from a
 * textarea or code editor (a new line), a button or select (their own
 * action), or a picker (Enter chooses an option there).
 */
export function enterSubmits(event) {
  const target = event.target;
  if (['TEXTAREA', 'BUTTON', 'SELECT'].includes(target?.tagName)) return false;
  if (target?.getAttribute?.('role') === 'combobox' || target?.getAttribute?.('aria-expanded') === 'true') {
    return false;
  }
  return !target?.closest?.('[data-code-editor], [role="listbox"], [role="combobox"]');
}
