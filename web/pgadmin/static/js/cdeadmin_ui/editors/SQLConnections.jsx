import {useEffect, useState} from 'react';
import {Box, MenuItem, TextField, Tabs, Tab} from '@mui/material';
import CodeEditor from './CodeEditor';
import {QueryToolFrame, QueryToolToolbar, QueryToolAction} from './QueryToolControls';
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
export function labelSQLConnection(id, label, engine) {
  if (!entries.some(item => item.id === id && (item.label !== label || (!item.engine && engine)))) return;
  entries = entries.map(item => item.id === id ? {...item, label, engine: item.engine || engine} : item);
  workbenchContextService.update({connectionState: entries.length ? 'connected' : 'disconnected'});
  listeners.forEach(notify => notify());
}
export function useSQLConnections() {
  const [, update] = useState(0);
  useEffect(() => {const notify = () => update(value => value + 1); listeners.add(notify);
    return () => listeners.delete(notify);}, []);
  return {entries, selected};
}
function DisconnectedQueryTool() {
  const [panel, setPanel] = useState('data');
  return <QueryToolFrame aria-label="SQL query tool">
    <QueryToolToolbar aria-label="SQL execution toolbar">
      <QueryToolAction action="execute" title="Run" disabled />
      <QueryToolAction action="cancel" title="Cancel request" disabled />
      <QueryToolAction action="commit" title="Commit" disabled />
      <QueryToolAction action="rollback" title="Rollback" disabled />
      <TextField size="small" label="Engine / dialect" value="No connection selected" disabled sx={{width: 220, ml: 1}} />
      <TextField size="small" label="Maximum rows per fetch" value={500} type="number" disabled sx={{width: 155}} />
    </QueryToolToolbar>
    <Box role="status" sx={{px: 1, py: 0.5, color: 'text.secondary'}}>
      Select a connected database to enable execution and its engine-specific tools.
    </Box>
    <Box sx={{height: '45%', minHeight: 120, resize: 'vertical', overflow: 'auto', flexShrink: 0}}>
      <CodeEditor label="SQL source" value="" readonly disabled />
    </Box>
    <Box sx={{flex: 1, minHeight: 120, overflow: 'auto'}}>
      <Tabs value={panel} onChange={(_, value) => setPanel(value)} aria-label="SQL result panels">
        <Tab value="data" label="Data Output" />
        <Tab value="messages" label="Messages" />
      </Tabs>
      <Box role="status" aria-label="Statement metrics" sx={{px: 1, py: 0.5}}>
        Buffered rows: 0 · Preparation: — · Execution: — · Plan used: —
      </Box>
      <Box role="tabpanel" aria-label="Data Output" hidden={panel !== 'data'} sx={{p: 1}}>No query results.</Box>
      <Box role="tabpanel" aria-label="Messages" hidden={panel !== 'messages'} sx={{p: 1}}>No connection selected.</Box>
    </Box>
  </QueryToolFrame>;
}

export default function SQLConnections() {
  const state = useSQLConnections();
  return <QueryToolFrame sx={{color: 'text.primary', bgcolor: 'background.default'}}>
    <QueryToolToolbar>
      <TextField select size="small" label="Active connection" value={state.selected} disabled={!state.entries.length}
        helperText={!state.entries.length ? 'Connect to a database in the explorer to select its connection.' : undefined}
        sx={{m: 0.5, maxWidth: '48rem'}} onChange={event => {
          const entry = entries.find(item => item.id === event.target.value);
          if (entry?.open && !entry.content) entry.open();
          else {selected = event.target.value; listeners.forEach(notify => notify());}
        }}>
        <MenuItem value="" disabled>Select a connected database</MenuItem>
        {state.entries.map(item => <MenuItem key={item.id} value={item.id}>{item.engine ? `${item.engine} — ${item.label}` : item.label}</MenuItem>)}
      </TextField>
    </QueryToolToolbar>
    {!state.selected && <DisconnectedQueryTool />}
    {state.entries.filter(item => item.content).map(item => <Box key={item.id} sx={{display: item.id === state.selected ? 'flex' : 'none',
      flexDirection: 'column', flex: 1, minHeight: 0}}>{item.content}</Box>)}
  </QueryToolFrame>;
}
