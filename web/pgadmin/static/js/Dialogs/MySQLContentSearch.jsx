import {useEffect, useId, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography} from '@mui/material';

const modes = {text_contains: 'Text contains (literal)', text_exact: 'Text equals', text_prefix: 'Text starts with (literal)',
  numeric_equal: 'Numeric equals', binary_exact: 'Binary equals (hex)', binary_contains: 'Binary contains (hex)', is_null: 'Is NULL'};
const shown = value => value == null ? 'NULL' : typeof value === 'object' ? JSON.stringify(value) : String(value);

export default function MySQLContentSearch({post, databaseTargetId=null}) {
  const [schema, setSchema] = useState(''), [databases, setDatabases] = useState([]), [databaseOffset, setDatabaseOffset] = useState(null);
  const [tables, setTables] = useState([]), [next, setNext] = useState(null), [selections, setSelections] = useState({});
  const [details, setDetails] = useState(null), [mode, setMode] = useState('text_contains'), [value, setValue] = useState('');
  const [indexed, setIndexed] = useState(false), [limit, setLimit] = useState(200), [seconds, setSeconds] = useState(30);
  const [consent, setConsent] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [job, setJob] = useState(null), [row, setRow] = useState(null);
  const generation = useRef(0), jobRef = useRef(null), postRef = useRef(post);
  const schemaListId = useId();
  postRef.current = post; jobRef.current = job;
  const api = (operation, request) => postRef.current({action: `mysql_content_search_${operation}`,
    request: {database_target_id: databaseTargetId, ...request}});
  useEffect(() => {
    const originalPost = postRef.current;
    generation.current++; setJob(null); setRow(null); setValue(''); setConsent(false); setSchema('');setTables([]);setSelections({});setDetails(null);
    setBusy(false);setError('');setDatabases([]);setDatabaseOffset(null);setNext(null);
    return () => {
      generation.current++;
      const active = jobRef.current;
      if(active && !active.terminal) originalPost({action:'mysql_content_search_cancel', request:{database_target_id:databaseTargetId,job_id:active.job_id}}).catch(() => {});
    };
  }, [databaseTargetId]);
  useEffect(() => {
    if(!job || job.terminal) return undefined;
    let live = true, pending = false;
    const timer = setInterval(async () => {
      if(pending) return;
      pending = true;
      const token = generation.current;
      try {
        const current = await api('status', {job_id:job.job_id});
        if(live && token===generation.current) setJob(current);
      } catch(failure) {if(live && token===generation.current) {
        setError(failure.response?.data?.errormsg || failure.message);setRow(null);setValue('');
        setJob(current => current?.job_id===job.job_id ? {...current,state:'unavailable',terminal:true,matches:[],coverage:[]} : current);
      }}
      finally {pending = false;}
    }, 500);
    return () => {live = false; clearInterval(timer);};
  }, [job?.job_id, job?.terminal, databaseTargetId]);
  const run = async (operation, request, accept) => {
    const token = ++generation.current;
    const originalPost = postRef.current;
    setBusy(true); setError('');
    try {
      const result = await api(operation,request);
      if(token===generation.current) accept(result);
      else if(operation==='start' && result?.job_id) originalPost({action:'mysql_content_search_cancel',
        request:{database_target_id:databaseTargetId,job_id:result.job_id}}).catch(() => {});
    }
    catch(failure) {if(token===generation.current) setError(failure.response?.data?.errormsg || failure.message || 'Native search request failed');}
    finally {if(token===generation.current) setBusy(false);}
  };
  const active = Boolean(job && !job.terminal);
  const changeSchema = event => {generation.current++; setSchema(event.target.value); setTables([]); setNext(null); setDetails(null); setSelections({}); setConsent(false); setRow(null);};
  const loadTables = offset => run('tables',{schema_name:schema,offset}, result => {setTables(result.rows); setNext(result.next_offset); setDetails(null);});
  const loadColumns = (table, offset=0) => run('columns',{schema_name:schema,table_name:table,offset}, result => {
    setDetails(result);
    setSelections(current => {
      const selected = current[table];
      return {...current, [table]: selected?.fingerprint===result.fingerprint ? selected : {table_name:table,
        fingerprint:result.fingerprint, columns:result.rows.filter(c => c.PRIVILEGES.split(',').includes('select')).map(c => c.COLUMN_NAME)}};
    });
  });
  const toggle = column => setSelections(current => {
    const item = current[details.table_name], selected = item.columns.includes(column);
    return {...current, [details.table_name]: {...item, columns:selected ? item.columns.filter(c => c!==column) : [...item.columns,column]}};
  });
  return <Box aria-label="MySQL database content search" sx={{p:1,height:'100%',overflow:'auto'}}>
    <Typography component="h3">MySQL database content search</Typography>
    <Alert severity="info">Search persistent base tables visible to the native account. Observers own separate read-only transactions.
      Results are bounded, private and kept in memory for five minutes. Native server logging still applies.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display:'flex',flexWrap:'wrap',gap:1,my:1}}>
      <Button disabled={busy || active} onClick={() => run('databases',{offset:0}, result => {setDatabases(result.rows); setDatabaseOffset(result.next_offset);})}>Discover databases</Button>
      {databaseOffset!==null && <Button disabled={busy || active} onClick={() => run('databases',{offset:databaseOffset}, result => {setDatabases(current => [...current,...result.rows]); setDatabaseOffset(result.next_offset);})}>More databases</Button>}
      <TextField size="small" label="Search database" value={schema} disabled={busy || active || Boolean(job)} onChange={changeSchema}
        inputProps={{list:schemaListId}} />
      <datalist id={schemaListId}>{databases.map(item => <option key={item.name} value={item.name} />)}</datalist>
      <Button disabled={busy || active || !schema || Boolean(job)} onClick={() => loadTables(0)}>Discover tables</Button>
      {next!==null && <Button disabled={busy || active || Boolean(job)} onClick={() => loadTables(next)}>Next table page</Button>}
    </Box>
    <Alert severity="info">Catalog visibility is permission filtered. Invisible tables are unknown; a catalog page is not proof of full database coverage.
      Select tables and columns below. One search admits at most 64 tables and 256 columns.</Alert>
    <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',md:'1fr 2fr'},gap:1,my:1}}>
      <Box sx={{maxHeight:300,overflow:'auto'}}><Table size="small" aria-label="Native search tables"><TableHead><TableRow>
        <TableCell>Table</TableCell><TableCell>Selected columns</TableCell><TableCell>Scope</TableCell></TableRow></TableHead>
      <TableBody>{tables.map(item => <TableRow key={item.name}><TableCell><Button disabled={busy || active || Boolean(job) || item.kind!=='BASE TABLE'} onClick={() => loadColumns(item.name)}>{item.name}</Button></TableCell>
        <TableCell>{selections[item.name]?.columns.length || 0}</TableCell><TableCell>{item.kind} / {item.engine}</TableCell></TableRow>)}</TableBody></Table></Box>
      {details && <Box sx={{maxHeight:300,overflow:'auto'}}>
        <Typography component="h4">{details.table_name}: select columns</Typography>
        <Typography>Native unique-key navigation: {details.key.length ? details.key.join(', ') : 'Unavailable'}</Typography>
        <Button disabled={busy || active || Boolean(job)} onClick={() => setSelections(current => ({...current,[details.table_name]:{table_name:details.table_name,fingerprint:details.fingerprint,columns:[]}}))}>Clear table selection</Button>
        {details.next_offset!==null && <Button disabled={busy || active || Boolean(job)} onClick={() => loadColumns(details.table_name,details.next_offset)}>Next column page</Button>}
        {details.rows.map(column => <FormControlLabel key={column.COLUMN_NAME} label={`${column.COLUMN_NAME} — ${column.COLUMN_TYPE} / ${column.COLLATION_NAME || 'native non-text'}`}
          control={<Checkbox checked={Boolean(selections[details.table_name]?.columns.includes(column.COLUMN_NAME))}
            disabled={busy || active || Boolean(job) || !column.PRIVILEGES.split(',').includes('select')} onChange={() => toggle(column.COLUMN_NAME)} />} />)}
      </Box>}
    </Box>
    <Typography>{Object.values(selections).filter(t => t.columns.length).length} selected tables; {Object.values(selections).reduce((n,t) => n+t.columns.length,0)} columns</Typography>
    <Box sx={{display:'flex',flexWrap:'wrap',gap:1,my:1}}>
      <TextField select size="small" label="Value comparison" value={mode} disabled={busy || active || Boolean(job)} onChange={event => setMode(event.target.value)}>
        {Object.entries(modes).map(([key,label]) => <MenuItem key={key} value={key}>{label}</MenuItem>)}</TextField>
      <TextField size="small" label="Private search value" value={value} disabled={busy || active || Boolean(job) || mode==='is_null'} onChange={event => setValue(event.target.value)} />
      <TextField size="small" label="Maximum matches" type="number" value={limit} disabled={busy || active || Boolean(job)} onChange={event => setLimit(Number(event.target.value))} />
      <TextField size="small" label="Maximum seconds" type="number" value={seconds} disabled={busy || active || Boolean(job)} onChange={event => setSeconds(Number(event.target.value))} />
      <FormControlLabel label="Indexed only: native lookup/range; skip scans" control={<Checkbox checked={indexed} disabled={busy || active || Boolean(job)} onChange={event => setIndexed(event.target.checked)} />} />
    </Box>
    <Alert severity="info">Text uses native column collation, case, accent and padding rules; % and _ are literal in contains/prefix searches.
      JSON and temporal text use native character conversion. Exact numeric types avoid string/float coercion; FLOAT/DOUBLE use native approximate comparisons.
      Binary modes compare hexadecimal bytes. Native conversion warnings and inapplicable types are reported as unsearched.</Alert>
    <FormControlLabel label="Allow private table-value search" control={<Checkbox checked={consent} disabled={busy || active || Boolean(job)} onChange={event => setConsent(event.target.checked)} />} />
    <Button disabled={busy || Boolean(job) || !consent || !schema || !Object.values(selections).some(t => t.columns.length)} onClick={() => run('start',{
      schema_name:schema,tables:Object.values(selections).filter(t => t.columns.length),confirmed:true,
      options:{mode,value,indexed_only:indexed,limit,seconds}},setJob)}>Start native content search</Button>
    <Button disabled={busy || !active} onClick={() => run('cancel',{job_id:job.job_id}, current => setJob(previous => previous?.terminal ? previous : current))}>Cancel search</Button>
    <Button disabled={busy || !job?.terminal} onClick={async () => {
      const id=job.job_id;generation.current++;setJob(null);setRow(null);setValue('');setConsent(false);
      try {await api('forget',{job_id:id});} catch {setError('Private results were cleared here; server expiry remains five minutes if removal was unavailable.');}
    }}>Clear private results</Button>
    {job && <>
      <Alert severity={job.state==='completed' ? 'success' : 'info'}>Search: {job.state}. {job.matches.length} returned matches. {job.elapsed_seconds} seconds.
        Source server: {job.identity.server_uuid}. Cancellation: {JSON.stringify(job.cancellation)}</Alert>
      <Box sx={{maxHeight:400,overflow:'auto'}}><Table size="small" aria-label="Native content matches"><TableHead><TableRow>
        {['Table','Column','Preview (256 characters / binary bytes)','Native value bytes','Navigate'].map(label => <TableCell key={label}>{label}</TableCell>)}
      </TableRow></TableHead><TableBody>{job.matches.map(match => <TableRow key={match.match_id}>
        <TableCell>{match.table_name}</TableCell><TableCell>{match.column_name}</TableCell><TableCell sx={{overflowWrap:'anywhere'}}>{shown(match.preview)} ({match.preview_encoding})</TableCell>
        <TableCell>{match.value_bytes}</TableCell><TableCell><Button disabled={busy || !job.terminal || !match.navigation_available}
          onClick={() => run('row',{job_id:job.job_id,match_id:match.match_id},setRow)}>Open current row</Button>
        {!match.navigation_available && 'No readable native unique key'}</TableCell></TableRow>)}</TableBody></Table></Box>
      <Typography component="h4">Selected-scope coverage</Typography>
      <Box sx={{maxHeight:300,overflow:'auto'}}>{job.coverage.map((table,index) => <Box key={index} sx={{my:1}}>
        <Typography>{table.table_name}: {table.state} {table.reason} {table.error_code ? `Native error ${table.error_code}` : ''}</Typography>
        {table.columns?.map(column => <Typography key={column.column_name} sx={{ml:1}}>{column.column_name}: {column.state} {column.reason}
          {column.truncated ? ' — result limit reached' : ''} {column.error_code ? `Native error ${column.error_code}` : ''}</Typography>)}
      </Box>)}</Box>
    </>}
    {row && <Box aria-label="Current native search row"><Alert severity="info">{row.state}: {row.table_name}. {row.basis}</Alert>
      <Table size="small"><TableBody>{row.values.map(cell => <TableRow key={cell.column_name}><TableCell>{cell.column_name}</TableCell>
        <TableCell>{cell.data_type}</TableCell><TableCell sx={{overflowWrap:'anywhere'}}>{shown(cell.preview)}</TableCell></TableRow>)}</TableBody></Table></Box>}
  </Box>;
}
MySQLContentSearch.propTypes = {post:PropTypes.func.isRequired,databaseTargetId:PropTypes.string};
