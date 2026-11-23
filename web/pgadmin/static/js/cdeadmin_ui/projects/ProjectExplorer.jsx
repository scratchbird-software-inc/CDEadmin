/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import cn from 'classnames';
import gettext from 'sources/gettext';
import {useLocaleRevision} from '../actions/t_actions';
import {Box} from '../primitives/Layout';
import {ensureScratchBaseStyles} from '../base/ScratchBaseStyles';
import {ScratchScrollArea} from '../base/ScratchScrollArea';
import {Icon, ObjectIcon} from '../icons';
import {ProjectAssetClient} from './ProjectAssetClient';
import {Button} from '../primitives/Button';
import {TextArea, TextField} from '../primitives/Field';
import {SearchField} from '../primitives/AdvancedControls';
import {readBranchedTreePreferences} from '../navigation/ScratchBranchedTree';
import ContextMenu from '../navigation/ContextMenu';
import {TreeBranchGuides} from '../../components/PgTree/FileTreeItem/TreeBranchGuides';
import {Dialog} from '../overlays/Dialog';
import {EmptyState} from '../feedback/EmptyState';
import {ProgressOverlay} from '../feedback/ProgressOverlay';
import FormReference from '../navigation/FormReference';
import {
  PROJECT_LOCAL_ASSET_TYPES,
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
    window.dispatchEvent(new CustomEvent(NAV_EVENT, {detail: selection}));
  }
}

function safeToken(value) {
  return String(value || '')
    .replaceAll('/', '_')
    .replaceAll(':', '~')
    .replaceAll(' ', '_');
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

const COMPACT_TOOLBAR_BTN_STYLE = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 26,
  height: 26,
  padding: 0,
  borderRadius: 6,
  border: 'none',
  background: 'transparent',
  color: 'var(--sr-accent, #0284c7)',
  cursor: 'pointer',
  flexShrink: 0,
};

function CompactToolbarIconButton({label, iconKey, active = false, onClick}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      style={{
        ...COMPACT_TOOLBAR_BTN_STYLE,
        background: active
          ? 'var(--sr-surface-selected, rgba(2,132,199,0.14))'
          : 'transparent',
      }}
    >
      <Icon iconKey={iconKey} decorative size={16} />
    </button>
  );
}

CompactToolbarIconButton.propTypes = {
  label: PropTypes.string.isRequired,
  iconKey: PropTypes.string.isRequired,
  active: PropTypes.bool,
  onClick: PropTypes.func,
};

/**
 * Renders a single Project Navigator row using the exact same `.file-entry`,
 * `<TreeBranchGuides>`, circular `button.directory-toggle`, `.file-icon`,
 * `.file-name`, and `.text-muted` DOM & stylesheet contract as Data Navigator
 * (`FileTreeItem` + `reactaspen.override.js`).
 */
function ExplorerTreeEntryRow({
  node,
  activeNode,
  branchStepX = 20,
  branchRadius = 8,
  rowHeight = 28,
  onSelect,
  onToggle,
  onActivate,
  onContextMenu,
}) {
  const stepW = Math.max(18, Math.min(28, Number(branchStepX) || 20));
  const slotCenterX = Math.round(stepW / 2);
  const rowH = Math.max(24, Math.round(Number(rowHeight) || 28));
  const midY = Math.round(rowH / 2);
  const showDirectoryToggle = Boolean(node.inode && node.has_children !== false);
  const isDirExpanded = Boolean(node.expanded);
  const showExpandedStem =
    showDirectoryToggle &&
    isDirExpanded &&
    Array.isArray(node.children) &&
    node.children.length > 0;
  const isSelected = Boolean(activeNode && activeNode.id === node.id);
  const siblings = Array.isArray(node.parent?.children)
    ? node.parent.children
    : [];
  const positionInSet = Math.max(1, siblings.indexOf(node) + 1);
  const setSize = Math.max(1, siblings.length);
  const ariaLabelParts = [
    node.label,
    node.object_type || 'object',
    node.info_label ? String(node.info_label).trim() : '',
    node.warning || '',
  ].filter(Boolean);

  return (
    <div
      className={cn(
        'file-entry',
        showDirectoryToggle ? 'directory' : 'file',
        isSelected && 'active',
        `depth-${node.depth}`
      )}
      style={{height: rowH, minHeight: rowH}}
      data-depth={node.depth}
      data-node-kind="object"
      data-object-type={node.object_type || 'object'}
      role="treeitem"
      tabIndex={isSelected ? 0 : -1}
      aria-label={ariaLabelParts.join(', ')}
      aria-expanded={showDirectoryToggle ? isDirExpanded : undefined}
      aria-selected={isSelected}
      aria-level={Math.max(1, Number(node.depth || 1))}
      aria-posinset={positionInSet}
      aria-setsize={setSize}
      onClick={(ev) => {
        ev.stopPropagation();
        onSelect?.(node);
      }}
      onDoubleClick={(ev) => {
        ev.stopPropagation();
        if (showDirectoryToggle) {
          onToggle?.(node);
        } else {
          onActivate?.(node);
        }
      }}
      onContextMenu={(ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        onContextMenu?.(ev, node);
      }}
      onKeyDown={(ev) => {
        if (ev.key === 'Enter') {
          ev.preventDefault();
          if (showDirectoryToggle) onToggle?.(node);
          else onActivate?.(node);
        } else if (ev.key === 'ArrowRight' && showDirectoryToggle && !isDirExpanded) {
          ev.preventDefault();
          onToggle?.(node);
        } else if (ev.key === 'ArrowLeft' && showDirectoryToggle && isDirExpanded) {
          ev.preventDefault();
          onToggle?.(node);
        }
      }}
    >
      <TreeBranchGuides
        item={node}
        activeItem={activeNode}
        stepX={stepW}
        radius={branchRadius}
        hasToggle={showDirectoryToggle}
        rowHeight={rowH}
      />

      {showDirectoryToggle ? (
        <span
          className={cn(
            'directory-toggle-slot',
            showExpandedStem && 'expanded-stem'
          )}
          style={{width: stepW, height: rowH}}
        >
          {showExpandedStem ? (
            <svg
              className="directory-toggle-stem"
              width={stepW}
              height={rowH}
              viewBox={`0 0 ${stepW} ${rowH}`}
              fill="none"
              aria-hidden="true"
            >
              <path
                d={`M ${slotCenterX} ${midY + 7} V ${rowH}`}
                stroke="var(--sr-tree-guide, rgba(71, 85, 105, 0.78))"
                strokeWidth="2.2"
                strokeLinecap="butt"
              />
            </svg>
          ) : null}
          <button
            type="button"
            tabIndex={-1}
            className={cn(
              'directory-toggle',
              isDirExpanded && 'open',
              node.loading && 'loading'
            )}
            aria-label={`${isDirExpanded ? 'Collapse' : 'Expand'} ${node.label}`}
            aria-expanded={isDirExpanded}
            title={`${isDirExpanded ? 'Collapse' : 'Expand'} ${node.label}`}
            onClick={(ev) => {
              ev.preventDefault();
              ev.stopPropagation();
              onToggle?.(node);
            }}
          />
        </span>
      ) : (
        <span className="tree-node-terminal leaf" aria-hidden="true" />
      )}

      <span className="file-label">
        {node.icon_key ? (
          <ObjectIcon
            className="file-icon"
            decorative
            iconKey={node.icon_key}
            objectType={node.object_type || 'object'}
          />
        ) : null}
        <span className="file-name">{node.label}</span>
        {node.info_label ? (
          <span
            className="text-muted"
            style={{fontSize: '0.88em', whiteSpace: 'nowrap', marginLeft: 4}}
          >
            {node.info_label}
          </span>
        ) : null}
      </span>
    </div>
  );
}

