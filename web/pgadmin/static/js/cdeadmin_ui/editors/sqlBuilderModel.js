/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Visual SQL builder drafts (owner direction 2026-11-06, option b).
 *
 * The form edits a draft; toModel turns it into the neutral query model
 * that the server writes in the connection's SQL (workspace action
 * sql_builder, cdeadmin/sdk/sql_builder.py). The model carries names and
 * values only, never SQL text. Which options the connection has comes from
 * the server; nothing here names an engine.
 */

export class BuilderDraftError extends Error {}

let keyCounter = 0;
export function newKey(prefix='k') {
  keyCounter += 1;
  return `${prefix}${keyCounter}`;
}

export const AGGREGATES = ['count', 'sum', 'avg', 'min', 'max'];
export const RANKING_WINDOWS = ['row_number', 'rank', 'dense_rank'];
export const WINDOWS = [...RANKING_WINDOWS, ...AGGREGATES];
export const COMPARISONS = ['=', '<>', '<', '<=', '>', '>=', 'LIKE', 'NOT LIKE',
  'IS NULL', 'IS NOT NULL'];
export const JOIN_TYPES = [
  {value: 'inner', label: 'Inner join'}, {value: 'left', label: 'Left join'},
  {value: 'right', label: 'Right join'}, {value: 'full', label: 'Full join'},
  {value: 'cross', label: 'Cross join'}, {value: 'natural', label: 'Natural join'},
];
export const SET_OPERATORS = [
  {value: 'union', label: 'UNION'}, {value: 'union_all', label: 'UNION ALL'},
  {value: 'intersect', label: 'INTERSECT'}, {value: 'except', label: 'EXCEPT'},
];
export const GROUPINGS = [
  {value: '', label: 'No grouping', option: null},
  {value: 'columns', label: 'GROUP BY columns', option: 'group_by'},
  {value: 'rollup', label: 'GROUP BY ROLLUP', option: 'group_by.rollup'},
  {value: 'cube', label: 'GROUP BY CUBE', option: 'group_by.cube'},
  {value: 'grouping_sets', label: 'GROUP BY GROUPING SETS', option: 'group_by.grouping_sets'},
  {value: 'all', label: 'GROUP BY ALL', option: 'group_by.all'},
];

export function available(options, id) {
  return options?.[id]?.available === true;
}

export function unavailableReason(options, id) {
  const entry = options?.[id];
  if(!entry) return 'This connection did not report this option.';
  return entry.available ? '' : entry.reason;
}

export function emptyOperand(kind='column') {
  return {
    kind,
    column: '',
    func: kind === 'window' ? 'row_number' : 'count',
    distinct: false,
    star: kind === 'aggregate',
    value: '',
    partitionBy: [],
    windowOrderColumn: '',
    windowOrderDirection: 'asc',
  };
}

export function emptyCondition(leftKind='column') {
  return {key: newKey('c'), left: emptyOperand(leftKind), op: '=', right: emptyOperand('text')};
}

export function emptyColumn(kind='column') {
  return {key: newKey('o'), ...emptyOperand(kind), alias: ''};
}

export function emptyJoin(source='') {
  return {key: newKey('j'), type: 'inner', source, alias: '', mode: 'on', using: [],
    on: {key: newKey('c'), left: emptyOperand(), op: '=', right: emptyOperand('column')}};
}

export function emptyOrder() {
  return {key: newKey('r'), operand: emptyOperand(), direction: 'asc', nulls: ''};
}

export function emptySelect(source='') {
  return {key: newKey('s'), source, alias: '', distinct: false, distinctOn: [],
    columns: [], joins: [], where: {combine: 'all', items: []},
    group: {kind: '', columns: [], sets: []}, having: {combine: 'all', items: []}};
}

export function emptyCompound(source='') {
  return {selects: [emptySelect(source)], operators: [], order: [], limit: '', offset: ''};
}

export function emptyDraft(source='') {
  return {recursive: false, ctes: [], query: emptyCompound(source)};
}

export function emptyCte(name, source='') {
  return {
    key: newKey('w'),
    name,
    columns: '',
    materialized: '',
    cycleEnabled: false,
    cycleColumns: '',
    cycleSetColumn: 'is_cycle',
    cycleUsingColumn: 'traversal_path',
    query: emptyCompound(source),
  };
}

// -- sources and columns ------------------------------------------------
export function relationSource(path) {
  return `rel:${JSON.stringify(path)}`;
}

export function cteSource(name) {
  return `cte:${name}`;
}

function sourceModel(value, label) {
  if(typeof value !== 'string' || !value) {
    throw new BuilderDraftError(`${label}: choose a table, view or CTE.`);
  }
  if(value.startsWith('rel:')) return {relation: JSON.parse(value.slice(4))};
  return {cte: value.slice(4)};
}

