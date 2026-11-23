import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';

export default function DuckDBCopy({post, databaseTargetId, resourceId}) {
  const [tables, setTables] = useState([]), [selected, setSelected] = useState('');
  const [direction, setDirection] = useState('to'), [format, setFormat] = useState('PARQUET');
  const [path, setPath] = useState(''), [result, setResult] = useState(null);
  const [capabilities, setCapabilities] = useState(null);
  const [targetSchema, setTargetSchema] = useState('main'), [targetTable, setTargetTable] = useState('');
  const [partitionedSource, setPartitionedSource] = useState(false);
  const [partitionByText, setPartitionByText] = useState('');
  const [overwriteOrIgnore, setOverwriteOrIgnore] = useState(false);
  const [writePartitionColumns, setWritePartitionColumns] = useState(false);
  const [filenamePattern, setFilenamePattern] = useState('');
  const [csvHeader, setCsvHeader] = useState(''), [csvDelimiter, setCsvDelimiter] = useState('');
  const [csvQuote, setCsvQuote] = useState(''), [csvEscape, setCsvEscape] = useState('');
  const [csvNullstr, setCsvNullstr] = useState(''), [csvCompression, setCsvCompression] = useState('');
  const [csvEncoding, setCsvEncoding] = useState(''), [csvAutoDetect, setCsvAutoDetect] = useState(false);
  const [csvIgnoreErrors, setCsvIgnoreErrors] = useState(false), [csvForceQuote, setCsvForceQuote] = useState('');
  const [parquetCompression, setParquetCompression] = useState(''), [parquetRowGroupSize, setParquetRowGroupSize] = useState('');
  const [parquetFieldIdsAuto, setParquetFieldIdsAuto] = useState(false), [parquetEncryptionKeyName, setParquetEncryptionKeyName] = useState('');
  const [parquetUnionByName, setParquetUnionByName] = useState(false), [parquetHivePartitioning, setParquetHivePartitioning] = useState(false);
  const [parquetFilename, setParquetFilename] = useState(false);
  const [jsonFormat, setJsonFormat] = useState(''), [jsonCompression, setJsonCompression] = useState('');
  const [jsonAutoDetect, setJsonAutoDetect] = useState(false), [jsonMaxObjectSize, setJsonMaxObjectSize] = useState('');
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const serial = useRef(0);
  useEffect(() => {serial.current++; setTables([]); setSelected(''); setResult(null); setCapabilities(null); setError('');
    return () => {serial.current++;};}, [databaseTargetId, resourceId]);
  const load = async () => {
    const token = ++serial.current; setBusy(true); setError('');
    try {
      const data = await post({action: 'duckdb_test_data', request: {database_target_id: databaseTargetId}});
      if(token === serial.current) {setTables(data.tables || []); setSelected(previous =>
        (data.tables || []).some(item => item.resource_id === previous) ? previous :
          (data.tables || []).some(item => item.resource_id === resourceId) ? resourceId :
            data.tables?.[0]?.resource_id || '');}
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'Native tables unavailable');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const inspectCapabilities = async () => {
    const token = ++serial.current; setBusy(true); setError('');
    try {
      const value = await post({action: 'duckdb_copy_plan', request: {
        database_target_id: databaseTargetId, operation: 'capabilities'}});
      if(token === serial.current) setCapabilities(value);
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'COPY capabilities unavailable');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const buildOptions = () => {
    const opts = {};
    if(direction === 'to') {
      const pCols = partitionByText.split(',').map(item => item.trim()).filter(Boolean);
      if(pCols.length) {
        opts.partition_by = pCols;
        if(writePartitionColumns) opts.write_partition_columns = true;
        if(filenamePattern.trim()) opts.filename_pattern = filenamePattern.trim();
      }
      if(overwriteOrIgnore) opts.overwrite_or_ignore = true;
    }
    if(format === 'CSV') {
      if(csvHeader === 'true' || csvHeader === 'false') opts.header = csvHeader === 'true';
      if(csvDelimiter) opts.delimiter = csvDelimiter;
      if(csvQuote) opts.quote = csvQuote;
      if(csvEscape) opts.escape = csvEscape;
      if(csvNullstr) opts.nullstr = csvNullstr;
      if(csvCompression) opts.compression = csvCompression;
      if(csvEncoding) opts.encoding = csvEncoding;
      if(direction !== 'to') {
        if(csvAutoDetect) opts.auto_detect = true;
        if(csvIgnoreErrors) opts.ignore_errors = true;
      } else {
        const fq = csvForceQuote.split(',').map(item => item.trim()).filter(Boolean);
        if(fq.length) opts.force_quote = fq;
      }
    } else if(format === 'PARQUET') {
      if(parquetCompression) opts.compression = parquetCompression;
      if(parquetEncryptionKeyName.trim()) opts.encryption_key_name = parquetEncryptionKeyName.trim();
      if(direction === 'to') {
        if(parquetRowGroupSize.trim()) opts.row_group_size = Number(parquetRowGroupSize.trim());
        if(parquetFieldIdsAuto) opts.field_ids = 'AUTO';
      } else {
        if(parquetUnionByName) opts.union_by_name = true;
        if(parquetHivePartitioning) opts.hive_partitioning = true;
        if(parquetFilename) opts.filename = true;
      }
    } else if(format === 'JSON') {
      if(jsonFormat) opts.json_format = jsonFormat;
      if(jsonCompression) opts.compression = jsonCompression;
      if(direction !== 'to') {
        if(jsonAutoDetect) opts.auto_detect = true;
        if(jsonMaxObjectSize.trim()) opts.maximum_object_size = Number(jsonMaxObjectSize.trim());
      }
    }
    return opts;
  };
  const preview = async () => {
    const token = ++serial.current; setBusy(true); setError(''); setResult(null);
    try {
      const options = buildOptions();
      const request = {
        database_target_id: databaseTargetId,
        direction,
        format,
        path,
        ...(direction === 'reader_ctas'
          ? {target_schema: targetSchema, target_table: targetTable}
          : {resource_id: selected}),
        ...(direction !== 'to' && partitionedSource ? {partitioned_source: true} : {}),
        ...(Object.keys(options).length ? {options} : {}),
      };
      const value = await post({action: 'duckdb_copy_plan', request});
      if(token === serial.current) setResult(value);
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'COPY preview failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([result.source], {type: 'text/plain'}));
    const link = document.createElement('a'); link.href = url; link.download = 'duckdb-copy.sql';
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const clear = () => setResult(null);
  const canPreview = direction === 'reader_ctas'
    ? Boolean(targetSchema.trim() && targetTable.trim() && path)
    : Boolean(selected && path);
  const partitionSet = Boolean(partitionByText.split(',').map(item => item.trim()).filter(Boolean).length);
  return <Box sx={{...compactFormSx, gridAutoRows: 'max-content', p: 1, overflow: 'auto'}}>
    <FormReference formKey="duckdb-copy" />
    <Alert severity="info">Preview one native COPY or direct reader statement for the selected registered file. Open the downloaded script on this same file in the shared Query Tool to execute it. Export creates an external file or Hive partition directory that SQL rollback may not remove.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap', my: 1}}>
      <Button disabled={busy} onClick={load}>Load native tables</Button>
      <Button disabled={busy} onClick={inspectCapabilities}>Inspect format capabilities</Button>
      {direction !== 'reader_ctas' && (
        <TextField select size="small" label="Native table" value={selected} disabled={busy || !tables.length}
          onChange={event => {setSelected(event.target.value); clear();}} sx={{minWidth: 260}}>
          {tables.map(table => <MenuItem key={table.resource_id} value={table.resource_id}>{table.catalog}.{table.schema}.{table.name}</MenuItem>)}
        </TextField>
      )}
      {direction === 'reader_ctas' && <>
        <TextField size="small" label="Target schema" value={targetSchema} disabled={busy}
          onChange={event => {setTargetSchema(event.target.value); clear();}} sx={{width: 160}} />
        <TextField size="small" label="New target table" value={targetTable} disabled={busy}
          onChange={event => {setTargetTable(event.target.value); clear();}} sx={{width: 200}} />
      </>}
      <TextField select size="small" label="Direction" value={direction} disabled={busy}
        onChange={event => {setDirection(event.target.value); clear();}}>
        <MenuItem value="to">Export table to file</MenuItem>
        <MenuItem value="from">Import file into table</MenuItem>
        <MenuItem value="reader_ctas">Create table from reader (CTAS)</MenuItem>
        <MenuItem value="reader_insert">Insert into table from reader</MenuItem>
      </TextField>
      <TextField select size="small" label="Format" value={format} disabled={busy}
        onChange={event => {setFormat(event.target.value); clear();}}>
        <MenuItem value="PARQUET">PARQUET</MenuItem>
        <MenuItem value="CSV">CSV with header</MenuItem>
        <MenuItem value="JSON">JSON / NDJSON</MenuItem>
      </TextField>
      <TextField size="small" label="Absolute file path" value={path} disabled={busy} sx={{minWidth: 340}}
        onChange={event => {setPath(event.target.value); clear();}} />
      {direction !== 'to' && (
        <FormControlLabel label="Partitioned source directory" control={<Checkbox checked={partitionedSource} disabled={busy}
          onChange={event => {setPartitionedSource(event.target.checked); clear();}} />} />
      )}
      <Button disabled={busy || !canPreview} onClick={preview}>Preview native COPY</Button>
      <Button disabled={busy || !result} onClick={download}>Save SQL script</Button>
    </Box>
    <Box sx={{display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap', my: 1}}>
      {direction === 'to' && <>
        <TextField size="small" label="Partition columns (comma-separated)" value={partitionByText} disabled={busy}
          onChange={event => {setPartitionByText(event.target.value); clear();}} sx={{minWidth: 240}} />
        <FormControlLabel label="Overwrite or ignore" control={<Checkbox checked={overwriteOrIgnore} disabled={busy}
          onChange={event => {setOverwriteOrIgnore(event.target.checked); clear();}} />} />
        {partitionSet && <>
          <FormControlLabel label="Write partition columns" control={<Checkbox checked={writePartitionColumns} disabled={busy}
            onChange={event => {setWritePartitionColumns(event.target.checked); clear();}} />} />
          <TextField size="small" label="Filename pattern" value={filenamePattern} disabled={busy}
            onChange={event => {setFilenamePattern(event.target.value); clear();}} sx={{width: 200}} />
        </>}
      </>}
      {format === 'CSV' && <>
        <TextField select size="small" label="CSV header" value={csvHeader} disabled={busy} sx={{width: 150}}
          onChange={event => {setCsvHeader(event.target.value); clear();}}>
          <MenuItem value="">Engine default</MenuItem><MenuItem value="true">Include header</MenuItem><MenuItem value="false">No header</MenuItem>
        </TextField>
        <TextField size="small" label="CSV delimiter" value={csvDelimiter} disabled={busy} sx={{width: 120}}
          onChange={event => {setCsvDelimiter(event.target.value); clear();}} />
        <TextField size="small" label="CSV quote" value={csvQuote} disabled={busy} sx={{width: 110}}
          onChange={event => {setCsvQuote(event.target.value); clear();}} />
        <TextField size="small" label="CSV escape" value={csvEscape} disabled={busy} sx={{width: 110}}
          onChange={event => {setCsvEscape(event.target.value); clear();}} />
        <TextField size="small" label="CSV NULL string" value={csvNullstr} disabled={busy} sx={{width: 140}}
          onChange={event => {setCsvNullstr(event.target.value); clear();}} />
        <TextField select size="small" label="CSV compression" value={csvCompression} disabled={busy} sx={{width: 150}}
          onChange={event => {setCsvCompression(event.target.value); clear();}}>
          <MenuItem value="">Default</MenuItem><MenuItem value="NONE">NONE</MenuItem><MenuItem value="GZIP">GZIP</MenuItem><MenuItem value="ZSTD">ZSTD</MenuItem>
        </TextField>
        <TextField select size="small" label="CSV encoding" value={csvEncoding} disabled={busy} sx={{width: 140}}
          onChange={event => {setCsvEncoding(event.target.value); clear();}}>
          <MenuItem value="">Default</MenuItem><MenuItem value="UTF-8">UTF-8</MenuItem><MenuItem value="UTF-16">UTF-16</MenuItem><MenuItem value="LATIN-1">LATIN-1</MenuItem>
        </TextField>
        {direction === 'to' ? (
          <TextField size="small" label="Force quote columns" value={csvForceQuote} disabled={busy} sx={{width: 200}}
            onChange={event => {setCsvForceQuote(event.target.value); clear();}} />
        ) : <>
          <FormControlLabel label="Auto-detect CSV dialect" control={<Checkbox checked={csvAutoDetect} disabled={busy}
            onChange={event => {setCsvAutoDetect(event.target.checked); clear();}} />} />
          <FormControlLabel label="Ignore malformed rows" control={<Checkbox checked={csvIgnoreErrors} disabled={busy}
            onChange={event => {setCsvIgnoreErrors(event.target.checked); clear();}} />} />
        </>}
      </>}
      {format === 'PARQUET' && <>
        <TextField select size="small" label="Parquet compression" value={parquetCompression} disabled={busy} sx={{width: 170}}
          onChange={event => {setParquetCompression(event.target.value); clear();}}>
          <MenuItem value="">Default</MenuItem><MenuItem value="UNCOMPRESSED">UNCOMPRESSED</MenuItem><MenuItem value="SNAPPY">SNAPPY</MenuItem>
          <MenuItem value="GZIP">GZIP</MenuItem><MenuItem value="ZSTD">ZSTD</MenuItem><MenuItem value="BROTLI">BROTLI</MenuItem><MenuItem value="LZ4">LZ4</MenuItem>
        </TextField>
        <TextField size="small" label="Encryption key name" value={parquetEncryptionKeyName} disabled={busy} sx={{width: 190}}
          onChange={event => {setParquetEncryptionKeyName(event.target.value); clear();}} />
        {direction === 'to' ? <>
          <TextField size="small" label="Parquet row group size" value={parquetRowGroupSize} disabled={busy} sx={{width: 180}}
            onChange={event => {setParquetRowGroupSize(event.target.value); clear();}} />
          <FormControlLabel label="Auto field IDs" control={<Checkbox checked={parquetFieldIdsAuto} disabled={busy}
            onChange={event => {setParquetFieldIdsAuto(event.target.checked); clear();}} />} />
        </> : <>
          <FormControlLabel label="Union by name" control={<Checkbox checked={parquetUnionByName} disabled={busy}
            onChange={event => {setParquetUnionByName(event.target.checked); clear();}} />} />
          <FormControlLabel label="Hive partitioning" control={<Checkbox checked={parquetHivePartitioning} disabled={busy}
            onChange={event => {setParquetHivePartitioning(event.target.checked); clear();}} />} />
          <FormControlLabel label="Include filename column" control={<Checkbox checked={parquetFilename} disabled={busy}
            onChange={event => {setParquetFilename(event.target.checked); clear();}} />} />
        </>}
      </>}
      {format === 'JSON' && <>
        <TextField select size="small" label="JSON layout" value={jsonFormat} disabled={busy} sx={{width: 200}}
          onChange={event => {setJsonFormat(event.target.value); clear();}}>
          <MenuItem value="">Default (NDJSON)</MenuItem><MenuItem value="NEWLINE_DELIMITED">NEWLINE_DELIMITED</MenuItem><MenuItem value="ARRAY">ARRAY</MenuItem>
        </TextField>
        <TextField select size="small" label="JSON compression" value={jsonCompression} disabled={busy} sx={{width: 160}}
          onChange={event => {setJsonCompression(event.target.value); clear();}}>
          <MenuItem value="">Default</MenuItem><MenuItem value="NONE">NONE</MenuItem><MenuItem value="GZIP">GZIP</MenuItem><MenuItem value="ZSTD">ZSTD</MenuItem>
        </TextField>
        {direction !== 'to' && <>
          <FormControlLabel label="Auto-detect JSON schema" control={<Checkbox checked={jsonAutoDetect} disabled={busy}
            onChange={event => {setJsonAutoDetect(event.target.checked); clear();}} />} />
          <TextField size="small" label="Max JSON object size (bytes)" value={jsonMaxObjectSize} disabled={busy} sx={{width: 210}}
            onChange={event => {setJsonMaxObjectSize(event.target.value); clear();}} />
        </>}
      </>}
    </Box>
    {capabilities && <Box component="pre" aria-label="DuckDB COPY format capabilities" sx={{whiteSpace: 'pre-wrap'}}>{JSON.stringify(capabilities, null, 2)}</Box>}
    {result && <><Alert severity="success">One native {result.native_format} COPY statement generated; not executed.</Alert>
      <Box component="textarea" aria-label="Generated DuckDB COPY SQL" value={result.source} readOnly
        sx={{width: '100%', boxSizing: 'border-box', minHeight: 100, resize: 'vertical', fontFamily: 'monospace', fontSize: '0.875rem'}} />
    </>}
  </Box>;
}
DuckDBCopy.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string.isRequired,
  resourceId: PropTypes.string};
