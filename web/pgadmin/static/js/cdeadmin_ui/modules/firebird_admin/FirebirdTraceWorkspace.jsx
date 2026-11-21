/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Grid, Panel, ScrollArea, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {NumberField, TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import {Tab} from '../../navigation/TabsAndBreadcrumbs';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
import {
  DatabaseTargetPickerBar,
  extractApiError,
  ReviewConfirmationCard,
  useFirebirdTargetScope,
} from './firebirdAdminHelpers';

function buildInitialFieldDefaults(fields = []) {
  const out = {};
  fields.forEach((f) => {
    out[f.field_id] = f.default !== undefined ? f.default : f.control === 'checkbox' ? false : '';
  });
  return out;
}

export default function FirebirdTraceWorkspace({
  endpointUrl,
  databaseTargetId = null,
  initialTraceScope = 'database',
  customPost = null,
}) {
  const {
    targets,
    selectedTargetId,
    setSelectedTargetId,
    targetsError,
    reloadTargets,
    post,
  } = useFirebirdTargetScope(endpointUrl, databaseTargetId, true, customPost);

  const [activeSection, setActiveSection] = useState(
    initialTraceScope === 'services' ? 'configure' : 'configure'
  );
  const [traceScope, setTraceScope] = useState(
    initialTraceScope === 'services' ? 'services' : 'database'
  );
  const [traceName, setTraceName] = useState('ScratchRobin native trace');
  const [descriptor, setDescriptor] = useState(null);
  const [dbOptions, setDbOptions] = useState({});
  const [svcOptions, setSvcOptions] = useState({});
  const [includeDbWithServices, setIncludeDbWithServices] = useState(false);

  const [sessions, setSessions] = useState([]);
  const [nativeSessions, setNativeSessions] = useState([]);
  const [activeTraceId, setActiveTraceId] = useState('');
  const [polledOutput, setPolledOutput] = useState(null);

  const [auditFilename, setAuditFilename] = useState('');
  const [auditRoot, setAuditRoot] = useState('');
  const [auditMaxLines, setAuditMaxLines] = useState(200);
  const [auditResult, setAuditResult] = useState(null);

  const [pendingReview, setPendingReview] = useState(null);
  const [lastOutcome, setLastOutcome] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const callTrace = useCallback(
    (action, extra = {}) =>
      post({
        action: 'firebird_trace',
        request: {action, ...extra},
      }),
    [post]
  );

  const loadWorkspace = useCallback(async () => {
    if (!selectedTargetId) return;
    setBusy(true);
    setError('');
    try {
      const [desc, listResp] = await Promise.all([
        callTrace('describe'),
        callTrace('list').catch(() => ({items: []})),
      ]);
      setDescriptor(desc);
      setDbOptions((prev) =>
        Object.keys(prev).length ? prev : buildInitialFieldDefaults(desc?.option_fields || [])
      );
      setSvcOptions((prev) =>
        Object.keys(prev).length ? prev : buildInitialFieldDefaults(desc?.service_option_fields || [])
      );
      const listed = Array.isArray(listResp?.items) ? listResp.items : Array.isArray(listResp?.sessions) ? listResp.sessions : [];
      setSessions(listed);
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  }, [callTrace, selectedTargetId]);

  useEffect(() => {
    loadWorkspace();
  }, [loadWorkspace]);

  const loadNativeSessions = async () => {
    if (!selectedTargetId) return;
    setBusy(true);
    setError('');
    try {
      const resp = await callTrace('list_native');
      setNativeSessions(Array.isArray(resp?.sessions) ? resp.sessions : Array.isArray(resp?.items) ? resp.items : []);
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const reviewStart = async () => {
    setBusy(true);
    setError('');
    setLastOutcome(null);
    try {
      let review;
      if (traceScope === 'database') {
        review = await callTrace('review', {
          operation: 'start',
          name: traceName,
          options: dbOptions,
        });
      } else {
        review = await callTrace('review', {
          operation: 'start_services',
          name: traceName,
          service_options: svcOptions,
          ...(includeDbWithServices ? {database_options: dbOptions} : {}),
        });
      }
      setPendingReview(review);
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const reviewSessionControl = async (operation, traceId) => {
    setBusy(true);
    setError('');
    try {
      const review = await callTrace('review', {operation, trace_id: traceId});
      setPendingReview(review);
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const reviewExternalControl = async (operation, nativeSessionId) => {
    setBusy(true);
    setError('');
    try {
      const review = await callTrace('review', {
        operation,
        native_session_id: Number(nativeSessionId),
      });
      setPendingReview(review);
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const applyPendingReview = async (confirmPayload) => {
    setBusy(true);
    setError('');
    try {
      const applied = await callTrace('apply', confirmPayload);
      setPendingReview(null);
      setLastOutcome(applied);
      const createdTraceId = applied?.outcome?.trace_id;
      if (createdTraceId) {
        setActiveTraceId(createdTraceId);
        setActiveSection('sessions');
      }
      await loadWorkspace();
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const pollSession = async (traceId) => {
    const id = traceId || activeTraceId;
    if (!id) return;
    setBusy(true);
    setError('');
    try {
      const resp = await callTrace('poll', {trace_id: id, after: 0, limit: 200});
      setActiveTraceId(id);
      setPolledOutput(resp);
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const readAuditLog = async () => {
    setBusy(true);
    setError('');
    try {
      const resp = await callTrace('read_audit_log', {
        log_filename: auditFilename,
        ...(auditRoot.trim() ? {allowed_root: auditRoot.trim()} : {}),
        max_lines: Number(auditMaxLines) || 200,
      });
      setAuditResult(resp);
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const renderFieldGroup = (fields, values, setValues) => (
    <Grid columns="repeat(auto-fit, minmax(220px, 1fr))">
      {(fields || []).map((f) => {
        const val = values[f.field_id];
        const label = f.field_id.replace(/_/g, ' ');
        if (f.control === 'checkbox') {
          return (
            <Checkbox
              key={f.field_id}
              label={label}
              checked={Boolean(val)}
              disabled={busy}
              onChange={(checked) => setValues((cur) => ({...cur, [f.field_id]: Boolean(checked)}))}
            />
          );
        }
        if (f.control === 'number') {
          return (
            <NumberField
              key={f.field_id}
              label={label}
              size="small"
              value={val ?? 0}
              disabled={busy}
              helperText={f.zero_semantics ? `0 = ${f.zero_semantics}` : undefined}
              onChange={(e) => {
                const raw = e?.target !== undefined ? e.target.value : e;
                setValues((cur) => ({...cur, [f.field_id]: Number(raw || 0)}));
              }}
            />
          );
        }
        return (
          <TextField
            key={f.field_id}
            label={label}
            size="small"
            value={val ?? ''}
            disabled={busy}
            onChange={(e) => setValues((cur) => ({...cur, [f.field_id]: e.target.value}))}
          />
        );
      })}
    </Grid>
  );

  return (
    <ScrollArea orientation="both" style={{height: '100%'}}>
      <Box sx={{p: 2}} data-cdeadmin-qa-key="firebird-trace-workspace">
        <Stack gap="comfortable">
          <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap'}}>
            <Box>
              <Box component="h2" sx={{m: 0, fontSize: '1.1rem', fontWeight: 600}}>
                {gettext('Firebird Native Service, Session & Audit Trace')}
              </Box>
              <Box sx={{fontSize: '0.8125rem', color: 'text.secondary'}}>
                {gettext('Reviewed one-use Services API user trace lifecycle, external trace session controls, and bounded audit log tailing.')}
              </Box>
            </Box>
            <FormReference formKey="firebird-trace" />
          </Stack>

          {!databaseTargetId && (
            <DatabaseTargetPickerBar
              targets={targets}
              selectedTargetId={selectedTargetId}
              onSelectTarget={setSelectedTargetId}
              disabled={busy}
              onRefresh={reloadTargets}
            />
          )}

          {(error || targetsError) && (
            <ValidationMessage status="error">{error || targetsError}</ValidationMessage>
          )}

          <Banner status="info">
            {gettext('Captured trace lines remain volatile in memory and never enter durable SQL history or operation journals. SQL text, plans, parameters, and filters require explicit sensitive-capture approval.')}
          </Banner>

          <Stack direction="row" gap="tight" style={{flexWrap: 'wrap'}}>
            <Tab
              id="trace-tab-configure"
              label={gettext('Start New Trace')}
              selected={activeSection === 'configure'}
              onSelect={() => setActiveSection('configure')}
            />
            <Tab
              id="trace-tab-sessions"
              label={`${gettext('Managed Sessions')} (${sessions.length})`}
              selected={activeSection === 'sessions'}
              onSelect={() => {
                setActiveSection('sessions');
                loadWorkspace();
              }}
            />
            <Tab
              id="trace-tab-external"
              label={gettext('External Server Trace Sessions')}
              selected={activeSection === 'external'}
              onSelect={() => {
                setActiveSection('external');
                loadNativeSessions();
              }}
            />
            <Tab
              id="trace-tab-audit"
              label={gettext('System Audit Log Tail')}
              selected={activeSection === 'audit'}
              onSelect={() => setActiveSection('audit')}
            />
          </Stack>

          {pendingReview && (
            <ReviewConfirmationCard
              review={pendingReview}
              title={gettext('Reviewed Native Trace Operation: %s', pendingReview.operation)}
              previewLabel={gettext('Generated Firebird trace configuration')}
              previewText={
                pendingReview.payload?.native_configuration ||
                JSON.stringify(pendingReview.payload, null, 2)
              }
              busy={busy}
              onApply={applyPendingReview}
              onDiscard={() => setPendingReview(null)}
            />
          )}

          {lastOutcome && (
            <Panel variant="outlined" style={{padding: 12}}>
              <Stack gap="tight">
                <Stack direction="row" gap="standard" style={{alignItems: 'center'}}>
                  <strong>{gettext('Latest Trace Action Outcome')}:</strong>
                  <Badge label={lastOutcome.outcome?.state || lastOutcome.state || 'submitted'} status="info" />
                </Stack>
                <CodeEditor
                  label={gettext('Outcome metadata receipt')}
                  readonly
                  language="json"
                  value={JSON.stringify(lastOutcome, null, 2)}
                />
              </Stack>
            </Panel>
          )}

          {activeSection === 'configure' && (
            <Panel variant="outlined" style={{padding: 12}}>
              <Stack gap="comfortable">
                <Grid columns="repeat(auto-fit, minmax(240px, 1fr))">
                  <Select
                    label={gettext('Trace scope')}
                    size="small"
                    options={[
                      {value: 'database', label: gettext('Database attachment trace (<database>)')},
                      {value: 'services', label: gettext('Engine Services API trace (<services>)')},
                    ]}
                    value={traceScope}
                    disabled={busy}
                    onChange={(val) => setTraceScope(val)}
                  />
                  <TextField
                    label={gettext('Trace session name')}
                    size="small"
                    value={traceName}
                    disabled={busy}
                    onChange={(e) => setTraceName(e.target.value)}
                  />
                </Grid>

                {traceScope === 'services' && (
                  <>
                    <Box component="h4" sx={{m: 0, fontSize: '0.85rem', fontWeight: 600}}>
                      {gettext('Services Trace Options (<services>)')}
                    </Box>
                    {renderFieldGroup(descriptor?.service_option_fields, svcOptions, setSvcOptions)}
                    <Checkbox
                      label={gettext('Also include scoped <database> trace section in this service trace')}
                      checked={includeDbWithServices}
                      disabled={busy}
                      onChange={(checked) => setIncludeDbWithServices(Boolean(checked))}
                    />
                  </>
                )}

                {(traceScope === 'database' || includeDbWithServices) && (
                  <>
                    <Box component="h4" sx={{m: 0, fontSize: '0.85rem', fontWeight: 600}}>
                      {gettext('Database Trace Options (<database>)')}
                    </Box>
                    {renderFieldGroup(descriptor?.option_fields, dbOptions, setDbOptions)}
                  </>
                )}

                <Stack direction="row" gap="standard" style={{justifyContent: 'flex-end'}}>
                  <Button
                    intent="primary"
                    disabled={busy || !selectedTargetId}
                    loading={busy}
                    onClick={reviewStart}
                  >
                    {gettext('Review Trace Configuration')}
                  </Button>
                </Stack>
              </Stack>
            </Panel>
          )}

          {activeSection === 'sessions' && (
            <Panel variant="outlined" style={{padding: 12}}>
              <Stack gap="comfortable">
                <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between'}}>
                  <Box component="h4" sx={{m: 0, fontSize: '0.875rem', fontWeight: 600}}>
                    {gettext('Managed User Trace Sessions')}
                  </Box>
                  <Button intent="neutral" size="small" disabled={busy} onClick={loadWorkspace}>
                    {gettext('Refresh Sessions')}
                  </Button>
                </Stack>

                {sessions.length === 0 ? (
                  <Box sx={{fontSize: '0.8125rem', color: 'text.secondary'}}>
                    {gettext('No active or retained user trace sessions for this database target.')}
                  </Box>
                ) : (
                  sessions.map((s) => {
                    const tid = s.trace_id;
                    return (
                      <Panel key={tid} variant="outlined" style={{padding: 10}}>
                        <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap'}}>
                          <Box>
                            <strong>{s.name || tid}</strong>{' '}
                            <Badge label={s.state || 'active'} status="info" />
                            <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
                              ID: <code>{tid}</code>
                              {s.native_session_id !== undefined ? ` · Native Session #${s.native_session_id}` : ''}
                            </Box>
                          </Box>
                          <Stack direction="row" gap="tight" style={{flexWrap: 'wrap'}}>
                            <Button intent="primary" size="small" disabled={busy} onClick={() => pollSession(tid)}>
                              {gettext('Poll Output')}
                            </Button>
                            {['suspend', 'resume', 'stop', 'release', 'forget'].map((op) => (
                              <Button
                                key={op}
                                intent={op === 'stop' || op === 'forget' ? 'destructive' : 'neutral'}
                                size="small"
                                disabled={busy}
                                onClick={() => reviewSessionControl(op, tid)}
                              >
                                {op}
                              </Button>
                            ))}
                          </Stack>
                        </Stack>
                      </Panel>
                    );
                  })
                )}

                {polledOutput && (
                  <CodeEditor
                    label={gettext('Captured trace output (%s)', activeTraceId)}
                    readonly
                    language="text"
                    value={
                      Array.isArray(polledOutput.lines)
                        ? polledOutput.lines.map((l) => (typeof l === 'string' ? l : l.text || JSON.stringify(l))).join('\n') ||
                          gettext('-- No trace lines emitted yet --')
                        : JSON.stringify(polledOutput, null, 2)
                    }
                  />
                )}
              </Stack>
            </Panel>
          )}

          {activeSection === 'external' && (
            <Panel variant="outlined" style={{padding: 12}}>
              <Stack gap="comfortable">
                <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between'}}>
                  <Box component="h4" sx={{m: 0, fontSize: '0.875rem', fontWeight: 600}}>
                    {gettext('Native Server Trace Sessions (svc_trace_list)')}
                  </Box>
                  <Button intent="neutral" size="small" disabled={busy} onClick={loadNativeSessions}>
                    {gettext('Query Services Manager')}
                  </Button>
                </Stack>
                {nativeSessions.length === 0 ? (
                  <Box sx={{fontSize: '0.8125rem', color: 'text.secondary'}}>
                    {gettext('No active native trace sessions reported by the Firebird Services Manager.')}
                  </Box>
                ) : (
                  nativeSessions.map((ns) => {
                    const sid = ns.native_session_id ?? ns.session_id ?? ns.id;
                    return (
                      <Panel key={String(sid)} variant="outlined" style={{padding: 10}}>
                        <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap'}}>
                          <Box>
                            <strong>{gettext('Native Session #%s', sid)}</strong>{' '}
                            {ns.name && <span>— {ns.name}</span>}{' '}
                            {ns.user && <Badge label={ns.user} status="neutral" />}
                          </Box>
                          <Stack direction="row" gap="tight">
                            <Button intent="neutral" size="small" disabled={busy} onClick={() => reviewExternalControl('suspend_external', sid)}>
                              {gettext('Suspend')}
                            </Button>
                            <Button intent="neutral" size="small" disabled={busy} onClick={() => reviewExternalControl('resume_external', sid)}>
                              {gettext('Resume')}
                            </Button>
                            <Button intent="destructive" size="small" disabled={busy} onClick={() => reviewExternalControl('stop_external', sid)}>
                              {gettext('Stop')}
                            </Button>
                          </Stack>
                        </Stack>
                      </Panel>
                    );
                  })
                )}
              </Stack>
            </Panel>
          )}

          {activeSection === 'audit' && (
            <Panel variant="outlined" style={{padding: 12}}>
              <Stack gap="comfortable">
                <Box component="h4" sx={{m: 0, fontSize: '0.875rem', fontWeight: 600}}>
                  {gettext('Bounded System Audit Log Tail')}
                </Box>
                <Grid columns="repeat(auto-fit, minmax(220px, 1fr))">
                  <TextField
                    label={gettext('Audit log filename')}
                    size="small"
                    value={auditFilename}
                    disabled={busy}
                    onChange={(e) => setAuditFilename(e.target.value)}
                  />
                  <TextField
                    label={gettext('Allowed root directory (optional)')}
                    size="small"
                    value={auditRoot}
                    disabled={busy}
                    onChange={(e) => setAuditRoot(e.target.value)}
                  />
                  <NumberField
                    label={gettext('Max tail lines')}
                    size="small"
                    value={auditMaxLines}
                    disabled={busy}
                    onChange={(e) => setAuditMaxLines(Number(e?.target !== undefined ? e.target.value : e) || 200)}
                  />
                </Grid>
                <Stack direction="row" gap="standard" style={{justifyContent: 'flex-end'}}>
                  <Button
                    intent="primary"
                    size="small"
                    disabled={busy || !auditFilename.trim() || !selectedTargetId}
                    onClick={readAuditLog}
                  >
                    {gettext('Read Audit Log Tail')}
                  </Button>
                </Stack>
                {auditResult && (
                  <CodeEditor
                    label={gettext('Audit log tail')}
                    readonly
                    language="text"
                    value={
                      Array.isArray(auditResult.lines)
                        ? auditResult.lines.join('\n')
                        : auditResult.text || JSON.stringify(auditResult, null, 2)
                    }
                  />
                )}
              </Stack>
            </Panel>
          )}
        </Stack>
      </Box>
    </ScrollArea>
  );
}

FirebirdTraceWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  databaseTargetId: PropTypes.string,
  initialTraceScope: PropTypes.string,
  customPost: PropTypes.func,
};
