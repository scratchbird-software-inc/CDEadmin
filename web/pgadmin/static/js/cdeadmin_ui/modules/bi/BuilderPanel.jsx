/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useMemo} from 'react';
import PropTypes from 'prop-types';
import {Stack} from '../../primitives/Layout';
import {errorAt} from './validateState';
import {orderTargets} from './outputs';
import SourcePicker from './SourcePicker';
import ColumnsSection from './ColumnsSection';
import SummariesSection from './SummariesSection';
import ModelFieldsSection from './ModelFieldsSection';
import FiltersSection from './FiltersSection';
import OrderSection from './OrderSection';

/** The visual builder: source, columns or model fields, summaries, filters, sort. */
export default function BuilderPanel({state, dispatch, catalog, columns, columnsLoading, model, modelLoading, errors}) {
  const summarized = state.aggregations.length > 0;
  const isModel = state.source.kind === 'model';
  const filterFields = useMemo(() => isModel ?
    (model?.dimensions || []).filter((dimension) => dimension.field).map((dimension) => ({
      id: dimension.id, label: dimension.name, category: dimension.category, field: dimension.field})) :
    columns.map((column) => ({id: column.name, label: column.name, category: column.category, column: column.name})),
  [isModel, model, columns]);
  const targets = useMemo(() => orderTargets(state, model), [state, model]);
  const selection = errorAt(errors, 'selection');

  return <Stack gap="compact" data-cdeadmin-qa-key="bi.builder">
    <SourcePicker source={state.source} sources={catalog.sources} models={catalog.models}
      status={catalog.status} error={catalog.error} validation={errorAt(errors, 'source')}
      onSelectTable={(relation) => dispatch({type: 'selectTable', relation})}
      onSelectModel={(id, revision) => dispatch({type: 'selectModel', id, revision})} />
    {isModel ?
      <ModelFieldsSection model={model} dimensions={state.dimensions} measures={state.measures}
        loading={modelLoading} error={selection}
        onToggleDimension={(id, on) => dispatch({type: on ? 'addDimension' : 'removeDimension', id})}
        onToggleMeasure={(id, on) => dispatch({type: on ? 'addMeasure' : 'removeMeasure', id})} /> :
      <>
        <ColumnsSection columns={columns} loading={columnsLoading} summarized={summarized}
          selected={summarized ? state.groupBy : state.columns} error={summarized ? '' : selection}
          onToggle={(column, on) => dispatch({
            type: summarized ? (on ? 'addGroupBy' : 'removeGroupBy') : (on ? 'addColumn' : 'removeColumn'), column})} />
        <SummariesSection aggregations={state.aggregations} columns={columns} errors={errors} dispatch={dispatch} />
      </>}
    <FiltersSection filters={state.filters} fields={filterFields} parameters={state.parameters}
      errors={errors} dispatch={dispatch} />
    <OrderSection orderBy={state.orderBy} targets={targets} limit={state.limit} errors={errors} dispatch={dispatch} />
  </Stack>;
}

BuilderPanel.propTypes = {
  state: PropTypes.object.isRequired,
  dispatch: PropTypes.func.isRequired,
  catalog: PropTypes.shape({
    status: PropTypes.string.isRequired, error: PropTypes.string,
    sources: PropTypes.array.isRequired, models: PropTypes.array.isRequired,
  }).isRequired,
  columns: PropTypes.array.isRequired,
  columnsLoading: PropTypes.bool,
  model: PropTypes.object,
  modelLoading: PropTypes.bool,
  errors: PropTypes.array.isRequired,
};
