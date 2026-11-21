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
import {Select} from '../../primitives/Choice';
import {Badge, Banner, ProgressBar, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
import {
  DatabaseTargetPickerBar,
  extractApiError,
  useFirebirdTargetScope,
} from './firebirdAdminHelpers';

export default function FirebirdDatabaseEncryptionWorkspace({
  endpointUrl,
  databaseTargetId = null,
  customPost = null,
}) {
  const {
    targets,
    selectedTargetId,
    setSelectedTargetId,
    selectedTarget,
    targetsError,
    reloadTargets,
    post,
  } = useFirebirdTargetScope(endpointUrl, databaseTargetId, true, customPost);

  const [descriptor, setDescriptor] = useState(null);
  const [status, setStatus] = useState(null);
  const [dbResource, setDbResource] = useState(null);

  const [operationMode, setOperationMode] = useState('encrypt_database');
  const [pluginName, setPluginName] = useState('');
  const [keyName, setKeyName] = useState('');
  const [baseKey, setBaseKey] = useState('');
  const [decryptConfirm, setDecryptConfirm] = useState('');
  const [settleTimeout, setSettleTimeout] = useState(15);

  const [plannedDdl, setPlannedDdl] = useState(null);
  const [applyResult, setApplyResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const callEncryption = useCallback(
    (action, extra = {}) =>
      post({
        action: 'firebird_database_encryption',
        request: {action, ...extra},
      }),
    [post]
  );

  const loadWorkspace = useCallback(async () => {
    if (!selectedTargetId) return;
    setBusy(true);
    setError('');
    try {
      const [desc, statResp, pageResp] = await Promise.all([
        callEncryption('describe'),
        callEncryption('inspect'),
        post({action: 'resource_page', request: {}}).catch(() => null),
      ]);
      setDescriptor(desc);
      setStatus(statResp);
      const dbRow = (pageResp?.items || []).find((r) => r.resource_kind === 'database') || null;
      setDbResource(dbRow);
      if (statResp?.encryption_plugin) {
        setPluginName((cur) => cur || statResp.encryption_plugin);
      }
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  }, [callEncryption, post, selectedTargetId]);

  useEffect(() => {
    loadWorkspace();
  }, [loadWorkspace]);

  const handlePlanDdl = async () => {
    setBusy(true);
    setError('');
    setApplyResult(null);
    try {
      const draft =
        operationMode === 'encrypt_database'
          ? {
            plugin_name: pluginName.trim(),
            ...(keyName.trim() ? {key_name: keyName.trim()} : {}),
            ...(baseKey.trim() ? {base_key: baseKey.trim()} : {}),
          }
          : {
            confirmation: decryptConfirm.trim(),
          };
      const plan = await post({
        action: 'visual_admin_plan',
        request: {
          resource_kind: 'database',
          operation_id: operationMode,
          ...(dbResource?.resource_id ? {resource_id: dbResource.resource_id} : {}),
          draft,
        },
      });
      setPlannedDdl({plan, draft});
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const handleApplyDdl = async () => {
    if (!plannedDdl?.plan) return;
    setBusy(true);
    setError('');
    try {
      const applied = await post({
        action: 'visual_admin_apply',
        request: {
          plan_id: plannedDdl.plan.plan_id,
          plan_digest: plannedDdl.plan.plan_digest,
          confirmed: true,
        },
      });
      setPlannedDdl(null);
      setApplyResult(applied);
      await loadWorkspace();
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const handleWaitSettle = async (expectedStateCode) => {
    setBusy(true);
    setError('');
    try {
      const settled = await callEncryption('wait_settle', {
        expected_state_code: expectedStateCode,
        timeout_seconds: Number(settleTimeout) || 15,
      });
      setStatus(settled);
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const totalPages = Number(status?.total_pages || 0);
  const cryptPage = Number(status?.crypt_page || 0);
  const progressPct = totalPages > 0 ? Math.min(100, Math.round((cryptPage / totalPages) * 100)) : 0;

  return (
    <ScrollArea orientation="both" style={{height: '100%'}}>
      <Box sx={{p: 2}} data-cdeadmin-qa-key="firebird-database-encryption-workspace">
        <Stack gap="comfortable">
          <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap'}}>
            <Box>
              <Box component="h2" sx={{m: 0, fontSize: '1.1rem', fontWeight: 600}}>
                {gettext('Firebird Database-at-Rest Encryption Status & Lifecycle')}
              </Box>
              <Box sx={{fontSize: '0.8125rem', color: 'text.secondary'}}>
                {descriptor?.external_plugin_dependency || gettext('Inspect MON$CRYPT_STATE, key-holder configuration, background crypt page progress, and execute reviewed ALTER DATABASE ENCRYPT / DECRYPT.')}
              </Box>
            </Box>
            <FormReference formKey="firebird-database-encryption" />
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
            {gettext('Database-at-rest encryption is distinct from WireCrypt transport encryption and gbak backup encryption. ScratchRobin never stores or handles raw database encryption keys.')}
          </Banner>

          {status && (
            <Panel variant="outlined" style={{padding: 12}} data-cdeadmin-qa-key="firebird-encryption.status">
              <Stack gap="comfortable">
                <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap'}}>
                  <Stack direction="row" gap="standard" style={{alignItems: 'center', flexWrap: 'wrap'}}>
                    <strong>{gettext('Current Crypt State')}:</strong>
                    <Badge
                      label={status.crypt_state || String(status.crypt_state_code ?? '0')}
                      status={status.crypt_state_code === 1 && !status.in_transition ? 'success' : status.in_transition ? 'warning' : 'neutral'}
                    />
                    {status.encryption_plugin && (
                      <span>{gettext('Plugin')}: <code>{status.encryption_plugin}</code></span>
                    )}
                    {status.encryption_key_name && (
                      <span>{gettext('Key')}: <code>{status.encryption_key_name}</code></span>
                    )}
                  </Stack>
                  <Button intent="neutral" size="small" disabled={busy} onClick={loadWorkspace}>
                    {gettext('Refresh Status')}
                  </Button>
                </Stack>

                {status.in_transition && (
                  <ProgressBar
                    value={progressPct}
                    status="determinate"
                    label={gettext('Background crypt thread progress (%s / %s pages)', cryptPage, totalPages)}
                  />
                )}

                <CodeEditor
                  label={gettext('Observed MON$DATABASE crypt state, RDB$CONFIG & host plugin readiness')}
                  readonly
                  language="json"
                  value={JSON.stringify(status, null, 2)}
                />

                <Stack direction="row" gap="standard" style={{alignItems: 'flex-end', flexWrap: 'wrap'}}>
                  <NumberField
                    label={gettext('Settle wait window (seconds, 1–60)')}
                    size="small"
                    value={settleTimeout}
                    disabled={busy}
                    onChange={(e) => setSettleTimeout(Number(e?.target !== undefined ? e.target.value : e) || 15)}
                  />
                  <Button intent="neutral" size="small" disabled={busy} onClick={() => handleWaitSettle(1)}>
                    {gettext('Wait for Encrypted Settle (State 1)')}
                  </Button>
                  <Button intent="neutral" size="small" disabled={busy} onClick={() => handleWaitSettle(0)}>
                    {gettext('Wait for Decrypted Settle (State 0)')}
                  </Button>
                </Stack>
              </Stack>
            </Panel>
          )}

          <Panel variant="outlined" style={{padding: 12}}>
            <Stack gap="comfortable">
              <Box component="h4" sx={{m: 0, fontSize: '0.875rem', fontWeight: 600}}>
                {gettext('Plan & Execute Native ALTER DATABASE ENCRYPT / DECRYPT')}
              </Box>
              <Select
                label={gettext('Operation')}
                size="small"
                options={[
                  {value: 'encrypt_database', label: gettext('Encrypt database (ALTER DATABASE ENCRYPT WITH …)')},
                  {value: 'decrypt_database', label: gettext('Decrypt database (ALTER DATABASE DECRYPT)')},
                ]}
                value={operationMode}
                disabled={busy}
                onChange={(val) => {
                  setOperationMode(val);
                  setPlannedDdl(null);
                }}
              />

              {operationMode === 'encrypt_database' ? (
                <Grid columns="repeat(auto-fit, minmax(220px, 1fr))">
                  <TextField
                    label={gettext('DbCrypt plugin name')}
                    size="small"
                    value={pluginName}
                    disabled={busy}
                    onChange={(e) => setPluginName(e.target.value)}
                  />
                  <TextField
                    label={gettext('Key name (optional)')}
                    size="small"
                    value={keyName}
                    disabled={busy}
                    onChange={(e) => setKeyName(e.target.value)}
                  />
                  <TextField
                    label={gettext('Base key / external key reference (optional)')}
                    size="small"
                    value={baseKey}
                    disabled={busy}
                    onChange={(e) => setBaseKey(e.target.value)}
                  />
                </Grid>
              ) : (
                <TextField
                  label={gettext('Type database name (%s) to confirm decryption', selectedTarget?.database_name || selectedTarget?.display_name || '')}
                  size="small"
                  value={decryptConfirm}
                  disabled={busy}
                  onChange={(e) => setDecryptConfirm(e.target.value)}
                />
              )}

              <Stack direction="row" gap="standard" style={{justifyContent: 'flex-end'}}>
                <Button
                  intent={operationMode === 'decrypt_database' ? 'destructive' : 'primary'}
                  disabled={busy || !selectedTargetId || (operationMode === 'encrypt_database' && !pluginName.trim())}
                  loading={busy}
                  onClick={handlePlanDdl}
                >
                  {gettext('Preview Native SQL Plan')}
                </Button>
              </Stack>

              {plannedDdl?.plan && (
                <Panel variant="outlined" style={{padding: 10}}>
                  <Stack gap="standard">
                    <CodeEditor
                      label={gettext('Planned Firebird DDL statement')}
                      readonly
                      language="sql"
                      value={
                        (plannedDdl.plan.statements || [])
                          .map((s) => (typeof s === 'string' ? s : s.sql || s.statement || JSON.stringify(s)))
                          .join(';\n') || plannedDdl.plan.command_preview?.sql || ''
                      }
                    />
                    <Stack direction="row" gap="standard" style={{justifyContent: 'flex-end'}}>
                      <Button intent="neutral" size="small" disabled={busy} onClick={() => setPlannedDdl(null)}>
                        {gettext('Cancel')}
                      </Button>
                      <Button intent="primary" size="small" loading={busy} disabled={busy} onClick={handleApplyDdl}>
                        {gettext('Execute Reviewed DDL')}
                      </Button>
                    </Stack>
                  </Stack>
                </Panel>
              )}

              {applyResult && (
                <CodeEditor
                  label={gettext('DDL execution receipt')}
                  readonly
                  language="json"
                  value={JSON.stringify(applyResult, null, 2)}
                />
              )}
            </Stack>
          </Panel>
        </Stack>
      </Box>
    </ScrollArea>
  );
}

FirebirdDatabaseEncryptionWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  databaseTargetId: PropTypes.string,
  customPost: PropTypes.func,
};
