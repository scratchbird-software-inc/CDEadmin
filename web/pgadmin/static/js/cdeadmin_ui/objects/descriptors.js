/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Pure descriptor logic for the object editor and operation dialog.
 *
 * Mirrors web/pgadmin/cdeadmin/ui_descriptors/__init__.py so the same
 * resolution can run against raw descriptor JSON in tests and against the
 * server bundle at runtime. Nothing here knows an engine by name; every
 * difference comes from the descriptor files (design principle 4).
 */

export const SHELL_PRIMITIVES = new Set([
  'sql_preview', 'data_grid', 'readonly_grid', 'readonly_groups',
]);

export const MENU_CATEGORIES = [
  {category: 'create', title: 'Create'},
  {category: 'open', title: 'Open'},
  {category: 'lifecycle', title: 'Definition and lifecycle'},
  {category: 'maintenance', title: 'Maintenance'},
  {category: 'backup_restore', title: 'Backup and restore'},
  {category: 'replication', title: 'Replication and availability'},
  {category: 'security', title: 'Security'},
  {category: 'diagnostics', title: 'Diagnostics'},
  {category: 'refresh', title: 'Refresh'},
];

const TIER1_MENU = {
  create: 'create', alter: 'lifecycle', rename: 'lifecycle', drop: 'lifecycle',
  comment: 'lifecycle', truncate: 'lifecycle', grant: 'security', revoke: 'security',
};

/** Merge a family skeleton and an engine form into render order. */
export function resolveForm(family, form) {
  if(!family) throw new Error(`unknown family ${form?.family}`);
  const omitted = Object.fromEntries((form.omitted_tabs || []).map((row) => [row.tab, row.reason]));
  const byTab = {};
  for(const field of form.fields || []) {
    const tab = field.tab || family.tabs[0].tab;
    (byTab[tab] = byTab[tab] || []).push(field);
  }
  const tabs = [];
  for(const tab of family.tabs) {
    const fields = byTab[tab.tab] || [];
    const shellTab = SHELL_PRIMITIVES.has(tab.primitive);
    if((!fields.length && !shellTab) || omitted[tab.tab]) continue;
    tabs.push({
      tab: tab.tab,
      title: tab.tab === 'Engine' ? (form.engine_tab_title || 'Engine') : tab.tab,
      primitive: tab.primitive,
      required: Boolean(tab.required),
      fields,
      grid_columns: tab.grid_columns || [],
      nested: tab.nested || [],
      notes: tab.notes,
    });
  }
  const present = new Set(tabs.map((tab) => tab.tab));
  return {
    ...form,
    tabs,
    family_title: family.title || form.family,
    family_tabs: family.tabs.map((tab) => tab.tab),
    missing_required_tabs: family.tabs
      .filter((tab) => tab.required && !present.has(tab.tab) && !omitted[tab.tab] &&
        tab.primitive !== 'sql_preview')
      .map((tab) => tab.tab),
  };
}

/** Build the same bundle shape the server serves, from raw descriptor files. */
export function resolveBundle({engine, families, capabilities, operations=[], navigator={}, forms={}, options={dialect: {}, catalog: {}}}) {
  const resolvedForms = {};
  for(const [familyId, form] of Object.entries(forms)) {
    resolvedForms[familyId] = resolveForm(families[familyId], form);
  }
  const opsByKind = {};
  for(const op of operations) (opsByKind[op.resource_kind] = opsByKind[op.resource_kind] || []).push(op);
  const kinds = {};
  for(const kind of capabilities.kinds || []) {
    const form = kind.family === 'engine_object' ? null : resolvedForms[kind.family];
    kinds[kind.resource_kind] = {
      resource_kind: kind.resource_kind,
      family: kind.family,
      variant: kind.variant || null,
      title: kind.title || null,
      form_status: form?.status || null,
      tier1: (kind.operations || []).map((op) => op.operation_id),
      operations: opsByKind[kind.resource_kind] || [],
    };
  }
  return {schema: 'cdeadmin.ui-bundle.v1', engine, capabilities, operations, navigator, options,
    forms: resolvedForms, kinds};
}

