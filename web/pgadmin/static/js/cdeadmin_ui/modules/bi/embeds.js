/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Pure model of signed BI embedding (docs/en_US/bi_embedding.rst): the draft
 * behind the Embed dialog, its conversion to the backend definition, early
 * validation, the reducer of the embed list (including the signing secret,
 * which is held only until the dialog closes), the status text, the preview
 * request and the code snippets. The server validates everything again; nothing
 * here is a gate, it only decides what the form offers and says early.
 *
 * The secret is never written to storage and never put into a snippet: the
 * snippets read it from the environment of the embedding site's server.
 */

import gettext from 'sources/gettext';
import {rank} from './sharing';

export const MODES = ['off', 'locked', 'editable', 'hidden'];
export const THEMES = ['auto', 'light', 'dark'];
export const RESERVED_CLAIMS = ['user_id', 'principal', 'embed_id', 'embedding', 'roles_override'];
export const MIN_LIFETIME = 30;
export const DEFAULT_LIFETIME = 600;
export const MAX_ORIGINS = 20;
export const MAX_CLAIMS = 16;

const NAME = /^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$/;
const HOST = '(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\.)+[a-z]{2,63}';
const ORIGIN = new RegExp(`^https://${HOST}(?::[0-9]{1,5})?$`);
const LOCAL = /^http:\/\/(?:localhost|127\.0\.0\.1)(?::[0-9]{1,5})?$/;
const MAX_NAME = 256;

// ---------------------------------------------------------------------------
// permissions
// ---------------------------------------------------------------------------

/**
 * What the dialog offers. Any manager sees the embeds of the resource and may
 * disable or revoke; only the embed's owner sees keys and may create, enable,
 * rotate, mint and preview. The server decides every action again.
 */
export function embedPermissions(access, {available = true} = {}) {
  const manage = rank(access) >= rank('manage');
  return {canOpen: manage && available, canCreate: manage && available};
}

export const ownerActions = (embed) => ({
  edit: embed.is_owner && embed.status !== 'revoked',
  enable: embed.is_owner && embed.status === 'disabled',
  disable: embed.status === 'enabled',
  rotate: embed.is_owner && embed.status !== 'revoked',
  retire: embed.is_owner && (embed.keys || []).some((key) => key.slot === 'previous'),
  preview: embed.is_owner && embed.status === 'enabled',
  revoke: embed.status !== 'revoked',
  remove: embed.is_owner && embed.status !== 'enabled',
  stats: true,
});

// ---------------------------------------------------------------------------
// status
// ---------------------------------------------------------------------------

const REASONS = {
  not_enabled: () => gettext('The embed is created but not enabled yet.'),
  manual: () => gettext('Disabled by a manager.'),
  owner_access_lost: () => gettext('The owner no longer manages this content, so the embed was disabled.'),
  delegation_expired: () => gettext('The owner\'s authorization expired. Enable the embed again.'),
  endpoint_changed: () => gettext('The connection changed. Enable the embed again.'),
  revoked: () => gettext('Revoked. No token works any more.'),
};

/** Badge tone, label and detail text for an embed. */
export function statusLine(embed) {
  if(embed.status === 'enabled') return {tone: 'success', label: gettext('Enabled'), detail: ''};
  if(embed.status === 'revoked') return {tone: 'error', label: gettext('Revoked'), detail: REASONS.revoked()};
  return {
    tone: 'warning', label: gettext('Disabled'),
    detail: REASONS[embed.disabled_reason]?.() || '',
  };
}

// ---------------------------------------------------------------------------
// draft
// ---------------------------------------------------------------------------

/** The parameters an embed may declare, from a question or dashboard filters. */
export function resourceParameters(items = []) {
  return items.filter((item) => item && item.id).map((item) => ({
    id: item.id, name: item.name || item.label || item.id, type: item.type || 'string',
    required: Boolean(item.required) && item.default === undefined,
    multiple: Boolean(item.multiple),
  }));
}

