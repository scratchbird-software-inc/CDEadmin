/////////////////////////////////////////////////////////////
//
// ScratchRobin — Database Engines On/Off Registry Editor
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import usePreferences from '../../../../../preferences/static/js/store';
import {Button} from '../../primitives/Button';
import {Select, Switch} from '../../primitives/Choice';
import {SearchField} from '../../primitives/AdvancedControls';
import {Banner} from '../../feedback/Indicators';
import {EngineIcon} from '../../icons';

function resolveCsrfHeaders() {
  if (typeof window === 'undefined') return {};
  const headerName =
    window.pgAdmin?.csrf_token_header ||
    document?.querySelector?.('meta[name="csrf-header"]')?.getAttribute('content') ||
    'X-pgA-CSRFToken';
  const token =
    window.pgAdmin?.csrf_token ||
    document?.querySelector?.('meta[name="csrf-token"]')?.getAttribute('content') ||
    '';
  return token ? {[headerName]: token} : {};
}

export const FALLBACK_DATABASE_ENGINES = Object.freeze([
  {id: 'postgresql', label: 'PostgreSQL', category: 'Relational SQL', interfaces: 'libpq / TCP 5432'},
  {id: 'firebird', label: 'Firebird', category: 'Relational SQL', interfaces: 'Wire / Embedded 3050'},
  {id: 'mariadb', label: 'MariaDB', category: 'Relational SQL', interfaces: 'MySQL Protocol 3306'},
  {id: 'mysql', label: 'MySQL', category: 'Relational SQL', interfaces: 'MySQL Protocol 3306'},
  {id: 'sqlite', label: 'SQLite', category: 'Embedded & Analytical', interfaces: 'Local File / VFS'},
  {id: 'duckdb', label: 'DuckDB', category: 'Embedded & Analytical', interfaces: 'Embedded OLAP'},
  {id: 'scratchbird', label: 'ScratchBird', category: 'Convergent (CDE)', interfaces: 'SBsql / Native'},
  {id: 'cockroachdb', label: 'CockroachDB', category: 'Distributed SQL', interfaces: 'PG Wire 26257'},
  {id: 'yugabytedb', label: 'YugabyteDB', category: 'Distributed SQL', interfaces: 'YSQL / YCQL 5433'},
  {id: 'tidb', label: 'TiDB', category: 'Distributed SQL', interfaces: 'MySQL Wire 4000'},
  {id: 'vitess', label: 'Vitess', category: 'Distributed SQL', interfaces: 'VTGate 15306'},
  {id: 'dolt', label: 'Dolt', category: 'Versioned SQL', interfaces: 'MySQL Wire 3306'},
  {id: 'clickhouse', label: 'ClickHouse', category: 'Columnar OLAP', interfaces: 'Native 9000 / HTTP 8123'},
  {id: 'mongodb', label: 'MongoDB', category: 'Document & Multi-Model', interfaces: 'Wire 27017'},
  {id: 'cassandra', label: 'Apache Cassandra', category: 'Wide-Column & KV', interfaces: 'CQL 9042'},
  {id: 'redis', label: 'Redis', category: 'Wide-Column & KV', interfaces: 'RESP 6379'},
  {id: 'tikv', label: 'TiKV', category: 'Wide-Column & KV', interfaces: 'gRPC PD 2379'},
  {id: 'foundationdb', label: 'FoundationDB', category: 'Wide-Column & KV', interfaces: 'Cluster File 4500'},
  {id: 'apache_ignite', label: 'Apache Ignite', category: 'Distributed Cache & SQL', interfaces: 'Thin Client 10800'},
  {id: 'neo4j', label: 'Neo4j', category: 'Graph & Vector', interfaces: 'Bolt 7687'},
  {id: 'milvus', label: 'Milvus', category: 'Graph & Vector', interfaces: 'gRPC 19530'},
  {id: 'opensearch', label: 'OpenSearch', category: 'Search & Time-Series', interfaces: 'REST HTTPS 9200'},
  {id: 'influxdb', label: 'InfluxDB', category: 'Search & Time-Series', interfaces: 'HTTP / Flight 8086'},
  {id: 'immudb', label: 'immudb', category: 'Immutable Ledger', interfaces: 'gRPC 3322'},
  {id: 'xtdb', label: 'XTDB', category: 'Bitemporal SQL', interfaces: 'PG Wire / HTTP 5432'},
]);

export const CORE_SQL_ENGINE_IDS = Object.freeze([
  'postgresql',
  'firebird',
  'mariadb',
  'mysql',
  'sqlite',
  'duckdb',
  'scratchbird',
]);

