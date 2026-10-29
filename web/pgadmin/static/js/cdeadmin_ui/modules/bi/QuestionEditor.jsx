/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {TextField} from '../../primitives/Field';
import {Badge, Banner} from '../../feedback/Indicators';
import {Tab} from '../../navigation/TabsAndBreadcrumbs';
import {errorAt} from './validateState';
import useQuestionSession from './useQuestionSession';
import BuilderPanel from './BuilderPanel';
import SqlPanel, {RedactedSql} from './SqlPanel';
import SqlPreview from './SqlPreview';
import ResultPane from './ResultPane';
import ParametersPanel from './ParametersPanel';
import RevisionHistory from './RevisionHistory';
import {SaveDialog} from './Dialogs';
import ShareDialog from './ShareDialog';
import AlertsPanel from './AlertsPanel';
import EmbedDialog from './EmbedDialog';
import {permissions} from './sharing';

/** The parameter values typed so far, as the text the alert form edits. */
const filled = (values) => Object.fromEntries(
  Object.entries(values || {}).filter(([, text]) => String(text ?? '').trim() !== ''));

const OUTPUT_TABS = ['result', 'sql', 'parameters'];

function outputLabel(id) {
  if(id === 'result') return gettext('Result');
  if(id === 'sql') return gettext('SQL preview');
  return gettext('Parameters');
}

function Tabs({label, ids, labelOf, active, onChange}) {
  return <Box role="tablist" aria-label={label} sx={{display: 'flex', borderBottom: '1px solid', borderColor: 'divider'}}>
    {ids.map((id) => <Tab key={id} label={labelOf(id)} active={active === id} onActivate={() => onChange(id)} />)}
  </Box>;
}

Tabs.propTypes = {
  label: PropTypes.string.isRequired, ids: PropTypes.array.isRequired, labelOf: PropTypes.func.isRequired,
  active: PropTypes.string.isRequired, onChange: PropTypes.func.isRequired,
};

/**
 * One open question: builder or SQL on the left, result / compiled SQL /
 * parameters on the right, with run, save, save as and revision history.
 */
