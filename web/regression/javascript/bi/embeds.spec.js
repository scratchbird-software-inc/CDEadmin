/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  coerceValue, draftFromEmbed, draftReducer, embedPermissions, frameAddress, initialPanel, newDraft, originProblem,
  ownerActions, panelReducer, previewRequest, resourceParameters, snippets, statsSummary, statusLine,
  toDefinition, validateDraft, warnings,
} from 'sources/cdeadmin_ui/modules/bi/embeds';
import {embedFixtures as fx} from './embedFixtures';

const filters = fx.dashboardFilters;
const fresh = (extra = {}) => newDraft({
  resourceType: 'dashboard', resourceId: fx.dashboardId, resourceName: 'Sales embed', parameters: filters, ...extra});
const apply = (draft, ...actions) => actions.reduce(draftReducer, draft);

describe('embed permissions and row actions', () => {
  it('opens for managers only, and only when the server has the feature', () => {
    expect(embedPermissions('manage')).toEqual({canOpen: true, canCreate: true});
    expect(embedPermissions('edit').canOpen).toBe(false);
    expect(embedPermissions('view').canCreate).toBe(false);
    expect(embedPermissions('manage', {available: false}).canOpen).toBe(false);
  });

  it('gives the owner every action and another manager only disable and revoke', () => {
    const [mine] = fx.list.items.filter((item) => item.name === 'Partner portal');
    expect(ownerActions(mine)).toMatchObject({
      edit: true, enable: false, disable: true, rotate: true, preview: true, revoke: true, remove: false});
    expect(ownerActions(mine).retire).toBe(false); // the old key was retired in the scenario
    const theirs = fx.listForManager.items.find((item) => item.name === 'Partner portal');
    expect(theirs.is_owner).toBe(false);
    expect(ownerActions(theirs)).toMatchObject({
      edit: false, enable: false, rotate: false, preview: false, retire: false, remove: false,
      disable: true, revoke: true, stats: true});
  });

  it('offers enable for a created embed, retire while two keys verify, nothing for a revoked one', () => {
    expect(ownerActions(fx.draft.embed)).toMatchObject({enable: true, disable: false, remove: true, preview: false});
    expect(ownerActions(fx.rotated.embed).retire).toBe(true);
    expect(ownerActions(fx.revoked)).toMatchObject({
      edit: false, rotate: false, revoke: false, enable: false, disable: false, remove: true});
  });
});

describe('status line', () => {
  it('names the state and the reason', () => {
    expect(statusLine(fx.enabled)).toEqual({tone: 'success', label: 'Enabled', detail: ''});
    expect(statusLine(fx.draft.embed)).toMatchObject({tone: 'warning', label: 'Disabled',
      detail: 'The embed is created but not enabled yet.'});
    expect(statusLine(fx.ownerLost)).toMatchObject({tone: 'warning',
      detail: 'The owner no longer manages this content, so the embed was disabled.'});
    expect(statusLine(fx.disabledByManager).detail).toBe('Disabled by a manager.');
    expect(statusLine(fx.revoked)).toMatchObject({tone: 'error', label: 'Revoked'});
  });

  it('tolerates a reason it does not know', () => {
    expect(statusLine({status: 'disabled', disabled_reason: 'future_reason'}).detail).toBe('');
  });
});

