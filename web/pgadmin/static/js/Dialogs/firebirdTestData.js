/* global BigInt */
// Bounded recipe materialization. Native preparation remains type authority.
const bytes = value => new TextEncoder().encode(JSON.stringify(value)).length;
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
function exactValue(value, depth=0) {
  if (depth > 32) throw new Error('Typed value nesting exceeds 32 levels.');
  if (typeof value === 'number' && !Number.isSafeInteger(value)) throw new Error('Use exact strings or native typed envelopes for fractional and large numeric values.');
  if (value !== null && typeof value === 'object') Object.values(value).forEach(item => exactValue(item, depth + 1));
}
const integer = value => {
  if (typeof value !== 'string' || !/^[+-]?\d{1,39}$/.test(value)) throw new Error('Use exact decimal strings for integer sources.');
  return BigInt(value);
};
function random(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6D2B79F5) >>> 0;
    let value = Math.imul(state ^ state >>> 15, 1 | state);
    value ^= value + Math.imul(value ^ value >>> 7, 61 | value);
    return ((value ^ value >>> 14) >>> 0) / 4294967296;
  };
}
export function parseRecipe(source) {
  if (typeof source !== 'string' || new TextEncoder().encode(source).length > 1024 * 1024) throw new Error('Recipe exceeds 1 MiB.');
  const recipe = JSON.parse(source);
  if (recipe?.format !== 'scratchrobin.firebird.test-data@1' || !Number.isInteger(recipe.seed) || recipe.seed < 0 || recipe.seed > 4294967295 ||
      !Array.isArray(recipe.tables) || !recipe.tables.length || recipe.tables.length > 32) throw new Error('Invalid Firebird recipe format, seed or table count.');
  return recipe;
}
export function materializeTestData(recipe, catalogs) {
  parseRecipe(JSON.stringify(recipe));
  const selected = new Map(), dependencies = new Map();
  let total = 0;
  for (const entry of recipe.tables) {
    const catalog = own(catalogs, entry.table) ? catalogs[entry.table] : null;
    if (!catalog || selected.has(entry.table) || !Number.isInteger(entry.count) || entry.count < 1 || entry.count > 1000 ||
        !entry.columns || typeof entry.columns !== 'object' || Array.isArray(entry.columns)) throw new Error('Unknown/duplicate table or invalid count/column sources.');
    total += entry.count;
    if (total > 5000) throw new Error('Recipe exceeds 5000 rows.');
    const names = new Map(catalog.columns.map(column => [column.name, column]));
    for (const [name, source] of Object.entries(entry.columns)) {
      if (!names.has(name) || names.get(name).insertable === false || !source || typeof source !== 'object' || Array.isArray(source)) throw new Error('Source must identify an admitted insertable column.');
      if (!['default', 'constant', 'sequential', 'random-integer', 'choice', 'file', 'existing', 'generated'].includes(source.kind)) throw new Error('Unknown data source.');
      const rate = source.nullPercent ?? 0;
      if (typeof rate !== 'number' || !Number.isFinite(rate) || rate < 0 || rate > 100) throw new Error('NULL percentage must be 0–100.');
      if (source.kind === 'constant' && !own(source, 'value')) throw new Error('Constant source requires a value.');
      if (source.kind === 'constant') exactValue(source.value);
      if (source.kind === 'sequential') {integer(source.start); integer(source.step);}
      if (source.kind === 'random-integer') {
        const width = integer(source.max) - integer(source.min) + 1n;
        if (width < 1n || width > 4294967296n) throw new Error('Random integer range must contain 1–2^32 values.');
      }
      if (['choice', 'file'].includes(source.kind) && (!Array.isArray(source.values) || !source.values.length || source.values.length > 1000)) throw new Error('Choice/file source requires 1–1000 typed values.');
      if (['choice', 'file'].includes(source.kind)) exactValue(source.values);
      if (source.kind === 'existing') {
        const sample = own(catalogs, source.table) ? catalogs[source.table] : null;
        if (!sample || !sample.columns.some(column => column.name === source.column) || !sample.rows.length || sample.rows.some(row => !own(row.values, source.column))) throw new Error('Existing source needs an available nonempty column sample.');
      }
    }
    selected.set(entry.table, entry);
  }
  for (const [name, entry] of selected) {
    const required = new Set();
    for (const source of Object.values(entry.columns)) {
      if (source.kind !== 'generated' || source.nullPercent === 100) continue;
      const parent = selected.get(source.table);
      if (!parent || !own(parent.columns, source.column) || parent.columns[source.column].kind === 'default') throw new Error('Generated source must reference an explicitly generated column.');
      required.add(source.table);
    }
    for (const key of catalogs[name].foreignKeys || []) {
      if (!selected.has(key.table)) continue;
      // Existing values or explicit all-NULL values do not depend on new rows.
      const independent = key.columns.every(column => {
        const source = entry.columns[column];
        return source && (source.kind === 'existing' || source.nullPercent === 100 || (source.kind === 'constant' && source.value === null));
      });
      if (!independent) required.add(key.table);
    }
    dependencies.set(name, required);
  }
  const order = [];
  while (dependencies.size) {
    const ready = [...dependencies].filter(([, required]) => !required.size).map(([name]) => name).sort();
    if (!ready.length) throw new Error('Cyclic generated/foreign-key dependencies. Use explicit NULL or existing values to break the cycle. No rows were dispatched.');
    order.push(...ready);
    ready.forEach(name => dependencies.delete(name));
    dependencies.forEach(required => ready.forEach(name => required.delete(name)));
  }
  const rng = random(recipe.seed), generated = Object.create(null), operations = [];
  const result = {format: 'scratchrobin.firebird.test-data-preview@1', seed: recipe.seed, order, operations};
  let outputBytes = bytes(result);
  for (const name of order) {
    const entry = selected.get(name), rows = [];
    for (let index = 0; index < entry.count; index++) {
      const values = Object.create(null);
      for (const [column, source] of Object.entries(entry.columns)) {
        if (source.kind === 'default') continue;
        let value;
        if (rng() * 100 < (source.nullPercent ?? 0)) value = null;
        else if (source.kind === 'constant') value = source.value;
        else if (source.kind === 'sequential') value = String(integer(source.start) + BigInt(index) * integer(source.step));
        else if (source.kind === 'random-integer') value = String(integer(source.min) + BigInt(Math.floor(rng() * Number(integer(source.max) - integer(source.min) + 1n))));
        else if (['choice', 'file'].includes(source.kind)) value = source.values[source.kind === 'file' ? index % source.values.length : Math.floor(rng() * source.values.length)];
        else if (source.kind === 'existing') value = catalogs[source.table].rows[index % catalogs[source.table].rows.length].values[source.column];
        else value = generated[source.table][index % generated[source.table].length][source.column];
        if (value === undefined) throw new Error('Generated value is unavailable.');
        values[column] = value;
      }
      exactValue(values);
      const operation = {table: name, row: index, values};
      outputBytes += bytes(operation) + 1;
      if (outputBytes > 4 * 1024 * 1024) throw new Error('Materialized preview exceeds 4 MiB.');
      rows.push(values);
      operations.push(operation);
    }
    generated[name] = rows;
  }
  return result;
}

