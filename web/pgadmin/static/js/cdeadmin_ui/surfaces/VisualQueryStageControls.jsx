/////////////////////////////////////////////////////////////
//
// ScratchRobin — Staged CTE (WITH / WITH RECURSIVE) & Window (OVER)
// Controls for the SQL Studio Visual Query Builder (DDN)
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Button} from '../primitives/Button';
import {TextField} from '../primitives/Field';

export const WINDOW_FUNCTIONS = Object.freeze([
  {value: 'ROW_NUMBER', label: 'ROW_NUMBER()', kind: 'ranking'},
  {value: 'RANK', label: 'RANK()', kind: 'ranking'},
  {value: 'DENSE_RANK', label: 'DENSE_RANK()', kind: 'ranking'},
  {value: 'NTILE', label: 'NTILE(n)', kind: 'ntile'},
  {value: 'PERCENT_RANK', label: 'PERCENT_RANK()', kind: 'ranking'},
  {value: 'CUME_DIST', label: 'CUME_DIST()', kind: 'ranking'},
  {value: 'SUM', label: 'SUM(expr)', kind: 'aggregate'},
  {value: 'AVG', label: 'AVG(expr)', kind: 'aggregate'},
  {value: 'COUNT', label: 'COUNT(expr)', kind: 'aggregate'},
  {value: 'MIN', label: 'MIN(expr)', kind: 'aggregate'},
  {value: 'MAX', label: 'MAX(expr)', kind: 'aggregate'},
  {value: 'LAG', label: 'LAG(expr, offset, default)', kind: 'offset'},
  {value: 'LEAD', label: 'LEAD(expr, offset, default)', kind: 'offset'},
  {value: 'FIRST_VALUE', label: 'FIRST_VALUE(expr)', kind: 'value'},
  {value: 'LAST_VALUE', label: 'LAST_VALUE(expr)', kind: 'value'},
  {value: 'NTH_VALUE', label: 'NTH_VALUE(expr, n)', kind: 'nth'},
]);

export const FRAME_START_OPTIONS = Object.freeze([
  'UNBOUNDED PRECEDING',
  '3 PRECEDING',
  '2 PRECEDING',
  '1 PRECEDING',
  'CURRENT ROW',
]);

export const FRAME_END_OPTIONS = Object.freeze([
  'CURRENT ROW',
  '1 FOLLOWING',
  '2 FOLLOWING',
  'UNBOUNDED FOLLOWING',
]);

export function createEmptyStageBranch() {
  return {
    tables: [],
    joins: [],
    projections: [],
    filters: [],
    where: [],
    group_by: [],
    having: [],
    windows: [],
    order_by: [],
    limit: null,
    distinct: false,
  };
}