describe('draft', () => {
  it('starts with every parameter unused and nothing allowed', () => {
    const draft = fresh();
    expect(draft.parameters).toEqual([
      {id: 'region', name: 'Region', type: 'string', required: false, multiple: false, mode: 'off'}]);
    expect(draft.origins).toEqual([]);
    expect(draft.display).toEqual({title: true, theme: 'auto', border: true, download: false});
    expect(toDefinition(draft).parameters).toEqual([]);
  });

  it('turns required parameters without a default into required rows', () => {
    expect(resourceParameters([{id: 'a', required: true}, {id: 'b', required: true, default: 1},
      {id: 'c'}, null, {name: 'no id'}]).map((item) => [item.id, item.required])).toEqual([
      ['a', true], ['b', false], ['c', false]]);
  });

  it('round-trips a stored embed through the draft', () => {
    const stored = fx.created.embed;
    const draft = draftFromEmbed(stored, filters);
    expect(draft.embedId).toBe('e-partner');
    expect(draft.parameters[0]).toMatchObject({id: 'region', mode: 'editable'});
    expect(draft.claims).toEqual([{name: 'tenant_id', required: true}]);
    expect(draft.lifetime).toBe(900);
    const back = toDefinition(draft);
    // everything the server returned is what would be sent back, so a save without edits is a no-op
    expect(back).toEqual({
      ...stored.definition,
      expires_at: null,
    });
  });

  it('keeps parameters the resource no longer has so they can be removed', () => {
    const stored = {...fx.created.embed, definition: {...fx.created.embed.definition,
      parameters: [{id: 'region', mode: 'locked'}, {id: 'gone', mode: 'hidden'}]}};
    const draft = draftFromEmbed(stored, filters);
    expect(draft.parameters.map((item) => [item.id, item.mode])).toEqual([['region', 'locked'], ['gone', 'hidden']]);
    expect(validateDraft(draft, fx.catalog)).toEqual({});
  });

  it('builds the definition the backend validates', () => {
    const draft = apply(fresh(),
      {type: 'field', field: 'name', value: '  Portal  '},
      {type: 'mode', id: 'region', mode: 'locked'},
      {type: 'addClaim'}, {type: 'claim', index: 0, patch: {name: ' tenant_id ', required: true}},
      {type: 'originText', value: 'https://app.example.com/'}, {type: 'addOrigin'},
      {type: 'field', field: 'lifetime', value: '300'},
      {type: 'field', field: 'requireJti', value: true},
      {type: 'display', patch: {theme: 'dark', border: false}});
    expect(toDefinition(draft)).toEqual({
      name: 'Portal',
      resource: {type: 'dashboard', id: 'd-sales', revision: null},
      parameters: [{id: 'region', mode: 'locked'}],
      claims: [{name: 'tenant_id', required: true}],
      origins: ['https://app.example.com'],
      max_token_lifetime_seconds: 300, require_jti: true, expires_at: null, page_size: 50, max_rows: 1000,
      display: {title: true, theme: 'dark', border: false, download: false},
    });
  });
});

describe('draft reducer', () => {
  it('adds each origin once and clears the field', () => {
    let draft = apply(fresh(), {type: 'originText', value: 'https://a.example.com'}, {type: 'addOrigin'},
      {type: 'originText', value: 'https://a.example.com'}, {type: 'addOrigin'},
      {type: 'originText', value: '   '}, {type: 'addOrigin'});
    expect(draft.origins).toEqual(['https://a.example.com']);
    expect(draft.originText).toBe('');
    draft = apply(draft, {type: 'removeOrigin', index: 0});
    expect(draft.origins).toEqual([]);
  });

  it('edits and removes claims by position', () => {
    const draft = apply(fresh(), {type: 'addClaim'}, {type: 'addClaim'},
      {type: 'claim', index: 1, patch: {name: 'org'}}, {type: 'removeClaim', index: 0});
    expect(draft.claims).toEqual([{name: 'org', required: false}]);
  });

  it('ignores unknown actions', () => {
    const draft = fresh();
    expect(draftReducer(draft, {type: 'nope'})).toBe(draft);
  });
});

describe('origins', () => {
  it.each([
    'https://app.example.com', 'https://portal.example.org:8443', 'http://localhost:3000', 'http://127.0.0.1',
  ])('accepts %s', (origin) => expect(originProblem(origin)).toBe(''));

  it.each([
    '', '*', 'https://*.example.com', 'http://example.com', 'https://example.com/path', 'https://user@example.com',
    'example.com', 'null', 'https://localhost', 'https://a.example.com; script-src *', 'javascript:alert(1)',
  ])('refuses "%s"', (origin) => expect(originProblem(origin)).not.toBe(''));

  it('refuses a port that cannot exist', () => {
    expect(originProblem('https://app.example.com:99999')).toBe('The port is out of range.');
  });
});

