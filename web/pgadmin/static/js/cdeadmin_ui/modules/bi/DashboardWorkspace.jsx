/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useReducer, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {TextField} from '../../primitives/Field';
import {Badge, Banner} from '../../feedback/Indicators';
import {Tab} from '../../navigation/TabsAndBreadcrumbs';
import {SaveDialog} from './Dialogs';
import ShareDialog from './ShareDialog';
import {permissions} from './sharing';
import {lossLines} from './dashboardImport';
import {reduce, toDashboard} from './dashboardState';
import DashboardEditor from './DashboardEditor';
import DashboardViewer from './DashboardViewer';
import DashboardHistory from './DashboardHistory';

/**
 * One open dashboard: the editor and the viewer share this draft and its
 * save / save as / history controls. The draft lives here, in a reducer, so
 * switching to the viewer never loses edits (the viewer shows the saved
 * revision), and the host is told when it is dirty so leaving can be guarded.
 */
export default function DashboardWorkspace({
  client, catalog, collections, questions, dashboards, initial, initialMode = 'edit', importLoss,
  onSaved, onClose, onDirtyChange,
}) {
  const [state, dispatch] = useReducer(reduce, initial);
  const [mode, setMode] = useState(initialMode);
  const [dialog, setDialog] = useState(null);
  const [notice, setNotice] = useState(null);
  const [saving, setSaving] = useState(false);
  const [report, setReport] = useState(importLoss ? lossLines(importLoss) : null);

  const stored = state.dashboardId !== null;
  const perms = permissions({access: state.access, is_owner: state.isOwner});
  // Below edit access a dashboard is for viewing only; a new draft is always yours.
  const readOnly = stored && perms.readOnly;
  useEffect(() => { onDirtyChange?.(state.dirty); }, [state.dirty, onDirtyChange]);

  const conflict = notice?.status === 'error' && /revision has changed/.test(notice.text);
  const fail = (error) => setNotice({status: 'error', text: error?.message || String(error)});

  const save = async () => {
    if(!stored) { setDialog('save'); return; }
    const sent = toDashboard(state);
    setSaving(true);
    setNotice(null);
    try {
      const record = await client.updateDashboard(state.dashboardId, state.revision, sent);
      dispatch({type: 'saved', record, sent});
      onSaved?.(record);
      setNotice({status: 'success', text: gettext('Saved as revision %s.', record.revision)});
    } catch(error) {
      fail(error);
    } finally {
      setSaving(false);
    }
  };
  const confirmNew = async ({name, description, collectionId}) => {
    const record = await client.createDashboard({
      ...toDashboard(state), name, description, collection_id: collectionId});
    dispatch({type: 'saved', record});
    onSaved?.(record);
    setNotice({status: 'success', text: gettext('Saved %s.', record.definition.name)});
  };
  const reload = async () => {
    try {
      dispatch({type: 'load', record: await client.getDashboard(state.dashboardId)});
      setNotice({status: 'info', text: gettext('Loaded the latest saved revision.')});
    } catch(error) {
      fail(error);
    }
  };
  const choose = (next) => {
    if(next === 'view' && !stored) return;
    if(next === 'edit' && readOnly) return;
    setMode(next);
  };

  return <Box data-cdeadmin-qa-key="bi.dashboard.workspace" sx={{display: 'grid', gap: 1, minWidth: 0, p: 1}}>
    <Stack direction="row" gap="comfortable" sx={{alignItems: 'center', flexWrap: 'wrap'}}>
      {mode === 'edit' && !readOnly ?
        <TextField size="small" label={gettext('Dashboard name')} value={state.name}
          placeholder={gettext('Untitled dashboard')}
          onChange={(event) => dispatch({type: 'rename', name: event.target.value})} sx={{minWidth: 260, flex: 1}} /> :
        <Box component="span" sx={{flex: 1}} />}
      {stored && <Badge status="neutral" label={gettext('Revision %s', state.revision)} />}
      {state.status === 'archived' && <Badge status="warning" label={gettext('Archived')} />}
      {stored && !state.isOwner && <Badge status="neutral" label={perms.canEdit ?
        gettext('Shared with you: can edit') : gettext('Shared with you: view only')} />}
      {state.dirty && <Badge status="warning" label={gettext('Unsaved changes')} />}
    </Stack>
    <Stack direction="row" gap="compact" sx={{alignItems: 'center', flexWrap: 'wrap'}}>
      <Box role="tablist" aria-label={gettext('Dashboard mode')} sx={{display: 'flex'}}>
        <Tab label={gettext('Edit')} active={mode === 'edit' && !readOnly} disabled={readOnly}
          onActivate={() => choose('edit')} />
        <Tab label={gettext('View')} active={mode === 'view' || readOnly} disabled={!stored}
          onActivate={() => choose('view')} />
      </Box>
      <Box sx={{flex: 1}} />
      {!readOnly && <Button intent="primary" loading={saving} disabled={!state.name.trim() || (stored && !state.dirty)}
        onClick={save}>{gettext('Save')}</Button>}
      <Button onClick={() => setDialog('saveAs')}>{gettext('Save as...')}</Button>
      <Button disabled={!stored} onClick={() => setDialog('history')}>{gettext('History')}</Button>
      {stored && perms.canShare && <Button onClick={() => setDialog('share')}>{gettext('Share...')}</Button>}
      <Button onClick={onClose}>{gettext('Close')}</Button>
    </Stack>
    {readOnly && <Banner status="info">
      {gettext('Read only: you can view this dashboard but not change it. Cards run with your own access, ' +
        'so a card whose question is not shared with you shows no data.')}
    </Banner>}
    {notice && <Banner status={notice.status} onClose={() => setNotice(null)}>
      {notice.text}
      {conflict && <Button size="small" onClick={reload}>{gettext('Reload latest')}</Button>}
    </Banner>}
    {report && <Banner status={report.length ? 'warning' : 'info'} onClose={() => setReport(null)}>
      {report.length ?
        gettext('Imported from a monitoring dashboard. The conversion could not represent:') :
        gettext('Imported from a monitoring dashboard without loss. It is not stored until you save it.')}
      {report.length > 0 && <Box component="ul" sx={{m: 0, pl: 2}}>
        {report.map((line, index) => <li key={index}>{line.text}</li>)}</Box>}
    </Banner>}
    {mode === 'view' && state.dirty && <Banner status="info">
      {gettext('Showing saved revision %s. Your unsaved edits are kept in the editor.', state.revision)}
    </Banner>}
    {mode === 'edit' && !readOnly ?
      <DashboardEditor client={client} catalog={catalog} state={state} dispatch={dispatch}
        questions={questions} dashboards={dashboards.filter((item) => item.dashboard_id !== state.dashboardId)}
        collections={collections} /> :
      <DashboardViewer key={state.revision} client={client} dashboardId={state.dashboardId} name={state.name} />}
    {(dialog === 'save' || dialog === 'saveAs') &&
      <SaveDialog open title={dialog === 'save' ? gettext('Save dashboard') : gettext('Save a copy')}
        confirmLabel={dialog === 'save' ? gettext('Save') : gettext('Save copy')}
        nameLabel={gettext('Dashboard name')}
        initial={{name: dialog === 'saveAs' && state.name ? gettext('Copy of %s', state.name) : state.name,
          description: state.description, collectionId: state.collectionId}}
        collections={collections} onConfirm={confirmNew} onClose={() => setDialog(null)} />}
    {dialog === 'history' && stored &&
      <DashboardHistory client={client} dashboardId={state.dashboardId} currentRevision={state.revision}
        canRestore={!readOnly}
        onRestore={(definition) => {
          dispatch({type: 'restore', definition});
          setMode('edit');
          setNotice({status: 'info', text: gettext('Revision loaded as a draft. Save to append it as a new revision.')});
        }}
        onClose={() => setDialog(null)} />}
    {dialog === 'share' && stored &&
      <ShareDialog client={client} resourceType="dashboard" resourceId={state.dashboardId}
        resourceName={state.name} hasCollection={state.collectionId !== null}
        onChanged={() => onSaved?.({dashboard_id: state.dashboardId})}
        onClose={(result) => {
          setDialog(null);
          if(result?.transferred) reload();
        }} />}
  </Box>;
}

DashboardWorkspace.propTypes = {
  client: PropTypes.object.isRequired,
  catalog: PropTypes.object,
  collections: PropTypes.array.isRequired,
  questions: PropTypes.array.isRequired,
  dashboards: PropTypes.array.isRequired,
  initial: PropTypes.object.isRequired,
  initialMode: PropTypes.oneOf(['edit', 'view']),
  importLoss: PropTypes.array,
  onSaved: PropTypes.func,
  onClose: PropTypes.func.isRequired,
  onDirtyChange: PropTypes.func,
};
