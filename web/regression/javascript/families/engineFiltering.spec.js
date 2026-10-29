/*
 * Per-engine filtering of offered features (owner direction 2026-10-29:
 * surface every feature, filter per engine) and the runtime support notice.
 */
import {
  fieldOptions, optionOffered, versionSupportNotice,
} from '../../../pgadmin/static/js/cdeadmin_ui/objects/descriptors';
import {loadEndpointResources} from '../../../pgadmin/static/js/cdeadmin_ui/objects/ProviderObjectEditorHost';

const moduleField = {
  field_id: 'module', control: 'select', options: [
    {value: 'fts5', label: 'Fts5', requires_resource: {resource_kind: 'extension', native_name: 'fts5'}},
    {value: 'csv', label: 'Csv', requires_resource: {resource_kind: 'extension', native_name: 'csv'}},
    {value: 'plain', label: 'Plain'},
    {value: 'newer', label: 'Newer', available: false, unavailable_reason: 'Requires version 9'},
  ],
};

describe('optionOffered and fieldOptions', () => {
  it('offers resource-backed options only when the endpoint reports the resource', () => {
    const context = {resources: {extension: [{display_name: 'fts5', native: {}}]}};
    expect(fieldOptions(moduleField, {context}).map((o) => o.value)).toEqual(['fts5', 'plain']);
  });

  it('fails closed when the endpoint resources are unknown', () => {
    expect(fieldOptions(moduleField, {context: {}}).map((o) => o.value)).toEqual(['plain']);
  });

  it('matches native names as well as display names', () => {
    const context = {resources: {extension: [{display_name: 'FTS5 module', native: {native_name: 'fts5'}}]}};
    expect(optionOffered(moduleField.options[0], context)).toBe(true);
  });

  it('drops values the resolver marked unavailable for the runtime version', () => {
    expect(optionOffered(moduleField.options[3], {})).toBe(false);
    expect(optionOffered('plain-string', {})).toBe(true);
  });

  it('filters option lists reached through option_values_path', () => {
    const field = {control: 'select', option_values_path: ['dialect', 'modules']};
    const context = {
      dialect: {modules: [
        {value: 'rtree', label: 'rtree', requires_resource: {resource_kind: 'extension', native_name: 'rtree'}},
        {value: 'gone', label: 'gone', available: false},
        'text-value',
      ]},
      resources: {extension: [{display_name: 'rtree'}]},
    };
    expect(fieldOptions(field, {context}).map((o) => o.value)).toEqual(['rtree', 'text-value']);
  });
});

describe('versionSupportNotice', () => {
  it('explains a runtime newer than every tracked version', () => {
    const text = versionSupportNotice({observed_version: '3.53.1', status: 'newer_than_tracked',
      reference_version: '3.53.0', requirement: '>=3.35.0'});
    expect(text).toContain('3.53.1');
    expect(text).toContain('3.53.0');
  });

  it('explains an untested version inside the range', () => {
    expect(versionSupportNotice({observed_version: '3.40.1', status: 'untested_in_range',
      reference_version: '3.53.0', requirement: '>=3.35.0'})).toContain('>=3.35.0');
  });

  it('says nothing for the reference or tested versions or without data', () => {
    expect(versionSupportNotice({observed_version: '3.53.0', status: 'reference'})).toBeNull();
    expect(versionSupportNotice({observed_version: '3.45.1', status: 'tested'})).toBeNull();
    expect(versionSupportNotice(null)).toBeNull();
  });
});

describe('loadEndpointResources', () => {
  it('follows continuations so later resources are not lost', async () => {
    const pages = {
      first: {items: [{resource_kind: 'table'}], next_cursor: 'c1', generation: 'g'},
      c1: {items: [{resource_kind: 'extension', display_name: 'fts5'}], next_cursor: null, generation: 'g'},
    };
    const requests = [];
    const post = async ({request}) => { requests.push(request); return pages[request.continuation || 'first']; };
    const items = await loadEndpointResources(post);
    expect(items.map((row) => row.resource_kind)).toEqual(['table', 'extension']);
    expect(requests).toEqual([{}, {continuation: 'c1', generation: 'g'}]);
  });

  it('stops at its page bound and on a failed read', async () => {
    let calls = 0;
    const endless = async () => { calls += 1; return {items: [{}], next_cursor: 'again', generation: 'g'}; };
    expect((await loadEndpointResources(endless)).length).toBe(20);
    expect(calls).toBe(20);
    const failing = async () => { throw new Error('offline'); };
    expect(await loadEndpointResources(failing)).toEqual([]);
  });
});
