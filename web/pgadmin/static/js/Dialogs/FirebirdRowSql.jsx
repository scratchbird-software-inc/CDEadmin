import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';
import {useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {generateRowSql} from './firebirdRowSqlHelpers';

export default function FirebirdRowSql({page, table, onLoad, disabled}) {
  const [selected, setSelected] = useState([]);
  const [keys, setKeys] = useState([]);
  const [operation, setOperation] = useState('insert');
  const [inline, setInline] = useState(false);
  const [inColumn, setInColumn] = useState('');
  const [plans, setPlans] = useState([]);
  const [error, setError] = useState(null);
  useEffect(() => {setSelected([]); setPlans([]); setError(null); setKeys(page.columns.filter(column => column.key === true || column.identity_key).map(column => column.name)); setInColumn(page.columns[0]?.name || '');}, [page, table]);
  const change = (fn) => {setPlans([]); setError(null); fn();};
  const toggle = (values, value) => values.includes(value) ? values.filter(item => item !== value) : [...values, value];
  const generate = () => {
    try {setPlans(generateRowSql({table, columns: page.columns, rows: page.rows.filter((_row, index) => selected.includes(index)), operation, keys, inColumn, inline})); setError(null);}
    catch (failure) {setError(failure.message); setPlans([]);}
  };
  return <Box data-cde-compact-form sx={{my: 2, ...compactFormSx}}>
    <FormReference formKey="firebird-row-sql" />
    <Alert severity="info">Generate SQL from fetched rows, excluding unsaved drafts. Preview does not execute. Executing generated statements may duplicate or change data. User-selected matching columns must identify the intended rows.</Alert>
    <TextField select label="Row SQL operation" value={operation} onChange={event => change(() => setOperation(event.target.value))}>
      <MenuItem value="insert">INSERT</MenuItem><MenuItem value="update">UPDATE</MenuItem><MenuItem value="upsert">UPDATE OR INSERT</MenuItem><MenuItem value="in">IN list</MenuItem>
    </TextField>
    <FormControlLabel label="Inline scalar literals" control={<Checkbox checked={inline} onChange={event => change(() => setInline(event.target.checked))} />} />
    {['update', 'upsert'].includes(operation) && <Box>Matching columns:
      {page.columns.map(column => <FormControlLabel key={column.name} label={column.name} control={<Checkbox checked={keys.includes(column.name)} onChange={() => change(() => setKeys(toggle(keys, column.name)))} />} />)}
    </Box>}
    {operation === 'in' && <TextField select label="IN-list column" value={inColumn} onChange={event => change(() => setInColumn(event.target.value))}>
      {page.columns.map(column => <MenuItem key={column.name} value={column.name}>{column.name}</MenuItem>)}
    </TextField>}
    <Box sx={{maxHeight: 180, overflow: 'auto'}}>{page.rows.map((_row, index) => <FormControlLabel key={index} label={`Fetched row ${index + 1}`} control={<Checkbox checked={selected.includes(index)} onChange={() => change(() => setSelected(toggle(selected, index)))} />} />)}</Box>
    <Button disabled={disabled || !selected.length} onClick={generate}>Generate row SQL</Button>
    {error && <Alert severity="error">{error}</Alert>}
    {plans.map((plan, index) => <Box key={index} sx={{my: 1}}>
      <TextField multiline fullWidth label={`Generated SQL ${index + 1}`} value={plan.source} InputProps={{readOnly: true}} />
      <TextField multiline fullWidth label={`Ordered parameters ${index + 1}`} value={JSON.stringify(plan.parameters)} InputProps={{readOnly: true}} />
      <Button onClick={async () => {try {await navigator.clipboard.writeText(plan.source);} catch {setError('Clipboard unavailable. Select and copy the displayed SQL.');}}}>Copy SQL</Button>
      <Button onClick={async () => {try {await navigator.clipboard.writeText(JSON.stringify(plan.parameters));} catch {setError('Clipboard unavailable. Select and copy the displayed parameters.');}}}>Copy parameters</Button>
      <Button disabled={disabled || !onLoad} onClick={() => onLoad(plan)}>Load statement into SQL editor</Button>
    </Box>)}
  </Box>;
}
FirebirdRowSql.propTypes = {page: PropTypes.object.isRequired, table: PropTypes.string.isRequired, onLoad: PropTypes.func, disabled: PropTypes.bool};
