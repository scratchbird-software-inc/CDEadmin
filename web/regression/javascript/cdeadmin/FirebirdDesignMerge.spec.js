import runtime, { setupDDNDOM } from './ddnTestRuntime';
import { refreshDesign } from 'sources/cdeadmin_ui/integrations/ddn/designMerge';
import { catalogBundle } from 'sources/Dialogs/FirebirdServerCatalog';
describe('Native DDN refresh with authored source retention', () => {
  beforeAll(setupDDNDOM);
  it('sends source workspaces to shared server conversion and retains editor metadata', async () => {
    const snapshot = {
      format: 'ddn-source-workspace@1',
      entry: 'a.ddn',
      view: 'v',
      files: {
        'a.ddn': 'source'
      }
    };
    const post = jest.fn().mockResolvedValue({
      ...snapshot,
      files: {
        'a.ddn': 'merged'
      }
    });
    const value = await refreshDesign(post, snapshot, {
      ...snapshot,
      editorState: 'retained'
    }, snapshot);
    expect(post).toHaveBeenCalledWith({
      action: 'ddn_design_merge',
      request: {
        baseline: snapshot,
        draft: snapshot,
        incoming: snapshot
      }
    });
    expect(value.files['a.ddn']).toBe('merged');
    expect(value.editorState).toBe('retained');
  });
  it('propagates conversion failure without replacing the authored draft', async () => {
    const snapshot = {
      format: 'ddn-source-workspace@1',
      entry: 'a.ddn',
      view: 'v',
      files: {
        'a.ddn': 'source'
      }
    };
    await expect(refreshDesign(() => Promise.reject(new Error('Conflict')), snapshot, snapshot, snapshot)).rejects.toThrow('Conflict');
    expect(snapshot.files['a.ddn']).toBe('source');
  });
  it('renders server overview using the paired public runtime', async () => {
    const overview = catalogBundle({
      endpoint_id: 'e',
      display_name: 'Server'
    }, [{
      target_id: 'one',
      label: 'First',
      status: 'failed'
    }, {
      target_id: 'two',
      label: 'Second',
      status: 'not-attempted'
    }]).overview;
    const workspace = await runtime.createWorkspace(overview.files);
    try {
      const result = await workspace.render(overview);
      expect(result.diagnostics.filter(item => item.severity === 'error')).toEqual([]);
      expect(result.svg).toContain('First');
      expect(result.svg).toContain('not-attempted');
    } finally {
      workspace.destroy();
    }
  });
});
