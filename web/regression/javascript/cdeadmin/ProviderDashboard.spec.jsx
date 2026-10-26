import {act, render, screen, waitFor} from '@testing-library/react';
import ProviderDashboard from '../../../pgadmin/dashboard/static/js/ProviderDashboard';
import getApiInstance from 'sources/api_instance';
import {resetDescriptorClient} from 'sources/cdeadmin_ui/objects/DescriptorClient';
import mysql from '../../../pgadmin/cdeadmin/ui_descriptors/mysql/tools.json';
import firebird from '../../../pgadmin/cdeadmin/ui_descriptors/firebird/tools.json';

jest.mock('sources/api_instance');
jest.mock('sources/components/EmptyPanelMessage', () => function Message(props) {return <div>{props.text}</div>;});
jest.mock('sources/Dialogs/FirebirdMonitoring', () => function FirebirdViewer(props) {return <div data-testid="firebird-viewer">{JSON.stringify(props)}</div>;});
jest.mock('sources/Dialogs/MySQLMonitoring', () => function RelationalViewer(props) {return <div data-testid="relational-viewer">{JSON.stringify(props)}</div>;});

describe('shared provider dashboard routing', () => {
  let api;
  beforeEach(() => {
    resetDescriptorClient();
    api = {get: jest.fn(async url => ({data: {success: 1,
      data: {tools: url.includes('/firebird') ? firebird.tools : mysql.tools}}}))};
    getApiInstance.mockReturnValue(api);
  });
  it.each([['mysql', 'relational'], ['firebird', 'firebird']])(
    'opens the declared %s viewer without an interactive SQL session', async (engine, viewer) => {
      render(<ProviderDashboard engine={engine} serverId="6" />);
      const surface = await screen.findByTestId(`${viewer}-viewer`);
      expect(JSON.parse(surface.textContent)).toEqual({engine, serverId: 6, policyMode: false, engineMode: false});
      expect(api.get).toHaveBeenCalledWith(`/cdeadmin/api/ui/descriptors/${engine}`);
    });
  it.each([['mysql', 'relational'], ['firebird', 'firebird']])(
    'uses the registered target and remounts the %s viewer when it changes', async (engine, viewer) => {
      const mounted = render(<ProviderDashboard engine={engine} serverId={6} targetId="target-a" />);
      const previous = await screen.findByTestId(`${viewer}-viewer`);
      mounted.rerender(<ProviderDashboard engine={engine} serverId={6} targetId="target-b" />);
      expect(JSON.parse(screen.getByTestId(`${viewer}-viewer`).textContent).targetId).toBe('target-b');
      expect(screen.getByTestId(`${viewer}-viewer`)).not.toBe(previous);
      expect(api.get).toHaveBeenCalledTimes(1);
    });
  it('uses descriptor options rather than engine names to choose a renderer', async () => {
    api.get.mockResolvedValue({data: {success: 1, data: {tools: mysql.tools}}});
    render(<ProviderDashboard engine="another_engine" serverId={8} version="2.3" />);
    expect(JSON.parse((await screen.findByTestId('relational-viewer')).textContent).engine).toBe('another_engine');
    expect(api.get).toHaveBeenCalledWith('/cdeadmin/api/ui/descriptors/another_engine?version=2.3');
  });
  it('does not substitute a server dashboard when no database viewer is declared', async () => {
    api.get.mockResolvedValue({data: {success: 1, data: {tools: mysql.tools.filter(t => t.scope === 'endpoint')}}});
    render(<ProviderDashboard engine="mysql" serverId={6} targetId="target" />);
    await screen.findByText('No dashboard is configured for this connection.');
    expect(screen.queryByTestId('relational-viewer')).toBeNull();
  });
  it.each([{tools: []}, {tools: [{scope: 'endpoint', arguments: {dashboard_viewer: 'unknown'}}]}])(
    'reports unsupported declarations without launching another tool: %j', async ({tools}) => {
      api.get.mockResolvedValue({data: {success: 1, data: {tools}}});
      render(<ProviderDashboard engine="unsupported" serverId={8} />);
      await screen.findByText('No dashboard is configured for this connection.');
    });
  it('does not retain an old engine when a late descriptor response arrives', async () => {
    let finish;
    api.get.mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
    const mounted = render(<ProviderDashboard engine="mysql" serverId={6} />);
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
    mounted.rerender(<ProviderDashboard engine="firebird" serverId={4} />);
    await screen.findByTestId('firebird-viewer');
    await act(async () => {finish({data: {success: 1, data: {tools: mysql.tools}}});});
    expect(screen.queryByTestId('relational-viewer')).toBeNull();
    expect(JSON.parse(screen.getByTestId('firebird-viewer').textContent).serverId).toBe(4);
  });
  it('shows authorization errors without a fallback or collector mutation', async () => {
    api.get.mockRejectedValue({response: {data: {errormsg: 'Access denied'}}});
    render(<ProviderDashboard engine="mysql" serverId={6} />);
    await screen.findByText('Access denied');
    expect(screen.queryByTestId('relational-viewer')).toBeNull();
  });
});
