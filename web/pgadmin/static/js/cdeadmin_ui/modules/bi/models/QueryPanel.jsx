/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../../../primitives/Layout';
import {Button} from '../../../primitives/Button';
import {Banner} from '../../../feedback/Indicators';
import {EmptyState} from '../../../feedback/EmptyState';
import ModelFields from './ModelFields';
import {modelOptionContext, queryForm} from './modelForm';
import {emptyQuery, queryErrors, toQuery} from './queryDraft';

const message = (error) => error?.message || String(error);

function download(name, content, type) {
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([content], {type}));
  link.download = name;
  link.click();
  URL.revokeObjectURL(link.href);
}

/** The pivot of a cellset result: levels and measures as columns, one row per cell. */
export function CellsetGrid({rendered}) {
  const view = rendered?.view_model || {};
  const [transposed, setTransposed] = useState(false);
  const [depth, setDepth] = useState((view.levels || []).length);
  const levels = (view.levels || []).slice(0, depth);
  const measures = view.measures || [];
  const cells = view.cells || [];
  const names = transposed ? [...measures, ...levels] : [...levels, ...measures];
  const value = (cell, name) => {
    const found = transposed ? (cell.measures?.[name] ?? cell.coordinates?.[name]) :
      (cell.coordinates?.[name] ?? cell.measures?.[name]);
    return found === null || found === undefined ? '' : String(found);
  };
  const exportCsv = () => {
    const quote = (item) => `"${String(item ?? '').replaceAll('"', '""')}"`;
    const rows = [[...levels, ...measures], ...cells.map((cell) => [
      ...levels.map((name) => cell.coordinates?.[name]), ...measures.map((name) => cell.measures?.[name])])];
    download('cellset.csv', rows.map((row) => row.map(quote).join(',')).join('\n'), 'text/csv');
  };
  return <Stack gap="compact" aria-label={gettext('Cube pivot results')}>
    <Stack direction="row" gap="compact" sx={{flexWrap: 'wrap'}}>
      <Button size="small" onClick={() => setTransposed((current) => !current)}>{gettext('Transpose axes')}</Button>
      <Button size="small" disabled={depth >= (view.levels || []).length}
        onClick={() => setDepth((current) => current + 1)}>{gettext('Drill down')}</Button>
      <Button size="small" disabled={depth <= 1} onClick={() => setDepth((current) => current - 1)}>
        {gettext('Drill up')}</Button>
      <Button size="small" onClick={exportCsv}>{gettext('Export CSV')}</Button>
      <Button size="small" onClick={() => download('cellset.json', JSON.stringify(view, null, 2), 'application/json')}>
        {gettext('Export JSON')}</Button>
    </Stack>
    {(view.slice || []).length > 0 && <Banner status="info">
      {gettext('Active slice')}: {JSON.stringify(view.slice)}</Banner>}
    {!cells.length ? <EmptyState message={gettext('The query returned no cells.')} /> :
      <Box sx={{overflow: 'auto', maxHeight: 420}}>
        <Box component="table" aria-label={gettext('Cube pivot cell grid')}
          sx={{borderCollapse: 'collapse', fontSize: '0.8125rem', width: '100%'}}>
          <Box component="thead"><Box component="tr">
            {names.map((name) => <Box key={name} component="th" scope="col" sx={{textAlign: 'left', p: 0.5,
              borderBottom: '1px solid', borderColor: 'divider', whiteSpace: 'nowrap'}}>{name}</Box>)}
          </Box></Box>
          <Box component="tbody">
            {cells.map((cell, index) => <Box component="tr" key={index}>
              {names.map((name) => <Box key={name} component="td" sx={{p: 0.5, borderBottom: '1px solid',
                borderColor: 'divider'}}>{value(cell, name)}</Box>)}
            </Box>)}
          </Box>
        </Box>
      </Box>}
  </Stack>;
}

CellsetGrid.propTypes = {rendered: PropTypes.object};

/**
 * Try the model: compile, diagnose and run a cube query against the stored model, or against the
 * unsaved draft when it differs. The query session is reused between runs and closed on unmount.
 */