/** The resolved form that edits a resource kind, or null when none is declared. */
export function formForKind(bundle, resourceKind) {
  const kind = bundle?.kinds?.[resourceKind];
  if(!kind || kind.family === 'engine_object') return null;
  return bundle.forms?.[kind.family] || null;
}

/** Whether the shell should open the family editor for this kind. */
export function editorAvailable(bundle, resourceKind) {
  const form = formForKind(bundle, resourceKind);
  return Boolean(form && form.status !== 'pending' && form.tabs.some((tab) => tab.fields.length));
}

/** Evaluate a descriptor visible_when against the current draft. */
export function fieldVisible(field, draft={}) {
  const rule = field?.visible_when;
  if(!rule || !rule.field) return true;
  const value = draft[rule.field];
  if(Object.hasOwn(rule, 'equals')) return value === rule.equals;
  if(Array.isArray(rule.in)) return rule.in.includes(value);
  if(Object.hasOwn(rule, 'truthy')) return Boolean(value) === Boolean(rule.truthy);
  return true;
}

/** Fields of a tab that apply in this mode and are visible for the draft. */
export function activeFields(fields, {mode='create', draft={}}={}) {
  return (fields || []).filter((field) =>
    (!field.modes || field.modes.includes(mode)) && fieldVisible(field, draft));
}

function readPath(root, path) {
  let node = root;
  for(const part of path) {
    if(node == null) return undefined;
    node = node[part];
  }
  return node;
}

/**
 * Options for a select/multiselect/reference field.
 *
 * `context` carries whatever the host can supply: `dialect` (type lists,
 * collations, privileges), `catalog` (tablespaces, databases), `target`
 * (columns of the object being edited), `resources` (for reference pickers,
 * keyed by kind). `draft` resolves ["draft","columns"] to the names in the
 * current Columns grid. Path segments starting with `$` are substituted
 * from the draft (`$resource_kind`, `$object_type`).
 */
export function fieldOptions(field, {context={}, draft={}, resourceKind}={}) {
  if(Array.isArray(field.options) && field.options.length) return field.options;
  const path = field.option_values_path;
  if(Array.isArray(path) && path.length) {
    const [head, ...rest] = path;
    const substituted = rest.map((part) =>
      part === '$resource_kind' ? resourceKind : part.startsWith('$') ? draft[part.slice(1)] : part);
    let values;
    if(head === 'draft') {
      const rows = draft[substituted[0]];
      values = Array.isArray(rows) ? rows.map((row) => row?.name ?? row).filter(Boolean) : [];
    } else {
      values = readPath(context[head], substituted);
    }
    if(Array.isArray(values)) {
      return values.map((item) => typeof item === 'object' && item !== null ?
        {value: item.value ?? item.name ?? item.resource_id, label: item.label ?? item.display_name ?? item.name ?? String(item.value)} :
        {value: item, label: String(item)});
    }
  }
  if(field.control === 'reference' && field.reference_kind) {
    const rows = context.resources?.[field.reference_kind] || [];
    // Providers take object references as dotted display paths (schema.name).
    return rows.map((row) => ({
      value: Array.isArray(row.display_path) && row.display_path.length ? row.display_path.join('.') :
        row.display_name ?? row.resource_id ?? row.value ?? row,
      label: row.display_name ?? row.label ?? String(row)}));
  }
  return [];
}

/** Initial draft for a form in a mode, from field defaults and an existing record. */
export function initialDraft(form, {mode='create', record={}}={}) {
  const draft = {};
  for(const tab of form.tabs || []) {
    for(const field of tab.fields) {
      if(field.modes && !field.modes.includes(mode)) continue;
      const backendId = field.backend_field_id || field.field_id;
      let existing = recordValue(field, record);
      if(existing === undefined) existing = readDotted(record, backendId);
      if(existing !== undefined) {
        draft[field.field_id] = field.control === 'grid' && Array.isArray(existing) ?
          existing.map((row, index) => gridRowFromRecord(field, row, index)) : existing;
      }
      else if(field.default !== undefined) draft[field.field_id] = field.default;
      else if(field.control === 'grid') draft[field.field_id] = [];
      else if(field.control === 'boolean') draft[field.field_id] = false;
    }
  }
  return draft;
}

