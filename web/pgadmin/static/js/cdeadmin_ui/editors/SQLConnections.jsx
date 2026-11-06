import {createContext, useContext, useEffect, useState, useSyncExternalStore} from 'react';
import PropTypes from 'prop-types';
import {Box, MenuItem, TextField, Tabs, Tab} from '@mui/material';
import CodeEditor from './CodeEditor';
import {QueryToolFrame, QueryToolToolbar, QueryToolAction} from './QueryToolControls';
import {workbenchContextService} from '../platform/PlatformRegistry';
let entries = [], selected = '';
const listeners = new Set();
// Every change bumps the version, so a component that subscribes after a
// change (a parent subscribes after its children's effects) still re-renders.
let version = 0;
function notifyAll() {version += 1; listeners.forEach(notify => notify());}
function subscribe(notify) {listeners.add(notify); return () => listeners.delete(notify);}
// Connections whose content shows the selector in its own query toolbar.
const slotHosts = new Set();
const SlotContext = createContext(null);
export function registerSQLConnection(connection) {
  if (!entries.some(item => item.id === connection.id)) entries = [...entries, connection];
  workbenchContextService.update({connectionState: entries.length ? 'connected' : 'disconnected'});
  notifyAll();
}
export function removeSQLConnections(serverId, databaseTargetId) {
  entries = entries.filter(item => String(item.serverId) !== String(serverId) ||
    (databaseTargetId !== undefined && item.databaseTargetId !== databaseTargetId));
  if (!entries.some(item => item.id === selected)) selected = '';
  workbenchContextService.update({connectionState: entries.length ? 'connected' : 'disconnected'});
  notifyAll();
}
export function activateSQLConnection(connection) {
  if (!entries.some(item => item.id === connection.id)) entries = [...entries, connection];
  entries = entries.map(item => item.id === connection.id ? {...item, content: item.content || connection.content} : item);
  selected = connection.id;
  workbenchContextService.update({connectionState: entries.length ? 'connected' : 'disconnected'});
  notifyAll();
}
export function labelSQLConnection(id, label, engine) {
  if (!entries.some(item => item.id === id && (item.label !== label || (!item.engine && engine)))) return;
  entries = entries.map(item => item.id === id ? {...item, label, engine: item.engine || engine} : item);
  workbenchContextService.update({connectionState: entries.length ? 'connected' : 'disconnected'});
  notifyAll();
}
export function useSQLConnections() {
  useSyncExternalStore(subscribe, () => version);
  return {entries, selected};
}
/**
 * The SQL tab's connection selector. Owner direction 2026-11-05: it sits at
 * the right of the query toolbar, after the dialect and max rows fields.
 */
export function SQLConnectionSelect() {
  const state = useSQLConnections();
  return <TextField select size="small" label="Connection" value={state.selected} disabled={!state.entries.length}
    InputProps={{sx: {minWidth: '16rem', maxWidth: '40rem'}}} onChange={event => {
      const entry = entries.find(item => item.id === event.target.value);
      if (entry?.open && !entry.content) entry.open();
      else {selected = event.target.value; notifyAll();}
    }}>
    <MenuItem value="" disabled>Select a connected database</MenuItem>
    {state.entries.map(item => <MenuItem key={item.id} value={item.id}>{item.engine ? `${item.engine} — ${item.label}` : item.label}</MenuItem>)}
  </TextField>;
}

/**
 * Where a connection's own query toolbar shows the selector. Outside the SQL
 * tab it renders nothing. A connection whose content has no slot keeps the
 * selector in a toolbar of its own, so switching is always possible.
 */
export function SQLConnectionSlot() {
  const entryId = useContext(SlotContext);
  useEffect(() => {
    if (entryId === null) return undefined;
    slotHosts.add(entryId); notifyAll();
    return () => {slotHosts.delete(entryId); notifyAll();};
  }, [entryId]);
  return entryId === null ? null : <SQLConnectionSelect />;
}

function DisconnectedQueryTool({hasConnections}) {
  const [panel, setPanel] = useState('data');
  return <QueryToolFrame aria-label="SQL query tool">
    <QueryToolToolbar aria-label="SQL execution toolbar">
      <QueryToolAction action="execute" title="Run" disabled />
      <QueryToolAction action="cancel" title="Cancel request" disabled />
      <QueryToolAction action="commit" title="Commit" disabled />
      <QueryToolAction action="rollback" title="Rollback" disabled />
      <TextField size="small" label="Dialect" value="No connection selected" disabled sx={{ml: 1}}
        InputProps={{sx: {width: 200}}} />
      <TextField size="small" label="Max rows" value={500} type="number" disabled InputProps={{sx: {width: 80}}} />
      <SQLConnectionSelect />
    </QueryToolToolbar>
    <Box role="status" sx={{px: 1, py: 0.5, color: 'text.secondary'}}>
      {hasConnections ? 'Select a connected database to enable execution and its engine-specific tools.' :
        'Connect to a database in the explorer to select its connection.'}
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

DisconnectedQueryTool.propTypes = {hasConnections: PropTypes.bool};

export default function SQLConnections() {
  const state = useSQLConnections();
  const hosted = Boolean(state.selected) && slotHosts.has(state.selected);
  return <QueryToolFrame sx={{color: 'text.primary', bgcolor: 'background.default'}}>
    {state.selected && !hosted && <QueryToolToolbar><SQLConnectionSelect /></QueryToolToolbar>}
    {!state.selected && <DisconnectedQueryTool hasConnections={state.entries.length > 0} />}
    {state.entries.filter(item => item.content).map(item => <Box key={item.id} sx={{display: item.id === state.selected ? 'flex' : 'none',
      flexDirection: 'column', flex: 1, minHeight: 0}}><SlotContext.Provider value={item.id}>{item.content}</SlotContext.Provider></Box>)}
  </QueryToolFrame>;
}
