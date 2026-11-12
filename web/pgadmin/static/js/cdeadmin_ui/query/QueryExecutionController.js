/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useState} from 'react';

export const DEFAULT_QUERY_LIMITS = Object.freeze({
  maxRows: 5000,
  rowsPerStep: 250,
});

const QUERY_LIMITS_STORAGE_KEY = 'scratchrobin.ui.query_limits.v1';

const ENGINE_CANCEL_SUPPORT = Object.freeze({
  postgresql: {supportsCancel: true, cancelMechanism: 'pg_cancel_backend'},
  postgres: {supportsCancel: true, cancelMechanism: 'pg_cancel_backend'},
  pg: {supportsCancel: true, cancelMechanism: 'pg_cancel_backend'},
  scratchbird: {supportsCancel: true, cancelMechanism: 'sbsql_session_cancel'},
  sbsql: {supportsCancel: true, cancelMechanism: 'sbsql_session_cancel'},
  firebird: {supportsCancel: true, cancelMechanism: 'MON$STATEMENTS / fb_cancel_operation'},
  mariadb: {supportsCancel: true, cancelMechanism: 'KILL QUERY'},
  mysql: {supportsCancel: true, cancelMechanism: 'KILL QUERY'},
  cockroachdb: {supportsCancel: true, cancelMechanism: 'CANCEL QUERY'},
  yugabytedb: {supportsCancel: true, cancelMechanism: 'pg_cancel_backend'},
  tidb: {supportsCancel: true, cancelMechanism: 'KILL TIDB QUERY'},
  clickhouse: {supportsCancel: true, cancelMechanism: 'KILL QUERY'},
  duckdb: {supportsCancel: true, cancelMechanism: 'conn.interrupt()'},
  sqlite: {supportsCancel: true, cancelMechanism: 'conn.interrupt()'},
  mssql: {supportsCancel: true, cancelMechanism: 'Attention signal'},
  oracle: {supportsCancel: true, cancelMechanism: 'OCIBreak'},
  db2: {supportsCancel: true, cancelMechanism: 'SQLCancel'},
  snowflake: {supportsCancel: true, cancelMechanism: 'SYSTEM$CANCEL_QUERY'},
  bigquery: {supportsCancel: true, cancelMechanism: 'jobs.cancel'},
  mongodb: {supportsCancel: true, cancelMechanism: 'killOp'},
  redis: {supportsCancel: false, cancelMechanism: 'Not supported for atomic Redis commands'},
  memcached: {supportsCancel: false, cancelMechanism: 'Not supported by engine'},
});

export function resolveQueryEngineCapabilities(engine) {
  const normalized = String(engine || 'postgresql').trim().toLowerCase();
  const entry = ENGINE_CANCEL_SUPPORT[normalized];
  if (entry) {
    return {
      engine: normalized,
      supportsStepFetch: true,
      supportsPause: true,
      supportsCancel: entry.supportsCancel,
      cancelMechanism: entry.cancelMechanism,
    };
  }
  return {
    engine: normalized || 'unknown',
    supportsStepFetch: true,
    supportsPause: true,
    supportsCancel: false,
    cancelMechanism: 'Cancellation not advertised by engine driver',
  };
}

export function readDefaultQueryLimits() {
  try {
    const raw = typeof window !== 'undefined' ? window.localStorage?.getItem(QUERY_LIMITS_STORAGE_KEY) : null;
    if (!raw) return DEFAULT_QUERY_LIMITS;
    const parsed = JSON.parse(raw);
    return {
      maxRows: Math.max(1, Number(parsed.maxRows) || DEFAULT_QUERY_LIMITS.maxRows),
      rowsPerStep: Math.max(1, Number(parsed.rowsPerStep) || DEFAULT_QUERY_LIMITS.rowsPerStep),
    };
  } catch (_err) {
    return DEFAULT_QUERY_LIMITS;
  }
}

export function writeDefaultQueryLimits(partial) {
  const next = {...readDefaultQueryLimits(), ...partial};
  next.maxRows = Math.max(1, Number(next.maxRows) || DEFAULT_QUERY_LIMITS.maxRows);
  next.rowsPerStep = Math.min(next.maxRows, Math.max(1, Number(next.rowsPerStep) || DEFAULT_QUERY_LIMITS.rowsPerStep));
  try {
    if (typeof window !== 'undefined') {
      window.localStorage?.setItem(QUERY_LIMITS_STORAGE_KEY, JSON.stringify(next));
      window.dispatchEvent(new CustomEvent('scratchrobin:query-limits-prefs', {detail: next}));
    }
  } catch (_err) {
    // Ignore storage errors
  }
  return next;
}

/**
 * Pure step/max-row slicing helper for client-buffered or cursor-paged result sets.
 */
