import {COUNTER_FIELDS} from './dashboardPublication.mjs';
import {dashboardPanelFiles} from './dashboardPanels.js';
// Fixed native bindings: a dashboard cannot supply SQL or connection routes.
const hex = (value) => Array.from(new TextEncoder().encode(String(value))).map((byte) => byte.toString(16).padStart(2, '0')).join('');
const metricNames = ['allocated_bytes', 'memory_used', 'user_attachments', 'oldest_age_seconds', 'crypt_state', 'replica_mode', 'page_reads_per_second', 'page_writes_per_second'];
const findingRows = (database, prefix) => (database.findings || []).map((finding) => Object.assign([finding.reason, finding.value,
  `Threshold: ${finding.threshold ?? 'not applicable'}; observed: ${finding.observed_at || 'unknown'}`], {bindingId:`${prefix}_finding_${hex(finding.code)}`}));
const panelFiles = (panels, title) => dashboardPanelFiles(panels, title, 'scratchrobin.firebird.monitoring');

export function firebirdDashboardFiles(snapshot, title='Firebird dashboard', scope='database') {
  const last = snapshot?.samples?.at(-1);
  const fresh = snapshot?.state === 'collecting' && Number.isFinite(snapshot?.sample_age_seconds) &&
    snapshot.sample_age_seconds <= snapshot.stale_after_seconds;
  const sample = fresh && ['available', 'partial'].includes(last?.status) ? last : null;
  const groups = sample?.groups || {};
  const panels = [{id: 'status', title: 'Observation and availability', rows: [
    ['Collection', snapshot?.state || 'Unknown', ''],
    ['Latest probe', last?.status || 'Not sampled', ''],
    ['Observed at', last?.ended_at, 'UTC'],
    ['Last successful observation', last?.last_success_at, 'UTC'],
    ['Visibility', sample?.coverage, ''],
    ['Heartbeat', snapshot?.heartbeat?.status || 'Disabled', ''],
    ['Heartbeat age', snapshot?.heartbeat?.age_seconds, 'seconds'],
    ['History', 'Volatile process buffer', ''],
    ['Sample age', snapshot?.sample_age_seconds, 'seconds'],
    ['Freshness', fresh ? 'Current' : 'No current observation', ''],
  ]}];
  const values = (name) => groups[name]?.status === 'available' ? groups[name].values : null;
  const group = (id, name, labels, unit='') => panels.push({id, title: name,
    rows: labels.map(([field, label]) => [label, values(id)?.[field], unit])});
  if(scope === 'server') {
    panels.push({id: 'server', title: 'Service manager', rows: [
      ['Version', values('version'), ''],
      ['Architecture', values('architecture'), ''],
      ['Service manager version', values('manager_version'), ''],
      ['Capabilities', values('capabilities'), 'native bitmask'],
      ['Database attachments', values('connection_count'), 'attachments'],
      ['Attached databases', groups.attached_databases?.status === 'available' ?
        values('attached_databases').join(', ') : null, 'visible attached files'],
    ]});
  } else {
    group('database', 'Database identity', [
      ['database_name', 'Database'], ['guid', 'GUID'], ['file_id', 'File identity'],
      ['owner', 'Owner'], ['ods_major', 'ODS major'], ['ods_minor', 'ODS minor'],
      ['page_size', 'Page size (bytes)'], ['sql_dialect', 'SQL dialect'],
      ['read_only', 'Read only (native flag)'], ['forced_writes', 'Forced writes (native flag)'],
    ]);
    group('attachments', 'Visible attachments — collector separated', [
      ['visible_total', 'Visible total'], ['user', 'User attachments'],
      ['collector', 'Collector'], ['system', 'System'],
      ['active_user', 'Active users'], ['idle_user', 'Idle users'],
    ], 'attachments');
    group('transactions', 'Visible transactions — collector excluded', [
      ['visible_total', 'Transactions'], ['active', 'Active'],
      ['read_only', 'Read only'], ['oldest_age_seconds', 'Oldest age (seconds)'],
    ]);
    for(const [id, name, unit] of [['io', 'Database I/O', 'pages'],
      ['records', 'Database record operations — not committed changes', 'operations'],
      ['memory', 'Database memory — not host RAM', 'bytes']]) {
      const fields = COUNTER_FIELDS[id].map((key) => [key, values(id)?.[key]]);
      panels.push({id, title: name, rows: fields.length ? fields.map(([key, value]) => [
        key.replaceAll('_', ' '), value, unit,
        sample?.rates?.status === 'available' ? sample.rates.per_second?.[`${id}.${key}`] : null,
      ]) : [['Source unavailable', null, unit]]});
    }
    panels.push({id: 'storage', title: 'Allocation and transaction distances', rows: [
      ['Allocated space', sample?.derived?.allocated_bytes, 'bytes (not filesystem size)'],
      ['Configured page cache', sample?.derived?.configured_cache_bytes, 'bytes'],
      ['Next minus OIT', sample?.derived?.next_minus_oit, 'transaction numbers'],
      ['Next minus OAT', sample?.derived?.next_minus_oat, 'transaction numbers'],
      ['Next minus OST', sample?.derived?.next_minus_ost, 'transaction numbers'],
    ]});
    const protection = values('protection_details')?.rows?.[0];
    panels.push({id: 'protection', title: 'Native protection and compiled inventory', rows: [
      ['Backup state', protection?.backup_state, 'native state, not backup verification'],
      ['Encryption state', protection?.crypt_state, 'native state'],
      ['Encryption page', protection?.crypt_page, 'progress marker, not percent complete'],
      ['Replica mode', protection?.replica_mode, 'native mode, not replication lag'],
      ['Visible compiled statements', values('compiled_counts')?.rows?.[0]?.count, 'compiled objects'],
      ['Newest visible physical backup', values('backup_details')?.rows?.[0]?.timestamp, 'native history, not gbak history'],
      ['Backup inventory observed at', groups.backup_details?.observed_at, 'cached inventory observation'],
    ]});
  }
  if(scope === 'server') panels.push(...serverDatabasePanels(snapshot));
  return panelFiles(panels, title);
}