export function newDraft({resourceType = 'dashboard', resourceId = '', resourceName = '',
  parameters = [], lifetime = DEFAULT_LIFETIME} = {}) {
  return {
    embedId: null, revision: null, name: resourceName,
    resource: {type: resourceType, id: resourceId, revision: null},
    parameters: resourceParameters(parameters).map((item) => ({...item, mode: 'off'})),
    claims: [], origins: [], originText: '', lifetime, requireJti: false, expiresAt: '',
    pageSize: 50, maxRows: 1000,
    display: {title: true, theme: 'auto', border: true, download: false},
  };
}

/** A draft that edits a stored embed (the shape bi_embed_get returns). */
export function draftFromEmbed(embed, parameters = []) {
  const stored = embed.definition || {};
  const modes = Object.fromEntries((stored.parameters || []).map((item) => [item.id, item.mode]));
  const known = resourceParameters(parameters);
  const extra = (stored.parameters || []).filter((item) => !known.some((entry) => entry.id === item.id))
    .map((item) => ({id: item.id, name: item.id, type: 'string', required: false, multiple: false}));
  return {
    embedId: embed.embed_id, revision: embed.revision, name: stored.name || embed.name,
    resource: {...(stored.resource || embed.resource)},
    parameters: [...known, ...extra].map((item) => ({...item, mode: modes[item.id] || 'off'})),
    claims: (stored.claims || []).map((item) => ({name: item.name, required: Boolean(item.required)})),
    origins: [...(stored.origins || [])], originText: '',
    lifetime: stored.max_token_lifetime_seconds ?? DEFAULT_LIFETIME,
    requireJti: Boolean(stored.require_jti), expiresAt: stored.expires_at || '',
    pageSize: stored.page_size ?? 50, maxRows: stored.max_rows ?? 1000,
    display: {title: true, theme: 'auto', border: true, download: false, ...(stored.display || {})},
  };
}

/** The definition the backend validates (the `embed` of bi_embed_create / update). */
export function toDefinition(draft) {
  return {
    name: draft.name.trim(),
    resource: {type: draft.resource.type, id: draft.resource.id, revision: draft.resource.revision ?? null},
    parameters: draft.parameters.filter((item) => item.mode !== 'off').map((item) => ({id: item.id, mode: item.mode})),
    claims: draft.claims.map((item) => ({name: item.name.trim(), required: Boolean(item.required)})),
    origins: [...draft.origins],
    max_token_lifetime_seconds: Number(draft.lifetime),
    require_jti: Boolean(draft.requireJti),
    expires_at: draft.expiresAt ? draft.expiresAt : null,
    page_size: Number(draft.pageSize),
    max_rows: Number(draft.maxRows),
    display: {...draft.display},
  };
}

/** Why an origin is refused (the server enforces the same rule), or ''. */
export function originProblem(origin) {
  const text = String(origin || '').trim();
  if(!text) return gettext('Enter an origin such as https://app.example.com');
  if(ORIGIN.test(text) || LOCAL.test(text)) {
    const port = /:(\d+)$/.exec(text);
    return port && Number(port[1]) > 65535 ? gettext('The port is out of range.') : '';
  }
  return gettext('Use an exact origin: https://host[:port], with no wildcard, path or credentials. ' +
    'Plain http is allowed only for localhost.');
}