export function sliceRowsForStep(allRows = [], {maxRows = 5000, rowsPerStep = 250, stepsCompleted = 1} = {}) {
  const safeMax = Math.max(1, Number(maxRows) || DEFAULT_QUERY_LIMITS.maxRows);
  const safeStep = Math.max(1, Number(rowsPerStep) || DEFAULT_QUERY_LIMITS.rowsPerStep);
  const cappedTotal = Math.min(allRows.length, safeMax);
  const visibleLimit = Math.min(cappedTotal, Math.max(1, stepsCompleted) * safeStep);
  return {
    visibleRows: allRows.slice(0, visibleLimit),
    visibleCount: visibleLimit,
    cappedTotal,
    totalAvailable: allRows.length,
    hasMoreSteps: visibleLimit < cappedTotal,
    truncatedByMaxRows: allRows.length > safeMax,
  };
}

/**
 * Shared React hook for query-capable surfaces (SQL Editor, View/Edit Data,
 * Visual SQL Builder, BI Question Preview, Cube Try-a-Query, Object Data tab).
 */
export function useQueryExecutionController({
  engine = 'postgresql',
  initialMaxRows,
  initialRowsPerStep,
  allRows = [],
  onCancel,
} = {}) {
  const defaults = useMemo(() => readDefaultQueryLimits(), []);
  const [maxRows, setMaxRowsState] = useState(initialMaxRows ?? defaults.maxRows);
  const [rowsPerStep, setRowsPerStepState] = useState(initialRowsPerStep ?? defaults.rowsPerStep);
  const [stepsCompleted, setStepsCompleted] = useState(1);
  const [status, setStatus] = useState('idle'); // 'idle' | 'running' | 'paused' | 'completed' | 'cancelled'

  useEffect(() => {
    const onPrefs = (e) => {
      if (e?.detail) {
        if (initialMaxRows === undefined) setMaxRowsState(e.detail.maxRows);
        if (initialRowsPerStep === undefined) setRowsPerStepState(e.detail.rowsPerStep);
      }
    };
    if (typeof window !== 'undefined') {
      window.addEventListener('scratchrobin:query-limits-prefs', onPrefs);
      return () => window.removeEventListener('scratchrobin:query-limits-prefs', onPrefs);
    }
    return undefined;
  }, [initialMaxRows, initialRowsPerStep]);

  const capabilities = useMemo(() => resolveQueryEngineCapabilities(engine), [engine]);

  const stepSlice = useMemo(
    () => sliceRowsForStep(allRows, {maxRows, rowsPerStep, stepsCompleted}),
    [allRows, maxRows, rowsPerStep, stepsCompleted]
  );

  const setMaxRows = useCallback((val) => {
    const clean = Math.max(1, Number(val) || DEFAULT_QUERY_LIMITS.maxRows);
    setMaxRowsState(clean);
    setStepsCompleted(1);
  }, []);

  const setRowsPerStep = useCallback((val) => {
    const clean = Math.max(1, Number(val) || DEFAULT_QUERY_LIMITS.rowsPerStep);
    setRowsPerStepState(clean);
    setStepsCompleted(1);
  }, []);

  const markRunStarted = useCallback(() => {
    setStepsCompleted(1);
    setStatus('running');
  }, []);

  const markBatchArrived = useCallback((rowCount = 0) => {
    const safeStep = Math.max(1, Number(rowsPerStep) || DEFAULT_QUERY_LIMITS.rowsPerStep);
    const safeMax = Math.max(1, Number(maxRows) || DEFAULT_QUERY_LIMITS.maxRows);
    setStatus(rowCount > safeStep && safeStep < safeMax ? 'paused' : 'completed');
  }, [rowsPerStep, maxRows]);

  const pauseExecution = useCallback(() => {
    setStatus('paused');
  }, []);

  const fetchNextStep = useCallback(() => {
    setStepsCompleted((prev) => {
      const next = prev + 1;
      const nextVisible = next * rowsPerStep;
      const capped = Math.min(allRows.length, maxRows);
      setStatus(nextVisible < capped ? 'paused' : 'completed');
      return next;
    });
  }, [rowsPerStep, allRows.length, maxRows]);

  const fetchToMaxRows = useCallback(() => {
    const neededSteps = Math.max(1, Math.ceil(maxRows / Math.max(1, rowsPerStep)));
    setStepsCompleted(neededSteps);
    setStatus('completed');
  }, [maxRows, rowsPerStep]);

  const cancelExecution = useCallback(async () => {
    if (!capabilities.supportsCancel) return false;
    setStatus('cancelled');
    await onCancel?.();
    return true;
  }, [capabilities.supportsCancel, onCancel]);

  return {
    engine,
    capabilities,
    status,
    setStatus,
    maxRows,
    setMaxRows,
    rowsPerStep,
    setRowsPerStep,
    stepsCompleted,
    ...stepSlice,
    markRunStarted,
    markBatchArrived,
    pauseExecution,
    fetchNextStep,
    fetchToMaxRows,
    cancelExecution,
  };
}
