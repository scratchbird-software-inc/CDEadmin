import {dashboardPanelFiles} from './dashboardPanels';

export function currentPostgresqlNativeMetrics(snapshot,scope) {
  const sample=snapshot?.samples?.at(-1);
  const fresh=snapshot?.state==='collecting' && Number.isFinite(snapshot?.sample_age_seconds) &&
    snapshot.sample_age_seconds>=0 && Number.isFinite(snapshot?.stale_after_seconds) && snapshot.sample_age_seconds<=snapshot.stale_after_seconds;
  const native=sample?.groups?.native_metrics;
  return fresh && sample?.transaction_completed===true && sample.scope===scope && ['available','partial'].includes(sample.status) &&
    native?.schema==='postgresql-native-metric-families@1' ? native : null;
}

export function postgresqlNativeMetricFiles(snapshot,scope,source,page=0) {
  const collected=currentPostgresqlNativeMetrics(snapshot,scope),frame=collected?.sources?.[source];
  const rows=['available','partial'].includes(frame?.status) && Array.isArray(frame.rows) ? frame.rows : [],pages=Math.max(1,Math.ceil(rows.length/10));
  const selected=Number.isInteger(page) && page>=0 && page<pages ? page : 0;
  const panels=[{id:'native_status',title:'Native PostgreSQL statistics coverage',rows:[
    ['Source',source || 'No source selected'],['Status',frame?.status || 'No current collected sample'],
    ['Native scope',frame?.scope],['Visibility',frame?.visibility],['Truncated',frame?.truncated],
    ['Statistics visibility',collected?.statistics_visibility],['Native SQLSTATE',frame?.sqlstate],
    ['Collected rows',frame?.visible_row_count],['Row byte budget',collected?.row_byte_limit,'bytes per sample'],
    ['Page',selected+1,'of '+pages],
  ]}];
  rows.slice(selected*10,selected*10+10).forEach((row,index) => {
    const vartype=frame.columns.findIndex(column => column.name==='vartype');
    panels.push({id:'native_row_'+index,title:source+' · row '+(selected*10+index+1),
      rows:(frame.columns || []).map((column,ordinal) => [column.name,
        column.redaction==='query_or_credential_text' || column.redaction?.startsWith('string_settings_redacted') && row[vartype]==='string' ? 'Redacted' : row[ordinal],
        column.metric?.unit || column.value_type])});
  });
  return dashboardPanelFiles(panels,'Native PostgreSQL statistics','scratchrobin.postgresql.native_statistics');
}
