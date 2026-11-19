import {useSyncExternalStore} from 'react';
import gettext from 'sources/gettext';
import currentUser from 'pgadmin.user_management.current_user';
import {Button} from '../primitives/Button';
import {useSQLConnections} from './SQLConnections';

const eventName = 'scratchrobin:quick-query-shortcuts';
const storageKey = () => {
  const identity = currentUser?.id ?? (currentUser?.username || currentUser?.email);
  return identity == null ? null : `scratchrobin.quick-query-shortcuts.${identity}`;
};

function snapshot() {
  try {
    const key = storageKey();
    return key ? localStorage.getItem(key) || '[]' : '[]';
  } catch {
    return '[]';
  }
}

function parse(value) {
  try {
    const shortcuts = JSON.parse(value);
    return Array.isArray(shortcuts) ? shortcuts.filter((item) => item?.query_id && item?.name) : [];
  } catch {
    return [];
  }
}

function subscribe(listener) {
  window.addEventListener(eventName, listener);
  window.addEventListener('storage', listener);
  return () => {
    window.removeEventListener(eventName, listener);
    window.removeEventListener('storage', listener);
  };
}

export function useQuickQueryShortcuts() {
  return parse(useSyncExternalStore(subscribe, snapshot));
}

export function setQuickQueryShortcut(query, pinned) {
  const key = storageKey();
  if (!key) return;
  const entries = parse(snapshot()).filter((item) => item.query_id !== query.query_id);
  if (pinned) {
    const {query_id, name, server_id, database_target_id} = query;
    entries.push({query_id, name, server_id, database_target_id});
  }
  localStorage.setItem(key, JSON.stringify(entries));
  window.dispatchEvent(new Event(eventName));
}

export default function QuickQueryShortcuts() {
  const shortcuts = useQuickQueryShortcuts();
  const {entries} = useSQLConnections();
  if (!shortcuts.length) return null;
  return (
    <section style={{padding: '0 24px 12px'}}>
      <h2>{gettext('Saved Queries')}</h2>
      <div style={{display: 'flex', gap: 8, flexWrap: 'wrap'}}>
        {shortcuts.map((query) => {
          const connection = entries.find((item) => item.openQuickQuery &&
            String(item.serverId) === String(query.server_id) &&
            (item.databaseTargetId || '') === (query.database_target_id || ''));
          return (
            <Button key={query.query_id} disabled={!connection}
              title={connection ? connection.label : gettext('Connect to this database to open the query.')}
              onClick={() => connection?.openQuickQuery(query.query_id)}>
              {query.name}
            </Button>
          );
        })}
      </div>
    </section>
  );
}
