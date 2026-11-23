/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Grid, Panel, Stack} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {NumberField, TextField} from '../primitives/Field';
import {Checkbox, Select} from '../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../feedback/Indicators';
import {Dialog} from '../overlays/Dialog';
import {Tab} from '../navigation/TabsAndBreadcrumbs';
import FormReference from '../navigation/FormReference';
import CodeEditor from '../editors/CodeEditor';
import {FIREBIRD_TRAP_COMMANDS} from '../../Dialogs/FirebirdSessionTraps';

function formatHexChunk(base64Data) {
  try {
    const raw = atob(base64Data || '');
    const lines = [];
    for (let offset = 0; offset < raw.length; offset += 16) {
      const slice = raw.slice(offset, offset + 16);
      const hex = Array.from(slice, (c) => c.charCodeAt(0).toString(16).padStart(2, '0')).join(' ');
      const ascii = Array.from(slice, (c) => {
        const code = c.charCodeAt(0);
        return code >= 32 && code <= 126 ? c : '.';
      }).join('');
      lines.push(`${offset.toString(16).padStart(8, '0')}  ${hex.padEnd(47, ' ')}  |${ascii}|`);
    }
    return lines.join('\n') || gettext('-- Empty chunk (0 bytes) --');
  } catch {
    return gettext('-- Unable to decode chunk Base64 --');
  }
}

function decodeStrictUtf8Chunk(base64Data) {
  try {
    const raw = atob(base64Data || '');
    const bytes = Uint8Array.from(raw, (c) => c.charCodeAt(0));
    return {
      ok: true,
      text: new TextDecoder('utf-8', {fatal: true, ignoreBOM: true}).decode(bytes),
    };
  } catch {
    return {
      ok: false,
      text: gettext(
        'Chunk boundary splits a multi-byte UTF-8 sequence or contains binary bytes. Inspect in Hex/ASCII view or download the complete value.'
      ),
    };
  }
}

/**
 * FB-UI-08: Renders Firebird native RDB$PROFILER report (SR-F-001358) and
 * MON$ before/after attachment query statistics (SR-F-001359) inside
 * SqlEditorSurface's Metrics & Plan view.
 */
