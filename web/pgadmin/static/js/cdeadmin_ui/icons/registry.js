/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import AddCircleIcon from '../../../assets/cdeadmin/commands/add-circle.svg?svgr';
import ArrowAllDirectionIcon from '../../../assets/cdeadmin/commands/arrow-all-direction.svg?svgr';
import CalendarClockIcon from '../../../assets/cdeadmin/commands/calendar-clock.svg?svgr';
import CancelCircleIcon from '../../../assets/cdeadmin/commands/cancel-circle.svg?svgr';
import CodeIcon from '../../../assets/cdeadmin/commands/code.svg?svgr';
import CommandLineIcon from '../../../assets/cdeadmin/commands/command-line.svg?svgr';
import ConnectIcon from '../../../assets/cdeadmin/commands/connect.svg?svgr';
import CopyIcon from '../../../assets/cdeadmin/commands/copy01.svg?svgr';
import DatabaseAddIcon from '../../../assets/cdeadmin/commands/database-add.svg?svgr';
import DatabaseBackupIcon from '../../../assets/cdeadmin/commands/database-backup.svg?svgr';
import DatabaseRestoreIcon from '../../../assets/cdeadmin/commands/database-restore.svg?svgr';
import DeleteIcon from '../../../assets/cdeadmin/commands/delete02.svg?svgr';
import DownloadIcon from '../../../assets/cdeadmin/commands/download01.svg?svgr';
import EditIcon from '../../../assets/cdeadmin/commands/edit01.svg?svgr';
import EyeIcon from '../../../assets/cdeadmin/commands/eye.svg?svgr';
import FileAddIcon from '../../../assets/cdeadmin/commands/file-add.svg?svgr';
import FilterIcon from '../../../assets/cdeadmin/commands/filter.svg?svgr';
import GitCompareIcon from '../../../assets/cdeadmin/commands/git-compare.svg?svgr';
import HelpCircleIcon from '../../../assets/cdeadmin/commands/help-circle.svg?svgr';
import HistoryIcon from '../../../assets/cdeadmin/commands/history.svg?svgr';
import InformationCircleIcon from '../../../assets/cdeadmin/commands/information-circle.svg?svgr';
import LinkIcon from '../../../assets/cdeadmin/commands/link01.svg?svgr';
import LockIcon from '../../../assets/cdeadmin/commands/lock.svg?svgr';
import MenuCircleIcon from '../../../assets/cdeadmin/commands/menu-circle.svg?svgr';
import PlayCircleIcon from '../../../assets/cdeadmin/commands/play-circle.svg?svgr';
import PrinterIcon from '../../../assets/cdeadmin/commands/printer.svg?svgr';
import RefreshIcon from '../../../assets/cdeadmin/commands/refresh.svg?svgr';
import SaveIcon from '../../../assets/cdeadmin/commands/save.svg?svgr';
import SearchIcon from '../../../assets/cdeadmin/commands/search01.svg?svgr';
import SettingsIcon from '../../../assets/cdeadmin/commands/settings02.svg?svgr';
import ShieldUserIcon from '../../../assets/cdeadmin/commands/shield-user.svg?svgr';
import SortIcon from '../../../assets/cdeadmin/commands/sort-by-down01.svg?svgr';
import TransactionIcon from '../../../assets/cdeadmin/commands/transaction.svg?svgr';
import UnlinkIcon from '../../../assets/cdeadmin/commands/unlink01.svg?svgr';
import UploadIcon from '../../../assets/cdeadmin/commands/upload01.svg?svgr';
import ScratchRobinIcon from '../../../assets/cdeadmin/branding/scratchrobincde.svg?svgr';

function UndoIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <path d="M5 9.5H14.5C17.5376 9.5 20 11.9624 20 15C20 18.0376 17.5376 20.5 14.5 20.5H10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M8.5 5.5L4.5 9.5L8.5 13.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function RedoIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <path d="M19 9.5H9.5C6.46243 9.5 4 11.9624 4 15C4 18.0376 6.46243 20.5 9.5 20.5H14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M15.5 5.5L19.5 9.5L15.5 13.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CutIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="6" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <line x1="20" y1="4" x2="8.12" y2="15.88" />
      <line x1="14.47" y1="14.48" x2="20" y2="20" />
      <line x1="8.12" y1="8.12" x2="12" y2="12" />
    </svg>
  );
}

function PasteIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
      <rect x="8" y="2" width="8" height="4" rx="1" />
    </svg>
  );
}

function SelectPointerIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M5 3l14 7.5-6.2 1.8L10 19 5 3z" />
      <path d="M12.8 12.3L18 17.5" />
    </svg>
  );
}

function SelectMarqueeIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="3 3" aria-hidden="true" {...props}>
      <rect x="4" y="4" width="16" height="16" rx="2" />
    </svg>
  );
}

function AlignIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <line x1="4" y1="4" x2="4" y2="20" />
      <rect x="8" y="6" width="12" height="4" rx="1" />
      <rect x="8" y="14" width="8" height="4" rx="1" />
    </svg>
  );
}

function LayersIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <polygon points="12 2 2 7 12 12 22 7 12 2" />
      <polyline points="2 12 12 17 22 12" />
      <polyline points="2 17 12 22 22 17" />
    </svg>
  );
}

function PaletteEntitiesIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <line x1="17.5" y1="14" x2="17.5" y2="21" />
      <line x1="14" y1="17.5" x2="21" y2="17.5" />
    </svg>
  );
}

function PaletteUdtIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M4 7V4h16v3" />
      <line x1="12" y1="4" x2="12" y2="20" />
      <line x1="9" y1="20" x2="15" y2="20" />
    </svg>
  );
}

function EndpointSourceIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <ellipse cx="10" cy="6" rx="6" ry="2.5" />
      <path d="M4 6v10c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5V6" />
      <path d="M15 12h6m-2.5-2.5L21 12l-2.5 2.5" />
    </svg>
  );
}

function EndpointTargetIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M3 12h6m-2.5-2.5L9 12l-2.5 2.5" />
      <ellipse cx="15" cy="6" rx="5.5" ry="2.5" />
      <path d="M9.5 6v10c0 1.4 2.5 2.5 5.5 2.5s5.5-1.1 5.5-2.5V6" />
    </svg>
  );
}

function SendReviewIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  );
}

function QueryPauseIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="6" y="4" width="4" height="16" rx="1" />
      <rect x="14" y="4" width="4" height="16" rx="1" />
    </svg>
  );
}

function FetchLimitsIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <line x1="4" y1="6" x2="20" y2="6" />
      <circle cx="9" cy="6" r="2" />
      <line x1="4" y1="12" x2="20" y2="12" />
      <circle cx="15" cy="12" r="2" />
      <line x1="4" y1="18" x2="20" y2="18" />
      <circle cx="11" cy="18" r="2" />
    </svg>
  );
}

function InspectorDrawerIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <line x1="15" y1="4" x2="15" y2="20" />
    </svg>
  );
}

export const ICON_CATEGORIES = Object.freeze({
  ACTION: 'action',
  ENGINE: 'engine',
  OBJECT: 'object',
  STATUS: 'status',
  TOOL: 'tool',
});

export const ENGINE_IDS = Object.freeze([
  'apache_ignite', 'cassandra', 'clickhouse', 'cockroachdb', 'dolt',
  'duckdb', 'firebird', 'foundationdb', 'immudb', 'influxdb', 'mariadb',
  'milvus', 'mongodb', 'mysql', 'neo4j', 'opensearch', 'postgresql',
  'redis', 'scratchbird', 'sqlite', 'tidb', 'tikv', 'vitess', 'xtdb',
  'yugabytedb',
]);

