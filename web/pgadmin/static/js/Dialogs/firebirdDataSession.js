import {useEffect, useMemo} from 'react';

// Each context owns its original route, post function and eventual session ID.
// Old async work cannot adopt a new context after its component is retargeted.
export default function useFirebirdDataSession({post, databaseTargetId, purpose, languageProfile='firebird-sql'}) {
  const scope = useMemo(() => {
    const owner = {active: false, stopped: false, sessionId: null, opening: null, closing: null, fileRevision: 0};
    owner.release = () => {
      if (!owner.sessionId) return Promise.resolve();
      if (owner.closing) return owner.closing;
      const sessionId = owner.sessionId;
      owner.closing = Promise.resolve().then(() => post({action: 'close_session',
        session_id: sessionId, database_target_id: databaseTargetId})).then(result => {
        if (result?.provider_closed !== true || result.session_id !== sessionId) throw new Error('Native session release was not confirmed.');
        if (owner.sessionId === sessionId) owner.sessionId = null;
      }).finally(() => {owner.closing = null;});
      return owner.closing;
    };
    owner.releaseAfterWork = async () => {
      // An early close can fail while a native row/transaction request is busy.
      // Wait for that response before one release attempt after work settles.
      if (owner.closing) await owner.closing.catch(() => {});
      return owner.release();
    };
    owner.ensure = async () => {
      if (!owner.active) throw new Error('Data workflow context changed.');
      if (owner.sessionId) return owner.sessionId;
      if (!owner.opening) owner.opening = Promise.resolve().then(() => post({action: 'open_session',
        language_profile: languageProfile, database_target_id: databaseTargetId, session_purpose: purpose})).then(async result => {
        if (typeof result?.session_id !== 'string' || !result.session_id) throw new Error('Native session identity was not received.');
        owner.sessionId = result.session_id;
        if (!owner.active) {
          await owner.release();
          throw new Error('Data workflow context changed.');
        }
        return owner.sessionId;
      }).finally(() => {owner.opening = null;});
      return owner.opening;
    };
    return owner;
  }, [post, databaseTargetId, purpose, languageProfile]);
  useEffect(() => {
    scope.active = true; scope.stopped = false;
    return () => {
      scope.active = false; scope.stopped = true;
      scope.release().catch(() => {});
    };
  }, [scope]);
  return scope;
}
