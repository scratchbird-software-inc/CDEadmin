/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useReducer, useState} from 'react';
import {emptyModel, validateDraft} from './modelDraft';
import {definitionOf, initialSession, reduce} from './modelSession';

const message = (error) => error?.message || String(error);

/**
 * The list of models, the open model and every lifecycle call on it. Each
 * call reports its failure through `error` and never throws into the view.
 */
export default function useModelSession(client, {onDirtyChange} = {}) {
  const [state, dispatch] = useReducer(reduce, undefined, initialSession);
  const [list, setList] = useState({status: 'loading', items: []});
  const [catalog, setCatalog] = useState({status: 'loading', capabilities: {}, delivery: {profiles: []},
    scheduler: {}, delegations: []});
  const [resources, setResources] = useState([]);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  const profile = catalog.capabilities?.analytical_profile || {};

  const refreshList = useCallback(async () => {
    const items = await client.list();
    setList({status: 'ready', items});
    return items;
  }, [client]);

  useEffect(() => {
    let cancelled = false;
    client.list().then(
      (items) => { if(!cancelled) setList({status: 'ready', items}); },
      (caught) => { if(!cancelled) { setList({status: 'error', items: []}); setError(message(caught)); } });
    client.catalog().then(
      (value) => { if(!cancelled) setCatalog({status: 'ready', ...value}); },
      (caught) => {
        if(!cancelled) { setCatalog((current) => ({...current, status: 'error'})); setError(message(caught)); }
      });
    // the discovered tables are optional: a model can name its sources by hand
    client.listResources().then(
      (items) => { if(!cancelled) setResources(items); }, () => {});
    return () => { cancelled = true; };
  }, [client]);

  useEffect(() => { onDirtyChange?.(state.dirty); }, [state.dirty, onDirtyChange]);

  const run = useCallback(async (key, work) => {
    setBusy(key);
    setError('');
    try {
      return await work();
    } catch(caught) {
      setError(message(caught));
      return undefined;
    } finally {
      setBusy('');
    }
  }, []);

  const open = useCallback((modelId) => run('open', async () => {
    dispatch({type: 'load', record: await client.get(modelId)});
    return true;
  }), [client, run]);

  const startNew = useCallback(() => {
    setError('');
    dispatch({type: 'new', definition: emptyModel(resources, profile)});
  }, [resources, profile]);

  const edit = useCallback((field, value) => dispatch({type: 'edit', field, value}), []);
  const replaceDefinition = useCallback((definition) => dispatch({type: 'definition', definition}), []);
  const addSource = useCallback((resource) => dispatch({type: 'addSource', resource, profile}), [profile]);

  const built = useMemo(() => definitionOf(state), [state]);
  const issues = useMemo(() => state.draft ? validateDraft(state.draft) : {}, [state.draft]);

  const validate = useCallback(() => run('validate', async () => {
    if(built.problems.length) {
      dispatch({type: 'validated', result: {valid: false, errors: built.problems.map((text) => ({message: text}))}});
      return false;
    }
    const result = await client.validate(built.definition);
    dispatch({type: 'validated', result});
    return result.valid;
  }), [client, run, built]);

  const save = useCallback(() => run('save', async () => {
    if(built.problems.length || Object.keys(issues).length) {
      setError([...built.problems, ...Object.values(issues)].join(' '));
      return false;
    }
    const stored = state.record ?
      await client.update(state.record.model_id, state.record.revision, built.definition) :
      await client.create(built.definition);
    dispatch({type: 'load', record: stored});
    await refreshList();
    return true;
  }), [client, run, built, issues, state.record, refreshList]);

  const setStatus = useCallback((status) => run('status', async () => {
    const stored = await client.setStatus(state.record.model_id, state.record.revision, status);
    dispatch({type: 'status', record: stored});
    await refreshList();
    return true;
  }), [client, run, state.record, refreshList]);

  const clone = useCallback((name) => run('clone', async () => {
    const stored = await client.clone(state.record.model_id, name);
    dispatch({type: 'load', record: stored});
    await refreshList();
    return true;
  }), [client, run, state.record, refreshList]);

  const remove = useCallback(() => run('remove', async () => {
    await client.remove(state.record.model_id, state.record.revision);
    dispatch({type: 'new', definition: emptyModel(resources, profile)});
    await refreshList();
    return true;
  }), [client, run, state.record, refreshList, resources, profile]);

  const refreshLineage = useCallback(() => run('lineage', async () => {
    dispatch({type: 'lineage', lineage: await client.lineage(built.definition)});
    return true;
  }), [client, run, built]);

  return {
    state, dispatch, list, catalog, profile, resources, busy, error, setError, issues, built,
    refreshList, open, startNew, edit, replaceDefinition, addSource, validate, save, setStatus, clone, remove,
    refreshLineage, readOnly: state.record?.status === 'published',
  };
}