export default function QuestionEditor({client, catalog, collections, initial, previewDelay, onSaved, onClose, onDirtyChange}) {
  const session = useQuestionSession({client, catalog, initial, previewDelay, onSaved, onDirtyChange});
  const {state, dispatch, errors, ready, columns, model, preview, run, paging} = session;
  const [output, setOutput] = useState('result');
  const [dialog, setDialog] = useState(null);
  const [notice, setNotice] = useState(null);
  const [saving, setSaving] = useState(false);
  const [showAlerts, setShowAlerts] = useState(false);

  const stored = state.questionId !== null;
  const perms = permissions({access: state.access, is_owner: state.isOwner});
  // Sharing grants view/edit/manage; below edit the question is read-only. A new draft is always yours.
  const readOnly = stored && perms.readOnly;
  const conflict = notice?.status === 'error' && /revision has changed/.test(notice.text);

  const save = async () => {
    if(!stored) { setDialog('save'); return; }
    setSaving(true);
    setNotice(null);
    try {
      const record = await session.saveExisting();
      setNotice({status: 'success', text: gettext('Saved as revision %s.', record.revision)});
    } catch(error) {
      setNotice({status: 'error', text: error?.message || String(error)});
    } finally {
      setSaving(false);
    }
  };
  const reload = async () => {
    try {
      await session.reload();
      setNotice({status: 'info', text: gettext('Loaded the latest saved revision.')});
    } catch(error) {
      setNotice({status: 'error', text: error?.message || String(error)});
    }
  };
  const confirmNew = async (values) => {
    const record = await session.saveNew(values);
    setNotice({status: 'success', text: gettext('Saved %s.', record.definition.name)});
  };
  const switchMode = (mode) => {
    if(mode === state.mode) return;
    // Start the SQL editor from what the builder compiles to.
    if(mode === 'sql' && !state.sql.trim() && preview.compiled?.source) {
      dispatch({type: 'setSql', sql: String(preview.compiled.source)});
    }
    dispatch({type: 'setMode', mode});
  };
  const runQuestion = (fresh) => {
    setOutput('result');
    session.execute({fresh});
  };

  return <Box data-cdeadmin-qa-key="bi.editor" sx={{display: 'grid', gap: 1, minWidth: 0, p: 1}}>
    <Stack direction="row" gap="comfortable" sx={{alignItems: 'center', flexWrap: 'wrap'}}>
      <TextField size="small" label={gettext('Question name')} value={state.name} disabled={readOnly}
        placeholder={gettext('Untitled question')}
        onChange={(event) => dispatch({type: 'rename', name: event.target.value})} sx={{minWidth: 260, flex: 1}} />
      {stored && <Badge status="neutral" label={gettext('Revision %s', state.revision)} />}
      {state.status === 'archived' && <Badge status="warning" label={gettext('Archived')} />}
      {stored && !state.isOwner && <Badge status="neutral" label={perms.canEdit ?
        gettext('Shared with you: can edit') : gettext('Shared with you: view only')} />}
      {state.dirty && <Badge status="warning" label={gettext('Unsaved changes')} />}
    </Stack>
    <Stack direction="row" gap="compact" sx={{alignItems: 'center', flexWrap: 'wrap'}}>
      <Box role="tablist" aria-label={gettext('Query mode')} sx={{display: 'flex'}}>
        <Tab label={gettext('Builder')} active={state.mode === 'builder'} disabled={readOnly}
          onActivate={() => switchMode('builder')} />
        <Tab label={gettext('SQL')} active={state.mode === 'sql'} disabled={readOnly}
          onActivate={() => switchMode('sql')} />
      </Box>
      <Box sx={{flex: 1}} />
      <Button intent="primary" loading={run.status === 'running'} disabled={!ready}
        onClick={() => runQuestion(false)}>{gettext('Run')}</Button>
      <Button disabled={!ready || !run.execution} onClick={() => runQuestion(true)}>{gettext('Refresh')}</Button>
      {!readOnly && <Button loading={saving} disabled={!ready || (stored && !state.dirty)} onClick={save}>
        {gettext('Save')}</Button>}
      <Button disabled={!ready || state.sqlRedacted} onClick={() => setDialog('saveAs')}
        title={state.sqlRedacted ? gettext('A copy needs edit access to the SQL.') : undefined}>
        {gettext('Save as...')}</Button>
      <Button disabled={!stored} onClick={() => setDialog('history')}>{gettext('History')}</Button>
      {stored && perms.canShare && <Button onClick={() => setDialog('share')}>{gettext('Share...')}</Button>}
      {stored && <Button aria-pressed={showAlerts} onClick={() => setShowAlerts(!showAlerts)}>
        {gettext('Alerts...')}</Button>}
      {stored && perms.canShare && <Button onClick={() => setDialog('embed')}>{gettext('Embed...')}</Button>}
      <Button onClick={onClose}>{gettext('Close')}</Button>
    </Stack>
    {readOnly && <Banner status="info">
      {state.sqlRedacted ?
        gettext('Read only: you can run this question but not change it, and its SQL is hidden.') :
        gettext('Read only: you can run this question but not change it. Save as... makes a copy you own.')}
    </Banner>}
    {notice && <Banner status={notice.status} onClose={() => setNotice(null)}>
      {notice.text}
      {conflict && <Button size="small" onClick={reload}>{gettext('Reload latest')}</Button>}
    </Banner>}
    <Box sx={{display: 'grid', gap: 1, alignItems: 'start',
      gridTemplateColumns: {xs: 'minmax(0, 1fr)', lg: 'minmax(340px, 0.9fr) minmax(0, 1.4fr)'}}}>
      {state.sqlRedacted ? <RedactedSql /> : state.mode === 'builder' ?
        <Box component="fieldset" disabled={readOnly}
          sx={{border: 0, m: 0, p: 0, minWidth: 0, opacity: readOnly ? 0.85 : 1}}>
          <BuilderPanel state={state} dispatch={dispatch} catalog={catalog} columns={columns.items}
            columnsLoading={columns.status === 'loading'} model={model.value}
            modelLoading={model.status === 'loading'} errors={errors} />
        </Box> :
        <SqlPanel sql={state.sql} error={errorAt(errors, 'sql')} readOnly={readOnly}
          onChange={(sql) => dispatch({type: 'setSql', sql})}
          onConvert={session.convertSql}
          onSwitch={(question) => dispatch({type: 'convert', question})} />}
      <Box sx={{display: 'grid', gap: 1, minWidth: 0}}>
        <Tabs label={gettext('Question output')} ids={OUTPUT_TABS} labelOf={outputLabel} active={output} onChange={setOutput} />
        <Box role="tabpanel" aria-label={outputLabel(output)} sx={{minWidth: 0}}>
          {output === 'result' && <ResultPane execution={run.execution} running={run.status === 'running'}
            error={run.error} visualization={state.visualization} loadingMore={paging}
            onVisualization={(visualization) => dispatch({type: 'setVisualization', visualization})}
            onLoadMore={session.loadMore} />}
          {output === 'sql' && <SqlPreview preview={preview} redacted={state.sqlRedacted} />}
          {output === 'parameters' && <ParametersPanel parameters={state.parameters} values={state.values}
            sql={state.mode === 'sql' ? state.sql : ''} errors={errors} dispatch={dispatch} />}
        </Box>
      </Box>
    </Box>
    {stored && showAlerts && <AlertsPanel client={client} resourceType="question" resourceId={state.questionId}
      resourceName={state.name} access={perms.access} parameters={state.parameters}
      seedValues={filled(state.values)} columns={(run.execution?.table?.columns || []).map((column) => column.name)}
      onClose={() => setShowAlerts(false)} />}
    {(dialog === 'save' || dialog === 'saveAs') &&
      <SaveDialog open title={dialog === 'save' ? gettext('Save question') : gettext('Save a copy')}
        confirmLabel={dialog === 'save' ? gettext('Save') : gettext('Save copy')}
        initial={{name: dialog === 'saveAs' && state.name ? gettext('Copy of %s', state.name) : state.name,
          description: state.description, collectionId: state.collectionId}}
        collections={collections} onConfirm={confirmNew} onClose={() => setDialog(null)} />}
    {dialog === 'history' && stored &&
      <RevisionHistory client={client} questionId={state.questionId} currentRevision={state.revision}
        canRestore={!readOnly} canPreviewSql={!state.sqlRedacted}
        onRestore={(definition) => {
          dispatch({type: 'restore', definition});
          setNotice({status: 'info', text: gettext('Revision loaded as a draft. Save to append it as a new revision.')});
        }}
        onClose={() => setDialog(null)} />}
    {dialog === 'embed' && stored &&
      <EmbedDialog client={client} resourceType="question" resourceId={state.questionId}
        resourceName={state.name} access={perms.access} parameters={state.parameters}
        rawSql={state.mode === 'sql'} onClose={() => setDialog(null)} />}
    {dialog === 'share' && stored &&
      <ShareDialog client={client} resourceType="question" resourceId={state.questionId}
        resourceName={state.name} hasCollection={state.collectionId !== null}
        onChanged={() => onSaved?.({question_id: state.questionId})}
        onClose={(result) => {
          setDialog(null);
          if(result?.transferred) {
            reload().catch(() => { /* the list refresh tells the user */ });
          }
        }} />}
  </Box>;
}

QuestionEditor.propTypes = {
  client: PropTypes.object.isRequired,
  catalog: PropTypes.object.isRequired,
  collections: PropTypes.array.isRequired,
  initial: PropTypes.object,
  previewDelay: PropTypes.number,
  onSaved: PropTypes.func,
  onClose: PropTypes.func.isRequired,
  onDirtyChange: PropTypes.func,
};
