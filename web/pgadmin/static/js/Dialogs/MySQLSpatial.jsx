import {useEffect, useId, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField, Typography} from '@mui/material';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import {loadDDNGeoLibraries} from '../cdeadmin_ui/integrations/ddn/library';
import {mysqlSpatialFiles} from '../cdeadmin_ui/integrations/ddn/mysqlSpatial';

function Map({report, selected}) {
  const [ready,setReady]=useState(false),[error,setError]=useState('');
  const files=useMemo(() => mysqlSpatialFiles(report,selected),[report,selected]);
  useEffect(() => {
    let active=true;
    if(files) loadDDNGeoLibraries().then(() => {if(active) setReady(true);}).catch(failure => {if(active) setError(failure.message);});
    return () => {active=false;};
  },[Boolean(files)]);
  return <Box sx={{minHeight:250}}>{error && <Alert severity="error">{error}</Alert>}
    {!files && <Alert severity="info">No geometry admitted to this map. Inspect native values and fallback reasons below.</Alert>}
    {files && ready && <DDNViewerSurface files={files} entry="spatial.ddn" view="spatial" presentation />}
  </Box>;
}
Map.propTypes={report:PropTypes.object,selected:PropTypes.string};

export default function MySQLSpatial({post,databaseTargetId=null}) {
  const [schema,setSchema]=useState(''),[table,setTable]=useState(''),[column,setColumn]=useState('');
  const [databases,setDatabases]=useState([]),[tables,setTables]=useState([]),[description,setDescription]=useState(null);
  const [databaseOffset,setDatabaseOffset]=useState(null),[tableOffset,setTableOffset]=useState(null);
  const [format,setFormat]=useState('mysql'),[srid,setSrid]=useState('0'),[axis,setAxis]=useState('long-lat');
  const [mapMode,setMapMode]=useState('native'),[limit,setLimit]=useState(25),[seconds,setSeconds]=useState(10);
  const [report,setReport]=useState(null),[selected,setSelected]=useState(''),[consent,setConsent]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const serial=useRef(0),postRef=useRef(post);postRef.current=post;
  const databaseList=useId(),tableList=useId();
  useEffect(() => {
    serial.current++;setSchema('');setTable('');setColumn('');setDatabases([]);setTables([]);setDescription(null);
    setReport(null);setSelected('');setConsent(false);setBusy(false);setError('');setDatabaseOffset(null);setTableOffset(null);
    return () => {serial.current++;};
  },[databaseTargetId]);
  const clear=() => {serial.current++;setReport(null);setSelected('');setConsent(false);setBusy(false);setError('');};
  const request=async(operation,values,accept) => {
    const token=++serial.current;setBusy(true);setError('');setReport(null);setSelected('');
    try {
      const result=await postRef.current({action:`mysql_spatial_${operation}`,request:{database_target_id:databaseTargetId,...values}});
      if(token===serial.current) accept(result);
    } catch(failure) {if(token===serial.current) setError(failure.response?.data?.errormsg || failure.message || 'Spatial inspection failed');}
    finally {if(token===serial.current) setBusy(false);}
  };
  const loadColumns=(offset=0) => request('columns',{schema_name:schema,table_name:table,offset},value => {setDescription(value);setColumn('');setConsent(false);});
  const read=offset => request('read',{schema_name:schema,table_name:table,column_name:column,fingerprint:description.fingerprint,
    confirmed:consent,options:{format,srid,axis_order:axis,map:mapMode,limit,offset,seconds}},setReport);
  const item=report?.rows?.find(row => row.id===selected);
  const download=() => {
    const bytes=Uint8Array.from(item.raw_hex.match(/../g) || [],pair => parseInt(pair,16));
    const url=URL.createObjectURL(new Blob([bytes],{type:'application/octet-stream'}));
    const link=document.createElement('a');link.href=url;link.download=item.format==='mysql'?'mysql-geometry.bin':'geometry.wkb';
    document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(url);
  };
  return <Box aria-label="MySQL spatial data inspection" sx={{p:1,height:'100%',overflow:'auto'}}>
    <Typography component="h3">MySQL spatial data inspection</Typography>
    <Alert severity="info">Read a bounded private page on a separate native connection. Geometry bytes remain exact; map positions are approximate.
      Native X/Y preserves source coordinate meaning. WGS84 uses native ST_Transform and longitude/latitude.
      This view works offline. External tiles and external network requests are disabled.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display:'flex',flexWrap:'wrap',gap:1,my:1}}>
      <Button disabled={busy} onClick={() => request('databases',{offset:0},value => {setDatabases(value.rows);setDatabaseOffset(value.next_offset);})}>Discover spatial databases</Button>
      {databaseOffset!==null && <Button disabled={busy} onClick={() => request('databases',{offset:databaseOffset},value => {setDatabases(value.rows);setDatabaseOffset(value.next_offset);})}>Next database page</Button>}
      <TextField size="small" label="Spatial database" value={schema} disabled={busy} inputProps={{list:databaseList}}
        onChange={event => {clear();setSchema(event.target.value);setTable('');setColumn('');setTables([]);setTableOffset(null);setDescription(null);}} />
      <datalist id={databaseList}>{databases.map(row => <option key={row.name} value={row.name} />)}</datalist>
      <Button disabled={busy || !schema} onClick={() => request('tables',{schema_name:schema,offset:0},value => {setTables(value.rows);setTableOffset(value.next_offset);})}>Discover spatial tables</Button>
      {tableOffset!==null && <Button disabled={busy} onClick={() => request('tables',{schema_name:schema,offset:tableOffset},value => {setTables(value.rows);setTableOffset(value.next_offset);})}>Next table page</Button>}
      <TextField size="small" label="Spatial table" value={table} disabled={busy} inputProps={{list:tableList}}
        onChange={event => {clear();setTable(event.target.value);setColumn('');setDescription(null);}} />
      <datalist id={tableList}>{tables.filter(row => row.kind==='BASE TABLE').map(row => <option key={row.name} value={row.name} />)}</datalist>
      <Button disabled={busy || !schema || !table} onClick={() => loadColumns()}>Observe geometry columns</Button>
      {description?.next_offset!=null && <Button disabled={busy} onClick={() => loadColumns(description.next_offset)}>Next column page</Button>}
      <TextField select size="small" label="Geometry or binary column" value={column} disabled={busy || !description}
        onChange={event => {clear();setColumn(event.target.value);}}>
        {(description?.rows || []).map(row => <MenuItem key={row.COLUMN_NAME} value={row.COLUMN_NAME}>{row.COLUMN_NAME} ({row.DATA_TYPE}; SRID {row.SRS_ID ?? 'unrestricted'})</MenuItem>)}
      </TextField>
    </Box>
    <Box sx={{display:'flex',flexWrap:'wrap',gap:1,my:1}}>
      <TextField select size="small" label="Geometry byte encoding" value={format} disabled={busy} onChange={event => {clear();setFormat(event.target.value);}}>
        <MenuItem value="mysql">MySQL internal SRID prefix + WKB</MenuItem><MenuItem value="wkb">WKB binary column</MenuItem>
      </TextField>
      <TextField size="small" label="WKB interpretation SRID" value={srid} disabled={busy || format!=='wkb'} onChange={event => {clear();setSrid(event.target.value);}} />
      <TextField select size="small" label="WKB input axis order" value={axis} disabled={busy || format!=='wkb'} onChange={event => {clear();setAxis(event.target.value);}}>
        <MenuItem value="long-lat">X/Y; longitude/latitude for geographic SRS</MenuItem><MenuItem value="lat-long">Latitude/longitude</MenuItem><MenuItem value="srid-defined">Native SRS defined order</MenuItem>
      </TextField>
      <TextField select size="small" label="Map coordinates" value={mapMode} disabled={busy} onChange={event => {clear();setMapMode(event.target.value);}}>
        <MenuItem value="native">Native X/Y (Cartesian display)</MenuItem><MenuItem value="wgs84">Native transform to WGS84 longitude/latitude</MenuItem>
      </TextField>
      <TextField size="small" type="number" label="Spatial row limit" value={limit} disabled={busy} onChange={event => {clear();setLimit(Number(event.target.value));}} />
      <TextField size="small" type="number" label="Spatial time limit seconds" value={seconds} disabled={busy} onChange={event => {clear();setSeconds(Number(event.target.value));}} />
    </Box>
    <FormControlLabel label="Allow private geometry inspection" control={<Checkbox checked={consent} disabled={busy} onChange={event => setConsent(event.target.checked)} />} />
    <Button disabled={busy || !description || !column || !consent} onClick={() => read(0)}>Inspect native geometry</Button>
    <Button disabled={busy || report?.next_offset==null} onClick={() => read(report.next_offset)}>Next spatial page</Button>
    <Button onClick={clear}>Clear private inspection</Button>
    {report && <Box aria-label="Native spatial inspection report">
      <Typography>Coverage: {report.coverage}. {report.rows.length} rows. Snapshot: {report.consistent_snapshot ? 'InnoDB consistent read' : 'Native engine; no cross-row snapshot guarantee'}.
        Server: {report.identity.server_uuid}. {report.observed_at}</Typography>
      <Typography>Map: {report.map_mode}. Tiles: {report.tiles}. Native SRS definitions: {JSON.stringify(report.srs)}</Typography>
      <TextField select size="small" label="Inspect spatial row" value={selected} onChange={event => setSelected(event.target.value)}>
        <MenuItem value="">All admitted map rows</MenuItem>{report.rows.map(row => <MenuItem key={row.id} value={row.id}>{row.id}: {row.state} / {row.map_status}</MenuItem>)}
      </TextField>
      <Map report={report} selected={selected} />
      {item && <>
        <Typography>State: {item.state}. SRID: {item.srid ?? 'unavailable'}. Native validity: {item.validity ?? 'unavailable'}.
          Bytes: {item.raw_bytes ?? 'NULL'}. {item.reason || ''} Keys (native hex): {JSON.stringify(item.key_hex)}</Typography>
        <Typography>Native diagnostics: {JSON.stringify(item.errors || [])}</Typography>
        <TextField fullWidth multiline label="WKT in native SRS order" value={item.wkt_srs || ''} InputProps={{readOnly:true}} />
        <TextField fullWidth multiline label="WKT X/Y (longitude/latitude for geographic SRS)" value={item.wkt_xy || ''} InputProps={{readOnly:true}} />
        <TextField fullWidth multiline label="Native GeoJSON X/Y" value={item.geojson ? JSON.stringify(item.geojson) : ''} InputProps={{readOnly:true}} />
        <TextField fullWidth multiline label="Original native bytes (hex)" value={item.raw_hex ?? ''} InputProps={{readOnly:true}} />
        <Button disabled={item.raw_hex==null} onClick={download}>Download exact original bytes</Button>
      </>}
    </Box>}
  </Box>;
}
MySQLSpatial.propTypes={post:PropTypes.func.isRequired,databaseTargetId:PropTypes.string};
