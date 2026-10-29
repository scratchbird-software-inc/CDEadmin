/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../../../primitives/Layout';
import {Button} from '../../../primitives/Button';
import {Checkbox} from '../../../primitives/Choice';
import {Badge, Banner} from '../../../feedback/Indicators';
import {EmptyState} from '../../../feedback/EmptyState';
import {embeddedContent} from './modelDraft';

const message = (error) => error?.message || String(error);

function Table({label, columns, rows, empty}) {
  if(!rows.length) return <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>{empty}</Box>;
  return <Box sx={{overflowX: 'auto'}}>
    <Box component="table" aria-label={label} sx={{borderCollapse: 'collapse', width: '100%', fontSize: '0.8125rem'}}>
      <Box component="thead"><Box component="tr">
        {columns.map((column) => <Box key={column.key} component="th" scope="col" sx={headerSx}>{column.label}</Box>)}
      </Box></Box>
      <Box component="tbody">
        {rows.map((row, index) => <Box component="tr" key={row.id ?? index}>
          {columns.map((column) => <Box key={column.key} component="td" sx={cellSx}>
            {column.render ? column.render(row) : row[column.key]}</Box>)}
        </Box>)}
      </Box>
    </Box>
  </Box>;
}

Table.propTypes = {
  label: PropTypes.string.isRequired, columns: PropTypes.array.isRequired, rows: PropTypes.array.isRequired,
  empty: PropTypes.node,
};

const headerSx = {textAlign: 'left', fontSize: '0.75rem', fontWeight: 600, p: 0.5, borderBottom: '1px solid',
  borderColor: 'divider', whiteSpace: 'nowrap'};
const cellSx = {p: 0.5, verticalAlign: 'top', borderBottom: '1px solid', borderColor: 'divider'};

function Part({title, children}) {
  return <Box component="section" aria-label={title} sx={{border: '1px solid', borderColor: 'divider', p: 1}}>
    <Box component="h3" sx={{m: 0, mb: 1, fontSize: '0.8125rem', fontWeight: 600}}>{title}</Box>
    {children}
  </Box>;
}

Part.propTypes = {title: PropTypes.string.isRequired, children: PropTypes.node};

const ACTION_STATUS = {create: 'success', exists: 'neutral', skipped: 'warning', blocked: 'warning', error: 'error'};

function actionLabel(action, dryRun) {
  if(action === 'create') return dryRun ? gettext('Would create') : gettext('Created');
  return {exists: gettext('Already migrated'), skipped: gettext('Skipped'), blocked: gettext('Blocked'),
    error: gettext('Error')}[action] || action;
}

function MigrationReport({report}) {
  const rows = [
    ...report.questions.map((item) => ({id: `q-${item.visualization_id}`, kind: gettext('Question'),
      source: item.visualization_id, name: item.name, action: item.action, fidelity: item.fidelity,
      detail: [...(item.losses || []), item.reason, item.error].filter(Boolean)})),
    ...report.dashboards.map((item) => ({id: `d-${item.model_dashboard_id}`, kind: gettext('Dashboard'),
      source: item.model_dashboard_id, name: item.name, action: item.action, fidelity: null,
      detail: [item.reason, item.error].filter(Boolean)})),
  ];
  return <Stack gap="compact" data-cdeadmin-qa-key="bi.models.migration.report">
    <Box role="status" sx={{fontSize: '0.8125rem'}}>
      {report.dry_run ?
        gettext('Preview of migrating revision %s. Nothing was created.', report.model_revision) :
        gettext('Migrated revision %s.', report.model_revision)}
      {' '}{report.collection?.name ? gettext('Collection: %s (%s).', report.collection.name, report.collection.action) : ''}
    </Box>
    <Table label={gettext('Migration result')} empty={gettext('Nothing to migrate.')} rows={rows} columns={[
      {key: 'kind', label: gettext('Kind')}, {key: 'source', label: gettext('Model item')},
      {key: 'name', label: gettext('BI name')},
      {key: 'action', label: gettext('Result'), render: (row) => <Badge status={ACTION_STATUS[row.action] || 'neutral'}
        label={actionLabel(row.action, report.dry_run)} />},
      {key: 'fidelity', label: gettext('Fidelity'), render: (row) => row.fidelity || ''},
      {key: 'detail', label: gettext('Details'), render: (row) => row.detail.map((text) =>
        <Box key={text} sx={{fontSize: '0.75rem'}}>{text}</Box>)},
    ]} />
  </Stack>;
}

MigrationReport.propTypes = {report: PropTypes.object.isRequired};

