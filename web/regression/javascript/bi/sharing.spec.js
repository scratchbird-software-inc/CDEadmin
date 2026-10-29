/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  LEVELS, accessOf, accessRows, canAdd, canTransfer, grantable, initialShare, ownerCandidates, permissions,
  rank, shareReducer, strongestFor,
} from 'sources/cdeadmin_ui/modules/bi/sharing';
import {
  SHARED_ROOT, findAnyCollection, isCollectionId, ownedItems, placementRows, sharedItems,
} from 'sources/cdeadmin_ui/modules/bi/collectionTree';
import {createBIClient} from 'sources/cdeadmin_ui/modules/bi/biClient';
import {initialViewer, viewerReducer} from 'sources/cdeadmin_ui/modules/bi/dashboardViewer';
import {dashboardFixtures} from './dashboardFixtures';
import {sharingFixtures as fx} from './sharingFixtures';

describe('permissions', () => {
  it('maps the effective access of real backend items to controls', () => {
    const [detail, east] = fx.viewerQuestions;
    expect(permissions(detail)).toMatchObject({access: 'view', isOwner: false, readOnly: true, canEdit: false,
      canMove: false, canDelete: false, canShare: false, canReadSql: false});
    expect(permissions({...detail, access: 'edit'})).toMatchObject({readOnly: false, canEdit: true, canMove: true,
      canReadSql: true, canDelete: false, canShare: false});
    expect(permissions({...east, access: 'manage'})).toMatchObject({canDelete: true, canShare: true});
  });

  it('treats an item without access (older backend) as the owner\'s', () => {
    expect(accessOf({name: 'x'})).toBe('manage');
    expect(permissions({name: 'x'})).toMatchObject({isOwner: true, canShare: true, readOnly: false});
    expect(permissions(undefined).canDelete).toBe(true);
  });

  it('orders levels', () => {
    expect(LEVELS.map(rank)).toEqual([1, 2, 3]);
    expect(rank('nope')).toBe(0);
  });
});

describe('share reducer against the real listing', () => {
  const listing = fx.grantListing;
  const loaded = shareReducer(initialShare(), {type: 'loaded', listing});

  it('loads, fails and recovers', () => {
    expect(loaded.status).toBe('ready');
    expect(shareReducer(initialShare(), {type: 'failed', error: 'x'})).toMatchObject({status: 'error', error: 'x'});
    const failed = shareReducer(loaded, {type: 'failed', error: 'x'});
    expect(failed).toMatchObject({status: 'ready', error: 'x'});
    expect(shareReducer(failed, {type: 'dismiss'}).error).toBe('');
  });

  it('offers only principals without a direct grant and not the owner', () => {
    const state = shareReducer(loaded, {type: 'searchDone', results: [
      ...fx.principalSearch, {type: 'user', id: listing.owner.user_id, name: 'owner'}]});
    const names = grantable(state).map((item) => item.name);
    expect(names).not.toContain('editor'); // already directly granted
    expect(names).not.toContain('owner');
    expect(names).toEqual(expect.arrayContaining(['viewer', 'analysts', 'manager']));
  });

  it('adds only with a pick, a valid level and nothing running', () => {
    expect(canAdd(loaded)).toBe(false);
    const picked = shareReducer(loaded, {type: 'pick', principal: fx.principalSearch[3]});
    expect(canAdd(picked)).toBe(true);
    expect(canAdd(shareReducer(picked, {type: 'level', level: 'owner'}))).toBe(false);
    expect(canAdd(shareReducer(picked, {type: 'busy', key: 'add'}))).toBe(false);
    expect(shareReducer(picked, {type: 'added'})).toMatchObject({pick: null, level: 'view'});
  });

  it('tracks search state', () => {
    const typing = shareReducer(loaded, {type: 'searchText', text: 'ed'});
    expect(typing.search).toMatchObject({text: 'ed', status: 'loading'});
    expect(shareReducer(typing, {type: 'searchFailed', error: 'no'}).search).toMatchObject({status: 'error', results: []});
    expect(shareReducer(loaded, {type: 'unknown'})).toBe(loaded);
  });

  it('transfers only to another user after the exact name is typed', () => {
    const state = shareReducer(loaded, {type: 'searchDone', results: fx.principalSearch});
    const candidates = ownerCandidates(state);
    expect(candidates.every((item) => item.type === 'user')).toBe(true);
    const chosen = shareReducer(state, {type: 'newOwner', principal: candidates[0]});
    expect(canTransfer(chosen, 'Detail by region')).toBe(false);
    const typed = shareReducer(chosen, {type: 'confirm', text: 'Detail by region'});
    expect(canTransfer(typed, 'Detail by region')).toBe(true);
    expect(canTransfer(shareReducer(typed, {type: 'confirm', text: 'detail by region'}), 'Detail by region')).toBe(false);
    expect(canTransfer(shareReducer(typed, {type: 'newOwner', principal: candidates[0]}), 'Detail by region')).toBe(false);
    expect(canTransfer(typed, '')).toBe(false);
    expect(ownerCandidates(initialShare())).toEqual([]);
  });

  it('lists direct then inherited rows and the strongest level per principal', () => {
    const rows = accessRows(listing);
    expect(rows.map((row) => [row.kind, row.name, row.level, row.source])).toEqual([
      ['direct', 'editor', 'edit', null],
      ['inherited', 'viewer', 'view', 'Team'],
      ['inherited', 'analysts', 'edit', 'Team']]);
    expect(accessRows(null)).toEqual([]);
    expect(strongestFor(listing, 'user', 3)).toBe('edit');
    expect(strongestFor(listing, 'role', 10)).toBe('edit');
    expect(strongestFor(listing, 'user', 999)).toBeNull();
  });
});

