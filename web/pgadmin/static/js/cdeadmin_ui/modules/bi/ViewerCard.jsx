/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {Badge, Banner} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import PagedDataGrid from '../../data/PagedDataGrid';
import {buildChart, chartTypeLabel, effectiveSettings} from './chartData';
import {formatClock, markColumn} from './dashboardViewer';
import {cardLabel} from './dashboardState';
import ChartView from './ChartView';
import MarkdownView from './MarkdownView';

function MetricPanel({panel}) {
  return <Box component="table" aria-label={gettext('Metrics of %s', panel.panel_id)}
    sx={{width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem',
      '& th, & td': {textAlign: 'left', p: 0.5, borderBottom: '1px solid', borderColor: 'divider'}}}>
    <thead>
      <tr>
        <th scope="col">{gettext('Measure')}</th><th scope="col">{gettext('Value')}</th>
        <th scope="col">{gettext('Unit')}</th><th scope="col">{gettext('Rate')}</th>
      </tr>
    </thead>
    <tbody>
      {panel.rows.map((row) => <tr key={row.id}>
        <td>{row.measure}</td><td>{row.value}</td><td>{row.unit}</td><td>{row.rate}</td>
      </tr>)}
    </tbody>
  </Box>;
}

MetricPanel.propTypes = {panel: PropTypes.object.isRequired};

function QuestionResult({card, execution, visualization, interactive, onActivate}) {
  const table = execution.table;
  const [showData, setShowData] = useState(false);
  const chart = useMemo(() => buildChart(visualization.type, table, visualization.settings),
    [table, visualization]);
  const columns = useMemo(() => table.columns.map((column) => ({
    key: column.key, name: column.name, engineType: column.type, resizable: true})), [table]);
  const settings = useMemo(() => effectiveSettings(visualization.settings, table), [visualization, table]);
  const asTable = visualization.type === 'table' || showData;
  const activate = interactive ? (row, column) => onActivate(card, row, column) : undefined;
  return <Box sx={{display: 'grid', gap: 0.5, height: '100%', gridTemplateRows: 'auto minmax(0, 1fr)'}}>
    <Stack direction="row" gap="compact" sx={{alignItems: 'center', flexWrap: 'wrap'}}>
      {visualization.type !== 'table' && <Button size="small" aria-pressed={showData}
        aria-label={showData ? gettext('Show %s as a chart', cardLabel(card)) : gettext('Show %s as a table', cardLabel(card))}
        onClick={() => setShowData(!showData)}>{showData ? gettext('Show chart') : gettext('Show data')}</Button>}
      {interactive && <Box component="span" sx={{fontSize: '0.7rem', color: 'text.secondary'}}>
        {asTable ? gettext('Select a cell and press Enter, or click it, to filter or drill through.') :
          gettext('Click a mark to filter or drill through. Show data for the keyboard.')}
      </Box>}
      {execution.redacted.length > 0 && <Badge status="warning" label={gettext('Redacted: %s', execution.redacted.join(', '))} />}
      <Box component="span" sx={{fontSize: '0.7rem', color: 'text.secondary'}}>
        {gettext('%s of %s rows', table.rows.length, execution.total)}
      </Box>
    </Stack>
    <Box sx={{minHeight: 0, minWidth: 0}}>
      {asTable ?
        <Box sx={{height: '100%', minHeight: 140}}>
          <PagedDataGrid gridId={`bi/dashboard/${card.id}`} aria-label={gettext('Result of %s', cardLabel(card))}
            readOnly pagination={false} columns={columns} rows={table.rows}
            onCellClick={activate ? (args) => activate(args.row, args.column.key) : undefined}
            onCellKeyDown={activate ? (args, event) => {
              if(event.key === 'Enter' && args.mode !== 'EDIT') activate(args.row, args.column.key);
            } : undefined} />
        </Box> :
        <ChartView chart={chart} height="100%"
          title={gettext('%s chart of %s', chartTypeLabel(visualization.type), cardLabel(card))}
          onMark={activate ? ({index, datasetIndex}) => {
            const row = table.rows[index];
            if(row) activate(row, markColumn(settings, datasetIndex));
          } : undefined} />}
    </Box>
  </Box>;
}

QuestionResult.propTypes = {
  card: PropTypes.object.isRequired, execution: PropTypes.object.isRequired,
  visualization: PropTypes.object.isRequired, interactive: PropTypes.bool, onActivate: PropTypes.func,
};

/**
 * One card in the viewer: title, when its data was produced (and whether the
 * result cache supplied it), refresh and full screen, then its content. A card
 * that is loading again or failed keeps showing its last result, marked stale.
 */
export default function ViewerCard({card, run, info, interactive, fullscreen, onRefresh, onFullscreen, onActivate}) {
  const title = cardLabel(card);
  const running = run?.status === 'loading';
  const execution = run?.execution;
  const visualization = card.visualization || info?.visualization || {type: 'table', settings: {}};
  return <Box component="article" aria-label={gettext('Card %s', title)} aria-busy={running || undefined}
    data-cdeadmin-qa-key="bi.dashboard.card.view"
    sx={{height: '100%', display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden',
      bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider'}}>
    <Stack direction="row" gap="compact" sx={{alignItems: 'center', p: 0.5, flexWrap: 'wrap'}}>
      <Box component="h3" sx={{m: 0, flex: 1, minWidth: 80, fontSize: '0.875rem', fontWeight: 600,
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>{title}</Box>
      {card.type === 'question' && <>
        {running && <Badge status="info" label={gettext('Updating')} />}
        {run?.stale && execution && <Badge status="warning" label={gettext('Stale')} />}
        {run?.status === 'ready' && !running && (run.cacheHit ?
          <Badge status="info" label={gettext('Cached at %s', formatClock(run.producedAt))} /> :
          <Badge status="success" label={gettext('Updated %s', formatClock(run.receivedAt))} />)}
        <Button size="small" loading={running} aria-label={gettext('Refresh %s', title)}
          onClick={() => onRefresh(card)}>{gettext('Refresh')}</Button>
      </>}
      <Button size="small" aria-label={fullscreen ? gettext('Exit full screen for %s', title) :
        gettext('Full screen for %s', title)} onClick={() => onFullscreen(fullscreen ? null : card.id)}>
        {fullscreen ? gettext('Exit full screen') : gettext('Full screen')}</Button>
    </Stack>
    <Box sx={{flex: 1, minHeight: 0, p: 1, overflow: 'auto'}}>
      {card.type === 'text' && <MarkdownView markdown={card.text.markdown} />}
      {card.type === 'metric_panel' && <MetricPanel panel={card.metric_panel} />}
      {card.type === 'question' && <>
        {run?.error && <Banner status="error">{gettext('This card could not run: %s', run.error)}</Banner>}
        {!execution && !run?.error && <Box role="status" sx={{fontSize: '0.8125rem'}}>
          {running ? gettext('Loading...') : gettext('Waiting to run.')}</Box>}
        {execution && (execution.table.columns.length ?
          <QuestionResult card={card} execution={execution} visualization={visualization}
            interactive={interactive} onActivate={onActivate} /> :
          <EmptyState message={gettext('The query returned no columns.')} />)}
      </>}
    </Box>
  </Box>;
}

ViewerCard.propTypes = {
  card: PropTypes.object.isRequired,
  run: PropTypes.object,
  info: PropTypes.object,
  interactive: PropTypes.bool,
  fullscreen: PropTypes.bool,
  onRefresh: PropTypes.func.isRequired,
  onFullscreen: PropTypes.func.isRequired,
  onActivate: PropTypes.func,
};