/**
 * Re-key a flat backend payload (the servers API properties response, whose keys are
 * the form's backend_field_id) by form field_id, so initialDraft can pre-fill an edit.
 * JSON-text values arrive as strings for grid/keyvalue controls and are decoded.
 */
export function recordFromBackend(form, data={}) {
  const record = {};
  for(const tab of form.tabs || []) {
    for(const field of tab.fields) {
      const target = field.backend_field_id || field.field_id;
      let value = Object.hasOwn(data, target) ? data[target] : readDotted(data, target);
      if(value === undefined || value === null) continue;
      if(['grid', 'keyvalue'].includes(field.control) && typeof value === 'string') {
        try {
          value = JSON.parse(value);
        } catch {
          continue;
        }
      }
      record[field.field_id] = value;
    }
  }
  return record;
}

// Record truthiness: catalog flags arrive as '0'/'1' strings too.
const EMPTYISH = new Set([null, undefined, '', 0, '0', false, 'false', 'FALSE']);

/**
 * The record value that pre-fills a field or grid column, or undefined.
 * Order: record_derive rule, record_key (dotted path allowed), field_id.
 */
export function recordValue(field, record) {
  if(!record || typeof record !== 'object') return undefined;
  if(field.record_derive) {
    for(const rule of field.record_derive.cases || []) {
      const found = readPath(record, rule.key.split('.'));
      if('equals' in rule) {
        if(found !== undefined && found === rule.equals) return rule.value;
      } else if('matches' in rule) {
        if(typeof found === 'string' && new RegExp(rule.matches, 'si').test(found)) return rule.value;
      } else if(!EMPTYISH.has(found) === (rule.truthy ?? true)) {
        return rule.value;
      }
    }
    return field.record_derive.default;
  }
  let value = field.record_key ? readPath(record, field.record_key.split('.')) : undefined;
  if(value === undefined && Object.hasOwn(record, field.field_id)) value = record[field.field_id];
  if(value === undefined) return undefined;
  if(field.record_filter && Array.isArray(value)) {
    const rule = field.record_filter;
    value = value.filter((row) => row && typeof row === 'object' && readPath(row, rule.key.split('.')) === rule.equals);
  }
  if(field.record_pluck && Array.isArray(value)) {
    value = value.map((row) => (row && typeof row === 'object') ? row[field.record_pluck] : row);
  }
  if(field.record_pattern && typeof value === 'string') {
    const match = new RegExp(field.record_pattern, 'si').exec(value);
    if(match) value = match[1];
  }
  if(field.control === 'multiselect' && typeof value === 'string') value = value ? [value] : [];
  return field.record_truthy ? !EMPTYISH.has(value) : value;
}

/** A grid row pre-filled from an inspected record row, keyed by column record_key. */
export function gridRowFromRecord(field, row, index) {
  if(field.item_kind === 'string' && (typeof row !== 'object' || row === null)) {
    return {[field.columns?.[0]?.field_id || 'value']: row, _id: `${index}`};
  }
  if(!row || typeof row !== 'object') return row;
  const out = {...row};
  for(const column of field.columns || []) {
    const found = recordValue(column, row);
    if(found !== undefined) out[column.field_id] = found;
  }
  if(!out._id) out._id = `${index}`;
  return out;
}

function readDotted(record, path) {
  if(!path || !path.includes('.')) return undefined;
  return readPath(record, path.split('.'));
}

