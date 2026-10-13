import {useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button} from '@mui/material';
import pgAdmin from 'sources/pgadmin';
import url_for from 'sources/url_for';
import getApiInstance from '../api_instance';
import {LAYOUT_EVENTS} from '../helpers/Layout';
import {DDNDesignerSurface} from '../cdeadmin_ui/integrations/ddn';
import {loadDDNLibraries} from '../cdeadmin_ui/integrations/ddn/library';
import {validatePublication} from '../cdeadmin_ui/integrations/ddn/dashboardPublication.mjs';
import {firebirdDashboardFiles, firebirdFleetFiles} from '../cdeadmin_ui/integrations/ddn/firebirdDashboard';
import {mysqlDashboardFiles, mysqlFleetFiles} from '../cdeadmin_ui/integrations/ddn/mysqlDashboard';
import FormReference from '../cdeadmin_ui/navigation/FormReference';

export default function FirebirdDashboardEditor({serverId, targetId, panelId, engine='firebird'}) {
  const [definition, setDefinition] = useState(null);
  const [error, setError] = useState('');
  const [sourceVersion, setSourceVersion] = useState(0);
  const [publicationVersion, setPublicationVersion] = useState(0);
  const [publishing, setPublishing] = useState(false);
  const [ready, setReady] = useState(false);
  const controller = useRef(null);
  const saving = useRef(false);
  const endpoint = useMemo(() => {
    const params = new URLSearchParams();
    if(serverId != null) params.set('sid', serverId);
    if(targetId) params.set('target_id', targetId);
    return url_for(engine === 'firebird' ? 'cdeadmin_monitoring.definition' : `cdeadmin_${engine}_monitoring.definition`) + (params.size ? `?${params}` : '');
  }, [serverId, targetId, engine]);
  useEffect(() => {
    let active = true;
    getApiInstance().get(endpoint).then(async ({data}) => {
      if(['mysql', 'mariadb'].includes(engine) && !data.data.snapshot) {
        const monitor = serverId == null ? url_for(`cdeadmin_${engine}_monitoring.fleet`) :
          url_for(`cdeadmin_${engine}_monitoring.monitoring`, {sid: serverId}) +
          (targetId ? `?target_id=${encodeURIComponent(targetId)}` : '');
        const current = (await getApiInstance().get(monitor)).data.data;
        const scope = serverId == null ? 'engine' : targetId ? 'database' : 'server';
        const files = serverId == null ? mysqlFleetFiles(current, engine) : mysqlDashboardFiles(current, scope, engine);
        const {viewer} = await loadDDNLibraries();
        // Discover binding identities, but never persist sampled telemetry in a draft.
        data = {...data, data: {...data.data, snapshot: validatePublication(viewer,
          {format: 'ddn-workspace@1', files, entry: 'dashboard.ddn', view: 'dashboard'}, scope, engine)}};
      }
      if(active) {
        setDefinition(data.data);
        setSourceVersion(data.data.assetRef.assetVersion);
        setPublicationVersion(data.data.publication_version || 0);
      }
    }).catch((err) => {
      if(active) setError(err.response?.data?.errormsg || 'Dashboard draft is unavailable.');
    });
    return () => { active = false; };
  }, [endpoint, engine, serverId, targetId]);
  useEffect(() => {
    const workspace = pgAdmin.Browser.docker.default_workspace;
    const dirty = () => {
      try { return Boolean(controller.current?.isDirty()); }
      catch { return true; } // An unapplied source draft must not be lost.
    };
    const unload = (event) => {
      if(dirty()) { event.preventDefault(); event.returnValue = ''; }
    };
    const remove = workspace.eventBus.registerListener(LAYOUT_EVENTS.CLOSING, (id) => {
      if(id !== panelId) return;
      if(saving.current) {
        pgAdmin.Browser.notifier.alert('Saving dashboard draft', 'Wait for the save to finish before closing.');
        return;
      }
      if(!dirty()) return workspace.close(panelId, true);
      pgAdmin.Browser.notifier.confirm('Unsaved dashboard draft',
        'Discard the unsaved dashboard changes?', () => workspace.close(panelId, true), () => true);
    });
    window.addEventListener('beforeunload', unload);
    return () => { remove(); window.removeEventListener('beforeunload', unload); };
  }, [panelId]);
  const snapshot = useMemo(() => definition?.snapshot || {
    format: 'ddn-workspace@1', entry: 'dashboard.ddn', view: 'dashboard',
    files: ['mysql', 'mariadb'].includes(engine) ? (serverId == null ? mysqlFleetFiles(null, engine) : mysqlDashboardFiles(null, targetId ? 'database' : 'server', engine)) :
      serverId == null ? firebirdFleetFiles(null) : firebirdDashboardFiles(null,
        'Firebird dashboard draft', targetId ? 'database' : 'server'),
  }, [definition, serverId, targetId, engine]);
  const save = async (payload) => {
    if(saving.current) throw new Error('Wait for the current save or publication to finish.');
    saving.current = true;
    try {
      const response = await getApiInstance().put(endpoint, payload);
      setSourceVersion(response.data.data.assetRef.assetVersion);
      return response.data.data;
    } catch(err) {
      const failure = new Error(err.response?.data?.errormsg || 'Dashboard draft save failed.');
      failure.code = err.response?.data?.code;
      throw failure;
    } finally { saving.current = false; }
  };
  const publish = async () => {
    let acquired = false;
    try {
      if(saving.current || controller.current.isDirty()) throw new Error('Save the current draft before publishing.');
      setPublishing(true); saving.current = true; acquired = true; setError('');
      const response = await getApiInstance().post(endpoint, {
        source_version: sourceVersion, expected_version: publicationVersion,
      });
      setPublicationVersion(response.data.data.version);
    } catch(err) {
      setError(err.response?.data?.errormsg || err.message || 'Dashboard publication failed.');
    } finally { if(acquired) { setPublishing(false); saving.current = false; } }
  };
  const exportSVG = (svg) => {
    const url = URL.createObjectURL(new Blob([svg], {type: 'image/svg+xml'}));
    const link = document.createElement('a');
    link.href = url; link.download = `${engine}-dashboard-draft.svg`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <Box sx={{height: '100%', display: 'flex', flexDirection: 'column'}}>
    <FormReference formKey={`${engine}-dashboard-editor`} />
    <Alert severity="info">Saving preserves a draft. Publish a saved revision to use its layout in the read-only dashboard. Metric values come from authorized collectors; publishing does not change collection.</Alert>
    <Box><Button disabled={!ready || !sourceVersion || publishing} onClick={publish}>Publish saved revision</Button>
      <span>{publicationVersion ? `Published revision ${publicationVersion}` : 'Standard dashboard is active'}</span></Box>
    {error && <Alert severity="error">{error}</Alert>}
    {definition && <DDNDesignerSurface snapshot={snapshot} assetRef={definition.assetRef}
      saveAsset={save} onExport={exportSVG} onReady={(value) => { controller.current = value; setReady(true); }} />}
  </Box>;
}
FirebirdDashboardEditor.propTypes = {engine: PropTypes.oneOf(['firebird', 'mysql', 'mariadb']), serverId: PropTypes.number,
  targetId: PropTypes.string, panelId: PropTypes.string.isRequired};