describe('shared-with-me tree', () => {
  it('keeps the shared collections out of the owned tree and finds them by id', () => {
    const shared = fx.sharedWithMe;
    expect(isCollectionId(SHARED_ROOT)).toBe(false);
    expect(isCollectionId(fx.ids.top)).toBe(true);
    expect(findAnyCollection([], shared.collections, fx.ids.sub).name).toBe('Reports');
    expect(sharedItems(fx.viewerQuestions)).toHaveLength(3);
    expect(ownedItems(fx.viewerQuestions)).toHaveLength(0);
  });

  it('offers a shared collection as a placement only with edit access, under the Shared with me group', () => {
    const shared = fx.sharedWithMe.collections;
    expect(placementRows([], shared, 'Shared with me')).toEqual([]);
    const editable = shared.map((collection) => ({...collection, access: 'edit', children: []}));
    expect(placementRows([], editable, 'Shared with me').map((row) => row.path)).toEqual([['Shared with me', 'Team']]);
  });
});

describe('what the backend leaves out', () => {
  it('redacts the SQL of a raw question for a viewer but not for an editor', () => {
    expect(fx.rawForViewer.sql_redacted).toBe(true);
    expect(fx.rawForViewer.definition.query.sql).toBe('');
    expect(JSON.stringify(fx.rawForViewer)).not.toContain('zzz_hidden_filter');
    expect(fx.rawForEditor.sql_redacted).toBeFalsy();
    expect(fx.rawForEditor.definition.query.sql).toContain('zzz_hidden_filter');
    expect(fx.rawRunForViewer).toMatchObject({sql: null, sql_redacted: true});
  });

  it('answers a missing and an unshared question alike', () => {
    expect(fx.errors.strangerGet).toBe(fx.errors.missingGet);
  });

  it('records the editor as the actor of a revision', () => {
    expect(fx.history[0]).toMatchObject({revision: 2, actor: 'editor'});
  });
});

describe('dashboard card without access', () => {
  it('marks a denied card as denied, with nothing known about it', () => {
    const board = dashboardFixtures.board;
    const card = board.cards.find((item) => item.type === 'question');
    let state = viewerReducer(initialViewer(board), {type: 'cardStart', id: card.id, token: 1, key: 'k'});
    state = viewerReducer(state, {type: 'cardDenied', id: card.id, token: 1});
    expect(state.cards[card.id]).toMatchObject({status: 'denied', error: '', stale: false});
    expect(state.cards[card.id].execution).toBeUndefined();
    // a late answer for an older run is ignored
    expect(viewerReducer(state, {type: 'cardDenied', id: card.id, token: 0})).toBe(state);
    expect(fx.dashboardRunForViewer.cards.c1).toEqual({no_access: true, type: 'question'});
    expect(JSON.stringify(fx.dashboardRunForViewer)).not.toContain('Payroll');
  });
});

describe('sharing client', () => {
  const calls = [];
  const client = createBIClient(async (payload) => {
    calls.push(payload);
    if(payload.action === 'bi_shared_with_me') return fx.sharedWithMe;
    if(payload.action === 'bi_principal_search') return {items: fx.principalSearch};
    if(payload.action === 'bi_audit_list') return {items: fx.audit};
    return {ok: true};
  });
  beforeEach(() => { calls.length = 0; });

  it('sends the sharing actions with the documented request keys', async () => {
    await client.effectiveAccess('question', 'q1');
    await client.listGrants('collection', 'c1');
    await client.addGrant('question', 'q1', 'role', 10, 'edit');
    await client.updateGrant('question', 'q1', 'g1', 'view');
    await client.removeGrant('dashboard', 'd1', 'g1');
    await client.setInherit('question', 'q1', false);
    await client.transferOwner('question', 'q1', 4, 'Name');
    expect(calls).toEqual([
      {action: 'bi_access_get', request: {resource_type: 'question', resource_id: 'q1'}},
      {action: 'bi_grant_list', request: {resource_type: 'collection', resource_id: 'c1'}},
      {action: 'bi_grant_add', request: {resource_type: 'question', resource_id: 'q1', principal_type: 'role',
        principal_id: 10, level: 'edit'}},
      {action: 'bi_grant_update', request: {resource_type: 'question', resource_id: 'q1', grant_id: 'g1', level: 'view'}},
      {action: 'bi_grant_remove', request: {resource_type: 'dashboard', resource_id: 'd1', grant_id: 'g1'}},
      {action: 'bi_access_inherit', request: {resource_type: 'question', resource_id: 'q1', inherit: false}},
      {action: 'bi_transfer_owner', request: {resource_type: 'question', resource_id: 'q1', new_owner_id: 4,
        confirm: 'Name'}}]);
  });

  it('unwraps lists', async () => {
    expect((await client.sharedWithMe()).questions).toHaveLength(3);
    expect(await client.searchPrincipals('ed', {kinds: ['user'], limit: 5})).toHaveLength(6);
    expect(calls[1].request).toEqual({text: 'ed', kinds: ['user'], limit: 5});
    expect(await client.auditTrail('question', 'q1')).toHaveLength(1);
  });
});
