import {useEffect, useMemo} from 'react';

const sharedSessionsByPost = new WeakMap();

function sessionPoolKey(databaseTargetId, purpose, languageProfile) {
  return `${databaseTargetId || ''}::${purpose || ''}::${languageProfile || 'firebird-sql'}`;
}

function getPoolMap(post) {
  if (typeof post !== 'function') return null;
  let map = sharedSessionsByPost.get(post);
  if (!map) {
    map = new Map();
    sharedSessionsByPost.set(post, map);
  }
  return map;
}

export function releaseSharedFirebirdDataSession(post, {
  databaseTargetId,
  purpose,
  languageProfile = 'firebird-sql',
} = {}) {
  const map = getPoolMap(post);
  if (!map) return Promise.resolve();
  const tasks = [];
  for (const [key, record] of map.entries()) {
    const matchesTarget = databaseTargetId === undefined || record.databaseTargetId === (databaseTargetId || '');
    const matchesPurpose = purpose === undefined || record.purpose === (purpose || '');
    const matchesProfile = !languageProfile || record.languageProfile === languageProfile;
    if (matchesTarget && matchesPurpose && matchesProfile) {
      record.reusable = false;
      record.owners.clear();
      map.delete(key);
      if (record.sessionId) {
        const sid = record.sessionId;
        record.sessionId = null;
        tasks.push(Promise.resolve().then(() => post({
          action: 'close_session',
          session_id: sid,
          database_target_id: record.databaseTargetId || undefined,
        })));
      }
    }
  }
  return Promise.all(tasks);
}

// Each context owns or borrows its original route, post function and eventual session ID.
// Old async work cannot adopt a new context after its component is retargeted, and
// shared/reusable sessions are never destroyed when a temporary sub-panel unmounts
// while another owner or reusable lease still holds the session.
export default function useFirebirdDataSession({
  post,
  databaseTargetId,
  purpose,
  languageProfile = 'firebird-sql',
  sharedSessionId = null,
  reusable = false,
  retainOnUnmount = false,
}) {
  const scope = useMemo(() => {
    const poolMap = getPoolMap(post);
    const poolKey = sessionPoolKey(databaseTargetId, purpose, languageProfile);
    let record = poolMap?.get(poolKey);
    if (!record) {
      record = {
        databaseTargetId: databaseTargetId || '',
        purpose: purpose || '',
        languageProfile,
        sessionId: sharedSessionId || null,
        borrowed: Boolean(sharedSessionId),
        reusable: Boolean(reusable || retainOnUnmount || sharedSessionId),
        opening: null,
        closing: null,
        owners: new Set(),
      };
      if (poolMap && (record.reusable || !sharedSessionId)) {
        poolMap.set(poolKey, record);
      }
    } else {
      if (sharedSessionId && !record.sessionId) {
        record.sessionId = sharedSessionId;
        record.borrowed = true;
      }
      if (reusable || retainOnUnmount || sharedSessionId) {
        record.reusable = true;
      }
    }

    const owner = {
      active: false,
      stopped: false,
      borrowed: Boolean(sharedSessionId || record.borrowed),
      reusable: Boolean(reusable || retainOnUnmount || record.reusable),
      get sessionId() {
        return sharedSessionId || record.sessionId;
      },
      set sessionId(val) {
        record.sessionId = val;
      },
      get opening() {
        return record.opening;
      },
      get closing() {
        return record.closing;
      },
      fileRevision: 0,
    };

    owner.release = ({force = false} = {}) => {
      record.owners.delete(owner);
      // Do not destroy a borrowed/shared session or one still owned/reusable on unmount.
      if (!force && (owner.borrowed || record.borrowed || record.owners.size > 0 || record.reusable)) {
        return Promise.resolve();
      }
      if (!record.sessionId) {
        poolMap?.delete(poolKey);
        return Promise.resolve();
      }
      if (record.closing) return record.closing;
      const sessionId = record.sessionId;
      record.closing = Promise.resolve().then(() => post({
        action: 'close_session',
        session_id: sessionId,
        database_target_id: databaseTargetId,
      })).then(result => {
        if (result?.provider_closed !== true || result.session_id !== sessionId) {
          throw new Error('Native session release was not confirmed.');
        }
        if (record.sessionId === sessionId) {
          record.sessionId = null;
          if (record.owners.size === 0 && !record.reusable) {
            poolMap?.delete(poolKey);
          }
        }
      }).finally(() => {
        record.closing = null;
      });
      return record.closing;
    };

    owner.releaseAfterWork = async (options = {}) => {
      // An early close can fail while a native row/transaction request is busy.
      // Wait for that response before one release attempt after work settles.
      if (record.closing) await record.closing.catch(() => {});
      return owner.release(options);
    };

    owner.ensure = async () => {
      if (!owner.active) throw new Error('Data workflow context changed.');
      if (sharedSessionId) return sharedSessionId;
      if (record.sessionId) return record.sessionId;
      if (!record.opening) {
        record.opening = Promise.resolve().then(() => post({
          action: 'open_session',
          language_profile: languageProfile,
          database_target_id: databaseTargetId,
          session_purpose: purpose,
        })).then(async result => {
          if (typeof result?.session_id !== 'string' || !result.session_id) {
            throw new Error('Native session identity was not received.');
          }
          record.sessionId = result.session_id;
          if (!owner.active && record.owners.size === 0 && !record.reusable) {
            await owner.release({force: true});
            throw new Error('Data workflow context changed.');
          }
          if (!owner.active) {
            throw new Error('Data workflow context changed.');
          }
          return record.sessionId;
        }).finally(() => {
          record.opening = null;
        });
      }
      return record.opening;
    };

    return owner;
  }, [post, databaseTargetId, purpose, languageProfile, sharedSessionId, reusable, retainOnUnmount]);

  useEffect(() => {
    const poolMap = getPoolMap(post);
    const poolKey = sessionPoolKey(databaseTargetId, purpose, languageProfile);
    const record = poolMap?.get(poolKey);
    record?.owners?.add(scope);
    scope.active = true;
    scope.stopped = false;
    return () => {
      scope.active = false;
      scope.stopped = true;
      scope.release().catch(() => {});
    };
  }, [scope, post, databaseTargetId, purpose, languageProfile]);

  return scope;
}