describe('validation', () => {
  const valid = () => apply(fresh(), {type: 'mode', id: 'region', mode: 'locked'},
    {type: 'originText', value: 'https://app.example.com'}, {type: 'addOrigin'});

  it('accepts a complete draft', () => {
    expect(validateDraft(valid(), fx.catalog)).toEqual({});
  });

  it('checks what the server checks, early', () => {
    const draft = apply(valid(),
      {type: 'field', field: 'name', value: ' '}, {type: 'field', field: 'lifetime', value: '5'},
      {type: 'field', field: 'pageSize', value: '100000'}, {type: 'field', field: 'maxRows', value: '0'},
      {type: 'addClaim'}, {type: 'claim', index: 0, patch: {name: 'user_id'}},
      {type: 'addClaim'}, {type: 'claim', index: 1, patch: {name: 'bad name'}},
      {type: 'addClaim'}, {type: 'claim', index: 2, patch: {name: 'org'}},
      {type: 'addClaim'}, {type: 'claim', index: 3, patch: {name: 'org'}},
      {type: 'originText', value: 'ftp://x'});
    const errors = validateDraft({...draft, origins: [...draft.origins, 'https://*.example.com']}, fx.catalog);
    expect(Object.keys(errors).sort()).toEqual([
      'claim.0', 'claim.1', 'claim.3', 'lifetime', 'maxRows', 'name', 'origin.1', 'pageSize']);
    expect(errors['claim.0']).toBe('"user_id" is reserved for the server.');
    expect(errors['claim.3']).toBe('Each claim can be declared once.');
    expect(errors.lifetime).toBe('Use a whole number of seconds from 30 to 3600.');
  });

  it('uses the limits the server reports', () => {
    const small = {...fx.catalog, max_token_lifetime_seconds: 120, max_page_size: 10, max_rows: 20};
    const draft = apply(valid(), {type: 'field', field: 'lifetime', value: '600'},
      {type: 'field', field: 'pageSize', value: '11'}, {type: 'field', field: 'maxRows', value: '21'});
    expect(Object.keys(validateDraft(draft, small)).sort()).toEqual(['lifetime', 'maxRows', 'pageSize']);
  });

  it('requires a required parameter to be declared', () => {
    const draft = newDraft({resourceType: 'question', resourceId: 'q', resourceName: 'Q',
      parameters: [{id: 'floor', required: true, type: 'integer'}]});
    expect(validateDraft(draft, fx.catalog)['parameter.floor']).toMatch(/must be locked, editable or hidden/);
    const declared = apply(draft, {type: 'mode', id: 'floor', mode: 'hidden'});
    expect(validateDraft(declared, fx.catalog)['parameter.floor']).toBeUndefined();
  });

  it('refuses downloads the server forbids', () => {
    const draft = apply(valid(), {type: 'display', patch: {download: true}});
    expect(validateDraft(draft, fx.catalog).download).toBeUndefined();
    expect(validateDraft(draft, {...fx.catalog, downloads_allowed: false}).download).toMatch(/disabled on this server/);
  });

  it('warns about choices that are legal but rarely intended', () => {
    const draft = apply(fresh(), {type: 'mode', id: 'region', mode: 'editable'},
      {type: 'field', field: 'lifetime', value: '3000'}, {type: 'addClaim'});
    expect(warnings(draft, {rawSql: true})).toEqual([
      'No origin is allowed, so no site can show this embed in a frame.',
      'Viewers can change editable parameters to any allowed value.',
      'Raw SQL cannot use claims, so the server will refuse this.',
      'Tokens that live longer than 15 minutes stay useful if they leak.',
    ]);
    expect(warnings(valid())).toEqual([]);

    function valid() {
      return apply(fresh(), {type: 'mode', id: 'region', mode: 'locked'},
        {type: 'originText', value: 'https://a.example.com'}, {type: 'addOrigin'});
    }
  });
});

