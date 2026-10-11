import runtime from '../../../pgadmin/static/vendor/ddn/current/ddn.mjs';
import {monitoringDetailFiles} from 'sources/Dialogs/FirebirdMonitoringDetails';

describe('authorized monitoring detail DDN', () => {
  beforeAll(() => runtime.setTextProvider((text, size) => ({width: String(text).length * size * 0.6,
    ascent: size * 0.8, descent: size * 0.2}), 'monitoring-details-test'));
  afterAll(() => runtime.setTextProvider(null));
  it.each(['accounts', 'receipts', 'server-paths'])('renders bounded %s through the public renderer', (operation) => {
    const files = monitoringDetailFiles({operation, rows: [{user_name: 'user " }', name: '/native/path',
      operation_id: 'operation-1', unknown_outcome: true}]});
    const workspace = runtime.createWorkspace(files);
    try {
      const rendered = workspace.renderSync({entry: 'details.ddn', view: 'details'});
      expect(rendered.diagnostics.filter((item) => item.severity === 'error')).toEqual([]);
      expect(rendered.svg).toContain('<svg');
    } finally {workspace.destroy();}
  });
});
