import runtime from '../../../pgadmin/static/vendor/ddn/current/ddn.mjs';
import {FIREBIRD_ACTIVITY, firebirdActivityFiles} from 'sources/cdeadmin_ui/integrations/ddn/firebirdActivity';

describe('native activity DDN adapter', () => {
  beforeAll(() => runtime.setTextProvider((text, size) => ({width: String(text).length * size * 0.6,
    ascent: size * 0.8, descent: size * 0.2}), 'activity-test'));
  afterAll(() => runtime.setTextProvider(null));
  it('renders each native category and preserves exact identities and escaped names', () => {
    for(const selection of FIREBIRD_ACTIVITY) {
      const row = Object.fromEntries(selection.fields.map((field) => [field, '9007199254740993']));
      row.user = 'name " } ;';
      const files = firebirdActivityFiles({groups: {[selection.id]: {status: 'available', values: {rows: [row]}}}}, selection.id);
      const workspace = runtime.createWorkspace(files);
      try {
        const result = workspace.renderSync({entry: 'activity.ddn', view: 'activity'});
        expect(result.diagnostics.filter((item) => item.severity === 'error')).toEqual([]);
        expect(new DOMParser().parseFromString(result.svg, 'image/svg+xml').documentElement.textContent).toContain('9007199254740993');
      } finally {workspace.destroy();}
    }
  });
  it('does not confuse denied observations with empty observations', () => {
    expect(firebirdActivityFiles(null, 'attachment_details')['activity.ddn']).toContain('Source unavailable');
    expect(firebirdActivityFiles({groups: {attachment_details: {status: 'available', values: {rows: []}}}},
      'attachment_details')['activity.ddn']).toContain('No visible rows');
    expect(() => firebirdActivityFiles(null, 'arbitrary-query')).toThrow();
  });
});
