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
import {TextArea, TextField} from '../../primitives/Field';
import {Select} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import {Tab} from '../../navigation/TabsAndBreadcrumbs';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
import {
  DatabaseTargetPickerBar,
  extractApiError,
  ReceiptHistoryPanel,
  ReviewConfirmationCard,
  useFirebirdTargetScope,
} from './firebirdAdminHelpers';

const MANAGED_FILES = ['firebird.conf', 'databases.conf', 'replication.conf', 'plugins.conf'];

export default function FirebirdHostConfigWorkspace({
  endpointUrl,
  databaseTargetId = null,
  customPost = null,
}) {
  const {
    targets,
    selectedTargetId,
    setSelectedTargetId,
    targetsError,
    reloadTargets,
    post,
  } = useFirebirdTargetScope(endpointUrl, databaseTargetId, false, customPost);

  const [descriptor, setDescriptor] = useState(null);
  const [inspection, setInspection] = useState(null);
  const [targetFile, setTargetFile] = useState('firebird.conf');
  const [lifecycleAction, setLifecycleAction] = useState('write_only');

  // firebird.conf structured set / unset rows
  const [setKey, setSetKey] = useState('');
  const [setValue, setSetValue] = useState('');
  const [stagedSetOptions, setStagedSetOptions] = useState({});
  const [unsetKeysText, setUnsetKeysText] = useState('');

  // databases.conf structured alias upsert / remove
  const [aliasName, setAliasName] = useState('');
  const [aliasPath, setAliasPath] = useState('');
  const [stagedAliases, setStagedAliases] = useState({});
  const [removeAliasesText, setRemoveAliasesText] = useState('');
  const [removeConfirmText, setRemoveConfirmText] = useState('');

  // replication.conf / plugins.conf structured drafts
  const [replDbPath, setReplDbPath] = useState('');
  const [replJournalDir, setReplJournalDir] = useState('');
  const [replArchiveDir, setReplArchiveDir] = useState('');
  const [pluginSpecName, setPluginSpecName] = useState('');
  const [pluginSpecModule, setPluginSpecModule] = useState('');

  const [pendingReview, setPendingReview] = useState(null);
  const [lastOutcome, setLastOutcome] = useState(null);
  const [receipts, setReceipts] = useState([]);
  const [selectedReceipt, setSelectedReceipt] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const callHostConfig = useCallback(
    (action, extra = {}) =>
      post({
        action: 'firebird_host_configuration',
        request: {action, ...extra},
      }),
    [post]
  );

  const loadWorkspace = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const [desc, listResp, inspectResp] = await Promise.all([
        callHostConfig('describe'),
        callHostConfig('list').catch(() => ({items: []})),
        callHostConfig('inspect').catch((err) => ({_inspectError: extractApiError(err)})),
      ]);
      setDescriptor(desc);
      setReceipts(Array.isArray(listResp?.items) ? listResp.items : []);
      if (inspectResp?._inspectError) {
        setInspection(null);
        setError(inspectResp._inspectError);
      } else {
        setInspection(inspectResp);
      }
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  }, [callHostConfig]);

  useEffect(() => {
    loadWorkspace();
  }, [loadWorkspace]);

  const currentFileSummary = inspection?.files?.[targetFile] || null;
  const expectedGen = currentFileSummary?.generation_sha256 || '';

  const addSetOption = () => {
    const k = setKey.trim();
    if (!k) return;
    setStagedSetOptions((cur) => ({...cur, [k]: setValue}));
    setSetKey('');
    setSetValue('');
  };

  const addAliasUpsert = () => {
    const name = aliasName.trim();
    const path = aliasPath.trim();
    if (!name || !path) return;
    setStagedAliases((cur) => ({...cur, [name]: {path, overrides: {}}}));
    setAliasName('');
    setAliasPath('');
  };

  const handleReview = async () => {
    setBusy(true);
    setError('');
    setLastOutcome(null);
    try {
      const base = {
        target_file: targetFile,
        expected_generation_sha256: expectedGen,
        lifecycle_action: lifecycleAction,
      };
      let payload = base;
      if (targetFile === 'firebird.conf') {
        const unsets = unsetKeysText
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean);
        payload = {
          ...base,
          set_options: stagedSetOptions,
          unset_options: unsets,
        };
      } else if (targetFile === 'databases.conf') {
        const removals = removeAliasesText
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean);
        payload = {
          ...base,
          upsert_aliases: stagedAliases,
          remove_aliases: removals,
          ...(removals.length ? {confirmation: removeConfirmText.trim()} : {}),
        };
      } else if (targetFile === 'replication.conf') {
        payload = {
          ...base,
          replication_spec: {
            databases: {
              [replDbPath.trim()]: {
                journal_directory: replJournalDir.trim(),
                journal_archive_directory: replArchiveDir.trim(),
                log_errors: true,
              },
            },
          },
        };
      } else if (targetFile === 'plugins.conf') {
        payload = {
          ...base,
          plugins_spec: {
            plugins: {
              [pluginSpecName.trim()]: {
                module: pluginSpecModule.trim(),
              },
            },
          },
        };
      }
      const review = await callHostConfig('review', payload);
      setPendingReview(review);
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const handleApply = async (confirmPayload) => {
    setBusy(true);
    setError('');
    try {
      const applied = await callHostConfig('apply', confirmPayload);
      setPendingReview(null);
      setLastOutcome(applied);
      setStagedSetOptions({});
      setStagedAliases({});
      await loadWorkspace();
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const inspectReceipt = async (reviewId) => {
    try {
      setSelectedReceipt(await callHostConfig('get', {review_id: reviewId}));
    } catch (err) {
      setError(extractApiError(err));
    }
  };

  return (
    <ScrollArea orientation="both" style={{height: '100%'}}>
      <Box sx={{p: 2}} data-cdeadmin-qa-key="firebird-host-configuration-workspace">
        <Stack gap="comfortable">
          <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap'}}>
            <Box>
              <Box component="h2" sx={{m: 0, fontSize: '1.1rem', fontWeight: 600}}>
                {gettext('Firebird Host Configuration Files')}
              </Box>
              <Box sx={{fontSize: '0.8125rem', color: 'text.secondary'}}>
                {descriptor?.notes || gettext('Inspect and update firebird.conf, databases.conf, replication.conf, and plugins.conf with SHA-256 compare-and-set and atomic rollback.')}
              </Box>
            </Box>
            <FormReference formKey="firebird-host-configuration" />
          </Stack>

          <DatabaseTargetPickerBar
            targets={targets}
            selectedTargetId={selectedTargetId}
            onSelectTarget={setSelectedTargetId}
            allowServerScope
            disabled={busy}
            onRefresh={() => {
              reloadTargets();
              loadWorkspace();
            }}
          />

          {(error || targetsError) && (
            <ValidationMessage status="error">{error || targetsError}</ValidationMessage>
          )}

          {inspection?.pending_restart_keys?.length > 0 && (
            <Banner status="warning">
              {gettext(
                'Global configuration keys differ from active RDB$CONFIG and require a daemon restart: %s',
                inspection.pending_restart_keys.join(', ')
              )}
            </Banner>
          )}

          <Stack direction="row" gap="tight" style={{flexWrap: 'wrap'}}>
            {MANAGED_FILES.map((fname) => (
              <Tab
                key={fname}
                id={`cfg-file-${fname}`}
                label={fname}
                selected={targetFile === fname}
                onSelect={() => setTargetFile(fname)}
              />
            ))}
          </Stack>

          <Panel variant="outlined" style={{padding: 12}}>
            <Stack gap="comfortable">
              <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap'}}>
                <Box>
                  <strong>{targetFile}</strong>{' '}
                  <Badge
                    label={currentFileSummary?.exists ? gettext('Present') : gettext('Not created yet')}
                    status={currentFileSummary?.exists ? 'success' : 'neutral'}
                  />
                  {expectedGen && (
                    <Box component="span" sx={{ml: 1, fontSize: '0.75rem', color: 'text.secondary'}}>
                      SHA-256: <code>{expectedGen.slice(0, 16)}…</code> ({currentFileSummary?.size_bytes || 0} B)
                    </Box>
                  )}
                </Box>
                <Select
                  label={gettext('Apply lifecycle mode')}
                  size="small"
                  options={[
                    {value: 'write_only', label: gettext('Write & validate atomically (no restart)')},
                    {value: 'restart_managed_daemon', label: gettext('Write, validate & restart managed daemon')},
                  ]}
                  value={lifecycleAction}
                  disabled={busy}
                  onChange={(val) => setLifecycleAction(val)}
                />
              </Stack>

              {currentFileSummary && (
                <CodeEditor
                  label={gettext('Observed %s entries / state', targetFile)}
                  readonly
                  language="json"
                  value={JSON.stringify(currentFileSummary, null, 2)}
                />
              )}

              {targetFile === 'firebird.conf' && (
                <Stack gap="standard">
                  <Box component="h4" sx={{m: 0, fontSize: '0.85rem', fontWeight: 600}}>
                    {gettext('Stage firebird.conf Key Updates')}
                  </Box>
                  <Grid columns="1fr 1fr auto">
                    <TextField label={gettext('Configuration key (e.g. DefaultDbCachePages)')} size="small" value={setKey} disabled={busy} onChange={(e) => setSetKey(e.target.value)} />
                    <TextField label={gettext('Value')} size="small" value={setValue} disabled={busy} onChange={(e) => setSetValue(e.target.value)} />
                    <Button intent="neutral" size="small" disabled={busy || !setKey.trim()} onClick={addSetOption}>
                      {gettext('Stage Key')}
                    </Button>
                  </Grid>
                  {Object.keys(stagedSetOptions).length > 0 && (
                    <TextArea
                      label={gettext('Staged set_options')}
                      rows={3}
                      readOnly
                      value={Object.entries(stagedSetOptions).map(([k, v]) => `${k} = ${v}`).join('\n')}
                    />
                  )}
                  <TextField
                    label={gettext('Keys to unset / revert to default (comma-separated)')}
                    size="small"
                    value={unsetKeysText}
                    disabled={busy}
                    onChange={(e) => setUnsetKeysText(e.target.value)}
                  />
                </Stack>
              )}

              {targetFile === 'databases.conf' && (
                <Stack gap="standard">
                  <Box component="h4" sx={{m: 0, fontSize: '0.85rem', fontWeight: 600}}>
                    {gettext('Stage databases.conf Alias Upserts / Removals')}
                  </Box>
                  <Grid columns="1fr 2fr auto">
                    <TextField label={gettext('Alias name')} size="small" value={aliasName} disabled={busy} onChange={(e) => setAliasName(e.target.value)} />
                    <TextField label={gettext('Database file path on host')} size="small" value={aliasPath} disabled={busy} onChange={(e) => setAliasPath(e.target.value)} />
                    <Button intent="neutral" size="small" disabled={busy || !aliasName.trim() || !aliasPath.trim()} onClick={addAliasUpsert}>
                      {gettext('Stage Alias')}
                    </Button>
                  </Grid>
                  {Object.keys(stagedAliases).length > 0 && (
                    <TextArea
                      label={gettext('Staged alias upserts')}
                      rows={3}
                      readOnly
                      value={Object.entries(stagedAliases).map(([k, v]) => `${k} = ${v.path}`).join('\n')}
                    />
                  )}
                  <Grid columns="1fr 1fr">
                    <TextField
                      label={gettext('Aliases to remove (comma-separated)')}
                      size="small"
                      value={removeAliasesText}
                      disabled={busy}
                      onChange={(e) => setRemoveAliasesText(e.target.value)}
                    />
                    <TextField
                      label={gettext('Type sorted removed alias names to confirm')}
                      size="small"
                      value={removeConfirmText}
                      disabled={busy || !removeAliasesText.trim()}
                      onChange={(e) => setRemoveConfirmText(e.target.value)}
                    />
                  </Grid>
                </Stack>
              )}

              {targetFile === 'replication.conf' && (
                <Grid columns="repeat(auto-fit, minmax(220px, 1fr))">
                  <TextField label={gettext('Database path')} size="small" value={replDbPath} disabled={busy} onChange={(e) => setReplDbPath(e.target.value)} />
                  <TextField label={gettext('Journal directory')} size="small" value={replJournalDir} disabled={busy} onChange={(e) => setReplJournalDir(e.target.value)} />
                  <TextField label={gettext('Journal archive directory')} size="small" value={replArchiveDir} disabled={busy} onChange={(e) => setReplArchiveDir(e.target.value)} />
                </Grid>
              )}

              {targetFile === 'plugins.conf' && (
                <Grid columns="repeat(auto-fit, minmax(220px, 1fr))">
                  <TextField label={gettext('Plugin configuration stanza name')} size="small" value={pluginSpecName} disabled={busy} onChange={(e) => setPluginSpecName(e.target.value)} />
                  <TextField label={gettext('Module path / name')} size="small" value={pluginSpecModule} disabled={busy} onChange={(e) => setPluginSpecModule(e.target.value)} />
                </Grid>
              )}

              <Stack direction="row" gap="standard" style={{justifyContent: 'flex-end'}}>
                <Button intent="primary" disabled={busy || !inspection} loading={busy} onClick={handleReview}>
                  {gettext('Review %s Changes', targetFile)}
                </Button>
              </Stack>
            </Stack>
          </Panel>

          {pendingReview && (
            <ReviewConfirmationCard
              review={pendingReview}
              title={gettext('Reviewed Host Configuration Update (%s)', pendingReview.payload?.target_file || targetFile)}
              previewLabel={gettext('Proposed rendered configuration file')}
              previewText={pendingReview.payload?.rendered_text || JSON.stringify(pendingReview.payload, null, 2)}
              busy={busy}
              onApply={handleApply}
              onDiscard={() => setPendingReview(null)}
            />
          )}

          {lastOutcome && (
            <CodeEditor
              label={gettext('Applied configuration receipt')}
              readonly
              language="json"
              value={JSON.stringify(lastOutcome, null, 2)}
            />
          )}

          <ReceiptHistoryPanel
            items={receipts}
            onInspectReceipt={inspectReceipt}
            selectedReceipt={selectedReceipt}
          />
        </Stack>
      </Box>
    </ScrollArea>
  );
}

FirebirdHostConfigWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  databaseTargetId: PropTypes.string,
  customPost: PropTypes.func,
};