const OBJECT_CLASSES = Object.freeze({
  unknown: 'icon-object',
  server: 'icon-server',
  instance: 'icon-server',
  cluster: 'icon-server-group',
  database: 'icon-database',
  catalog: 'icon-database',
  schema: 'icon-schema',
  keyspace: 'icon-schema',
  table: 'icon-table',
  columnar_table: 'icon-table',
  wide_column_table: 'icon-table',
  view: 'icon-view',
  materialized_view: 'icon-mview',
  mview: 'icon-mview',
  column: 'icon-column',
  domain: 'icon-domain',
  type: 'icon-type',
  sequence: 'icon-sequence',
  function: 'icon-function',
  procedure: 'icon-procedure',
  package: 'icon-package',
  trigger: 'icon-trigger',
  index: 'icon-index',
  constraint: 'icon-check_constraint',
  role: 'icon-role',
  user: 'icon-role',
  grant: 'icon-security',
  privilege: 'icon-security',
  extension: 'icon-extension',
  plugin: 'icon-extension',
  partition: 'icon-partition',
  tablespace: 'icon-tablespace',
  filespace: 'icon-tablespace',
  replication: 'icon-publication',
  job: 'icon-pga_job',
  event: 'icon-event_trigger',
  collection: 'icon-coll-table',
  document: 'icon-file',
  validation_rule: 'icon-check_constraint',
  aggregation_pipeline: 'icon-query-tool',
  replica_set: 'icon-server-group',
  sharding: 'icon-partition',
  node: 'icon-server',
  relationship: 'icon-dependency',
  label: 'icon-collation',
  graph_projection: 'icon-erd',
  transaction: 'icon-commit',
  query_plan: 'icon-query-tool',
  cluster_member: 'icon-server',
  key: 'icon-key',
  ttl: 'icon-clock',
  stream: 'icon-query-tool',
  pubsub: 'icon-publication',
  consumer_group: 'icon-role',
  module: 'icon-extension',
  acl: 'icon-security',
  index_alias: 'icon-synonym',
  template: 'icon-template',
  pipeline: 'icon-query-tool',
  shard: 'icon-partition',
  snapshot: 'icon-backup',
  ingest_processor: 'icon-query-tool',
  measurement: 'icon-statistics',
  tag: 'icon-collation',
  field: 'icon-column',
  retention_policy: 'icon-clock',
  vector_collection: 'icon-coll-table',
  vector: 'icon-type',
  semantic_model: 'icon-erd',
  measure: 'icon-statistics',
  hierarchy: 'icon-schema',
});

const ACTION_COMPONENTS = Object.freeze({
  about: InformationCircleIcon,
  add: AddCircleIcon,
  align: AlignIcon,
  alter: EditIcon,
  attach: LinkIcon,
  backup: DatabaseBackupIcon,
  cancel: CancelCircleIcon,
  checkpoints: HistoryIcon,
  close: CancelCircleIcon,
  commit: SaveIcon,
  compare: GitCompareIcon,
  compare_run: RefreshIcon,
  connect: ConnectIcon,
  copy: CopyIcon,
  create: AddCircleIcon,
  create_database: DatabaseAddIcon,
  cut: CutIcon,
  delete: DeleteIcon,
  detach: UnlinkIcon,
  disconnect: UnlinkIcon,
  documentation: HelpCircleIcon,
  drop: DeleteIcon,
  duplicate: CopyIcon,
  edit: EditIcon,
  endpoint_source: EndpointSourceIcon,
  endpoint_target: EndpointTargetIcon,
  execute: PlayCircleIcon,
  export: DownloadIcon,
  fetch_limits: FetchLimitsIcon,
  filter: FilterIcon,
  float: ArrowAllDirectionIcon,
  help: HelpCircleIcon,
  import: UploadIcon,
  inspector_drawer: InspectorDrawerIcon,
  layers: LayersIcon,
  lock: LockIcon,
  move: ArrowAllDirectionIcon,
  new: FileAddIcon,
  open: EyeIcon,
  palette_entities: PaletteEntitiesIcon,
  palette_udt: PaletteUdtIcon,
  paste: PasteIcon,
  print: PrinterIcon,
  properties: InformationCircleIcon,
  query_pause: QueryPauseIcon,
  refresh: RefreshIcon,
  redo: RedoIcon,
  rename: EditIcon,
  restore: DatabaseRestoreIcon,
  rollback: HistoryIcon,
  save: SaveIcon,
  schedule: CalendarClockIcon,
  script: CodeIcon,
  search: SearchIcon,
  security: ShieldUserIcon,
  select_marquee: SelectMarqueeIcon,
  select_pointer: SelectPointerIcon,
  send_review: SendReviewIcon,
  settings: SettingsIcon,
  sort: SortIcon,
  sql_preview: CodeIcon,
  terminal: CommandLineIcon,
  transaction: TransactionIcon,
  undo: UndoIcon,
  unlock: LockIcon,
  view: EyeIcon,
});