export async function stageTestData({preview, catalogs, post, sessionId, databaseTargetId, stopped, onProgress}) {
  let staged = 0;
  for (const operation of preview.operations) {
    if (stopped()) return {state: 'stopped', staged, dispatched: staged};
    const request = {resource_kind: 'table', operation_id: 'insert',
      target_resource: catalogs[operation.table].resource, draft: {values: operation.values, options: {},
        ...(Object.prototype.hasOwnProperty.call(operation, 'override_identity') ? {override_identity: operation.override_identity} : {})},
      session_id: sessionId, database_target_id: databaseTargetId};
    try {
      const validation = await post({action: 'visual_admin_validate', request});
      if (!validation.valid) throw new Error(validation.errors.map(item => item.message).join(' '));
      const plan = await post({action: 'visual_admin_plan', request});
      if (plan.state !== 'ready' || !plan.execution_available) throw new Error('Native insert plan is blocked.');
      if (stopped()) return {state: 'stopped', staged, dispatched: staged};
      const result = await post({action: 'visual_admin_apply', request: {
        plan_id: plan.plan_id, plan_digest: plan.plan_digest, confirmed: true,
        session_id: sessionId, database_target_id: databaseTargetId}});
      if (result?.provider_result?.staged_in_provider_session !== true) throw new Error('Native staged-row outcome was not confirmed.');
      staged++;
      onProgress(staged);
    } catch {
      // Do not leak arbitrary provider error text or replay an uncertain row.
      return {state: 'stopped_after_error', staged, failedTable: operation.table, failedRow: operation.row,
        message: 'Dispatch stopped. The last row may be pending; inspect the native transaction and explicitly roll back or commit. Do not retry this preview.'};
    }
  }
  return {state: 'staged', staged, dispatched: staged};
}

export function tableForeignKeys(resource) {
  const native = resource.native || resource.extensions?.firebird?.native || {};
  return (native.constraints || []).filter(item => item.constraint_type === 'FOREIGN KEY').map(item => {
    const index = (native.indexes || []).find(value => value.name === item.index_name);
    if (!index?.segments?.length) throw new Error('Foreign-key column metadata is incomplete. Refresh the catalog.');
    return {table: item.referenced_relation, columns: [...index.segments].sort((a, b) => Number(a.position) - Number(b.position)).map(value => value.field_name)};
  });
}

export function generatorTable(resource) {
  const native = resource.native || resource.extensions?.firebird?.native || {};
  return resource.resource_kind === 'table' && native.system_object !== true;
}
