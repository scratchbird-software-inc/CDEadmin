/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * The Models view forms, in the descriptor shape ObjectEditor reads
 * (`{tabs: [{tab, title, fields: [...]}]}` with typed controls and grids), so
 * the model JSON is edited through FieldControl and RecordGrid only. The
 * vocabulary lists (source kinds, dimension kinds, ...) come from the
 * provider's analytical profile; choices that name other parts of the draft
 * (a join's sources, a window's measure) are read from `context.model` by
 * `modelOptionContext`.
 */

import gettext from 'sources/gettext';
import {
  AGGREGATIONS, CALCULATION_OPERATORS, CARDINALITIES, CERTIFICATION_STATUSES, DRILL_MODES, FILTER_OPERATORS,
  JOIN_TYPES, PARAMETER_TYPES, TIME_ROLES, TIME_VALUE_TYPES, WINDOW_DIRECTIONS,
} from './modelDraft';

export const options = (values) => values.map((value) => ({value, label: String(value).replaceAll('_', ' ')}));
const path = (name) => ['model', name];
const NEEDS_VALUE = FILTER_OPERATORS.filter((operator) => !['is_null', 'is_not_null'].includes(operator));

const text = (field_id, label, extra = {}) => ({field_id, label, control: 'text', ...extra});
const select = (field_id, label, list, extra = {}) => ({field_id, label, control: 'select',
  options: options(list), default: list[0], ...extra});
const model = (field_id, label, source, extra = {}) => ({field_id, label, control: 'select',
  option_values_path: path(source), ...extra});

/** Columns of a filter grid: shared by default filters, row policies and role filters. */
export function filterColumns({withParameter = true} = {}) {
  return [
    model('source_id', gettext('Source'), 'sources', {required: true}),
    text('field', gettext('Field'), {required: true}),
    select('operator', gettext('Operator'), FILTER_OPERATORS, {default: 'eq'}),
    ...(withParameter ? [model('parameter_id', gettext('Parameter'), 'parameters_or_none', {
      help: gettext('Compare with a query parameter instead of a fixed value.'),
      visible_when: {field: 'operator', in: NEEDS_VALUE}})] : []),
    text('value_text', gettext('Value'), {
      help: gettext('Text, or JSON for numbers and lists, for example [1, 2].'),
      visible_when: {field: 'operator', in: NEEDS_VALUE}}),
  ];
}

