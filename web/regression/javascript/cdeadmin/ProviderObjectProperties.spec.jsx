import {act, render, screen, waitFor} from '@testing-library/react';
import ProviderObjectProperties from '../../../pgadmin/misc/properties/ProviderObjectProperties';
import getApiInstance from '../../../pgadmin/static/js/api_instance';
import pgAdmin from 'sources/pgadmin';
import {promptEndpointVerification} from '../../../pgadmin/browser/static/js/ProviderObjectEditor';

jest.mock('../../../pgadmin/static/js/api_instance');
jest.mock('../../../pgadmin/browser/static/js/ProviderObjectEditor', () => ({
  promptEndpointVerification: jest.fn(),
}));

describe('provider selection inspector', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('uses the target-scoped URL, exact resource identity, generation and auto-placing field grid', async () => {
    const api = {
      get: jest.fn().mockResolvedValue({
        data: {
          data: {
            resource_page: {generation: 'g1'},
            visual_admin: {objects: []},
          },
        },
      }),
      post: jest.fn().mockResolvedValue({
        data: {
          data: {
            display_name: 'Orders',
            resource_kind: 'table',
            display_path: ['public', 'Orders'],
            native: {
              owner_name: 'SYSDBA',
              system_flag: false,
              external_file: null,
            },
          },
        },
      }),
    };
    getApiInstance.mockReturnValue(api);
    const {container} = render(
      <ProviderObjectProperties
        nodeData={{
          cde_workspace_url: '/scope?database_target_id=db1',
          cde_database_target_id: 'db1',
          cde_resource_id: 'table:1',
          cde_resource_kind: 'table',
        }}
      />
    );
    expect((await screen.findAllByText('Orders'))[0]).toBeVisible();
    expect(container.querySelector('[data-contained-scroll="false"]')).toBeInTheDocument();
    const grid = container.querySelector('[data-cdeadmin-qa-key="auto-placing-properties-grid"]');
    expect(grid).toBeInTheDocument();
    expect(container.querySelector('[data-cdeadmin-qa-key="property-field-owner_name"]')).toHaveTextContent('SYSDBA');
    expect(container.querySelector('[data-cdeadmin-qa-key="property-field-system_flag"]')).toHaveTextContent('No');
    expect(api.post).toHaveBeenCalledWith(
      '/scope?database_target_id=db1',
      {
        action: 'resource_inspect',
        request: {
          resource_id: 'table:1',
          generation: 'g1',
          database_target_id: 'db1',
        },
      },
      expect.objectContaining({signal: expect.any(AbortSignal)})
    );
  });

  it('never replaces the current selection with a late response', async () => {
    let finishFirst;
    const api = {
      get: jest.fn().mockResolvedValue({data: {data: {}}}),
      post: jest.fn().mockImplementation((_url, payload) =>
        payload.request.resource_id === 'first'
          ? new Promise((resolve) => {
              finishFirst = resolve;
            })
          : Promise.resolve({data: {data: {display_name: 'Second'}}})
      ),
    };
    getApiInstance.mockReturnValue(api);
    const node = {cde_workspace_url: '/scope', cde_resource_kind: 'table'};
    const {rerender} = render(<ProviderObjectProperties nodeData={{...node, cde_resource_id: 'first'}} />);
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    rerender(<ProviderObjectProperties nodeData={{...node, cde_resource_id: 'second'}} />);
    expect((await screen.findAllByText('Second'))[0]).toBeVisible();
    await act(async () => finishFirst({data: {data: {display_name: 'First'}}}));
    expect(screen.queryByText('First')).not.toBeInTheDocument();
    expect(screen.getAllByText('Second')[0]).toBeVisible();
  });

  it('surfaces permission failures instead of pretending metadata is empty', async () => {
    getApiInstance.mockReturnValue({
      get: jest.fn().mockRejectedValue({
        response: {data: {errormsg: 'Permission denied'}},
      }),
    });
    render(
      <ProviderObjectProperties
        nodeData={{
          cde_workspace_url: '/scope',
          cde_resource_id: 'table:1',
          cde_resource_kind: 'table',
        }}
      />
    );
    expect(await screen.findByRole('alert')).toHaveTextContent('Permission denied');
  });

  it('prompts for credential verification and retries automatically on HTTP 401 CREDENTIAL_REQUIRED', async () => {
    const serverItem = {id: 'srv-fb'};
    const tableItem = {id: 'tbl-orders'};
    pgAdmin.Browser = {
      ...(pgAdmin.Browser || {}),
      tree: {
        selected: () => tableItem,
        hasParent: (item) => item === tableItem,
        parent: (item) => (item === tableItem ? serverItem : null),
        itemData: (item) => (item === serverItem ? {_type: 'server'} : {_type: 'cde_resource'}),
      },
    };
    promptEndpointVerification.mockResolvedValue(true);

    const get = jest
      .fn()
      .mockRejectedValueOnce({
        response: {status: 401, data: {code: 'CREDENTIAL_REQUIRED', errormsg: 'Verify endpoint'}},
      })
      .mockResolvedValueOnce({
        data: {data: {resource_page: {generation: 'g2'}, visual_admin: {objects: []}}},
      });
    const post = jest.fn().mockResolvedValue({
      data: {data: {display_name: 'RecoveredTable', resource_kind: 'table', native: {owner_name: 'SYSDBA'}}},
    });
    getApiInstance.mockReturnValue({get, post});

    render(
      <ProviderObjectProperties
        nodeData={{
          cde_workspace_url: '/scope?database_target_id=db1',
          cde_database_target_id: 'db1',
          cde_resource_id: 'table:recovered',
          cde_resource_kind: 'table',
        }}
      />
    );

    expect((await screen.findAllByText('RecoveredTable'))[0]).toBeVisible();
    expect(promptEndpointVerification).toHaveBeenCalledWith(serverItem, 'db1');
    expect(get).toHaveBeenCalledTimes(2);
  });
});
