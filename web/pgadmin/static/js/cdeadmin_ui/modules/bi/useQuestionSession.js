/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useReducer, useRef, useState} from 'react';
import {
  emptyState, hasSelection, parameterValues, reduce, toQuestion,
} from './queryState';
import {validateState} from './validateState';
import {categoryMap} from './sourceCatalog';
import {appendPage, executionFrom} from './executionModel';

const PAGE_SIZE = 100;
const message = (error) => error?.message || String(error);

/**
 * Everything one open question needs: the builder reducer, the source's
 * columns or model fields, the live SQL preview, running with paging, and
 * the save / save-as / reload calls. Components stay presentational.
 */
export default function useQuestionSession({client, catalog, initial, previewDelay = 350, onSaved, onDirtyChange}) {
  const [state, dispatch] = useReducer(reduce, initial, (value) => value || emptyState());
  const [columns, setColumns] = useState({status: 'idle', items: []});
  const [model, setModel] = useState({status: 'idle', value: null});
  const [preview, setPreview] = useState({status: 'idle'});
  const [run, setRun] = useState({status: 'idle', execution: null, error: ''});
  const [paging, setPaging] = useState(false);
  const latest = useRef(state);
  latest.current = state;

  const relation = state.source.kind === 'table' ? state.source.relation : [];
  const relationKey = relation.join('.');
  const modelId = state.source.kind === 'model' ? state.source.model.id : '';
  const {status: catalogStatus, loadColumns, loadModel} = catalog;

  useEffect(() => {
    if(!relationKey || state.mode !== 'builder') {
      setColumns({status: 'idle', items: []});
      return undefined;
    }
    if(catalogStatus !== 'ready') return undefined;
    let cancelled = false;
    setColumns((current) => ({...current, status: 'loading'}));
    loadColumns(latest.current.source.relation).then((items) => {
      if(cancelled) return;
      setColumns({status: 'ready', items});
      dispatch({type: 'retypeFilters', types: categoryMap(items)});
    }, (error) => { if(!cancelled) setColumns({status: 'error', items: [], error: message(error)}); });
    return () => { cancelled = true; };
  }, [relationKey, state.mode, catalogStatus, loadColumns]);

  useEffect(() => {
    if(!modelId || state.mode !== 'builder') {
      setModel({status: 'idle', value: null});
      return undefined;
    }
    let cancelled = false;
    setModel((current) => ({...current, status: 'loading'}));
    loadModel(modelId).then((value) => {
      if(cancelled) return;
      setModel({status: 'ready', value});
      dispatch({type: 'retypeFilters', types: Object.fromEntries(
        value.dimensions.filter((dimension) => dimension.field).map((dimension) =>
          [dimension.field.field, dimension.category]))});
    }, (error) => { if(!cancelled) setModel({status: 'error', value: null, error: message(error)}); });
    return () => { cancelled = true; };
  }, [modelId, state.mode, loadModel]);

  useEffect(() => { onDirtyChange?.(state.dirty); }, [state.dirty, onDirtyChange]);

  const errors = useMemo(() => validateState(state, {model: model.value}), [state, model.value]);
  const ready = errors.length === 0 && hasSelection(state);
  const questionJson = useMemo(() => JSON.stringify(toQuestion(state)), [state]);
  const valuesJson = useMemo(() => JSON.stringify(parameterValues(state)), [state]);

  useEffect(() => {
    if(!ready) {
      setPreview({status: 'idle'});
      return undefined;
    }
    let cancelled = false;
    setPreview((current) => ({...current, status: 'loading', error: ''}));
    const timer = setTimeout(() => {
      client.compile(JSON.parse(questionJson), JSON.parse(valuesJson)).then(
        (compiled) => { if(!cancelled) setPreview({status: 'ready', compiled}); },
        (error) => { if(!cancelled) setPreview({status: 'error', error: message(error)}); });
    }, previewDelay);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [client, ready, questionJson, valuesJson, previewDelay]);

  const execute = useCallback(async ({fresh = false} = {}) => {
    setRun((current) => ({status: 'running', execution: current.execution, error: ''}));
    try {
      const response = await client.execute(JSON.parse(questionJson), {
        parameters: JSON.parse(valuesJson), pageSize: PAGE_SIZE, bypassCache: fresh});
      setRun({status: 'done', execution: executionFrom(response), error: ''});
    } catch(error) {
      setRun((current) => ({status: 'error', execution: current.execution, error: message(error)}));
    }
  }, [client, questionJson, valuesJson]);

  const loadMore = useCallback(async () => {
    const current = run.execution;
    if(!current?.cursor) return;
    setPaging(true);
    try {
      const response = await client.page(current.resultId, current.cursor, PAGE_SIZE);
      setRun((now) => now.execution ? {...now, execution: appendPage(now.execution, response)} : now);
    } catch(error) {
      setRun((now) => ({...now, error: message(error)}));
    } finally {
      setPaging(false);
    }
  }, [client, run.execution]);

  const saved = useCallback((record) => {
    dispatch({type: 'saved', record});
    onSaved?.(record);
    return record;
  }, [onSaved]);

  /** Save over the stored question: an optimistic revision check on the server. */
  const saveExisting = useCallback(async () => saved(await client.updateQuestion(
    state.questionId, state.revision, toQuestion(state))), [client, saved, state]);

  /** First save, or a copy: always creates a new stored question. */
  const saveNew = useCallback(async ({name, description, collectionId}) => saved(
    await client.createQuestion(toQuestion({...state, name, description, collectionId}))), [client, saved, state]);

  const reload = useCallback(async () => {
    dispatch({type: 'load', record: await client.getQuestion(state.questionId)});
  }, [client, state.questionId]);

  const convertSql = useCallback((sql) => {
    const parameterTypes = Object.fromEntries(state.parameters.map((parameter) => [parameter.id, parameter.type]));
    return client.convertSql(sql, {name: state.name.trim() || undefined, parameterTypes, collectionId: state.collectionId});
  }, [client, state.name, state.parameters, state.collectionId]);

  return {
    state, dispatch, errors, ready,
    columns, model, preview, run, paging,
    execute, loadMore, saveExisting, saveNew, reload, convertSql,
  };
}