function sourceName(value) {
  if(value.startsWith('rel:')) {
    const path = JSON.parse(value.slice(4));
    return path[path.length - 1];
  }
  return value.slice(4);
}

function splitNames(text) {
  return text.split(',').map((name) => name.trim()).filter(Boolean);
}

/* The output column names of a compound query: its first SELECT's. */
export function outputColumns(compound, columnsOf) {
  const select = compound.selects[0];
  if(!select) return [];
  const names = [];
  for(const column of select.columns) {
    if(column.kind === 'all') {
      for(const source of selectSources(select)) names.push(...columnsOf(source.value));
    } else if(column.alias.trim()) {
      names.push(column.alias.trim());
    } else if(column.kind === 'column' && column.column) {
      const ref = JSON.parse(column.column);
      names.push(ref[ref.length - 1]);
    }
  }
  if(select.columns.length === 0) {
    for(const source of selectSources(select)) names.push(...columnsOf(source.value));
  }
  return [...new Set(names)];
}

/* columnsOf(source value) -> column names, for relations and CTEs. */
export function columnResolver(relations, ctes) {
  const byValue = new Map(relations.map((item) =>
    [relationSource(item.path), item.columns || []]));
  const resolve = (value, seen=new Set()) => {
    if(!value) return [];
    if(byValue.has(value)) return byValue.get(value);
    const name = value.startsWith('cte:') ? value.slice(4) : null;
    const cte = ctes.find((item) => item.name === name);
    if(!cte || seen.has(name)) return [];
    const declared = splitNames(cte.columns);
    if(declared.length) return declared;
    return outputColumns(cte.query, (inner) => resolve(inner, new Set([...seen, name])));
  };
  return (value) => resolve(value);
}

export function selectSources(select) {
  return [{value: select.source, alias: select.alias},
    ...select.joins.map((join) => ({value: join.source, alias: join.alias}))]
    .filter((item) => item.value);
}

/* The qualified column choices of one SELECT: alias.column for each source. */
export function columnChoices(select, columnsOf) {
  const choices = [];
  for(const source of selectSources(select)) {
    const qualifier = source.alias.trim() || sourceName(source.value);
    for(const name of columnsOf(source.value)) {
      choices.push({value: JSON.stringify([qualifier, name]), label: `${qualifier}.${name}`});
    }
  }
  return choices;
}

// -- the model ------------------------------------------------------------
function operandModel(operand, label) {
  switch(operand.kind) {
  case 'column':
    if(!operand.column) throw new BuilderDraftError(`${label}: choose a column.`);
    return {column: JSON.parse(operand.column)};
  case 'aggregate':
    if(!operand.star && !operand.column) {
      throw new BuilderDraftError(`${label}: choose the column to aggregate, or *.`);
    }
    return {aggregate: {function: operand.func, distinct: Boolean(operand.distinct),
      argument: operand.star ? '*' : {column: JSON.parse(operand.column)}}};
  case 'window': {
    const fn = operand.func || 'row_number';
    const win = {function: fn};
    if(!RANKING_WINDOWS.includes(fn)) {
      if(!operand.star && !operand.column) {
        throw new BuilderDraftError(`${label}: choose the column for the window function, or *.`);
      }
      win.distinct = Boolean(operand.distinct);
      win.argument = operand.star ? '*' : {column: JSON.parse(operand.column)};
    }
    if(Array.isArray(operand.partitionBy) && operand.partitionBy.length) {
      win.partition_by = operand.partitionBy.map((column) => ({column: JSON.parse(column)}));
    }
    if(operand.windowOrderColumn) {
      win.order_by = [{
        expr: {column: JSON.parse(operand.windowOrderColumn)},
        direction: operand.windowOrderDirection || 'asc',
      }];
    }
    return {window: win};
  }
  case 'number': {
    const number = Number(operand.value);
    if(!operand.value.trim() || !Number.isFinite(number)) {
      throw new BuilderDraftError(`${label}: enter a number.`);
    }
    return {value: number};
  }
  case 'null':
    return {value: null};
  default:
    return {value: operand.value};
  }
}

function conditionModel(condition, label) {
  const left = operandModel(condition.left, label);
  if(condition.op === 'IS NULL') return {is_null: left};
  if(condition.op === 'IS NOT NULL') return {is_not_null: left};
  return {compare: {left, op: condition.op, right: operandModel(condition.right, label)}};
}

function conditionsModel(group, label) {
  if(group.items.length === 0) return undefined;
  const items = group.items.map((item, index) => conditionModel(item, `${label} ${index + 1}`));
  return items.length === 1 ? items[0] : {[group.combine]: items};
}

