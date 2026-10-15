import {act, renderHook, waitFor} from '@testing-library/react';
import useFirebirdDataSession from 'sources/Dialogs/firebirdDataSession';
import {firebirdTransactionIdle} from 'sources/Dialogs/firebirdTestDataHelpers';

const settings = {databaseTargetId: 'original', purpose: 'firebird-data-import'};
const closed = request => ({session_id: request.session_id, provider_closed: true});

describe('Firebird data session ownership', () => {
  it('releases a late open in its original scope without adopting the new target', async () => {
    let finish;
    const originalPost = jest.fn(request => request.action === 'open_session' ? new Promise(resolve => {finish = resolve;}) : Promise.resolve(closed(request)));
    const nextPost = jest.fn().mockResolvedValue({session_id: 'new-session'});
    const view = renderHook(props => useFirebirdDataSession(props), {initialProps: {...settings, post: originalPost}});
    const old = view.result.current;
    const outcome = old.ensure().catch(error => error);
    await waitFor(() => expect(finish).toBeDefined());
    view.rerender({...settings, post: nextPost, databaseTargetId: 'next'});
    await act(async () => {finish({session_id: 'old-session'}); await outcome;});
    expect(await outcome).toBeInstanceOf(Error);
    expect(originalPost).toHaveBeenCalledWith({action: 'close_session', session_id: 'old-session', database_target_id: 'original'});
    expect(view.result.current.sessionId).toBeNull();
    expect(nextPost).not.toHaveBeenCalled();
    await act(async () => {expect(await view.result.current.ensure()).toBe('new-session');});
    expect(nextPost).toHaveBeenCalledWith(expect.objectContaining({database_target_id: 'next', session_purpose: 'firebird-data-import'}));
  });
  it('coalesces opens and retries only owned release after an in-flight operation settles', async () => {
    let releaseClose;
    let closes = 0;
    const post = jest.fn(request => {
      if(request.action === 'open_session') return Promise.resolve({session_id: 'owned'});
      if(++closes === 1) return new Promise((_resolve, reject) => {releaseClose = reject;});
      return Promise.resolve(closed(request));
    });
    const view = renderHook(() => useFirebirdDataSession({...settings, post}));
    const owner = view.result.current;
    await act(async () => {expect(await Promise.all([owner.ensure(), owner.ensure()])).toEqual(['owned', 'owned']);});
    expect(post.mock.calls.filter(([request]) => request.action === 'open_session')).toHaveLength(1);
    view.unmount();
    await waitFor(() => expect(releaseClose).toBeDefined());
    const after = owner.releaseAfterWork();
    expect(closes).toBe(1);
    releaseClose(new Error('native request busy'));
    await after;
    expect(closes).toBe(2);
    expect(owner.sessionId).toBeNull();
    expect(post.mock.calls.every(([request]) => ['open_session', 'close_session'].includes(request.action))).toBe(true);
  });
  it.each([
    {}, {state: 'idle'}, {state: 'unknown', attachment_live: true},
    {state: 'active', in_transaction: true, attachment_live: true},
    {state: 'idle', in_transaction: false, attachment_live: false},
  ])('retains uncertainty for incomplete or active native observations: %j', provider_payload => {
    expect(firebirdTransactionIdle({provider_payload})).toBe(false);
  });
  it('accepts the native live attachment observation of an idle transaction', () => {
    expect(firebirdTransactionIdle({provider_payload: {state: 'idle', in_transaction: false, attachment_live: true}})).toBe(true);
  });
});