function Migration({client, record, dirty}) {
  const [acceptLoss, setAcceptLoss] = useState(false);
  const [busy, setBusy] = useState('');
  const [report, setReport] = useState(null);
  const [error, setError] = useState('');
  const run = async (dryRun) => {
    setBusy(dryRun ? 'preview' : 'apply');
    setError('');
    try {
      setReport(await client.migrate(record.model_id, {dryRun, acceptLoss}));
    } catch(caught) {
      setError(message(caught));
    } finally {
      setBusy('');
    }
  };
  return <Part title={gettext('Move to BI questions and dashboards')}>
    <Stack gap="compact">
      <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
        {gettext('Copies each chart into a saved question and each dashboard into a BI dashboard. The model keeps its own copies because its reports still use them, and running this again never creates duplicates.')}
      </Box>
      {!record && <Banner status="info">{gettext('Save the model first; the migration reads the saved revision.')}</Banner>}
      {record && dirty && <Banner status="warning">
        {gettext('There are unsaved edits. The migration reads saved revision %s.', record.revision)}</Banner>}
      {error && <Banner status="error">{error}</Banner>}
      <Stack direction="row" gap="comfortable" sx={{alignItems: 'center', flexWrap: 'wrap'}}>
        <Button disabled={!record} loading={busy === 'preview'} onClick={() => run(true)}>
          {gettext('Preview migration')}</Button>
        <Button intent="primary" disabled={!record} loading={busy === 'apply'} onClick={() => run(false)}>
          {gettext('Migrate to BI')}</Button>
        <Checkbox size="small" label={gettext('Also migrate charts that lose features')} checked={acceptLoss}
          onChange={setAcceptLoss} />
      </Stack>
      {report && <MigrationReport report={report} />}
    </Stack>
  </Part>;
}

Migration.propTypes = {client: PropTypes.object.isRequired, record: PropTypes.object, dirty: PropTypes.bool};

function Scheduling({client, record, reports, catalog}) {
  const [grants, setGrants] = useState(catalog.delegations || []);
  const [occurrences, setOccurrences] = useState([]);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const available = Boolean(catalog.capabilities?.scheduled_report_execution);
  const published = record?.status === 'published';

  const refresh = useCallback(async (reportId = null) => {
    const [granted, listed] = await Promise.all([client.grants(), client.occurrences(reportId)]);
    setGrants(granted);
    setOccurrences(listed);
  }, [client]);
  const act = async (key, work, reportId) => {
    setBusy(key);
    setError('');
    try {
      await work();
      await refresh(reportId);
    } catch(caught) {
      setError(message(caught));
    } finally {
      setBusy('');
    }
  };
  const active = (reportId) => grants.some((item) => item.report_id === reportId && item.state === 'active');
  if(!available) {
    return <Banner status="info">{gettext('Automatic execution needs provider query execution and an operator-configured worker. Schedule definitions are stored but nothing runs them on this endpoint.')}</Banner>;
  }
  return <Stack gap="compact">
    {error && <Banner status="error">{error}</Banner>}
    {!published && <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
      {gettext('Publish the model to authorize its scheduled reports.')}</Box>}
    {published && reports.filter((report) => report.schedule_id).map((report) => <Stack key={report.id} direction="row"
      gap="compact" sx={{alignItems: 'center', flexWrap: 'wrap'}}>
      <Box sx={{minWidth: 160}}>{report.name}</Box>
      {active(report.id) ?
        <Button size="small" loading={busy === `revoke-${report.id}`} onClick={() =>
          act(`revoke-${report.id}`, () => client.revoke(report.id), report.id)}>
          {gettext('Revoke schedule')}</Button> :
        <Button size="small" loading={busy === `authorize-${report.id}`} onClick={() =>
          act(`authorize-${report.id}`, () => client.authorize(record.model_id, report.id), report.id)}>
          {gettext('Authorize schedule')}</Button>}
      <Button size="small" loading={busy === `refresh-${report.id}`} onClick={() =>
        act(`refresh-${report.id}`, async () => {}, report.id)}>{gettext('Refresh occurrences')}</Button>
    </Stack>)}
    {occurrences.map((item) => <Stack key={item.occurrence_id} direction="row" gap="compact"
      aria-label={gettext('Scheduled report occurrence')} sx={{alignItems: 'center', fontSize: '0.8125rem'}}>
      <span>{item.report_id} · {item.scheduled_for} · {item.state} · {item.phase}</span>
      {['scheduled', 'claimed', 'executing', 'delivering'].includes(item.state) &&
        <Button size="small" loading={busy === `cancel-${item.occurrence_id}`} onClick={() =>
          act(`cancel-${item.occurrence_id}`, () => client.cancel(item.occurrence_id), item.report_id)}>
          {gettext('Cancel scheduled occurrence')}</Button>}
    </Stack>)}
  </Stack>;
}

