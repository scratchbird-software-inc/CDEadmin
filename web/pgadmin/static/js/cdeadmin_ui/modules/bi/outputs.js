/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Output column naming for builder questions. This mirrors the identifier
 * rules of web/pgadmin/cdeadmin/bi/builder.py (output_id and _unique) so the
 * UI can offer the same ordering and chart targets the compiler will accept
 * before a question has been run. The backend remains the authority.
 */

export function outputId(name) {
  let text = String(name).replace(/[^A-Za-z0-9_]+/g, '_').replace(/^_+|_+$/g, '') || 'col';
  if(!/^[A-Za-z]/.test(text)) text = `c_${text}`;
  return text.slice(0, 100);
}

function unique(name, used) {
  let candidate = name;
  let index = 2;
  while(used.has(candidate)) {
    candidate = `${name}_${index}`;
    index += 1;
  }
  used.add(candidate);
  return candidate;
}

/** Default output name of a summary, e.g. sum_amount or count. */
export function defaultAggregationName(aggregation) {
  return aggregation.function + (aggregation.column ? `_${outputId(aggregation.column)}` : '');
}

/**
 * Outputs a table builder question produces, in result order:
 * [{id, kind: 'dimension'|'measure'|'column', label, column?}].
 */
export function tableOutputs(state) {
  const used = new Set();
  const outputs = [];
  if(state.aggregations.length) {
    for(const entry of state.groupBy) {
      outputs.push({id: unique(entry.alias || outputId(entry.column), used),
        kind: 'dimension', label: entry.column, column: entry.column});
    }
    for(const entry of state.aggregations) {
      const id = unique(entry.alias || defaultAggregationName(entry), used);
      outputs.push({id, kind: 'measure', label: id});
    }
    return outputs;
  }
  for(const entry of state.columns) {
    outputs.push({id: unique(entry.alias || outputId(entry.column), used),
      kind: 'column', label: entry.column, column: entry.column});
  }
  return outputs;
}

/**
 * Outputs of a semantic question: chosen dimensions then measures, labelled
 * from the model's own names when the model definition is known.
 */
export function modelOutputs(state, model) {
  const label = (list, id) => list?.find((item) => item.id === id)?.name || id;
  return [
    ...state.dimensions.map((id) => ({id, kind: 'dimension', label: label(model?.dimensions, id)})),
    ...state.measures.map((id) => ({id, kind: 'measure', label: label(model?.measures, id)})),
  ];
}

/** Everything ORDER BY may name for a question in the current state. */
export function orderTargets(state, model) {
  if(state.source.kind === 'model') return modelOutputs(state, model);
  const outputs = tableOutputs(state);
  const named = new Map(outputs.map((output) => [output.id, output]));
  // The compiler also accepts the native column name of a selected column.
  for(const output of outputs) {
    if(output.column && !named.has(output.column)) {
      named.set(output.column, {...output, id: output.column});
    }
  }
  return [...named.values()];
}
