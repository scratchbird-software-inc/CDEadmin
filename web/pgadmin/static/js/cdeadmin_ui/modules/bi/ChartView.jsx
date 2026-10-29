/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useId, useMemo, useRef} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import BaseChart from 'sources/chartjs';
import {Box} from '../../primitives/Layout';
import {EmptyState} from '../../feedback/EmptyState';

function metricText(value) {
  if(value === null || value === undefined) return '—';
  const number = Number(value);
  return typeof value !== 'boolean' && value !== '' && Number.isFinite(number) ?
    number.toLocaleString() : String(value);
}

/**
 * Draw a buildChart() result with the shared BaseChart wrapper. `chart` must
 * be referentially stable between renders (the wrapper redraws on change).
 */
export default function ChartView({chart, title, onMark, height = 340}) {
  const id = useId();
  // Chart.js keeps the options it was created with, so the click handler reads the latest callback.
  const latest = useRef(onMark);
  useEffect(() => { latest.current = onMark; }, [onMark]);
  const options = useMemo(() => chart.kind === 'chart' && onMark ? {
    ...chart.options,
    onClick: (_event, elements) => {
      if(elements?.length) latest.current?.({index: elements[0].index, datasetIndex: elements[0].datasetIndex});
    },
  } : chart.options, [chart, Boolean(onMark)]);
  if(chart.kind === 'empty') return <EmptyState message={chart.reason} />;
  if(chart.kind === 'metric') {
    return <Box role="img" aria-label={gettext('%s: %s', chart.label, metricText(chart.value))}
      sx={{display: 'grid', placeItems: 'center', minHeight: 160, gap: 0.5}}>
      <Box sx={{fontSize: '2.75rem', fontWeight: 600, color: 'primary.main'}}>{metricText(chart.value)}</Box>
      <Box sx={{fontSize: '0.875rem', color: 'text.secondary'}}>{chart.label}</Box>
    </Box>;
  }
  if(chart.kind !== 'chart') return null;
  return <Box role="img" aria-label={title} sx={{height, position: 'relative', minWidth: 0}}>
    <BaseChart id={`bi-chart-${id.replace(/[^A-Za-z0-9_-]/g, '')}`} type={chart.type}
      data={chart.data} options={options} />
  </Box>;
}

ChartView.propTypes = {
  chart: PropTypes.shape({kind: PropTypes.string.isRequired}).isRequired,
  title: PropTypes.string.isRequired,
  onMark: PropTypes.func,
  height: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
};