Scheduling.propTypes = {
  client: PropTypes.object.isRequired, record: PropTypes.object, reports: PropTypes.array.isRequired,
  catalog: PropTypes.object.isRequired,
};

const list = (items) => (items || []).join(', ');

/**
 * What a model still carries from before the BI module: charts, dashboards,
 * reports and schedules. Shown read-only; new charts and dashboards are made
 * in BI. Reports and schedules keep running through the report scheduler.
 */
export default function EmbeddedPanel({client, record, dirty, definition, catalog}) {
  useEffect(() => { /* the scheduler list is loaded on demand */ }, []);
  const content = embeddedContent(definition);
  const nothing = Object.values(content).every((items) => !items.length);
  return <Stack gap="standard" data-cdeadmin-qa-key="bi.models.tab.embedded">
    <Banner status="info">
      {gettext('New charts and dashboards are built in BI questions and dashboards. What this model already holds stays readable here, and its reports keep running through the report scheduler.')}
    </Banner>
    {nothing && <EmptyState message={gettext('This model has no charts, dashboards, reports or schedules.')} />}
    {!nothing && <>
      <Migration client={client} record={record} dirty={dirty} />
      <Part title={gettext('Charts')}>
        <Table label={gettext('Charts')} empty={gettext('No charts.')} rows={content.visualizations} columns={[
          {key: 'name', label: gettext('Name')}, {key: 'chart_type', label: gettext('Type')},
          {key: 'measures', label: gettext('Measures'), render: (row) => list(row.query?.measures)},
          {key: 'levels', label: gettext('Axes'), render: (row) => list([
            ...(row.query?.axes?.rows || []), ...(row.query?.axes?.columns || []), ...(row.query?.axes?.pages || [])])},
          {key: 'encodings', label: gettext('Encodings'),
            render: (row) => `${row.encodings?.x || '-'} → ${row.encodings?.y || '-'}`},
        ]} />
      </Part>
      <Part title={gettext('Dashboards')}>
        <Table label={gettext('Dashboards')} empty={gettext('No dashboards.')} rows={content.dashboards} columns={[
          {key: 'name', label: gettext('Name')},
          {key: 'tiles', label: gettext('Charts'), render: (row) => list(row.tiles.map((tile) => tile.visualization_id))},
          {key: 'cross_filtering', label: gettext('Cross-filtering'),
            render: (row) => row.cross_filtering ? gettext('Enabled') : gettext('Independent tiles')},
        ]} />
      </Part>
      <Part title={gettext('Reports')}>
        <Table label={gettext('Reports')} empty={gettext('No reports.')} rows={content.reports} columns={[
          {key: 'name', label: gettext('Name')}, {key: 'dashboard_id', label: gettext('Dashboard')},
          {key: 'schedule_id', label: gettext('Schedule'), render: (row) => row.schedule_id || gettext('Manual')},
          {key: 'export_formats', label: gettext('Formats'), render: (row) => list(row.export_formats)},
        ]} />
        <Box sx={{mt: 1}}><Scheduling client={client} record={record} reports={content.reports} catalog={catalog} /></Box>
        <Box sx={{mt: 1, fontSize: '0.75rem', color: 'text.secondary'}} data-cdeadmin-qa-key="bi.models.subscription-todo">
          {gettext('Converting a report to a BI subscription is not available yet. It needs the alerts and subscriptions feature, which has not been released; reports stay in the model until then.')}
        </Box>
      </Part>
      <Part title={gettext('Schedules')}>
        <Table label={gettext('Schedules')} empty={gettext('No schedules.')} rows={content.schedules} columns={[
          {key: 'name', label: gettext('Name')}, {key: 'expression', label: gettext('Cron expression')},
          {key: 'timezone', label: gettext('Timezone')},
          {key: 'enabled', label: gettext('Enabled'), render: (row) => row.enabled ? gettext('Yes') : gettext('No')},
          {key: 'delivery', label: gettext('Delivery'), render: (row) => row.delivery?.profile_id ?
            `${row.delivery.profile_id} (${row.delivery.format})` : gettext('None')},
        ]} />
      </Part>
    </>}
  </Stack>;
}

EmbeddedPanel.propTypes = {
  client: PropTypes.object.isRequired, record: PropTypes.object, dirty: PropTypes.bool,
  definition: PropTypes.object, catalog: PropTypes.object.isRequired,
};
