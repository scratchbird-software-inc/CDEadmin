import { createTestWorkspace, setupDDNDOM } from './ddnTestRuntime';
import { mysqlSpatialFiles } from 'sources/cdeadmin_ui/integrations/ddn/mysqlSpatial';
const geometry = {
  type: 'GeometryCollection',
  geometries: [{
    type: 'Point',
    coordinates: [1000000, 2000000]
  }, {
    type: 'LineString',
    coordinates: [[1000000, 2000000], [1001000, 2002000]]
  }, {
    type: 'MultiLineString',
    coordinates: [[[1000000, 2000000], [1001500, 2002500]]]
  }, {
    type: 'Polygon',
    coordinates: [[[0, 0], [10, 0], [10, 10], [0, 0]], [[2, 2], [3, 2], [3, 3], [2, 2]]]
  }]
};
beforeAll(setupDDNDOM);
it('captures Cartesian lines, collections, points and holes through paired DDN', async () => {
  const workspace = await createTestWorkspace(mysqlSpatialFiles({
    map_mode: 'native',
    rows: [{
      id: 'row-0',
      map_geometry: geometry
    }]
  }));
  try {
    const result = await workspace.render({
      entry: 'spatial.ddn',
      view: 'spatial'
    });
    expect(result.diagnostics.filter(item => item.severity === 'error')).toEqual([]);
    expect(result.svg).toContain('fill-rule="evenodd"');
    expect(result.svg).toContain('ellipse');
    expect(result.svg).not.toMatch(/NaN|Infinity|requires ddn-geo/);
    expect(result.svg).not.toMatch(/https?:\/\/(?!www.w3.org)/);
  } finally {
    workspace.destroy();
  }
});
it('keeps extreme finite native coordinates drawable and respects selected rows', async () => {
  const files = mysqlSpatialFiles({
    map_mode: 'native',
    rows: [{
      id: 'a',
      map_geometry: {
        type: 'LineString',
        coordinates: [[-1e308, 0], [1e308, 0]]
      }
    }, {
      id: 'b',
      map_geometry: geometry
    }]
  }, 'a');
  const workspace = await createTestWorkspace(files);
  try {
    const result = await workspace.render({
      entry: 'spatial.ddn',
      view: 'spatial'
    });
    expect(result.svg).not.toMatch(/NaN|Infinity/);
    expect(result.diagnostics.filter(item => item.severity === 'error')).toEqual([]);
  } finally {
    workspace.destroy();
  }
  expect(files['spatial.ddn']).not.toContain('""id"":""b""');
});
it('retains geographic antimeridian outlines and admits no missing geometry', async () => {
  const workspace = await createTestWorkspace(mysqlSpatialFiles({
    map_mode: 'wgs84',
    rows: [{
      id: 'line',
      map_geometry: {
        type: 'LineString',
        coordinates: [[170, 0], [-170, 0]]
      }
    }]
  }));
  try {
    const result = await workspace.render({
      entry: 'spatial.ddn',
      view: 'spatial'
    });
    expect(result.svg).not.toMatch(/NaN|Infinity/);
    expect(result.diagnostics.filter(item => item.severity === 'error')).toEqual([]);
  } finally {
    workspace.destroy();
  }
  expect(mysqlSpatialFiles({
    rows: [{
      id: 'null',
      map_geometry: null
    }]
  })).toBeNull();
});
