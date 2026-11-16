/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

export function assetIcon(assetType) {
  if (
    assetType === 'ddn-workspace' ||
    assetType === 'cdeadmin.design.erd' ||
    assetType === 'cdeadmin.lineage.v1' ||
    assetType === 'cdeadmin.schema_compare.v1'
  ) {
    return 'tool.erd';
  }
  if (
    assetType === 'cdeadmin.design.screen' ||
    assetType === 'cdeadmin.design.screen_flow'
  ) {
    return 'object.table';
  }
  if (
    assetType === 'cdeadmin.design.question' ||
    assetType === 'cdeadmin.design.dashboard'
  ) {
    return 'tool.bi';
  }
  if (assetType === 'cube' || assetType === 'cdeadmin.design.cube') {
    return 'object.cube';
  }
  if (assetType === 'semantic-model') return 'object.semantic_model';
  if (
    assetType === 'query' ||
    assetType === 'script' ||
    assetType === 'cdeadmin.sql-notebook.v1'
  ) {
    return 'tool.query';
  }
  if (assetType === 'cdeadmin.project.task.v1') return 'action.check';
  if (assetType === 'cdeadmin.project.calendar.v1') return 'object.schedule';
  if (assetType === 'cdeadmin.project.channel.v1') return 'action.comment';
  if (
    assetType === 'cdeadmin.project.report.print.v1' ||
    assetType === 'cdeadmin.project.report.pdf.v1'
  ) {
    return 'action.export';
  }
  if (assetType === 'cdeadmin.project.document.v1') return 'object.notebook';
  return 'object.notebook';
}

export function dbObjectIcon(kind) {
  switch (String(kind || 'table').toLowerCase()) {
    case 'table':
      return 'object.table';
    case 'view':
      return 'object.view';
    case 'procedure':
      return 'object.procedure';
    case 'package':
      return 'object.package';
    case 'function':
      return 'object.function';
    case 'sequence':
      return 'object.sequence';
    default:
      return 'object.table';
  }
}

export function collectDescendantProjectIds(projects, rootProjectId) {
  const childrenByParent = new Map();
  for (const item of projects || []) {
    const pid = item?.parent_project_id;
    if (!pid) continue;
    if (!childrenByParent.has(pid)) childrenByParent.set(pid, []);
    childrenByParent.get(pid).push(item.project_id);
  }
  const descendants = new Set();
  const stack = [...(childrenByParent.get(rootProjectId) || [])];
  while (stack.length > 0) {
    const current = stack.pop();
    if (!current || current === rootProjectId || descendants.has(current)) {
      continue;
    }
    descendants.add(current);
    for (const childId of childrenByParent.get(current) || []) {
      if (!descendants.has(childId)) stack.push(childId);
    }
  }
  return descendants;
}

export function canAssignProjectParent(projects, projectId, candidateParentId) {
  if (!candidateParentId) return true;
  if (projectId && candidateParentId === projectId) return false;
  const byId = new Map((projects || []).map((p) => [p.project_id, p]));
  if (!byId.has(candidateParentId)) return false;
  const visited = new Set(projectId ? [projectId] : []);
  let cursor = byId.get(candidateParentId);
  while (cursor) {
    if (visited.has(cursor.project_id)) return false;
    visited.add(cursor.project_id);
    cursor = cursor.parent_project_id
      ? byId.get(cursor.parent_project_id)
      : null;
  }
  return true;
}

export function buildProjectHierarchy(projects) {
  const list = Array.isArray(projects) ? projects : [];
  const byId = new Map(list.map((p) => [p.project_id, p]));
  const childrenMap = new Map();
  const roots = [];

  const introducesCycle = (project) => {
    const seen = new Set([project.project_id]);
    let cur = project.parent_project_id
      ? byId.get(project.parent_project_id)
      : null;
    while (cur) {
      if (seen.has(cur.project_id)) return true;
      seen.add(cur.project_id);
      cur = cur.parent_project_id ? byId.get(cur.parent_project_id) : null;
    }
    return false;
  };

  for (const project of list) {
    const parentId = project.parent_project_id;
    if (parentId && byId.has(parentId) && !introducesCycle(project)) {
      if (!childrenMap.has(parentId)) childrenMap.set(parentId, []);
      childrenMap.get(parentId).push(project);
    } else {
      roots.push(project);
    }
  }
  return {roots, childrenMap, byId};
}

/**
 * Extract deduplicated database object bindings grouped by kind
 * (table, view, procedure, package, function, sequence) across a project's assets.
 */