const LOCAL_ENGINES_STORAGE_KEY = 'scratchrobin.shell.enabled_engines.v1';

function readLocalEnabledEngines() {
  try {
    const raw = window?.localStorage?.getItem(LOCAL_ENGINES_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function writeLocalEnabledEngines(ids) {
  try {
    window?.localStorage?.setItem(LOCAL_ENGINES_STORAGE_KEY, JSON.stringify(ids));
  } catch {
    // Ignore storage quota issues.
  }
}

export function DatabaseEnginesEditor({
  globalSettings = {},
  fetchImpl = null,
  onChangeGlobal,
}) {
  const runFetch = fetchImpl || (typeof fetch === 'function' ? fetch : null);

  const [engines, setEngines] = useState(() =>
    FALLBACK_DATABASE_ENGINES.map((e) => ({
      ...e,
      enabled: CORE_SQL_ENGINE_IDS.includes(e.id),
      local_detected: false,
    }))
  );
  const [enabledIds, setEnabledIds] = useState(() => {
    if (Array.isArray(globalSettings.enabled_engines)) {
      return globalSettings.enabled_engines;
    }
    return readLocalEnabledEngines() || [...CORE_SQL_ENGINE_IDS];
  });
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [feedback, setFeedback] = useState('');

  useEffect(() => {
    if (!runFetch) return undefined;
    let active = true;
    Promise.resolve(runFetch('/cdeadmin/api/shell/engines', {credentials: 'same-origin'}))
      .then((res) => (res?.ok ? res.json() : null))
      .then((data) => {
        if (!active || !Array.isArray(data?.engines)) return;
        setEngines(
          data.engines.map((srv) => {
            const fb = FALLBACK_DATABASE_ENGINES.find((f) => f.id === srv.id);
            return {
              id: srv.id,
              label: srv.label || fb?.label || srv.id,
              category: srv.category || fb?.category || 'Database Engine',
              interfaces:
                Array.isArray(srv.interfaces) && srv.interfaces.length > 0
                  ? srv.interfaces.join(', ')
                  : fb?.interfaces || '',
              local_detected: Boolean(srv.local_available ?? srv.local_detected),
              enabled: Boolean(srv.enabled),
            };
          })
        );
        if (Array.isArray(data.enabled_engine_ids)) {
          setEnabledIds(data.enabled_engine_ids);
          writeLocalEnabledEngines(data.enabled_engine_ids);
        }
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [runFetch]);

  const categories = useMemo(() => {
    const uniq = [...new Set(engines.map((e) => e.category).filter(Boolean))];
    return [{value: 'all', label: gettext('All Engine Families (%s)', engines.length)}, ...uniq.map((c) => ({value: c, label: c}))];
  }, [engines]);

  const commitEnabledEngines = useCallback(
    async (nextIds) => {
      const clean = [...new Set(nextIds)];
      setEnabledIds(clean);
      writeLocalEnabledEngines(clean);
      onChangeGlobal?.({enabled_engines: clean});
      setFeedback(
        gettext(
          'Active database engines updated (%s enabled). Data Navigator Connectors refreshed.',
          clean.length
        )
      );

      if (runFetch) {
        try {
          const res = await runFetch('/cdeadmin/api/shell/engines', {
            method: 'PUT',
            credentials: 'same-origin',
            headers: {'Content-Type': 'application/json', ...resolveCsrfHeaders()},
            body: JSON.stringify({enabled_engines: clean}),
          });
          if (res?.ok) {
            const data = await res.json();
            if (Array.isArray(data?.enabled_engine_ids)) {
              setEnabledIds(data.enabled_engine_ids);
              writeLocalEnabledEngines(data.enabled_engine_ids);
            }
          }
          // Refresh preference cache & Data Navigator Connectors branch live
          await usePreferences.getState?.()?.cache?.();
          if (typeof window !== 'undefined') {
            window.dispatchEvent(
              new CustomEvent('scratchrobin:connectors-changed', {
                detail: {enabled_engines: clean},
              })
            );
          }
        } catch {
          // Offline / test harness safe.
        }
      }
    },
    [onChangeGlobal, runFetch]
  );

  const filteredEngines = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return engines.filter((eng) => {
      if (categoryFilter !== 'all' && eng.category !== categoryFilter) return false;
      if (!q) return true;
      return `${eng.id} ${eng.label} ${eng.category} ${eng.interfaces}`.toLowerCase().includes(q);
    });
  }, [categoryFilter, engines, searchQuery]);

  return (
    <div
      data-cdeadmin-qa-key="settings-engines-editor"
      style={{display: 'flex', flexDirection: 'column', gap: 12}}
    >
      <div
        style={{
          border: '1px solid var(--sr-border-default)',
          borderRadius: 6,
          background: 'color-mix(in srgb, var(--sr-surface-subtle) 55%, var(--sr-surface-card))',
          padding: '10px 14px 12px',
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
        }}
      >
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap'}}>
          <div>
            <div style={{fontWeight: 600, fontSize: '0.84rem', color: 'var(--sr-text-primary)'}}>
              {gettext('Database Engines & Connectors On/Off (%s of %s Active)', enabledIds.length, engines.length)}
            </div>
            <div style={{fontSize: '0.75rem', color: 'var(--sr-text-secondary)'}}>
              {gettext(
                'Enabled engines appear under Data Navigator › Connectors and Server Registration.'
              )}
            </div>
          </div>
          <div style={{display: 'flex', gap: 6, flexWrap: 'wrap'}}>
            <Button
              intent="neutral"
              data-cdeadmin-qa-key="engines-enable-core"
              onClick={() => void commitEnabledEngines([...CORE_SQL_ENGINE_IDS])}
            >
              {gettext('Core SQL Only')}
            </Button>
            <Button
              intent="neutral"
              data-cdeadmin-qa-key="engines-enable-all"
              onClick={() => void commitEnabledEngines(engines.map((e) => e.id))}
            >
              {gettext('Enable All')}
            </Button>
            <Button
              intent="neutral"
              data-cdeadmin-qa-key="engines-disable-all"
              onClick={() => void commitEnabledEngines([])}
            >
              {gettext('Disable All')}
            </Button>
          </div>
        </div>

        <div style={{display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 10, alignItems: 'end'}}>
          <SearchField
            aria-label={gettext('Filter engines')}
            placeholder={gettext('Filter engines (PostgreSQL, Firebird, DuckDB, ScratchBird…)')}
            value={searchQuery}
            onChange={setSearchQuery}
          />
          <Select
            aria-label={gettext('Engine Family')}
            value={categoryFilter}
            options={categories}
            onChange={(val) => setCategoryFilter(val || 'all')}
          />
        </div>
      </div>

      {feedback && <Banner status="info">{feedback}</Banner>}

      <div
        style={{
          border: '1px solid var(--sr-border-default)',
          borderRadius: 6,
          background: 'var(--sr-surface-card)',
          overflow: 'hidden',
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
        }}
      >
        {filteredEngines.map((eng) => {
          const isEnabled = enabledIds.includes(eng.id);
          return (
            <div
              key={eng.id}
              data-cdeadmin-qa-key={`engine-card-${eng.id}`}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 8,
                padding: '6px 12px',
                borderBottom: '1px solid var(--sr-border-subtle)',
                borderRight: '1px solid var(--sr-border-subtle)',
                background: isEnabled
                  ? 'var(--sr-surface-card)'
                  : 'color-mix(in srgb, var(--sr-surface-subtle) 60%, var(--sr-surface-card))',
                opacity: isEnabled ? 1 : 0.78,
              }}
            >
              <div style={{display: 'flex', alignItems: 'center', gap: 8, minWidth: 0}}>
                <EngineIcon engine={eng.id} decorative size="18px" />
                <div style={{minWidth: 0}}>
                  <div style={{display: 'flex', alignItems: 'center', gap: 6}}>
                    <span style={{fontWeight: 600, fontSize: '0.8rem'}}>{eng.label}</span>
                    {eng.local_detected && (
                      <span
                        style={{
                          fontSize: '0.62rem',
                          fontWeight: 700,
                          padding: '1px 5px',
                          borderRadius: 999,
                          background: 'var(--sr-accent-subtle)',
                          color: 'var(--sr-accent)',
                        }}
                      >
                        {gettext('Local')}
                      </span>
                    )}
                  </div>
                  <div
                    style={{
                      fontSize: '0.68rem',
                      color: 'var(--sr-text-secondary)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {eng.category} · {eng.interfaces}
                  </div>
                </div>
              </div>

              <Switch
                label=""
                aria-label={`Enable ${eng.label}`}
                checked={isEnabled}
                data-cdeadmin-qa-key={`engine-switch-${eng.id}`}
                onChange={(checked) => {
                  const next = checked
                    ? [...enabledIds, eng.id]
                    : enabledIds.filter((id) => id !== eng.id);
                  void commitEnabledEngines(next);
                }}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

DatabaseEnginesEditor.propTypes = {
  globalSettings: PropTypes.object,
  fetchImpl: PropTypes.func,
  onChangeGlobal: PropTypes.func,
};