ExplorerTreeEntryRow.propTypes = {
  node: PropTypes.object.isRequired,
  activeNode: PropTypes.object,
  branchStepX: PropTypes.number,
  branchRadius: PropTypes.number,
  rowHeight: PropTypes.number,
  onSelect: PropTypes.func,
  onToggle: PropTypes.func,
  onActivate: PropTypes.func,
  onContextMenu: PropTypes.func,
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
      setDocDraft(
        String(loaded?.content?.body || loaded?.content?.markdown || '')
      );
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
    return (
      <EmptyState
        role="alert"
        message={err}
        actionLabel={gettext('Retry')}
        onAction={loadFull}
      />
    );
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
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
            gap: 10,
          }}
        >
          <div style={AUTO_FIELD_CARD_STYLE}>
            <span style={{fontSize: '0.75rem', opacity: 0.7}}>
              {gettext('Status')}
            </span>
            <strong>{curStatus.replace('_', ' ').toUpperCase()}</strong>
          </div>
          <div style={AUTO_FIELD_CARD_STYLE}>
            <span style={{fontSize: '0.75rem', opacity: 0.7}}>
              {gettext('Assignee')}
            </span>
            <strong>{content.assignee || 'Unassigned'}</strong>
          </div>
          <div style={AUTO_FIELD_CARD_STYLE}>
            <span style={{fontSize: '0.75rem', opacity: 0.7}}>
              {gettext('Priority')}
            </span>
            <strong>{content.priority || 'Medium'}</strong>
          </div>
          <div style={AUTO_FIELD_CARD_STYLE}>
            <span style={{fontSize: '0.75rem', opacity: 0.7}}>
              {gettext('Due Date')}
            </span>
            <strong>{content.due_date || '—'}</strong>
          </div>
        </div>
        <div style={AUTO_FIELD_CARD_STYLE}>
          <span style={{fontSize: '0.75rem', opacity: 0.7}}>
            {gettext('Summary')}
          </span>
          <div style={{whiteSpace: 'pre-wrap'}}>
            {content.description || fullAsset.name}
          </div>
        </div>
        <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap'}}>
          <Button
            disabled={saving || curStatus === 'pending'}
            onClick={() => updateTaskStatus('pending')}
          >
            {gettext('Move to Pending')}
          </Button>
          <Button
            disabled={saving || curStatus === 'in_process'}
            onClick={() => updateTaskStatus('in_process')}
          >
            {gettext('Move to In Process')}
          </Button>
          <Button
            intent="primary"
            disabled={saving || curStatus === 'completed'}
            onClick={() => updateTaskStatus('completed')}
          >
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
          {content.summary ||
            (isGantt
              ? gettext('Project Gantt Schedule')
              : gettext('Project Shared & Personal Calendar'))}
        </div>
        {entries.map((entry, idx) => (
          <div key={entry.id || idx} style={AUTO_FIELD_CARD_STYLE}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                gap: 8,
              }}
            >
              <strong>{entry.title}</strong>
              <span style={{fontSize: '0.78rem', opacity: 0.75}}>
                {entry.start} → {entry.end || entry.start}
              </span>
            </div>
            {isGantt && (
              <div
                style={{
                  height: 10,
                  borderRadius: 5,
                  background: 'rgba(128,128,128,0.18)',
                  overflow: 'hidden',
                  marginTop: 4,
                }}
              >
                <div
                  style={{
                    width: `${Math.min(
                      Math.max(Number(entry.progress ?? 50), 5),
                      100
                    )}%`,
                    height: '100%',
                    background: 'var(--sr-accent-primary, #2563eb)',
                  }}
                />
              </div>
            )}
            <span style={{fontSize: '0.78rem', opacity: 0.75}}>
              {entry.owner || 'Team'}
              {isGantt ? ` · ${entry.progress ?? 50}%` : ''}
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
        <div style={{fontSize: '0.85rem', opacity: 0.8}}>
          {content.topic || fullAsset.name}
        </div>
        <div style={{display: 'grid', gap: 8}}>
          {messages.map((m, idx) => (
            <div key={m.id || idx} style={AUTO_FIELD_CARD_STYLE}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontSize: '0.75rem',
                  opacity: 0.75,
                }}
              >
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
          <Button
            intent="primary"
            loading={saving}
            onClick={postChannelMessage}
          >
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
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
            gap: 10,
          }}
        >
          <div style={AUTO_FIELD_CARD_STYLE}>
            <span style={{fontSize: '0.75rem', opacity: 0.7}}>
              {gettext('Format')}
            </span>
            <strong>
              {meta.report_category === 'pdf' ? 'PDF Report' : 'Print Format'}
            </strong>
          </div>
          <div style={AUTO_FIELD_CARD_STYLE}>
            <span style={{fontSize: '0.75rem', opacity: 0.7}}>
              {gettext('Paper / Orientation')}
            </span>
            <strong>{content.paper || 'A4 Portrait'}</strong>
          </div>
          <div style={AUTO_FIELD_CARD_STYLE}>
            <span style={{fontSize: '0.75rem', opacity: 0.7}}>
              {gettext('Source Relation')}
            </span>
            <strong>{content.source_table || '—'}</strong>
          </div>
        </div>
        <div style={AUTO_FIELD_CARD_STYLE}>
          <span style={{fontSize: '0.75rem', opacity: 0.7}}>
            {gettext('Report Query / Template')}
          </span>
          <pre
            style={{
              margin: 0,
              whiteSpace: 'pre-wrap',
              fontFamily: 'monospace',
              fontSize: '0.82rem',
            }}
          >
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
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);

  const client = useMemo(
    () => suppliedClient ?? new ProjectAssetClient(),
    [suppliedClient]
  );
  const hasHostNavigator = typeof client?.navigatorNodes === 'function';
  const hasHostVirtualTree = typeof client?.projectVirtualTree === 'function';

  const [projects, setProjects] = useState([]);
  const [expanded, setExpanded] = useState(
    () => new Set(['virt~__platform_modules__'])
  );
  const [selectedNodeId, setSelectedNodeId] = useState('');
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [activeSelection, setActiveSelection] = useState(
    () => sharedNavSelection
  );
  const [states, setStates] = useState({});
  const [hostNodesByParent, setHostNodesByParent] = useState({});
  const [hostLoadingParents, setHostLoadingParents] = useState(() => new Set());
  const [hostVirtualTrees, setHostVirtualTrees] = useState({});
  const [hostMatchCount, setHostMatchCount] = useState(null);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [contextPos, setContextPos] = useState(null);
  const [contextItemData, setContextItemData] = useState(null);
  const [branchPrefs, setBranchPrefs] = useState(() =>
    readBranchedTreePreferences()
  );
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

  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    const onBranchPrefs = () => setBranchPrefs(readBranchedTreePreferences());
    if (typeof window !== 'undefined') {
      window.addEventListener('scratchrobin:branched-tree-prefs', onBranchPrefs);
    }
    return () => {
      mountedRef.current = false;
      if (typeof window !== 'undefined') {
        window.removeEventListener(
          'scratchrobin:branched-tree-prefs',
          onBranchPrefs
        );
      }
    };
  }, []);

  const filter = query.trim().toLowerCase();

  const loadHostParentSlice = useCallback(
    async (parentToken, activeQuery = '', depth = 0) => {
      if (!hasHostNavigator || depth > 3) return [];
      const cacheKey = `${activeQuery}::${parentToken}`;
      setHostLoadingParents((prev) => new Set([...prev, parentToken]));
      try {
        const resp = await client.navigatorNodes({
          parent: parentToken,
          query: activeQuery,
        });
        if (!mountedRef.current) return [];
        const nodes = Array.isArray(resp?.nodes) ? resp.nodes : [];
        if (typeof resp?.matching_project_count === 'number') {
          setHostMatchCount(resp.matching_project_count);
        }
        setHostNodesByParent((cur) => ({...cur, [cacheKey]: nodes}));
        setHostLoadingParents((prev) => {
          const next = new Set(prev);
          next.delete(parentToken);
          return next;
        });

        // Auto-expand small populated virtual folders returned by the host
        if (parentToken) {
          const autoNodes = nodes.filter(
            (n) => n.inode && n.has_children !== false && n.auto_expand
          );
          if (autoNodes.length > 0) {
            setExpanded((prev) => {
              const next = new Set(prev);
              for (const an of autoNodes) next.add(an.id);
              return next;
            });
            for (const an of autoNodes) {
              await loadHostParentSlice(an.id, activeQuery, depth + 1);
            }
          }
        }
        return nodes;
      } catch (err) {
        if (mountedRef.current) {
          setHostLoadingParents((prev) => {
            const next = new Set(prev);
            next.delete(parentToken);
            return next;
          });
        }
        throw err;
      }
    },
    [client, hasHostNavigator]
  );

  const loadProject = useCallback(
    async (project) => {
      if (!project?.project_id) return null;
      const pid = project.project_id;
      if (hasHostVirtualTree) {
        try {
          const payload = await client.projectVirtualTree(pid);
          if (!mountedRef.current) return null;
          if (payload?.virtual_tree) {
            setHostVirtualTrees((cur) => ({...cur, [pid]: payload}));
          }
          if (payload?.state) {
            setStates((cur) => ({...cur, [pid]: payload.state}));
            return payload.state;
          }
        } catch {
          // Fall back to client.project if needed
        }
      }
      if (!client.project) return null;
      setStates((current) => ({
        ...current,
        [pid]: {...current[pid], loading: true},
      }));
      try {
        const state = await client.project(pid);
        if (!mountedRef.current) return state;
        setStates((current) => ({...current, [pid]: state}));
        return state;
      } catch (loadError) {
        if (!mountedRef.current) return null;
        setStates((current) => ({
          ...current,
          [pid]: {error: loadError.message},
        }));
        return null;
      }
    },
    [client, hasHostVirtualTree]
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const list = await client.listProjects();
      if (!mountedRef.current) return;
      const safeList = Array.isArray(list) ? list : [];
      setProjects(safeList);
      if (variant === 'tree' && hasHostNavigator) {
        await loadHostParentSlice('', filter, 0);
      }
      if (
        variant === 'workspace' &&
        safeList.length > 0 &&
        !sharedNavSelection
      ) {
        const firstRoot =
          safeList.find((p) => !p.parent_project_id) || safeList[0];
        const state = await loadProject(firstRoot);
        if (!mountedRef.current) return;
        setActiveSelection({
          kind: 'project',
          projectId: firstRoot.project_id,
          virtualId: null,
          item: null,
          state,
        });
      }
    } catch (loadError) {
      if (mountedRef.current) {
        setError(loadError.message);
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, [client, variant, hasHostNavigator, loadHostParentSlice, filter, loadProject]);

  useEffect(() => {
    refresh();
  }, [client, variant]);

  // Refresh host root slice when query changes in host-navigator mode
  useEffect(() => {
    if (variant !== 'tree' || !hasHostNavigator || loading) return undefined;
    const cacheKey = `${filter}::`;
    if (hostNodesByParent[cacheKey]) return undefined;
    let active = true;
    loadHostParentSlice('', filter, 0).catch(() => {
      if (!active) return;
    });
    return () => {
      active = false;
    };
  }, [variant, hasHostNavigator, loading, filter, hostNodesByParent, loadHostParentSlice]);

  useEffect(() => {
    const onNav = (event) => {
      const detail = event.detail;
      if (!detail) return;
      setActiveSelection(detail);
      if (detail.projectId) {
        setSelectedProjectId(detail.projectId);
        const proj = projects.find((p) => p.project_id === detail.projectId);
        if (proj && !states[detail.projectId]) {
          loadProject(proj);
        }
      }
      if (detail.virtualId) {
        setSelectedNodeId(safeToken(detail.virtualId));
      } else if (detail.projectId) {
        setSelectedNodeId(`proj~${safeToken(detail.projectId)}`);
      }
    };
    window.addEventListener(NAV_EVENT, onNav);
    return () => window.removeEventListener(NAV_EVENT, onNav);
  }, [projects, states, loadProject]);

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
    return () =>
      window.removeEventListener('cdeadmin:project-create', listener);
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
      setHostNodesByParent({});
      if (createDraft.parentProjectId) {
        const pidTok = safeToken(createDraft.parentProjectId);
        setExpanded(
          (prev) =>
            new Set([
              ...prev,
              `proj~${pidTok}`,
              `virt~${pidTok}~projects`,
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
      setHostNodesByParent({});
      if (reparentValue) {
        const pidTok = safeToken(reparentValue);
        setExpanded(
          (prev) =>
            new Set([
              ...prev,
              `proj~${pidTok}`,
              `virt~${pidTok}~projects`,
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
        if (
          vnode.key === 'projects' &&
          childProjects.length > 0 &&
          childProjects.length <= 12
        ) {
          next.add(safeToken(vnode.id));
        } else if (vnode.totalCount > 0 && vnode.totalCount <= 8) {
          next.add(safeToken(vnode.id));
          for (const sg of vnode.subgroups || []) {
            if ((sg.items?.length || 0) > 0 && sg.items.length <= 8) {
              next.add(safeToken(sg.id));
            }
          }
        }
      }
      return next;
    },
    [childrenMap]
  );

  const handleOpenLeafItem = useCallback(
    (leaf) => {
      if (!leaf) return;
      if (leaf.itemKind === 'module' && typeof leaf.onOpen === 'function') {
        leaf.onOpen();
        return;
      }
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
                  initialSql:
                    sqlByKind[kind] || `SELECT FIRST 100 * FROM ${name};`,
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
    },
    [onOpenAsset, onOpenDatabaseObject]
  );

  const handleSelectLeafItem = useCallback(
    (leaf, nodeId) => {
      if (!leaf) return;
      if (leaf.itemKind === 'module' && typeof leaf.onOpen === 'function') {
        leaf.onOpen();
        return;
      }
      if (leaf.project?.project_id) {
        setSelectedProjectId(leaf.project.project_id);
      }
      if (nodeId) setSelectedNodeId(nodeId);
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
    },
    [onSelectAsset]
  );

  const handleToggleNode = useCallback(
    async (node) => {
      const nodeId = node.id;
      if (node.project_id) {
        setSelectedProjectId(node.project_id);
      }
      setSelectedNodeId(nodeId);

      const wasExpanded = expanded.has(nodeId);
      if (wasExpanded) {
        setExpanded((prev) => {
          const next = new Set(prev);
          next.delete(nodeId);
          return next;
        });
        if (node.nav_payload) {
          publishNavSelection(node.nav_payload);
        }
        return;
      }

      setExpanded((prev) => {
        const next = new Set(prev);
        next.add(nodeId);
        if (node._type === 'cde_project' && node.project_id) {
          const cList = childrenMap.get(node.project_id) || [];
          if (cList.length > 0 && cList.length <= 12) {
            next.add(`virt~${safeToken(node.project_id)}~projects`);
          }
        }
        return next;
      });

      if (hasHostNavigator && nodeId !== 'virt~__platform_modules__') {
        const cacheKey = `${filter}::${nodeId}`;
        if (!hostNodesByParent[cacheKey]) {
          await loadHostParentSlice(nodeId, filter, 0);
        }
      } else if (node._type === 'cde_project' && node.project) {
        let projState = states[node.project_id];
        if (!projState && client.project) {
          projState = await loadProject(node.project);
        }
        if (projState && mountedRef.current) {
          setExpanded((prev) =>
            autoExpandSmallVirtuals(node.project, projState, prev)
          );
        }
      }

      if (node.nav_payload) {
        publishNavSelection(node.nav_payload);
      }
    },
    [
      expanded,
      childrenMap,
      hasHostNavigator,
      filter,
      hostNodesByParent,
      loadHostParentSlice,
      states,
      client.project,
      loadProject,
      autoExpandSmallVirtuals,
    ]
  );

  const handleSelectNode = useCallback(
    (node) => {
      setSelectedNodeId(node.id);
      if (node.project_id) {
        setSelectedProjectId(node.project_id);
      }
      if (node._type === 'cde_project') {
        if (
          !hasHostNavigator &&
          node.project &&
          !states[node.project_id] &&
          client.project
        ) {
          loadProject(node.project);
        }
        publishNavSelection(
          node.nav_payload || {
            kind: 'project',
            projectId: node.project_id,
            virtualId: null,
            item: null,
          }
        );
      } else if (node._type === 'cde_project_virtual') {
        if (node.nav_payload) {
          publishNavSelection(node.nav_payload);
        }
      } else if (node._type === 'cde_project_leaf' && node.leaf) {
        handleSelectLeafItem(node.leaf, node.id);
      }
    },
    [hasHostNavigator, states, client.project, loadProject, handleSelectLeafItem]
  );

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

    const hostPayload = hostVirtualTrees[activeProj.project_id];
    const activeState = states[activeProj.project_id];
    const childProjects =
      hostPayload?.child_projects ||
      childrenMap.get(activeProj.project_id) ||
      [];
    const virtualTree =
      hostPayload?.virtual_tree ||
      buildProjectVirtualTree(activeProj, activeState, childProjects);
    const parentProj =
      hostPayload?.parent_project ??
      (activeProj.parent_project_id
        ? byId.get(activeProj.parent_project_id)
        : null);

    if (
      activeSelection?.kind === 'local-asset' &&
      activeSelection.item?.asset
    ) {
      const leaf = activeSelection.item;
      return (
        <ScratchScrollArea
          orientation="both"
          style={{height: '100%', minHeight: 0}}
        >
          <Box sx={{p: 2, display: 'grid', gap: 1.5}}>
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 1,
              }}
            >
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
            if (!states[cp.project_id]) loadProject(cp);
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
              ? `${item.dbObject.kind.toUpperCase()} · ${
                item.dbObject.scope || 'Firebird'
              }`
              : item.asset?.path || item.member?.principal_type || '',
          badge: item.badge || '',
          iconKey: item.iconKey,
          onActivate: () => handleOpenLeafItem(item),
        })),
      ];

      return (
        <ScratchScrollArea
          orientation="both"
          style={{height: '100%', minHeight: 0}}
        >
          <Box sx={{p: 2, display: 'grid', gap: 2}}>
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: 1,
              }}
            >
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 0.75,
                  flexWrap: 'wrap',
                }}
              >
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
              <EmptyState
                message={gettext(
                  'No items are currently linked under this virtual folder.'
                )}
              />
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
                      <div
                        style={{
                          fontWeight: 600,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {card.label}
                      </div>
                      {card.subtitle && (
                        <div
                          style={{
                            fontSize: '0.74rem',
                            opacity: 0.7,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {card.subtitle}
                        </div>
                      )}
                    </div>
                    {card.badge && (
                      <span
                        style={{
                          fontSize: '0.72rem',
                          opacity: 0.75,
                          padding: '2px 6px',
                          borderRadius: 4,
                          border: '1px solid rgba(128,128,128,0.28)',
                        }}
                      >
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

    const propFields = [
      {label: gettext('Project Name'), value: activeProj.name},
      {label: gettext('Project ID'), value: activeProj.project_id},
      {
        label: gettext('Parent Project'),
        value: parentProj
          ? `${parentProj.name} (${parentProj.project_id})`
          : gettext('None (Top-Level)'),
      },
      {label: gettext('Access'), value: activeProj.access || 'owner'},
      {label: gettext('Child Projects'), value: String(childProjects.length)},
      {
        label: gettext('Linked Tables'),
        value: String(
          virtualTree.find((v) => v.key === 'tables')?.totalCount ?? 0
        ),
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
      <ScratchScrollArea
        orientation="both"
        style={{height: '100%', minHeight: 0}}
      >
        <Box sx={{p: 2, display: 'grid', gap: 2.5}}>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 1,
              flexWrap: 'wrap',
            }}
          >
            <Box sx={{display: 'flex', alignItems: 'center', gap: 1}}>
              <Icon
                iconKey={
                  childProjects.length > 0 ? 'folder.system' : 'object.schema'
                }
                decorative
              />
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
              <span style={{fontSize: '0.75rem', opacity: 0.7}}>
                {gettext('Description')}
              </span>
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
                <span style={{fontSize: '0.74rem', opacity: 0.7}}>
                  {f.label}
                </span>
                <strong
                  style={{
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {f.value}
                </strong>
              </div>
            ))}
          </div>

          <Box sx={{display: 'grid', gap: 1}}>
            <strong style={{fontSize: '0.88rem'}}>
              {gettext('Project Virtual Sections')}
            </strong>
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
                    <div
                      style={{
                        fontWeight: 600,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {gettext(vnode.label)}
                    </div>
                    <div style={{fontSize: '0.74rem', opacity: 0.7}}>
                      {gettext('Virtual group')}
                    </div>
                  </div>
                  <span
                    style={{fontSize: '0.75rem', fontWeight: 600, opacity: 0.8}}
                  >
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
  // TREE VARIANT (Area 3a Left Drawer — Data Explorer visual & host parity)
  // =========================================================================
  const {flatRows, activeNodeObj, inlineErrors} = useMemo(() => {
    const rootRef = {id: '__root__', depth: 0, parent: null, children: []};
    const rows = [];
    const errs = [];
    let foundActive = null;

    const itemMatchesFilter = (item) =>
      !filter ||
      `${item.label} ${item.asset?.path || ''} ${item.asset?.asset_type || ''}`
        .toLowerCase()
        .includes(filter);

    if (hasHostNavigator) {
      const buildFromHost = (parentToken, parentNode, depth, visited = new Set()) => {
        const cacheKey = `${filter}::${parentToken}`;
        const fallbackBaseKey = `::${parentToken}`;
        const rawSlice =
          hostNodesByParent[cacheKey] ?? hostNodesByParent[fallbackBaseKey] ?? [];
        for (const raw of rawSlice) {
          if (visited.has(raw.id)) continue;
          const isExp = expanded.has(raw.id) || Boolean(filter);
          const nodeObj = {
            ...raw,
            icon_key: raw.icon_key || raw.icon,
            depth,
            parent: parentNode,
            expanded: isExp,
            loading: hostLoadingParents.has(raw.id),
            children: [],
          };
          parentNode.children.push(nodeObj);
          if (nodeObj.id === selectedNodeId) foundActive = nodeObj;
          if (raw.inode && isExp) {
            const nextVis = new Set(visited);
            nextVis.add(raw.id);
            buildFromHost(raw.id, nodeObj, depth + 1, nextVis);
          }
        }
      };
      buildFromHost('', rootRef, 1);
    } else {
      const buildFallbackVirtual = (
        project,
        vnode,
        parentNode,
        depth,
        visitedProjects
      ) => {
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
          return;
        }

        const vid = safeToken(vnode.id);
        const isExp = expanded.has(vid) || Boolean(filter);
        const hasChildren =
          (vnode.totalCount || 0) > 0 || (vnode.subgroups || []).length > 0;
        const vObj = {
          id: vid,
          label: gettext(vnode.label),
          info_label: ` (${vnode.totalCount})`,
          icon_key: vnode.iconKey,
          _type: 'cde_project_virtual',
          object_type: 'folder',
          inode: true,
          has_children: hasChildren,
          project_id: project.project_id,
          virtual_id: vnode.id,
          project,
          nav_payload: {
            kind: 'virtual',
            projectId: project.project_id,
            virtualId: vnode.id,
            item: null,
          },
          depth,
          parent: parentNode,
          expanded: isExp,
          loading: false,
          children: [],
        };
        parentNode.children.push(vObj);
        if (vObj.id === selectedNodeId) foundActive = vObj;

        if (isExp) {
          for (const cp of filteredChildProjects) {
            buildFallbackProject(cp, vObj, depth + 1, visitedProjects);
          }
          for (const sg of filteredSubgroups) {
            buildFallbackVirtual(
              project,
              sg,
              vObj,
              depth + 1,
              visitedProjects
            );
          }
          for (const item of filteredItems) {
            const leafId = `item~${safeToken(item.id)}`;
            const leafObj = {
              id: leafId,
              label: item.label,
              info_label: item.badge ? ` · ${item.badge}` : '',
              icon_key: item.iconKey,
              _type: 'cde_project_leaf',
              object_type: item.itemKind || 'asset',
              inode: false,
              has_children: false,
              warning: item.warning ? gettext(item.warning) : '',
              project_id: project.project_id,
              leaf: item,
              depth: depth + 1,
              parent: vObj,
              expanded: false,
              loading: false,
              children: [],
            };
            vObj.children.push(leafObj);
            if (leafObj.id === selectedNodeId) foundActive = leafObj;
          }
        }
      };

      const buildFallbackProject = (
        project,
        parentNode,
        depth,
        visited = new Set()
      ) => {
        if (visited.has(project.project_id)) return;
        const nextVisited = new Set(visited);
        nextVisited.add(project.project_id);

        const pidNodeId = `proj~${safeToken(project.project_id)}`;
        const isExp = expanded.has(pidNodeId) || Boolean(filter);
        const st = states[project.project_id];
        const childProjects = (childrenMap.get(project.project_id) || []).filter(
          (ch) => matchingIds.has(ch.project_id)
        );
        const accessLabel =
          project.access === 'owner' ? gettext('Owner') : project.access;
        const info =
          childProjects.length > 0
            ? ` (${childProjects.length} sub)`
            : ` (${accessLabel})`;

        const projObj = {
          id: pidNodeId,
          label: project.name,
          info_label: info,
          icon_key: childProjects.length > 0 ? 'folder.system' : 'object.schema',
          _type: 'cde_project',
          object_type: 'project',
          inode: true,
          has_children: true,
          project_id: project.project_id,
          project,
          nav_payload: {
            kind: 'project',
            projectId: project.project_id,
            virtualId: null,
            item: null,
          },
          depth,
          parent: parentNode,
          expanded: isExp,
          loading: Boolean(st?.loading),
          warning: st?.error || '',
          children: [],
        };
        parentNode.children.push(projObj);
        if (projObj.id === selectedNodeId) foundActive = projObj;

        if (isExp && st?.error) {
          errs.push({project, error: st.error, depth: depth + 1});
        } else if (isExp) {
          const vnodes = buildProjectVirtualTree(project, st, childProjects);
          for (const vnode of vnodes) {
            buildFallbackVirtual(
              project,
              vnode,
              projObj,
              depth + 1,
              nextVisited
            );
          }
        }
      };

      for (const rootProj of visibleRoots) {
        buildFallbackProject(rootProj, rootRef, 1);
      }
    }

    if (modules.length > 0) {
      const visibleModules = modules.filter(
        (mod) =>
          !filter ||
          `${mod.label} ${mod.id}`.toLowerCase().includes(filter)
      );
      if (visibleModules.length > 0) {
        const modGroupId = 'virt~__platform_modules__';
        const modExp = expanded.has(modGroupId) || Boolean(filter);
        const modGroupObj = {
          id: modGroupId,
          label: gettext('Platform Modules'),
          info_label: ` (${visibleModules.length})`,
          icon_key: 'tool.project-explorer',
          _type: 'cde_project_virtual',
          object_type: 'folder',
          inode: true,
          has_children: true,
          depth: 1,
          parent: rootRef,
          expanded: modExp,
          loading: false,
          children: [],
        };
        rootRef.children.push(modGroupObj);
        if (modGroupObj.id === selectedNodeId) foundActive = modGroupObj;
        if (modExp) {
          for (const mod of visibleModules) {
            const mLeaf = {
              id: `mod~${safeToken(mod.id)}`,
              label: mod.label,
              info_label: '',
              icon_key: mod.iconKey || 'command.default',
              _type: 'cde_project_leaf',
              object_type: 'module',
              inode: false,
              has_children: false,
              leaf: {
                itemKind: 'module',
                id: `mod:${mod.id}`,
                label: mod.label,
                onOpen: mod.onOpen,
              },
              depth: 2,
              parent: modGroupObj,
              expanded: false,
              loading: false,
              children: [],
            };
            modGroupObj.children.push(mLeaf);
            if (mLeaf.id === selectedNodeId) foundActive = mLeaf;
          }
        }
      }
    }

    const flatten = (container) => {
      for (const ch of container.children) {
        rows.push(ch);
        if (ch.expanded && ch.children.length > 0) {
          flatten(ch);
        }
      }
    };
    flatten(rootRef);

    return {flatRows: rows, activeNodeObj: foundActive, inlineErrors: errs};
  }, [
    hasHostNavigator,
    hostNodesByParent,
    hostLoadingParents,
    filter,
    expanded,
    selectedNodeId,
    states,
    childrenMap,
    matchingIds,
    visibleRoots,
    modules,
  ]);

  const contextMenuItems = useMemo(() => {
    if (!contextItemData) return [];
    const items = [];
    if (contextItemData._type === 'cde_project_leaf' && contextItemData.leaf) {
      items.push({
        label: gettext('Open'),
        icon: 'action.open',
        callback: () => handleOpenLeafItem(contextItemData.leaf),
      });
    }
    if (contextItemData.project_id) {
      items.push({
        label: gettext('New Child Project…'),
        icon: 'action.new',
        callback: () => {
          setCreateDraft({
            id: '',
            name: '',
            description: '',
            parentProjectId: contextItemData.project_id,
          });
          setCreateError('');
          setCreateOpen(true);
        },
      });
      if (client.updateProject) {
        const proj = projects.find(
          (p) => p.project_id === contextItemData.project_id
        );
        if (proj) {
          items.push({
            label: gettext('Set Parent Project…'),
            icon: 'action.attach',
            callback: () => {
              setReparentTarget(proj);
              setReparentValue(proj.parent_project_id || '');
              setReparentError('');
            },
          });
        }
      }
    }
    items.push({
      label: gettext('Refresh'),
      icon: 'action.refresh',
      callback: () => refresh(),
    });
    return items;
  }, [contextItemData, client.updateProject, projects, handleOpenLeafItem, refresh]);

  const reparentForbiddenIds = useMemo(() => {
    if (!reparentTarget) return new Set();
    const desc = collectDescendantProjectIds(
      projects,
      reparentTarget.project_id
    );
    desc.add(reparentTarget.project_id);
    return desc;
  }, [projects, reparentTarget]);

  const effectiveMatchCount = hasHostNavigator
    ? (hostMatchCount ?? projects.length)
    : matchingIds.size;

  const isEmpty = !error && !loading && flatRows.length === 0;

  const breadcrumbTrail = useMemo(() => {
    if (!selectedProject) return [gettext('Projects')];
    const chain = [];
    const seen = new Set();
    let cur = selectedProject;
    while (cur && !seen.has(cur.project_id)) {
      seen.add(cur.project_id);
      chain.unshift(cur.name);
      cur = cur.parent_project_id ? byId.get(cur.parent_project_id) : null;
    }
    return [gettext('Projects'), ...chain];
  }, [selectedProject, byId]);

  return (
    <Box
      component="section"
      aria-label={gettext('Project Navigator')}
      sx={{
        height: '100%',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Data-Navigator-matching compact icon toolbar */}
      <div
        role="toolbar"
        aria-label={gettext('Project Navigator commands')}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 4,
          padding: '3px 6px',
          borderBottom:
            '1px solid var(--sr-border-subtle, rgba(128,128,128,0.18))',
          flexShrink: 0,
        }}
      >
        <div style={{display: 'flex', alignItems: 'center', gap: 4}}>
          <CompactToolbarIconButton
            label={gettext('New project')}
            iconKey="action.new"
            onClick={beginCreate}
          />
          {selectedProject && client.updateProject && (
            <CompactToolbarIconButton
              label={gettext('Set parent')}
              iconKey="action.attach"
              onClick={beginReparent}
            />
          )}
          <CompactToolbarIconButton
            label={gettext('Refresh')}
            iconKey="action.refresh"
            onClick={refresh}
          />
        </div>
        <FormReference formKey="project-explorer" />
      </div>

      {/* Breadcrumb strip matching Data Navigator */}
      <div
        style={{
          padding: '2px 8px',
          fontSize: '0.73rem',
          color: 'var(--sr-text-muted, #64748b)',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          borderBottom:
            '1px solid var(--sr-border-subtle, rgba(128,128,128,0.14))',
          flexShrink: 0,
        }}
      >
        {breadcrumbTrail.join(' › ')}
      </div>

      {/* Compact inline filter */}
      <Box sx={{px: 0.75, py: 0.5, flexShrink: 0}}>
        <SearchField
          label={gettext('Filter projects and assets')}
          value={query}
          onChange={setQuery}
          resultCount={effectiveMatchCount}
        />
      </Box>

      {/* Main `.file-tree` body — exact Data Explorer `.file-entry` + `<TreeBranchGuides>` + `(+)/(-)` toggles */}
      <ScratchScrollArea
        orientation="both"
        style={{flex: 1, minHeight: 0}}
        onScroll={() => {
          if (contextPos) setContextPos(null);
        }}
      >
        <div
          className="file-tree"
          role="tree"
          aria-label={gettext('Projects and authored assets')}
          style={{
            position: 'relative',
            minHeight: 120,
            width: '100%',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <section
            role="presentation"
            style={{display: 'flex', flexDirection: 'column', width: '100%'}}
          >
            {error && (
              <EmptyState
                role="alert"
                message={error}
                actionLabel={gettext('Retry')}
                onAction={refresh}
              />
            )}
            {isEmpty && (
              <EmptyState
                message={gettext(
                  'No projects match this view. Create a project to store queries, diagrams, models, and other authored assets.'
                )}
                actionLabel={gettext('New project')}
                onAction={beginCreate}
              />
            )}
            {!error &&
              flatRows.map((rowNode) => (
                <ExplorerTreeEntryRow
                  key={rowNode.id}
                  node={rowNode}
                  activeNode={activeNodeObj}
                  branchStepX={branchPrefs.stepX}
                  branchRadius={branchPrefs.radius}
                  rowHeight={28}
                  onSelect={handleSelectNode}
                  onToggle={handleToggleNode}
                  onActivate={(n) => n.leaf && handleOpenLeafItem(n.leaf)}
                  onContextMenu={(ev, n) => {
                    handleSelectNode(n);
                    setContextItemData(n);
                    setContextPos({x: ev.clientX, y: ev.clientY});
                  }}
                />
              ))}
            {inlineErrors.map((ie) => (
              <Box
                key={ie.project.project_id}
                role="alert"
                sx={{pl: ie.depth * 2, py: 0.75}}
              >
                {ie.error}{' '}
                <Button onClick={() => loadProject(ie.project)}>
                  {gettext('Retry')}
                </Button>
              </Box>
            ))}
            <ProgressOverlay
              message={loading ? gettext('Loading projects') : ''}
            />
          </section>
        </div>
      </ScratchScrollArea>

      <ContextMenu
        position={contextPos}
        onClose={() => {
          setContextPos(null);
          setContextItemData(null);
        }}
        menuItems={contextMenuItems}
        label={gettext('Project Navigator Context Menu')}
      />

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
              <label
                htmlFor="sr-project-parent-select"
                className="sr-field-label"
              >
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
            <label
              htmlFor="sr-reparent-project-select"
              className="sr-field-label"
            >
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