function optionalName(text) {
  return text.trim() ? text.trim() : undefined;
}

function selectModel(select, label) {
  const model = {from: {source: sourceModel(select.source, `${label} FROM`)}};
  if(optionalName(select.alias)) model.from.alias = select.alias.trim();
  if(select.distinct) model.distinct = true;
  if(select.distinctOn.length) {
    model.distinct_on = select.distinctOn.map((column) => ({column: JSON.parse(column)}));
  }
  if(select.columns.length) {
    model.columns = select.columns.map((column, index) => {
      if(column.kind === 'all') return {all: null};
      const entry = {expr: operandModel(column, `${label} column ${index + 1}`)};
      if(optionalName(column.alias)) entry.alias = column.alias.trim();
      return entry;
    });
  }
  if(select.joins.length) {
    model.joins = select.joins.map((join, index) => {
      const name = `${label} join ${index + 1}`;
      const entry = {type: join.type, source: sourceModel(join.source, name)};
      if(optionalName(join.alias)) entry.alias = join.alias.trim();
      if(join.type === 'cross' || join.type === 'natural') return entry;
      if(join.mode === 'using') {
        if(!join.using.length) throw new BuilderDraftError(`${name}: choose the shared columns.`);
        entry.using = [...join.using];
      } else {
        entry.on = conditionModel(join.on, name);
      }
      return entry;
    });
  }
  const where = conditionsModel(select.where, `${label} condition`);
  if(where) model.where = where;
  if(select.group.kind) {
    const group = {kind: select.group.kind};
    if(['columns', 'rollup', 'cube'].includes(select.group.kind)) {
      if(!select.group.columns.length) {
        throw new BuilderDraftError(`${label}: choose the grouping columns.`);
      }
      group.items = select.group.columns.map((column) => ({column: JSON.parse(column)}));
    }
    if(select.group.kind === 'grouping_sets') {
      if(!select.group.sets.length) {
        throw new BuilderDraftError(`${label}: add at least one grouping set.`);
      }
      group.sets = select.group.sets.map((set) => set.map((column) => ({column: JSON.parse(column)})));
    }
    model.group_by = group;
  }
  const having = conditionsModel(select.having, `${label} HAVING`);
  if(having) model.having = having;
  return model;
}

function wholeNumber(text, label) {
  if(!String(text).trim()) return undefined;
  const number = Number(text);
  if(!Number.isInteger(number) || number < 0) {
    throw new BuilderDraftError(`${label} must be a whole number of 0 or more.`);
  }
  return number;
}

function compoundModel(compound, label) {
  const model = {selects: compound.selects.map((select, index) =>
    selectModel(select, compound.selects.length > 1 ? `${label} SELECT ${index + 1}` : label))};
  if(compound.operators.length) model.operators = [...compound.operators];
  if(compound.order.length) {
    model.order_by = compound.order.map((item, index) => {
      const entry = {expr: operandModel(item.operand, `${label} order ${index + 1}`),
        direction: item.direction};
      if(item.nulls) entry.nulls = item.nulls;
      return entry;
    });
  }
  const limit = wholeNumber(compound.limit, `${label} LIMIT`);
  const offset = wholeNumber(compound.offset, `${label} OFFSET`);
  if(limit !== undefined) model.limit = limit;
  if(offset !== undefined) model.offset = offset;
  return model;
}

function cteModel(cte, recursive) {
  const name = cte.name.trim();
  if(!name) throw new BuilderDraftError('Every common table expression needs a name.');
  const entry = {name, query: compoundModel(cte.query, name)};
  const columns = splitNames(cte.columns);
  if(columns.length) entry.columns = columns;
  if(cte.materialized) entry.materialized = cte.materialized === 'yes';
  if(recursive && cte.cycleEnabled) {
    const cycleColumns = splitNames(cte.cycleColumns || '');
    if(!cycleColumns.length) {
      throw new BuilderDraftError(`${name} CYCLE: enter at least one column name.`);
    }
    const setColumn = (cte.cycleSetColumn || '').trim();
    const usingColumn = (cte.cycleUsingColumn || '').trim();
    if(!setColumn || !usingColumn) {
      throw new BuilderDraftError(`${name} CYCLE: enter both SET and USING column names.`);
    }
    if(setColumn === usingColumn) {
      throw new BuilderDraftError(`${name} CYCLE: SET and USING column names must differ.`);
    }
    entry.cycle = {columns: cycleColumns, set_column: setColumn, using_column: usingColumn};
  }
  return entry;
}

export function toModel(draft) {
  const model = {query: compoundModel(draft.query, 'Query')};
  if(draft.ctes.length) {
    model.with = draft.ctes.map((cte) => cteModel(cte, draft.recursive));
    if(draft.recursive) model.recursive = true;
  }
  return model;
}

