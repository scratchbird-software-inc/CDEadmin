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
import {flattenCollections} from './collectionTree';
import useBICatalog from './useBICatalog';
import CollectionBrowser from './CollectionBrowser';
import QuestionEditor from './QuestionEditor';

const message = (error) => error?.message || String(error);

/**
 * The "BI questions" tool: collections and saved questions on the left, the
 * open question (builder or SQL, result, history) on the right. It talks to
 * one endpoint's workspace route through the bi_* actions only.
 */
export default function BIQuestionsTool({api, endpointUrl, client: suppliedClient, previewDelay, onDirtyChange}) {
  const client = useMemo(() => suppliedClient || createBIClient(makePost(api, endpointUrl)),
    [suppliedClient, api, endpointUrl]);
  const catalog = useBICatalog(client);
  const [data, setData] = useState({status: 'loading', tree: [], questions: []});
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(undefined);
  const [search, setSearch] = useState('');
  const [showArchived, setShowArchived] = useState(false);
  const [open, setOpen] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [pending, setPending] = useState(null);
  const sequence = useRef(0);

  const refresh = useCallback(async () => {
    const [tree, questions] = await Promise.all([client.listCollections(), client.listQuestions()]);
    setData({status: 'ready', tree, questions});
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

  const load = useCallback(async (questionId) => {
    try {
      const record = await client.getQuestion(questionId);
      start({key: questionId, questionId, initial: fromQuestion(record)});
    } catch(caught) {
      setError(message(caught));
    }
  }, [client, start]);

  // Leaving unsaved edits asks first; everything else opens at once.
  // setPending takes a function as an updater, so the action is wrapped to be stored as a value.
  const guarded = (action) => dirty ? setPending(() => action) : action();
  const openQuestion = (question) => guarded(() => load(question.question_id));
  const newQuestion = (collectionId) => guarded(() => start({
    key: 'new', questionId: null, initial: emptyState({collectionId})}));

  const changed = async (questionId) => {
    await refresh();
    if(questionId && open?.questionId === questionId) await load(questionId);
  };
  const collections = useMemo(() => flattenCollections(data.tree), [data.tree]);

  return <Box data-cdeadmin-qa-key="bi.tool" sx={{display: 'grid', gap: 1, p: 1, minWidth: 0,
    gridTemplateColumns: {xs: 'minmax(0, 1fr)', md: 'minmax(250px, 320px) minmax(0, 1fr)'}, alignItems: 'start'}}>
    {error && <Box sx={{gridColumn: '1 / -1'}}>
      <Banner status="error" onClose={() => setError('')}>{error}</Banner>
    </Box>}
    <CollectionBrowser client={client} tree={data.tree} questions={data.questions} selected={selected}
      onSelect={setSelected} search={search} onSearch={setSearch} showArchived={showArchived}
      onShowArchived={setShowArchived} activeQuestionId={open?.questionId || undefined}
      dirtyQuestionId={dirty ? open?.questionId || undefined : undefined}
      onOpen={openQuestion} onNew={newQuestion} onChanged={changed} onError={setError} />
    {open ?
      <QuestionEditor key={open.key} client={client} catalog={catalog} collections={collections}
        initial={open.initial} previewDelay={previewDelay} onDirtyChange={changeDirty}
        onSaved={(record) => {
          setOpen((current) => current ? {...current, questionId: record.question_id} : current);
          refresh().catch((caught) => setError(message(caught)));
        }}
        onClose={() => guarded(() => { setOpen(null); changeDirty(false); })} /> :
      <EmptyState message={data.status === 'loading' ? gettext('Loading questions...') :
        gettext('Open a question, or start a new one from a table or semantic model.')}
      actionLabel={data.status === 'ready' ? gettext('New question') : undefined}
      onAction={() => newQuestion(typeof selected === 'string' ? selected : null)} />}
    {pending && <Dialog open title={gettext('Discard unsaved changes?')} onClose={() => setPending(null)}
      actions={<Stack direction="row" gap="compact">
        <Button onClick={() => setPending(null)}>{gettext('Keep editing')}</Button>
        <Button intent="destructive" onClick={() => { const action = pending; setPending(null); action(); }}>
          {gettext('Discard changes')}
        </Button>
      </Stack>}>
      {gettext('The open question has changes that are not saved. They are lost if you continue.')}
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
