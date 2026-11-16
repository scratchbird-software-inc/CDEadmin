/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {useLocaleRevision} from '../actions/t_actions';
import {Box} from '../primitives/Layout';
import {ScratchScrollArea} from '../base/ScratchScrollArea';
import {Icon} from '../icons';
import {ProjectAssetClient} from './ProjectAssetClient';
import {Toolbar} from '../layout/WorkbenchChrome';
import {Button} from '../primitives/Button';
import {TextArea, TextField} from '../primitives/Field';
import {SearchField} from '../primitives/AdvancedControls';
import {TreeRow} from '../navigation/AdvancedNavigation';
import {Dialog} from '../overlays/Dialog';
import {EmptyState} from '../feedback/EmptyState';
import {ProgressOverlay} from '../feedback/ProgressOverlay';
import FormReference from '../navigation/FormReference';
import {
  PROJECT_LOCAL_ASSET_TYPES,
  assetIcon,
  buildProjectHierarchy,
  buildProjectVirtualTree,
  canAssignProjectParent,
  collectDescendantProjectIds,
} from './ProjectNavigatorModel';

export {
  buildProjectHierarchy,
  buildProjectVirtualTree,
  canAssignProjectParent,
  collectDescendantProjectIds,
};

const NAV_EVENT = 'scratchrobin:project-navigator-selection';
let sharedNavSelection = null;

function publishNavSelection(selection) {
  sharedNavSelection = selection;
  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent(NAV_EVENT, {detail: selection})
    );
  }
}

function findVirtualNodeById(virtualNodes, targetId) {
  for (const vnode of virtualNodes || []) {
    if (vnode.id === targetId) return {node: vnode, trail: [vnode]};
    for (const sg of vnode.subgroups || []) {
      if (sg.id === targetId) return {node: sg, trail: [vnode, sg]};
    }
  }
  return null;
}

const AUTO_FIELD_CARD_STYLE = {
  border: '1px solid var(--sr-border-subtle, rgba(128,128,128,0.22))',
  borderRadius: '8px',
  padding: '10px 12px',
  background: 'var(--sr-surface-card, rgba(128,128,128,0.04))',
  display: 'flex',
  flexDirection: 'column',
  gap: '4px',
  minWidth: 0,
};

const VIRTUAL_ITEM_BTN_STYLE = {
  display: 'flex',
  alignItems: 'center',
  gap: '10px',
  padding: '10px 12px',
  borderRadius: '8px',
  border: '1px solid var(--sr-border-default, rgba(128,128,128,0.28))',
  background: 'var(--sr-surface-card, rgba(128,128,128,0.04))',
  color: 'inherit',
  cursor: 'pointer',
  textAlign: 'left',
  minWidth: 0,
  width: '100%',
};

