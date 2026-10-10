// Native Firebird script controls; results never replay source SQL.
import {useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {readFirebirdScriptFile, saveFirebirdScriptFile} from './firebirdScriptFiles';
import {Alert, Box, Button, MenuItem, Table, TableBody, TableCell,
  TableHead, TableRow, TextField} from '@mui/material';

export default function FirebirdScript({source, disabled, onPreview, onRun, result, onSourceChange}) {
  const [preview, setPreview] = useState(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(1);
  const [page, setPage] = useState(0);
  const current = preview?.source === source;
  const entries = result?.entries || [];
  const entry = entries.find((item) => item.index === selected) || entries[0];
  const rows = entry?.result?.payload?.rows || [];
  const columns = entry?.result?.schema?.columns || [];
  const pageCount = Math.max(1, Math.ceil(rows.length / 100));
  const currentPage = Math.min(page, pageCount - 1);
  const exportResult = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)],
      {type: 'application/json'}));
    const link = document.createElement('a');
    link.href = url; link.download = 'firebird-script-results.json';
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <Box component="fieldset" sx={{mt: 1, minWidth: 0}}
    aria-label={gettext('Firebird SQL script')}>
    <legend>{gettext('SQL script')}</legend>
    <Alert severity="info">{gettext('Preview checks script boundaries, not SQL validity or permissions. Manual DDL and stop on error are the defaults. SET AUTODDL ON commits DDL in a separate transaction. Explicit SQL and autonomous procedures may commit work. Cancellation does not undo earlier statements.')}</Alert>
    <Box sx={{display: 'flex', gap: 1, mt: 1}}>
      {onSourceChange && <Button component="label" disabled={disabled || pending}>
        {gettext('Load SQL script')}
        <input type="file" hidden accept=".sql,text/plain,application/sql"
          aria-label={gettext('Load SQL script file')} disabled={disabled || pending}
          onChange={async (event) => {
            const file = event.target.files?.[0]; event.target.value = '';
            if (!file) return;
            setPending(true); setError(null); setPreview(null);
            try { onSourceChange(await readFirebirdScriptFile(file)); }
            catch (failure) { setError(failure.message); }
            finally { setPending(false); }
          }} />
      </Button>}
      <Button disabled={disabled || pending || !source} onClick={() => saveFirebirdScriptFile(source)}>
        {gettext('Save SQL script')}</Button>
      <Button disabled={disabled || pending || !source.trim()} onClick={async () => {
        setPending(true); setPreview(null); setError(null);
        try { setPreview({source, value: await onPreview(source)}); }
        catch (failure) { setError(failure?.response?.data?.errormsg || failure.message || gettext('Script preview failed.')); }
        finally { setPending(false); }
      }}>{gettext('Preview script')}</Button>
      <Button disabled={disabled || pending || !current} onClick={() => {
        setPreview(null); onRun(source);
      }}>{gettext('Run script')}</Button>
    </Box>
    {error && <Alert severity="error">{error}</Alert>}
    {current && <Box aria-label={gettext('Script preview')}>
      {gettext('Entries:')} {preview.value.total_entries}
      <Box sx={{maxHeight: 180, overflow: 'auto'}}>
        {preview.value.entries.map((item) => <Box key={item.index}>
          {item.index}: {gettext('Line')} {item.line} — {item.kind}
          {item.transaction_action ? ' — ' + item.transaction_action : ''}
          {item.value !== null && item.value !== undefined ? ' ' + String(item.value) : ''}
        </Box>)}
      </Box>
    </Box>}
    {result && <Box aria-label={gettext('Script outcomes')}>
      {result.had_errors && <Alert severity="warning">{gettext('One or more script entries failed. Select an entry to inspect its outcome and retained result.')}</Alert>}
      {result.unknown_outcome && <Alert severity="error">{gettext('A script outcome is unknown. Do not replay the script. Inspect the retained transaction or reconnect explicitly if the session is unavailable.')}</Alert>}
      {result.stopped_before_end && <Alert severity="warning">{gettext('The script stopped before all entries ran. Earlier effects may remain pending or committed. Entries marked not_run were not dispatched.')}</Alert>}
      <TextField select fullWidth size="small" sx={{mt: 1}}
        label={gettext('Script entry')} value={entry?.index || ''}
        onChange={(event) => { setSelected(Number(event.target.value)); setPage(0); }}>
        {entries.map((item) => <MenuItem key={item.index} value={item.index}>
          {item.index}: {gettext('Line')} {item.line} — {item.kind} — {item.state}
        </MenuItem>)}
      </TextField>
      {entry?.error && <Alert severity="error">
        {entry.error.message} {gettext('Native status codes:')} {(entry.error.native_status_codes || []).join(', ')}
      </Alert>}
      {entry?.ddl_transaction && <Box component="pre" sx={{whiteSpace: 'pre-wrap'}}>
        {JSON.stringify(entry.ddl_transaction, null, 2)}
      </Box>}
      {entry?.result?.payload?.fetch_observation?.limit_reached &&
        <Alert severity="warning">{gettext('Fetch limit reached for this statement. Further rows may exist; no total was counted.')}</Alert>}
      {entry?.result && <Box sx={{overflow: 'auto', maxHeight: 420}}>
        <Table size="small" aria-label={gettext('Script statement result')}>
          <TableHead><TableRow>{columns.map((column, index) =>
            <TableCell key={index}>{column.name} ({column.native_type || ''})</TableCell>)}</TableRow></TableHead>
          <TableBody>{rows.slice(currentPage * 100, (currentPage + 1) * 100).map((row, index) =>
            <TableRow key={index}>{row.map((cell, ordinal) => <TableCell key={ordinal}>
              {cell === null ? 'NULL' : typeof cell === 'object' ? JSON.stringify(cell) : String(cell)}
            </TableCell>)}</TableRow>)}</TableBody>
        </Table>
      </Box>}
      {rows.length > 100 && <Box>
        <Button disabled={!currentPage} onClick={() => setPage(currentPage - 1)}>{gettext('Previous result page')}</Button>
        {currentPage + 1} / {pageCount}
        <Button disabled={currentPage + 1 >= pageCount} onClick={() => setPage(currentPage + 1)}>{gettext('Next result page')}</Button>
      </Box>}
      <Button onClick={exportResult}>{gettext('Export script outcomes and results')}</Button>
    </Box>}
  </Box>;
}
FirebirdScript.propTypes = {
  source: PropTypes.string.isRequired, disabled: PropTypes.bool,
  onPreview: PropTypes.func.isRequired, onRun: PropTypes.func.isRequired,
  result: PropTypes.object, onSourceChange: PropTypes.func,
};