/** Early validation. `catalog` carries the server limits (bi_embed_catalog). */
export function validateDraft(draft, catalog = {}) {
  const errors = {};
  if(!draft.name.trim()) errors.name = gettext('Enter a name.');
  else if(draft.name.trim().length > MAX_NAME) errors.name = gettext('The name is too long.');
  const maxLifetime = catalog.max_token_lifetime_seconds || 3600;
  const lifetime = Number(draft.lifetime);
  if(!Number.isInteger(lifetime) || lifetime < MIN_LIFETIME || lifetime > maxLifetime) {
    errors.lifetime = gettext('Use a whole number of seconds from %s to %s.', MIN_LIFETIME, maxLifetime);
  }
  const maxPage = catalog.max_page_size || 200;
  const pageSize = Number(draft.pageSize);
  if(!Number.isInteger(pageSize) || pageSize < 1 || pageSize > maxPage) {
    errors.pageSize = gettext('Use a whole number from 1 to %s.', maxPage);
  }
  const maxRows = catalog.max_rows || 5000;
  const rows = Number(draft.maxRows);
  if(!Number.isInteger(rows) || rows < 1 || rows > maxRows) {
    errors.maxRows = gettext('Use a whole number from 1 to %s.', maxRows);
  }
  draft.origins.forEach((origin, index) => {
    const problem = originProblem(origin);
    if(problem) errors[`origin.${index}`] = problem;
  });
  if(draft.origins.length > MAX_ORIGINS) errors.origins = gettext('At most %s origins.', MAX_ORIGINS);
  const reserved = new Set([...(catalog.reserved_claims || RESERVED_CLAIMS)]);
  const seen = new Set();
  draft.claims.forEach((claim, index) => {
    const name = claim.name.trim();
    if(!NAME.test(name)) errors[`claim.${index}`] = gettext('Use letters, digits, dots, dashes or underscores.');
    else if(reserved.has(name)) errors[`claim.${index}`] = gettext('"%s" is reserved for the server.', name);
    else if(seen.has(name)) errors[`claim.${index}`] = gettext('Each claim can be declared once.');
    seen.add(name);
  });
  if(draft.claims.length > MAX_CLAIMS) errors.claims = gettext('At most %s claims.', MAX_CLAIMS);
  draft.parameters.forEach((item) => {
    if(item.required && item.mode === 'off') {
      errors[`parameter.${item.id}`] = gettext('A required parameter must be locked, editable or hidden so a value can reach it.');
    }
  });
  if(draft.display.download && catalog.downloads_allowed === false) {
    errors.download = gettext('Downloads from embeds are disabled on this server.');
  }
  return errors;
}

/** Things that are allowed but probably not intended. */
export function warnings(draft, {rawSql = false} = {}) {
  const found = [];
  if(!draft.origins.length) found.push(gettext('No origin is allowed, so no site can show this embed in a frame.'));
  if(draft.parameters.some((item) => item.mode === 'editable')) {
    found.push(gettext('Viewers can change editable parameters to any allowed value.'));
  }
  if(rawSql && draft.claims.length) found.push(gettext('Raw SQL cannot use claims, so the server will refuse this.'));
  if(Number(draft.lifetime) > 900) found.push(gettext('Tokens that live longer than 15 minutes stay useful if they leak.'));
  return found;
}

export function draftReducer(draft, action) {
  switch(action.type) {
  case 'field':
    return {...draft, [action.field]: action.value};
  case 'display':
    return {...draft, display: {...draft.display, ...action.patch}};
  case 'mode':
    return {...draft, parameters: draft.parameters.map((item) => item.id === action.id ?
      {...item, mode: action.mode} : item)};
  case 'originText':
    return {...draft, originText: action.value};
  case 'addOrigin': {
    const origin = draft.originText.trim().replace(/\/+$/, '');
    if(!origin || draft.origins.includes(origin)) return {...draft, originText: ''};
    return {...draft, origins: [...draft.origins, origin], originText: ''};
  }
  case 'removeOrigin':
    return {...draft, origins: draft.origins.filter((_, index) => index !== action.index)};
  case 'addClaim':
    return {...draft, claims: [...draft.claims, {name: '', required: false}]};
  case 'claim':
    return {...draft, claims: draft.claims.map((item, index) => index === action.index ?
      {...item, ...action.patch} : item)};
  case 'removeClaim':
    return {...draft, claims: draft.claims.filter((_, index) => index !== action.index)};
  case 'reset':
    return action.draft;
  default:
    return draft;
  }
}

// ---------------------------------------------------------------------------
// list / secret
// ---------------------------------------------------------------------------