function ProjectLocalAssetViewer({project, asset, client, onAssetUpdated}) {
  const [fullAsset, setFullAsset] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [messageDraft, setMessageDraft] = useState('');
  const [docDraft, setDocDraft] = useState('');
  const [err, setErr] = useState('');

  const loadFull = useCallback(async () => {
    setLoading(true);
    setErr('');
    try {
      const loaded = await client.asset(project.project_id, asset.asset_id);
      setFullAsset(loaded);
      setDocDraft(String(loaded?.content?.body || loaded?.content?.markdown || ''));
    } catch (e) {
      setErr(e.message || 'Failed to load asset.');
    } finally {
      setLoading(false);
    }
  }, [client, project.project_id, asset.asset_id]);

  useEffect(() => {
    loadFull();
  }, [loadFull]);

  if (loading) {
    return <Box sx={{p: 2}}>{gettext('Loading item…')}</Box>;
  }
  if (err) {
    return <EmptyState role="alert" message={err} actionLabel={gettext('Retry')} onAction={loadFull} />;
  }
  const content = fullAsset?.content || {};
  const meta = fullAsset?.metadata || {};
  const at = fullAsset?.asset_type;

  const updateTaskStatus = async (nextStatus) => {
    setSaving(true);
    try {
      await client.saveAsset(project.project_id, asset.asset_id, {
        asset_type: at,
        schema_name: fullAsset.schema_name,
        schema_version: fullAsset.schema_version || 1,
        expected_version: fullAsset.version,
        name: fullAsset.name,
        path: fullAsset.path,
        content: {...content, status: nextStatus},
        metadata: {...meta, task_status: nextStatus},
        resource_bindings: fullAsset.resource_bindings || [],
        validation_state: 'valid',
      });
      await loadFull();
      await onAssetUpdated?.(project);
    } catch (e) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  };

  const postChannelMessage = async () => {
    const text = messageDraft.trim();
    if (!text) return;
    setSaving(true);
    try {
      const nextMessages = [
        ...(Array.isArray(content.messages) ? content.messages : []),
        {
          id: `msg-${Date.now()}`,
          author: 'cdeadmin@localhost',
          timestamp: new Date().toISOString().slice(0, 16).replace('T', ' '),
          text,
        },
      ];
      await client.saveAsset(project.project_id, asset.asset_id, {
        asset_type: at,
        schema_name: fullAsset.schema_name,
        schema_version: fullAsset.schema_version || 1,
        expected_version: fullAsset.version,
        name: fullAsset.name,
        path: fullAsset.path,
        content: {...content, messages: nextMessages},
        metadata: meta,
        resource_bindings: fullAsset.resource_bindings || [],
        validation_state: 'valid',
      });
      setMessageDraft('');
      await loadFull();
      await onAssetUpdated?.(project);
    } catch (e) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  };

  const saveDocumentBody = async () => {
    setSaving(true);
    try {
      await client.saveAsset(project.project_id, asset.asset_id, {
        asset_type: at,
        schema_name: fullAsset.schema_name,
        schema_version: fullAsset.schema_version || 1,
        expected_version: fullAsset.version,
        name: fullAsset.name,
        path: fullAsset.path,
        content: {...content, body: docDraft},
        metadata: meta,
        resource_bindings: fullAsset.resource_bindings || [],
        validation_state: 'valid',
      });
      await loadFull();
      await onAssetUpdated?.(project);
    } catch (e) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  };

  if (at === 'cdeadmin.project.task.v1') {
    const curStatus = String(meta.task_status || content.status || 'pending');
    return (
      <Box sx={{display: 'grid', gap: 2, p: 2}}>
        <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10}}>
          <div style={AUTO_FIELD_CARD_STYLE}>
            <span style={{fontSize: '0.75rem', opacity: 0.7}}>{gettext('Status')}</span>
            <strong>{curStatus.replace('_', ' ').toUpperCase()}</strong>
          </div>
          <div style={AUTO_FIELD_CARD_STYLE}>
            <span style={{fontSize: '0.75rem', opacity: 0.7}}>{gettext('Assignee')}</span>
            <strong>{content.assignee || 'Unassigned'}</strong>
          </div>
          <div style={AUTO_FIELD_CARD_STYLE}>
            <span style={{fontSize: '0.75rem', opacity: 0.7}}>{gettext('Priority')}</span>
            <strong>{content.priority || 'Medium'}</strong>
          </div>
          <div style={AUTO_FIELD_CARD_STYLE}>
            <span style={{fontSize: '0.75rem', opacity: 0.7}}>{gettext('Due Date')}</span>
            <strong>{content.due_date || '—'}</strong>
          </div>
        </div>
        <div style={AUTO_FIELD_CARD_STYLE}>
          <span style={{fontSize: '0.75rem', opacity: 0.7}}>{gettext('Summary')}</span>
          <div style={{whiteSpace: 'pre-wrap'}}>{content.description || fullAsset.name}</div>
        </div>
        <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap'}}>
          <Button disabled={saving || curStatus === 'pending'} onClick={() => updateTaskStatus('pending')}>
            {gettext('Move to Pending')}
          </Button>
          <Button disabled={saving || curStatus === 'in_process'} onClick={() => updateTaskStatus('in_process')}>
            {gettext('Move to In Process')}
          </Button>
          <Button intent="primary" disabled={saving || curStatus === 'completed'} onClick={() => updateTaskStatus('completed')}>
            {gettext('Mark Completed')}
          </Button>
        </Box>
      </Box>
    );
  }

  if (at === 'cdeadmin.project.calendar.v1') {
    const isGantt = String(meta.calendar_kind || '') === 'gantt';
    const entries = Array.isArray(content.entries) ? content.entries : [];
    return (
      <Box sx={{display: 'grid', gap: 1.5, p: 2}}>
        <div style={{fontSize: '0.85rem', opacity: 0.8}}>
          {content.summary || (isGantt ? gettext('Project Gantt Schedule') : gettext('Project Shared & Personal Calendar'))}
        </div>
        {entries.map((entry, idx) => (
          <div key={entry.id || idx} style={AUTO_FIELD_CARD_STYLE}>
            <div style={{display: 'flex', justifyContent: 'space-between', gap: 8}}>
              <strong>{entry.title}</strong>
              <span style={{fontSize: '0.78rem', opacity: 0.75}}>
                {entry.start} → {entry.end || entry.start}
              </span>
            </div>
            {isGantt && (
              <div style={{height: 10, borderRadius: 5, background: 'rgba(128,128,128,0.18)', overflow: 'hidden', marginTop: 4}}>
                <div
                  style={{
                    width: `${Math.min(Math.max(Number(entry.progress ?? 50), 5), 100)}%`,
                    height: '100%',
                    background: 'var(--sr-accent-primary, #2563eb)',
                  }}
                />
              </div>
            )}
            <span style={{fontSize: '0.78rem', opacity: 0.75}}>
              {entry.owner || 'Team'}{isGantt ? ` · ${entry.progress ?? 50}%` : ''}
            </span>
          </div>
        ))}
      </Box>
    );
  }

  if (at === 'cdeadmin.project.channel.v1') {
    const messages = Array.isArray(content.messages) ? content.messages : [];
    return (
      <Box sx={{display: 'grid', gap: 1.5, p: 2}}>
        <div style={{fontSize: '0.85rem', opacity: 0.8}}>{content.topic || fullAsset.name}</div>
        <div style={{display: 'grid', gap: 8}}>
          {messages.map((m, idx) => (
            <div key={m.id || idx} style={AUTO_FIELD_CARD_STYLE}>
              <div style={{display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', opacity: 0.75}}>
                <strong>{m.author}</strong>
                <span>{m.timestamp}</span>
              </div>
              <div>{m.text}</div>
            </div>
          ))}
        </div>
        <Box sx={{display: 'flex', gap: 1, alignItems: 'flex-end'}}>
          <div style={{flex: 1}}>
            <TextField
              label={gettext('Post message')}
              value={messageDraft}
              onChange={(e) => setMessageDraft(e.target.value)}
            />
          </div>
          <Button intent="primary" loading={saving} onClick={postChannelMessage}>
            {gettext('Send')}
          </Button>
        </Box>
      </Box>
    );
  }

  if (
    at === 'cdeadmin.project.report.print.v1' ||
    at === 'cdeadmin.project.report.pdf.v1'
  ) {
    return (
      <Box sx={{display: 'grid', gap: 1.5, p: 2}}>
        <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10}}>
          <div style={AUTO_FIELD_CARD_STYLE}>
            <span style={{fontSize: '0.75rem', opacity: 0.7}}>{gettext('Format')}</span>
            <strong>{meta.report_category === 'pdf' ? 'PDF Report' : 'Print Format'}</strong>
          </div>
          <div style={AUTO_FIELD_CARD_STYLE}>
            <span style={{fontSize: '0.75rem', opacity: 0.7}}>{gettext('Paper / Orientation')}</span>
            <strong>{content.paper || 'A4 Portrait'}</strong>
          </div>
          <div style={AUTO_FIELD_CARD_STYLE}>
            <span style={{fontSize: '0.75rem', opacity: 0.7}}>{gettext('Source Relation')}</span>
            <strong>{content.source_table || '—'}</strong>
          </div>
        </div>
        <div style={AUTO_FIELD_CARD_STYLE}>
          <span style={{fontSize: '0.75rem', opacity: 0.7}}>{gettext('Report Query / Template')}</span>
          <pre style={{margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: '0.82rem'}}>
            {content.sql || content.template || fullAsset.name}
          </pre>
        </div>
      </Box>
    );
  }

  return (
    <Box sx={{display: 'grid', gap: 1.5, p: 2}}>
      <TextArea
        rows={10}
        label={gettext('Document / Note / Transcript Content')}
        value={docDraft}
        onChange={(e) => setDocDraft(e.target.value)}
      />
      <Box sx={{display: 'flex', justifyContent: 'flex-end'}}>
        <Button intent="primary" loading={saving} onClick={saveDocumentBody}>
          {gettext('Save changes')}
        </Button>
      </Box>
    </Box>
  );
}

