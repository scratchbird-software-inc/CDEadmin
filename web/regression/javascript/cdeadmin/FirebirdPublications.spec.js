import runtime from '../../../pgadmin/static/vendor/ddn/current/ddn.mjs';
import {firebirdPublicationFiles} from 'sources/cdeadmin_ui/integrations/ddn/firebirdPublications';

describe('native publication topology', () => {
  beforeAll(() => runtime.setTextProvider((text, size) => ({width: String(text).length * size * 0.6,
    ascent: size * 0.8, descent: size * 0.2}), 'publication-topology-test'));
  afterAll(() => runtime.setTextProvider(null));
  it('renders captured memberships with explicit missing attributes, never invented replicas', () => {
    const files = firebirdPublicationFiles({groups: {
      publication_details: {status: 'available', values: {rows: [{publication_name: 'P', active_flag: '1'}]}},
      publication_table_details: {status: 'available', values: {rows: [
        {publication_name: 'P', table_name: 'TABLE_ONE'}, {publication_name: 'OTHER', table_name: 'TABLE_ONE'}]}},
    }});
    const workspace = runtime.createWorkspace(files);
    try {
      const rendered = workspace.renderSync({entry: 'publications.ddn', view: 'publications'});
      expect(rendered.diagnostics.filter((item) => item.severity === 'error')).toEqual([]);
      expect(rendered.svg).toContain('attributes not captured');
      expect(files['publications.ddn'].match(/record t0/g)).toHaveLength(1);
    } finally {workspace.destroy();}
  });
});
