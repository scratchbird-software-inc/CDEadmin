import runtime, { setupDDNDOM } from './ddnTestRuntime';
import { monitoringDetailFiles } from 'sources/Dialogs/FirebirdMonitoringDetails';
describe('authorized monitoring detail DDN', () => {
  beforeAll(setupDDNDOM);
  it.each(['accounts', 'receipts', 'server-paths'])('renders bounded %s through the public renderer', async operation => {
    const files = monitoringDetailFiles({
      operation,
      rows: [{
        user_name: 'user " }',
        name: '/native/path',
        operation_id: 'operation-1',
        unknown_outcome: true
      }]
    });
    const workspace = await runtime.createWorkspace(files);
    try {
      const rendered = await workspace.render({
        entry: 'details.ddn',
        view: 'details'
      });
      expect(rendered.diagnostics.filter(item => item.severity === 'error')).toEqual([]);
      expect(rendered.svg).toContain('<svg');
    } finally {
      workspace.destroy();
    }
  });
});
