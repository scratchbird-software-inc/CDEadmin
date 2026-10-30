/*
 * Load the raw UI descriptors from the repository and resolve them the way the
 * server does, so family render tests exercise the real engine forms.
 */
import fs from 'fs';
import path from 'path';
import {resolveBundle} from '../../../pgadmin/static/js/cdeadmin_ui/objects/descriptors';

export const DESCRIPTOR_ROOT = path.resolve(__dirname, '../../../pgadmin/cdeadmin/ui_descriptors');
// Owner direction 2026-10-30: the parity engines join beta as their descriptor folders land.
export const BETA_ENGINES = ['postgresql', 'mysql', 'mariadb', 'firebird', 'duckdb', 'sqlite',
  'dolt', 'tidb', 'vitess', 'cockroachdb', 'yugabytedb'];
export const FAMILIES = ['table', 'view', 'index', 'routine', 'trigger', 'sequence', 'type', 'role', 'database', 'server'];

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

export function loadFamilies() {
  const families = {};
  for(const file of fs.readdirSync(path.join(DESCRIPTOR_ROOT, 'families'))) {
    if(!file.endsWith('.family.json')) continue;
    const doc = readJson(path.join(DESCRIPTOR_ROOT, 'families', file));
    families[doc.family] = doc;
  }
  return families;
}

export function loadEngineBundle(engine) {
  const folder = path.join(DESCRIPTOR_ROOT, engine);
  const forms = {};
  const formsDir = path.join(folder, 'forms');
  for(const file of fs.readdirSync(formsDir)) {
    if(!file.endsWith('.form.json')) continue;
    const doc = readJson(path.join(formsDir, file));
    forms[doc.family === 'engine_object' ? `engine_object:${doc.resource_kinds[0]}` : doc.family] = doc;
  }
  const readOptional = (name) => fs.existsSync(path.join(folder, name)) ? readJson(path.join(folder, name)) : null;
  return resolveBundle({
    engine,
    families: loadFamilies(),
    capabilities: readJson(path.join(folder, 'capabilities.json')),
    operations: readOptional('operations.json')?.operations || [],
    navigator: readOptional('navigator.json') || {},
    forms,
  });
}

/** engine × family pairs that have a form with at least one field. */
export function populatedForms() {
  const pairs = [];
  for(const engine of BETA_ENGINES) {
    const bundle = loadEngineBundle(engine);
    for(const family of FAMILIES) {
      const form = bundle.forms[family];
      if(form && form.status !== 'pending' && form.tabs.some((tab) => tab.fields.length)) {
        pairs.push([engine, family, form, bundle]);
      }
    }
  }
  return pairs;
}