export const initialPanel = () => ({
  status: 'idle', items: [], error: '', notice: '', busy: '', editing: null, secret: null,
  stats: {status: 'idle', id: '', data: null, error: ''},
});

/**
 * The reducer behind the dialog. `secret` is `{embedId, kid, secret}` after a
 * create or rotate and is the only place the signing secret lives; it stays
 * until `secretHidden` (the user says they copied it) or the dialog closes.
 * `editing` is the id of the embed being edited, `'new'`, or null.
 */
export function panelReducer(state, action) {
  switch(action.type) {
  case 'loading':
    return {...state, status: 'loading', error: ''};
  case 'loaded':
    return {...state, status: 'ready', busy: '', error: '', items: action.items};
  case 'failed':
    return {...state, status: state.items.length ? 'ready' : 'error', busy: '', error: action.error};
  case 'busy':
    return {...state, busy: action.key, error: '', notice: ''};
  case 'notice':
    return {...state, busy: '', notice: action.text};
  case 'dismiss':
    return {...state, error: '', notice: ''};
  case 'secretShown':
    return {...state, busy: '', secret: {embedId: action.embedId, kid: action.kid, secret: action.secret}};
  case 'secretHidden':
    return {...state, secret: null};
  case 'edit':
    return {...state, editing: action.id};
  case 'closeEditor':
    return {...state, editing: null};
  case 'statsLoading':
    return {...state, stats: {status: 'loading', id: action.id, data: null, error: ''}};
  case 'statsLoaded':
    return state.stats.id !== action.id ? state : {...state, stats: {status: 'ready', id: action.id, data: action.data, error: ''}};
  case 'statsFailed':
    return state.stats.id !== action.id ? state : {...state, stats: {status: 'error', id: action.id, data: null, error: action.error}};
  case 'statsClosed':
    return {...state, stats: {status: 'idle', id: '', data: null, error: ''}};
  default:
    return state;
  }
}

/** Daily counts for the view: totals and one row per day, newest first. */
export function statsSummary(stats) {
  if(!stats) return {totals: {views: 0, cardRuns: 0, errors: 0}, rows: []};
  const totals = stats.totals || {};
  return {
    totals: {views: totals.views || 0, cardRuns: totals.card_runs || 0, errors: totals.errors || 0},
    rows: [...(stats.series || [])].sort((a, b) => (a.day < b.day ? 1 : -1)).map((item) => ({
      day: item.day, views: item.views, cardRuns: item.card_runs, errors: item.errors,
    })),
  };
}

// ---------------------------------------------------------------------------
// preview
// ---------------------------------------------------------------------------

/** A typed value from text for a parameter of `type`; `undefined` when blank, `null` when invalid. */
export function coerceValue(type, text, multiple = false) {
  const raw = String(text ?? '').trim();
  if(raw === '') return undefined;
  const one = (piece) => {
    const value = piece.trim();
    switch(type) {
    case 'integer': return /^-?\d+$/.test(value) ? Number.parseInt(value, 10) : null;
    case 'number': return value !== '' && Number.isFinite(Number(value)) ? Number(value) : null;
    case 'boolean': return value === 'true' ? true : value === 'false' ? false : null;
    default: return value;
    }
  };
  if(!multiple) return one(raw);
  const pieces = raw.split(',').map(one);
  return pieces.some((item) => item === null) ? null : pieces;
}

/**
 * The `params` and `claims` of a preview request from what the user typed.
 * Blank values are left out; an invalid one is reported by name.
 */
export function previewRequest(draft, texts = {}, claimTexts = {}) {
  const params = {};
  const problems = {};
  draft.parameters.filter((item) => item.mode !== 'off').forEach((item) => {
    const value = coerceValue(item.type, texts[item.id], item.multiple);
    if(value === null) problems[item.id] = gettext('Not a valid %s value.', item.type);
    else if(value === undefined) {
      if(item.mode !== 'editable' && item.required) problems[item.id] = gettext('The token needs a value for this parameter.');
    } else params[item.id] = value;
  });
  const claims = {};
  draft.claims.forEach((claim) => {
    const text = String(claimTexts[claim.name] ?? '').trim();
    if(!text) {
      if(claim.required) problems[`claim.${claim.name}`] = gettext('This claim is required.');
      return;
    }
    claims[claim.name] = /^-?\d+$/.test(text) ? Number.parseInt(text, 10) : text;
  });
  return {params, claims, problems};
}

