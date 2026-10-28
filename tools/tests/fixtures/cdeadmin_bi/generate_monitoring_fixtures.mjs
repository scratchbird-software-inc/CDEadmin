// Regenerates monitoring_dashboards.json from the real JavaScript encoder:
//   node --no-warnings tools/tests/fixtures/cdeadmin_bi/generate_monitoring_fixtures.mjs \
//     > tools/tests/fixtures/cdeadmin_bi/monitoring_dashboards.json
// The BI converter test compares its Python writer against these files byte
// for byte, so regenerate after any change to dashboardPanels.js.
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../../web/pgadmin/static/js/cdeadmin_ui/integrations/ddn');
const {sqliteDashboardFiles, sqliteFleetPublication} = await import(path.join(root, 'sqliteDashboard.js'));
const {duckdbDashboardFiles} = await import(path.join(root, 'duckdbDashboard.js'));
const {dashboardPanelFiles} = await import(path.join(root, 'dashboardPanels.js'));

const sample = (extra = {}) => ({
  status: 'available', scope: 'database', ended_at: '2026-10-28T12:00:00Z',
  identity: {database_name: 'main', target_id: 't1'},
  transaction_refresh: {status: 'completed'}, ...extra,
});
const sqlite = {
  state: 'collecting', sample_age_seconds: 3, stale_after_seconds: 30,
  heartbeat: {status: 'ok'}, databases: [{}, {}],
  samples: [sample({groups: {
    storage: {rows: [{page_size_bytes: 4096, page_count: 10, freelist_pages: 1,
      logical_size_bytes: 40960, free_space_bytes: 4096, file_size_bytes: 40960}]},
    database: {rows: [{journal_mode: 'wal', schema_version: 3, user_version: 0,
      read_only_route: 'no'}]}}})],
};
const duckdb = {
  state: 'collecting', sample_age_seconds: 1, stale_after_seconds: 30,
  heartbeat: {status: 'ok'}, databases: [],
  samples: [sample({groups: {storage: {rows: [{database_size: '12 KiB', block_size: 262144,
    total_blocks: 4, used_blocks: 2, free_blocks: 2, memory_usage: '1 MiB', memory_limit: '8 GiB'}]}}})],
};
const fleetSnapshot = {
  registered_endpoints: 14,
  servers: Array.from({length: 14}, (_, index) => ({
    server_id: index + 1, name: `Endpoint ${index + 1}`,
    snapshot: {state: 'collecting', sample_age_seconds: 2, stale_after_seconds: 30,
      heartbeat: {status: 'ok'}, samples: [sample()]},
    databases: [],
  })),
};
const fleet = sqliteFleetPublication(fleetSnapshot);
const wrap = (engine, scope, view, files) => ({
  engine, scope, snapshot: {format: 'ddn-source-workspace@1', entry: 'dashboard.ddn', view, files},
});
const escapePanels = [
  {id: 'p', title: 'Say "hi"\nnow', rows: [
    Object.assign(['A "quoted"\tname', 'line1\nline2', '', 'x/s'], {bindingId: 'p_0'}),
    ['Defaults']]},
  {id: 'long_' + 'x'.repeat(260), title: 'T'.repeat(1100), rows: [['m', 'v']]},
];
const escapes = {
  title: 'T', module: 'scratchrobin.x.monitoring',
  panels: escapePanels.map(panel => ({id: panel.id, title: panel.title,
    rows: panel.rows.map((row, index) => ({id: row.bindingId ?? `${panel.id}_${index}`,
      measure: row[0] ?? 'Unavailable', value: row[1] ?? 'Unavailable', unit: row[2] ?? '', rate: row[3] ?? ''}))})),
  files: dashboardPanelFiles(escapePanels, 'T', 'scratchrobin.x.monitoring'),
};
console.log(JSON.stringify({
  escapes,
  sqlite_database: wrap('sqlite', 'database', 'dashboard', sqliteDashboardFiles(sqlite, 'database')),
  sqlite_engine_fleet: wrap('sqlite', 'engine', 'dashboard', fleet.files),
  duckdb_database: wrap('duckdb', 'database', 'dashboard', duckdbDashboardFiles(duckdb, 'database')),
}, null, 1));
