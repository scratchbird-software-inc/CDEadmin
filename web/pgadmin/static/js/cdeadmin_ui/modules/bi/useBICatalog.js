/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {modelFields, sourceColumns, tableSources} from './sourceCatalog';

const message = (error) => error?.message || String(error);

/**
 * Load the endpoint's catalog tables and semantic models once, and resolve a
 * source's columns or a model's fields on demand (cached per source).
 */
export default function useBICatalog(client) {
  const [state, setState] = useState({status: 'loading', resources: [], models: [], error: ''});
  const columnCache = useRef(new Map());
  const modelCache = useRef(new Map());

  useEffect(() => {
    let cancelled = false;
    setState({status: 'loading', resources: [], models: [], error: ''});
    columnCache.current = new Map();
    modelCache.current = new Map();
    // Models are optional: an endpoint without any still has catalog tables.
    Promise.all([client.listResources(), client.listModels().catch(() => [])]).then(
      ([resources, models]) => {
        if(!cancelled) setState({status: 'ready', resources, models, error: ''});
      },
      (error) => {
        if(!cancelled) setState({status: 'error', resources: [], models: [], error: message(error)});
      });
    return () => { cancelled = true; };
  }, [client]);

  const sources = useMemo(() => tableSources(state.resources), [state.resources]);

  const loadColumns = useCallback(async (relation) => {
    const label = relation.join('.');
    if(columnCache.current.has(label)) return columnCache.current.get(label);
    const source = sources.find((item) => item.label === label);
    let inspected = null;
    if(source) {
      try { inspected = await client.inspectResource(source.resourceId); } catch { inspected = null; }
    }
    const columns = sourceColumns(inspected, state.resources, source);
    columnCache.current.set(label, columns);
    return columns;
  }, [client, sources, state.resources]);

  const loadModel = useCallback(async (modelId) => {
    if(modelCache.current.has(modelId)) return modelCache.current.get(modelId);
    const record = await client.getModel(modelId);
    const fields = {...modelFields(record.definition), revision: record.revision};
    modelCache.current.set(modelId, fields);
    return fields;
  }, [client]);

  return {status: state.status, error: state.error, sources, models: state.models, loadColumns, loadModel};
}
