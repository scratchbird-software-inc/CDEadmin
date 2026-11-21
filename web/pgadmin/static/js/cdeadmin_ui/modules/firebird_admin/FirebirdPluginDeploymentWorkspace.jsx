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
import {TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
import {
  DatabaseTargetPickerBar,
  extractApiError,
  ReceiptHistoryPanel,
  ReviewConfirmationCard,
  useFirebirdTargetScope,
} from './firebirdAdminHelpers';

export default function FirebirdPluginDeploymentWorkspace({
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
  const [inventory, setInventory] = useState(null);
  const [operation, setOperation] = useState('deploy_udr_module');
  const [moduleName, setModuleName] = useState('');
  const [stagedFilename, setStagedFilename] = useState('');
  const [expectedSourceSha, setExpectedSourceSha] = useState('');
  const [stagedConfigFilename, setStagedConfigFilename] = useState('');
  const [expectedConfigSha, setExpectedConfigSha] = useState('');
  const [pluginAlias, setPluginAlias] = useState('');
  const [replaceExisting, setReplaceExisting] = useState(false);
  const [acknowledgeDependents, setAcknowledgeDependents] = useState(false);
  const [confirmationName, setConfirmationName] = useState('');

  const [pendingReview, setPendingReview] = useState(null);
  const [lastOutcome, setLastOutcome] = useState(null);
  const [receipts, setReceipts] = useState([]);
  const [selectedReceipt, setSelectedReceipt] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const callPlugins = useCallback(
    (action, extra = {}) =>
      post({
        action: 'firebird_plugin_deployment',
        request: {action, ...extra},
      }),
    [post]
  );

  const loadWorkspace = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const [desc, listResp, invResp] = await Promise.all([
        callPlugins('describe'),
        callPlugins('list').catch(() => ({items: []})),
        callPlugins('inspect').catch((err) => ({_inspectError: extractApiError(err)})),
      ]);
      setDescriptor(desc);
      setReceipts(Array.isArray(listResp?.items) ? listResp.items : []);
      if (invResp?._inspectError) {
        setInventory(null);
        setError(invResp._inspectError);
      } else {
        setInventory(invResp);
      }
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  }, [callPlugins]);

  useEffect(() => {
    loadWorkspace();
  }, [loadWorkspace]);

  const isDeploy = operation === 'deploy_udr_module' || operation === 'deploy_plugin';
  const isPluginOp = operation === 'deploy_plugin' || operation === 'remove_plugin';

  const handleReview = async () => {
    setBusy(true);
    setError('');
    setLastOutcome(null);
    try {
      const payload = isDeploy
        ? {
          operation,
          module_name: moduleName.trim(),
          ...(stagedFilename.trim() ? {staged_filename: stagedFilename.trim()} : {}),
          ...(expectedSourceSha.trim() ? {expected_source_sha256: expectedSourceSha.trim()} : {}),
          ...(isPluginOp && stagedConfigFilename.trim() ? {staged_config_filename: stagedConfigFilename.trim()} : {}),
          ...(isPluginOp && expectedConfigSha.trim() ? {expected_config_sha256: expectedConfigSha.trim()} : {}),
          ...(isPluginOp && pluginAlias.trim() ? {plugin_alias: pluginAlias.trim()} : {}),
          replace_existing: Boolean(replaceExisting),
        }
        : {
          operation,
          module_name: moduleName.trim(),
          confirmation: confirmationName.trim(),
          acknowledge_dependents: Boolean(acknowledgeDependents),
          ...(isPluginOp && pluginAlias.trim() ? {plugin_alias: pluginAlias.trim()} : {}),
        };
      const review = await callPlugins('review', payload);
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
      const applied = await callPlugins('apply', confirmPayload);
      setPendingReview(null);
      setLastOutcome(applied);
      await loadWorkspace();
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const inspectReceipt = async (reviewId) => {
    try {
      setSelectedReceipt(await callPlugins('get', {review_id: reviewId}));
    } catch (err) {
      setError(extractApiError(err));
    }
  };

  return (
    <ScrollArea orientation="both" style={{height: '100%'}}>
      <Box sx={{p: 2}} data-cdeadmin-qa-key="firebird-plugin-deployment-workspace">
        <Stack gap="comfortable">
          <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap'}}>
            <Box>
              <Box component="h2" sx={{m: 0, fontSize: '1.1rem', fontWeight: 600}}>
                {gettext('Firebird Plugins & UDR Module Deployment')}
              </Box>
              <Box sx={{fontSize: '0.8125rem', color: 'text.secondary'}}>
                {gettext('Inspect ELF shared-library plugins and UDR modules, verify exported entrypoints & SHA-256 digests, and track catalog dependents.')}
              </Box>
            </Box>
            <FormReference formKey="firebird-plugin-deployment" />
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

          {descriptor?.platform_constraints?.Win_Sspi && (
            <Banner status="info">
              {descriptor.platform_constraints.Win_Sspi.reason}{' '}
              {descriptor.platform_constraints.sample_crypt_plugins?.reason}
            </Banner>
          )}

          {inventory && (
            <Panel variant="outlined" style={{padding: 12}}>
              <Stack gap="standard">
                <Stack direction="row" gap="standard" style={{alignItems: 'center', flexWrap: 'wrap'}}>
                  <strong>{gettext('Runtime Root')}:</strong> <code>{inventory.runtime_root}</code>
                  <Badge label={`${(inventory.plugins || []).length} plugins`} status="info" />
                  <Badge label={`${(inventory.udr_modules || []).length} UDR modules`} status="info" />
                  <Badge label={`${(inventory.database_udr_dependents || []).length} catalog UDR dependents`} status="neutral" />
                </Stack>
                <CodeEditor
                  label={gettext('Installed plugin, UDR & catalog dependent inventory')}
                  readonly
                  language="json"
                  value={JSON.stringify(
                    {
                      staging_directory: inventory.staging_directory,
                      plugins: inventory.plugins,
                      udr_modules: inventory.udr_modules,
                      database_udr_dependents: inventory.database_udr_dependents,
                      unavailable_platform_plugins: inventory.unavailable_platform_plugins,
                    },
                    null,
                    2
                  )}
                />
              </Stack>
            </Panel>
          )}

          <Panel variant="outlined" style={{padding: 12}}>
            <Stack gap="comfortable">
              <Box component="h4" sx={{m: 0, fontSize: '0.875rem', fontWeight: 600}}>
                {gettext('Stage & Review Plugin / UDR Operation')}
              </Box>
              <Grid columns="repeat(auto-fit, minmax(220px, 1fr))">
                <Select
                  label={gettext('Operation')}
                  size="small"
                  options={[
                    {value: 'deploy_udr_module', label: gettext('Deploy UDR module (plugins/udr)')},
                    {value: 'remove_udr_module', label: gettext('Remove UDR module')},
                    {value: 'deploy_plugin', label: gettext('Deploy engine plugin (plugins/)')},
                    {value: 'remove_plugin', label: gettext('Remove engine plugin')},
                  ]}
                  value={operation}
                  disabled={busy}
                  onChange={(val) => setOperation(val)}
                />
                <TextField
                  label={gettext('Module name (without lib / .so)')}
                  size="small"
                  value={moduleName}
                  disabled={busy}
                  onChange={(e) => setModuleName(e.target.value)}
                />
                {isPluginOp && (
                  <TextField
                    label={gettext('Plugin alias (optional)')}
                    size="small"
                    value={pluginAlias}
                    disabled={busy}
                    onChange={(e) => setPluginAlias(e.target.value)}
                  />
                )}
              </Grid>

              {isDeploy ? (
                <Grid columns="repeat(auto-fit, minmax(240px, 1fr))">
                  <TextField
                    label={gettext('Staged binary filename (optional default lib<name>.so)')}
                    size="small"
                    value={stagedFilename}
                    disabled={busy}
                    onChange={(e) => setStagedFilename(e.target.value)}
                  />
                  <TextField
                    label={gettext('Expected binary SHA-256')}
                    size="small"
                    value={expectedSourceSha}
                    disabled={busy}
                    onChange={(e) => setExpectedSourceSha(e.target.value)}
                  />
                  {isPluginOp && (
                    <>
                      <TextField
                        label={gettext('Staged config filename (optional)')}
                        size="small"
                        value={stagedConfigFilename}
                        disabled={busy}
                        onChange={(e) => setStagedConfigFilename(e.target.value)}
                      />
                      <TextField
                        label={gettext('Expected config SHA-256')}
                        size="small"
                        value={expectedConfigSha}
                        disabled={busy}
                        onChange={(e) => setExpectedConfigSha(e.target.value)}
                      />
                    </>
                  )}
                  <Checkbox
                    label={gettext('Replace existing non-core module binary')}
                    checked={replaceExisting}
                    disabled={busy}
                    onChange={(v) => setReplaceExisting(Boolean(v))}
                  />
                </Grid>
              ) : (
                <Grid columns="repeat(auto-fit, minmax(240px, 1fr))">
                  <TextField
                    label={gettext('Type exact module name to confirm removal')}
                    size="small"
                    value={confirmationName}
                    disabled={busy}
                    onChange={(e) => setConfirmationName(e.target.value)}
                  />
                  <Checkbox
                    label={gettext('Acknowledge dependent external routines in catalog')}
                    checked={acknowledgeDependents}
                    disabled={busy}
                    onChange={(v) => setAcknowledgeDependents(Boolean(v))}
                  />
                </Grid>
              )}

              <Stack direction="row" gap="standard" style={{justifyContent: 'flex-end'}}>
                <Button
                  intent={isDeploy ? 'primary' : 'destructive'}
                  disabled={busy || !moduleName.trim()}
                  loading={busy}
                  onClick={handleReview}
                >
                  {gettext('Review Plugin / UDR Operation')}
                </Button>
              </Stack>
            </Stack>
          </Panel>

          {pendingReview && (
            <ReviewConfirmationCard
              review={pendingReview}
              title={gettext('Reviewed Module Operation: %s', pendingReview.operation)}
              previewLabel={gettext('Verified binary & destination plan')}
              previewText={JSON.stringify(pendingReview.payload, null, 2)}
              previewLanguage="json"
              busy={busy}
              onApply={handleApply}
              onDiscard={() => setPendingReview(null)}
            />
          )}

          {lastOutcome && (
            <CodeEditor
              label={gettext('Plugin / UDR operation receipt')}
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

FirebirdPluginDeploymentWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  databaseTargetId: PropTypes.string,
  customPost: PropTypes.func,
};
