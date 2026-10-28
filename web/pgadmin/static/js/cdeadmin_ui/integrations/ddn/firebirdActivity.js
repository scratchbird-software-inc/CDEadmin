import {observationTable} from './source.js';
// Native values from an authorized retained collector snapshot. No query execution.
export const FIREBIRD_ACTIVITY = Object.freeze([
  {id: 'findings', label: 'Policy attention findings', fields: ['code', 'severity', 'reason', 'value', 'threshold', 'observed_at']},
  {id: 'attachment_details', label: 'Attachments', fields: ['attachment_id', 'user', 'role',
    'remote_protocol', 'remote_address', 'timestamp', 'state', 'system_flag']},
  {id: 'transaction_details', label: 'Transactions', fields: ['transaction_id', 'attachment_id',
    'timestamp', 'state', 'isolation_mode', 'read_only', 'lock_timeout', 'auto_commit', 'auto_undo']},
  {id: 'statement_details', label: 'Statements', fields: ['statement_id', 'attachment_id',
    'transaction_id', 'timestamp', 'state', 'statement_timeout', 'compiled_statement_id']},
  {id: 'compiled_details', label: 'Compiled statement identities', fields: [
    'compiled_statement_id', 'object_name', 'object_type', 'package_name', 'stat_id']},
  {id: 'compiled_counts', label: 'Visible compiled statement count', fields: ['count']},
  {id: 'wire_counts', label: 'Visible wire encryption coverage', fields: ['transport', 'encrypted', 'count']},
  {id: 'protection_details', label: 'Backup, encryption and replica state', fields: [
    'crypt_state', 'crypt_page', 'replica_mode', 'backup_state', 'sec_database']},
  {id: 'role_details', label: 'Visible roles', fields: ['role_name', 'owner_name', 'system_flag']},
  {id: 'crypt_identity', label: 'Native encryption plugin and key names', fields: ['plugin_name', 'key_name']},
  {id: 'creator_details', label: 'Visible database creators', fields: ['user', 'user_type']},
  {id: 'global_mapping_details', label: 'Visible global authentication mappings', fields: ['map_name',
    'map_using', 'map_plugin', 'map_db', 'map_from_type', 'map_from', 'map_to_type', 'map_to']},
  {id: 'grant_details', label: 'Visible grants', fields: ['user', 'grantor', 'privilege',
    'grant_option', 'relation_name', 'field_name', 'user_type', 'object_type']},
  {id: 'mapping_details', label: 'Local authentication mappings', fields: ['map_name',
    'map_using', 'map_plugin', 'map_db', 'map_from_type', 'map_from', 'map_to_type', 'map_to']},
  {id: 'client_details', label: 'Client transport', fields: ['attachment_id',
    'remote_protocol', 'auth_method', 'wire_encrypted', 'wire_compressed',
    'wire_crypt_plugin', 'client_version', 'remote_version']},
  {id: 'file_details', label: 'Secondary files and shadows', fields: ['file_name',
    'file_sequence', 'file_start', 'file_length', 'file_flags', 'shadow_number']},
  {id: 'page_inventory', label: 'Native allocated page inventory', fields: ['pages_used', 'pages_free']},
  {id: 'backup_details', label: 'Native physical backup history', fields: ['backup_id',
    'timestamp', 'backup_level', 'guid', 'scn', 'file_name']},
  {id: 'publication_details', label: 'Publications', fields: ['publication_name',
    'owner_name', 'system_flag', 'active_flag', 'auto_enable']},
  {id: 'publication_table_details', label: 'Publication tables', fields: [
    'publication_name', 'table_name']},
  {id: 'security_counts', label: 'Visible security inventory', fields: ['kind', 'count']},
  {id: 'user_counts', label: 'Visible user plugin counts', fields: ['plugin', 'active', 'admin', 'count']},
  {id: 'schema_counts', label: 'Table and view counts', fields: ['kind', 'system_flag', 'count']},
  {id: 'schema_health', label: 'Schema health observations', fields: ['kind', 'name', 'condition']},
  {id: 'configuration_details', label: 'Effective operational configuration', fields: [
    'config_name', 'config_value', 'config_default', 'config_is_set', 'config_source']},
  {id: 'table_details', label: 'Table record activity (name order)', fields: [
    'table_name', 'record_stat_id', 'rate_status', 'rate_gap_reason',
    'record_seq_reads_per_second', 'record_idx_reads_per_second',
    'record_inserts_per_second', 'record_updates_per_second', 'record_deletes_per_second',
    'record_backouts_per_second', 'record_purges_per_second', 'record_expunges_per_second',
    'record_waits_per_second', 'record_conflicts_per_second', 'backversion_reads_per_second']},
]);
export function firebirdActivityFiles(sample, category, filter='') {
  const selection = FIREBIRD_ACTIVITY.find((item) => item.id === category);
  if(!selection) throw new Error('Unsupported activity category.');
  const group = category === 'findings' && ['available', 'partial'].includes(sample?.status) ?
    {status: 'available', values: {rows: sample.findings || []}} : sample?.groups?.[category];
  const needle = filter.trim().toLocaleLowerCase();
  const rows = group?.status === 'available' ? (group.values?.rows || []).slice(0, 100)
    .filter((row) => !needle || selection.fields.some((field) => String(row[field] ?? '').toLocaleLowerCase().includes(needle))) : [];
  const message = group?.status === 'available' ? (needle ? 'No matching captured rows' : 'No visible rows in this snapshot') : 'Source unavailable';
  return observationTable('activity.ddn','activity',selection.label,rows,selection.fields,'scratchrobin.firebird.activity',message);
}
