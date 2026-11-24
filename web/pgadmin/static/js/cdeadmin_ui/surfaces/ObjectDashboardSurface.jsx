/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {Checkbox, Select} from '../primitives/Choice';
import {TextField} from '../primitives/Field';
import {ScratchScrollArea} from '../base/ScratchScrollArea';
import {Dialog} from '../overlays/Dialog';
import {StatusBadge} from '../status/StatusBadge';
import {Icon} from '../icons/Icon';
import UnifiedDataGrid from '../data/UnifiedDataGrid';
import {DDNViewerSurface} from '../integrations/ddn/DDNViewerSurface';

const SERIES_COLORS = [
  '#2563eb',
  '#0d9488',
  '#d97706',
  '#7c3aed',
  '#dc2626',
  '#0284c7',
];

const SEGMENT_COLORS = {
  primary: '#2563eb',
  info: '#0ea5e9',
  warning: '#f59e0b',
  danger: '#dc2626',
  neutral: '#94a3b8',
};

const WINDOW_LABELS = {
  live: () => gettext('Live (15m)'),
  '1h': () => gettext('Last 1 Hour (Raw)'),
  '24h': () => gettext('Last 24 Hours (Raw)'),
  '30d': () => gettext('Last 30 Days (5m Rollup)'),
  '365d': () => gettext('Last 365 Days (1h Rollup)'),
};

export function extractNodeQueryParams(nodeData) {
  if (!nodeData) return {};
  const nodeType = String(nodeData._type || '');
  const serverId =
    nodeData._type === 'server'
      ? nodeData._id ?? nodeData.id
      : nodeData.server_id ?? nodeData._pid ?? '';
  const dbTargetId =
    nodeData.cde_database_target_id ??
    (nodeData._type === 'cde_database_target' || nodeData._type === 'database'
      ? nodeData._id
      : '');
  const resourceId = nodeData.cde_resource_id || '';
  const rawKind =
    nodeData.cde_resource_kind ||
    (nodeType === 'cde_database_target' ? 'database' : nodeType);
  const engineId = nodeData.cde_engine_id || nodeData.engine_id || '';
  const label = String(nodeData.label || nodeData._label || '').trim();
  const dbName = String(
    nodeData.cde_database || nodeData.database || (rawKind === 'database' ? label : '')
  ).trim();
  return {
    node_type: nodeType,
    object_kind: rawKind,
    server_id: Number.isFinite(Number(serverId)) ? Number(serverId) : 0,
    database_target_id: String(dbTargetId || ''),
    resource_id: String(resourceId || ''),
    schema: String(nodeData.schema || ''),
    object_name: label,
    database_name: dbName,
    engine_id: String(engineId || ''),
  };
}

function buildJsonHeaders() {
  const win = typeof window !== 'undefined' ? window : {};
  const headerName = win.pgAdmin?.csrf_token_header || 'X-pgA-CSRFToken';
  const token = win.pgAdmin?.csrf_token || '';
  return {
    'Content-Type': 'application/json',
    ...(token ? {[headerName]: token} : {}),
  };
}

function formatSeriesValue(val, unit) {
  if (val === null || val === undefined || Number.isNaN(Number(val))) return '—';
  const num = Number(val);
  if (unit === 'bytes') {
    const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
    let v = num;
    let i = 0;
    while (v >= 1024 && i < units.length - 1) {
      v /= 1024;
      i += 1;
    }
    return i === 0 ? `${Math.round(v)} B` : `${v.toFixed(2)} ${units[i]}`;
  }
  if (unit === 'percent') return `${num.toFixed(1)}%`;
  if (unit === 'per_sec') return `${num.toFixed(2)}/s`;
  if (Math.abs(num - Math.round(num)) < 1e-6) return Math.round(num).toLocaleString();
  return num.toFixed(2);
}

