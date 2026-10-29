/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Turn the endpoint's existing resource lists (resource_page,
 * resource_inspect) and semantic models (semantic_model_get) into the
 * pickers the builder needs. Resource kinds, not engine identities, decide
 * what counts as a table source.
 */

import {typeCategory} from './columnTypes';

const SOURCE_KINDS = new Set(['table', 'view', 'materialized_view', 'materialized-view']);
const TYPE_KEYS = ['data_type', 'type_name', 'type', 'sql_type', 'native_type', 'column_type'];

/** First provider-native block of a resource, wherever the provider nests it. */
function nativeBlock(resource) {
  for(const [key, value] of Object.entries(resource?.extensions || {})) {
    if(key !== 'cdeadmin' && value && typeof value === 'object' && value.native) return value.native;
  }
  return resource?.native && typeof resource.native === 'object' ? resource.native : {};
}

/** Catalog tables and views a builder question can read, sorted by path. */
export function tableSources(resources) {
  return (resources || [])
    .filter((item) => SOURCE_KINDS.has(item.resource_kind) && nativeBlock(item).system_object !== true)
    .map((item) => {
      const relation = item.display_path?.length ? [...item.display_path] : [item.display_name];
      return {
        resourceId: item.resource_id, kind: item.resource_kind, relation,
        label: relation.join('.'),
      };
    })
    .sort((left, right) => left.label.localeCompare(right.label));
}

function columnEntry(column) {
  if(typeof column === 'string') return {name: column, type: '', category: typeCategory('')};
  const name = column?.name ?? column?.column_name ?? '';
  const type = TYPE_KEYS.map((key) => column?.[key]).find((value) => typeof value === 'string' && value) || '';
  return {name, type, category: typeCategory(type)};
}

/**
 * Columns of a source: from the inspected resource's native column list, or
 * from catalog resources of kind column that sit under the table.
 */
export function sourceColumns(inspected, resources = [], source = null) {
  const listed = nativeBlock(inspected).columns;
  if(Array.isArray(listed) && listed.length) return listed.map(columnEntry).filter((column) => column.name);
  if(!source) return [];
  return resources
    .filter((item) => item.resource_kind === 'column' && (
      item.parent_resource_id === source.resourceId ||
      nativeBlock(item).navigator_parent_resource_id === source.resourceId ||
      (item.display_path || []).slice(0, -1).join('.') === source.relation.join('.')))
    .map((item) => columnEntry({...nativeBlock(item), name: item.display_name}));
}

/** Map of column name to category for retyping stored filters. */
export function categoryMap(columns) {
  return Object.fromEntries(columns.map((column) => [column.name, column.category]));
}

/** Dimensions, measures and parameters of a semantic model definition. */
export function modelFields(definition) {
  const dimensions = (definition?.dimensions || []).map((dimension) => ({
    id: dimension.id, name: dimension.name || dimension.id, field: dimension.field || null,
    category: typeCategory(dimension.data_type || dimension.type || ''),
  }));
  const measures = (definition?.measures || []).map((measure) => ({
    id: measure.id, name: measure.name || measure.id, aggregation: measure.aggregation || '',
  }));
  return {dimensions, measures, name: definition?.name || ''};
}