/* Build a model for previewing a named CTE stage (validating only CTEs 0..k)
 * or the final Query stage. */
export function toStageModel(draft, stage) {
  if(!stage || stage === '__query__') return toModel(draft);
  const cutoff = draft.ctes.findIndex((cte) => cte.name.trim() === stage);
  if(cutoff === -1) {
    throw new BuilderDraftError(`Unknown CTE stage ${stage}.`);
  }
  const model = {
    with: draft.ctes.slice(0, cutoff + 1).map((cte) => cteModel(cte, draft.recursive)),
    query: {selects: [{from: {source: {cte: stage}}}]},
  };
  if(draft.recursive) model.recursive = true;
  return model;
}

function partialSource(value) {
  if(typeof value !== 'string' || !value) return {relation: ['draft']};
  if(value.startsWith('rel:')) {
    try { return {relation: JSON.parse(value.slice(4))}; } catch { return {relation: [value.slice(4)]}; }
  }
  return {cte: value.slice(4) || 'cte'};
}

function partialCompound(compound) {
  const selects = (compound?.selects || []).map((select) => {
    const item = {from: {source: partialSource(select.source)}};
    if(optionalName(select.alias || '')) item.from.alias = select.alias.trim();
    const joins = (select.joins || [])
      .filter((join) => join.source)
      .map((join) => {
        const j = {type: join.type || 'inner', source: partialSource(join.source)};
        if(optionalName(join.alias || '')) j.alias = join.alias.trim();
        return j;
      });
    if(joins.length) item.joins = joins;
    const cols = [];
    for(const col of select.columns || []) {
      if(col.kind === 'all') cols.push({all: null});
      else {
        try {
          const expr = operandModel(col, 'Column');
          const entry = {expr};
          if(optionalName(col.alias || '')) entry.alias = col.alias.trim();
          cols.push(entry);
        } catch {
          // Skip incomplete column expressions during partial flow preview
        }
      }
    }
    if(cols.length) item.columns = cols;
    return item;
  });
  const out = {selects: selects.length ? selects : [{from: {source: {relation: ['draft']}}}]};
  if(compound?.operators?.length) out.operators = [...compound.operators];
  return out;
}

/* Tolerant projection of an in-progress draft into a sql_builder flow model
 * for server-side DDN dataflow rendering. */
export function toPartialFlowModel(draft) {
  try {
    return toModel(draft);
  } catch {
    const model = {query: partialCompound(draft?.query)};
    const ctes = (draft?.ctes || []).map((cte, idx) => {
      const name = (cte.name || '').trim() || `cte_${idx + 1}`;
      const entry = {name, query: partialCompound(cte.query)};
      const columns = splitNames(cte.columns || '');
      if(columns.length) entry.columns = columns;
      if(cte.materialized) entry.materialized = cte.materialized === 'yes';
      if(draft?.recursive && cte.cycleEnabled) {
        const cycleColumns = splitNames(cte.cycleColumns || '');
        if(cycleColumns.length) {
          entry.cycle = {
            columns: cycleColumns,
            set_column: (cte.cycleSetColumn || 'is_cycle').trim(),
            using_column: (cte.cycleUsingColumn || 'traversal_path').trim(),
          };
        }
      }
      return entry;
    });
    if(ctes.length) {
      model.with = ctes;
      if(draft?.recursive) model.recursive = true;
    }
    return model;
  }
}

export function describeFlowStages(draft) {
  if(!draft) return [];
  const stages = (draft.ctes || []).map((cte, index) => {
    const name = cte.name.trim() || `CTE ${index + 1}`;
    const joins = (cte.query?.selects || []).reduce(
      (sum, sel) => sum + (sel.joins?.length || 0), 0
    );
    return {
      key: cte.key,
      stageId: cte.name.trim() || null,
      kind: 'cte',
      index,
      label: `WITH ${name}`,
      joins,
      selectBranches: cte.query?.selects?.length || 1,
      recursive: Boolean(draft.recursive),
      materialized: cte.materialized === 'yes' ? 'MATERIALIZED' :
        cte.materialized === 'no' ? 'NOT MATERIALIZED' : '',
      cycle: Boolean(draft.recursive && cte.cycleEnabled),
    };
  });
  const queryJoins = (draft.query?.selects || []).reduce(
    (sum, sel) => sum + (sel.joins?.length || 0), 0
  );
  stages.push({
    key: '__query__',
    stageId: '__query__',
    kind: 'query',
    index: stages.length,
    label: 'Final Query',
    joins: queryJoins,
    selectBranches: draft.query?.selects?.length || 1,
    recursive: false,
    materialized: '',
    cycle: false,
  });
  return stages;
}
