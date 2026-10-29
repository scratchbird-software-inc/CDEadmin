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
import gettext from 'sources/gettext';
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {Checkbox, Select} from '../../primitives/Choice';
import {Badge, Banner} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import PagedDataGrid from '../../data/PagedDataGrid';
import {CHART_TYPES} from './queryState';
import {buildChart, chartTypeLabel, effectiveSettings} from './chartData';
import ChartView from './ChartView';

function ChartSettings({table, settings, onChange}) {
  const effective = effectiveSettings(settings, table);
  const toggle = (key, on) => {
    const next = on ? [...effective.y, key] : effective.y.filter((item) => item !== key);
    onChange({...settings, x: effective.x, y: next});
  };
  return <Box role="group" aria-label={gettext('Chart settings')}
    sx={{display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'flex-start'}}>
    <Select size="small" label={gettext('X axis')} value={effective.x}
      options={table.columns.map((column) => ({value: column.key, label: column.name}))}
      onChange={(x) => onChange({...settings, x, y: effective.y})} />
    <Box role="group" aria-label={gettext('Y axis series')} sx={{display: 'flex', flexWrap: 'wrap'}}>
      {table.columns.map((column) => <Checkbox key={column.key} size="small" label={column.name}
        checked={effective.y.includes(column.key)} onChange={(on) => toggle(column.key, on)} />)}
    </Box>
  </Box>;
}

ChartSettings.propTypes = {
  table: PropTypes.object.isRequired, settings: PropTypes.object.isRequired, onChange: PropTypes.func.isRequired,
};

/** Result of a run: chart type chooser, table or chart, paging and policy notes. */
export default function ResultPane({execution, running, error, visualization, onVisualization, onLoadMore, loadingMore}) {
  const table = execution?.table;
  const chart = useMemo(() => table ? buildChart(visualization.type, table, visualization.settings) : null,
    [table, visualization]);
  const columns = useMemo(() => (table?.columns || []).map((column) => ({
    key: column.key, name: column.name, engineType: column.type, resizable: true})), [table]);
  return <Box data-cdeadmin-qa-key="bi.result" sx={{display: 'grid', gap: 1, minWidth: 0}}>
    {running && <Box role="status" sx={{fontSize: '0.75rem'}}>{gettext('Running...')}</Box>}
    {error && <Banner status="error">{error}</Banner>}
    {!table && !running && !error && <EmptyState message={gettext('Run the question to see its result.')} />}
    {table && <>
      <Stack direction="row" gap="comfortable" sx={{alignItems: 'center', flexWrap: 'wrap'}}>
        <Select size="small" label={gettext('Display as')} value={visualization.type}
          options={CHART_TYPES.map((type) => ({value: type, label: chartTypeLabel(type)}))}
          onChange={(type) => onVisualization({type, settings: visualization.settings})} />
        <Box role="status" sx={{fontSize: '0.75rem'}}>
          {gettext('%s of %s rows loaded', table.rows.length, execution.total)}
        </Box>
        {execution.cache?.hit && <Badge status="info" label={gettext('From cache')} />}
        {execution.redacted.length > 0 && <Badge status="warning"
          label={gettext('Redacted: %s', execution.redacted.join(', '))} />}
      </Stack>
      {visualization.type !== 'table' && visualization.type !== 'metric' &&
        <ChartSettings table={table} settings={visualization.settings}
          onChange={(settings) => onVisualization({type: visualization.type, settings})} />}
      {visualization.type === 'table' ?
        <Box sx={{height: 360, minWidth: 0}}>
          <PagedDataGrid gridId="bi/result" aria-label={gettext('Query result')} readOnly
            columns={columns} rows={table.rows} />
        </Box> :
        <ChartView chart={chart} title={gettext('%s chart of the query result', chartTypeLabel(visualization.type))} />}
      {execution.cursor && <Stack direction="row">
        <Button loading={loadingMore} onClick={onLoadMore}>{gettext('Load more rows')}</Button>
      </Stack>}
    </>}
  </Box>;
}

ResultPane.propTypes = {
  execution: PropTypes.shape({
    table: PropTypes.object, total: PropTypes.number, cursor: PropTypes.string,
    cache: PropTypes.object, redacted: PropTypes.array.isRequired,
  }),
  running: PropTypes.bool,
  error: PropTypes.string,
  visualization: PropTypes.shape({type: PropTypes.string.isRequired, settings: PropTypes.object.isRequired}).isRequired,
  onVisualization: PropTypes.func.isRequired,
  onLoadMore: PropTypes.func.isRequired,
  loadingMore: PropTypes.bool,
};