export function modelForm(profile = {}) {
  const sourceKinds = profile.source_kinds || ['table'];
  const classifications = profile.source_classifications || ['fact'];
  const measureKinds = [...new Set([...(profile.measure_kinds || ['aggregate']), 'calculated'])];
  const aggregateKinds = measureKinds.filter((kind) => kind !== 'calculated');
  return {
    family_title: gettext('Semantic model'),
    tabs: [{
      tab: 'model', title: gettext('Model'), fields: [
        text('name', gettext('Model name'), {required: true}),
        text('description', gettext('Description')),
        text('semantic_family', gettext('Model family'), {readonly: true,
          help: gettext('Fixed by the endpoint provider.')}),
        {field_id: 'sources', label: gettext('Data sources'), control: 'grid', required: true,
          help: gettext('The tables or collections the model reads. Grain fields are comma separated.'),
          columns: [
            text('id', gettext('Source ID'), {required: true}),
            text('resource_id', gettext('Resource'), {required: true}),
            text('relation', gettext('Native relation path'), {required: true,
              help: gettext('Dotted path, for example schema.table.')}),
            text('alias', gettext('Alias')),
            select('source_kind', gettext('Source kind'), sourceKinds),
            select('classification', gettext('Classification'), classifications),
            text('grain', gettext('Declared grain fields')),
          ]},
        {field_id: 'joins', label: gettext('Joins'), control: 'grid', columns: [
          text('id', gettext('Join ID'), {required: true}),
          model('left_source', gettext('Left source'), 'sources', {required: true}),
          model('right_source', gettext('Right source'), 'sources', {required: true}),
          select('join_type', gettext('Join type'), JOIN_TYPES, {default: 'inner'}),
          select('cardinality', gettext('Cardinality'), CARDINALITIES, {default: 'many-to-one'}),
          text('left_field', gettext('Left field'), {visible_when: {field: 'join_type',
            in: JOIN_TYPES.filter((type) => type !== 'cross')}}),
          text('right_field', gettext('Right field'), {visible_when: {field: 'join_type',
            in: JOIN_TYPES.filter((type) => type !== 'cross')}}),
        ]},
        {field_id: 'relationships', label: gettext('Relationships'), control: 'grid',
          help: gettext('Provider-described relationships between sources, such as graph edges.'),
          columns: [
            text('id', gettext('Relationship ID'), {required: true}),
            text('name', gettext('Name'), {required: true}),
            model('from_source', gettext('From source'), 'sources', {required: true}),
            model('to_source', gettext('To source'), 'sources', {required: true}),
            select('relationship_kind', gettext('Relationship kind'), profile.relationship_kinds || ['join']),
          ]},
      ]}, {
      tab: 'dimensions', title: gettext('Dimensions'), fields: [
        {field_id: 'dimensions', label: gettext('Dimensions'), control: 'grid',
          help: gettext('A dimension is a field to group by. Hierarchies hold its levels, which queries use as axes.'),
          columns: [
            text('id', gettext('Dimension ID'), {required: true}),
            text('name', gettext('Name'), {required: true}),
            model('source_id', gettext('Source'), 'sources', {required: true}),
            text('field', gettext('Field'), {required: true}),
            select('dimension_kind', gettext('Dimension kind'), profile.dimension_kinds || ['attribute']),
            {field_id: 'time_enabled', label: gettext('Time intelligence'), control: 'boolean'},
            select('time_role', gettext('Time role'), TIME_ROLES, {visible_when: {field: 'time_enabled', truthy: true}}),
            text('timezone', gettext('Timezone'), {visible_when: {field: 'time_enabled', truthy: true}}),
            select('time_value_type', gettext('Time value type'), TIME_VALUE_TYPES,
              {visible_when: {field: 'time_enabled', truthy: true}}),
            {field_id: 'fiscal_year_start_month', label: gettext('Fiscal start month'), control: 'number', min: 1,
              max: 12, default: 1, visible_when: {field: 'time_enabled', truthy: true}},
            {field_id: 'hierarchies', label: gettext('Hierarchies'), control: 'grid', columns: [
              text('id', gettext('Hierarchy ID'), {required: true}),
              text('name', gettext('Name'), {required: true}),
              {field_id: 'levels', label: gettext('Levels'), control: 'grid', columns: [
                text('id', gettext('Level ID'), {required: true}),
                text('name', gettext('Name'), {required: true}),
                model('source_id', gettext('Source'), 'sources', {required: true}),
                text('field', gettext('Field'), {required: true}),
              ]},
            ]},
          ]},
      ]}, {
      tab: 'measures', title: gettext('Measures'), fields: [
        {field_id: 'measures', label: gettext('Measures'), control: 'grid',
          help: gettext('Aggregates over a source field, or a calculation of two other measures. Calculation trees with more than two measures are kept as stored and edited on the Advanced tab.'),
          columns: [
            text('id', gettext('Measure ID'), {required: true}),
            text('name', gettext('Name'), {required: true}),
            select('measure_kind', gettext('Measure kind'), measureKinds, {default: aggregateKinds[0] || 'aggregate'}),
            select('aggregation', gettext('Aggregation'), AGGREGATIONS, {default: 'sum',
              visible_when: {field: 'measure_kind', in: aggregateKinds}}),
            model('source_id', gettext('Source'), 'sources', {
              visible_when: {field: 'measure_kind', in: aggregateKinds}}),
            text('field', gettext('Field'), {help: gettext('Leave empty to count rows.'),
              visible_when: {field: 'measure_kind', in: aggregateKinds}}),
            model('calc_left', gettext('Left measure'), 'measures', {
              visible_when: {field: 'measure_kind', equals: 'calculated'}}),
            select('calc_operator', gettext('Operator'), CALCULATION_OPERATORS, {default: 'divide',
              visible_when: {field: 'measure_kind', equals: 'calculated'}}),
            model('calc_right', gettext('Right measure'), 'measures', {
              visible_when: {field: 'measure_kind', equals: 'calculated'}}),
            text('format', gettext('Format')),
            select('certification_status', gettext('Certification'), CERTIFICATION_STATUSES,
              {default: 'uncertified'}),
            text('certification_owner', gettext('Metric owner')),
            text('certification_definition', gettext('Business definition')),
          ]},
      ]}, {
      tab: 'parameters', title: gettext('Parameters & filters'), fields: [
        {field_id: 'parameters', label: gettext('Parameters'), control: 'grid', columns: [
          text('id', gettext('Parameter ID'), {required: true}),
          text('name', gettext('Name'), {required: true}),
          select('type', gettext('Type'), PARAMETER_TYPES, {default: 'string'}),
          {field_id: 'required', label: gettext('Required'), control: 'boolean'},
          text('default_text', gettext('Default'), {
            help: gettext('JSON for number, integer, boolean and array parameters.')}),
          text('allowed_text', gettext('Allowed values'), {
            help: gettext('Comma separated; empty allows any value.'),
            visible_when: {field: 'type', in: PARAMETER_TYPES.filter((type) => type !== 'array')}}),
        ]},
        {field_id: 'default_filters', label: gettext('Default filters'), control: 'grid',
          help: gettext('Applied to every query on this model.'), columns: filterColumns()},
      ]}, {
      tab: 'security', title: gettext('Security'), fields: [
        {field_id: 'row_filters', label: gettext('Row policies'), control: 'grid',
          help: gettext('Structured policy the provider compiles into every query.'),
          columns: filterColumns()},
        {field_id: 'tenant_enabled', label: gettext('Filter rows by tenant'), control: 'boolean',
          group: gettext('Tenant filtering')},
        model('tenant_source', gettext('Tenant source'), 'sources', {group: gettext('Tenant filtering'),
          visible_when: {field: 'tenant_enabled', truthy: true}}),
        text('tenant_field', gettext('Tenant field'), {group: gettext('Tenant filtering'),
          visible_when: {field: 'tenant_enabled', truthy: true}}),
        text('tenant_claim', gettext('Trusted principal claim'), {group: gettext('Tenant filtering'),
          help: gettext('The tenant value is bound server-side from this claim of the signed-in user, never from the request.'),
          visible_when: {field: 'tenant_enabled', truthy: true}}),
        {field_id: 'tenant_required', label: gettext('Refuse queries without a tenant'), control: 'boolean',
          group: gettext('Tenant filtering'), visible_when: {field: 'tenant_enabled', truthy: true}},
        {field_id: 'roles', label: gettext('Role policies'), control: 'grid',
          help: gettext('Row filters that apply when the principal claim lists the role.'), columns: [
            text('name', gettext('Role'), {required: true}),
            text('principal_claim', gettext('Principal claim'), {required: true}),
            {field_id: 'filters', label: gettext('Filters'), control: 'grid',
              columns: filterColumns({withParameter: false})},
          ]},
      ]}, {
      tab: 'materializations', title: gettext('Materializations'), fields: [
        {field_id: 'materializations', label: gettext('Materializations'), control: 'grid',
          help: gettext('Portable intent. Creating or refreshing one is a provider-planned operation.'),
          columns: [
            text('id', gettext('Materialization ID'), {required: true}),
            text('name', gettext('Name'), {required: true}),
            text('strategy', gettext('Strategy'), {default: 'provider_managed'}),
            {field_id: 'enabled', label: gettext('Enabled'), control: 'boolean'},
          ]},
      ]},
    ],
  };
}