/** Required-field validation across visible fields; returns {field_id: message}. */
export function validateDraft(form, draft, {mode='create', baseline=null}={}) {
  const errors = {};
  for(const tab of form.tabs || []) {
    for(const field of activeFields(tab.fields, {mode, draft})) {
      if(field.readonly || field.available === false) continue;
      const value = draft[field.field_id];
      const empty = value === undefined || value === null || value === '' ||
        (Array.isArray(value) && value.length === 0);
      // In alter mode a required field the provider did not report (and the
      // user has not touched) is not the user's omission; only changes are checked.
      const untouched = mode === 'alter' && baseline !== null &&
        JSON.stringify(value ?? null) === JSON.stringify(baseline[field.field_id] ?? null);
      if(field.required && empty && !untouched) errors[field.field_id] = `${field.label} is required.`;
      if(field.control === 'number' && !empty && Number.isNaN(Number(value))) {
        errors[field.field_id] = `${field.label} must be a number.`;
      }
      if(field.control === 'grid' && Array.isArray(value)) {
        value.forEach((row, index) => {
          for(const column of field.columns || []) {
            if(column.required && (row?.[column.field_id] === undefined || row?.[column.field_id] === '')) {
              errors[`${field.field_id}[${index}].${column.field_id}`] = `${column.label} is required in row ${index + 1}.`;
            }
          }
        });
      }
    }
  }
  return errors;
}

/**
 * Diff two column grids into the add/drop/rename lists an ALTER path takes.
 * Rows are matched by a stable `_id` the editor assigns when it loads a
 * record (falling back to name); a changed name on a matched row is a rename.
 */
export function diffColumns(before=[], after=[]) {
  const key = (row, index) => row?._id ?? `${row?.name ?? ''}#${index}`;
  const beforeByKey = new Map(before.map((row, index) => [key(row, index), row]));
  const afterKeys = new Set(after.map((row, index) => key(row, index)));
  const add_columns = [], rename_columns = [];
  for(const [index, row] of after.entries()) {
    const previous = beforeByKey.get(key(row, index));
    if(!previous) {
      add_columns.push(stripMeta(row));
    } else if(previous.name !== row.name && row.name) {
      rename_columns.push({from: previous.name, to: row.name});
    }
  }
  const drop_columns = before.filter((row, index) => !afterKeys.has(key(row, index))).map((row) => row.name);
  return {add_columns, drop_columns, rename_columns};
}

function stripMeta(row) {
  const copy = {};
  for(const [key, value] of Object.entries(row)) {
    if(key === '_id' || value === undefined || value === null || value === '') continue;
    copy[key] = value;
  }
  return copy;
}

/** Map a UI draft onto the provider's field ids (backend_field_id) for plan/apply. */
export function toBackendDraft(form, draft, {mode='create', baseline=null}={}) {
  const out = {};
  for(const tab of form.tabs || []) {
    for(const field of activeFields(tab.fields, {mode, draft})) {
      if(!Object.hasOwn(draft, field.field_id) || field.ui_only) continue;
      let value = draft[field.field_id];
      if(field.wrap_list && !Array.isArray(value)) value = (value === undefined || value === null || value === '') ? [] : [value];
      if(mode === 'alter' && field.control === 'grid' && field.field_id === 'columns' && baseline) {
        // The Columns grid diff is what ALTER paths consume (design 6.1).
        const diff = diffColumns(baseline.columns || [], value || []);
        if(diff.add_columns.length) out.add_columns = diff.add_columns;
        if(diff.drop_columns.length) out.drop_columns = diff.drop_columns;
        if(diff.rename_columns.length) out.rename_columns = diff.rename_columns;
        continue;
      }
      if(mode === 'alter' && baseline && JSON.stringify(value ?? null) === JSON.stringify(baseline[field.field_id] ?? null)) {
        continue; // unchanged fields are not part of the ALTER set, required or not (the target names the object)
      }
      const target = field.backend_field_id || field.field_id;
      const bracket = target.match(/^([a-z0-9_]+)\[([a-z0-9_]+)=([a-z0-9_]+)\]$/i);
      if(bracket) {
        const [, list, key, discriminator] = bracket;
        out[list] = (out[list] || []).concat((Array.isArray(value) ? value : []).map((row) => ({[key]: discriminator, ...stripMeta(row)})));
      } else if(target.includes('.')) {
        const parts = target.split('.');
        let node = out;
        for(const part of parts.slice(0, -1)) node = (node[part] = node[part] || {});
        node[parts.at(-1)] = value;
      } else if(field.control === 'grid' && field.item_kind === 'string') {
        const column = field.columns?.[0]?.field_id || 'value';
        out[target] = (Array.isArray(value) ? value : []).map((row) => (row && typeof row === 'object') ? row[column] : row)
          .filter((item) => item !== undefined && item !== null && item !== '');
      } else {
        out[target] = Array.isArray(value) ? value.map((row) => (row && typeof row === 'object' && '_id' in row) ? stripMeta(row) : row) : value;
      }
    }
  }
  return out;
}

