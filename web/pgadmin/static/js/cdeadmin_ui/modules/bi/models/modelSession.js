/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * The open model: a pure reducer over the stored record and the editable
 * draft. Async work (load, save, status changes) lives in the hook
 * (useModelSession); this file has no React and no network.
 */

import {addDiscoveredSource, fromDraft, toDraft, uniqueId} from './modelDraft';

const ID_PREFIX = {
  sources: 'source', joins: 'join', relationships: 'relationship', dimensions: 'dimension',
  measures: 'measure', parameters: 'parameter', materializations: 'materialization',
};

/**
 * New grid rows have no `id` key at all (the grid does not know how to make one). Give them the next free
 * identifier so the model stays valid while the user fills in the rest; an id the user cleared is left alone.
 */
export function fillIds(draft) {
  let next = draft;
  for(const [section, prefix] of Object.entries(ID_PREFIX)) {
    const rows = draft[section];
    if(!Array.isArray(rows) || rows.every((row) => row.id !== undefined)) continue;
    const taken = rows.map((row) => row.id).filter(Boolean);
    next = {...next, [section]: rows.map((row) => {
      if(row.id !== undefined) return row;
      const id = uniqueId(prefix, taken);
      taken.push(id);
      return {...row, id};
    })};
  }
  if(Array.isArray(next.dimensions)) {
    const levelIds = [];
    const hierarchyIds = [];
    next.dimensions.forEach((dimension) => (dimension.hierarchies || []).forEach((hierarchy) => {
      if(hierarchy.id) hierarchyIds.push(hierarchy.id);
      (hierarchy.levels || []).forEach((level) => level.id && levelIds.push(level.id));
    }));
    const missing = next.dimensions.some((dimension) => (dimension.hierarchies || []).some((hierarchy) =>
      hierarchy.id === undefined || (hierarchy.levels || []).some((level) => level.id === undefined)));
    if(missing) {
      next = {...next, dimensions: next.dimensions.map((dimension) => ({...dimension,
        hierarchies: (dimension.hierarchies || []).map((hierarchy) => {
          const id = hierarchy.id === undefined ? uniqueId('hierarchy', hierarchyIds) : hierarchy.id;
          if(hierarchy.id === undefined) hierarchyIds.push(id);
          return {...hierarchy, id, levels: (hierarchy.levels || []).map((level) => {
            if(level.id !== undefined) return level;
            const levelId = uniqueId('level', levelIds);
            levelIds.push(levelId);
            return {...level, id: levelId};
          })};
        })}))};
    }
  }
  return next;
}

const serialize = (draft) => JSON.stringify(draft);

export function initialSession() {
  return {record: null, draft: null, baseline: '', dirty: false, validation: null, lineage: null};
}

function loaded(record) {
  const draft = toDraft(record.definition);
  return {record: {model_id: record.model_id, name: record.name, status: record.status,
    revision: record.revision, updated_at: record.updated_at},
  draft, baseline: serialize(draft), dirty: false, validation: null, lineage: null};
}

export function reduce(state, action) {
  switch(action.type) {
  case 'load':
    return loaded(action.record);
  case 'new': {
    const draft = toDraft(action.definition);
    return {record: null, draft, baseline: serialize(draft), dirty: false, validation: null, lineage: null};
  }
  case 'edit': {
    const draft = fillIds({...state.draft, [action.field]: action.value});
    return {...state, draft, dirty: serialize(draft) !== state.baseline, validation: null};
  }
  case 'definition': {
    // the Advanced tab replaced the whole document
    const draft = toDraft(action.definition);
    return {...state, draft, dirty: serialize(draft) !== state.baseline, validation: null};
  }
  case 'addSource': {
    const draft = addDiscoveredSource(state.draft, action.resource, action.profile);
    return {...state, draft, dirty: serialize(draft) !== state.baseline, validation: null};
  }
  case 'status':
    // a status change saves a new revision of the stored definition; the draft is untouched
    return {...state, record: {...state.record, status: action.record.status,
      revision: action.record.revision, updated_at: action.record.updated_at}};
  case 'validated':
    return {...state, validation: action.result,
      lineage: action.result?.valid && action.result.lineage ? action.result.lineage : state.lineage};
  case 'lineage':
    return {...state, lineage: action.lineage};
  default:
    return state;
  }
}

/** The document the draft stands for, plus anything the typed controls could not express. */
export const definitionOf = (state) => (state.draft ? fromDraft(state.draft) : {definition: null, problems: []});
