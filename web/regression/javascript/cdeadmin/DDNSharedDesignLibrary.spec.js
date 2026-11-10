import {
  DESIGN_KINDS,
  DESIGN_SAVE_POINTS,
  DesignStoreClient,
  ERD_MODELLING_LEVELS,
  SharedDDNTaskController,
} from 'sources/cdeadmin_ui/integrations/ddn';

const sampleWorkspace = {
  format: 'ddn-source-workspace@1',
  entry: 'sales.ddn',
  view: 'main',
  files: {
    'sales.ddn': 'version ddn-next-1\nelement "019a0000-0000-7000-8000-000000000001" as "table"\n    with\n        id "019a0000-0000-7000-8000-000000000001"\n        title "customers"\n',
  },
};

function makeFakeApi() {
  const sessionPayload = {
    design: {
      id: '019a0000-0000-7000-8000-000000000010',
      kind: 'erd',
      title: 'Sales ERD',
      head_version: 1,
      active_version: null,
      version: {
        version: 1,
        status: 'draft',
        ddn_text: sampleWorkspace.files['sales.ddn'],
      },
    },
    workspace: sampleWorkspace,
    layout: {
      algorithm: 'scratchrobin-server-layered@1',
      tile_size: 1024,
      nodes: [
        {
          id: '019a0000-0000-7000-8000-000000000001',
          name: 'customers',
          role: 'table',
          layer: 0,
          order: 0,
          x: 48,
          y: 48,
          width: 240,
          height: 86,
          pinned: false,
        },
      ],
      edges: [],
      tiles: [
        {
          tx: 0,
          ty: 0,
          tile_key: 'tile-0-0',
          bounds: {min_x: 0, min_y: 0, max_x: 1024, max_y: 1024},
          node_ids: ['019a0000-0000-7000-8000-000000000001'],
          edge_ids: [],
        },
        {
          tx: 2,
          ty: 2,
          tile_key: 'tile-2-2',
          bounds: {min_x: 2048, min_y: 2048, max_x: 3072, max_y: 3072},
          node_ids: [],
          edge_ids: [],
        },
      ],
    },
    resolved_includes: [
      {
        depends_on_design_id: '019a0000-0000-7000-8000-000000000099',
        mode: 'pinned',
        resolved_version: 1,
      },
    ],
    binding_summary: {total: 1, valid: 1, suspect: 0, unknown: 0},
  };

  return {
    sessionPayload,
    get: jest.fn(async () => ({data: {data: sessionPayload}})),
    post: jest.fn(async () => ({data: {data: sessionPayload.design}})),
    put: jest.fn(async () => {
      sessionPayload.design.head_version = 2;
      sessionPayload.design.version.version = 2;
      return {data: {data: {design: sessionPayload.design, layout: sessionPayload.layout}}};
    }),
    delete: jest.fn(async () => ({data: {data: {deleted: true}}})),
  };
}

describe('Shared client-side DDN DesignStoreClient and SharedDDNTaskController', () => {
  it('exposes canonical save points, design kinds and ERD levels', () => {
    expect(DESIGN_SAVE_POINTS).toEqual(['draft', 'in_progress', 'in_review', 'accepted']);
    expect(DESIGN_KINDS).toContain('erd');
    expect(DESIGN_KINDS).toContain('cube');
    expect(DESIGN_KINDS).toContain('screen_mesh');
    expect(ERD_MODELLING_LEVELS).toEqual(['conceptual', 'logical', 'physical', 'deployment']);
  });

  it('loads server-computed layout and tiles, pins nodes, saves and accepts', async () => {
    const api = makeFakeApi();
    const client = new DesignStoreClient(api);
    const controller = new SharedDDNTaskController({
      client,
      projectId: 'proj-1',
      designId: '019a0000-0000-7000-8000-000000000010',
      kind: 'erd',
      tileSize: 1024,
    });

    const events = [];
    const unsubscribe = controller.subscribe((_state, evt) => events.push(evt.type));

    const loaded = await controller.load();
    expect(loaded.loaded).toBe(true);
    expect(loaded.headVersion).toBe(1);
    expect(loaded.tiles).toHaveLength(2);
    expect(loaded.resolvedIncludes[0].mode).toBe('pinned');

    // Viewport culling returns only intersecting server tiles
    const visible = controller.visibleTiles({
      min_x: 0,
      min_y: 0,
      max_x: 500,
      max_y: 500,
    });
    expect(visible.map((t) => t.tile_key)).toEqual(['tile-0-0']);

    controller.pinNode('019a0000-0000-7000-8000-000000000001', 320, 240, true);
    const saved = await controller.save({status: 'in_review', note: 'Pinned customers'});
    expect(saved.currentVersion).toBe(2);
    expect(api.put).toHaveBeenCalledWith(
      '/cdeadmin/api/projects/proj-1/designs/019a0000-0000-7000-8000-000000000010',
      expect.objectContaining({
        expected_head_version: 1,
        pinned_positions: {
          '019a0000-0000-7000-8000-000000000001': {x: 320, y: 240, pinned: true},
        },
      })
    );

    await controller.accept({
      requireGitReview: true,
      gitReviewRef: 'pr:77',
      comment: 'Accepted',
    });
    expect(api.post).toHaveBeenCalledWith(
      '/cdeadmin/api/projects/proj-1/designs/019a0000-0000-7000-8000-000000000010/versions/2/accept',
      {
        require_git_review: true,
        git_review_ref: 'pr:77',
        comment: 'Accepted',
      }
    );

    await controller.confirmSuspectBinding('bind-1', 'res-new');
    expect(api.post).toHaveBeenCalledWith(
      '/cdeadmin/api/projects/proj-1/designs/019a0000-0000-7000-8000-000000000010/bindings/bind-1/confirm',
      {new_target_ref: 'res-new'}
    );

    unsubscribe();
    expect(events).toContain('loaded');
    expect(events).toContain('pin-changed');
    expect(events).toContain('saved');
  });
});
