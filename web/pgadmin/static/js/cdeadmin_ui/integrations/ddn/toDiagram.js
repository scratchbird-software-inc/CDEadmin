/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// To Diagram (owner direction 2026-11-06): add a database's tables and views,
// with their relations, to a diagram made with the Diagrams tool. The server
// action catalog_diagram returns the engine's catalog relations source, the
// file it goes in, the nested regions (host, instance, database, schemas)
// and each table's region. Edits go through DDN's own source functions; no
// engine is named here.

import {sourceSet} from './runtime.js';
import {ddnQuoted, verifyDiagramSnapshot} from './diagrams.js';
import {DDN_ASSET_SCHEMA} from './contracts.js';

function decode(libraries, files, entry) {
  const input = sourceSet(files, entry, true);
  const decoded = libraries.language.decodeSources(input);
  if(!decoded.syntaxValid) {
    throw new Error((decoded.diagnostics ?? []).map((item) => item.message).join('\n') ||
      'DDN could not read the diagram source.');
  }
  return {input, decoded};
}

function patched(libraries, input, patches) {
  const result = libraries.language.applySourcePatches(input, patches);
  return Object.fromEntries(result.files.map((file) => [file.id, file.text]));
}

function viewRecord(libraries, decoded, file, id) {
  const entry = libraries.model.listRecords(decoded.normalized).find((item) =>
    item.kind === 'view' && item.ref.id === id && item.ref.file === file);
  if(!entry) throw new Error('The diagram\'s view is missing.');
  return entry.record;
}

// The catalog source without its own views: the diagram's view selects.
export function objectsSource(libraries, file, text) {
  const {input, decoded} = decode(libraries, {[file]: text}, file);
  const patches = libraries.model.listRecords(decoded.normalized)
    .filter((item) => item.kind === 'view')
    .flatMap((item) => libraries.language.deleteDeclaration(decoded, item.ref));
  return patched(libraries, input, patches)[file];
}

const sameRef = (left, right) => left.id === right.id && left.file === right.file;

export function mergeIntoDiagram(libraries, content, contribution, {resourceIds=null}={}) {
  const chosen = resourceIds ? contribution.relations.filter((item) =>
    resourceIds.includes(item.resource_id)) : contribution.relations;
  if(!chosen.length) {
    throw new Error('The object is not drawn in its database\'s catalog diagram.');
  }
  const file = contribution.file;
  const files = {...content.files,
    [file]: objectsSource(libraries, file, contribution.snapshot.files[contribution.snapshot.entry])};
  const include = `include ${ddnQuoted(file)}`;
  if(!files[content.entry].split(/\r?\n/).some((line) => line.trim() === include)) {
    files[content.entry] = files[content.entry].replace(/\s*$/, '\n') + '\n' + include + '\n';
  }
  // Re-adding a database replaces its file; drop references to objects
  // that are no longer in it, or DDN would refuse the diagram.
  const present = new Set(contribution.relations.map((item) => item.key));
  const kept = (ref) => ref.file !== file || present.has(ref.id);
  let view = viewRecord(libraries, decode(libraries, files, content.entry).decoded, content.entry, content.view);
  const before = view.selection?.include ?? [];
  const selection = before.filter(kept);
  const dropped = before.length - selection.length;
  const added = [];
  for(const item of chosen) {
    const ref = {id: item.key, file};
    if(!selection.some((value) => sameRef(value, ref))) { selection.push(ref); added.push(item); }
  }
  const regions = (view.regions ?? []).map((region) => ({...region,
    members: (region.members ?? []).filter(kept)}));
  const byId = new Map(contribution.regions.map((region) => [region.id, region]));
  const needed = [];
  for(const item of chosen) {
    for(let id = item.region; id; id = byId.get(id)?.parent) {
      if(!needed.includes(id)) needed.push(id);
    }
  }
  for(const region of contribution.regions) {
    if(needed.includes(region.id) && !regions.some((value) => value.id === region.id)) {
      regions.push({...region, members: []});
    }
  }
  for(const item of chosen) {
    const region = regions.find((value) => value.id === item.region);
    const ref = {id: item.key, file};
    if(!region.members.some((value) => sameRef(value, ref))) region.members.push(ref);
  }
  let state = decode(libraries, files, content.entry);
  let next = patched(libraries, state.input, libraries.language.patchProperty(
    state.decoded, {file: content.entry, id: content.view}, 'selection.include', selection));
  state = decode(libraries, next, content.entry);
  next = patched(libraries, state.input, libraries.language.patchProperty(
    state.decoded, {file: content.entry, id: content.view}, 'regions', regions));
  view = viewRecord(libraries, decode(libraries, next, content.entry).decoded, content.entry, content.view);
  return {snapshot: {...content, files: next}, added: added.length, dropped,
    selected: view.selection?.include?.length ?? 0};
}

// Load the diagram, merge, have DDN verify it, and save the next version.
export async function addToDiagram({client, libraries, post, projectId, assetId,
  databaseTargetId, resourceIds=null}) {
  const contribution = await post({action: 'catalog_diagram',
    request: {database_target_id: databaseTargetId}});
  const asset = await client.asset(projectId, assetId);
  const {format, entry, view, files} = asset.content;
  const merged = mergeIntoDiagram(libraries, {format, entry, view, files}, contribution, {resourceIds});
  await verifyDiagramSnapshot(libraries, merged.snapshot);
  const saved = await client.saveAsset(projectId, assetId, {
    schema: DDN_ASSET_SCHEMA,
    assetRef: {...asset.assetRef, assetVersion: asset.version},
    snapshot: merged.snapshot,
    ...(asset.metadata ? {metadata: asset.metadata} : {}),
  });
  return {...merged, saved, warnings: contribution.warnings ?? []};
}