const ACTION_INFERENCE = Object.freeze([
  ['create_database', /\b(?:create|new|register|add)[ _-]+database\b/],
  ['disconnect', /\bdisconnect(?:ed|ion)?\b/],
  ['detach', /\bdetach\b/],
  ['rollback', /\broll[ _-]?back\b/],
  ['restore', /\brestore\b/],
  ['backup', /\bbackup\b/],
  ['documentation', /\b(?:documentation|manual|docs)\b/],
  ['properties', /\b(?:properties|details|information)\b/],
  ['security', /\b(?:security|permissions?|privileges?|grants?|roles?|users?)\b/],
  ['transaction', /\btransactions?\b/],
  ['schedule', /\b(?:schedule|jobs?|events?)\b/],
  ['compare', /\b(?:compare|comparison|diff)\b/],
  ['settings', /\b(?:settings?|preferences?|configure|configuration|manage)\b/],
  ['execute', /\b(?:execute|run|start|play)\b/],
  ['terminal', /\b(?:terminal|console|shell|command[ _-]?line|psql)\b/],
  ['script', /\b(?:script|code|sql)\b/],
  ['connect', /\bconnect(?:ion)?\b/],
  ['attach', /\b(?:attach|link)\b/],
  ['delete', /\b(?:delete|remove)\b/],
  ['drop', /\bdrop\b/],
  ['cancel', /\b(?:cancel|abort|stop)\b/],
  ['close', /\b(?:close|exit|quit)\b/],
  ['import', /\b(?:import|upload)\b/],
  ['export', /\b(?:export|download)\b/],
  ['refresh', /\b(?:refresh|reload|rescan|sync)\b/],
  ['search', /\b(?:search|find|locate)\b/],
  ['filter', /\bfilter\b/],
  ['sort', /\bsort\b/],
  ['copy', /\b(?:copy|duplicate|clone)\b/],
  ['rename', /\brename\b/],
  ['alter', /\balter\b/],
  ['edit', /\b(?:edit|modify|update)\b/],
  ['commit', /\bcommit\b/],
  ['save', /\bsave\b/],
  ['undo', /\bundo\b/],
  ['redo', /\bredo\b/],
  ['print', /\bprint\b/],
  ['lock', /\block\b/],
  ['unlock', /\bunlock\b/],
  ['float', /\b(?:float|tear[ _-]?off|undock)\b/],
  ['move', /\b(?:move|reorder)\b/],
  ['new', /\bnew\b/],
  ['create', /\b(?:create|register|add)\b/],
  ['open', /\bopen\b/],
  ['view', /\b(?:view|show|inspect|browse)\b/],
  ['about', /\babout\b/],
  ['help', /\bhelp\b/],
]);

const STATUS_CLASSES = Object.freeze({
  connected: 'fa fa-check-circle',
  disconnected: 'fa fa-circle-o',
  error: 'fa fa-exclamation-circle',
  loading: 'fa fa-spinner fa-spin',
  locked: 'fa fa-lock',
  offline: 'fa fa-minus-circle',
  readonly: 'fa fa-eye',
  running: 'fa fa-play-circle',
  stopped: 'fa fa-stop-circle',
  warning: 'fa fa-exclamation-triangle',
});

const TOOL_CLASSES = Object.freeze({
  dashboard: 'icon-dashboard',
  dataflow: 'icon-erd',
  datapump: 'fa fa-exchange',
  mind_map: 'fa fa-sitemap',
  report: 'fa fa-bar-chart',
  whiteboard: 'fa fa-pencil-square-o',
});

const TAXONOMY_FALLBACKS = Object.freeze([
  ['relation.view.materialized', 'object.materialized_view'],
  ['relation.view', 'object.view'],
  ['relation.column', 'object.column'],
  ['relation.partition', 'object.partition'],
  ['relation.sequence', 'object.sequence'],
  ['relation.table', 'object.table'],
  ['columnar.table', 'object.columnar_table'],
  ['wide_column.table', 'object.wide_column_table'],
  ['access.index', 'object.index'],
  ['constraint.', 'object.constraint'],
  ['routine.procedure', 'object.procedure'],
  ['routine.trigger', 'object.trigger'],
  ['routine.package', 'object.package'],
  ['routine.', 'object.function'],
  ['namespace.keyspace', 'object.keyspace'],
  ['namespace.schema', 'object.schema'],
  ['namespace.', 'object.database'],
  ['security.role', 'object.role'],
  ['security.user', 'object.user'],
  ['security.', 'object.privilege'],
  ['replication.', 'object.replication'],
  ['operation.job', 'object.job'],
  ['operation.event', 'object.event'],
  ['operation.snapshot', 'object.snapshot'],
  ['topology.node', 'object.node'],
  ['topology.', 'object.cluster'],
  ['keyvalue.stream', 'object.stream'],
  ['keyvalue.ttl', 'object.ttl'],
  ['keyvalue.', 'object.key'],
  ['graph.relationship', 'object.relationship'],
  ['graph.node', 'object.node'],
  ['graph.', 'object.graph_projection'],
  ['search.pipeline', 'object.pipeline'],
  ['search.', 'object.index'],
  ['timeseries.measurement', 'object.measurement'],
  ['timeseries.tag', 'object.tag'],
  ['timeseries.', 'object.field'],
  ['vector.collection', 'object.vector_collection'],
  ['vector.', 'object.vector'],
  ['semantic.', 'object.semantic_model'],
  ['storage.filespace', 'object.filespace'],
  ['storage.tablespace', 'object.tablespace'],
]);

