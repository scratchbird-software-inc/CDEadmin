import {createContext, useCallback, useContext, useEffect, useRef, useState, useSyncExternalStore} from 'react';
import PropTypes from 'prop-types';
import {Box, MenuItem, TextField, Tabs, Tab} from '@mui/material';
import CodeEditor from './CodeEditor';
import {Button} from '../primitives/Button';
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

function splitEndpointAndTarget(rawUrl, explicitDatabaseTargetId) {
  const str = String(rawUrl || '');
  if (str.includes('::')) {
    const sep = str.indexOf('::');
    const base = str.slice(0, sep);
    const suffix = str.slice(sep + 2);
    return {
      endpointUrl: base,
      databaseTargetId: explicitDatabaseTargetId !== undefined && explicitDatabaseTargetId !== null
        ? String(explicitDatabaseTargetId)
        : suffix,
    };
  }
  let parsedTarget = '';
  let normalizedUrl = str;
  const qIdx = str.indexOf('?');
  if (qIdx >= 0) {
    const pathPart = str.slice(0, qIdx);
    const params = new URLSearchParams(str.slice(qIdx + 1));
    if (params.has('database_target_id')) {
      parsedTarget = params.get('database_target_id') || '';
      params.delete('database_target_id');
    }
    const rest = params.toString();
    normalizedUrl = rest ? `${pathPart}?${rest}` : pathPart;
  }
  const resolvedTarget = explicitDatabaseTargetId !== undefined && explicitDatabaseTargetId !== null
    ? String(explicitDatabaseTargetId)
    : parsedTarget;
  return {endpointUrl: normalizedUrl, databaseTargetId: resolvedTarget};
}

export function sqlConnectionKey(idOrConnection, explicitDatabaseTargetId) {
  if (idOrConnection && typeof idOrConnection === 'object') {
    const rawUrl = idOrConnection.endpointUrl ?? idOrConnection.id ?? '';
    const targetId = explicitDatabaseTargetId !== undefined
      ? explicitDatabaseTargetId
      : idOrConnection.databaseTargetId;
    const {endpointUrl, databaseTargetId} = splitEndpointAndTarget(rawUrl, targetId);
    return `${endpointUrl}::${databaseTargetId || ''}`;
  }
  const {endpointUrl, databaseTargetId} = splitEndpointAndTarget(idOrConnection, explicitDatabaseTargetId);
  return `${endpointUrl}::${databaseTargetId || ''}`;
}

function normalizeConnectionEntry(connection) {
  const key = sqlConnectionKey(connection);
  const {endpointUrl, databaseTargetId} = splitEndpointAndTarget(
    connection?.endpointUrl ?? connection?.id ?? '',
    connection?.databaseTargetId,
  );
  return {
    ...connection,
    id: key,
    endpointUrl: connection?.id && !String(connection.id).includes('::') ? connection.id : endpointUrl,
    baseEndpointUrl: endpointUrl,
    databaseTargetId: databaseTargetId || connection?.databaseTargetId || '',
  };
}

