/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Smart OS/environment defaults, determinable option lists, and sample
 * placeholder text for descriptor-driven forms. Kept completely engine-neutral
 * so every database family form benefits without engine-specific UI branches.
 */

const TIME_ZONE_FIELD_IDS = new Set([
  'session_time_zone',
  'time_zone',
  'timezone',
  'default_time_zone',
]);

const CHARSET_FIELD_IDS = new Set([
  'charset',
  'character_set',
  'client_encoding',
  'connection_charset',
]);

const FALLBACK_IANA_TIME_ZONES = [
  'UTC',
  'America/New_York',
  'America/Toronto',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Vancouver',
  'America/Sao_Paulo',
  'Europe/London',
  'Europe/Dublin',
  'Europe/Paris',
  'Europe/Berlin',
  'Europe/Madrid',
  'Europe/Rome',
  'Europe/Stockholm',
  'Europe/Warsaw',
  'Europe/Athens',
  'Europe/Kyiv',
  'Asia/Dubai',
  'Asia/Kolkata',
  'Asia/Singapore',
  'Asia/Shanghai',
  'Asia/Tokyo',
  'Asia/Seoul',
  'Australia/Sydney',
  'Pacific/Auckland',
];

const COMMON_CHARSETS = [
  {value: 'UTF8', label: 'UTF8'},
  {value: 'ISO8859_1', label: 'ISO8859_1'},
  {value: 'WIN1252', label: 'WIN1252'},
  {value: 'ASCII', label: 'ASCII'},
  {value: 'LATIN1', label: 'LATIN1'},
  {value: 'OCTETS', label: 'OCTETS'},
  {value: 'NONE', label: 'NONE'},
];

let cachedTimeZoneOptions = null;
let cachedTimeZoneKey = null;

/** Resolve the operating system / host runtime IANA time zone. */
export function getSystemTimeZone() {
  try {
    const resolved = Intl?.DateTimeFormat?.()?.resolvedOptions?.()?.timeZone;
    if (typeof resolved === 'string' && resolved.trim().length > 0) {
      return resolved.trim();
    }
  } catch {
    // Fall back cleanly when Intl timeZone inspection is unavailable.
  }
  return 'UTC';
}

/** Build determinable time zone options with the OS local time zone first. */
export function getSystemTimeZoneOptions() {
  const osTimeZone = getSystemTimeZone();
  if (cachedTimeZoneOptions && cachedTimeZoneKey === osTimeZone) {
    return cachedTimeZoneOptions;
  }
  let zones = FALLBACK_IANA_TIME_ZONES;
  try {
    if (typeof Intl?.supportedValuesOf === 'function') {
      const supported = Intl.supportedValuesOf('timeZone');
      if (Array.isArray(supported) && supported.length > 0) {
        zones = supported;
      }
    }
  } catch {
    // Keep curated IANA list when Intl.supportedValuesOf is unavailable.
  }

  const seen = new Set();
  const options = [];
  const pushZone = (zone, label = zone) => {
    if (!zone || seen.has(zone)) return;
    seen.add(zone);
    options.push({value: zone, label});
  };

  pushZone(osTimeZone, `${osTimeZone} (OS local)`);
  pushZone('UTC', 'UTC');
  for (const zone of zones) {
    pushZone(zone, zone);
  }

  cachedTimeZoneKey = osTimeZone;
  cachedTimeZoneOptions = options;
  return options;
}

export function isTimeZoneField(field) {
  return Boolean(
    field &&
      field.control === 'text' &&
      !Array.isArray(field.options) &&
      TIME_ZONE_FIELD_IDS.has(field.field_id)
  );
}

export function isCharsetField(field) {
  return Boolean(
    field &&
      field.control === 'text' &&
      !Array.isArray(field.options) &&
      CHARSET_FIELD_IDS.has(field.field_id)
  );
}

