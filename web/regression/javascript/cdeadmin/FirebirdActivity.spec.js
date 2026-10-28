import runtime, { setupDDNDOM } from './ddnTestRuntime';
import { FIREBIRD_ACTIVITY, firebirdActivityFiles } from 'sources/cdeadmin_ui/integrations/ddn/firebirdActivity';
describe('native activity DDN adapter', () => {
  beforeAll(setupDDNDOM);
  it('renders each native category and preserves exact identities and escaped names', async () => {
    for (const selection of FIREBIRD_ACTIVITY) {
      const row = Object.fromEntries(selection.fields.map(field => [field, '9007199254740993']));
      row.user = 'name " } ;';
      const files = firebirdActivityFiles({
        groups: {
          [selection.id]: {
            status: 'available',
            values: {
              rows: [row]
            }
          }
        }
      }, selection.id);
      const workspace = await runtime.createWorkspace(files);
      try {
        const result = await workspace.render({
          entry: 'activity.ddn',
          view: 'activity'
        });
        expect(result.diagnostics.filter(item => item.severity === 'error')).toEqual([]);
        expect(new DOMParser().parseFromString(result.svg, 'image/svg+xml').documentElement.textContent).toContain('9007199254740993');
      } finally {
        workspace.destroy();
      }
    }
  });
  it('does not confuse denied observations with empty observations', () => {
    expect(firebirdActivityFiles(null, 'attachment_details')['activity.ddn']).toContain('Source unavailable');
    expect(firebirdActivityFiles({
      groups: {
        attachment_details: {
          status: 'available',
          values: {
            rows: []
          }
        }
      }
    }, 'attachment_details')['activity.ddn']).toContain('No visible rows');
    expect(() => firebirdActivityFiles(null, 'arbitrary-query')).toThrow();
  });
});