describe('panel reducer and the one-time secret', () => {
  it('shows the secret after a create and keeps it until the user says so', () => {
    const {embed, secret} = fx.created;
    let state = panelReducer(initialPanel(), {type: 'loaded', items: [embed]});
    state = panelReducer(state, {type: 'secretShown', embedId: embed.embed_id, kid: secret.kid, secret: secret.secret});
    expect(state.secret).toEqual({embedId: 'e-partner', kid: 'kid-1', secret: 'SECRET-1'});
    // reloads, edits and notices do not drop it
    state = panelReducer(state, {type: 'loaded', items: [embed]});
    state = panelReducer(state, {type: 'edit', id: 'new'});
    state = panelReducer(state, {type: 'notice', text: 'x'});
    state = panelReducer(state, {type: 'failed', error: 'boom'});
    expect(state.secret.secret).toBe('SECRET-1');
    state = panelReducer(state, {type: 'secretHidden'});
    expect(state.secret).toBeNull();
  });

  it('never puts the secret into the list or into what the server returns again', () => {
    const state = panelReducer(initialPanel(), {type: 'loaded', items: fx.list.items});
    expect(JSON.stringify(state)).not.toMatch(/SECRET|TOKEN/);
    expect(JSON.stringify(fx.list)).not.toMatch(/SECRET|TOKEN/);
    expect(JSON.stringify(fx.listForManager)).not.toMatch(/SECRET|TOKEN/);
  });

  it('tracks loading, errors and busy work', () => {
    let state = panelReducer(initialPanel(), {type: 'loading'});
    expect(state.status).toBe('loading');
    state = panelReducer(state, {type: 'failed', error: 'down'});
    expect(state).toMatchObject({status: 'error', error: 'down'});
    state = panelReducer(state, {type: 'loaded', items: fx.list.items});
    state = panelReducer(state, {type: 'busy', key: 'rotate-e-partner'});
    expect(state).toMatchObject({busy: 'rotate-e-partner', error: '', notice: ''});
    state = panelReducer(state, {type: 'failed', error: 'again'});
    expect(state).toMatchObject({status: 'ready', busy: '', error: 'again'});
    state = panelReducer(state, {type: 'dismiss'});
    expect(state.error).toBe('');
  });

  it('keeps statistics for the embed that asked for them', () => {
    let state = panelReducer(initialPanel(), {type: 'statsLoading', id: 'e-partner'});
    state = panelReducer(state, {type: 'statsLoaded', id: 'someone-else', data: fx.stats});
    expect(state.stats.status).toBe('loading');
    state = panelReducer(state, {type: 'statsLoaded', id: 'e-partner', data: fx.stats});
    expect(state.stats).toMatchObject({status: 'ready', id: 'e-partner'});
    state = panelReducer(state, {type: 'statsFailed', id: 'e-partner', error: 'no'});
    expect(state.stats).toMatchObject({status: 'error', error: 'no'});
    state = panelReducer(state, {type: 'statsClosed'});
    expect(state.stats.status).toBe('idle');
  });
});

describe('statistics', () => {
  it('summarizes the counts the server keeps', () => {
    expect(statsSummary(fx.stats)).toEqual({
      totals: {views: 3, cardRuns: 2, errors: 0},
      rows: [{day: '2026-03-02', views: 3, cardRuns: 2, errors: 0}]});
    expect(statsSummary(null).rows).toEqual([]);
    expect(statsSummary({series: [{day: 'a', views: 1}, {day: 'b', views: 2}]}).rows.map((row) => row.day))
      .toEqual(['b', 'a']);
  });
});