const SAFE_CLASS = /^[a-zA-Z0-9_-]+(?:\s+[a-zA-Z0-9_-]+)*$/;
const SAFE_KEY = /^[a-z0-9][a-z0-9._-]*$/;
export const ICON_ASSIGNMENT_SCHEMA = 'cdeadmin.icon-assignments.v1';

function title(value) {
  return String(value).replace(/[._-]+/g, ' ').replace(/\b\w/g, (c)=>c.toUpperCase());
}

function definition(key, category, className, label=title(key.split('.').pop())) {
  return Object.freeze({key, category, kind: 'class', className, label});
}

function componentDefinition(
  key, category, component, label=title(key.split('.').pop())
) {
  return Object.freeze({
    key,
    category,
    kind: 'component',
    component,
    label,
    license: 'MIT',
    attribution: 'Hugeicons Free Icons 4.3.0',
  });
}

const BUILTIN_DEFINITIONS = [
  ...ENGINE_IDS.map((id)=>definition(
    `engine.${id}`, ICON_CATEGORIES.ENGINE, `icon-engine-type-${id}`,
    title(id)
  )),
  ...Object.entries(OBJECT_CLASSES).map(([name, className])=>definition(
    `object.${name}`, ICON_CATEGORIES.OBJECT, className
  )),
  componentDefinition(
    'object.blob_filter', ICON_CATEGORIES.OBJECT, FilterIcon, 'BLOB Filter'
  ),
  componentDefinition(
    'object.shadow', ICON_CATEGORIES.OBJECT, CopyIcon, 'Database Shadow'
  ),
  componentDefinition(
    'object.storage_file', ICON_CATEGORIES.OBJECT, SaveIcon, 'Storage File'
  ),
  componentDefinition(
    'command.default', ICON_CATEGORIES.ACTION, MenuCircleIcon, 'Command'
  ),
  componentDefinition(
    'tool.schema-compare', ICON_CATEGORIES.TOOL, GitCompareIcon, 'Schema Comparison'
  ),
  componentDefinition(
    'tool.lineage', ICON_CATEGORIES.TOOL, LinkIcon, 'Data Lineage'
  ),
  componentDefinition(
    'tool.quality', ICON_CATEGORIES.TOOL, FilterIcon, 'Data Quality'
  ),
  componentDefinition(
    'tool.contract', ICON_CATEGORIES.TOOL, ShieldUserIcon, 'Data Contract Manager'
  ),
  componentDefinition(
    'tool.etl', ICON_CATEGORIES.TOOL, ArrowAllDirectionIcon, 'ETL Designer'
  ),
  componentDefinition(
    'tool.cdc', ICON_CATEGORIES.TOOL, TransactionIcon, 'CDC Designer'
  ),
  componentDefinition(
    'tool.replication', ICON_CATEGORIES.TOOL, RefreshIcon, 'Replication Topology'
  ),
  componentDefinition(
    'tool.tracing', ICON_CATEGORIES.TOOL, SearchIcon, 'Distributed Tracing'
  ),
  componentDefinition(
    'tool.migration', ICON_CATEGORIES.TOOL, UploadIcon, 'Migration Planning'
  ),
  componentDefinition(
    'tool.api', ICON_CATEGORIES.TOOL, LinkIcon, 'API Designer'
  ),
  componentDefinition(
    'tool.ml-vector', ICON_CATEGORIES.TOOL, SearchIcon, 'ML / Vector Tooling'
  ),
  componentDefinition(
    'tool.ai', ICON_CATEGORIES.TOOL, CommandLineIcon, 'AI Database Assistant'
  ),
  ...Object.entries(ACTION_COMPONENTS).map(([name, component])=>componentDefinition(
    `action.${name}`, ICON_CATEGORIES.ACTION, component
  )),
  ...Object.entries(STATUS_CLASSES).map(([name, className])=>definition(
    `status.${name}`, ICON_CATEGORIES.STATUS, className
  )),
  ...Object.entries(TOOL_CLASSES).map(([name, className])=>definition(
    `tool.${name}`, ICON_CATEGORIES.TOOL, className
  )),
  componentDefinition(
    'tool.data-explorer', ICON_CATEGORIES.TOOL, EyeIcon, 'Data Explorer'
  ),
  componentDefinition(
    'tool.project-explorer', ICON_CATEGORIES.TOOL, FileAddIcon, 'Project Explorer'
  ),
  componentDefinition(
    'object.cube', ICON_CATEGORIES.OBJECT, DatabaseAddIcon, 'Cube'
  ),
  componentDefinition(
    'tool.cube', ICON_CATEGORIES.TOOL, DatabaseAddIcon, 'Cube Designer'
  ),
  componentDefinition(
    'tool.bi', ICON_CATEGORIES.TOOL, SortIcon, 'BI Questions & Dashboards'
  ),
  componentDefinition(
    'tool.screen-mesh', ICON_CATEGORIES.TOOL, EditIcon, 'Screen Mesh Designer'
  ),
  componentDefinition(
    'tool.erd', ICON_CATEGORIES.TOOL, ArrowAllDirectionIcon, 'Diagram Designer'
  ),
  componentDefinition(
    'tool.search', ICON_CATEGORIES.TOOL, SearchIcon, 'Discovery Search'
  ),
  componentDefinition(
    'tool.query', ICON_CATEGORIES.TOOL, CodeIcon, 'Query Tool'
  ),
  componentDefinition(
    'tool.scratchrobin', ICON_CATEGORIES.TOOL, ScratchRobinIcon,
    'ScratchRobin Home'
  ),
];

