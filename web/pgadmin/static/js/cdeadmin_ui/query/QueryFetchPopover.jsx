/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import PropTypes from 'prop-types';
import {ScratchPopoverPalette} from '../base/ScratchOverlays';
import {Button, IconButton} from '../primitives/Button';
import {NumberField} from '../primitives/Field';
import {Tooltip} from '../navigation/AdvancedNavigation';

const STEP_PRESETS = [50, 100, 250, 500, 1000];
const MAX_PRESETS = [500, 1000, 5000, 10000, 50000];

/**
 * Compact 4-icon query execution cluster for Area 3b or inline query surfaces:
 * [▶ Run] [⏸ Pause] [⏹ Cancel (engine capability-gated)] [🔢 Fetch & Step Limits Popover]
 */
export function QueryExecutionToolbarCluster({
  status = 'idle',
  maxRows = 5000,
  rowsPerStep = 250,
  onMaxRowsChange,
  onRowsPerStepChange,
  onRun,
  onPause,
  onCancel,
  capabilities = {supportsPause: true, supportsCancel: true, cancelMechanism: 'Supported'},
  disabled = false,
}) {
  const isRunning = status === 'running';
  const canPause = Boolean(capabilities?.supportsPause) && (isRunning || status === 'paused');
  const canCancel = Boolean(capabilities?.supportsCancel) && (isRunning || status === 'paused');

  const cancelTitle = capabilities?.supportsCancel
    ? `Cancel query (${capabilities.cancelMechanism || 'driver interrupt'})`
    : `Cancel unavailable (${capabilities?.cancelMechanism || 'not supported by engine'})`;

  return (
    <div
      role="group"
      aria-label="Query execution controls"
      style={{display: 'inline-flex', alignItems: 'center', gap: 3}}
    >
      <Tooltip title="Run query">
        <IconButton
          label="Run query"
          disabled={disabled || isRunning}
          onClick={onRun}
          data-active={isRunning ? 'true' : undefined}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
            <polygon points="4,2.5 13.5,8 4,13.5" />
          </svg>
        </IconButton>
      </Tooltip>

      <Tooltip title={status === 'paused' ? 'Resume next step' : 'Pause step fetch'}>
        <IconButton
          label={status === 'paused' ? 'Resume next step' : 'Pause step fetch'}
          disabled={disabled || !canPause}
          onClick={onPause}
          data-active={status === 'paused' ? 'true' : undefined}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
            <rect x="3.5" y="3" width="3.2" height="10" rx="0.8" />
            <rect x="9.3" y="3" width="3.2" height="10" rx="0.8" />
          </svg>
        </IconButton>
      </Tooltip>

      <Tooltip title={cancelTitle}>
        <IconButton
          label="Cancel query"
          title={cancelTitle}
          disabled={disabled || !canCancel}
          onClick={onCancel}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
            <rect x="3.5" y="3.5" width="9" height="9" rx="1.4" />
          </svg>
        </IconButton>
      </Tooltip>

      <ScratchPopoverPalette
        title="Query Step & Max Row Limits"
        width={280}
        trigger={(
          <IconButton
            label={`Fetch limits: ${rowsPerStep} rows/step, max ${maxRows}`}
            title={`Fetch limits: ${rowsPerStep} rows/step · max ${maxRows} rows`}
            disabled={disabled}
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
              <line x1="2.5" y1="4.5" x2="13.5" y2="4.5" />
              <circle cx="6" cy="4.5" r="1.6" fill="currentColor" />
              <line x1="2.5" y1="8.5" x2="13.5" y2="8.5" />
              <circle cx="10.5" cy="8.5" r="1.6" fill="currentColor" />
              <line x1="2.5" y1="12.5" x2="13.5" y2="12.5" />
              <circle cx="7.5" cy="12.5" r="1.6" fill="currentColor" />
            </svg>
          </IconButton>
        )}
      >
        <div style={{display: 'flex', flexDirection: 'column', gap: 10}}>
          <NumberField
            label="Rows per Step"
            value={rowsPerStep}
            inputProps={{min: 1, max: maxRows}}
            onChange={(e) => onRowsPerStepChange?.(Number(e.target.value))}
          />
          <div style={{display: 'flex', flexWrap: 'wrap', gap: 4}}>
            {STEP_PRESETS.map((n) => (
              <button
                key={n}
                type="button"
                className="sr-bui-chip"
                data-active={rowsPerStep === n ? 'true' : undefined}
                onClick={() => onRowsPerStepChange?.(n)}
              >
                {n}
              </button>
            ))}
          </div>

          <NumberField
            label="Max Rows"
            value={maxRows}
            inputProps={{min: 1, max: 1000000}}
            onChange={(e) => onMaxRowsChange?.(Number(e.target.value))}
          />
          <div style={{display: 'flex', flexWrap: 'wrap', gap: 4}}>
            {MAX_PRESETS.map((n) => (
              <button
                key={n}
                type="button"
                className="sr-bui-chip"
                data-active={maxRows === n ? 'true' : undefined}
                onClick={() => onMaxRowsChange?.(n)}
              >
                {n.toLocaleString()}
              </button>
            ))}
          </div>

          <div style={{fontSize: '0.71rem', color: 'var(--sr-text-muted)', paddingTop: 4, borderTop: '1px solid var(--sr-border-subtle)'}}>
            Engine cancel: <strong>{capabilities?.supportsCancel ? capabilities.cancelMechanism : 'Unsupported'}</strong>
          </div>
        </div>
      </ScratchPopoverPalette>
    </div>
  );
}