/** Return an auto-populated value when the environment determines a sensible default. */
export function resolveSmartDefault(field) {
  if (!field) return undefined;
  if (isTimeZoneField(field)) {
    return getSystemTimeZone();
  }
  return undefined;
}

/** Return determinable dropdown choices for a field when available. */
export function resolveSmartOptions(field, descriptorOptions = []) {
  if (Array.isArray(descriptorOptions) && descriptorOptions.length > 0) {
    return descriptorOptions;
  }
  if (isTimeZoneField(field)) {
    return getSystemTimeZoneOptions();
  }
  if (isCharsetField(field)) {
    return COMMON_CHARSETS;
  }
  return descriptorOptions;
}

const SAMPLE_PLACEHOLDERS_BY_ID = {
  name: 'e.g. Production database',
  host: 'e.g. localhost or 10.0.0.15',
  hostaddr: 'e.g. 127.0.0.1',
  port: 'e.g. 5432',
  username: 'e.g. admin',
  user: 'e.g. admin',
  role: 'e.g. RDB$ADMIN',
  database: 'e.g. app_data',
  db: 'e.g. app_data',
  maintenance_db: 'e.g. postgres',
  service: 'e.g. pg_prod',
  database_create_root: 'e.g. /var/lib/db/data',
  service_expected_database: 'e.g. employee',
  charset: 'e.g. UTF8',
  character_set: 'e.g. UTF8',
  client_encoding: 'e.g. UTF8',
  collation: 'e.g. UNICODE_CI_AI',
  wire_crypt_plugins: 'e.g. ChaCha64, ChaCha, Arc4',
  remote_crypt_key_type: 'e.g. Symmetric',
  key_plugin: 'e.g. KeyHolder',
  ssl_ca: 'e.g. /etc/ssl/certs/ca.pem',
  ssl_root_cert: 'e.g. /etc/ssl/certs/ca.pem',
  ssl_cert: 'e.g. /etc/ssl/certs/client.crt',
  ssl_key: 'e.g. /etc/ssl/private/client.key',
  ssl_crl: 'e.g. /etc/ssl/certs/revoked.crl',
  ssl_crl_dir: 'e.g. /etc/ssl/crl',
  connect_timeout: 'e.g. 10',
  connection_timeout: 'e.g. 10',
  timeout: 'e.g. 10',
  dummy_packet_interval: 'e.g. 60',
  cache_size: 'e.g. 2048',
  page_buffers: 'e.g. 2048',
  parallel_workers: 'e.g. 2',
  schema: 'e.g. public',
  owner: 'e.g. app_owner',
  tablespace: 'e.g. pg_default',
  comment: 'e.g. Optional notes or purpose…',
  description: 'e.g. Optional notes or purpose…',
};

/** Resolve greyed-out sample placeholder text for text/number/picker inputs. */
export function resolveSmartPlaceholder(field) {
  if (!field) return undefined;
  if (typeof field.placeholder === 'string' && field.placeholder.length > 0) {
    return field.placeholder;
  }
  if (isTimeZoneField(field)) {
    return `e.g. ${getSystemTimeZone()}`;
  }
  if (field.default !== undefined && field.default !== null && String(field.default) !== '') {
    if (field.control === 'text' || field.control === 'number' || field.control === 'file') {
      return `e.g. ${field.default}`;
    }
  }
  const byId = SAMPLE_PLACEHOLDERS_BY_ID[field.field_id];
  if (byId) return byId;
  if (field.control === 'file') {
    return 'e.g. /path/to/file';
  }
  if (field.control === 'password' || field.control === 'secret-reference') {
    return 'Enter secret…';
  }
  if (field.control === 'number') {
    if (typeof field.min === 'number') return `e.g. ${field.min}`;
    return 'e.g. 0';
  }
  if (field.control === 'reference') {
    return `Select ${String(field.label || 'item').toLowerCase()}…`;
  }
  return undefined;
}