const builtins = new Map(BUILTIN_DEFINITIONS.map((item)=>[item.key, item]));
const providerDefinitions = new Map();

function normalizeDefinition(input) {
  const key = String(input?.key ?? '').trim().toLowerCase();
  if(!SAFE_KEY.test(key)) {
    throw new TypeError('Icon key must contain only lowercase semantic segments.');
  }
  const category = String(input.category ?? key.split('.')[0]);
  if(!Object.values(ICON_CATEGORIES).includes(category)) {
    throw new TypeError(`Unknown icon category: ${category}`);
  }
  const kind = input.svgUrl ? 'svg' : 'class';
  const className = String(input.className ?? '').trim();
  const svgUrl = String(input.svgUrl ?? '').trim();
  if(kind === 'class' && (!className || !SAFE_CLASS.test(className))) {
    throw new TypeError('Class icon definitions require safe CSS class names.');
  }
  if(kind === 'svg' && !svgUrl) {
    throw new TypeError('SVG icon definitions require a URL.');
  }
  if(kind === 'svg' && !/^(?:\/|https:\/\/)/.test(svgUrl)) {
    throw new TypeError('SVG icon URLs must use an application or HTTPS URL.');
  }
  return Object.freeze({
    key,
    category,
    kind,
    className,
    svgUrl,
    label: String(input.label ?? title(key.split('.').pop())),
    license: String(input.license ?? ''),
    attribution: String(input.attribution ?? ''),
    providerId: String(input.providerId ?? ''),
  });
}

export function registerIconDefinition(input) {
  const item = normalizeDefinition(input);
  if(builtins.has(item.key) || providerDefinitions.has(item.key)) {
    throw new Error(`Icon key is already registered: ${item.key}`);
  }
  providerDefinitions.set(item.key, item);
  return ()=>providerDefinitions.delete(item.key);
}

