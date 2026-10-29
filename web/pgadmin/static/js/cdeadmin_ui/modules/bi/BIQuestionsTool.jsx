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
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {Banner} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import {Dialog} from '../../overlays/Dialog';
import {makePost} from '../../objects/ProviderObjectEditorHost';
import {createBIClient} from './biClient';
import {emptyState, fromQuestion} from './queryState';
import {emptyDashboard, fromDashboard} from './dashboardState';
import {isCollectionId, placementRows} from './collectionTree';
import useBICatalog from './useBICatalog';
import CollectionBrowser from './CollectionBrowser';
import QuestionEditor from './QuestionEditor';
import DashboardWorkspace from './DashboardWorkspace';
import ImportDashboardDialog from './ImportDashboardDialog';

const message = (error) => error?.message || String(error);

/**
 * The "BI questions" tool: collections, saved questions and dashboards on the
 * left, the open question (builder or SQL, result, history) or dashboard
 * (editor and viewer) on the right. It talks to one endpoint's workspace
 * route through the bi_* actions only.
 *
 * Leaving unsaved edits asks first. The question to ask is kept as plain data
 * (an "intent") and carried out by `perform`; no function is ever stored in
 * React state, where a state setter would call it as an updater.
 */
export default function BIQuestionsTool({api, endpointUrl, client: suppliedClient, previewDelay, onDirtyChange}) {
  const client = useMemo(() => suppliedClient || createBIClient(makePost(api, endpointUrl)),
    [suppliedClient, api, endpointUrl]);
  const catalog = useBICatalog(client);
  const [data, setData] = useState({
    status: 'loading', tree: [], questions: [], dashboards: [], shared: {collections: [], questions: [], dashboards: []}});
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(undefined);
  const [search, setSearch] = useState('');
  const [showArchived, setShowArchived] = useState(false);
  const [open, setOpen] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [pending, setPending] = useState(null);
  const [importing, setImporting] = useState(false);
  const sequence = useRef(0);

  const refresh = useCallback(async () => {
    // The questions stay usable when the dashboards cannot be listed.
    let dashboardProblem = '';
    const [tree, questions, dashboards, shared] = await Promise.all([
      client.listCollections(), client.listQuestions(),
      client.listDashboards().catch((caught) => { dashboardProblem = message(caught); return []; }),
      // A server without sharing simply has nothing shared with the caller.
      client.sharedWithMe().catch(() => ({collections: [], questions: [], dashboards: []}))]);
    setData({status: 'ready', tree, questions, dashboards, shared});
    if(dashboardProblem) setError(gettext('Dashboards are unavailable: %s', dashboardProblem));
  }, [client]);

  useEffect(() => {
    refresh().catch((caught) => { setData((current) => ({...current, status: 'error'})); setError(message(caught)); });
  }, [refresh]);

  const changeDirty = useCallback((value) => {
    setDirty(value);
    onDirtyChange?.(value);
  }, [onDirtyChange]);

  const start = useCallback((next) => {
    sequence.current += 1;
    setError('');
    changeDirty(false);
    setOpen({...next, key: `${next.key}-${sequence.current}`});
  }, [changeDirty]);

  const loadQuestion = useCallback(async (questionId) => {
    try {
      const record = await client.getQuestion(questionId);
      start({kind: 'question', key: questionId, questionId, initial: fromQuestion(record)});
    } catch(caught) {
      setError(message(caught));
    }
  }, [client, start]);

  const loadDashboard = useCallback(async (dashboardId, mode) => {
    try {
      const record = await client.getDashboard(dashboardId);
      start({kind: 'dashboard', key: dashboardId, dashboardId, mode, initial: fromDashboard(record)});
    } catch(caught) {
      setError(message(caught));
    }
  }, [client, start]);

  const perform = (intent) => {
    switch(intent.type) {
    case 'openQuestion':
      loadQuestion(intent.questionId);
      break;
    case 'newQuestion':
      start({kind: 'question', key: 'new', questionId: null, initial: emptyState({collectionId: intent.collectionId})});
      break;
    case 'openDashboard':
      loadDashboard(intent.dashboardId, intent.mode);
      break;
    case 'newDashboard':
      start({kind: 'dashboard', key: 'new', dashboardId: null, mode: 'edit',
        initial: emptyDashboard({collectionId: intent.collectionId})});
      break;
    case 'showImported':
      start({kind: 'dashboard', key: 'imported', dashboardId: null, mode: 'edit', loss: intent.loss,
        initial: {...fromDashboard({definition: intent.definition}), collectionId: intent.collectionId, dirty: true}});
      break;
    default:
      setOpen(null);
      changeDirty(false);
    }
  };
  const guarded = (intent) => dirty ? setPending(intent) : perform(intent);

  const collectionOf = () => isCollectionId(selected) ? selected : null;
  const changed = async (questionId) => {
    await refresh();
    if(questionId && open?.kind === 'question' && open.questionId === questionId) await loadQuestion(questionId);
  };
  const changedDashboard = async (dashboardId) => {
    await refresh();
    if(dashboardId && open?.kind === 'dashboard' && open.dashboardId === dashboardId) {
      await loadDashboard(dashboardId, open.mode);
    }
  };
  // Where an item may be filed: own collections plus shared ones the caller can edit.
  const collections = useMemo(() => placementRows(data.tree, data.shared.collections, gettext('Shared with me')),
    [data.tree, data.shared.collections]);
  const openQuestionId = open?.kind === 'question' ? open.questionId || undefined : undefined;
  const openDashboardId = open?.kind === 'dashboard' ? open.dashboardId || undefined : undefined;

  return <Box data-cdeadmin-qa-key="bi.tool" sx={{display: 'grid', gap: 1, p: 1, minWidth: 0,
    gridTemplateColumns: {xs: 'minmax(0, 1fr)', md: 'minmax(250px, 320px) minmax(0, 1fr)'}, alignItems: 'start'}}>
    {error && <Box sx={{gridColumn: '1 / -1'}}>
      <Banner status="error" onClose={() => setError('')}>{error}</Banner>
    </Box>}
    <CollectionBrowser client={client} tree={data.tree} shared={data.shared} questions={data.questions}
      dashboards={data.dashboards}
      selected={selected} onSelect={setSelected} search={search} onSearch={setSearch} showArchived={showArchived}
      onShowArchived={setShowArchived} activeQuestionId={openQuestionId}
      dirtyQuestionId={dirty ? openQuestionId : undefined}
      activeDashboardId={openDashboardId} dirtyDashboardId={dirty ? openDashboardId : undefined}
      onOpen={(question) => guarded({type: 'openQuestion', questionId: question.question_id})}
      onNew={(collectionId) => guarded({type: 'newQuestion', collectionId})}
      onOpenDashboard={(dashboard, mode) => guarded({type: 'openDashboard', dashboardId: dashboard.dashboard_id, mode})}
      onNewDashboard={(collectionId) => guarded({type: 'newDashboard', collectionId})}
      onImportDashboard={() => setImporting(true)}
      onChanged={changed} onChangedDashboard={changedDashboard} onError={setError} />
    {open?.kind === 'dashboard' ?
      <DashboardWorkspace key={open.key} client={client} catalog={catalog} collections={collections}
        questions={data.questions} dashboards={data.dashboards} initial={open.initial}
        initialMode={open.mode} importLoss={open.loss} onDirtyChange={changeDirty}
        onSaved={(record) => {
          setOpen((current) => current ? {...current, dashboardId: record.dashboard_id} : current);
          refresh().catch((caught) => setError(message(caught)));
        }}
        onClose={() => guarded({type: 'close'})} /> :
      open?.kind === 'question' ?
        <QuestionEditor key={open.key} client={client} catalog={catalog} collections={collections}
          initial={open.initial} previewDelay={previewDelay} onDirtyChange={changeDirty}
          onSaved={(record) => {
            setOpen((current) => current ? {...current, questionId: record.question_id} : current);
            refresh().catch((caught) => setError(message(caught)));
          }}
          onClose={() => guarded({type: 'close'})} /> :
        <EmptyState message={data.status === 'loading' ? gettext('Loading questions...') :
          gettext('Open a question or a dashboard, or start a new one.')}
        actionLabel={data.status === 'ready' ? gettext('New question') : undefined}
        onAction={() => guarded({type: 'newQuestion', collectionId: collectionOf()})} />}
    {importing && <ImportDashboardDialog client={client} onClose={() => setImporting(false)}
      onImported={(definition, loss) => {
        setImporting(false);
        guarded({type: 'showImported', definition, loss, collectionId: collectionOf()});
      }} />}
    {pending && <Dialog open title={gettext('Discard unsaved changes?')} onClose={() => setPending(null)}
      actions={<Stack direction="row" gap="compact">
        <Button onClick={() => setPending(null)}>{gettext('Keep editing')}</Button>
        <Button intent="destructive" onClick={() => { const intent = pending; setPending(null); perform(intent); }}>
          {gettext('Discard changes')}
        </Button>
      </Stack>}>
      {open?.kind === 'dashboard' ?
        gettext('The open dashboard has changes that are not saved. They are lost if you continue.') :
        gettext('The open question has changes that are not saved. They are lost if you continue.')}
    </Dialog>}
  </Box>;
}

BIQuestionsTool.propTypes = {
  api: PropTypes.shape({post: PropTypes.func.isRequired}),
  endpointUrl: PropTypes.string,
  client: PropTypes.object,
  previewDelay: PropTypes.number,
  onDirtyChange: PropTypes.func,
};