ProjectLocalAssetViewer.propTypes = {
  project: PropTypes.object.isRequired,
  asset: PropTypes.object.isRequired,
  client: PropTypes.object.isRequired,
  onAssetUpdated: PropTypes.func,
};

export function ProjectExplorer({
  client: suppliedClient,
  onOpenAsset,
  onSelectAsset,
  onOpenDatabaseObject,
  onCreateProject,
  modules = [],
  variant = 'tree',
}) {
  useLocaleRevision();
  const client = useMemo(
    () => suppliedClient ?? new ProjectAssetClient(),
    [suppliedClient]
  );
  const [projects, setProjects] = useState([]);
  const [expanded, setExpanded] = useState(new Set(['__platform_modules__']));
  const [selectedNodeId, setSelectedNodeId] = useState('');
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [activeSelection, setActiveSelection] = useState(() => sharedNavSelection);
  const [states, setStates] = useState({});
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [createDraft, setCreateDraft] = useState({
    id: '',
    name: '',
    description: '',
    parentProjectId: '',
  });
  const [createError, setCreateError] = useState('');
  const [reparentTarget, setReparentTarget] = useState(null);
  const [reparentValue, setReparentValue] = useState('');
  const [reparentError, setReparentError] = useState('');
  const [saving, setSaving] = useState(false);

  const loadProject = useCallback(
    async (project) => {
      if (!project?.project_id) return null;
      setStates((current) => ({
        ...current,
        [project.project_id]: {...current[project.project_id], loading: true},
      }));
      try {
        const state = await client.project(project.project_id);
        setStates((current) => ({...current, [project.project_id]: state}));
        return state;
      } catch (loadError) {
        setStates((current) => ({
          ...current,
          [project.project_id]: {error: loadError.message},
        }));
        return null;
      }
    },
    [client]
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const list = await client.listProjects();
      setProjects(list);
      if (variant === 'workspace' && list.length > 0 && !sharedNavSelection) {
        const firstRoot =
          list.find((p) => !p.parent_project_id) || list[0];
        const state = client.project ? await loadProject(firstRoot) : null;
        const initSel = {
          kind: 'project',
          projectId: firstRoot.project_id,
          virtualId: null,
          item: null,
          state,
        };
        setActiveSelection(initSel);
      }
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }, [client, variant, loadProject]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const onNav = (event) => {
      const detail = event.detail;
      if (!detail) return;
      setActiveSelection(detail);
      if (detail.projectId) {
        setSelectedProjectId(detail.projectId);
        const proj = projects.find((p) => p.project_id === detail.projectId);
        if (proj && !states[detail.projectId] && client.project) {
          loadProject(proj);
        }
      }
      if (detail.virtualId) {
        setSelectedNodeId(detail.virtualId);
      } else if (detail.projectId) {
        setSelectedNodeId(`proj:${detail.projectId}`);
      }
    };
    window.addEventListener(NAV_EVENT, onNav);
    return () => window.removeEventListener(NAV_EVENT, onNav);
  }, [projects, states, client, loadProject]);

  const beginCreate = useCallback(() => {
    if (onCreateProject) return onCreateProject();
    setCreateDraft({
      id: '',
      name: '',
      description: '',
      parentProjectId: selectedProjectId || '',
    });
    setCreateError('');
    setCreateOpen(true);
  }, [onCreateProject, selectedProjectId]);

  useEffect(() => {
    if (variant !== 'tree') return undefined;
    const listener = () => beginCreate();
    window.addEventListener('cdeadmin:project-create', listener);
    return () => window.removeEventListener('cdeadmin:project-create', listener);
  }, [beginCreate, variant]);

  const createProject = async () => {
    const id = createDraft.id.trim();
    if (!/^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,255}$/.test(id)) {
      setCreateError('Project ID must be a stable identifier without spaces.');
      return;
    }
    if (
      createDraft.parentProjectId &&
      !canAssignProjectParent(projects, id, createDraft.parentProjectId)
    ) {
      setCreateError(
        'Selected parent project would create a circular dependency.'
      );
      return;
    }
    setSaving(true);
    setCreateError('');
    try {
      const payload = {
        name: createDraft.name.trim() || id,
        description: createDraft.description,
      };
      if (createDraft.parentProjectId) {
        payload.parent_project_id = createDraft.parentProjectId;
      }
      await client.createProject(id, payload);
      setCreateOpen(false);
      if (createDraft.parentProjectId) {
        setExpanded(
          (prev) =>
            new Set([
              ...prev,
              createDraft.parentProjectId,
              `virt:${createDraft.parentProjectId}:projects`,
            ])
        );
      }
      await refresh();
    } catch (saveError) {
      setCreateError(saveError.message);
    } finally {
      setSaving(false);
    }
  };

  const selectedProject = useMemo(
    () => projects.find((p) => p.project_id === selectedProjectId) || null,
    [projects, selectedProjectId]
  );

  const beginReparent = () => {
    if (!selectedProject) return;
    setReparentTarget(selectedProject);
    setReparentValue(selectedProject.parent_project_id || '');
    setReparentError('');
  };

  const saveReparent = async () => {
    if (!reparentTarget) return;
    if (
      !canAssignProjectParent(
        projects,
        reparentTarget.project_id,
        reparentValue
      )
    ) {
      setReparentError('Circular project dependency loop is not allowed.');
      return;
    }
    setSaving(true);
    setReparentError('');
    try {
      await client.updateProject(reparentTarget.project_id, {
        expected_revision: reparentTarget.revision ?? 0,
        parent_project_id: reparentValue || null,
      });
      setReparentTarget(null);
      if (reparentValue) {
        setExpanded(
          (prev) =>
            new Set([
              ...prev,
              reparentValue,
              `virt:${reparentValue}:projects`,
            ])
        );
      }
      await refresh();
    } catch (saveErr) {
      setReparentError(saveErr.message);
    } finally {
      setSaving(false);
    }
  };

  const {roots, childrenMap, byId} = useMemo(
    () => buildProjectHierarchy(projects),
    [projects]
  );

  const autoExpandSmallVirtuals = useCallback(
    (project, loadedState, baseExpanded) => {
      const next = new Set(baseExpanded);
      const childProjects = childrenMap.get(project.project_id) || [];
      const vnodes = buildProjectVirtualTree(
        project,
        loadedState,
        childProjects
      );
      for (const vnode of vnodes) {
        if (vnode.key === 'projects' && childProjects.length > 0 && childProjects.length <= 12) {
          next.add(vnode.id);
        } else if (vnode.totalCount > 0 && vnode.totalCount <= 8) {
          next.add(vnode.id);
          for (const sg of vnode.subgroups || []) {
            if ((sg.items?.length || 0) > 0 && sg.items.length <= 8) {
              next.add(sg.id);
            }
          }
        }
      }
      return next;
    },
    [childrenMap]
  );

  const toggleProject = async (project) => {
    const pid = project.project_id;
    setSelectedProjectId(pid);
    setSelectedNodeId(`proj:${pid}`);

    if (expanded.has(pid)) {
      const next = new Set(expanded);
      next.delete(pid);
      setExpanded(next);
      publishNavSelection({
        kind: 'project',
        projectId: pid,
        virtualId: null,
        item: null,
      });
      return;
    }

    let projState = states[pid];
    let next = new Set(expanded);
    next.add(pid);
    const childProjects = childrenMap.get(pid) || [];
    if (childProjects.length > 0 && childProjects.length <= 12) {
      next.add(`virt:${pid}:projects`);
    }
    setExpanded(next);

    if (!projState && client.project) {
      projState = await loadProject(project);
    }
    if (projState) {
      setExpanded((prev) => autoExpandSmallVirtuals(project, projState, prev));
    }
    publishNavSelection({
      kind: 'project',
      projectId: pid,
      virtualId: null,
      item: null,
    });
  };

  const toggleVirtual = (project, vnodeId) => {
    setSelectedProjectId(project.project_id);
    setSelectedNodeId(vnodeId);
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(vnodeId)) next.delete(vnodeId);
      else next.add(vnodeId);
      return next;
    });
    publishNavSelection({
      kind: 'virtual',
      projectId: project.project_id,
      virtualId: vnodeId,
      item: null,
    });
  };

  const handleOpenLeafItem = (leaf) => {
    if (leaf.itemKind === 'db-object') {
      if (onOpenDatabaseObject) {
        onOpenDatabaseObject(leaf.project, leaf.dbObject);
        return;
      }
      if (typeof window !== 'undefined') {
        const kind = leaf.dbObject.kind;
        const name = leaf.dbObject.nativeIdentity;
        const sqlByKind = {
          table: `SELECT FIRST 100 *\nFROM ${name};`,
          view: `SELECT FIRST 100 *\nFROM ${name};`,
          procedure: `SELECT TRIM(RDB$PROCEDURE_NAME) AS PROCEDURE_NAME, RDB$PROCEDURE_SOURCE\nFROM RDB$PROCEDURES\nWHERE TRIM(RDB$PROCEDURE_NAME) = '${name}';`,
          package: `SELECT TRIM(RDB$PACKAGE_NAME) AS PACKAGE_NAME, RDB$PACKAGE_HEADER_SOURCE, RDB$PACKAGE_BODY_SOURCE\nFROM RDB$PACKAGES\nWHERE TRIM(RDB$PACKAGE_NAME) = '${name}';`,
          function: `SELECT TRIM(RDB$FUNCTION_NAME) AS FUNCTION_NAME, RDB$FUNCTION_SOURCE\nFROM RDB$FUNCTIONS\nWHERE TRIM(RDB$FUNCTION_NAME) = '${name}';`,
          sequence: `SELECT TRIM(RDB$GENERATOR_NAME) AS SEQUENCE_NAME, RDB$INITIAL_VALUE, RDB$GENERATOR_INCREMENT\nFROM RDB$GENERATORS\nWHERE TRIM(RDB$GENERATOR_NAME) = '${name}';`,
        };
        window.dispatchEvent(
          new CustomEvent('scratchrobin:open-app-surface', {
            detail: {
              appId: 'sql-editor',
              options: {
                title: `${kind}: ${name}`,
                initialSql: sqlByKind[kind] || `SELECT FIRST 100 * FROM ${name};`,
                databaseTargetId: leaf.dbObject.databaseTargetId,
              },
            },
          })
        );
      }
      return;
    }
    if (leaf.itemKind === 'asset') {
      if (PROJECT_LOCAL_ASSET_TYPES.has(leaf.asset.asset_type)) {
        publishNavSelection({
          kind: 'local-asset',
          projectId: leaf.project.project_id,
          virtualId: null,
          item: leaf,
        });
        return;
      }
      onOpenAsset?.(leaf.project, leaf.asset);
    }
  };

  const handleSelectLeafItem = (leaf) => {
    setSelectedProjectId(leaf.project.project_id);
    setSelectedNodeId(leaf.id);
    if (leaf.itemKind === 'asset') {
      onSelectAsset?.(leaf.project, leaf.asset);
      if (PROJECT_LOCAL_ASSET_TYPES.has(leaf.asset.asset_type)) {
        publishNavSelection({
          kind: 'local-asset',
          projectId: leaf.project.project_id,
          virtualId: null,
          item: leaf,
        });
      }
    } else if (leaf.itemKind === 'member') {
      publishNavSelection({
        kind: 'member',
        projectId: leaf.project.project_id,
        virtualId: null,
        item: leaf,
      });
    }
  };

  const filter = query.trim().toLowerCase();

  const matchingIds = useMemo(() => {
    if (!filter) return new Set(projects.map((p) => p.project_id));
    const matched = new Set();
    const checkSubtree = (proj, visited = new Set()) => {
      if (visited.has(proj.project_id)) return false;
      visited.add(proj.project_id);
      const st = states[proj.project_id];
      const selfMatches =
        `${proj.name} ${proj.project_id}`.toLowerCase().includes(filter) ||
        (st?.assets ?? []).some(
          (asset) =>
            `${asset.name} ${asset.path} ${asset.asset_type}`
              .toLowerCase()
              .includes(filter) ||
            (asset.resource_bindings ?? []).some((rb) =>
              String(rb?.nativeIdentity || rb?.resource_id || '')
                .toLowerCase()
                .includes(filter)
            )
        );
      let childMatches = false;
      for (const child of childrenMap.get(proj.project_id) || []) {
        if (checkSubtree(child, visited)) childMatches = true;
      }
      if (selfMatches || childMatches) {
        matched.add(proj.project_id);
        return true;
      }
      return false;
    };
    for (const root of roots) checkSubtree(root);
    return matched;
  }, [projects, filter, states, childrenMap, roots]);

  const visibleRoots = roots.filter((p) => matchingIds.has(p.project_id));

  // =========================================================================
  // WORKSPACE VARIANT (Area 3e cooperative Project Manager view)
  // =========================================================================
  if (variant === 'workspace') {
    const activeProj =
      (activeSelection?.projectId && byId.get(activeSelection.projectId)) ||
      visibleRoots[0] ||
      null;
    if (loading && !activeProj) {
      return <ProgressOverlay message={gettext('Loading projects')} />;
    }
    if (!activeProj) {
      return (
        <EmptyState
          message={gettext(
            'Select a project or virtual folder in the Project Navigator on the left to inspect its items.'
          )}
        />
      );
    }

    const activeState = states[activeProj.project_id];
    const childProjects = childrenMap.get(activeProj.project_id) || [];
    const virtualTree = buildProjectVirtualTree(
      activeProj,
      activeState,
      childProjects
    );
    const parentProj = activeProj.parent_project_id
      ? byId.get(activeProj.parent_project_id)
      : null;

    if (activeSelection?.kind === 'local-asset' && activeSelection.item?.asset) {
      const leaf = activeSelection.item;
      return (
        <ScratchScrollArea orientation="both" style={{height: '100%', minHeight: 0}}>
          <Box sx={{p: 2, display: 'grid', gap: 1.5}}>
            <Box sx={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1}}>
              <Box sx={{display: 'flex', alignItems: 'center', gap: 1}}>
                <Icon iconKey={leaf.iconKey} decorative />
                <strong style={{fontSize: '1rem'}}>{leaf.label}</strong>
              </Box>
              <Button
                onClick={() =>
                  publishNavSelection({
                    kind: 'project',
                    projectId: activeProj.project_id,
                    virtualId: null,
                    item: null,
                  })
                }
              >
                {gettext('Back to Project')}
              </Button>
            </Box>
            <ProjectLocalAssetViewer
              project={activeProj}
              asset={leaf.asset}
              client={client}
              onAssetUpdated={loadProject}
            />
          </Box>
        </ScratchScrollArea>
      );
    }

    const foundVirtual = activeSelection?.virtualId
      ? findVirtualNodeById(virtualTree, activeSelection.virtualId)
      : null;

    if (foundVirtual) {
      const {node: vnode, trail} = foundVirtual;
      const cards = [
        ...(vnode.childProjects || []).map((cp) => ({
          id: `cp:${cp.project_id}`,
          label: cp.name,
          subtitle: cp.project_id,
          badge: gettext('Project'),
          iconKey: 'folder.system',
          onActivate: () => {
            if (!states[cp.project_id] && client.project) loadProject(cp);
            publishNavSelection({
              kind: 'project',
              projectId: cp.project_id,
              virtualId: null,
              item: null,
            });
          },
        })),
        ...(vnode.subgroups || []).map((sg) => ({
          id: sg.id,
          label: sg.label,
          subtitle: gettext('Virtual folder'),
          badge: `${sg.totalCount}`,
          iconKey: sg.iconKey,
          onActivate: () =>
            publishNavSelection({
              kind: 'virtual',
              projectId: activeProj.project_id,
              virtualId: sg.id,
              item: null,
            }),
        })),
        ...(vnode.items || []).map((item) => ({
          id: item.id,
          label: item.label,
          subtitle:
            item.itemKind === 'db-object'
              ? `${item.dbObject.kind.toUpperCase()} · ${item.dbObject.scope || 'Firebird'}`
              : item.asset?.path || item.member?.principal_type || '',
          badge: item.badge || '',
          iconKey: item.iconKey,
          onActivate: () => handleOpenLeafItem(item),
        })),
      ];

      return (
        <ScratchScrollArea orientation="both" style={{height: '100%', minHeight: 0}}>
          <Box sx={{p: 2, display: 'grid', gap: 2}}>
            <Box sx={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1}}>
              <Box sx={{display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap'}}>
                <Button
                  onClick={() =>
                    publishNavSelection({
                      kind: 'project',
                      projectId: activeProj.project_id,
                      virtualId: null,
                      item: null,
                    })
                  }
                >
                  {activeProj.name}
                </Button>
                {trail.map((step) => (
                  <span key={step.id} style={{fontWeight: 600}}>
                    {' / '}
                    {step.label}
                  </span>
                ))}
              </Box>
              <span style={{fontSize: '0.82rem', opacity: 0.75}}>
                {cards.length} {gettext('items')}
              </span>
            </Box>
            {cards.length === 0 ? (
              <EmptyState message={gettext('No items are currently linked under this virtual folder.')} />
            ) : (
              <div
                data-testid="virtual-group-buttons-grid"
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))',
                  gap: '10px',
                }}
              >
                {cards.map((card) => (
                  <button
                    key={card.id}
                    type="button"
                    style={VIRTUAL_ITEM_BTN_STYLE}
                    onClick={card.onActivate}
                  >
                    <Icon iconKey={card.iconKey} decorative />
                    <div style={{flex: 1, minWidth: 0}}>
                      <div style={{fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>
                        {card.label}
                      </div>
                      {card.subtitle && (
                        <div style={{fontSize: '0.74rem', opacity: 0.7, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>
                          {card.subtitle}
                        </div>
                      )}
                    </div>
                    {card.badge && (
                      <span style={{fontSize: '0.72rem', opacity: 0.75, padding: '2px 6px', borderRadius: 4, border: '1px solid rgba(128,128,128,0.28)'}}>
                        {card.badge}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </Box>
        </ScratchScrollArea>
      );
    }

    // Default Project Overview: Auto-placing property fields + Virtual Spot Buttons!
    const propFields = [
      {label: gettext('Project Name'), value: activeProj.name},
      {label: gettext('Project ID'), value: activeProj.project_id},
      {
        label: gettext('Parent Project'),
        value: parentProj ? `${parentProj.name} (${parentProj.project_id})` : gettext('None (Top-Level)'),
      },
      {label: gettext('Access'), value: activeProj.access || 'owner'},
      {label: gettext('Child Projects'), value: String(childProjects.length)},
      {
        label: gettext('Linked Tables'),
        value: String(virtualTree.find((v) => v.key === 'tables')?.totalCount ?? 0),
      },
      {
        label: gettext('Views & Coding'),
        value: String(
          (virtualTree.find((v) => v.key === 'views')?.totalCount ?? 0) +
            (virtualTree.find((v) => v.key === 'coding')?.totalCount ?? 0)
        ),
      },
      {
        label: gettext('Screens & Reports'),
        value: String(
          (virtualTree.find((v) => v.key === 'screens')?.totalCount ?? 0) +
            (virtualTree.find((v) => v.key === 'reports')?.totalCount ?? 0)
        ),
      },
    ];

    return (
      <ScratchScrollArea orientation="both" style={{height: '100%', minHeight: 0}}>
        <Box sx={{p: 2, display: 'grid', gap: 2.5}}>
          <Box sx={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap'}}>
            <Box sx={{display: 'flex', alignItems: 'center', gap: 1}}>
              <Icon iconKey={childProjects.length > 0 ? 'folder.system' : 'object.schema'} decorative />
              <strong style={{fontSize: '1.05rem'}}>{activeProj.name}</strong>
            </Box>
            {parentProj && (
              <Button
                onClick={() =>
                  publishNavSelection({
                    kind: 'project',
                    projectId: parentProj.project_id,
                    virtualId: null,
                    item: null,
                  })
                }
              >
                ↑ {parentProj.name}
              </Button>
            )}
          </Box>

          {activeProj.description && (
            <div style={AUTO_FIELD_CARD_STYLE}>
              <span style={{fontSize: '0.75rem', opacity: 0.7}}>{gettext('Description')}</span>
              <div>{activeProj.description}</div>
            </div>
          )}

          <div
            data-testid="auto-placing-properties-grid"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))',
              gap: '10px',
            }}
          >
            {propFields.map((f) => (
              <div key={f.label} style={AUTO_FIELD_CARD_STYLE}>
                <span style={{fontSize: '0.74rem', opacity: 0.7}}>{f.label}</span>
                <strong style={{overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>
                  {f.value}
                </strong>
              </div>
            ))}
          </div>

          <Box sx={{display: 'grid', gap: 1}}>
            <strong style={{fontSize: '0.88rem'}}>{gettext('Project Virtual Sections')}</strong>
            <div
              data-testid="virtual-group-buttons-grid"
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
                gap: '10px',
              }}
            >
              {virtualTree.map((vnode) => (
                <button
                  key={vnode.id}
                  type="button"
                  style={VIRTUAL_ITEM_BTN_STYLE}
                  onClick={() =>
                    publishNavSelection({
                      kind: 'virtual',
                      projectId: activeProj.project_id,
                      virtualId: vnode.id,
                      item: null,
                    })
                  }
                >
                  <Icon iconKey={vnode.iconKey} decorative />
                  <div style={{flex: 1, minWidth: 0}}>
                    <div style={{fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>
                      {gettext(vnode.label)}
                    </div>
                    <div style={{fontSize: '0.74rem', opacity: 0.7}}>
                      {gettext('Virtual group')}
                    </div>
                  </div>
                  <span style={{fontSize: '0.75rem', fontWeight: 600, opacity: 0.8}}>
                    {vnode.totalCount}
                  </span>
                </button>
              ))}
            </div>
          </Box>
        </Box>
      </ScratchScrollArea>
    );
  }

  // =========================================================================
  // TREE VARIANT (Area 3a Left Drawer Project Navigator Tree)
  // =========================================================================
  const itemMatchesFilter = (item) =>
    !filter ||
    `${item.label} ${item.asset?.path || ''} ${item.asset?.asset_type || ''}`
      .toLowerCase()
      .includes(filter);

  const renderLeafItems = (items, level) =>
    items.filter(itemMatchesFilter).map((item, idx, arr) => (
      <TreeRow
        key={item.id}
        level={level}
        label={item.label}
        selected={selectedNodeId === item.id}
        isLast={idx === arr.length - 1}
        icon={<Icon iconKey={item.iconKey} decorative />}
        warning={item.warning ? gettext(item.warning) : ''}
        trailing={item.badge || ''}
        onSelect={() => handleSelectLeafItem(item)}
        onOpen={() => handleOpenLeafItem(item)}
      />
    ));

  const renderVirtualNode = (project, vnode, level, isLast, visitedProjects) => {
    const projectSelfMatches =
      !filter ||
      `${project.name} ${project.project_id}`.toLowerCase().includes(filter);
    const filteredChildProjects = (vnode.childProjects || []).filter((cp) =>
      matchingIds.has(cp.project_id)
    );
    const filteredItems = projectSelfMatches
      ? vnode.items || []
      : (vnode.items || []).filter(itemMatchesFilter);
    const filteredSubgroups = (vnode.subgroups || []).filter((sg) => {
      if (!filter || projectSelfMatches) return true;
      return (sg.items || []).some(itemMatchesFilter);
    });

    if (
      filter &&
      !projectSelfMatches &&
      !filteredChildProjects.length &&
      !filteredItems.length &&
      !filteredSubgroups.length
    ) {
      return null;
    }

    const isExpanded = expanded.has(vnode.id) || Boolean(filter);

    return (
      <Box key={vnode.id} role="group">
        <TreeRow
          level={level}
          label={gettext(vnode.label)}
          selected={selectedNodeId === vnode.id}
          expandable
          expanded={isExpanded}
          isLast={isLast}
          icon={<Icon iconKey={vnode.iconKey} decorative />}
          trailing={`${vnode.totalCount}`}
          onSelect={() => {
            setSelectedProjectId(project.project_id);
            setSelectedNodeId(vnode.id);
            publishNavSelection({
              kind: 'virtual',
              projectId: project.project_id,
              virtualId: vnode.id,
              item: null,
            });
          }}
          onToggle={() => toggleVirtual(project, vnode.id)}
          onOpen={() => toggleVirtual(project, vnode.id)}
        />
        {isExpanded &&
          filteredChildProjects.map((childProj, cIdx) =>
            renderProjectSubtree(
              childProj,
              level + 1,
              cIdx === filteredChildProjects.length - 1 &&
                !filteredSubgroups.length &&
                !filteredItems.length,
              visitedProjects
            )
          )}
        {isExpanded &&
          filteredSubgroups.map((sg, sIdx) =>
            renderVirtualNode(
              project,
              sg,
              level + 1,
              sIdx === filteredSubgroups.length - 1 && !filteredItems.length,
              visitedProjects
            )
          )}
        {isExpanded && renderLeafItems(filteredItems, level + 1)}
      </Box>
    );
  };

  const renderProjectSubtree = (
    project,
    level,
    isLastSibling,
    visited = new Set()
  ) => {
    if (visited.has(project.project_id)) return null;
    const nextVisited = new Set(visited);
    nextVisited.add(project.project_id);

    const isExpanded = expanded.has(project.project_id) || Boolean(filter);
    const state = states[project.project_id];
    const childProjects = (childrenMap.get(project.project_id) || []).filter(
      (ch) => matchingIds.has(ch.project_id)
    );
    const virtualNodes = buildProjectVirtualTree(
      project,
      state,
      childProjects
    );

    const accessLabel =
      project.access === 'owner' ? gettext('Owner') : project.access;
    const trailing =
      childProjects.length > 0 ? `${childProjects.length} sub` : accessLabel;

    return (
      <Box key={project.project_id} role="group">
        <TreeRow
          level={level}
          label={project.name}
          selected={selectedNodeId === `proj:${project.project_id}`}
          expandable
          expanded={isExpanded}
          isLast={isLastSibling}
          loading={state?.loading}
          warning={state?.error ?? ''}
          icon={
            <Icon
              iconKey={childProjects.length > 0 ? 'folder.system' : 'object.schema'}
              decorative
            />
          }
          trailing={trailing}
          onSelect={() => {
            setSelectedProjectId(project.project_id);
            setSelectedNodeId(`proj:${project.project_id}`);
            if (!state && client.project) loadProject(project);
            publishNavSelection({
              kind: 'project',
              projectId: project.project_id,
              virtualId: null,
              item: null,
            });
          }}
          onToggle={() => toggleProject(project)}
          onOpen={() => toggleProject(project)}
        />
        {isExpanded && state?.error && (
          <Box role="alert" sx={{pl: (level + 2) * 1.5, py: 0.75}}>
            {state.error}{' '}
            <Button onClick={() => loadProject(project)}>
              {gettext('Retry')}
            </Button>
          </Box>
        )}
        {isExpanded &&
          !state?.error &&
          virtualNodes.map((vnode, vIdx) =>
            renderVirtualNode(
              project,
              vnode,
              level + 1,
              vIdx === virtualNodes.length - 1,
              nextVisited
            )
          )}
      </Box>
    );
  };

  const reparentForbiddenIds = useMemo(() => {
    if (!reparentTarget) return new Set();
    const desc = collectDescendantProjectIds(
      projects,
      reparentTarget.project_id
    );
    desc.add(reparentTarget.project_id);
    return desc;
  }, [projects, reparentTarget]);

  return (
    <Box
      component="section"
      aria-label={gettext('Project Navigator')}
      sx={{height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column'}}
    >
      <Toolbar
        label={gettext('Project Navigator commands')}
        trailing={<FormReference formKey="project-explorer" />}
      >
        <Button onClick={beginCreate}>{gettext('New project')}</Button>
        {selectedProject && client.updateProject && (
          <Button onClick={beginReparent}>{gettext('Set parent')}</Button>
        )}
        <Button onClick={refresh}>{gettext('Refresh')}</Button>
      </Toolbar>
      <Box sx={{p: 0.5}}>
        <SearchField
          label={gettext('Filter projects and assets')}
          value={query}
          onChange={setQuery}
          resultCount={matchingIds.size}
        />
      </Box>
      <ScratchScrollArea orientation="both" style={{flex: 1, minHeight: 0}}>
        <Box
          role="tree"
          aria-label={gettext('Projects and authored assets')}
          sx={{position: 'relative', minHeight: 120, p: 0.5}}
        >
          {error && (
            <EmptyState
              role="alert"
              message={error}
              actionLabel={gettext('Retry')}
              onAction={refresh}
            />
          )}
          {!error && !loading && !visibleRoots.length && (
            <EmptyState
              message={gettext(
                'No projects match this view. Create a project to store queries, diagrams, models, and other authored assets.'
              )}
              actionLabel={gettext('New project')}
              onAction={beginCreate}
            />
          )}
          {!error &&
            visibleRoots.map((project, pIdx) =>
              renderProjectSubtree(
                project,
                1,
                pIdx === visibleRoots.length - 1 && !modules.length
              )
            )}
          {modules.length > 0 &&
            (() => {
              const visibleModules = modules.filter(
                (mod) =>
                  !filter ||
                  `${mod.label} ${mod.id}`.toLowerCase().includes(filter)
              );
              if (!visibleModules.length) return null;
              const modulesExpanded = expanded.has('__platform_modules__');
              const toggleModules = () => {
                const next = new Set(expanded);
                if (next.has('__platform_modules__')) {
                  next.delete('__platform_modules__');
                } else {
                  next.add('__platform_modules__');
                }
                setExpanded(next);
              };
              return (
                <Box key="__platform_modules__" role="group">
                  <TreeRow
                    level={1}
                    label={gettext('Platform Modules')}
                    expandable
                    expanded={modulesExpanded}
                    isLast
                    icon={<Icon iconKey="tool.project-explorer" decorative />}
                    trailing={`${visibleModules.length}`}
                    onToggle={toggleModules}
                    onOpen={toggleModules}
                  />
                  {modulesExpanded &&
                    visibleModules.map((mod, mIdx) => (
                      <TreeRow
                        level={2}
                        key={mod.id}
                        label={mod.label}
                        isLast={mIdx === visibleModules.length - 1}
                        icon={
                          <Icon
                            iconKey={mod.iconKey || 'command.default'}
                            decorative
                          />
                        }
                        onSelect={() => mod.onOpen?.()}
                        onOpen={() => mod.onOpen?.()}
                      />
                    ))}
                </Box>
              );
            })()}
          <ProgressOverlay
            message={loading ? gettext('Loading projects') : ''}
          />
        </Box>
      </ScratchScrollArea>
      <Dialog
        open={createOpen}
        title={gettext('New project')}
        size="medium"
        formKey="project-explorer"
        onClose={() => !saving && setCreateOpen(false)}
        busy={saving}
        validationError={createError}
        defaultAction={createProject}
        actions={
          <>
            <Button disabled={saving} onClick={() => setCreateOpen(false)}>
              {gettext('Cancel')}
            </Button>
            <Button intent="primary" loading={saving} onClick={createProject}>
              {gettext('Create project')}
            </Button>
          </>
        }
      >
        <Box sx={{display: 'grid', gap: 2}}>
          <TextField
            autoFocus
            required
            label={gettext('Project ID')}
            value={createDraft.id}
            onChange={(event) =>
              setCreateDraft((current) => ({
                ...current,
                id: event.target.value,
              }))
            }
            helperText={gettext(
              'Stable identity used by assets and source control.'
            )}
          />
          <TextField
            label={gettext('Project name')}
            value={createDraft.name}
            onChange={(event) =>
              setCreateDraft((current) => ({
                ...current,
                name: event.target.value,
              }))
            }
          />
          {projects.length > 0 && (
            <div className="sr-field">
              <label htmlFor="sr-project-parent-select" className="sr-field-label">
                {gettext('Parent project')}
              </label>
              <select
                id="sr-project-parent-select"
                aria-label={gettext('Parent project')}
                className="sr-input"
                value={createDraft.parentProjectId}
                onChange={(event) =>
                  setCreateDraft((current) => ({
                    ...current,
                    parentProjectId: event.target.value,
                  }))
                }
              >
                <option value="">{gettext('None (top-level project)')}</option>
                {projects.map((item) => (
                  <option key={item.project_id} value={item.project_id}>
                    {item.name} ({item.project_id})
                  </option>
                ))}
              </select>
            </div>
          )}
          <TextArea
            label={gettext('Description')}
            value={createDraft.description}
            onChange={(event) =>
              setCreateDraft((current) => ({
                ...current,
                description: event.target.value,
              }))
            }
          />
        </Box>
      </Dialog>
      <Dialog
        open={Boolean(reparentTarget)}
        title={gettext('Set parent project')}
        size="small"
        formKey="project-explorer"
        onClose={() => !saving && setReparentTarget(null)}
        busy={saving}
        validationError={reparentError}
        defaultAction={saveReparent}
        actions={
          <>
            <Button disabled={saving} onClick={() => setReparentTarget(null)}>
              {gettext('Cancel')}
            </Button>
            <Button intent="primary" loading={saving} onClick={saveReparent}>
              {gettext('Save parent')}
            </Button>
          </>
        }
      >
        <Box sx={{display: 'grid', gap: 2}}>
          <div className="sr-field">
            <label htmlFor="sr-reparent-project-select" className="sr-field-label">
              {gettext('Parent project')}
            </label>
            <select
              id="sr-reparent-project-select"
              aria-label={gettext('Parent project')}
              className="sr-input"
              value={reparentValue}
              onChange={(event) => setReparentValue(event.target.value)}
            >
              <option value="">{gettext('None (top-level project)')}</option>
              {projects
                .filter((item) => !reparentForbiddenIds.has(item.project_id))
                .map((item) => (
                  <option key={item.project_id} value={item.project_id}>
                    {item.name} ({item.project_id})
                  </option>
                ))}
            </select>
          </div>
        </Box>
      </Dialog>
    </Box>
  );
}

ProjectExplorer.propTypes = {
  client: PropTypes.object,
  onOpenAsset: PropTypes.func,
  onSelectAsset: PropTypes.func,
  onOpenDatabaseObject: PropTypes.func,
  onCreateProject: PropTypes.func,
  modules: PropTypes.array,
  variant: PropTypes.oneOf(['tree', 'workspace']),
};
