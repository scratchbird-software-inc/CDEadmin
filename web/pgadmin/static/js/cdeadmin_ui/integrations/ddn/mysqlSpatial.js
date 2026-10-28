import {recordSource,viewSource,sourceHeader} from './source.js';
// Native geometry is inert input to DDN; no tile or network layer.
export function mysqlSpatialFiles(report,selected=null) {
  const rows=(report?.rows || []).filter(row=>row.map_geometry && (!selected || selected===row.id));
  if(!rows.length) return null;
  const geography={type:'FeatureCollection',features:rows.map(row=>({type:'Feature',id:row.id,properties:{name:row.id},geometry:row.map_geometry}))};
  return {'spatial.ddn':sourceHeader('scratchrobin.mysql.spatial')+
    recordSource('native_geometry','Native geometry inspection',{geography})+
    viewSource('spatial','Native spatial inspection','geo.outline@1',{
      geography:'native_geometry',method:report.map_mode==='wgs84'?'equirectangular':'cartesian',graticule:false})};
}
