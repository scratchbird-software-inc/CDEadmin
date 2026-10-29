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
import {Select} from '../../../primitives/Choice';
import {Badge, Banner} from '../../../feedback/Indicators';
import {EmptyState} from '../../../feedback/EmptyState';
import CodeEditor from '../../../editors/CodeEditor';

const message = (error) => error?.message || String(error);
const STATUS_BADGE = {draft: 'neutral', published: 'success', archived: 'warning'};

export function StatusBadge({status}) {
  return <Badge status={STATUS_BADGE[status] || 'neutral'} label={status} />;
}

StatusBadge.propTypes = {status: PropTypes.string};

/** Sources, joins and the objects built on them, as the validator derived them. */
export function LineagePanel({lineage, busy, onRefresh}) {
  const nodes = lineage?.nodes || [];
  const edges = lineage?.edges || [];
  const label = new Map(nodes.map((node) => [node.id, node.label || node.id]));
  return <Stack gap="compact" data-cdeadmin-qa-key="bi.models.tab.lineage">
    <Box><Button loading={busy} onClick={onRefresh}>{gettext('Refresh lineage')}</Button></Box>
    {!lineage ? <EmptyState message={gettext('Refresh lineage to see how sources feed this model.')} /> : <>
      <Box component="ul" aria-label={gettext('Lineage nodes')} sx={{m: 0, pl: 2}}>
        {nodes.map((node) => <Box component="li" key={node.id}>
          <Box component="code">{node.kind}</Box> {node.label}</Box>)}
      </Box>
      <Box component="ul" aria-label={gettext('Lineage edges')} sx={{m: 0, pl: 2}}>
        {edges.map((edge, index) => <Box component="li" key={index}>
          {label.get(edge.from) || edge.from} → {label.get(edge.to) || edge.to} ({edge.kind})</Box>)}
      </Box>
    </>}
  </Stack>;
}

LineagePanel.propTypes = {lineage: PropTypes.object, busy: PropTypes.bool, onRefresh: PropTypes.func.isRequired};

const show = (value) => value === undefined ? '' : JSON.stringify(value, null, 1);

/** Every stored revision, and a field-level comparison of any two. */
export function RevisionsPanel({client, record}) {
  const [history, setHistory] = useState([]);
  const [left, setLeft] = useState('');
  const [right, setRight] = useState('');
  const [comparison, setComparison] = useState(null);
  const [error, setError] = useState('');
  const modelId = record?.model_id;
  const revision = record?.revision;

  useEffect(() => {
    if(!modelId) return undefined;
    let cancelled = false;
    client.history(modelId).then((items) => {
      if(cancelled) return;
      setHistory(items);
      const ordered = items.map((item) => item.revision).sort((a, b) => b - a);
      setRight(String(ordered[0] ?? ''));
      setLeft(String(ordered[1] ?? ordered[0] ?? ''));
      setComparison(null);
    }, (caught) => { if(!cancelled) setError(message(caught)); });
    return () => { cancelled = true; };
  }, [client, modelId, revision]);

  const compare = async () => {
    setError('');
    try {
      setComparison(await client.compare(modelId, Number(left), Number(right)));
    } catch(caught) {
      setError(message(caught));
    }
  };
  if(!modelId) return <EmptyState message={gettext('Save the model to start its revision history.')} />;
  const choices = history.map((item) => ({value: String(item.revision), label: `r${item.revision} · ${item.status}`}));
  return <Stack gap="compact" data-cdeadmin-qa-key="bi.models.tab.revisions">
    {error && <Banner status="error">{error}</Banner>}
    <Box component="ul" aria-label={gettext('Revision history')} sx={{m: 0, pl: 0, listStyle: 'none'}}>
      {history.map((item) => <Stack component="li" key={item.revision} direction="row" gap="compact"
        sx={{alignItems: 'center', py: 0.25}}>
        <span>r{item.revision}</span><StatusBadge status={item.status} /><span>{item.created_at}</span>
      </Stack>)}
    </Box>
    {history.length > 1 && <Stack direction="row" gap="compact" sx={{alignItems: 'flex-end', flexWrap: 'wrap'}}>
      <Select size="small" label={gettext('Compare')} value={left} options={choices} onChange={setLeft} />
      <Select size="small" label={gettext('with')} value={right} options={choices} onChange={setRight} />
      <Button onClick={compare}>{gettext('Compare revisions')}</Button>
    </Stack>}
    {comparison && (comparison.changes.length ? <Box component="table" aria-label={gettext('Revision changes')}
      sx={{borderCollapse: 'collapse', fontSize: '0.8125rem', width: '100%'}}>
      <Box component="thead"><Box component="tr">
        {[gettext('Field'), `r${comparison.left_revision}`, `r${comparison.right_revision}`].map((title) =>
          <Box key={title} component="th" scope="col" sx={{textAlign: 'left', p: 0.5, borderBottom: '1px solid',
            borderColor: 'divider'}}>{title}</Box>)}
      </Box></Box>
      <Box component="tbody">
        {comparison.changes.map((change) => <Box component="tr" key={change.field}>
          <Box component="td" sx={{p: 0.5, verticalAlign: 'top'}}>{change.field}</Box>
          <Box component="td" sx={{p: 0.5, verticalAlign: 'top'}}><pre style={{margin: 0}}>{show(change.before)}</pre></Box>
          <Box component="td" sx={{p: 0.5, verticalAlign: 'top'}}><pre style={{margin: 0}}>{show(change.after)}</pre></Box>
        </Box>)}
      </Box>
    </Box> : <Banner status="info">{gettext('These revisions are identical.')}</Banner>)}
  </Stack>;
}