/** Categorised menu for a resource kind, in the fixed category order. */
export function menuForKind(bundle, resourceKind, {connected=true, childKinds=[]}={}) {
  const kind = bundle?.kinds?.[resourceKind];
  if(!kind) return [];
  const items = {};
  const add = (category, item) => (items[category] = items[category] || []).push(item);
  for(const child of childKinds) add('create', {id: `create:${child}`, label: childLabel(bundle, child), operation_id: 'create', resource_kind: child, tier: 1});
  add('open', {id: 'open:properties', label: 'Properties', action: 'properties'});
  for(const op of kind.tier1) {
    if(['inspect', 'insert', 'update', 'delete', 'create'].includes(op)) continue;
    add(TIER1_MENU[op] || 'lifecycle', {id: `op:${op}`, label: tier1Label(op), operation_id: op, resource_kind: resourceKind, tier: 1, enabled: connected});
  }
  for(const op of kind.operations) {
    add(op.menu?.category || 'maintenance', {id: `op:${op.operation_id}`, label: op.title, operation_id: op.operation_id,
      resource_kind: resourceKind, tier: op.tier, enabled: connected && op.available !== false,
      disabled_reason: op.unavailable_reason, submenu: op.menu?.submenu, order: op.menu?.order ?? 0});
  }
  add('refresh', {id: 'refresh', label: 'Refresh', action: 'refresh'});
  return MENU_CATEGORIES
    .filter((entry) => items[entry.category]?.length)
    .map((entry) => ({...entry, items: items[entry.category].sort((a, b) => (a.order ?? 0) - (b.order ?? 0))}));
}

function tier1Label(op) {
  return {alter: 'Edit...', rename: 'Rename...', drop: 'Drop...', comment: 'Comment...', truncate: 'Truncate...',
    grant: 'Grant...', revoke: 'Revoke...', create_or_alter: 'Create or alter...', recreate: 'Recreate...'}[op] ||
    op.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase()) + '...';
}

function childLabel(bundle, kind) {
  const entry = bundle?.kinds?.[kind];
  return (entry?.title || kind).replace(/-/g, ' ').replace(/^./, (c) => c.toUpperCase()) + '...';
}

/**
 * Build the editor option context for an engine from its bundle options and
 * the endpoint's resources: `dialect` lists come from options.json,
 * `catalog` lists from resources of the kinds options.json names, and
 * `resources` (for reference pickers) are grouped by kind.
 */
export function buildOptionContext(bundle, resources=[]) {
  const byKind = {};
  for(const resource of resources) {
    (byKind[resource.resource_kind] = byKind[resource.resource_kind] || []).push(resource);
  }
  const catalog = {};
  for(const [key, source] of Object.entries(bundle?.options?.catalog || {})) {
    const rows = byKind[source.resource_kind] || [];
    catalog[key] = rows.map((row) => ({
      value: row[source.value || 'display_name'] ?? row.display_name,
      label: row[source.label || 'display_name'] ?? row.display_name,
    }));
  }
  return {dialect: bundle?.options?.dialect || {}, catalog, resources: byKind, bundle};
}
