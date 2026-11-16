/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import PropTypes from 'prop-types';
import {createRoot} from 'react-dom/client';
import gettext from 'sources/gettext';
import {Dialog} from './Dialog';
import {Button} from '../primitives/Button';

/**
 * 3-button ("Yes", "No", "Cancel") close confirmation dialog for Surfaces
 * with uncommitted transaction activity since the last commit or rollback
 * (especially Firebird SQL, which is always inside a transaction).
 *
 * Choices:
 *   - 'yes'    -> Abandon work: rollback transaction / discard staged edits and close surface
 *   - 'no'     -> Do not abandon: commit transaction / staged edits and close surface
 *   - 'cancel' -> Cancel close: keep surface open with uncommitted work intact
 */
export function UncommittedWorkDialog({
  open,
  surfaceTitle = '',
  isFirebird = true,
  onDecision,
}) {
  return (
    <Dialog
      open={Boolean(open)}
      title={gettext('Abandon Uncommitted Work?')}
      size="small"
      data-cdeadmin-qa-key="uncommitted-work-dialog"
      onClose={() => onDecision?.('cancel')}
      actions={
        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 8,
            width: '100%',
          }}
        >
          <Button
            data-cdeadmin-qa-key="uncommitted-work-cancel"
            onClick={() => onDecision?.('cancel')}
          >
            {gettext('Cancel')}
          </Button>
          <Button
            intent="primary"
            data-cdeadmin-qa-key="uncommitted-work-no"
            onClick={() => onDecision?.('no')}
          >
            {gettext('No')}
          </Button>
          <Button
            intent="danger"
            data-cdeadmin-qa-key="uncommitted-work-yes"
            onClick={() => onDecision?.('yes')}
          >
            {gettext('Yes')}
          </Button>
        </div>
      }
    >
      <div style={{display: 'grid', gap: 10, fontSize: '0.84rem', lineHeight: 1.45}}>
        <p style={{margin: 0}}>
          {isFirebird
            ? gettext(
              'This Firebird surface%s has an uncommitted transaction with activity since the last commit or rollback. Do you mean to abandon your work?',
              surfaceTitle ? ` (${surfaceTitle})` : ''
            )
            : gettext(
              'This surface%s has uncommitted activity since the last commit or rollback. Do you mean to abandon your work?',
              surfaceTitle ? ` (${surfaceTitle})` : ''
            )}
        </p>
        <div
          style={{
            padding: '8px 10px',
            borderRadius: 6,
            border: '1px solid var(--sr-border-subtle, rgba(128,128,128,0.25))',
            fontSize: '0.78rem',
            display: 'grid',
            gap: 4,
          }}
        >
          <div>
            <strong>{gettext('Yes')}</strong> —{' '}
            {gettext('Abandon work (rollback transaction and close surface)')}
          </div>
          <div>
            <strong>{gettext('No')}</strong> —{' '}
            {gettext('Commit work and close surface')}
          </div>
          <div>
            <strong>{gettext('Cancel')}</strong> —{' '}
            {gettext('Keep surface open without closing')}
          </div>
        </div>
      </div>
    </Dialog>
  );
}

UncommittedWorkDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  surfaceTitle: PropTypes.string,
  isFirebird: PropTypes.bool,
  onDecision: PropTypes.func.isRequired,
};

/**
 * Imperatively open UncommittedWorkDialog in document.body so it works both
 * for active Surfaces and when closing an unfocused background Surface tab.
 *
 * @returns {Promise<'yes'|'no'|'cancel'>}
 */
export function promptAbandonUncommittedWork({
  surfaceTitle = '',
  isFirebird = true,
} = {}) {
  if (typeof document === 'undefined' || !document.body) {
    return Promise.resolve('cancel');
  }
  return new Promise((resolve) => {
    const hostEl = document.createElement('div');
    hostEl.setAttribute('data-sr-uncommitted-work-portal', 'true');
    document.body.appendChild(hostEl);
    const root = createRoot(hostEl);
    let settled = false;

    const finish = (choice) => {
      if (settled) return;
      settled = true;
      resolve(choice || 'cancel');
      setTimeout(() => {
        try {
          root.unmount();
        } catch {
          // Ignore unmount race
        }
        hostEl.remove();
      }, 0);
    };

    root.render(
      <UncommittedWorkDialog
        open
        surfaceTitle={surfaceTitle}
        isFirebird={isFirebird}
        onDecision={finish}
      />
    );
  });
}

export default UncommittedWorkDialog;
