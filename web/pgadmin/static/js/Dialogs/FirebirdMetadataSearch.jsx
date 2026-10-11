import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, TextField, Typography} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';

export default function FirebirdMetadataSearch({targets, post, onOpen}) {
  const [selected, setSelected] = useState([]);
  const [fields, setFields] = useState(['name', 'description', 'source', 'fields']);
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState('');
  const [results, setResults] = useState([]);
  const [busy, setBusy] = useState(false);
  const [stopped, setStopped] = useState(false);
  const stop = useRef(false), mounted = useRef(true);
  useEffect(() => {mounted.current = true; return () => {mounted.current = false; stop.current = true;};}, []);
  const toggle = (values, value) => values.includes(value) ? values.filter(item => item !== value) : [...values, value];
  const run = async () => {
    stop.current = false; setStopped(false); setBusy(true); setResults([]);
    try {
      for (const target of targets.filter(item => selected.includes(item.target_id))) {
        if (stop.current) break;
        let result;
        try {
          result = await post({action: 'firebird_metadata_search', request: {target_id: target.target_id, query, kind, fields}});
          if (result.target_id !== target.target_id) throw new Error('ScopeMismatch');
        } catch {result = {error: 'Database search unavailable. Check registration, credentials and catalog access.'};}
        if (mounted.current) setResults(current => [...current, {target, ...result}]);
      }
    } finally {if (mounted.current) {setBusy(false); setStopped(stop.current);}}
  };
  return <Box sx={{p: 2, overflow: 'auto'}}>
    <FormReference formKey="firebird-metadata-search" />
    <Alert severity="info">Search registered databases on this server using their authorized catalog connections. User SQL transactions are unchanged. Results cover only visible metadata.</Alert>
    <Box>{targets.map(target => <FormControlLabel key={target.target_id} label={target.label || target.database || target.target_id}
      control={<Checkbox disabled={busy} checked={selected.includes(target.target_id)} onChange={() => setSelected(toggle(selected, target.target_id))} />} />)}</Box>
    <TextField label="Metadata search text" value={query} disabled={busy} inputProps={{maxLength: 256}} onChange={event => setQuery(event.target.value)} />
    <TextField label="Exact object kind (optional)" value={kind} disabled={busy} onChange={event => setKind(event.target.value)} />
    <Box>{['name', 'kind', 'description', 'source', 'fields'].map(field => <FormControlLabel key={field} label={field}
      control={<Checkbox checked={fields.includes(field)} disabled={busy} onChange={() => setFields(toggle(fields, field))} />} />)}</Box>
    <Button disabled={busy || !selected.length || !fields.length || !query.trim()} onClick={run}>Search metadata</Button>
    <Button disabled={!busy} onClick={() => {stop.current = true;}}>Stop after current database</Button>
    {stopped && <Alert severity="info">Search stopped. Completed database results remain visible.</Alert>}
    {results.map(result => <Box key={result.target.target_id} sx={{my: 1}}>
      <Typography variant="h6">{result.target.label || result.target.database || result.target.target_id}</Typography>
      {result.error ? <Alert severity="warning">{result.error}</Alert> : <>
        <Typography>{result.match_count} matches. {result.coverage}</Typography>
        {result.truncated && <Alert severity="warning">Only the first 500 matches are shown. Narrow the search.</Alert>}
        {result.missing_ddl_count > 0 && <Alert severity="warning">Native DDL unavailable for {result.missing_ddl_count} objects.</Alert>}
        {(result.catalog_observations || []).filter(item => !item.available).map((item, index) => <Alert severity="warning" key={index}>{item.section}: unavailable ({item.error_type}).</Alert>)}
        {result.matches.map(match => <Box key={match.resource_id} sx={{borderBottom: 1, borderColor: 'divider', py: 1}}>
          <Button disabled={!onOpen} onClick={() => onOpen(result.target.target_id, match)}>{match.resource_kind}: {(match.display_path || [match.display_name]).join(' / ')}</Button>
          <Typography variant="caption">{match.matched_fields.join(', ')}</Typography>
          <Box component="pre" sx={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{match.snippet}{match.snippet_truncated ? ' …' : ''}</Box>
        </Box>)}
      </>}
    </Box>)}
  </Box>;
}
FirebirdMetadataSearch.propTypes = {targets: PropTypes.array.isRequired, post: PropTypes.func.isRequired, onOpen: PropTypes.func};
