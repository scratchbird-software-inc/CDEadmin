// Native geometry is inert input to the paired DDN renderer; no tile/network layer.
export function mysqlSpatialFiles(report, selected=null) {
  const rows=(report?.rows || []).filter(row => row.map_geometry && (!selected || selected===row.id));
  const geometry={type:'FeatureCollection',features:rows.map(row => ({type:'Feature',id:row.id,properties:{name:row.id},geometry:row.map_geometry}))};
  if(!rows.length) return null;
  const method=report.map_mode==='wgs84' ? 'equirectangular' : 'cartesian';
  return {'spatial.ddn':`ddn "0.5"; module "scratchrobin.mysql.spatial";
data geometry_data { record geometry "Native geometry inspection" { x_record: ${JSON.stringify(geometry)}; } }
view spatial "MySQL native spatial inspection" {
 data: [@geometry_data]; select: [@geometry_data.geometry];
 projection { kind:geo; profile:"geo.outline@1"; geography:@geometry_data.geometry; method:${method};
   graticule:false; width:1050px; height:620px; }
 publication { size:content; fit:none; }
}`};
}
