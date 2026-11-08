/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// Named diagrams made with the Diagrams tool (owner direction 2026-11-06).
// A diagram is a DDN workspace project asset whose metadata names it as a
// diagram and records its notation; DDN renders and edits it. ScratchRobin
// only writes the first, empty view.

import {DDN_ASSET_SCHEMA} from './contracts.js';
import {sourceSet} from './runtime.js';

export const DIAGRAM_SCHEMA = 'cdeadmin.diagram.v1';
export const DIAGRAM_ENTRY = 'diagram.ddn';
export const DIAGRAM_VIEW = 'diagram';
export const DEFAULT_DIAGRAM_NOTATION = 'erd.crowfoot@1';

// Entity-relationship notations in DDN's profile registry. A notation is
// offered only once ScratchRobin can map catalog objects into it ("To
// Diagram"); the others are listed but unavailable until their mapping
// exists.
export const DIAGRAM_NOTATIONS = Object.freeze([
  Object.freeze({id: 'erd.crowfoot@1', label: 'Crow\'s foot ERD', available: true,
    layout: {algorithm: 'organic', gap: 80}}),
  Object.freeze({id: 'ddn@1', label: 'DDN relations graph', available: true,
    layout: {algorithm: 'layered', gap: 240}}),
  ...[['chen.basic@1', 'Chen ERD'], ['uml.structure@2', 'UML class diagram'],
    ['orm.basic@1', 'Object-role model'], ['chebotko.logical@1', 'Chebotko logical diagram']]
    .map(([id, label]) => Object.freeze({id, label, available: false,
      reason: 'ScratchRobin has no catalog mapping for this notation yet.'})),
]);

export function diagramNotation(id) {
  return DIAGRAM_NOTATIONS.find((notation) => notation.id === id) ?? null;
}

// DDN quoted text, as ScratchRobin's server-side encoder writes it.
export function ddnQuoted(value) {
  const text = String(value);
  if(/[\r\n\0]/.test(text)) throw new TypeError('Diagram names cannot contain line breaks.');
  return '"' + text.replaceAll('"', '""') + '"';
}

export function diagramName(value) {
  const name = String(value ?? '').trim();
  if(!name) throw new TypeError('A diagram needs a name.');
  if(name.length > 256) throw new TypeError('Diagram names are limited to 256 characters.');
  ddnQuoted(name);
  return name;
}

export function newDiagramSource(name, notationId=DEFAULT_DIAGRAM_NOTATION) {
  const notation = diagramNotation(notationId);
  if(!notation?.available) throw new TypeError('This diagram notation is not available.');
  return [
    'version ddn-next-1',
    '// ScratchRobin diagram',
    '',
    `view ${ddnQuoted(DIAGRAM_VIEW)} as ${ddnQuoted(notation.id)}`,
    '    with',
    `        id ${ddnQuoted(DIAGRAM_VIEW)}`,
    `        title ${ddnQuoted(diagramName(name))}`,
    '        selection',
    '            include empty list',
    '        layout',
    `            algorithm ${ddnQuoted(notation.layout.algorithm)}`,
    `            gap ${notation.layout.gap}`,
    '',
  ].join('\n');
}

function slug(name) {
  return name.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '').slice(0, 64) || 'diagram';
}

// crypto.randomUUID needs a secure context; a plain-HTTP server address is not one.
function randomHex() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return [...bytes].map((value) => value.toString(16).padStart(2, '0')).join('');
}

// The asset id is opaque and new. The path follows the name plus part of the
// id, because a path names one asset per project and names may repeat.
export function newDiagramAsset({projectId, name, notation=DEFAULT_DIAGRAM_NOTATION,
  random=randomHex}) {
  const display = diagramName(name);
  const unique = random();
  const assetId = `diagram-${unique}`;
  return {
    schema: DDN_ASSET_SCHEMA,
    assetRef: {schemaVersion: 1, projectId, assetId, assetType: 'ddn-workspace',
      assetVersion: 0, path: `diagrams/${slug(display)}-${unique.slice(0, 8)}.ddn`,
      displayName: display},
    snapshot: {format: 'ddn-source-workspace@1', entry: DIAGRAM_ENTRY, view: DIAGRAM_VIEW,
      files: {[DIAGRAM_ENTRY]: newDiagramSource(display, notation)}},
    metadata: {diagram: {schema: DIAGRAM_SCHEMA, notation}},
  };
}

export function isDiagramAsset(asset) {
  return asset?.asset_type === 'ddn-workspace' &&
    asset?.metadata?.diagram?.schema === DIAGRAM_SCHEMA;
}

// Every diagram the user can open, grouped under its project.
export async function listDiagrams(client) {
  const projects = await client.listProjects();
  const states = await Promise.all(projects.map(async (project) => {
    try { return {project, state: await client.project(project.project_id)}; }
    catch(error) { return {project, error: error.message}; }
  }));
  return states.map(({project, state, error}) => ({
    project, error: error ?? '',
    diagrams: (state?.assets ?? []).filter(isDiagramAsset)
      .sort((left, right) => left.name.localeCompare(right.name)),
  }));
}

// DDN admits the new source before it is stored, so a diagram is never saved
// in a form the viewer or designer would refuse.
export async function verifyDiagramSnapshot(libraries, snapshot) {
  const api = libraries.viewer;
  const verifier = api.createVerifier(api.createBrowserRuntimeOptions ?
    api.createBrowserRuntimeOptions() : api.createCompleteRuntimeOptions());
  const verified = await api.verifySourcesWithModel(verifier, sourceSet(snapshot.files, snapshot.entry),
    {level: 'semantic', scope: {kind: 'workarea'}, purpose: 'view'});
  const report = verified.report ?? verified;
  const errors = (report.diagnostics ?? []).filter((item) => item.severity === 'error');
  if(report.outcome === 'invalid' || errors.length) {
    throw new Error(errors.map((item) => item.message).join('\n') || 'DDN refused the new diagram.');
  }
  return report;
}

export async function createDiagram(client, libraries, {projectId, name, notation, random}) {
  const payload = newDiagramAsset({projectId, name, notation, random});
  await verifyDiagramSnapshot(libraries, payload.snapshot);
  const saved = await client.saveAsset(projectId, payload.assetRef.assetId, payload);
  return {payload, saved};
}