QueryExecutionToolbarCluster.propTypes = {
  status: PropTypes.string,
  maxRows: PropTypes.number,
  rowsPerStep: PropTypes.number,
  onMaxRowsChange: PropTypes.func,
  onRowsPerStepChange: PropTypes.func,
  onRun: PropTypes.func,
  onPause: PropTypes.func,
  onCancel: PropTypes.func,
  capabilities: PropTypes.object,
  disabled: PropTypes.bool,
};

/**
 * Compact step-fetch footer bar for query result grids when more steps remain
 * or max-row cap has been reached.
 */
export function QueryStepStatusFooter({
  visibleCount = 0,
  totalAvailable = 0,
  rowsPerStep = 250,
  maxRows = 5000,
  hasMoreSteps = false,
  truncatedByMaxRows = false,
  status = 'idle',
  capabilities,
  onFetchNextStep,
  onFetchToMax,
  onCancel,
}) {
  return (
    <div style={{display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8, width: '100%', justifyContent: 'space-between'}}>
      <div style={{display: 'inline-flex', alignItems: 'center', gap: 6}}>
        <span className="sr-bui-mono">
          Showing {visibleCount.toLocaleString()} of {Math.min(totalAvailable, maxRows).toLocaleString()} rows
        </span>
        <span className="sr-bui-pill">
          Step: {rowsPerStep} · Max: {maxRows.toLocaleString()}
        </span>
        {hasMoreSteps && (
          <span className="sr-bui-pill" data-tone="warning">
            Paused after step
          </span>
        )}
        {truncatedByMaxRows && !hasMoreSteps && (
          <span className="sr-bui-pill" data-tone="info">
            Max rows cap ({maxRows.toLocaleString()}) reached
          </span>
        )}
        {status === 'cancelled' && (
          <span className="sr-bui-pill" data-tone="danger">
            Cancelled
          </span>
        )}
      </div>

      <div style={{display: 'inline-flex', alignItems: 'center', gap: 6}}>
        {hasMoreSteps && (
          <>
            <Button intent="primary" onClick={onFetchNextStep}>
              ▶ Next {rowsPerStep} rows
            </Button>
            <Button onClick={onFetchToMax}>
              ⏭ Fetch to Max ({maxRows.toLocaleString()})
            </Button>
          </>
        )}
        {(hasMoreSteps || status === 'running') && capabilities?.supportsCancel && onCancel && (
          <Button intent="destructive" onClick={onCancel}>
            ⏹ Cancel
          </Button>
        )}
      </div>
    </div>
  );
}

QueryStepStatusFooter.propTypes = {
  visibleCount: PropTypes.number,
  totalAvailable: PropTypes.number,
  rowsPerStep: PropTypes.number,
  maxRows: PropTypes.number,
  hasMoreSteps: PropTypes.bool,
  truncatedByMaxRows: PropTypes.bool,
  status: PropTypes.string,
  capabilities: PropTypes.object,
  onFetchNextStep: PropTypes.func,
  onFetchToMax: PropTypes.func,
  onCancel: PropTypes.func,
};