RevisionsPanel.propTypes = {client: PropTypes.object.isRequired, record: PropTypes.object};

/** The whole model document, for what the typed tabs do not cover. Applying it replaces the draft. */
export function AdvancedPanel({definition, readOnly, onApply}) {
  const current = JSON.stringify(definition, null, 2);
  const [text, setText] = useState(current);
  const [error, setError] = useState('');
  useEffect(() => { setText(current); setError(''); }, [current]);
  const apply = () => {
    let parsed;
    try {
      parsed = JSON.parse(text);
    } catch(caught) {
      setError(gettext('The JSON is not valid: %s', message(caught)));
      return;
    }
    if(!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      setError(gettext('The model must be a JSON object.'));
      return;
    }
    setError('');
    onApply(parsed);
  };
  return <Stack gap="compact" data-cdeadmin-qa-key="bi.models.tab.advanced">
    <Banner status="info">{gettext('The complete model document. Everything here can be set from the other tabs except new charts, dashboards, reports and schedules, which are only editable as JSON. Validate the model after applying.')}</Banner>
    {error && <Banner status="error">{error}</Banner>}
    <Box sx={{height: 360}}>
      <CodeEditor label={gettext('Model JSON')} language="json" value={text} readonly={readOnly}
        onChange={setText} />
    </Box>
    <Box><Button disabled={readOnly || text === current} onClick={apply}>{gettext('Apply JSON')}</Button></Box>
  </Stack>;
}

AdvancedPanel.propTypes = {definition: PropTypes.object, readOnly: PropTypes.bool, onApply: PropTypes.func.isRequired};

/** Provider plans for the model's materializations, with the confirmed apply step. */
export function MaterializationPlans({client, record, definition, catalog, dirty}) {
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const executable = Boolean(catalog.capabilities?.materialization?.execution_available);
  const items = definition?.materializations || [];

  const preview = useCallback(async (id) => {
    setBusy(id);
    setError('');
    setDone(false);
    setPlan(null);
    try {
      setPlan(await client.materializationPlan(record.model_id, id));
    } catch(caught) {
      setError(message(caught));
    } finally {
      setBusy('');
    }
  }, [client, record]);
  const apply = async () => {
    setBusy('apply');
    setError('');
    try {
      await client.applyPlan(plan);
      setPlan(null);
      setDone(true);
    } catch(caught) {
      setError(message(caught));
    } finally {
      setBusy('');
    }
  };
  if(!items.length) return null;
  return <Stack gap="compact" aria-label={gettext('Materialization plans')}>
    {!executable && <Banner status="warning">
      {gettext('This provider does not activate physical semantic materializations.')}</Banner>}
    {dirty && <Banner status="info">{gettext('Plans are made from the saved revision.')}</Banner>}
    {error && <Banner status="error">{error}</Banner>}
    {done && <Banner status="success">{gettext('The materialization was created.')}</Banner>}
    {items.map((item) => <Stack key={item.id} direction="row" gap="compact" sx={{alignItems: 'center'}}>
      <span>{item.name || item.id}</span>
      <Button size="small" disabled={!record || !executable} loading={busy === item.id}
        onClick={() => preview(item.id)}>{gettext('Preview provider plan')}</Button>
    </Stack>)}
    {plan && <>
      <Box component="pre" aria-label={gettext('Semantic materialization plan')} sx={{m: 0, p: 1, overflow: 'auto',
        maxHeight: 280, whiteSpace: 'pre-wrap', bgcolor: 'background.default', fontSize: '0.75rem'}}>
        {JSON.stringify(plan, null, 2)}</Box>
      <Box><Button intent="destructive" loading={busy === 'apply'}
        disabled={plan.state !== 'ready' || !plan.execution_available} onClick={apply}>
        {gettext('Confirm and create materialization')}</Button></Box>
    </>}
  </Stack>;
}

MaterializationPlans.propTypes = {
  client: PropTypes.object.isRequired, record: PropTypes.object, definition: PropTypes.object,
  catalog: PropTypes.object.isRequired, dirty: PropTypes.bool,
};