export function registerSQLConnection(connection) {
  const normalized = normalizeConnectionEntry(connection);
  if (!entries.some(item => item.id === normalized.id)) entries = [...entries, normalized];
  else if (normalized.openQuickQuery || normalized.open) {
    entries = entries.map((item) => item.id === normalized.id ? {
      ...item,
      open: normalized.open || item.open,
      openQuickQuery: normalized.openQuickQuery || item.openQuickQuery,
    } : item);
  }
  workbenchContextService.update({connectionState: entries.length ? 'connected' : 'disconnected'});
  notifyAll();
}
export function removeSQLConnections(serverId, databaseTargetId) {
  entries = entries.filter(item => String(item.serverId) !== String(serverId) ||
    (databaseTargetId !== undefined && String(item.databaseTargetId || '') !== String(databaseTargetId || '')));
  if (!entries.some(item => item.id === selected)) selected = entries[0]?.id || '';
  if (!entries.length) selected = '';
  workbenchContextService.update({connectionState: entries.length ? 'connected' : 'disconnected'});
  notifyAll();
}
export function activateSQLConnection(connection) {
  const normalized = normalizeConnectionEntry(connection);
  if (!entries.some(item => item.id === normalized.id)) entries = [...entries, normalized];
  entries = entries.map(item => item.id === normalized.id
    ? {...item, ...normalized, content: item.content || normalized.content}
    : item);
  selected = normalized.id;
  workbenchContextService.update({connectionState: entries.length ? 'connected' : 'disconnected'});
  notifyAll();
}
export function labelSQLConnection(id, label, engine, databaseTargetId) {
  const key = sqlConnectionKey(id, databaseTargetId);
  const {endpointUrl, databaseTargetId: parsedTarget} = splitEndpointAndTarget(id, databaseTargetId);
  const matchesEntry = (item) =>
    item.id === key ||
    (!parsedTarget && item.endpointUrl === id && entries.filter(e => e.baseEndpointUrl === endpointUrl).length === 1);
  if (!entries.some(item => matchesEntry(item) && (item.label !== label || (!item.engine && engine)))) return;
  entries = entries.map(item => matchesEntry(item) ? {...item, label, engine: item.engine || engine} : item);
  workbenchContextService.update({connectionState: entries.length ? 'connected' : 'disconnected'});
  notifyAll();
}
export function useSQLConnections() {
  useSyncExternalStore(subscribe, () => version);
  return {entries, selected};
}
// Source requests for a connection's editor (Browse data). The editor may
// already be open, so a request is posted here rather than passed on open.
const sourceRequests = new Map();
let requestSequence = 0;
export function requestSQLSource(id, request, databaseTargetId) {
  const key = sqlConnectionKey(id, databaseTargetId ?? request?.database_target_id ?? request?.databaseTargetId);
  sourceRequests.set(key, {...request, nonce: ++requestSequence});
  notifyAll();
}
export function takeSQLSourceRequest(id, nonce, databaseTargetId) {
  const key = sqlConnectionKey(id, databaseTargetId);
  if (sourceRequests.get(key)?.nonce === nonce) {
    sourceRequests.delete(key);
    return;
  }
  for (const [entryKey, pending] of sourceRequests.entries()) {
    if (pending?.nonce === nonce) {
      sourceRequests.delete(entryKey);
      break;
    }
  }
}
export function useSQLSourceRequest(id, databaseTargetId) {
  const slotEntryId = useContext(SlotContext);
  useSyncExternalStore(subscribe, () => version);
  const key = sqlConnectionKey(id, databaseTargetId);
  if (sourceRequests.has(key)) return sourceRequests.get(key) || null;
  if (slotEntryId) {
    const {endpointUrl, databaseTargetId: parsedTarget} = splitEndpointAndTarget(id, databaseTargetId);
    if (!parsedTarget && slotEntryId.startsWith(`${endpointUrl}::`) && sourceRequests.has(slotEntryId)) {
      return sourceRequests.get(slotEntryId) || null;
    }
  }
  return null;
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

function DisconnectedQueryTool({hasConnections, sqlText, onSqlTextChange, onSaveAsBiQuestion}) {
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
      <Button size="sm" variant="secondary" onClick={onSaveAsBiQuestion}>Save as BI Question…</Button>
    </QueryToolToolbar>
    <Box role="status" sx={{px: 1, py: 0.5, color: 'text.secondary'}}>
      {hasConnections ? 'Select a connected database to enable execution and its engine-specific tools.' :
        'Connect to a database in the explorer to select its connection.'}
    </Box>
    <Box sx={{height: '45%', minHeight: 120, resize: 'vertical', overflow: 'auto', flexShrink: 0}}>
      <CodeEditor label="SQL source" language="sql" value={sqlText} onChange={onSqlTextChange} />
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

DisconnectedQueryTool.propTypes = {
  hasConnections: PropTypes.bool,
  sqlText: PropTypes.string,
  onSqlTextChange: PropTypes.func,
  onSaveAsBiQuestion: PropTypes.func,
};

export default function SQLConnections({instanceId = null}) {
  const state = useSQLConnections();
  const rootRef = useRef(null);
  const [draftSql, setDraftSql] = useState('');
  const draftSqlRef = useRef('');
  draftSqlRef.current = draftSql;
  const hosted = Boolean(state.selected) && slotHosts.has(state.selected);

  const handleDraftSqlChange = useCallback((val) => {
    const next = typeof val === 'string' ? val : val?.target?.value ?? '';
    if (next === draftSqlRef.current) return;
    draftSqlRef.current = next;
    setDraftSql(next);
  }, []);

  const readCurrentEditorSql = useCallback(() => {
    if (state.selected && rootRef.current) {
      const activeBox = rootRef.current.querySelector('[data-active-connection="true"]');
      const field = activeBox?.querySelector('textarea, input[type="text"], input:not([type])');
      if (field && typeof field.value === 'string' && field.value.trim()) {
        return field.value;
      }
    }
    return draftSql;
  }, [state.selected, draftSql]);

  const handleSaveAsBiQuestion = useCallback(() => {
    const sql = String(readCurrentEditorSql() || '').trim();
    const detail = {
      activity: 'activity.bi-designs',
      design_shortcut: 'bi_question_from_sql',
      kind: 'question',
      sql,
    };
    if (typeof window !== 'undefined') {
      window.__cdeadminPendingDesignShortcut = detail;
      window.dispatchEvent(new CustomEvent('cdeadmin:design-shortcut', {detail}));
      window.dispatchEvent(new CustomEvent('scratchrobin:open-app-surface', {
        detail: {appId: 'bi-designer', payload: detail},
      }));
      window.pgAdmin?.Browser?.CDEadminCommandContext?.()?.showActivity?.('activity.bi-designs');
    }
  }, [readCurrentEditorSql]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const onOpenSqlInEditor = (event) => {
      const incomingSql = String(event?.detail?.sql ?? '');
      setDraftSql(incomingSql);
      if (selected) {
        requestSQLSource(selected, {
          sql: incomingSql,
          dialect: event?.detail?.dialect || '',
          parameters: event?.detail?.parameters || {},
          title: event?.detail?.title || '',
        });
      }
      if (rootRef.current) {
        const activeBox = rootRef.current.querySelector('[data-active-connection="true"]');
        const field = activeBox?.querySelector('textarea, input[type="text"], input:not([type])');
        if (field) {
          const proto = field.tagName === 'TEXTAREA'
            ? window.HTMLTextAreaElement?.prototype
            : window.HTMLInputElement?.prototype;
          const desc = proto ? Object.getOwnPropertyDescriptor(proto, 'value') : null;
          if (desc?.set) desc.set.call(field, incomingSql);
          else field.value = incomingSql;
          field.dispatchEvent(new Event('input', {bubbles: true}));
          field.dispatchEvent(new Event('change', {bubbles: true}));
        }
      }
    };
    const onSqlEditorAction = (event) => {
      const targetInstanceId = event?.detail?.instanceId;
      if (instanceId && targetInstanceId && targetInstanceId !== instanceId) return;
      const action = event?.detail?.action;
      if (!action) return;
      if (action === 'save_bi_question') {
        handleSaveAsBiQuestion();
        return;
      }
      const activeBox = rootRef.current?.querySelector('[data-active-connection="true"]');
      if (!activeBox) return;
      const selectors = {
        execute: ['button[aria-label="Run"]:not(:disabled)', 'button[title="Run"]:not(:disabled)'],
        explain: ['button[aria-label*="Explain"]:not(:disabled)', 'button[title*="Explain"]:not(:disabled)'],
        cancel: ['button[aria-label="Cancel request"]:not(:disabled)', 'button[title="Cancel request"]:not(:disabled)'],
        commit: ['button[aria-label="commit"]:not(:disabled)', 'button[title="commit"]:not(:disabled)'],
        rollback: ['button[aria-label="rollback"]:not(:disabled)', 'button[title="rollback"]:not(:disabled)'],
        sql_builder: ['button:not(:disabled)'],
      }[action];
      if (!selectors) return;
      for (const selector of selectors) {
        if (action === 'sql_builder') {
          const btn = Array.from(activeBox.querySelectorAll(selector)).find((el) =>
            /build query/i.test(el.textContent || '')
          );
          if (btn) {
            btn.click();
            return;
          }
        } else {
          const btn = activeBox.querySelector(selector);
          if (btn) {
            btn.click();
            return;
          }
        }
      }
    };
    window.addEventListener('cdeadmin:open-sql-in-editor', onOpenSqlInEditor);
    window.addEventListener('scratchrobin:open-sql-from-bi', onOpenSqlInEditor);
    window.addEventListener('scratchrobin:sql-editor-action', onSqlEditorAction);
    return () => {
      window.removeEventListener('cdeadmin:open-sql-in-editor', onOpenSqlInEditor);
      window.removeEventListener('scratchrobin:open-sql-from-bi', onOpenSqlInEditor);
      window.removeEventListener('scratchrobin:sql-editor-action', onSqlEditorAction);
    };
  }, [handleSaveAsBiQuestion, instanceId]);

  return <QueryToolFrame ref={rootRef} sx={{color: 'text.primary', bgcolor: 'background.default'}}>
    {state.selected && <QueryToolToolbar>
      {!hosted && <SQLConnectionSelect />}
      <Button size="sm" variant="secondary" onClick={handleSaveAsBiQuestion}>Save as BI Question…</Button>
    </QueryToolToolbar>}
    {!state.selected && <DisconnectedQueryTool
      hasConnections={state.entries.length > 0}
      sqlText={draftSql}
      onSqlTextChange={handleDraftSqlChange}
      onSaveAsBiQuestion={handleSaveAsBiQuestion}
    />}
    {state.entries.filter(item => item.content).map(item => <Box key={item.id}
      data-active-connection={item.id === state.selected ? 'true' : 'false'}
      sx={{display: item.id === state.selected ? 'flex' : 'none',
        flexDirection: 'column', flex: 1, minHeight: 0}}><SlotContext.Provider value={item.id}>{item.content}</SlotContext.Provider></Box>)}
  </QueryToolFrame>;
}

SQLConnections.propTypes = {
  instanceId: PropTypes.string,
};