function formatTimeShort(tsMs, windowId) {
  if (!tsMs) return '';
  const d = new Date(Number(tsMs));
  if (Number.isNaN(d.getTime())) return '';
  if (windowId === '30d' || windowId === '365d') {
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:00`;
  }
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
}

function HistoricSeriesChartCard({groupTitle, seriesList, windowId}) {
  const width = 520;
  const height = 148;
  const padL = 48;
  const padR = 14;
  const padT = 14;
  const padB = 24;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  const allPts = seriesList.flatMap((s) => s.points || []);
  const minTs = allPts.length ? Math.min(...allPts.map((p) => p.ts)) : Date.now() - 3600_000;
  const maxTs = allPts.length ? Math.max(...allPts.map((p) => p.ts)) : Date.now();
  const tsSpan = Math.max(1, maxTs - minTs);

  const rawMaxV = allPts.length
    ? Math.max(...allPts.map((p) => Math.max(Number(p.max ?? p.value ?? 0), Number(p.value ?? 0))))
    : 1;
  const maxV = rawMaxV <= 0 ? 1 : rawMaxV * 1.08;
  const primaryUnit = seriesList[0]?.unit || 'count';

  const toX = (ts) =>
    allPts.length <= 1
      ? padL + plotW / 2
      : padL + ((Number(ts) - minTs) / tsSpan) * plotW;
  const toY = (v) => padT + plotH - (Math.max(0, Number(v || 0)) / maxV) * plotH;

  return (
    <div
      data-cdeadmin-qa-key={`dashboard-history-chart-${groupTitle}`}
      style={{
        border: '1px solid var(--sr-border-default)',
        borderRadius: 10,
        padding: '12px 14px',
        background: 'var(--sr-surface-default, var(--sr-island-bg))',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8}}>
        <span style={{fontWeight: 600, fontSize: '0.84rem'}}>{groupTitle}</span>
        <span style={{fontSize: '0.72rem', color: 'var(--sr-text-secondary)'}}>
          {seriesList[0]?.resolution === '1h'
            ? gettext('1h rollups')
            : seriesList[0]?.resolution === '5m'
              ? gettext('5m rollups')
              : gettext('raw samples')}
        </span>
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        style={{width: '100%', height: 148, display: 'block', overflow: 'visible'}}
        role="img"
        aria-label={groupTitle}
      >
        {[0, 0.5, 1].map((frac) => {
          const y = padT + plotH * (1 - frac);
          const labelVal = formatSeriesValue(maxV * frac, primaryUnit);
          return (
            <g key={frac}>
              <line
                x1={padL}
                y1={y}
                x2={width - padR}
                y2={y}
                stroke="var(--sr-border-subtle, rgba(148,163,184,0.28))"
                strokeDasharray={frac === 0 ? undefined : '3 3'}
              />
              <text
                x={padL - 6}
                y={y + 3}
                textAnchor="end"
                fontSize="9.5"
                fill="var(--sr-text-secondary, #64748b)"
              >
                {labelVal}
              </text>
            </g>
          );
        })}

        {seriesList.map((s, idx) => {
          const color = SERIES_COLORS[idx % SERIES_COLORS.length];
          const pts = s.points || [];
          if (!pts.length) return null;
          if (pts.length === 1) {
            const cx = toX(pts[0].ts);
            const cy = toY(pts[0].value);
            return <circle key={s.series_id} cx={cx} cy={cy} r={4} fill={color} />;
          }
          const lineD = pts
            .map((p, i) => `${i === 0 ? 'M' : 'L'} ${toX(p.ts).toFixed(1)} ${toY(p.value).toFixed(1)}`)
            .join(' ');
          const areaD = `${lineD} L ${toX(pts[pts.length - 1].ts).toFixed(1)} ${(padT + plotH).toFixed(1)} L ${toX(pts[0].ts).toFixed(1)} ${(padT + plotH).toFixed(1)} Z`;
          return (
            <g key={s.series_id}>
              {idx === 0 && <path d={areaD} fill={color} fillOpacity="0.11" />}
              <path d={lineD} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" />
            </g>
          );
        })}

        {allPts.length > 0 && (
          <>
            <text x={padL} y={height - 5} fontSize="9.5" fill="var(--sr-text-secondary, #64748b)">
              {formatTimeShort(minTs, windowId)}
            </text>
            <text
              x={width - padR}
              y={height - 5}
              textAnchor="end"
              fontSize="9.5"
              fill="var(--sr-text-secondary, #64748b)"
            >
              {formatTimeShort(maxTs, windowId)}
            </text>
          </>
        )}
      </svg>

      <div style={{display: 'flex', flexWrap: 'wrap', gap: '6px 14px', fontSize: '0.75rem'}}>
        {seriesList.map((s, idx) => {
          const color = SERIES_COLORS[idx % SERIES_COLORS.length];
          return (
            <div key={s.series_id} style={{display: 'inline-flex', alignItems: 'center', gap: 6}}>
              <span
                style={{
                  width: 9,
                  height: 9,
                  borderRadius: '50%',
                  background: color,
                  display: 'inline-block',
                }}
              />
              <span style={{fontWeight: 500}}>{s.label}:</span>
              <span style={{fontFamily: 'var(--sr-font-mono, monospace)'}}>
                {formatSeriesValue(s.latest_value, s.unit)}
              </span>
              {s.sample_count > 1 && (
                <span style={{color: 'var(--sr-text-secondary)'}}>
                  (max {formatSeriesValue(s.max_value, s.unit)})
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

HistoricSeriesChartCard.propTypes = {
  groupTitle: PropTypes.string.isRequired,
  seriesList: PropTypes.array.isRequired,
  windowId: PropTypes.string.isRequired,
};

function buildFallbackSnapshotFromNode(nodeData) {
  const q = extractNodeQueryParams(nodeData);
  const title = q.object_name || q.database_name || gettext('Selected Object');
  const engineLabel =
    nodeData?.engine_display_name ||
    (q.engine_id ? q.engine_id.charAt(0).toUpperCase() + q.engine_id.slice(1) : gettext('Database'));
  const connected = Boolean(
    nodeData?.connected || nodeData?.runtime_verification_state === 'verified'
  );
  const fallbackKpis = [];
  if (nodeData?.host) {
    fallbackKpis.push({
      id: 'endpoint_host',
      label: gettext('Endpoint'),
      formatted: nodeData.port ? `${nodeData.host}:${nodeData.port}` : String(nodeData.host),
      subtext: nodeData.username ? `${gettext('User')}: ${nodeData.username}` : '',
      status: 'ok',
    });
  }
  if (nodeData?.cde_database) {
    fallbackKpis.push({
      id: 'target_database',
      label: gettext('Database Target'),
      formatted: String(nodeData.cde_database),
      subtext: engineLabel,
      status: 'ok',
    });
  }
  return {
    object_identity: {
      object_kind: q.object_kind || 'object',
      object_key: `${q.object_kind}:${q.server_id}:${q.database_target_id || q.object_name}`,
      title,
      subtitle: `${engineLabel} · ${String(q.object_kind || 'object')}`,
      engine_id: q.engine_id || 'postgresql',
      engine_label: engineLabel,
      connected,
      status_banner: connected ? null : null,
    },
    comment: {
      text: String(nodeData?.comment || nodeData?.description || ''),
      supported: true,
    },
    kpis: fallbackKpis,
    storage_bars: [],
    rankings: [],
    history: {
      window: '1h',
      resolution: 'raw',
      series: [],
      retention_policy: {raw_hours: 24, rollup_5m_days: 30, rollup_1h_days: 365},
    },
    ddn: {ddn_text: '', scene: null},
    deep_stats: {available_actions: [], cached: null},
    reports: [],
    customization: {
      show_comment_banner: true,
      show_kpi_strip: true,
      show_ddn_topology: true,
      show_historic_charts: true,
      show_storage_and_rankings: true,
      show_deep_stats: true,
      show_diagnostic_reports: true,
      default_window: '1h',
    },
  };
}

export default function ObjectDashboardSurface({
  boundNodeData,
  instanceId,
  historyWindow = '1h',
  autoRefreshSec = 0,
  onHistoryWindowChange,
}) {
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const fallbackPayload = useMemo(
    () => buildFallbackSnapshotFromNode(boundNodeData),
    [boundNodeData]
  );

  const [payload, setPayload] = useState(fallbackPayload);
  const [loading, setLoading] = useState(false);
  const [deepRunning, setDeepRunning] = useState(false);
  const [deepError, setDeepError] = useState('');
  const [customizeOpen, setCustomizeOpen] = useState(false);
  const [customDraft, setCustomDraft] = useState(fallbackPayload.customization);
  const [retentionDraft, setRetentionDraft] = useState({
    raw_hours: 24,
    rollup_5m_days: 30,
    rollup_1h_days: 365,
  });

  const queryParams = useMemo(() => extractNodeQueryParams(boundNodeData), [boundNodeData]);
  const querySignature = useMemo(() => JSON.stringify(queryParams), [queryParams]);

  const fetchSnapshot = useCallback(
    async (winOverride = null, recordSample = true) => {
      if (typeof fetch !== 'function' || !boundNodeData) return;
      const effectiveWin = winOverride || historyWindow || '1h';
      const search = new URLSearchParams();
      Object.entries(queryParams).forEach(([k, v]) => {
        if (v !== '' && v !== null && v !== undefined) {
          search.set(k, String(v));
        }
      });
      search.set('window', effectiveWin);
      search.set('record_sample', recordSample ? '1' : '0');

      setLoading(true);
      try {
        const resp = await fetch(`/cdeadmin/api/object_dashboard/snapshot?${search.toString()}`, {
          credentials: 'same-origin',
        });
        if (!resp.ok) return;
        const json = await resp.json();
        if (mountedRef.current && json && json.object_identity) {
          setPayload(json);
          if (json.customization) {
            setCustomDraft((prev) => ({...prev, ...json.customization}));
          }
          if (json.history?.retention_policy) {
            setRetentionDraft(json.history.retention_policy);
          }
        }
      } catch {
        // Keep clean local fallback when offline or in unit test harness.
      } finally {
        if (mountedRef.current) {
          setLoading(false);
        }
      }
    },
    [boundNodeData, historyWindow, queryParams]
  );

  useEffect(() => {
    setPayload(fallbackPayload);
    setDeepError('');
    void fetchSnapshot(historyWindow, true);
  }, [querySignature]);

  useEffect(() => {
    void fetchSnapshot(historyWindow, false);
  }, [historyWindow]);

  // Opt-In Tier-2 Live Auto-Refresh (paused when tab is hidden)
  useEffect(() => {
    const sec = Number(autoRefreshSec || 0);
    if (!sec || sec <= 0 || typeof window === 'undefined') return undefined;
    const timer = window.setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      void fetchSnapshot(historyWindow, true);
    }, sec * 1000);
    return () => window.clearInterval(timer);
  }, [autoRefreshSec, fetchSnapshot, historyWindow]);

  const triggerDeepRefresh = useCallback(async () => {
    if (typeof fetch !== 'function' || !boundNodeData) return;
    setDeepRunning(true);
    setDeepError('');
    try {
      const resp = await fetch('/cdeadmin/api/object_dashboard/deep_refresh', {
        method: 'POST',
        credentials: 'same-origin',
        headers: buildJsonHeaders(),
        body: JSON.stringify({...queryParams, window: historyWindow}),
      });
      const json = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        if (mountedRef.current) {
          setDeepError(json.error || gettext('Unable to compute deep statistics while disconnected.'));
        }
        return;
      }
      if (mountedRef.current) {
        setPayload((prev) => ({
          ...prev,
          deep_stats: json.deep_stats || prev.deep_stats,
          history: json.history?.series?.length ? {...prev.history, ...json.history} : prev.history,
        }));
      }
    } catch (err) {
      if (mountedRef.current) {
        setDeepError(String(err?.message || gettext('Deep statistics scan failed.')));
      }
    } finally {
      if (mountedRef.current) {
        setDeepRunning(false);
      }
    }
  }, [boundNodeData, historyWindow, queryParams]);

  // Ribbon Action Event Listeners
  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const matchesInstance = (ev) =>
      !ev?.detail?.instanceId || !instanceId || ev.detail.instanceId === instanceId;

    const onRefresh = (ev) => {
      if (matchesInstance(ev)) void fetchSnapshot(historyWindow, true);
    };
    const onDeep = (ev) => {
      if (matchesInstance(ev)) void triggerDeepRefresh();
    };
    const onCustomize = (ev) => {
      if (matchesInstance(ev)) setCustomizeOpen(true);
    };
    window.addEventListener('scratchrobin:object-dashboard-refresh', onRefresh);
    window.addEventListener('scratchrobin:object-dashboard-deep-refresh', onDeep);
    window.addEventListener('scratchrobin:object-dashboard-customize', onCustomize);
    return () => {
      window.removeEventListener('scratchrobin:object-dashboard-refresh', onRefresh);
      window.removeEventListener('scratchrobin:object-dashboard-deep-refresh', onDeep);
      window.removeEventListener('scratchrobin:object-dashboard-customize', onCustomize);
    };
  }, [fetchSnapshot, historyWindow, instanceId, triggerDeepRefresh]);

  const handleSaveCustomization = async () => {
    setPayload((prev) => ({...prev, customization: {...customDraft}}));
    setCustomizeOpen(false);
    if (customDraft.default_window && onHistoryWindowChange) {
      onHistoryWindowChange(customDraft.default_window);
    }
    if (typeof fetch === 'function') {
      try {
        await fetch('/cdeadmin/api/object_dashboard/preferences', {
          method: 'POST',
          credentials: 'same-origin',
          headers: buildJsonHeaders(),
          body: JSON.stringify({
            dashboard: customDraft,
            retention_policy: retentionDraft,
          }),
        });
      } catch {
        // Ignore offline preference persistence error in test mode.
      }
    }
  };

  const identity = payload.object_identity || fallbackPayload.object_identity;
  const cust = payload.customization || fallbackPayload.customization;
  const kpis = payload.kpis || [];
  const storageBars = payload.storage_bars || [];
  const rankings = payload.rankings || [];
  const reports = payload.reports || [];
  const historySeries = payload.history?.series || [];
  const deepStats = payload.deep_stats || {available_actions: [], cached: null};

  const groupedSeries = useMemo(() => {
    const groups = new Map();
    const titles = {
      sessions: gettext('Sessions & Connections'),
      transactions: gettext('Transactions & Horizon'),
      throughput: gettext('Query Throughput'),
      memory: gettext('Memory & Cache Hit Ratio'),
      io: gettext('Page & Disk I/O'),
      storage: gettext('Storage Footprint'),
      rows: gettext('Row Cardinality & Dead Tuples'),
      catalog: gettext('Catalog Object Inventory'),
      general: gettext('Engine Telemetry'),
    };
    historySeries.forEach((s) => {
      const gKey = `${s.group || 'general'}:${s.unit || 'count'}`;
      if (!groups.has(gKey)) {
        groups.set(gKey, {
          key: gKey,
          title: titles[s.group] || s.label || gettext('Historic Metrics'),
          items: [],
        });
      }
      groups.get(gKey).items.push(s);
    });
    return Array.from(groups.values());
  }, [historySeries]);

  return (
    <ScratchScrollArea orientation="both" style={{flex: 1, minHeight: 0}}>
      <Box
        data-cdeadmin-qa-key="object-dashboard-surface"
        sx={{
          p: 2,
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
          minWidth: 0,
        }}
      >
        {/* 1. Identity & Comment Header */}
        <div
          data-cdeadmin-qa-key="object-dashboard-header"
          style={{
            border: '1px solid var(--sr-border-default)',
            borderRadius: 10,
            padding: '12px 16px',
            background: 'var(--sr-surface-subtle)',
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
              flexWrap: 'wrap',
            }}
          >
            <div style={{display: 'flex', alignItems: 'center', gap: 10, minWidth: 0}}>
              <Icon
                iconKey={`engine.${identity.engine_id || 'postgresql'}`}
                decorative
                size={24}
              />
              <div style={{minWidth: 0}}>
                <div style={{fontWeight: 700, fontSize: '0.98rem'}}>
                  {gettext('%s Dashboard — %s', identity.object_kind === 'server' ? gettext('Server') : identity.object_kind === 'database' ? gettext('Database') : gettext('Object'), identity.title)}
                </div>
                <div style={{fontSize: '0.76rem', color: 'var(--sr-text-secondary)'}}>
                  {identity.subtitle}
                  {identity.verified_version ? ` · ${identity.verified_version}` : ''}
                </div>
              </div>
            </div>

            <div style={{display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap'}}>
              <StatusBadge
                status={identity.connected ? 'success' : 'neutral'}
                label={identity.connected ? gettext('Connected') : gettext('Stored History / Offline')}
              />
              <StatusBadge
                status="info"
                label={(WINDOW_LABELS[historyWindow] || WINDOW_LABELS['1h'])()}
              />
              {Number(autoRefreshSec) > 0 && (
                <StatusBadge
                  status="success"
                  label={gettext('Auto-Refresh %ss', autoRefreshSec)}
                />
              )}
              {loading && (
                <span style={{fontSize: '0.74rem', color: 'var(--sr-text-secondary)'}}>
                  {gettext('Refreshing…')}
                </span>
              )}
            </div>
          </div>

          {identity.status_banner && (
            <div
              data-cdeadmin-qa-key="object-dashboard-offline-banner"
              style={{
                fontSize: '0.78rem',
                padding: '6px 10px',
                borderRadius: 6,
                background: 'var(--sr-surface-default, rgba(148,163,184,0.12))',
                color: 'var(--sr-text-secondary)',
              }}
            >
              {identity.status_banner}
            </div>
          )}

          {cust.show_comment_banner !== false && payload.comment?.text && (
            <div
              data-cdeadmin-qa-key="object-dashboard-comment"
              style={{
                padding: '8px 12px',
                borderRadius: 8,
                borderLeft: '3px solid var(--sr-accent-primary, #2563eb)',
                background: 'var(--sr-surface-default, var(--sr-island-bg))',
                fontSize: '0.82rem',
                whiteSpace: 'pre-wrap',
                lineHeight: 1.45,
              }}
            >
              <div
                style={{
                  fontSize: '0.7rem',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                  color: 'var(--sr-text-secondary)',
                  marginBottom: 2,
                }}
              >
                {gettext('Comment / Description')}
              </div>
              {payload.comment.text}
            </div>
          )}
        </div>

        {/* 2. Bounded Capacity & KPI Strip */}
        {cust.show_kpi_strip !== false && kpis.length > 0 && (
          <div
            data-cdeadmin-qa-key="object-dashboard-kpi-strip"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))',
              gap: 10,
            }}
          >
            {kpis.map((kpi) => {
              const capPct =
                typeof kpi.capacity_pct === 'number' && Number.isFinite(kpi.capacity_pct)
                  ? Math.max(0, Math.min(100, kpi.capacity_pct))
                  : null;
              const barColor =
                kpi.status === 'critical'
                  ? '#dc2626'
                  : kpi.status === 'warning'
                    ? '#d97706'
                    : '#2563eb';
              return (
                <div
                  key={kpi.id}
                  data-cdeadmin-qa-key={`dashboard-kpi-${kpi.id}`}
                  style={{
                    border: '1px solid var(--sr-border-default)',
                    borderRadius: 10,
                    padding: '10px 12px',
                    background: 'var(--sr-surface-default, var(--sr-island-bg))',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 4,
                  }}
                >
                  <div style={{fontSize: '0.74rem', color: 'var(--sr-text-secondary)', fontWeight: 500}}>
                    {kpi.label}
                  </div>
                  <div
                    style={{
                      fontSize: '1.08rem',
                      fontWeight: 700,
                      fontFamily: 'var(--sr-font-mono, monospace)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                    title={String(kpi.formatted ?? kpi.value ?? '')}
                  >
                    {kpi.formatted ?? kpi.value}
                  </div>
                  {capPct !== null && (
                    <div
                      style={{
                        position: 'relative',
                        height: 6,
                        borderRadius: 999,
                        background: 'rgba(148, 163, 184, 0.22)',
                        overflow: 'hidden',
                        marginTop: 2,
                      }}
                    >
                      <div
                        style={{
                          width: `${capPct}%`,
                          height: '100%',
                          background: barColor,
                          borderRadius: 999,
                        }}
                      />
                    </div>
                  )}
                  {kpi.subtext && (
                    <div
                      style={{
                        fontSize: '0.72rem',
                        color: 'var(--sr-text-secondary)',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                      title={kpi.subtext}
                    >
                      {kpi.subtext}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* 3. Historic Time-Series Metrics from Encrypted Firebird Embedded DB */}
        {cust.show_historic_charts !== false && (
          <div
            data-cdeadmin-qa-key="object-dashboard-history-section"
            style={{display: 'flex', flexDirection: 'column', gap: 10}}
          >
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
              <div style={{fontWeight: 600, fontSize: '0.88rem'}}>
                {gettext('Historic Metrics (Embedded UserConfigurationDatabase)')}
              </div>
              <div style={{fontSize: '0.74rem', color: 'var(--sr-text-secondary)'}}>
                {gettext(
                  'Retention: %sh raw · %sd 5m · %sd 1h',
                  retentionDraft.raw_hours,
                  retentionDraft.rollup_5m_days,
                  retentionDraft.rollup_1h_days
                )}
              </div>
            </div>

            {groupedSeries.length === 0 ? (
              <div
                style={{
                  border: '1px dashed var(--sr-border-default)',
                  borderRadius: 10,
                  padding: '14px 16px',
                  fontSize: '0.8rem',
                  color: 'var(--sr-text-secondary)',
                }}
              >
                {gettext(
                  'No historic metric samples recorded in this time window yet. Connect or click Refresh Dashboard on the ribbon to record observations into UserConfigurationDatabase.'
                )}
              </div>
            ) : (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
                  gap: 12,
                }}
              >
                {groupedSeries.map((grp) => (
                  <HistoricSeriesChartCard
                    key={grp.key}
                    groupTitle={grp.title}
                    seriesList={grp.items}
                    windowId={historyWindow}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* 4. Storage Composition Bars & Top-N Rankings */}
        {cust.show_storage_and_rankings !== false &&
          (storageBars.length > 0 || rankings.length > 0) && (
          <div
            data-cdeadmin-qa-key="object-dashboard-storage-rankings"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))',
              gap: 12,
            }}
          >
            {storageBars.map((bar) => (
              <div
                key={bar.id}
                style={{
                  border: '1px solid var(--sr-border-default)',
                  borderRadius: 10,
                  padding: '12px 14px',
                  background: 'var(--sr-surface-default, var(--sr-island-bg))',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 10,
                }}
              >
                <div style={{display: 'flex', justifyContent: 'space-between', fontSize: '0.84rem'}}>
                  <span style={{fontWeight: 600}}>{bar.title}</span>
                  <span style={{fontFamily: 'var(--sr-font-mono, monospace)', fontWeight: 600}}>
                    {bar.total_formatted}
                  </span>
                </div>
                <div
                  style={{
                    display: 'flex',
                    height: 14,
                    borderRadius: 999,
                    overflow: 'hidden',
                    background: 'rgba(148, 163, 184, 0.2)',
                  }}
                >
                  {(bar.segments || []).map((seg) => (
                    <div
                      key={seg.id}
                      title={`${seg.label}: ${seg.formatted} (${seg.pct}%)`}
                      style={{
                        width: `${Math.max(seg.bytes > 0 ? 2 : 0, seg.pct || 0)}%`,
                        background: SEGMENT_COLORS[seg.tone] || SEGMENT_COLORS.primary,
                      }}
                    />
                  ))}
                </div>
                <div style={{display: 'flex', flexWrap: 'wrap', gap: '6px 14px', fontSize: '0.75rem'}}>
                  {(bar.segments || []).map((seg) => (
                    <div key={seg.id} style={{display: 'inline-flex', alignItems: 'center', gap: 6}}>
                      <span
                        style={{
                          width: 8,
                          height: 8,
                          borderRadius: 2,
                          background: SEGMENT_COLORS[seg.tone] || SEGMENT_COLORS.primary,
                        }}
                      />
                      <span>{seg.label}:</span>
                      <span style={{fontFamily: 'var(--sr-font-mono, monospace)'}}>
                        {seg.formatted} ({seg.pct}%)
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))}

            {rankings.map((rk) => (
              <div
                key={rk.id}
                style={{
                  border: '1px solid var(--sr-border-default)',
                  borderRadius: 10,
                  padding: '12px 14px',
                  background: 'var(--sr-surface-default, var(--sr-island-bg))',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 8,
                }}
              >
                <div style={{fontWeight: 600, fontSize: '0.84rem'}}>{rk.title}</div>
                <div style={{display: 'flex', flexDirection: 'column', gap: 6}}>
                  {(rk.items || []).slice(0, 8).map((item) => (
                    <div key={item.id} style={{display: 'flex', flexDirection: 'column', gap: 2}}>
                      <div style={{display: 'flex', justifyContent: 'space-between', fontSize: '0.76rem'}}>
                        <span style={{fontWeight: 500}}>{item.label}</span>
                        <span style={{fontFamily: 'var(--sr-font-mono, monospace)'}}>
                          {item.formatted}
                        </span>
                      </div>
                      <div
                        style={{
                          height: 5,
                          borderRadius: 999,
                          background: 'rgba(148, 163, 184, 0.18)',
                          overflow: 'hidden',
                        }}
                      >
                        <div
                          style={{
                            width: `${Math.max(2, item.pct_of_max || 0)}%`,
                            height: '100%',
                            background: '#0d9488',
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 5. Shared DDN Topology & Architecture Overview */}
        {cust.show_ddn_topology !== false && payload.ddn?.ddn_text && (
          <div
            data-cdeadmin-qa-key="object-dashboard-ddn-card"
            style={{
              border: '1px solid var(--sr-border-default)',
              borderRadius: 10,
              overflow: 'hidden',
              background: 'var(--sr-surface-default, var(--sr-island-bg))',
            }}
          >
            <div
              style={{
                padding: '8px 14px',
                borderBottom: '1px solid var(--sr-border-default)',
                fontWeight: 600,
                fontSize: '0.84rem',
              }}
            >
              {gettext('DDN Architecture & Object Neighborhood')}
            </div>
            <div style={{height: 250, minHeight: 220}}>
              <DDNViewerSurface
                files={{'dashboard.ddn': payload.ddn.ddn_text}}
                initialScene={payload.ddn.scene || null}
                showViewSelector={false}
              />
            </div>
          </div>
        )}

        {/* 6. Explicit On-Demand Deep Statistics (Zero Automatic Query Churn) */}
        {cust.show_deep_stats !== false &&
          (deepStats.available_actions?.length > 0 || deepStats.cached) && (
          <div
            data-cdeadmin-qa-key="object-dashboard-deep-stats"
            style={{
              border: '1px solid var(--sr-border-default)',
              borderRadius: 10,
              padding: '12px 16px',
              background: 'var(--sr-surface-subtle)',
              display: 'flex',
              flexDirection: 'column',
              gap: 10,
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: 12,
                flexWrap: 'wrap',
              }}
            >
              <div>
                <div style={{fontWeight: 600, fontSize: '0.86rem'}}>
                  {gettext('On-Demand Deep Statistics (Churn-Protected)')}
                </div>
                <div style={{fontSize: '0.75rem', color: 'var(--sr-text-secondary)'}}>
                  {deepStats.cached?.computed_at
                    ? gettext('Last computed: %s', deepStats.cached.computed_at)
                    : gettext(
                      'Full-scan statistics (exact COUNT(*), page slack, column profiles) run only when requested via Compute Deep Stats on the ribbon.'
                    )}
                </div>
              </div>
              {deepRunning && (
                <StatusBadge status="info" label={gettext('Computing deep statistics…')} />
              )}
            </div>

            {deepError && (
              <div style={{fontSize: '0.78rem', color: '#dc2626'}}>{deepError}</div>
            )}

            {deepStats.cached?.stats?.metrics?.length > 0 && (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))',
                  gap: 8,
                }}
              >
                {deepStats.cached.stats.metrics.map((m, idx) => (
                  <div
                    key={`${m.label}-${idx}`}
                    style={{
                      padding: '8px 10px',
                      borderRadius: 8,
                      border: '1px solid var(--sr-border-default)',
                      background: 'var(--sr-surface-default, var(--sr-island-bg))',
                    }}
                  >
                    <div style={{fontSize: '0.72rem', color: 'var(--sr-text-secondary)'}}>
                      {m.label}
                    </div>
                    <div style={{fontWeight: 700, fontFamily: 'var(--sr-font-mono, monospace)'}}>
                      {m.value}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {(deepStats.cached?.stats?.tables || []).map((tbl) => (
              <div key={tbl.id} style={{display: 'flex', flexDirection: 'column', gap: 6}}>
                <div style={{fontWeight: 600, fontSize: '0.8rem'}}>{tbl.title}</div>
                <div style={{height: 240, border: '1px solid var(--sr-border-default)', borderRadius: 8}}>
                  <UnifiedDataGrid
                    columns={tbl.columns || []}
                    rows={tbl.rows || []}
                    editable={false}
                  />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 7. Diagnostic Reports (UnifiedDataGrid) */}
        {cust.show_diagnostic_reports !== false &&
          reports.map((rep) => (
            <div
              key={rep.id}
              data-cdeadmin-qa-key={`dashboard-report-${rep.id}`}
              style={{
                border: '1px solid var(--sr-border-default)',
                borderRadius: 10,
                padding: '12px 14px',
                background: 'var(--sr-surface-default, var(--sr-island-bg))',
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
              }}
            >
              <div>
                <div style={{fontWeight: 600, fontSize: '0.86rem'}}>{rep.title}</div>
                {rep.description && (
                  <div style={{fontSize: '0.74rem', color: 'var(--sr-text-secondary)'}}>
                    {rep.description}
                  </div>
                )}
              </div>
              <div style={{height: 240, border: '1px solid var(--sr-border-default)', borderRadius: 8}}>
                <UnifiedDataGrid
                  columns={rep.columns || []}
                  rows={rep.rows || []}
                  editable={false}
                />
              </div>
            </div>
          ))}
      </Box>

      {/* Customize Dashboard & Historic Retention Dialog */}
      <Dialog
        open={customizeOpen}
        onClose={() => setCustomizeOpen(false)}
        title={gettext('Customize Dashboard & Historic Metrics')}
        size="medium"
        actions={
          <div style={{display: 'flex', justifyContent: 'flex-end', gap: 8}}>
            <Button size="small" intent="neutral" onClick={() => setCustomizeOpen(false)}>
              {gettext('Cancel')}
            </Button>
            <Button
              size="small"
              intent="primary"
              data-cdeadmin-qa-key="save-dashboard-customization"
              onClick={() => void handleSaveCustomization()}
            >
              {gettext('Save Preferences')}
            </Button>
          </div>
        }
      >
        <div style={{display: 'flex', flexDirection: 'column', gap: 12, padding: '4px 0'}}>
          <div style={{fontWeight: 600, fontSize: '0.84rem'}}>
            {gettext('Visible Dashboard Sections')}
          </div>
          {[
            ['show_comment_banner', gettext('Show Object Comment / Description Banner')],
            ['show_kpi_strip', gettext('Show Bounded Capacity & KPI Strip')],
            ['show_historic_charts', gettext('Show Historic Time-Series Graphs')],
            ['show_storage_and_rankings', gettext('Show Storage Composition & Top-N Rankings')],
            ['show_ddn_topology', gettext('Show DDN Architecture & Neighborhood Diagram')],
            ['show_deep_stats', gettext('Show On-Demand Deep Statistics Panel')],
            ['show_diagnostic_reports', gettext('Show Diagnostic Report Grids')],
          ].map(([field, label]) => (
            <Checkbox
              key={field}
              label={label}
              checked={customDraft[field] !== false}
              onChange={(checked) =>
                setCustomDraft((prev) => ({...prev, [field]: Boolean(checked)}))
              }
            />
          ))}

          <Select
            label={gettext('Default Historic Metric Window')}
            value={customDraft.default_window || '1h'}
            options={[
              {value: 'live', label: gettext('Live (15 minutes)')},
              {value: '1h', label: gettext('Last 1 Hour (Raw)')},
              {value: '24h', label: gettext('Last 24 Hours (Raw)')},
              {value: '30d', label: gettext('Last 30 Days (5-minute Rollups)')},
              {value: '365d', label: gettext('Last 365 Days (1-hour Rollups)')},
            ]}
            onChange={(val) => setCustomDraft((prev) => ({...prev, default_window: val}))}
          />

          <div style={{fontWeight: 600, fontSize: '0.84rem', marginTop: 4}}>
            {gettext('Embedded Vault Retention Policy (user_configuration.fdb)')}
          </div>
          <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10}}>
            <TextField
              label={gettext('Raw Samples (Hours)')}
              type="number"
              value={String(retentionDraft.raw_hours)}
              onChange={(val) =>
                setRetentionDraft((prev) => ({
                  ...prev,
                  raw_hours: Math.max(1, Number(val) || 24),
                }))
              }
            />
            <TextField
              label={gettext('5m Rollups (Days)')}
              type="number"
              value={String(retentionDraft.rollup_5m_days)}
              onChange={(val) =>
                setRetentionDraft((prev) => ({
                  ...prev,
                  rollup_5m_days: Math.max(1, Number(val) || 30),
                }))
              }
            />
            <TextField
              label={gettext('1h Rollups (Days)')}
              type="number"
              value={String(retentionDraft.rollup_1h_days)}
              onChange={(val) =>
                setRetentionDraft((prev) => ({
                  ...prev,
                  rollup_1h_days: Math.max(1, Number(val) || 365),
                }))
              }
            />
          </div>
        </div>
      </Dialog>
    </ScratchScrollArea>
  );
}

ObjectDashboardSurface.propTypes = {
  boundNodeData: PropTypes.object,
  instanceId: PropTypes.string,
  historyWindow: PropTypes.string,
  autoRefreshSec: PropTypes.number,
  onHistoryWindowChange: PropTypes.func,
};