export function extractProjectDatabaseObjects(state) {
  const buckets = {
    table: new Map(),
    view: new Map(),
    procedure: new Map(),
    package: new Map(),
    function: new Map(),
    sequence: new Map(),
  };
  for (const asset of state?.assets || []) {
    for (const raw of asset?.resource_bindings || []) {
      const refId = String(raw?.resource_id || '');
      const colonIdx = refId.indexOf(':');
      const inferredKind = colonIdx > 0 ? refId.slice(0, colonIdx) : 'table';
      const inferredName = colonIdx > 0 ? refId.slice(colonIdx + 1) : refId;
      const kind = String(raw?.kind || inferredKind || 'table').toLowerCase();
      const name = String(raw?.nativeIdentity || inferredName || '').trim();
      if (!name || !buckets[kind]) continue;
      const existing = buckets[kind].get(name);
      const role = raw?.bindingRole || 'linked';
      if (!existing || (existing.bindingRole !== 'owned' && role === 'owned')) {
        buckets[kind].set(name, {
          ...raw,
          kind,
          nativeIdentity: name,
          resource_id: `${kind}:${name}`,
          bindingRole: role,
        });
      }
    }
  }
  const result = {};
  for (const [kind, map] of Object.entries(buckets)) {
    result[kind] = [...map.values()].sort((a, b) =>
      a.nativeIdentity.localeCompare(b.nativeIdentity)
    );
  }
  return result;
}

const SCREEN_TYPES = new Set([
  'cdeadmin.design.screen',
  'cdeadmin.design.screen_flow',
]);
const GRAPH_TYPES = new Set([
  'cdeadmin.design.question',
  'cdeadmin.design.dashboard',
  'cdeadmin.design.cube',
  'cube',
  'semantic-model',
]);
const DIAGRAM_TYPES = new Set([
  'cdeadmin.design.erd',
  'ddn-workspace',
  'cdeadmin.lineage.v1',
  'cdeadmin.schema_compare.v1',
]);

export const PROJECT_LOCAL_ASSET_TYPES = new Set([
  'cdeadmin.project.report.print.v1',
  'cdeadmin.project.report.pdf.v1',
  'cdeadmin.project.task.v1',
  'cdeadmin.project.calendar.v1',
  'cdeadmin.project.channel.v1',
  'cdeadmin.project.document.v1',
]);

/**
 * Build the canonical Project Navigator virtual hierarchy for one project:
 *   - Projects -> [child projects]
 *   - Tables -> [child tables]
 *   - Views -> [child views]
 *   - Coding -> Procedures / Packages / Functions / Sequences
 *   - Screens -> [screen meshes]
 *   - Reports -> Print / Graphs / Diagrams / PDF
 *   - Tasks -> Pending / In Process / Completed
 *   - Calendars -> Shared & Personal Calendars / Gantt Charts
 *   - Channels -> [chat channels]
 *   - Members -> Groups / Individuals
 *   - Notes, Documents, Transcripts -> [notebooks, queries, notes, docs, transcripts]
 */