export function SqlProfilerAndStatsView({profiling, statistics}) {
  if (!profiling && !statistics) return null;
  const counterNames = Object.keys(
    statistics?.before?.counters || statistics?.after?.counters || {}
  );
  return (
    <Stack gap="comfortable" data-cdeadmin-qa-key="sql-surface.firebird-profiler-stats">
      {statistics && (
        <Panel variant="outlined" style={{padding: 12}}>
          <Stack gap="standard">
            <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap'}}>
              <strong>{gettext('Attachment Query Statistics (MON$)')}</strong>
              <FormReference formKey="firebird-query-statistics" />
            </Stack>
            <Banner status={statistics.complete ? 'info' : 'warning'}>
              {statistics.scope || gettext('Attachment window')}. {gettext('Host elapsed')}:{' '}
              <strong>{statistics.elapsed ?? gettext('unavailable')}</strong> ns.{' '}
              {gettext('Covers native dispatch, execution, fetch and cursor release (not isolated server CPU time).')}
            </Banner>
            <Box sx={{fontSize: '0.8rem'}}>
              {gettext('Sampled attachment ID')}: {gettext('before')}{' '}
              <code>{statistics.before?.attachment_id ?? 'unavailable'}</code> · {gettext('after')}{' '}
              <code>{statistics.after?.attachment_id ?? 'unavailable'}</code>
            </Box>
            {(statistics.unavailable_reasons || []).length > 0 && (
              <Banner status="warning">
                {gettext('Incomplete measurements')}: {statistics.unavailable_reasons.join(', ')}
                {(statistics.reset_counters || []).length > 0
                  ? ` · ${gettext('Reset counters')}: ${statistics.reset_counters.join(', ')}`
                  : ''}
              </Banner>
            )}
            {counterNames.length > 0 && (
              <table style={{width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem'}} aria-label={gettext('Query attachment counters')}>
                <thead>
                  <tr style={{textAlign: 'left', borderBottom: '1px solid var(--sr-border-default)'}}>
                    <th style={{padding: 6}}>{gettext('Counter')}</th>
                    <th style={{padding: 6}}>{gettext('Before')}</th>
                    <th style={{padding: 6}}>{gettext('After')}</th>
                    <th style={{padding: 6}}>{gettext('Delta')}</th>
                  </tr>
                </thead>
                <tbody>
                  {counterNames.map((name) => (
                    <tr key={name} style={{borderBottom: '1px solid var(--sr-border-subtle)'}}>
                      <td style={{padding: 6}}>{name}</td>
                      <td style={{padding: 6}}>{statistics.before?.counters?.[name] ?? gettext('Unavailable')}</td>
                      <td style={{padding: 6}}>{statistics.after?.counters?.[name] ?? gettext('Unavailable')}</td>
                      <td style={{padding: 6}}>
                        <strong>{statistics.deltas?.[name] ?? gettext('Unavailable / reset')}</strong>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Stack>
        </Panel>
      )}

      {profiling && (
        <Panel variant="outlined" style={{padding: 12}}>
          <Stack gap="standard">
            <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap'}}>
              <strong>{gettext('Native SQL / PSQL Profile (RDB$PROFILER)')}</strong>
              <FormReference formKey="firebird-profiler" />
            </Stack>
            <Banner status={profiling.state === 'complete' ? 'info' : 'warning'}>
              {gettext('Profile ID')}: <code>{profiling.profile_id || 'unavailable'}</code> ({profiling.state}).{' '}
              {gettext('Elapsed timings are in nanoseconds.')}
            </Banner>
            {(profiling.errors || []).map((err, idx) => (
              <ValidationMessage key={idx} status="error">
                {err.stage}: {err.error_type} {(err.native_status_codes || []).join(', ')}
              </ValidationMessage>
            ))}
            {Object.entries(profiling.sections || {}).map(([name, section]) => (
              <Box key={name}>
                <Box component="h4" sx={{m: 0, mb: 0.5, fontSize: '0.8125rem', fontWeight: 600}}>
                  {name.replace(/_/g, ' ')}
                </Box>
                {section.truncated && (
                  <Banner status="warning">
                    {gettext('Displayed first %s native records.', profiling.section_limit)}
                  </Banner>
                )}
                {!section.rows?.length ? (
                  <Box sx={{fontSize: '0.78rem', opacity: 0.75}}>
                    {gettext('No measurements recorded in this section.')}
                  </Box>
                ) : (
                  <Box sx={{maxHeight: 260, overflow: 'auto'}}>
                    <table style={{width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem'}}>
                      <thead>
                        <tr style={{textAlign: 'left', borderBottom: '1px solid var(--sr-border-default)'}}>
                          {Object.keys(section.rows[0]).map((colKey) => (
                            <th key={colKey} style={{padding: '4px 6px'}}>{colKey}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {section.rows.map((row, rIdx) => (
                          <tr key={rIdx} style={{borderBottom: '1px solid var(--sr-border-subtle)'}}>
                            {Object.entries(row).map(([k, v]) => (
                              <td key={k} style={{padding: '4px 6px'}}>
                                {v == null ? 'NULL' : String(v)}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </Box>
                )}
              </Box>
            ))}
          </Stack>
        </Panel>
      )}
    </Stack>
  );
}

SqlProfilerAndStatsView.propTypes = {
  profiling: PropTypes.object,
  statistics: PropTypes.object,
};

/**
 * FB-UI-08: Explicit consent dialog before starting RDB$PROFILER on the attachment.
 */
export function SqlProfilerConsentDialog({open, busy = false, onConfirm, onClose}) {
  const [consentChecked, setConsentChecked] = useState(false);
  useEffect(() => {
    if (open) setConsentChecked(false);
  }, [open]);
  return (
    <Dialog
      open={open}
      title={gettext('Run Profiled Single Statement (RDB$PROFILER)')}
      formKey="firebird-profiler"
      size="medium"
      busy={busy}
      onClose={busy ? undefined : onClose}
      actions={
        <>
          <Button intent="neutral" disabled={busy} onClick={onClose}>
            {gettext('Cancel')}
          </Button>
          <Button
            intent="primary"
            disabled={busy || !consentChecked}
            loading={busy}
            onClick={onConfirm}
          >
            {gettext('Start Profiler & Run Statement')}
          </Button>
        </>
      }
    >
      <Stack gap="standard">
        <Banner status="warning">
          {gettext(
            'Starting RDB$PROFILER replaces any active profile session on this attachment and flushes persistent diagnostic rows into native PLG$PROF tables under native database permissions.'
          )}
        </Banner>
        <Checkbox
          label={gettext('I consent to replacing any active attachment profile and flushing native PLG$PROF diagnostic tables')}
          checked={consentChecked}
          disabled={busy}
          onChange={(v) => setConsentChecked(Boolean(v))}
        />
      </Stack>
    </Dialog>
  );
}

SqlProfilerConsentDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  busy: PropTypes.bool,
  onConfirm: PropTypes.func.isRequired,
  onClose: PropTypes.func.isRequired,
};

/**
 * FB-UI-09: Persistent server-side searchable SQL history panel (SR-F-001357)
 * mounted inside SqlEditorSurface's Right Drawer History panel.
 */
export function SqlPersistentHistoryPanel({
  post,
  databaseTargetId,
  clientSqlDialect = 3,
  supportsDialectScope = false,
  onLoadSql,
  disabled = false,
}) {
  const [data, setData] = useState(null);
  const [policy, setPolicy] = useState(null);
  const [search, setSearch] = useState('');
  const [selectedIdx, setSelectedIdx] = useState(-1);
  const [clearConfirmed, setClearConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const tokenRef = useRef(0);

  const callHistory = useCallback(
    async (action = 'query_history_read') => {
      if (!post) return;
      const reqToken = ++tokenRef.current;
      setBusy(true);
      setError('');
      const scope = {
        database_target_id: databaseTargetId,
        ...(supportsDialectScope ? {client_sql_dialect: clientSqlDialect} : {}),
      };
      try {
        if (action !== 'query_history_read') {
          await post({
            action,
            request: {
              ...scope,
              ...(action === 'query_history_configure' ? {policy} : {confirmed: clearConfirmed}),
            },
          });
        }
        const resp = await post({
          action: 'query_history_read',
          request: {...scope, search},
        });
        if (tokenRef.current !== reqToken) return;
        setData(resp);
        setPolicy(resp?.policy || null);
        setSelectedIdx(-1);
        setClearConfirmed(false);
      } catch (err) {
        if (tokenRef.current === reqToken) {
          setError(err?.response?.data?.errormsg || err?.message || String(err));
        }
      } finally {
        if (tokenRef.current === reqToken) setBusy(false);
      }
    },
    [clearConfirmed, clientSqlDialect, databaseTargetId, policy, post, search, supportsDialectScope]
  );

  useEffect(() => {
    callHistory('query_history_read');
  }, [databaseTargetId, clientSqlDialect]);

  const entries = data?.entries || [];
  const loadAt = (idx) => {
    const entry = entries[idx];
    if (typeof entry?.source === 'string') {
      setSelectedIdx(idx);
      onLoadSql(entry.source);
    }
  };
  const prevIdx = entries.findIndex((item, idx) => idx > selectedIdx && typeof item.source === 'string');
  let nextIdx = -1;
  for (let i = selectedIdx - 1; i >= 0; i -= 1) {
    if (typeof entries[i]?.source === 'string') {
      nextIdx = i;
      break;
    }
  }

  return (
    <Stack gap="standard" data-cdeadmin-qa-key="sql-surface.persistent-history">
      <Stack direction="row" gap="tight" style={{alignItems: 'center', justifyContent: 'space-between'}}>
        <strong style={{fontSize: '0.82rem'}}>{gettext('Persistent Scoped SQL History')}</strong>
        <FormReference formKey="firebird-query-history" />
      </Stack>
      <Banner status="info">
        {gettext('Opt-in source capture omits credential-bearing statements and never records parameters or result rows. Loading history never executes automatically.')}
      </Banner>
      {error && <ValidationMessage status="error">{error}</ValidationMessage>}

      {policy && (
        <Panel variant="outlined" style={{padding: 8}}>
          <Stack gap="tight">
            <Checkbox
              label={gettext('Capture SQL source in persistent history')}
              checked={Boolean(policy.capture_source)}
              disabled={disabled || busy}
              onChange={(v) => setPolicy({...policy, capture_source: Boolean(v)})}
            />
            <Grid columns="1fr 1fr">
              <NumberField
                label={gettext('Retention days')}
                size="small"
                value={policy.retention_days ?? 30}
                disabled={disabled || busy}
                onChange={(e) =>
                  setPolicy({
                    ...policy,
                    retention_days: Number(e?.target !== undefined ? e.target.value : e) || 30,
                  })
                }
              />
              <NumberField
                label={gettext('Max records')}
                size="small"
                value={policy.max_records ?? 200}
                disabled={disabled || busy}
                onChange={(e) =>
                  setPolicy({
                    ...policy,
                    max_records: Number(e?.target !== undefined ? e.target.value : e) || 200,
                  })
                }
              />
            </Grid>
            <Button size="small" intent="neutral" disabled={disabled || busy} onClick={() => callHistory('query_history_configure')}>
              {gettext('Save History Policy')}
            </Button>
          </Stack>
        </Panel>
      )}

      <Stack direction="row" gap="tight" style={{flexWrap: 'wrap'}}>
        <Box style={{flex: 1, minWidth: 140}}>
          <TextField
            label={gettext('Search retained SQL')}
            size="small"
            value={search}
            disabled={busy}
            onChange={(e) => setSearch(e.target.value)}
          />
        </Box>
        <Button size="small" intent="neutral" disabled={busy} onClick={() => callHistory('query_history_read')}>
          {gettext('Search')}
        </Button>
        <Button size="small" intent="neutral" disabled={busy || prevIdx < 0} onClick={() => loadAt(prevIdx)}>
          {gettext('Older')}
        </Button>
        <Button size="small" intent="neutral" disabled={busy || nextIdx < 0} onClick={() => loadAt(nextIdx)}>
          {gettext('Newer')}
        </Button>
      </Stack>

      {entries.length === 0 ? (
        <Box sx={{fontSize: '0.75rem', opacity: 0.75}}>
          {gettext('No retained persistent history entries in this scope.')}
        </Box>
      ) : (
        <Stack gap="tight">
          {entries.slice(0, 40).map((entry, idx) => (
            <Panel key={entry.entry_id || idx} variant="outlined" style={{padding: 8}}>
              <Stack gap="tight">
                <Stack direction="row" gap="tight" style={{justifyContent: 'space-between', fontSize: '0.7rem', opacity: 0.78}}>
                  <span>{entry.kind}: {entry.request_state}</span>
                  <span>{entry.created_at ? new Date(entry.created_at * 1000).toISOString().slice(11, 19) : ''}</span>
                </Stack>
                <pre style={{margin: 0, fontSize: '0.74rem', whiteSpace: 'pre-wrap', maxHeight: 84, overflow: 'auto'}}>
                  {entry.source ?? entry.source_omitted_reason ?? gettext('(source omitted)')}
                </pre>
                {typeof entry.source === 'string' && (
                  <Button size="small" disabled={disabled || busy} onClick={() => loadAt(idx)}>
                    {gettext('Load into Editor')}
                  </Button>
                )}
              </Stack>
            </Panel>
          ))}
        </Stack>
      )}

      <Panel variant="outlined" style={{padding: 8}}>
        <Stack gap="tight">
          <Checkbox
            label={gettext('Confirm clearing retained history for this scope')}
            checked={clearConfirmed}
            disabled={disabled || busy}
            onChange={(v) => setClearConfirmed(Boolean(v))}
          />
          <Button
            size="small"
            intent="destructive"
            disabled={disabled || busy || !clearConfirmed}
            onClick={() => callHistory('query_history_clear')}
          >
            {gettext('Clear Persistent History')}
          </Button>
        </Stack>
      </Panel>
    </Stack>
  );
}

SqlPersistentHistoryPanel.propTypes = {
  post: PropTypes.func,
  databaseTargetId: PropTypes.string,
  clientSqlDialect: PropTypes.number,
  supportsDialectScope: PropTypes.bool,
  onLoadSql: PropTypes.func.isRequired,
  disabled: PropTypes.bool,
};

/**
 * FB-UI-10: Session Tools Dialog for External Connection Pool (EDS) Admin,
 * Session DECFLOAT Traps, and >1 MiB Forward-Only BLOB / Array Stream Reader.
 */
export function SqlFirebirdSessionToolsDialog({
  open,
  onClose,
  post,
  databaseTargetId,
  sessionId,
  ensureSession,
  sqlSource,
  clientSqlDialect = 3,
  onExecuteTrapSql,
  initialTab = 'eds_pool',
}) {
  const [tab, setTab] = useState(initialTab);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  // EDS Pool State
  const [edsAction, setEdsAction] = useState('set_size');
  const [edsValue, setEdsValue] = useState('32');
  const [edsUnit, setEdsUnit] = useState('SECOND');
  const [edsInventory, setEdsInventory] = useState(null);
  const [edsRecord, setEdsRecord] = useState(null);
  const [edsReceipts, setEdsReceipts] = useState(null);
  const [edsConfirmPid, setEdsConfirmPid] = useState('');
  const [edsConfirmed, setEdsConfirmed] = useState(false);

  // DECFLOAT Trap State
  const [trapDisableConfirmed, setTrapDisableConfirmed] = useState(false);

  // Forward-only Stream Reader State (>1 MiB BLOBs & Multidimensional Arrays)
  const [streamPage, setStreamPage] = useState(null);
  const [blobChunk, setBlobChunk] = useState(null);
  const [chunkViewMode, setChunkViewMode] = useState('hex'); // 'hex' | 'utf8'
  const [arraySlice, setArraySlice] = useState(null);
  const streamOwnerRef = useRef(`stream-${Date.now()}`);
  const activeStreamSessionRef = useRef(null);

  useEffect(() => {
    if (open) setTab(initialTab);
  }, [initialTab, open]);

  const runEds = async (operation, archived = false, targetRecord = edsRecord) => {
    setBusy(true);
    setError('');
    try {
      const sid = archived ? null : sessionId || (await ensureSession?.());
      const req =
        operation === 'inventory'
          ? {operation}
          : operation === 'list'
            ? {operation, offset: 0, limit: 25}
            : operation === 'review'
              ? {
                operation,
                draft: {
                  action: edsAction,
                  ...(edsAction.startsWith('set_') ? {value: Number(edsValue || 0)} : {}),
                  ...(edsAction === 'set_lifetime' ? {unit: edsUnit} : {}),
                },
              }
              : {
                operation,
                review_id: targetRecord?.review_id,
                ...(operation === 'apply'
                  ? {
                    review_digest: targetRecord?.review_digest,
                    confirmation: edsConfirmPid.trim(),
                    confirmed: edsConfirmed,
                  }
                  : operation === 'discard'
                    ? {review_digest: targetRecord?.review_digest}
                    : {}),
              };
      const res = await post({
        action: archived ? 'firebird_eds_pool_receipts' : 'firebird_eds_pool',
        database_target_id: databaseTargetId,
        ...(!archived && sid ? {session_id: sid} : {}),
        request: req,
      });
      if (operation === 'inventory') setEdsInventory(res);
      else if (operation === 'list') setEdsReceipts(res);
      else {
        setEdsRecord(res);
        setEdsConfirmPid('');
        setEdsConfirmed(false);
      }
    } catch (err) {
      setError(err?.response?.data?.errormsg || err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const runStream = async (streamAction, extra = {}) => {
    setBusy(true);
    setError('');
    try {
      const sid = activeStreamSessionRef.current || sessionId || (await ensureSession?.());
      activeStreamSessionRef.current = sid;
      const res = await post({
        action: 'query_stream',
        session_id: sid,
        database_target_id: databaseTargetId,
        request: {
          owner_id: streamOwnerRef.current,
          stream_action: streamAction,
          ...extra,
        },
      });
      if (streamAction === 'open' || streamAction === 'next') {
        setStreamPage(res);
        setBlobChunk(null);
        setArraySlice(null);
      } else if (streamAction === 'close') {
        setStreamPage(null);
        setBlobChunk(null);
        setArraySlice(null);
      } else if (streamAction === 'blob_chunk') {
        setBlobChunk(res);
      } else if (streamAction === 'array_slice') {
        setArraySlice(res);
      }
    } catch (err) {
      setError(err?.response?.data?.errormsg || err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      title={gettext('Firebird Attachment Pool, Session Traps & Stream Reader')}
      formKey="firebird-eds-pool"
      size="large"
      busy={busy}
      onClose={busy ? undefined : onClose}
      actions={
        <Button intent="neutral" disabled={busy} onClick={onClose}>
          {gettext('Close')}
        </Button>
      }
    >
      <Stack gap="comfortable" data-cdeadmin-qa-key="sql-surface.firebird-session-tools">
        <Stack direction="row" gap="tight" style={{flexWrap: 'wrap'}}>
          <Tab
            id="fb-sess-eds"
            label={gettext('External Connection Pool (EDS)')}
            selected={tab === 'eds_pool'}
            onSelect={() => setTab('eds_pool')}
          />
          <Tab
            id="fb-sess-traps"
            label={gettext('Session DECFLOAT Traps')}
            selected={tab === 'traps'}
            onSelect={() => setTab('traps')}
          />
          <Tab
            id="fb-sess-stream"
            label={gettext('Chunked BLOB & Array Stream Reader (>1 MiB)')}
            selected={tab === 'stream'}
            onSelect={() => setTab('stream')}
          />
        </Stack>

        {error && <ValidationMessage status="error">{error}</ValidationMessage>}

        {tab === 'eds_pool' && (
          <Stack gap="standard">
            <Banner status="warning">
              {gettext(
                'ALTER EXTERNAL CONNECTIONS POOL administers the native engine process pool (requires MODIFY_EXT_CONN_POOL), takes effect immediately outside transaction rollback, and does not modify firebird.conf.'
              )}
            </Banner>
            <Grid columns="repeat(auto-fit, minmax(180px, 1fr))">
              <Select
                label={gettext('EDS pool command')}
                size="small"
                options={[
                  {value: 'set_size', label: gettext('Set pool size')},
                  {value: 'set_lifetime', label: gettext('Set idle lifetime')},
                  {value: 'clear_oldest', label: gettext('CLEAR OLDEST (expired idle)')},
                  {value: 'clear_all', label: gettext('CLEAR ALL bindings')},
                ]}
                value={edsAction}
                disabled={busy}
                onChange={(val) => setEdsAction(val)}
              />
              {edsAction.startsWith('set_') && (
                <TextField
                  label={gettext('Quantity')}
                  size="small"
                  value={edsValue}
                  disabled={busy}
                  onChange={(e) => setEdsValue(e.target.value)}
                />
              )}
              {edsAction === 'set_lifetime' && (
                <Select
                  label={gettext('Lifetime unit')}
                  size="small"
                  options={[
                    {value: 'SECOND', label: 'SECOND'},
                    {value: 'MINUTE', label: 'MINUTE'},
                    {value: 'HOUR', label: 'HOUR'},
                  ]}
                  value={edsUnit}
                  disabled={busy}
                  onChange={(val) => setEdsUnit(val)}
                />
              )}
            </Grid>
            <Stack direction="row" gap="tight" style={{flexWrap: 'wrap'}}>
              <Button size="small" intent="neutral" disabled={busy} onClick={() => runEds('inventory')}>
                {gettext('Inspect Native EDS Pool')}
              </Button>
              <Button size="small" intent="primary" disabled={busy} onClick={() => runEds('review')}>
                {gettext('Review EDS Pool Command')}
              </Button>
              <Button size="small" intent="neutral" disabled={busy} onClick={() => runEds('list', true)}>
                {gettext('Load Retained EDS Receipts')}
              </Button>
            </Stack>

            {edsInventory && (
              <CodeEditor
                label={gettext('Observed native process EDS pool state')}
                readonly
                language="json"
                value={JSON.stringify(edsInventory, null, 2)}
              />
            )}

            {edsRecord && (
              <Panel variant="outlined" style={{padding: 10}}>
                <Stack gap="standard">
                  <CodeEditor
                    label={gettext('Reviewed EDS SQL statement')}
                    readonly
                    language="sql"
                    value={edsRecord.source || JSON.stringify(edsRecord, null, 2)}
                  />
                  {edsRecord.state === 'reviewed' && !edsRecord.archived_read_only && (
                    <Stack gap="tight">
                      <TextField
                        label={gettext(
                          'Confirm native server process ID (%s)',
                          edsRecord.native_before?.server_process_id ?? ''
                        )}
                        size="small"
                        value={edsConfirmPid}
                        disabled={busy}
                        onChange={(e) => setEdsConfirmPid(e.target.value)}
                      />
                      <Checkbox
                        label={gettext('I reviewed shared process scope and immediate non-transactional effect')}
                        checked={edsConfirmed}
                        disabled={busy}
                        onChange={(v) => setEdsConfirmed(Boolean(v))}
                      />
                      <Stack direction="row" gap="tight">
                        <Button
                          size="small"
                          intent="primary"
                          disabled={
                            busy ||
                            !edsConfirmed ||
                            String(edsConfirmPid.trim()) !== String(edsRecord.native_before?.server_process_id ?? '')
                          }
                          onClick={() => runEds('apply')}
                        >
                          {gettext('Apply Reviewed EDS Command')}
                        </Button>
                        <Button size="small" intent="neutral" disabled={busy} onClick={() => runEds('discard')}>
                          {gettext('Discard')}
                        </Button>
                      </Stack>
                    </Stack>
                  )}
                </Stack>
              </Panel>
            )}

            {edsReceipts?.receipts && (
              <CodeEditor
                label={gettext('Retained EDS pool receipts')}
                readonly
                language="json"
                value={JSON.stringify(edsReceipts.receipts, null, 2)}
              />
            )}
          </Stack>
        )}

        {tab === 'traps' && (
          <Stack gap="standard">
            <Banner status="warning">
              {gettext(
                'DECFLOAT trap changes take effect immediately on this SQL attachment and survive COMMIT/ROLLBACK until session reset or reconnect.'
              )}
            </Banner>
            <Checkbox
              label={gettext('Confirm disabling all DECFLOAT arithmetic traps in this session')}
              checked={trapDisableConfirmed}
              disabled={busy}
              onChange={(v) => setTrapDisableConfirmed(Boolean(v))}
            />
            <Stack direction="row" gap="standard" style={{flexWrap: 'wrap'}}>
              <Button
                size="small"
                intent="neutral"
                disabled={busy}
                onClick={() => {
                  onExecuteTrapSql?.(FIREBIRD_TRAP_COMMANDS.inspect);
                  onClose();
                }}
              >
                {gettext('Inspect Current DECFLOAT Traps')}
              </Button>
              <Button
                size="small"
                intent="destructive"
                disabled={busy || !trapDisableConfirmed}
                onClick={() => {
                  setTrapDisableConfirmed(false);
                  onExecuteTrapSql?.(FIREBIRD_TRAP_COMMANDS.disable);
                  onClose();
                }}
              >
                {gettext('Disable All DECFLOAT Traps')}
              </Button>
            </Stack>
          </Stack>
        )}

        {tab === 'stream' && (
          <Stack gap="standard">
            <Banner status="info">
              {gettext(
                'Forward-only stream reader inspects >1 MiB BLOB chunks in Hex/ASCII or strict UTF-8 and slices multidimensional arrays without materializing the full result set in memory.'
              )}
            </Banner>
            <Stack direction="row" gap="tight" style={{flexWrap: 'wrap'}}>
              <Button
                size="small"
                intent="primary"
                disabled={busy || !String(sqlSource || '').trim()}
                onClick={() =>
                  runStream('open', {
                    source: sqlSource,
                    parameters: [],
                    client_sql_dialect: clientSqlDialect,
                    page_rows: 50,
                  })
                }
              >
                {gettext('Open Stream for Current SQL')}
              </Button>
              {streamPage?.has_more && (
                <Button
                  size="small"
                  intent="neutral"
                  disabled={busy}
                  onClick={() =>
                    runStream('next', {
                      stream_reference: streamPage.stream_reference,
                      sequence: (streamPage.sequence || 0) + 1,
                    })
                  }
                >
                  {gettext('Next Stream Page')}
                </Button>
              )}
              {streamPage && (
                <Button size="small" intent="neutral" disabled={busy} onClick={() => runStream('close')}>
                  {gettext('Close Stream')}
                </Button>
              )}
            </Stack>

            {streamPage && (
              <Panel variant="outlined" style={{padding: 10}}>
                <Stack gap="standard">
                  <Stack direction="row" gap="standard" style={{alignItems: 'center', flexWrap: 'wrap'}}>
                    <Badge label={`Page #${(streamPage.sequence || 0) + 1}`} status="info" />
                    <span>{gettext('Rows in page')}: {(streamPage.rows || []).length}</span>
                  </Stack>
                  <CodeEditor
                    label={gettext('Streamed page handles & scalar values')}
                    readonly
                    language="json"
                    value={JSON.stringify(streamPage.rows || [], null, 2)}
                  />
                  {(streamPage.blob_handles || []).map((bh) => (
                    <Stack key={bh.blob_reference} direction="row" gap="tight" style={{alignItems: 'center'}}>
                      <code>{bh.column || bh.blob_reference}</code>
                      <Button
                        size="small"
                        onClick={() =>
                          runStream('blob_chunk', {
                            stream_reference: streamPage.stream_reference,
                            blob_reference: bh.blob_reference,
                            offset: 0,
                          })
                        }
                      >
                        {gettext('Read First Chunk')}
                      </Button>
                    </Stack>
                  ))}
                </Stack>
              </Panel>
            )}

            {blobChunk && (
              <Panel variant="outlined" style={{padding: 10}}>
                <Stack gap="tight">
                  <Stack direction="row" gap="tight" style={{alignItems: 'center', justifyContent: 'space-between'}}>
                    <strong>
                      {gettext('BLOB Chunk')} (offset {blobChunk.offset ?? 0}, {blobChunk.byte_length ?? 0} B)
                    </strong>
                    <Stack direction="row" gap="tight">
                      <Button size="small" intent={chunkViewMode === 'hex' ? 'primary' : 'neutral'} onClick={() => setChunkViewMode('hex')}>
                        {gettext('Hex / ASCII')}
                      </Button>
                      <Button size="small" intent={chunkViewMode === 'utf8' ? 'primary' : 'neutral'} onClick={() => setChunkViewMode('utf8')}>
                        {gettext('Strict UTF-8')}
                      </Button>
                    </Stack>
                  </Stack>
                  <CodeEditor
                    label={chunkViewMode === 'hex' ? gettext('Hexadecimal / ASCII chunk') : gettext('Strict UTF-8 chunk')}
                    readonly
                    language="text"
                    value={
                      chunkViewMode === 'hex'
                        ? formatHexChunk(blobChunk.data)
                        : decodeStrictUtf8Chunk(blobChunk.data).text
                    }
                  />
                </Stack>
              </Panel>
            )}

            {arraySlice && (
              <CodeEditor
                label={gettext('Array slice')}
                readonly
                language="json"
                value={JSON.stringify(arraySlice, null, 2)}
              />
            )}
          </Stack>
        )}
      </Stack>
    </Dialog>
  );
}

SqlFirebirdSessionToolsDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  post: PropTypes.func,
  databaseTargetId: PropTypes.string,
  sessionId: PropTypes.string,
  ensureSession: PropTypes.func,
  sqlSource: PropTypes.string,
  clientSqlDialect: PropTypes.number,
  onExecuteTrapSql: PropTypes.func,
  initialTab: PropTypes.string,
};
