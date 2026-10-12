import {useEffect, useState} from 'react';
import {Box, MenuItem, TextField} from '@mui/material';
import CodeEditor from './CodeEditor';
import {workbenchContextService} from '../platform/PlatformRegistry';
let entries = [], selected = '';
const listeners = new Set();
export function registerSQLConnection(connection) {
  if (!entries.some(item => item.id === connection.id)) entries = [...entries, connection];
  workbenchContextService.update({connectionState: entries.length ? 'connected' : 'disconnected'});
  listeners.forEach(notify => notify());
}
export function removeSQLConnections(serverId, databaseTargetId) {
  entries = entries.filter(item => String(item.serverId) !== String(serverId) ||
    (databaseTargetId !== undefined && item.databaseTargetId !== databaseTargetId));
  if (!entries.some(item => item.id === selected)) selected = '';
  workbenchContextService.update({connectionState: entries.length ? 'connected' : 'disconnected'});
  listeners.forEach(notify => notify());
}
export function activateSQLConnection(connection) {
  if (!entries.some(item => item.id === connection.id)) entries = [...entries, connection];
  entries = entries.map(item => item.id === connection.id ? {...item, content: item.content || connection.content} : item);
  selected = connection.id;
  workbenchContextService.update({connectionState: entries.length ? 'connected' : 'disconnected'});
  listeners.forEach(notify => notify());
}
export function labelSQLConnection(id, label) {
  if (!entries.some(item => item.id === id && item.label !== label)) return;
  entries = entries.map(item => item.id === id ? {...item, label} : item);
  workbenchContextService.update({connectionState: entries.length ? 'connected' : 'disconnected'});
  listeners.forEach(notify => notify());
}
export function useSQLConnections() {
  const [, update] = useState(0);
  useEffect(() => {const notify = () => update(value => value + 1); listeners.add(notify);
    return () => listeners.delete(notify);}, []);
  return {entries, selected};
}
export default function SQLConnections() {
  const state = useSQLConnections();
  return <Box sx={{height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0}}>
    <TextField select size="small" label="Active connection" value={state.selected} disabled={!state.entries.length}
      helperText={!state.entries.length ? 'Connect to a database in the explorer to select its connection.' : undefined}
      sx={{m: 0.5, maxWidth: '48rem'}} onChange={event => {
        const entry = entries.find(item => item.id === event.target.value);
        if (entry?.open && !entry.content) entry.open();
        else {selected = event.target.value; listeners.forEach(notify => notify());}
      }}>
      <MenuItem value="" disabled>Select a connected database</MenuItem>
      {state.entries.map(item => <MenuItem key={item.id} value={item.id}>{item.label}</MenuItem>)}
    </TextField>
    {!state.selected && <Box sx={{flex: 1, minHeight: 0}}><CodeEditor label="SQL source" value="" readonly disabled /></Box>}
    {state.entries.filter(item => item.content).map(item => <Box key={item.id} sx={{display: item.id === state.selected ? 'flex' : 'none',
      flexDirection: 'column', flex: 1, minHeight: 0}}>{item.content}</Box>)}
  </Box>;
}