export function buildProjectVirtualTree(project, state, childProjects = []) {
  const pid = project.project_id;
  const dbObjects = extractProjectDatabaseObjects(state);
  const assets = Array.isArray(state?.assets) ? state.assets : [];

  const screens = [];
  const reportsPrint = [];
  const reportsGraphs = [];
  const reportsDiagrams = [];
  const reportsPdf = [];
  const tasksPending = [];
  const tasksInProcess = [];
  const tasksCompleted = [];
  const calSharedPersonal = [];
  const calGantt = [];
  const channels = [];
  const documents = [];

  for (const asset of assets) {
    const at = asset.asset_type;
    const meta = asset.metadata || {};
    if (SCREEN_TYPES.has(at)) {
      screens.push(asset);
    } else if (
      at === 'cdeadmin.project.report.print.v1' ||
      meta.report_category === 'print'
    ) {
      reportsPrint.push(asset);
    } else if (
      at === 'cdeadmin.project.report.pdf.v1' ||
      meta.report_category === 'pdf'
    ) {
      reportsPdf.push(asset);
    } else if (GRAPH_TYPES.has(at)) {
      reportsGraphs.push(asset);
    } else if (DIAGRAM_TYPES.has(at)) {
      reportsDiagrams.push(asset);
    } else if (at === 'cdeadmin.project.task.v1') {
      const st = String(meta.task_status || 'pending').toLowerCase();
      if (st === 'completed') tasksCompleted.push(asset);
      else if (st === 'in_process' || st === 'in-process') tasksInProcess.push(asset);
      else tasksPending.push(asset);
    } else if (at === 'cdeadmin.project.calendar.v1') {
      if (String(meta.calendar_kind || '').toLowerCase() === 'gantt') {
        calGantt.push(asset);
      } else {
        calSharedPersonal.push(asset);
      }
    } else if (at === 'cdeadmin.project.channel.v1') {
      channels.push(asset);
    } else {
      documents.push(asset);
    }
  }

  const rawMembers = Array.isArray(state?.members) ? state.members : [];
  const metaGroups = Array.isArray(state?.metadata_groups)
    ? state.metadata_groups
    : [];
  const memberGroups = [
    ...rawMembers
      .filter((m) => m.principal_type === 'role')
      .map((m) => ({
        id: `role-${m.principal_id}`,
        label: m.label || `Role #${m.principal_id}`,
        access_level: m.access_level,
        principal_type: 'role',
        principal_id: m.principal_id,
      })),
    ...metaGroups,
  ];
  // Extract rich member descriptors from project governance doc if present
  const teamDoc = documents.find(
    (d) => d.metadata?.document_kind === 'team_roster'
  );
  if (Array.isArray(teamDoc?.metadata?.groups)) {
    for (const g of teamDoc.metadata.groups) {
      if (!memberGroups.some((x) => x.label === g.name)) {
        memberGroups.push({
          id: `grp-${g.name}`,
          label: g.name,
          access_level: g.access || 'editor',
          principal_type: 'role',
        });
      }
    }
  }

  const memberIndividuals = [
    {
      id: `owner-${pid}`,
      label: teamDoc?.metadata?.lead || 'Project Owner (cdeadmin@localhost)',
      access_level: project.access || 'owner',
      principal_type: 'user',
    },
    ...rawMembers
      .filter((m) => m.principal_type === 'user')
      .map((m) => ({
        id: `user-${m.principal_id}`,
        label: m.label || `User #${m.principal_id}`,
        access_level: m.access_level,
        principal_type: 'user',
        principal_id: m.principal_id,
      })),
  ];
  if (Array.isArray(teamDoc?.metadata?.individuals)) {
    for (const ind of teamDoc.metadata.individuals) {
      if (!memberIndividuals.some((x) => x.label === ind.name)) {
        memberIndividuals.push({
          id: `ind-${ind.name}`,
          label: `${ind.name} (${ind.role || 'Contributor'})`,
          access_level: ind.access || 'editor',
          principal_type: 'user',
        });
      }
    }
  }

  const toDbItems = (items) =>
    items.map((obj) => ({
      itemKind: 'db-object',
      id: `${pid}:db:${obj.kind}:${obj.nativeIdentity}`,
      label: obj.nativeIdentity,
      iconKey: dbObjectIcon(obj.kind),
      badge: obj.bindingRole === 'owned' ? 'owned' : 'linked',
      dbObject: obj,
      project,
    }));

  const toAssetItems = (items) =>
    items.map((asset) => ({
      itemKind: 'asset',
      id: `${pid}:asset:${asset.asset_id}`,
      label: asset.name,
      iconKey: assetIcon(asset.asset_type),
      badge: `v${asset.version ?? 1}`,
      warning: asset.validation_state === 'invalid' ? 'Validation failed' : '',
      asset,
      project,
    }));

  const toMemberItems = (items, iconKey) =>
    items.map((m) => ({
      itemKind: 'member',
      id: `${pid}:member:${m.id}`,
      label: m.label,
      iconKey,
      badge: m.access_level,
      member: m,
      project,
    }));

  const codingSubgroups = [
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:coding:procedures`,
      key: 'procedures',
      label: 'Procedures',
      iconKey: 'object.procedure',
      project,
      items: toDbItems(dbObjects.procedure),
      subgroups: [],
    },
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:coding:packages`,
      key: 'packages',
      label: 'Packages',
      iconKey: 'object.package',
      project,
      items: toDbItems(dbObjects.package),
      subgroups: [],
    },
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:coding:functions`,
      key: 'functions',
      label: 'Functions',
      iconKey: 'object.function',
      project,
      items: toDbItems(dbObjects.function),
      subgroups: [],
    },
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:coding:sequences`,
      key: 'sequences',
      label: 'Sequences',
      iconKey: 'object.sequence',
      project,
      items: toDbItems(dbObjects.sequence),
      subgroups: [],
    },
  ];

  const reportsSubgroups = [
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:reports:print`,
      key: 'print',
      label: 'Print',
      iconKey: 'action.export',
      project,
      items: toAssetItems(reportsPrint),
      subgroups: [],
    },
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:reports:graphs`,
      key: 'graphs',
      label: 'Graphs',
      iconKey: 'tool.bi',
      project,
      items: toAssetItems(reportsGraphs),
      subgroups: [],
    },
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:reports:diagrams`,
      key: 'diagrams',
      label: 'Diagrams',
      iconKey: 'tool.erd',
      project,
      items: toAssetItems(reportsDiagrams),
      subgroups: [],
    },
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:reports:pdf`,
      key: 'pdf',
      label: 'PDF',
      iconKey: 'action.export',
      project,
      items: toAssetItems(reportsPdf),
      subgroups: [],
    },
  ];

  const tasksSubgroups = [
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:tasks:pending`,
      key: 'pending',
      label: 'Pending',
      iconKey: 'action.check',
      project,
      items: toAssetItems(tasksPending),
      subgroups: [],
    },
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:tasks:in_process`,
      key: 'in_process',
      label: 'In Process',
      iconKey: 'action.execute',
      project,
      items: toAssetItems(tasksInProcess),
      subgroups: [],
    },
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:tasks:completed`,
      key: 'completed',
      label: 'Completed',
      iconKey: 'action.check',
      project,
      items: toAssetItems(tasksCompleted),
      subgroups: [],
    },
  ];

  const calendarsSubgroups = [
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:calendars:shared_personal`,
      key: 'shared_personal',
      label: 'Shared & Personal Calendars',
      iconKey: 'object.schedule',
      project,
      items: toAssetItems(calSharedPersonal),
      subgroups: [],
    },
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:calendars:gantt`,
      key: 'gantt',
      label: 'Gantt Charts',
      iconKey: 'tool.bi',
      project,
      items: toAssetItems(calGantt),
      subgroups: [],
    },
  ];

  const membersSubgroups = [
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:members:groups`,
      key: 'groups',
      label: 'Groups',
      iconKey: 'folder.security',
      project,
      items: toMemberItems(memberGroups, 'folder.security'),
      subgroups: [],
    },
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:members:individuals`,
      key: 'individuals',
      label: 'Individuals',
      iconKey: 'object.role',
      project,
      items: toMemberItems(memberIndividuals, 'object.role'),
      subgroups: [],
    },
  ];

  const countVirtual = (vnode) =>
    (vnode.items?.length || 0) +
    (vnode.childProjects?.length || 0) +
    (vnode.subgroups || []).reduce((acc, sg) => acc + countVirtual(sg), 0);

  const topVirtuals = [
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:projects`,
      key: 'projects',
      label: 'Projects',
      iconKey: 'folder.system',
      project,
      childProjects,
      items: [],
      subgroups: [],
    },
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:tables`,
      key: 'tables',
      label: 'Tables',
      iconKey: 'object.table',
      project,
      items: toDbItems(dbObjects.table),
      subgroups: [],
    },
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:views`,
      key: 'views',
      label: 'Views',
      iconKey: 'object.view',
      project,
      items: toDbItems(dbObjects.view),
      subgroups: [],
    },
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:coding`,
      key: 'coding',
      label: 'Coding',
      iconKey: 'folder.programming',
      project,
      items: [],
      subgroups: codingSubgroups,
    },
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:screens`,
      key: 'screens',
      label: 'Screens',
      iconKey: 'object.table',
      project,
      items: toAssetItems(screens),
      subgroups: [],
    },
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:reports`,
      key: 'reports',
      label: 'Reports',
      iconKey: 'tool.bi',
      project,
      items: [],
      subgroups: reportsSubgroups,
    },
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:tasks`,
      key: 'tasks',
      label: 'Tasks',
      iconKey: 'action.check',
      project,
      items: [],
      subgroups: tasksSubgroups,
    },
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:calendars`,
      key: 'calendars',
      label: 'Calendars',
      iconKey: 'object.schedule',
      project,
      items: [],
      subgroups: calendarsSubgroups,
    },
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:channels`,
      key: 'channels',
      label: 'Channels',
      iconKey: 'action.comment',
      project,
      items: toAssetItems(channels),
      subgroups: [],
    },
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:members`,
      key: 'members',
      label: 'Members',
      iconKey: 'folder.security',
      project,
      items: [],
      subgroups: membersSubgroups,
    },
    {
      nodeKind: 'virtual',
      id: `virt:${pid}:documents`,
      key: 'documents',
      label: 'Notes, Documents, Transcripts',
      iconKey: 'object.notebook',
      project,
      items: toAssetItems(documents),
      subgroups: [],
    },
  ];

  const stampCounts = (vnode) => {
    for (const sg of vnode.subgroups || []) stampCounts(sg);
    vnode.totalCount = countVirtual(vnode);
    return vnode;
  };

  return topVirtuals.map(stampCounts);
}
