import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';
import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {generatorTable, materializeTestData, parseRecipe, stageTestData, tableForeignKeys} from './firebirdTestData';

const save = (value, filename) => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], {type: 'application/json'}));
  const link = document.createElement('a'); link.href = url; link.download = filename;
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

export default function FirebirdTestData({resources, post, databaseTargetId, languageProfile}) {
  const tables = resources.filter(generatorTable);
  const [selected, setSelected] = useState([]), [catalogs, setCatalogs] = useState(null);
  const [source, setSource] = useState(''), [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [attempted, setAttempted] = useState(false), [pending, setPending] = useState(false);
  const [receipt, setReceipt] = useState(null), [confirmed, setConfirmed] = useState(false);
  const [progress, setProgress] = useState(0), [transaction, setTransaction] = useState(null);
  const [fileTable, setFileTable] = useState(''), [fileColumn, setFileColumn] = useState('');
  const session = useRef(null), stop = useRef(false), mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false; stop.current = true;
      if (session.current) post({action: 'close_session', session_id: session.current, database_target_id: databaseTargetId}).catch(() => {});
    };
  }, [post, databaseTargetId]);
  const ensureSession = async () => {
    if (!session.current) {
      const opened = await post({action: 'open_session', language_profile: languageProfile, database_target_id: databaseTargetId, session_purpose: 'firebird-test-data'});
      session.current = opened.session_id;
      if (!mounted.current) {
        await post({action: 'close_session', session_id: opened.session_id, database_target_id: databaseTargetId});
        session.current = null; throw new Error('Form closed.');
      }
    }
    return session.current;
  };
  const change = value => {setSource(value); setPreview(null); setConfirmed(false);};
  const load = async () => {
    setBusy(true); setError(''); setCatalogs(null); setPreview(null); setReceipt(null); setAttempted(false);
    try {
      const id = await ensureSession(), next = Object.create(null), entries = [];
      for (const table of tables.filter(item => selected.includes(item.resource_id))) {
        if (!mounted.current) return;
        if (Object.prototype.hasOwnProperty.call(next, table.display_name)) throw new Error('Ambiguous table names.');
        const page = await post({action: 'visual_admin_rows', request: {target_resource: table,
          session_id: id, database_target_id: databaseTargetId, limit: 200}});
        if (page.continuation) await post({action: 'visual_admin_rows_cancel', request: {continuation: page.continuation}});
        if (!page.row_operations?.includes('insert')) throw new Error('Native insertion was not admitted for ' + table.display_name);
        next[table.display_name] = {resource: table, columns: page.columns, rows: page.rows,
          sampleLimited: !!page.continuation || page.complete === false, foreignKeys: tableForeignKeys(table)};
        entries.push({table: table.display_name, count: 10, columns: Object.fromEntries(page.columns
          .filter(column => column.insertable !== false).map(column => [column.name, {kind: 'default'}]))});
      }
      // Sampling never leaves an idle MGA snapshot open while editing a recipe.
      await post({action: 'transaction_action', session_id: id, transaction_action: 'rollback', database_target_id: databaseTargetId});
      if (mounted.current) {setCatalogs(next); change(JSON.stringify({format: 'scratchrobin.firebird.test-data@1', seed: 1, tables: entries}, null, 2));}
    } catch (failure) {
      if (mounted.current) setError(failure.message || 'Sample loading failed.');
      if (session.current && mounted.current) {
        try {await post({action: 'transaction_action', session_id: session.current, transaction_action: 'rollback', database_target_id: databaseTargetId});}
        catch {setPending(true); setError('Sample transaction cleanup was not confirmed. Inspect or explicitly roll back before continuing.');}
      }
    }
    finally {if (mounted.current) setBusy(false);}
  };
  const importRecipe = async event => {
    const file = event.target.files?.[0]; event.target.value = ''; if (!file) return;
    try {
      if (file.size > 1024 * 1024) throw new Error('Recipe exceeds 1 MiB.');
      const text = new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer());
      parseRecipe(text); change(text); setError('');
    } catch (failure) {setError(failure.message);}
  };
  const previewRecipe = () => {
    try {setPreview(materializeTestData(parseRecipe(source), catalogs)); setError(''); setConfirmed(false);}
    catch (failure) {setError(failure.message); setPreview(null);}
  };
  const importValues = async event => {
    const file = event.target.files?.[0]; event.target.value = ''; if (!file) return;
    try {
      if (file.size > 1024 * 1024) throw new Error('Value file exceeds 1 MiB.');
      const values = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer()));
      if (!Array.isArray(values) || !values.length || values.length > 1000) throw new Error('Value file requires 1–1000 typed JSON values.');
      const recipe = parseRecipe(source), entry = recipe.tables.find(table => table.table === fileTable);
      if (!entry || !Object.prototype.hasOwnProperty.call(entry.columns, fileColumn)) throw new Error('Choose an exact recipe table and column.');
      entry.columns[fileColumn] = {kind: 'file', values};
      change(JSON.stringify(recipe, null, 2)); setError('');
    } catch (failure) {setError(failure.message);}
  };
  const run = async () => {
    stop.current = false; setBusy(true); setAttempted(true); setPending(true); setError(''); setProgress(0);
    try {
      const id = await ensureSession();
      const result = await stageTestData({preview, catalogs, post, sessionId: id, databaseTargetId,
        stopped: () => stop.current || !mounted.current, onProgress: count => {if (mounted.current) setProgress(count);}});
      if (mounted.current) setReceipt(result);
    } catch {if (mounted.current) setError('Execution stopped. Inspect the dedicated transaction; do not retry this preview.');}
    finally {if (mounted.current) setBusy(false);}
  };
  const control = async action => {
    setBusy(true); setError('');
    try {
      const result = await post({action: action === 'state' ? 'transaction' : 'transaction_action',
        session_id: session.current, ...(action === 'state' ? {} : {transaction_action: action}), database_target_id: databaseTargetId});
      setTransaction(result);
      // Require a fresh sample/preview after every explicit finalization attempt.
      if (action !== 'state') {setPending(false); setPreview(null); setCatalogs(null); setConfirmed(false);}
    } catch {setError('Native transaction outcome was not received. Keep this session open and inspect its state before further work.');}
    finally {setBusy(false);}
  };
  return <Box data-cde-compact-form sx={{p: 1, overflow: 'auto', ...compactFormSx}}>
    <FormReference formKey="firebird-test-data" />
    <Alert severity="warning">Generate test rows only in the selected database. This form uses its own native transaction. Preview does not execute. Staged rows require explicit commit or rollback; closing requests session release, without claiming a confirmed outcome.</Alert>
    <Box>{tables.map(table => <FormControlLabel key={table.resource_id} label={table.display_name}
      control={<Checkbox disabled={busy || pending} checked={selected.includes(table.resource_id)} onChange={() => {
        setSelected(values => values.includes(table.resource_id) ? values.filter(value => value !== table.resource_id) : [...values, table.resource_id]);
        setCatalogs(null); setPreview(null);
      }} />} />)}</Box>
    <Button disabled={busy || pending || !selected.length || selected.length > 32} onClick={load}>Load table columns and existing samples</Button>
    <Alert severity="info">Only discovered user tables are listed. Refresh the explorer for missing metadata. Each selected table supplies at most 200 existing rows. Sources: default; constant with value; sequential with decimal-string start/step; random-integer with decimal-string min/max; choice or file with typed values array; existing or generated with exact table/column. Optional nullPercent is 0–100. Change default sources before preview where native defaults are absent. Generated references use matching row positions across composite keys. Cycles require explicit NULL or existing values; constraints stay enabled.</Alert>
    {catalogs && <Box component="pre">{Object.entries(catalogs).map(([name, value]) => `${name}: ${value.rows.length} sampled rows${value.sampleLimited ? ' (limited)' : ''}\n`).join('')}</Box>}
    <TextField label="Test-data recipe JSON" multiline minRows={10} fullWidth value={source}
      disabled={busy || pending} onChange={event => change(event.target.value)} />
    <Button component="label" disabled={busy || pending}>Read saved recipe<input hidden type="file" accept=".json,application/json" aria-label="Test-data recipe file" disabled={busy || pending} onChange={importRecipe} /></Button>
    <Box>
      <TextField size="small" label="File source table" value={fileTable} disabled={busy || pending} onChange={event => setFileTable(event.target.value)} />
      <TextField size="small" label="File source column" value={fileColumn} disabled={busy || pending} onChange={event => setFileColumn(event.target.value)} />
      <Button component="label" disabled={busy || pending || !source || !fileTable || !fileColumn}>Read column values file
        <input hidden type="file" accept=".json,application/json" aria-label="Test-data column values file" disabled={busy || pending || !source || !fileTable || !fileColumn} onChange={importValues} /></Button>
    </Box>
    <Button disabled={!source || busy} onClick={() => {try {save(parseRecipe(source), 'firebird-test-data-recipe.json');} catch (failure) {setError(failure.message);}}}>Save recipe (may contain data)</Button>
    <Button disabled={!catalogs || busy || pending} onClick={previewRecipe}>Preview generated rows</Button>
    {error && <Alert severity="error">{error}</Alert>}
    {preview && <>
      <Alert severity="info">{preview.operations.length} rows. Table order: {preview.order.join(', ')}. First 20 rows shown. Native constraints and permissions are checked during staging.</Alert>
      <Box component="pre" sx={{maxHeight: 300, overflow: 'auto'}}>{JSON.stringify(preview.operations.slice(0, 20), null, 2)}</Box>
      <Button onClick={() => save(preview, 'firebird-generated-preview.json')}>Download all preview rows</Button>
      <FormControlLabel label="I authorize staging these generated rows in this database" control={<Checkbox checked={confirmed} disabled={busy || attempted} onChange={event => setConfirmed(event.target.checked)} />} />
      <Button disabled={!confirmed || busy || attempted} onClick={run}>Stage generated rows</Button>
    </>}
    <Button disabled={!busy || !pending} onClick={() => {stop.current = true;}}>Stop before next row</Button>
    {attempted && <Alert severity="warning">{progress} rows confirmed staged. Stop is not rollback. Do not rerun this preview.</Alert>}
    {receipt && <Box component="pre">{JSON.stringify(receipt, null, 2)}</Box>}
    <Button disabled={busy || !session.current} onClick={() => control('state')}>Inspect generator transaction</Button>
    <Button disabled={busy || !pending} onClick={() => control('commit')}>Commit generated rows</Button>
    <Button disabled={busy || !pending} onClick={() => control('rollback')}>Rollback generated rows</Button>
    {transaction && <Box component="pre">{JSON.stringify(transaction, null, 2)}</Box>}
  </Box>;
}
FirebirdTestData.propTypes = {resources: PropTypes.array.isRequired, post: PropTypes.func.isRequired,
  databaseTargetId: PropTypes.string.isRequired, languageProfile: PropTypes.string.isRequired};
