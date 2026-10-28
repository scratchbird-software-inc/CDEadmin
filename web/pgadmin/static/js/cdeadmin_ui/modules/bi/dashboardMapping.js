/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Filter mapping and editor diagnostics. A dashboard filter targets, per
 * question card, one parameter of the pinned question or one field of it
 * (docs/en_US/bi_dashboards.rst). The rules here mirror
 * dashboard_models.check_mappings so the editor can warn before the server
 * refuses a save; the server stays authoritative.
 *
 * `infos` maps infoKey(question) to a questionInfo() summary, or to nothing
 * while the pinned revision is still loading (unknown is never an error).
 */

import gettext from 'sources/gettext';
import {cardLabel, drillMappings, mappingTargetKey, questionCards} from './dashboardState';
import {orderTargets} from './outputs';
import {fromQuestion} from './queryState';

export const infoKey = (question) => `${question.question_id}@${question.revision}`;

/**
 * What a filter can map to on a pinned question definition. `columns` are the
 * known source columns of a builder question and `model` the loaded semantic
 * model (modelFields()), both optional hints for the pickers.
 */
export function questionInfo(definition, {columns = [], model = null} = {}) {
  const query = definition?.query || {};
  const builder = query.builder || {};
  const names = new Set(columns.map((column) => column.name ?? column));
  if(query.kind === 'builder') {
    for(const entry of [...(builder.columns || []), ...(builder.group_by || [])]) {
      names.add(typeof entry === 'string' ? entry : entry.column);
    }
    for(const entry of builder.aggregations || []) if(entry.column) names.add(entry.column);
  }
  const fields = (model?.dimensions || []).filter((dimension) => dimension.field).map((dimension) => ({
    source_id: dimension.field.source_id, field: dimension.field.field,
    label: dimension.name || dimension.id,
  }));
  let outputs = [];
  if(query.kind === 'builder' || query.kind === 'semantic') {
    try {
      outputs = orderTargets(fromQuestion({definition}), model).map((output) => output.id);
    } catch {
      outputs = [];
    }
  }
  return {
    kind: query.kind || 'builder',
    outputs,
    name: definition?.name || '',
    parameters: (definition?.parameters || []).map((parameter) => ({
      id: parameter.id, type: parameter.type, required: Boolean(parameter.required)})),
    columns: [...names].filter(Boolean).sort(),
    fields,
    visualization: definition?.visualization || {type: 'table', settings: {}},
    modelId: definition?.semantic_model?.id || '',
    relation: builder.source?.relation || [],
  };
}

/** The problem with a filter target against its card's question, or '' when none is known. */
export function targetIssue(filter, target, info) {
  if(!info) return '';
  if(target.parameter_id !== undefined) {
    if(!target.parameter_id) return gettext('Choose a parameter.');
    const declared = info.parameters.find((parameter) => parameter.id === target.parameter_id);
    if(!declared) return gettext('Parameter %s is not declared by the pinned question.', target.parameter_id);
    const compatible = declared.type === filter.type ||
      (declared.type === 'array' && (filter.multiple || filter.operator === 'between'));
    return compatible ? '' : gettext('The filter type %s does not match the type %s of parameter %s.',
      filter.type, declared.type, declared.id);
  }
  const field = target.field || {};
  if(info.kind === 'sql') return gettext('A raw SQL question only accepts a parameter mapping.');
  if(info.kind === 'builder') {
    return field.column ? '' : gettext('Choose a column of the question source.');
  }
  return field.source_id && field.field ? '' : gettext('Choose a field of the semantic model.');
}

/** Per card: its mappings for one filter with issues, and whether it is unmapped. */
export function mappingRows(state, filter, infos) {
  return questionCards(state).map((card) => {
    const info = infos[infoKey(card.question)];
    const targets = filter.targets
      .map((target, index) => ({target, index}))
      .filter((item) => item.target.card_id === card.id)
      .map((item, position) => ({
        ...item, position, issue: targetIssue(filter, item.target, info)}));
    return {card, info, targets, unmapped: targets.length === 0};
  });
}

/** Everything the editor warns about; `level` is 'error' (the server will refuse) or 'warning'. */
export function dashboardIssues(state, infos = {}) {
  const issues = [];
  const add = (level, path, message) => issues.push({level, path, message});
  if(!state.name.trim()) add('error', 'name', gettext('Give the dashboard a name.'));
  const cards = questionCards(state);
  for(const filter of state.filters) {
    const path = `filters.${filter.id}`;
    if(!filter.targets.length) {
      const driven = state.crossFilters.some((link) => link.filter_id === filter.id);
      add('warning', path, driven ?
        gettext('Filter %s is set by a cross-filter but filters no card.', filter.name) :
        gettext('Filter %s is not mapped to any card.', filter.name));
    }
    for(const row of mappingRows(state, filter, infos)) {
      for(const item of row.targets) {
        if(item.issue) add('error', `${path}.${row.card.id}`,
          gettext('%s on %s: %s', filter.name, cardLabel(row.card), item.issue));
      }
      if(row.unmapped && filter.targets.length) {
        add('warning', `${path}.${row.card.id}`,
          gettext('%s is not filtered by %s.', cardLabel(row.card), filter.name));
      }
    }
    if(filter.required && !('default' in filter)) {
      add('warning', path, gettext('Required filter %s has no default: no card runs until a value is chosen.', filter.name));
    }
    if(filter.widget === 'select' || filter.widget === 'multi_select') {
      if(!filter.allowed_values.length) {
        add('warning', path, gettext('Filter %s has no allowed values to choose from.', filter.name));
      }
    }
  }
  for(const link of state.crossFilters) {
    if(!link.source_column.trim()) {
      add('error', `cross_filters.${link.id}`, gettext('A cross-filter needs the column whose value it sets.'));
    }
  }
  for(const drill of state.drillThroughs) {
    const path = `drill_throughs.${drill.id}`;
    const target = drill.target;
    if(target.kind === 'question') {
      const info = infos[infoKey(target)];
      if(!target.question_id) add('error', path, gettext('Choose the question to open.'));
      for(const mapping of drillMappings(target)) {
        if(!mapping.parameter_id) add('error', path, gettext('Choose the parameter each value fills.'));
        else if(info && !info.parameters.some((parameter) => parameter.id === mapping.parameter_id)) {
          add('error', path, gettext('Parameter %s is not declared by the target question.', mapping.parameter_id));
        }
      }
    } else if(!target.dashboard_id) {
      add('error', path, gettext('Choose the dashboard to open.'));
    }
    for(const mapping of drillMappings(target)) {
      if(!mapping[mappingTargetKey(target)]) {
        add('error', path, gettext('Every mapping needs a target.'));
      }
      const from = mapping.from || {};
      const given = ('column' in from) ? from.column : ('filter_id' in from) ? from.filter_id : from.value;
      if(('column' in from || 'filter_id' in from) && !given) {
        add('error', path, gettext('Every mapping needs a value source.'));
      }
    }
    if(!cards.some((card) => card.id === drill.source_card_id)) {
      add('error', path, gettext('The source card no longer exists.'));
    }
  }
  return issues;
}

export const hasErrors = (issues) => issues.some((issue) => issue.level === 'error');
