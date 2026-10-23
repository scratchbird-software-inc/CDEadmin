import fs from 'fs';
import path from 'path';
import vm from 'vm';
import {mysqlSpatialFiles} from 'sources/cdeadmin_ui/integrations/ddn/mysqlSpatial';

const vendor=path.resolve(__dirname,'../../../pgadmin/static/vendor/ddn/current');
function context() {
  const value=vm.createContext({performance,TextEncoder,TextDecoder});
  for(const file of ['ddn.global.js','ddn-geo.js']) vm.runInContext(fs.readFileSync(path.join(vendor,file),'utf8'),value);
  return value;
}
const geometry={type:'GeometryCollection',geometries:[{type:'Point',coordinates:[1000000,2000000]},
  {type:'LineString',coordinates:[[1000000,2000000],[1001000,2002000]]},
  {type:'MultiLineString',coordinates:[[[1000000,2000000],[1001500,2002500]]]},
  {type:'Polygon',coordinates:[[[0,0],[10,0],[10,10],[0,0]],[[2,2],[3,2],[3,3],[2,2]]]}]};
it('renders native Cartesian lines, collections, points and holes with paired DDN only',() => {
  const lib=context(),files=mysqlSpatialFiles({map_mode:'native',rows:[{id:'row-0',map_geometry:geometry}]});
  const ws=lib.DDNLive.createWorkspace(files);
  try {
    const result=ws.renderSync({entry:'spatial.ddn',view:'spatial'});
    expect(result.diagnostics.filter(d => d.severity==='error')).toEqual([]);
    expect(result.svg).toContain('fill-rule="evenodd"');expect(result.svg).toContain('circle');
    expect(result.svg).not.toMatch(/NaN|Infinity|requires ddn-geo/);
    expect(result.svg).not.toMatch(/https?:\/\/(?!www.w3.org)/);
  } finally {ws.destroy();}
});
it('keeps large native coordinates finite and selected row filtering explicit',() => {
  const lib=context(),files=mysqlSpatialFiles({map_mode:'native',rows:[{id:'a',map_geometry:{type:'LineString',coordinates:[[-1e308,0],[1e308,0]]}},
    {id:'b',map_geometry:geometry}]},'a');
  const ws=lib.DDNLive.createWorkspace(files);
  try {expect(ws.renderSync({entry:'spatial.ddn',view:'spatial'}).svg).not.toMatch(/NaN|Infinity/);}
  finally {ws.destroy();}
  expect(files['spatial.ddn']).not.toContain('"id":"b"');
});
it('retains the geographic antimeridian boundary and bounded module input',() => {
  const lib=context();
  expect(lib.DDNGeo.geoPath({type:'LineString',coordinates:[[170,0],[-170,0]]},p => p)).toBe('M170 0M-170 0');
  expect(() => lib.DDNGeo.ingest({type:'LineString',coordinates:[[1,2],[1,NaN]]})).toThrow();
  expect(mysqlSpatialFiles({rows:[{id:'null',map_geometry:null}]})).toBeNull();
});
