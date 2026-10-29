/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Pure model of BI sharing (docs/en_US/bi_permissions.rst): what an effective
 * access level allows, and the reducer behind the Share dialog. The server is
 * the authority for every decision here; these functions only decide what the
 * UI offers, so a hidden or disabled control is a convenience, never a gate.
 */

export const LEVELS = ['view', 'edit', 'manage'];
const RANK = {view: 1, edit: 2, manage: 3};

export const rank = (level) => RANK[level] || 0;

/** Items from a backend that predates sharing carry no `access`: they were the owner's. */
export const accessOf = (item) => item?.access || 'manage';

/** What the UI offers for one question, dashboard or collection. */
export function permissions(item) {
  const level = accessOf(item);
  const value = rank(level);
  return {
    access: level,
    isOwner: item?.is_owner !== false,
    canEdit: value >= RANK.edit,
    canMove: value >= RANK.edit,
    canArchive: value >= RANK.edit,
    canDuplicate: value >= RANK.edit,
    canDelete: value >= RANK.manage,
    canShare: value >= RANK.manage,
    canReadSql: value >= RANK.edit,
    readOnly: value < RANK.edit,
  };
}

export const LEVEL_OPTIONS = [
  {value: 'view', label: 'Can view'},
  {value: 'edit', label: 'Can edit'},
  {value: 'manage', label: 'Can manage'},
];

// ---------------------------------------------------------------------------
// Share dialog
// ---------------------------------------------------------------------------

export function initialShare() {
  return {
    status: 'loading', error: '', listing: null, busy: '',
    search: {text: '', status: 'loading', results: [], error: ''},
    pick: null, level: 'view', confirm: '', newOwner: null,
  };
}

export function shareReducer(state, action) {
  switch(action.type) {
  case 'loaded':
    return {...state, status: 'ready', error: '', busy: '', listing: action.listing};
  case 'failed':
    return {...state, status: state.listing ? 'ready' : 'error', busy: '', error: action.error};
  case 'busy':
    return {...state, busy: action.key, error: ''};
  case 'dismiss':
    return {...state, error: ''};
  case 'searchText':
    return {...state, search: {...state.search, text: action.text, status: 'loading', error: ''}};
  case 'searchDone':
    return {...state, search: {...state.search, status: 'ready', results: action.results}};
  case 'searchFailed':
    return {...state, search: {...state.search, status: 'error', results: [], error: action.error}};
  case 'pick':
    return {...state, pick: action.principal};
  case 'level':
    return {...state, level: action.level};
  case 'added':
    return {...state, pick: null, level: 'view', search: {text: '', status: 'loading', results: [], error: ''}};
  case 'confirm':
    return {...state, confirm: action.text};
  case 'newOwner':
    return {...state, newOwner: action.principal, confirm: ''};
  default:
    return state;
  }
}

const sameKey = (a, b) => a.type === b.principal_type && a.id === b.principal_id;

/** Search hits that can still be granted: not the owner, nobody who already has a direct grant. */
export function grantable(state) {
  const listing = state.listing;
  if(!listing) return [];
  return state.search.results.filter((item) => {
    if(item.type === 'user' && item.id === listing.owner.user_id) return false;
    return !listing.direct.some((grant) => sameKey(item, grant));
  });
}

export const canAdd = (state) => Boolean(state.pick) && LEVELS.includes(state.level) && state.busy === '';

/** Users that ownership can move to (a role cannot own anything). */
export const ownerCandidates = (state) => state.listing ? state.search.results.filter(
  (item) => item.type === 'user' && item.id !== state.listing.owner.user_id) : [];

/** Ownership moves only after the resource's exact name is typed. */
export const canTransfer = (state, resourceName) => Boolean(state.newOwner) && state.busy === '' &&
  typeof resourceName === 'string' && resourceName !== '' && state.confirm === resourceName;

/**
 * Direct grants first, then what flows in from containing collections (read
 * only here: it is changed on the collection or by breaking inheritance).
 */
export function accessRows(listing) {
  if(!listing) return [];
  const direct = listing.direct.map((grant) => ({
    key: grant.grant_id, kind: 'direct', grantId: grant.grant_id, principalType: grant.principal_type,
    name: grant.principal_name || '', level: grant.level, source: null,
  }));
  const inherited = listing.inherited.map((grant, index) => ({
    key: `inherited-${index}-${grant.grant_id}`, kind: 'inherited', grantId: grant.grant_id,
    principalType: grant.principal_type, name: grant.principal_name || '', level: grant.level,
    source: grant.collection_name, // null when the caller cannot see that collection
  }));
  return [...direct, ...inherited];
}

/** The strongest level a principal ends up with, counting both lists. */
export function strongestFor(listing, principalType, principalId) {
  const levels = [...listing.direct, ...listing.inherited]
    .filter((grant) => grant.principal_type === principalType && grant.principal_id === principalId)
    .map((grant) => rank(grant.level));
  const best = Math.max(0, ...levels);
  return LEVELS[best - 1] || null;
}