export function inferStageOutputColumns(stageObj, explicitColumns = '') {
  if (typeof explicitColumns === 'string' && explicitColumns.trim()) {
    const names = explicitColumns
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    if (names.length > 0) {
      return names.map((name) => ({name, type: 'ANY', native_type: 'ANY'}));
    }
  }
  const projs = Array.isArray(stageObj?.projections) ? stageObj.projections : [];
  const seen = new Set();
  const out = [];
  if (projs.length > 0) {
    projs.forEach((p, idx) => {
      let name = String(p?.alias || '').trim();
      if (!name && p?.column && p.column !== '*') {
        name = String(p.column).trim();
      }
      if (!name && p?.expr) {
        const m = String(p.expr)
          .trim()
          .match(/^[A-Za-z0-9_."`]+\.([A-Za-z_][A-Za-z0-9_$]*)$/);
        if (m) name = m[1];
      }
      if (!name) name = `col_${idx + 1}`;
      if (!seen.has(name)) {
        seen.add(name);
        out.push({
          name,
          type: p?.window || p?.aggregate === 'WINDOW' ? 'WINDOW' : 'ANY',
          native_type: p?.window || p?.aggregate === 'WINDOW' ? 'WINDOW' : 'ANY',
        });
      }
    });
    return out;
  }
  for (const tbl of stageObj?.tables || []) {
    for (const c of tbl?.columns || []) {
      const cname = String(c?.name || c || '').trim();
      if (cname && !seen.has(cname)) {
        seen.add(cname);
        out.push({
          name: cname,
          type: c?.type || c?.native_type || 'ANY',
          native_type: c?.native_type || c?.type || 'ANY',
        });
      }
    }
  }
  return out;
}

export function getActiveStageKey(visualModel) {
  return String(visualModel?.active_stage || '__final__').trim() || '__final__';
}

export function getActiveVisualStage(visualModel) {
  const stageKey = getActiveStageKey(visualModel);
  if (stageKey.startsWith('cte:')) {
    const parts = stageKey.split(':');
    const cteId = parts[1] || '';
    const branch = parts[2] || 'anchor';
    const ctes = Array.isArray(visualModel?.ctes) ? visualModel.ctes : [];
    const matched = ctes.find((c) => (c.id || c.name) === cteId);
    if (matched) {
      if (branch === 'recursive' && matched.recursive) {
        return matched.recursive_branch || createEmptyStageBranch();
      }
      return matched.anchor || createEmptyStageBranch();
    }
  }
  return visualModel || createEmptyStageBranch();
}

export function updateActiveVisualStage(visualModel, updater) {
  const stageKey = getActiveStageKey(visualModel);
  if (stageKey.startsWith('cte:')) {
    const parts = stageKey.split(':');
    const cteId = parts[1] || '';
    const branch = parts[2] || 'anchor';
    const ctes = Array.isArray(visualModel?.ctes) ? visualModel.ctes : [];
    const nextCtes = ctes.map((c) => {
      if ((c.id || c.name) !== cteId) return c;
      if (branch === 'recursive' && c.recursive) {
        const curBranch = c.recursive_branch || createEmptyStageBranch();
        const updated = typeof updater === 'function' ? updater(curBranch) : updater;
        return {...c, recursive_branch: {...curBranch, ...updated}};
      }
      const curAnchor = c.anchor || createEmptyStageBranch();
      const updated = typeof updater === 'function' ? updater(curAnchor) : updater;
      return {...c, anchor: {...curAnchor, ...updated}};
    });
    return {...visualModel, ctes: nextCtes};
  }
  const updated = typeof updater === 'function' ? updater(visualModel) : updater;
  return {...visualModel, ...updated};
}

export function listVisibleCteSources(visualModel) {
  const ctes = Array.isArray(visualModel?.ctes) ? visualModel.ctes : [];
  if (ctes.length === 0) return [];
  const stageKey = getActiveStageKey(visualModel);
  let cutoffIdx = ctes.length;
  let recursiveSelfCte = null;
  if (stageKey.startsWith('cte:')) {
    const parts = stageKey.split(':');
    const cteId = parts[1] || '';
    const branch = parts[2] || 'anchor';
    const idx = ctes.findIndex((c) => (c.id || c.name) === cteId);
    if (idx >= 0) {
      cutoffIdx = idx;
      if (branch === 'recursive' && ctes[idx]?.recursive) {
        recursiveSelfCte = ctes[idx];
      }
    }
  }
  const items = [];
  if (recursiveSelfCte && recursiveSelfCte.name) {
    const cols = inferStageOutputColumns(recursiveSelfCte.anchor, recursiveSelfCte.columns);
    items.push({
      resource_id: `cte-self:${recursiveSelfCte.name}`,
      resource_kind: 'cte-self',
      display_name: recursiveSelfCte.name,
      schema_name: '',
      system_object: false,
      columns: cols,
    });
  }
  for (let i = 0; i < cutoffIdx; i += 1) {
    const c = ctes[i];
    if (!c?.name) continue;
    const cols = inferStageOutputColumns(c.anchor, c.columns);
    items.push({
      resource_id: `cte:${c.name}`,
      resource_kind: 'cte',
      display_name: c.name,
      schema_name: '',
      system_object: false,
      columns: cols,
    });
  }
  return items;
}

export function applyWindowPreset(presetId, defaultCol) {
  const col = defaultCol || '*';
  switch (presetId) {
  case 'row_number':
    return {
      function: 'ROW_NUMBER',
      argument: '',
      partition_by: defaultCol ? [defaultCol] : [],
      order_by: defaultCol ? [`${defaultCol} ASC`] : [],
      frame_mode: '',
      frame_start: 'UNBOUNDED PRECEDING',
      frame_end: 'CURRENT ROW',
    };
  case 'rank':
    return {
      function: 'DENSE_RANK',
      argument: '',
      partition_by: [],
      order_by: defaultCol ? [`${defaultCol} DESC`] : [],
      frame_mode: '',
      frame_start: 'UNBOUNDED PRECEDING',
      frame_end: 'CURRENT ROW',
    };
  case 'running_total':
    return {
      function: 'SUM',
      argument: col,
      partition_by: [],
      order_by: defaultCol ? [`${defaultCol} ASC`] : [],
      frame_mode: 'ROWS',
      frame_start: 'UNBOUNDED PRECEDING',
      frame_end: 'CURRENT ROW',
    };
  case 'moving_avg':
    return {
      function: 'AVG',
      argument: col,
      partition_by: [],
      order_by: defaultCol ? [`${defaultCol} ASC`] : [],
      frame_mode: 'ROWS',
      frame_start: '2 PRECEDING',
      frame_end: 'CURRENT ROW',
    };
  case 'lag_prev':
    return {
      function: 'LAG',
      argument: col,
      offset: 1,
      default_expr: '0',
      partition_by: [],
      order_by: defaultCol ? [`${defaultCol} ASC`] : [],
      frame_mode: '',
      frame_start: 'UNBOUNDED PRECEDING',
      frame_end: 'CURRENT ROW',
    };
  default:
    return {
      function: 'ROW_NUMBER',
      argument: '',
      partition_by: [],
      order_by: [],
      frame_mode: '',
      frame_start: 'UNBOUNDED PRECEDING',
      frame_end: 'CURRENT ROW',
    };
  }
}

export function VisualBuilderPipelineBar({
  visualModel,
  onSelectStage,
  onAddCte,
  onOpenCtesInspector,
}) {
  const ctes = Array.isArray(visualModel?.ctes) ? visualModel.ctes : [];
  const activeKey = getActiveStageKey(visualModel);

  return (
    <div
      data-cdeadmin-qa-key="vb-pipeline-stage-bar"
      style={{
        position: 'absolute',
        top: 10,
        left: 12,
        right: 12,
        zIndex: 9,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 8,
        padding: '6px 10px',
        borderRadius: 10,
        background: 'var(--sr-island-bg, rgba(255, 255, 255, 0.96))',
        border: '1px solid var(--sr-border-default, #cbd5e1)',
        boxShadow: '0 4px 12px rgba(15, 23, 42, 0.08)',
        flexWrap: 'wrap',
      }}
    >
      <div style={{display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap'}}>
        <span style={{fontSize: '0.72rem', fontWeight: 700, opacity: 0.78, marginRight: 2}}>
          {ctes.some((c) => c.recursive) ? 'WITH RECURSIVE:' : gettext('Query Pipeline:')}
        </span>
        {ctes.map((cte) => {
          const cid = cte.id || cte.name;
          const anchorKey = `cte:${cid}:anchor`;
          const recKey = `cte:${cid}:recursive`;
          return (
            <span key={cid} style={{display: 'inline-flex', alignItems: 'center', gap: 4}}>
              <button
                type="button"
                data-cdeadmin-qa-key={`vb-stage-pill-${cte.name}-anchor`}
                onClick={() => onSelectStage(anchorKey)}
                style={{
                  padding: '3px 9px',
                  borderRadius: 999,
                  fontSize: '0.73rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  border: '1px solid #4f46e5',
                  background: activeKey === anchorKey ? '#4f46e5' : 'rgba(79, 70, 229, 0.1)',
                  color: activeKey === anchorKey ? '#ffffff' : 'inherit',
                }}
              >
                {cte.recursive ? `CTE ${cte.name} · Anchor` : `CTE: ${cte.name}`}
              </button>
              {cte.recursive && (
                <>
                  <span style={{fontSize: '0.68rem', fontWeight: 700, opacity: 0.72}}>
                    {cte.union_mode || 'UNION ALL'}
                  </span>
                  <button
                    type="button"
                    data-cdeadmin-qa-key={`vb-stage-pill-${cte.name}-recursive`}
                    onClick={() => onSelectStage(recKey)}
                    style={{
                      padding: '3px 9px',
                      borderRadius: 999,
                      fontSize: '0.73rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                      border: '1px solid #d97706',
                      background: activeKey === recKey ? '#d97706' : 'rgba(217, 119, 6, 0.14)',
                      color: activeKey === recKey ? '#ffffff' : 'inherit',
                    }}
                  >
                    {`↻ ${cte.name} · Recursive`}
                  </button>
                </>
              )}
              <span style={{opacity: 0.55, fontSize: '0.76rem'}}>→</span>
            </span>
          );
        })}
        <button
          type="button"
          data-cdeadmin-qa-key="vb-stage-pill-final"
          onClick={() => onSelectStage('__final__')}
          style={{
            padding: '3px 10px',
            borderRadius: 999,
            fontSize: '0.73rem',
            fontWeight: 600,
            cursor: 'pointer',
            border: '1px solid var(--sr-accent-primary, #2563eb)',
            background:
              activeKey === '__final__'
                ? 'var(--sr-accent-primary, #2563eb)'
                : 'rgba(37, 99, 235, 0.08)',
            color: activeKey === '__final__' ? '#ffffff' : 'inherit',
          }}
        >
          {gettext('Final SELECT')}
        </button>
      </div>
      <div style={{display: 'flex', alignItems: 'center', gap: 6}}>
        <Button
          size="small"
          data-cdeadmin-qa-key="vb-pipeline-add-cte"
          onClick={() => {
            onAddCte();
            onOpenCtesInspector?.();
          }}
        >
          + {gettext('Add CTE')}
        </Button>
      </div>
    </div>
  );
}

VisualBuilderPipelineBar.propTypes = {
  visualModel: PropTypes.object,
  onSelectStage: PropTypes.func.isRequired,
  onAddCte: PropTypes.func.isRequired,
  onOpenCtesInspector: PropTypes.func,
};

export function VisualCtesInspectorPanel({
  visualModel,
  onUpdateModel,
  onSelectStageAndTab,
}) {
  const ctes = Array.isArray(visualModel?.ctes) ? visualModel.ctes : [];
  const activeKey = getActiveStageKey(visualModel);

  const handleAddNewCte = (recursiveDefault = false) => {
    const idx = ctes.length + 1;
    const cteId = `cte_${Date.now()}_${idx}`;
    const cteName = recursiveDefault ? `hierarchy_cte_${idx}` : `stage_cte_${idx}`;
    const newCte = {
      id: cteId,
      name: cteName,
      columns: '',
      recursive: recursiveDefault,
      union_mode: 'UNION ALL',
      materialized: '',
      cycle: {
        enabled: false,
        columns: '',
        set_column: 'is_cycle',
        using_column: 'traversal_path',
      },
      anchor: createEmptyStageBranch(),
      recursive_branch: recursiveDefault
        ? {
          ...createEmptyStageBranch(),
          tables: [
            {
              id: 'r1',
              resource_id: `cte-self:${cteName}`,
              resource_kind: 'cte-self',
              name: cteName,
              alias: 'r1',
              x: 84,
              y: 88,
              columns: [],
            },
          ],
        }
        : createEmptyStageBranch(),
    };
    onUpdateModel({
      ...visualModel,
      active_stage: `cte:${cteId}:anchor`,
      ctes: [...ctes, newCte],
    });
  };

  const updateCteAt = (index, patchFn) => {
    const nextCtes = ctes.map((c, i) => (i === index ? patchFn(c) : c));
    onUpdateModel({...visualModel, ctes: nextCtes});
  };

  const removeCteAt = (index) => {
    const removed = ctes[index];
    const nextCtes = ctes.filter((_, i) => i !== index);
    const removedPrefix = `cte:${removed?.id || removed?.name}:`;
    const nextActive = activeKey.startsWith(removedPrefix) ? '__final__' : activeKey;
    onUpdateModel({...visualModel, active_stage: nextActive, ctes: nextCtes});
  };

  const addCteToFinalSelect = (cteItem) => {
    const cols = inferStageOutputColumns(cteItem.anchor, cteItem.columns);
    const existing = Array.isArray(visualModel?.tables) ? visualModel.tables : [];
    const alias = `c${existing.length + 1}`;
    const node = {
      id: alias,
      resource_id: `cte:${cteItem.name}`,
      resource_kind: 'cte',
      name: cteItem.name,
      alias,
      x: 90 + (existing.length % 3) * 320,
      y: 88 + Math.floor(existing.length / 3) * 260,
      columns: cols,
    };
    onUpdateModel({
      ...visualModel,
      active_stage: '__final__',
      tables: [...existing, node],
    });
  };

  return (
    <div data-cdeadmin-qa-key="vb-ctes-inspector-panel" style={{display: 'grid', gap: 10}}>
      <div style={{display: 'flex', gap: 6, flexWrap: 'wrap'}}>
        <Button
          size="small"
          intent="primary"
          data-cdeadmin-qa-key="vb-add-standard-cte"
          onClick={() => handleAddNewCte(false)}
        >
          + {gettext('Standard CTE (WITH)')}
        </Button>
        <Button
          size="small"
          data-cdeadmin-qa-key="vb-add-recursive-cte"
          onClick={() => handleAddNewCte(true)}
        >
          + {gettext('Recursive CTE (WITH RECURSIVE)')}
        </Button>
      </div>

      {ctes.length === 0 ? (
        <div
          style={{
            padding: 10,
            borderRadius: 8,
            border: '1px dashed var(--sr-border-default, #cbd5e1)',
            fontSize: '0.76rem',
            opacity: 0.85,
          }}
        >
          {gettext(
            'Add a WITH or WITH RECURSIVE Common Table Expression stage to build multi-step aggregations, hierarchical traversals, or post-window filters visually.'
          )}
        </div>
      ) : (
        ctes.map((cte, idx) => {
          const cid = cte.id || cte.name;
          const anchorKey = `cte:${cid}:anchor`;
          const recKey = `cte:${cid}:recursive`;
          const isEditingThis = activeKey === anchorKey || activeKey === recKey;
          const cycle = cte.cycle || {};

          return (
            <div
              key={cid}
              data-cdeadmin-qa-key={`vb-cte-card-${cte.name}`}
              style={{
                padding: 10,
                borderRadius: 8,
                border: isEditingThis
                  ? '1.5px solid #4f46e5'
                  : '1px solid var(--sr-border-subtle)',
                background: isEditingThis ? 'rgba(79, 70, 229, 0.05)' : 'transparent',
                display: 'grid',
                gap: 8,
              }}
            >
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 6}}>
                <strong style={{fontSize: '0.8rem'}}>
                  {gettext('CTE #%s: %s', idx + 1, cte.name)}
                </strong>
                <Button size="small" onClick={() => removeCteAt(idx)}>
                  ×
                </Button>
              </div>

              <TextField
                label={gettext('CTE Name')}
                value={cte.name || ''}
                onChange={(e) => {
                  const newName = e.target.value.replace(/[^A-Za-z0-9_$]/g, '');
                  updateCteAt(idx, (prev) => ({
                    ...prev,
                    name: newName,
                    recursive_branch: prev.recursive_branch
                      ? {
                        ...prev.recursive_branch,
                        tables: (prev.recursive_branch.tables || []).map((t) =>
                          t.resource_kind === 'cte-self' ? {...t, name: newName} : t
                        ),
                      }
                      : prev.recursive_branch,
                  }));
                }}
              />

              <TextField
                label={gettext('Explicit Column List (optional)')}
                placeholder="id, manager_id, depth"
                value={cte.columns || ''}
                onChange={(e) => updateCteAt(idx, (prev) => ({...prev, columns: e.target.value}))}
              />

              <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6}}>
                <label style={{display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.76rem'}}>
                  <input
                    type="checkbox"
                    data-cdeadmin-qa-key={`vb-cte-recursive-toggle-${idx}`}
                    checked={Boolean(cte.recursive)}
                    onChange={(e) => {
                      const nextRec = e.target.checked;
                      updateCteAt(idx, (prev) => {
                        const curRecBranch = prev.recursive_branch || createEmptyStageBranch();
                        const hasSelfCard = (curRecBranch.tables || []).some(
                          (t) => t.resource_kind === 'cte-self'
                        );
                        const nextRecTables =
                          nextRec && !hasSelfCard
                            ? [
                              {
                                id: 'r1',
                                resource_id: `cte-self:${prev.name}`,
                                resource_kind: 'cte-self',
                                name: prev.name,
                                alias: 'r1',
                                x: 84,
                                y: 88,
                                columns: inferStageOutputColumns(prev.anchor, prev.columns),
                              },
                              ...(curRecBranch.tables || []),
                            ]
                            : curRecBranch.tables || [];
                        return {
                          ...prev,
                          recursive: nextRec,
                          recursive_branch: {...curRecBranch, tables: nextRecTables},
                        };
                      });
                    }}
                  />
                  {gettext('Recursive')}
                </label>

                <select
                  className="sr-input"
                  aria-label={gettext('Materialization')}
                  value={cte.materialized || ''}
                  onChange={(e) =>
                    updateCteAt(idx, (prev) => ({...prev, materialized: e.target.value}))
                  }
                  style={{fontSize: '0.74rem'}}
                >
                  <option value="">{gettext('Default Materialization')}</option>
                  <option value="MATERIALIZED">MATERIALIZED</option>
                  <option value="NOT MATERIALIZED">NOT MATERIALIZED</option>
                </select>
              </div>

              {cte.recursive && (
                <div
                  style={{
                    padding: 8,
                    borderRadius: 6,
                    background: 'rgba(217, 119, 6, 0.08)',
                    border: '1px solid rgba(217, 119, 6, 0.35)',
                    display: 'grid',
                    gap: 6,
                  }}
                >
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 6}}>
                    <span style={{fontSize: '0.73rem', fontWeight: 600}}>
                      {gettext('Recursive Branch Operator')}
                    </span>
                    <select
                      className="sr-input"
                      value={cte.union_mode || 'UNION ALL'}
                      onChange={(e) =>
                        updateCteAt(idx, (prev) => ({...prev, union_mode: e.target.value}))
                      }
                      style={{fontSize: '0.73rem', maxWidth: 124}}
                    >
                      <option value="UNION ALL">UNION ALL</option>
                      <option value="UNION">UNION</option>
                    </select>
                  </div>

                  <label style={{display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.74rem'}}>
                    <input
                      type="checkbox"
                      checked={Boolean(cycle.enabled)}
                      onChange={(e) =>
                        updateCteAt(idx, (prev) => ({
                          ...prev,
                          cycle: {...(prev.cycle || {}), enabled: e.target.checked},
                        }))
                      }
                    />
                    {gettext('SQL CYCLE Detection Clause')}
                  </label>

                  {cycle.enabled && (
                    <div style={{display: 'grid', gap: 4}}>
                      <input
                        className="sr-input"
                        placeholder={gettext('Cycle key column(s), e.g. id')}
                        value={cycle.columns || ''}
                        onChange={(e) =>
                          updateCteAt(idx, (prev) => ({
                            ...prev,
                            cycle: {...(prev.cycle || {}), columns: e.target.value},
                          }))
                        }
                        style={{fontSize: '0.74rem'}}
                      />
                      <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4}}>
                        <input
                          className="sr-input"
                          placeholder="is_cycle"
                          value={cycle.set_column || 'is_cycle'}
                          onChange={(e) =>
                            updateCteAt(idx, (prev) => ({
                              ...prev,
                              cycle: {...(prev.cycle || {}), set_column: e.target.value},
                            }))
                          }
                          style={{fontSize: '0.74rem'}}
                        />
                        <input
                          className="sr-input"
                          placeholder="traversal_path"
                          value={cycle.using_column || 'traversal_path'}
                          onChange={(e) =>
                            updateCteAt(idx, (prev) => ({
                              ...prev,
                              cycle: {...(prev.cycle || {}), using_column: e.target.value},
                            }))
                          }
                          style={{fontSize: '0.74rem'}}
                        />
                      </div>
                    </div>
                  )}
                </div>
              )}

              <div style={{display: 'flex', gap: 4, flexWrap: 'wrap'}}>
                <Button
                  size="small"
                  intent={activeKey === anchorKey ? 'primary' : 'neutral'}
                  onClick={() => onSelectStageAndTab(anchorKey, 'tables')}
                >
                  {cte.recursive ? gettext('Edit Anchor Canvas') : gettext('Edit CTE Canvas')}
                </Button>
                {cte.recursive && (
                  <Button
                    size="small"
                    intent={activeKey === recKey ? 'primary' : 'neutral'}
                    onClick={() => onSelectStageAndTab(recKey, 'tables')}
                  >
                    {gettext('Edit ↻ Recursive Canvas')}
                  </Button>
                )}
                <Button
                  size="small"
                  data-cdeadmin-qa-key={`vb-cte-use-in-final-${cte.name}`}
                  onClick={() => addCteToFinalSelect(cte)}
                >
                  {gettext('Use in Final SELECT →')}
                </Button>
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}

VisualCtesInspectorPanel.propTypes = {
  visualModel: PropTypes.object,
  onUpdateModel: PropTypes.func.isRequired,
  onSelectStageAndTab: PropTypes.func.isRequired,
};

export function VisualProjectionWindowEditor({
  projection,
  availableCols,
  namedWindows,
  onChangeWindow,
}) {
  const win = projection?.window || {};
  const fn = String(win.function || 'ROW_NUMBER').toUpperCase();
  const fnMeta = WINDOW_FUNCTIONS.find((f) => f.value === fn) || WINDOW_FUNCTIONS[0];
  const needsArg = !['ranking', 'ntile'].includes(fnMeta.kind);
  const partStr = Array.isArray(win.partition_by)
    ? win.partition_by.join(', ')
    : String(win.partition_by || '');
  const ordStr = Array.isArray(win.order_by)
    ? win.order_by
      .map((o) => (typeof o === 'string' ? o : `${o.expr || o.column} ${o.dir || 'ASC'}`))
      .join(', ')
    : String(win.order_by || '');

  const patch = (nextFields) => onChangeWindow({...win, ...nextFields});

  return (
    <div
      data-cdeadmin-qa-key="vb-window-spec-editor"
      style={{
        padding: 8,
        borderRadius: 6,
        background: 'rgba(8, 145, 178, 0.07)',
        border: '1px solid rgba(8, 145, 178, 0.35)',
        display: 'grid',
        gap: 6,
      }}
    >
      <div style={{display: 'flex', gap: 4, flexWrap: 'wrap', alignItems: 'center'}}>
        <span style={{fontSize: '0.68rem', fontWeight: 700, opacity: 0.78}}>
          {gettext('Presets:')}
        </span>
        {[
          ['row_number', gettext('Row #')],
          ['rank', gettext('Rank')],
          ['running_total', gettext('Running Total')],
          ['moving_avg', gettext('Moving Avg')],
          ['lag_prev', gettext('Prior Row (LAG)')],
        ].map(([pid, plbl]) => (
          <button
            key={pid}
            type="button"
            data-cdeadmin-qa-key={`vb-win-preset-${pid}`}
            onClick={() =>
              onChangeWindow(
                applyWindowPreset(pid, projection?.expr || availableCols[0]?.ref || '')
              )
            }
            style={{
              padding: '1px 6px',
              borderRadius: 999,
              fontSize: '0.68rem',
              cursor: 'pointer',
              border: '1px solid rgba(8, 145, 178, 0.45)',
              background: 'transparent',
            }}
          >
            {plbl}
          </button>
        ))}
      </div>

      <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6}}>
        <div>
          <div style={{fontSize: '0.69rem', opacity: 0.78}}>{gettext('Window Function')}</div>
          <select
            className="sr-input"
            aria-label={gettext('Window Function')}
            value={fn}
            onChange={(e) => patch({function: e.target.value})}
            style={{width: '100%', fontSize: '0.75rem'}}
          >
            {WINDOW_FUNCTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <div style={{fontSize: '0.69rem', opacity: 0.78}}>{gettext('OVER Window Source')}</div>
          <select
            className="sr-input"
            aria-label={gettext('OVER Window Source')}
            value={win.window_ref || ''}
            onChange={(e) => patch({window_ref: e.target.value})}
            style={{width: '100%', fontSize: '0.75rem'}}
          >
            <option value="">{gettext('Inline OVER (...)')}</option>
            {(namedWindows || []).map((nw) => (
              <option key={nw.name} value={nw.name}>
                {`WINDOW ${nw.name}`}
              </option>
            ))}
          </select>
        </div>
      </div>

      {needsArg && (
        <div>
          <div style={{fontSize: '0.69rem', opacity: 0.78}}>{gettext('Function Argument')}</div>
          <input
            className="sr-input"
            aria-label={gettext('Window Argument')}
            placeholder={availableCols[0]?.ref || 't1.amount'}
            value={win.argument ?? projection?.expr ?? ''}
            onChange={(e) => patch({argument: e.target.value})}
            style={{width: '100%', fontSize: '0.75rem'}}
          />
        </div>
      )}

      {fnMeta.kind === 'ntile' && (
        <div>
          <div style={{fontSize: '0.69rem', opacity: 0.78}}>{gettext('NTILE Buckets')}</div>
          <input
            type="number"
            min={1}
            className="sr-input"
            value={win.buckets ?? 4}
            onChange={(e) => patch({buckets: parseInt(e.target.value, 10) || 4})}
            style={{width: '100%', fontSize: '0.75rem'}}
          />
        </div>
      )}

      {(fnMeta.kind === 'offset' || fnMeta.kind === 'nth') && (
        <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6}}>
          <div>
            <div style={{fontSize: '0.69rem', opacity: 0.78}}>{gettext('Row Offset / N')}</div>
            <input
              type="number"
              min={1}
              className="sr-input"
              value={win.offset ?? 1}
              onChange={(e) => patch({offset: parseInt(e.target.value, 10) || 1})}
              style={{width: '100%', fontSize: '0.75rem'}}
            />
          </div>
          {fnMeta.kind === 'offset' && (
            <div>
              <div style={{fontSize: '0.69rem', opacity: 0.78}}>{gettext('Default Value')}</div>
              <input
                className="sr-input"
                placeholder="0 or NULL"
                value={win.default_expr ?? ''}
                onChange={(e) => patch({default_expr: e.target.value})}
                style={{width: '100%', fontSize: '0.75rem'}}
              />
            </div>
          )}
        </div>
      )}

      {!win.window_ref && (
        <>
          <div>
            <div style={{fontSize: '0.69rem', opacity: 0.78}}>
              {gettext('PARTITION BY')}
            </div>
            <input
              className="sr-input"
              aria-label={gettext('Window PARTITION BY')}
              placeholder={availableCols[0]?.ref || 't1.region'}
              value={partStr}
              onChange={(e) =>
                patch({
                  partition_by: e.target.value
                    .split(',')
                    .map((s) => s.trim())
                    .filter(Boolean),
                })
              }
              style={{width: '100%', fontSize: '0.75rem'}}
            />
          </div>

          <div>
            <div style={{fontSize: '0.69rem', opacity: 0.78}}>
              {gettext('Window ORDER BY')}
            </div>
            <input
              className="sr-input"
              aria-label={gettext('Window ORDER BY')}
              placeholder={availableCols[0] ? `${availableCols[0].ref} DESC` : 't1.created_at ASC'}
              value={ordStr}
              onChange={(e) =>
                patch({
                  order_by: e.target.value
                    .split(',')
                    .map((s) => s.trim())
                    .filter(Boolean),
                })
              }
              style={{width: '100%', fontSize: '0.75rem'}}
            />
          </div>

          <div style={{display: 'grid', gridTemplateColumns: '88px 1fr 1fr', gap: 4}}>
            <select
              className="sr-input"
              aria-label={gettext('Window Frame Mode')}
              value={win.frame_mode || ''}
              onChange={(e) => patch({frame_mode: e.target.value})}
              style={{fontSize: '0.73rem'}}
            >
              <option value="">{gettext('No Frame')}</option>
              <option value="ROWS">ROWS</option>
              <option value="RANGE">RANGE</option>
              <option value="GROUPS">GROUPS</option>
            </select>

            <select
              className="sr-input"
              aria-label={gettext('Frame Start')}
              disabled={!win.frame_mode}
              value={win.frame_start || 'UNBOUNDED PRECEDING'}
              onChange={(e) => patch({frame_start: e.target.value})}
              style={{fontSize: '0.72rem'}}
            >
              {FRAME_START_OPTIONS.map((b) => (
                <option key={b} value={b}>
                  {b}
                </option>
              ))}
            </select>

            <select
              className="sr-input"
              aria-label={gettext('Frame End')}
              disabled={!win.frame_mode}
              value={win.frame_end || 'CURRENT ROW'}
              onChange={(e) => patch({frame_end: e.target.value})}
              style={{fontSize: '0.72rem'}}
            >
              {FRAME_END_OPTIONS.map((b) => (
                <option key={b} value={b}>
                  {b}
                </option>
              ))}
            </select>
          </div>
        </>
      )}
    </div>
  );
}

VisualProjectionWindowEditor.propTypes = {
  projection: PropTypes.object,
  availableCols: PropTypes.array,
  namedWindows: PropTypes.array,
  onChangeWindow: PropTypes.func.isRequired,
};

export function VisualNamedWindowsPanel({
  activeStage,
  visualModel,
  availableCols,
  onUpdateActiveStage,
  onWrapStageInCte,
}) {
  const namedWindows = Array.isArray(activeStage?.windows) ? activeStage.windows : [];
  const winProjections = (activeStage?.projections || []).filter(
    (p) => p?.window || p?.aggregate === 'WINDOW'
  );
  const isFinalStage = getActiveStageKey(visualModel) === '__final__';

  const addNamedWindow = () => {
    const idx = namedWindows.length + 1;
    const nextWin = {
      name: `w_part_${idx}`,
      partition_by: availableCols[0] ? [availableCols[0].ref] : [],
      order_by: availableCols[1]
        ? [`${availableCols[1].ref} DESC`]
        : availableCols[0]
          ? [`${availableCols[0].ref} ASC`]
          : [],
      frame_mode: '',
      frame_start: 'UNBOUNDED PRECEDING',
      frame_end: 'CURRENT ROW',
    };
    onUpdateActiveStage((st) => ({
      ...st,
      windows: [...namedWindows, nextWin],
    }));
  };

  const updateWindowAt = (idx, patch) => {
    const next = namedWindows.map((w, i) => (i === idx ? {...w, ...patch} : w));
    onUpdateActiveStage((st) => ({...st, windows: next}));
  };

  return (
    <div data-cdeadmin-qa-key="vb-named-windows-panel" style={{display: 'grid', gap: 10}}>
      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 6}}>
        <strong style={{fontSize: '0.78rem'}}>{gettext('Named WINDOW Clauses')}</strong>
        <Button size="small" data-cdeadmin-qa-key="vb-add-named-window" onClick={addNamedWindow}>
          + {gettext('Add WINDOW')}
        </Button>
      </div>

      {namedWindows.length === 0 ? (
        <div
          style={{
            padding: 8,
            borderRadius: 6,
            border: '1px dashed var(--sr-border-default, #cbd5e1)',
            fontSize: '0.74rem',
            opacity: 0.85,
          }}
        >
          {gettext(
            'Define reusable WINDOW w AS (PARTITION BY … ORDER BY …) specifications here to share across multiple OVER window columns.'
          )}
        </div>
      ) : (
        namedWindows.map((nw, idx) => (
          <div
            key={idx}
            style={{
              padding: 8,
              borderRadius: 6,
              border: '1px solid var(--sr-border-subtle)',
              display: 'grid',
              gap: 6,
            }}
          >
            <div style={{display: 'flex', justifyContent: 'space-between', gap: 6}}>
              <input
                className="sr-input"
                aria-label={gettext('Window Name')}
                value={nw.name || ''}
                onChange={(e) =>
                  updateWindowAt(idx, {name: e.target.value.replace(/[^A-Za-z0-9_$]/g, '')})
                }
                style={{fontWeight: 600, fontSize: '0.76rem'}}
              />
              <Button
                size="small"
                onClick={() =>
                  onUpdateActiveStage((st) => ({
                    ...st,
                    windows: namedWindows.filter((_, i) => i !== idx),
                  }))
                }
              >
                ×
              </Button>
            </div>
            <input
              className="sr-input"
              placeholder={gettext('PARTITION BY columns (comma-separated)')}
              value={Array.isArray(nw.partition_by) ? nw.partition_by.join(', ') : nw.partition_by || ''}
              onChange={(e) =>
                updateWindowAt(idx, {
                  partition_by: e.target.value
                    .split(',')
                    .map((s) => s.trim())
                    .filter(Boolean),
                })
              }
              style={{fontSize: '0.74rem'}}
            />
            <input
              className="sr-input"
              placeholder={gettext('ORDER BY columns, e.g. t1.amount DESC')}
              value={Array.isArray(nw.order_by) ? nw.order_by.join(', ') : nw.order_by || ''}
              onChange={(e) =>
                updateWindowAt(idx, {
                  order_by: e.target.value
                    .split(',')
                    .map((s) => s.trim())
                    .filter(Boolean),
                })
              }
              style={{fontSize: '0.74rem'}}
            />
          </div>
        ))
      )}

      {isFinalStage && winProjections.length > 0 && (
        <div
          style={{
            padding: 8,
            borderRadius: 6,
            background: 'rgba(79, 70, 229, 0.08)',
            border: '1px solid rgba(79, 70, 229, 0.35)',
            display: 'grid',
            gap: 6,
          }}
        >
          <div style={{fontSize: '0.73rem'}}>
            {gettext(
              'Need to filter on a window result (for example WHERE rn = 1)? Standard SQL evaluates WHERE before OVER — wrap this query into a CTE in one click:'
            )}
          </div>
          <Button
            size="small"
            intent="primary"
            data-cdeadmin-qa-key="vb-wrap-window-in-cte"
            onClick={onWrapStageInCte}
          >
            {gettext('Wrap in CTE & Filter Outer Query')}
          </Button>
        </div>
      )}
    </div>
  );
}

VisualNamedWindowsPanel.propTypes = {
  activeStage: PropTypes.object,
  visualModel: PropTypes.object,
  availableCols: PropTypes.array,
  onUpdateActiveStage: PropTypes.func.isRequired,
  onWrapStageInCte: PropTypes.func.isRequired,
};
