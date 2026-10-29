import runtime, { setupDDNDOM } from './ddnTestRuntime';
import { firebirdPublicationFiles } from 'sources/cdeadmin_ui/integrations/ddn/firebirdPublications';
describe('native publication topology', () => {
  beforeAll(setupDDNDOM);
  it('renders captured memberships with explicit missing attributes, never invented replicas', async () => {
    const files = firebirdPublicationFiles({
      groups: {
        publication_details: {
          status: 'available',
          values: {
            rows: [{
              publication_name: 'P',
              active_flag: '1'
            }]
          }
        },
        publication_table_details: {
          status: 'available',
          values: {
            rows: [{
              publication_name: 'P',
              table_name: 'TABLE_ONE'
            }, {
              publication_name: 'OTHER',
              table_name: 'TABLE_ONE'
            }]
          }
        }
      }
    });
    const workspace = await runtime.createWorkspace(files);
    try {
      const rendered = await workspace.render({
        entry: 'publications.ddn',
        view: 'publications'
      });
      expect(rendered.diagnostics.filter(item => item.severity === 'error')).toEqual([]);
      expect(rendered.svg).toContain('attributes not captured');
      expect(files['publications.ddn'].match(/element "t0" as "record"/g)).toHaveLength(1);
    } finally {
      workspace.destroy();
    }
  });
});