/** The address a frame loads: the token travels in the query of the first request only. */
export const frameAddress = (framePath, token) => `${framePath}?token=${encodeURIComponent(token)}`;

// ---------------------------------------------------------------------------
// snippets
// ---------------------------------------------------------------------------

const jsonText = (value) => JSON.stringify(value, null, 4);

/**
 * Text-only examples for the embedding site. They read the secret from the
 * environment and never contain it. `host` is this server's origin.
 */
export function snippets({embed, draft, host = 'https://your-server'}) {
  const embedId = embed.embed_id;
  const kid = (embed.keys || []).find((key) => key.slot === 'current')?.kid || '<kid>';
  const params = {};
  (draft?.parameters || []).filter((item) => item.mode !== 'off').forEach((item) => {
    params[item.id] = `<${item.id}>`;
  });
  const claims = {};
  (draft?.claims || []).forEach((claim) => { claims[claim.name] = `<${claim.name}>`; });
  const payload = {aud: embedId, iat: '<now>', exp: '<now + 300>'};
  if(Object.keys(params).length) payload.params = params;
  if(Object.keys(claims).length) payload.claims = claims;
  const frame = `${host}${embed.frame_path || `/cdeadmin/embed/${embedId}/frame`}`;
  const lifetime = Math.min(300, embed.definition?.max_token_lifetime_seconds || 300);
  const pythonParams = Object.keys(params).length ? `        "params": ${JSON.stringify(params)},\n` : '';
  const pythonClaims = Object.keys(claims).length ? `        "claims": ${JSON.stringify(claims)},\n` : '';
  const nodeParams = Object.keys(params).length ? `    params: ${JSON.stringify(params)},\n` : '';
  const nodeClaims = Object.keys(claims).length ? `    claims: ${JSON.stringify(claims)},\n` : '';
  return {
    python: [
      '# On YOUR server. Install PyJWT. Never send the secret to a browser.',
      'import os, time, jwt',
      '',
      'def embed_url():',
      '    now = int(time.time())',
      '    token = jwt.encode({',
      `        "aud": "${embedId}",`,
      '        "iat": now,',
      `        "exp": now + ${lifetime},`,
      `${pythonParams}${pythonClaims}    }, os.environ["CDE_EMBED_SECRET"], algorithm="HS256",`,
      `       headers={"kid": "${kid}"})`,
      `    return "${frame}?token=" + token`,
    ].join('\n').replace(/\n\n\n/g, '\n\n'),
    node: [
      '// On YOUR server. npm install jsonwebtoken. Never send the secret to a browser.',
      'const jwt = require("jsonwebtoken");',
      '',
      'function embedUrl() {',
      '  const now = Math.floor(Date.now() / 1000);',
      '  const token = jwt.sign({',
      `    aud: "${embedId}",`,
      '    iat: now,',
      `    exp: now + ${lifetime},`,
      `${nodeParams}${nodeClaims}  }, process.env.CDE_EMBED_SECRET, {`,
      `    algorithm: "HS256", noTimestamp: true, header: {kid: "${kid}"}});`,
      `  return "${frame}?token=" + token;`,
      '}',
    ].join('\n'),
    pseudo: [
      'token  = HS256_sign(',
      `  header  = ${jsonText({alg: 'HS256', typ: 'JWT', kid}).replace(/\n/g, '\n  ')},`,
      `  payload = ${jsonText(payload).replace(/\n/g, '\n  ')},`,
      '  secret  = <the secret shown once when the embed was created>)',
      `iframe src = ${frame}?token=<token>`,
    ].join('\n'),
  };
}