export default function QueryPanel({client, record, dirty, built, draft, catalog}) {
  const [query, setQuery] = useState(emptyQuery);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [compiled, setCompiled] = useState(null);
  const [diagnostics, setDiagnostics] = useState(null);
  const [rendered, setRendered] = useState(null);
  const session = useRef('');
  const available = Boolean(catalog.capabilities?.execution_available);

  useEffect(() => () => {
    if(session.current) client.closeSession(session.current).catch(() => {});
  }, [client]);

  const form = useMemo(() => queryForm(catalog.capabilities || {}), [catalog.capabilities]);
  const context = useMemo(() => modelOptionContext(draft, built.definition), [draft, built.definition]);
  const errors = queryErrors(query);
  // a clean, saved model is queried by id; anything else is sent as the draft itself
  const target = record && !dirty ? {model_id: record.model_id} : {definition: built.definition};

  const run = useCallback(async (key, work) => {
    if(!built.definition || built.problems.length) {
      setError(built.problems.join(' ') || gettext('The model cannot be built yet.'));
      return;
    }
    const {query: document, problems} = toQuery(query, built.definition.parameters || []);
    if(problems.length || Object.keys(errors).length) {
      setError([...problems, ...Object.values(errors)].join(' '));
      return;
    }
    setBusy(key);
    setError('');
    try {
      await work(document);
    } catch(caught) {
      setError(message(caught));
    } finally {
      setBusy('');
    }
  }, [built, query, errors]);

  const compile = () => run('compile', async (document) => setCompiled(await client.compile(target, document)));
  const diagnose = () => run('diagnostics', async (document) =>
    setDiagnostics(await client.diagnostics(target, document)));
  const execute = () => run('execute', async (document) => {
    const value = await client.execute(target, document, session.current);
    session.current = value.session_id || value.occurrence?.session_id || session.current;
    const response = await client.poll(value.occurrence.occurrence_id);
    if(!response.rendered_result) throw new Error(gettext('The provider did not return a result page.'));
    setRendered(response.rendered_result);
  });

  if(!available) {
    return <Banner status="info">{gettext('This endpoint cannot execute semantic queries, so the model cannot be tried here. It can still be edited, validated and published.')}</Banner>;
  }
  return <Stack gap="standard" data-cdeadmin-qa-key="bi.models.tab.try">
    {dirty && <Banner status="info">{gettext('Queries run against your unsaved edits.')}</Banner>}
    {error && <Banner status="error">{error}</Banner>}
    <ModelFields tab={form.tabs[0]} draft={query} context={context} errors={errors}
      onChange={(field, value) => setQuery((current) => ({...current, [field]: value}))} />
    <Stack direction="row" gap="compact" sx={{flexWrap: 'wrap'}}>
      <Button loading={busy === 'compile'} onClick={compile}>{gettext('Compile query')}</Button>
      <Button loading={busy === 'diagnostics'} onClick={diagnose}>{gettext('Query diagnostics')}</Button>
      <Button intent="primary" loading={busy === 'execute'} onClick={execute}>{gettext('Run query')}</Button>
    </Stack>
    {compiled && <Box component="pre" aria-label={gettext('Compiled query')} sx={{m: 0, p: 1, overflow: 'auto',
      maxHeight: 280, whiteSpace: 'pre-wrap', bgcolor: 'background.default', fontSize: '0.75rem'}}>
      {compiled.compiled?.source || JSON.stringify(compiled, null, 2)}</Box>}
    {diagnostics && <Box component="pre" aria-label={gettext('Query diagnostics result')} sx={{m: 0, p: 1,
      overflow: 'auto', maxHeight: 280, whiteSpace: 'pre-wrap', bgcolor: 'background.default',
      fontSize: '0.75rem'}}>{JSON.stringify(diagnostics, null, 2)}</Box>}
    {rendered && <CellsetGrid rendered={rendered} />}
  </Stack>;
}

QueryPanel.propTypes = {
  client: PropTypes.object.isRequired, record: PropTypes.object, dirty: PropTypes.bool,
  built: PropTypes.object.isRequired, draft: PropTypes.object.isRequired, catalog: PropTypes.object.isRequired,
};