export function queryForm(capabilities = {}) {
  const operations = capabilities.time_intelligence_operations || [];
  const periods = capabilities.time_intelligence_periods || [];
  const windowOperations = capabilities.analytical_window_operations || [];
  const windows = windowOperations.length ? [{
    field_id: 'windows', label: gettext('Analytical windows'), control: 'grid',
    help: gettext('Native window columns over a selected measure. The measure must be one of the query measures.'),
    columns: [
      text('id', gettext('Output ID'), {required: true}),
      model('measure_id', gettext('Measure'), 'measures', {required: true}),
      select('operation', gettext('Window operation'), windowOperations),
      {field_id: 'partition_by', label: gettext('Partition levels'), control: 'multiselect',
        option_values_path: path('levels')},
      model('order_level', gettext('Order level'), 'levels', {required: true}),
      select('direction', gettext('Direction'), WINDOW_DIRECTIONS, {default: 'asc'}),
      {field_id: 'frame_size', label: gettext('Frame or lag'), control: 'number', min: 1, max: 10000, default: 1},
    ]}] : [];
  const timeFields = operations.length ? [
    select('time_operation', gettext('Time operation'), ['', ...operations], {group: gettext('Time intelligence'),
      options: [{value: '', label: gettext('None')}, ...options(operations)]}),
    model('time_dimension', gettext('Time dimension'), 'time_dimensions', {group: gettext('Time intelligence'),
      visible_when: {field: 'time_operation', in: operations}}),
    text('time_start', gettext('Start or as-of value'), {group: gettext('Time intelligence'),
      visible_when: {field: 'time_operation', in: ['as_of', 'range']}}),
    text('time_end', gettext('End value'), {group: gettext('Time intelligence'),
      visible_when: {field: 'time_operation', in: ['range']}}),
    select('time_period', gettext('Period'), periods, {group: gettext('Time intelligence'),
      visible_when: {field: 'time_operation', in: ['period_to_date', 'period_comparison']}}),
    text('time_anchor', gettext('Anchor date or datetime'), {group: gettext('Time intelligence'),
      visible_when: {field: 'time_operation', in: ['period_to_date', 'period_comparison']}}),
  ] : [];
  return {
    family_title: gettext('Cube query'),
    tabs: [{
      tab: 'query', title: gettext('Cube query'), fields: [
        {field_id: 'rows', label: gettext('Rows'), control: 'multiselect', option_values_path: path('levels'),
          group: gettext('Axes')},
        {field_id: 'columns', label: gettext('Columns'), control: 'multiselect', option_values_path: path('levels'),
          group: gettext('Axes')},
        {field_id: 'pages', label: gettext('Pages'), control: 'multiselect', option_values_path: path('levels'),
          group: gettext('Axes')},
        {field_id: 'measures', label: gettext('Measures'), control: 'multiselect', required: true,
          option_values_path: path('measures'), group: gettext('Axes')},
        {field_id: 'filters', label: gettext('Slices'), control: 'grid', group: gettext('Slice and dice'),
          columns: filterColumns({withParameter: true})},
        {field_id: 'parameters', label: gettext('Parameter values'), control: 'grid', group: gettext('Slice and dice'),
          columns: [
            model('parameter_id', gettext('Parameter'), 'parameters', {required: true}),
            text('value_text', gettext('Value'), {required: true}),
          ]},
        select('drill_mode', gettext('Drill mode'), DRILL_MODES, {group: gettext('Drill'), default: 'summary'}),
        {...model('drill_target', gettext('Drill-down target'), 'levels_or_none'), group: gettext('Drill'),
          visible_when: {field: 'drill_mode', equals: 'down'}},
        text('drill_details', gettext('Drill-through fields'), {group: gettext('Drill'),
          help: gettext('source.field, source.field'), visible_when: {field: 'drill_mode', equals: 'through'}}),
        ...timeFields,
        ...windows,
        {field_id: 'totals', label: gettext('Rollup totals'), control: 'boolean', group: gettext('Limits')},
        {field_id: 'limit', label: gettext('Cell limit'), control: 'number', min: 1, max: 10000,
          group: gettext('Limits')},
      ]}],
  };
}