export function firebirdFleetFiles(snapshot) {
  const panels = [{id: 'inventory', title: 'Owner registrations — this process', rows: [
    ['Registered native endpoints', snapshot?.registered_endpoints, 'registrations'],
    ...['reachable', 'failed', 'unknown', 'permission-limited', 'stale'].map((key) =>
      [key, snapshot?.status_counts?.[key], 'endpoints']),
    ['Inventory basis', 'Registered targets and visible attached files are separate inventories', ''],
    ['History', 'Volatile process buffer', ''],
  ]}];
  for(const server of (snapshot?.servers || [])) {
    panels.push({id: `server_${server.server_id}`, title: server.name, rows: [
      ['Observation', server.status, ''],
      ['Collection', server.collection_state, ''],
      ['Sample age', server.sample_age_seconds, 'seconds'],
      ['Observed at', server.observed_at, 'UTC'],
      ['Version', server.version, ''], ['Architecture', server.architecture, ''],
      ['Known database targets', server.known_databases, 'registrations'],
      ['Monitored database targets', server.monitored_databases, 'collectors'],
      ['Attached files', server.attached_databases?.join(', '), 'service-visible only'],
    ]});
    for(const database of (server.databases || [])) {
      panels.push({id: `fleetdb_${server.server_id}_${hex(database.target_id)}`, title: `${server.name} / ${database.name}`, rows: [
        ['Status', database.status, ''], ['Coverage', database.coverage, 'native visibility'],
        ['Sample age', database.sample_age_seconds, 'seconds'],
        ['Allocated bytes', database.metrics?.allocated_bytes, 'bytes'],
        ['Database memory used', database.metrics?.memory_used, 'bytes, not server RSS'],
        ['User attachments', database.metrics?.user_attachments, 'visible, collector excluded'],
        ['Oldest transaction age', database.metrics?.oldest_age_seconds, 'seconds'],
        ['Page reads', database.metrics?.page_reads_per_second, 'pages per second'],
        ['Page writes', database.metrics?.page_writes_per_second, 'pages per second'],
        ['Rate observation time', database.rate_window?.ended_at, 'UTC'],
        ['Rate interval', database.rate_window?.elapsed_seconds, 'seconds'],
        ['Encryption state', database.metrics?.crypt_state, 'native flag'],
        ['Replica mode', database.metrics?.replica_mode, 'native flag, not replication lag'],
        ...findingRows(database, `fleetdb_${server.server_id}_${hex(database.target_id)}`),
      ]});
    }
    panels.push({id: `aggregate_${server.server_id}`, title: `${server.name} / observed database totals`, rows: [
      ['Identified databases', server.aggregate?.identified_databases, 'GUID and file ID within this endpoint'],
      ['Alias registrations', server.aggregate?.alias_targets, 'excluded from sums'],
      ['Unidentified registrations', server.aggregate?.unidentified_targets, 'excluded from sums'],
      ...['allocated_bytes','memory_used','user_attachments','page_reads_per_second','page_writes_per_second'].map((name) => {
        const metric = server.aggregate?.metrics?.[name] || {};
        return [
          name.replaceAll('_', ' '), metric.value,
          `${metric.observed_databases}/${metric.identified_databases} identified databases observed; ${metric.status || 'availability not reported'}`,
        ]; }),
      ...['encrypted','unencrypted','wire_unknown','local','transport_unknown','observed_databases','identified_databases'].map((name) => [
        `Wire coverage: ${name.replaceAll('_', ' ')}`, server.aggregate?.wire_security?.[name], 'visible user attachments; local and unknown kept separate',
      ]),
      ...['0','1','2','3','unknown'].map((name) => [
        `Database encryption native state ${name}`, server.aggregate?.database_encryption?.[name], 'identified databases, not all registered targets',
      ]),
    ]});
  }
  return panelFiles(panels, 'Firebird engine dashboard');
}

function serverDatabasePanels(snapshot) {
  const panels = (snapshot?.databases || []).map((database) => ({
    id: `database_${hex(database.target_id)}`, title: database.name, rows: [
      ['Status', database.status, ''], ['Coverage', database.coverage, 'native visibility'],
      ['Observed at', database.observed_at, 'UTC'],
      ['Sample age', database.sample_age_seconds, 'seconds'],
      ['Rate observation time', database.rate_window?.ended_at, 'UTC'],
      ['Rate interval', database.rate_window?.elapsed_seconds, 'seconds'],
      ...metricNames.map((name) => [
        name.replaceAll('_', ' '), database.metrics?.[name], 'native database observation']),
      ...findingRows(database, `database_${hex(database.target_id)}`),
    ],
  }));
  if(!panels.length) panels.push({id: 'empty', title: 'Registered databases', rows: [
    ['No registered database observations', null, 'No collector is started by this view'],
  ]});
  return panels;
}

export function firebirdServerDatabaseFiles(snapshot) {
  return panelFiles(serverDatabasePanels(snapshot), 'Registered database observations');
}