export function normalizeIconAssignments(input={}) {
  let candidate = input;
  if(typeof candidate === 'string') {
    try {
      candidate = JSON.parse(candidate || '{}');
    } catch {
      return Object.freeze({});
    }
  }
  if(candidate?.schema === ICON_ASSIGNMENT_SCHEMA) {
    candidate = candidate.assignments;
  }
  if(!candidate || Array.isArray(candidate) || typeof candidate !== 'object') {
    return Object.freeze({});
  }
  const assignments = {};
  Object.entries(candidate).forEach(([source, target]) => {
    const normalizedSource = String(source).trim().toLowerCase();
    const normalizedTarget = String(target).trim().toLowerCase();
    if(SAFE_KEY.test(normalizedSource) && SAFE_KEY.test(normalizedTarget) &&
        normalizedSource !== normalizedTarget) {
      assignments[normalizedSource] = normalizedTarget;
    }
  });
  return Object.freeze(assignments);
}

export function mergeIconAssignments(...layers) {
  return Object.freeze(Object.assign({}, ...layers.map(normalizeIconAssignments)));
}

export function createIconAssignmentDocument(assignments={}) {
  return Object.freeze({
    schema: ICON_ASSIGNMENT_SCHEMA,
    assignments: normalizeIconAssignments(assignments),
  });
}

function assignedIconKey(iconKey, input) {
  const assignments = normalizeIconAssignments(input);
  let key = String(iconKey ?? '').trim().toLowerCase();
  const visited = new Set();
  while(assignments[key] && !visited.has(key)) {
    visited.add(key);
    key = assignments[key];
  }
  return key;
}

function familyFallback(key) {
  const match = TAXONOMY_FALLBACKS.find(([prefix])=>key.startsWith(prefix));
  if(match) return builtins.get(match[1]);
  if(key.startsWith('action.') || key.startsWith('command.')) {
    return builtins.get('command.default');
  }
  return builtins.get('object.unknown');
}

export function resolveIconDefinition(iconKey, options={}) {
  let key = assignedIconKey(iconKey, options.assignments);
  if(providerDefinitions.has(key)) return providerDefinitions.get(key);
  if(builtins.has(key)) return builtins.get(key);

  // Provider object kinds use hyphens; the semantic icon registry uses
  // underscores. Preserve exact registered overrides before normalizing.
  if(key.startsWith('object.')) {
    const semanticKey = `object.${key.slice(7).replace(/-/g, '_')}`;
    const assignedSemanticKey = assignedIconKey(semanticKey, options.assignments);
    if(assignedSemanticKey !== semanticKey && assignedSemanticKey !== key) {
      return resolveIconDefinition(assignedSemanticKey, {...options, assignments: undefined});
    }
    if(providerDefinitions.has(semanticKey)) return providerDefinitions.get(semanticKey);
    if(builtins.has(semanticKey)) return builtins.get(semanticKey);
  }

  if(SAFE_CLASS.test(key) && (key.startsWith('icon-') || key.startsWith('fa '))) {
    return Object.freeze({
      key: `legacy.${key.replace(/\s+/g, '.')}`,
      category: options.category ?? ICON_CATEGORIES.OBJECT,
      kind: 'class',
      className: key,
      label: String(options.label ?? title(key)),
      legacy: true,
    });
  }

  if(!key.includes('.')) {
    const objectKey = `object.${key.replace(/-/g, '_')}`;
    if(builtins.has(objectKey)) return builtins.get(objectKey);
  }
  if(key.startsWith('engine.') && SAFE_KEY.test(key)) {
    return definition(key, ICON_CATEGORIES.ENGINE,
      `icon-engine-type-${key.slice(7)}`);
  }
  return familyFallback(key || 'object.unknown');
}

export function listIconDefinitions({category}={}) {
  return Object.freeze([...builtins.values(), ...providerDefinitions.values()]
    .filter((item)=>!category || item.category === category));
}

export function semanticObjectIconKey(objectType) {
  const normalized = String(objectType ?? 'unknown').trim().toLowerCase()
    .replace(/^coll-/, '').replace(/-/g, '_');
  return builtins.has(`object.${normalized}`) ?
    `object.${normalized}` : `object.${normalized || 'unknown'}`;
}

export function semanticEngineIconKey(engineId) {
  return `engine.${String(engineId ?? '').trim().toLowerCase()}`;
}

export function inferActionIconKey(action={}) {
  if(action.iconKey) return action.iconKey;
  const source = [action.id, action.name, action.label, action.description]
    .filter(Boolean).join(' ').toLowerCase().replace(/[^a-z0-9]+/g, ' ');
  const match = ACTION_INFERENCE.find(([, pattern])=>pattern.test(source));
  return match ? `action.${match[0]}` : '';
}