describe('preview request', () => {
  const draft = () => draftFromEmbed(fx.created.embed, filters);

  it('types the values and leaves blanks out', () => {
    expect(previewRequest(draft(), {region: ' east '}, {tenant_id: '42'})).toEqual({
      params: {region: 'east'}, claims: {tenant_id: 42}, problems: {}});
    expect(previewRequest(draft(), {}, {tenant_id: 'acme'}).claims).toEqual({tenant_id: 'acme'});
  });

  it('reports a missing required claim by name', () => {
    expect(previewRequest(draft(), {region: 'east'}, {}).problems).toEqual({
      'claim.tenant_id': 'This claim is required.'});
  });

  it('reports values that do not fit the parameter type', () => {
    const typed = apply(newDraft({resourceType: 'question', resourceId: 'q', resourceName: 'Q', parameters: [
      {id: 'n', type: 'integer', required: true}, {id: 'on', type: 'boolean'}, {id: 'many', type: 'integer', multiple: true},
    ]}), {type: 'mode', id: 'n', mode: 'locked'}, {type: 'mode', id: 'on', mode: 'locked'},
    {type: 'mode', id: 'many', mode: 'editable'});
    expect(previewRequest(typed, {n: '1.5', on: 'maybe', many: '1, x'}).problems).toEqual({
      n: 'Not a valid integer value.', on: 'Not a valid boolean value.', many: 'Not a valid integer value.'});
    expect(previewRequest(typed, {n: '7', on: 'true', many: '1, 2'})).toMatchObject({
      params: {n: 7, on: true, many: [1, 2]}, problems: {}});
    expect(previewRequest(typed, {on: 'false'}).problems).toEqual({
      n: 'The token needs a value for this parameter.'});
  });

  it('coerces by type', () => {
    expect(coerceValue('integer', '12')).toBe(12);
    expect(coerceValue('integer', '1e3')).toBeNull();
    expect(coerceValue('number', '1.5')).toBe(1.5);
    expect(coerceValue('number', 'abc')).toBeNull();
    expect(coerceValue('string', ' x ')).toBe('x');
    expect(coerceValue('string', '   ')).toBeUndefined();
    expect(coerceValue('boolean', 'true')).toBe(true);
    expect(coerceValue('string', 'a, b', true)).toEqual(['a', 'b']);
  });

  it('puts the token in the query of the frame address and encodes it', () => {
    expect(frameAddress('/cdeadmin/embed/e/frame', 'a.b-c_d')).toBe('/cdeadmin/embed/e/frame?token=a.b-c_d');
    expect(frameAddress('/f', 'a b&c')).toBe('/f?token=a%20b%26c');
    expect(frameAddress(fx.preview.frame_path, fx.preview.token)).toBe(
      '/cdeadmin/embed/e-partner/frame?token=TOKEN-3');
  });
});

describe('snippets', () => {
  const embed = fx.rotated.embed;
  const draft = () => draftFromEmbed(embed, filters);

  it('never contain a secret, and read it from the environment', () => {
    const {python, node, pseudo} = snippets({embed, draft: draft(), host: 'https://bi.example.com'});
    for(const text of [python, node, pseudo]) {
      expect(text).not.toMatch(/SECRET-\d/);
      expect(text).toContain('/cdeadmin/embed/e-partner/frame?token=');
      expect(text).toContain('https://bi.example.com');
      expect(text).toContain('e-partner');
    }
    expect(python).toContain('os.environ["CDE_EMBED_SECRET"]');
    expect(python).toContain('algorithm="HS256"');
    expect(node).toContain('process.env.CDE_EMBED_SECRET');
  });

  it('use the current key id and declare the parameters and claims', () => {
    const {python, pseudo} = snippets({embed, draft: draft(), host: 'https://bi.example.com'});
    expect(python).toContain('headers={"kid": "kid-4"}');
    expect(python).toContain('"params": {"region":"<region>"}');
    expect(python).toContain('"claims": {"tenant_id":"<tenant_id>"}');
    expect(pseudo).toContain('"kid": "kid-4"');
    expect(pseudo).toContain('"aud": "e-partner"');
  });

  it('cap the example lifetime at the embed maximum', () => {
    const short = {...embed, definition: {...embed.definition, max_token_lifetime_seconds: 60}};
    expect(snippets({embed: short, draft: draft()}).python).toContain('now + 60');
    expect(snippets({embed, draft: draft()}).python).toContain('now + 300');
  });

  it('fall back to placeholders when the viewer cannot see the keys', () => {
    const hidden = {...embed, keys: []};
    expect(snippets({embed: hidden, draft: null}).pseudo).toContain('<kid>');
  });
});