const named = (items, key = 'id') => items.map((item) => ({value: item[key], label: item.name || item[key]}));

/** The lists the grids' reference columns choose from, derived from the current draft. */
export function modelOptionContext(draft, definition) {
  const sources = (draft.sources || []).filter((row) => row.id).map((row) => ({value: row.id, label: row.id}));
  const dimensions = (draft.dimensions || []).filter((row) => row.id);
  const levels = [];
  for(const dimension of dimensions) {
    levels.push({value: dimension.id, label: dimension.name || dimension.id});
    for(const hierarchy of dimension.hierarchies || []) {
      for(const level of hierarchy.levels || []) {
        if(level.id) {
          levels.push({value: level.id,
            label: `${dimension.name || dimension.id} / ${hierarchy.name || hierarchy.id} / ${level.name || level.id}`});
        }
      }
    }
  }
  const measures = named((draft.measures || []).filter((row) => row.id));
  return {
    model: {
      sources, measures, levels,
      levels_or_none: [{value: '', label: gettext('None')}, ...levels],
      parameters: named((draft.parameters || []).filter((row) => row.id)),
      parameters_or_none: [{value: '', label: gettext('None')},
        ...named((draft.parameters || []).filter((row) => row.id))],
      time_dimensions: named(dimensions.filter((row) => row.time_enabled)),
      definition,
    },
  };
}
