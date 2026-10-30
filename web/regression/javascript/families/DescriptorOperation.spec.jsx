import pgAdmin from 'sources/pgadmin';
import {act} from 'react';
import {openDescriptorOperation} from 'pgbrowser/ProviderObjectEditor';
import {
  descriptorClient, fieldOptions, resetDescriptorClient,
} from '../../../pgadmin/static/js/cdeadmin_ui/objects';
import {loadEngineBundle} from './familyFixtures';

// The dialog's props are what this spec checks; the dialog itself has its own.
const mockRendered = [];
jest.mock('../../../pgadmin/static/js/cdeadmin_ui/objects/OperationDialog', () => ({
  __esModule: true,
  default: (props) => { mockRendered.push(props); return null; },
}));

const tablet = {resource_kind: 'tablet', resource_id: 'tablet:lookup_keyspace:-:test-0000000301',
  display_name: 'test-0000000301', display_path: ['lookup_keyspace', '-', 'test-0000000301'], native: {}};
const backups = [
  {resource_kind: 'backup', resource_id: 'backup:lookup_keyspace:-:b1', display_name: '2026-10-30.125734.test-0000000301',
    display_path: ['lookup_keyspace', '-', '2026-10-30.125734.test-0000000301']},
  {resource_kind: 'backup', resource_id: 'backup:test_keyspace:-80:b2', display_name: '2026-10-30.120000.test-0000000101',
    display_path: ['test_keyspace', '-80', '2026-10-30.120000.test-0000000101']},
];

const mockApi = {
  get: jest.fn(async () => ({data: {success: 1, data: loadEngineBundle('vitess')}})),
  post: jest.fn(async (_url, payload) => {
    if(payload.action === 'resource_inspect') return {data: {success: 1, data: tablet}};
    // Two pages: the dialog must read past the first.
    if(payload.action === 'resource_page' && !payload.request.continuation) {
      return {data: {success: 1, data: {items: [tablet, backups[1]], next_cursor: 'c1', generation: 'g'}}};
    }
    return {data: {success: 1, data: {items: [backups[0]], next_cursor: null}}};
  }),
};
jest.mock('sources/api_instance', () => () => mockApi);

const serverData = {_type: 'server', _id: 7, cde_endpoint: true, cde_engine_id: 'vitess', cde_profile_id: 'vitess',
  runtime_verification_state: 'verified', cde_session_authenticated: true, verified_runtime_version: '23.0.3'};
const tabletData = {_type: 'cde_resource', cde_resource_kind: 'tablet', cde_resource_id: tablet.resource_id,
  cde_engine_id: 'vitess', cde_database_target_id: 'db-1', label: 'test-0000000301', cde_context_actions: []};

describe('descriptor operation dialog wiring', () => {
  beforeEach(() => {
    mockRendered.length = 0;
    resetDescriptorClient();
    pgAdmin.Browser.tree = {
      itemData: (item) => ({server: serverData, tablet: tabletData})[item],
      hasParent: (item) => item === 'tablet',
      parent: () => 'server',
    };
    pgAdmin.Browser.Nodes.server.generate_url = jest.fn(() => '/browser/server/cde_workspace/1/7');
  });

  it('gives the dialog the catalog context, scoped to the target, so restore lists this shard\'s backups', async () => {
    const bundle = await descriptorClient(mockApi).bundle('vitess', {version: '23.0.3'});
    const restore = bundle.kinds.tablet.operations.find((op) => op.operation_id === 'restore');
    await act(async () => {
      openDescriptorOperation(tabletData, 'tablet', restore);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(mockRendered).toHaveLength(1);
    const {context, operation} = mockRendered[0];
    expect(context.target_resource).toEqual(tablet);
    expect(fieldOptions(operation.fields[0], {context}).map((option) => option.value))
      .toEqual(['2026-10-30.125734.test-0000000301']);
  });
});
