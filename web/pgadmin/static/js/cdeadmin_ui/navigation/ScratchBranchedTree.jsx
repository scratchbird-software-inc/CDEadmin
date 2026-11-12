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
import {ensureScratchBaseStyles} from '../base/ScratchBaseStyles';
import {ScratchScrollArea} from '../base/ScratchScrollArea';
import {Checkbox} from '../primitives/Choice';

export const DEFAULT_BRANCHED_TREE_OPTIONS = Object.freeze({
  stepX: 15,
  radius: 7,
  rowHeight: 28,
  stickyAncestors: true,
});

const TREE_PREFS_STORAGE_KEY = 'scratchrobin.ui.branched_tree.v1';

export function readBranchedTreePreferences() {
  try {
    const raw = typeof window !== 'undefined' ? window.localStorage?.getItem(TREE_PREFS_STORAGE_KEY) : null;
    if (!raw) return DEFAULT_BRANCHED_TREE_OPTIONS;
    const parsed = JSON.parse(raw);
    return {
      stepX: Number.isFinite(Number(parsed.stepX)) ? Math.min(28, Math.max(10, Number(parsed.stepX))) : DEFAULT_BRANCHED_TREE_OPTIONS.stepX,
      radius: Number.isFinite(Number(parsed.radius)) ? Math.min(12, Math.max(3, Number(parsed.radius))) : DEFAULT_BRANCHED_TREE_OPTIONS.radius,
      rowHeight: Number.isFinite(Number(parsed.rowHeight)) ? Math.min(38, Math.max(22, Number(parsed.rowHeight))) : DEFAULT_BRANCHED_TREE_OPTIONS.rowHeight,
      stickyAncestors: typeof parsed.stickyAncestors === 'boolean' ? parsed.stickyAncestors : DEFAULT_BRANCHED_TREE_OPTIONS.stickyAncestors,
    };
  } catch (_err) {
    return DEFAULT_BRANCHED_TREE_OPTIONS;
  }
}

export function writeBranchedTreePreferences(partial) {
  const next = {...readBranchedTreePreferences(), ...partial};
  try {
    if (typeof window !== 'undefined') {
      window.localStorage?.setItem(TREE_PREFS_STORAGE_KEY, JSON.stringify(next));
      window.dispatchEvent(new CustomEvent('scratchrobin:branched-tree-prefs', {detail: next}));
    }
  } catch (_err) {
    // Ignore storage quota or sandbox errors
  }
  return next;
}

function collectDescendantIds(node, acc = []) {
  const children = Array.isArray(node?.children) ? node.children : [];
  for (const child of children) {
    if (!child.disabled) {
      acc.push(child.id);
    }
    collectDescendantIds(child, acc);
  }
  return acc;
}

function computeCheckState(node, checkedSet) {
  const children = Array.isArray(node?.children) ? node.children : [];
  if (children.length === 0) {
    return {checked: checkedSet.has(node.id), indeterminate: false};
  }
  const descendants = collectDescendantIds(node);
  if (descendants.length === 0) {
    return {checked: checkedSet.has(node.id), indeterminate: false};
  }
  let checkedCount = 0;
  for (const id of descendants) {
    if (checkedSet.has(id)) checkedCount += 1;
  }
  if (checkedCount === 0) return {checked: false, indeterminate: false};
  if (checkedCount === descendants.length) return {checked: true, indeterminate: false};
  return {checked: false, indeterminate: true};
}

/**
 * Computes both:
 * 1) Structural trunk + quadratic elbow SVG path commands for every expanded branch
 * 2) Continuous unbroken multi-level stepped waterfall active trace from root to active node
 */
export function computeBranchedTreeGeometry(flatRows, selectedId, {stepX = 15, radius = 7, rowHeight = 28, basePad = 10} = {}) {
  const trunkX = (depth) => basePad + (depth - 1) * stepX + 8;
  const r = Math.min(radius, Math.floor(stepX * 0.6), Math.floor(rowHeight * 0.45));
  const structuralPaths = [];

  const indexById = new Map();
  flatRows.forEach((entry, idx) => {
    indexById.set(entry.id, idx);
  });

  // Group visible direct children by parentId
  const childrenIndicesByParent = new Map();
  flatRows.forEach((entry, idx) => {
    if (entry.parentId != null && indexById.has(entry.parentId)) {
      let list = childrenIndicesByParent.get(entry.parentId);
      if (!list) {
        list = [];
        childrenIndicesByParent.set(entry.parentId, list);
      }
      list.push(idx);
    }
  });

  for (const [parentId, childIndices] of childrenIndicesByParent.entries()) {
    const parentIdx = indexById.get(parentId);
    if (parentIdx === undefined || childIndices.length === 0) continue;
    const firstChild = flatRows[childIndices[0]];
    const x = trunkX(firstChild.depth);
    const yStart = parentIdx * rowHeight + Math.round(rowHeight * 0.72);
    const lastIdx = childIndices[childIndices.length - 1];
    const yLast = lastIdx * rowHeight + Math.round(rowHeight * 0.5);

    if (yLast - r > yStart) {
      structuralPaths.push(`M ${x} ${yStart} V ${yLast - r}`);
    }
    for (const cIdx of childIndices) {
      const yChild = cIdx * rowHeight + Math.round(rowHeight * 0.5);
      const yCurveStart = Math.max(yStart, yChild - r);
      const xEnd = x + stepX - 2;
      structuralPaths.push(`M ${x} ${yCurveStart} Q ${x} ${yChild} ${x + r} ${yChild} H ${xEnd}`);
    }
  }

  // Build continuous unbroken stepped waterfall active trace from root ancestor -> selectedId
  let activeTracePath = '';
  if (selectedId != null && indexById.has(selectedId)) {
    const selectedIdx = indexById.get(selectedId);
    const selectedEntry = flatRows[selectedIdx];
    if (selectedEntry && selectedEntry.depth >= 1) {
      // Collect chain [a_0, a_1, ..., a_D = selectedEntry]
      const chain = [];
      let cursor = selectedEntry;
      while (cursor) {
        chain.unshift(cursor);
        cursor = cursor.parentId != null && indexById.has(cursor.parentId)
          ? flatRows[indexById.get(cursor.parentId)]
          : null;
      }
      if (chain.length >= 2) {
        const segments = [];
        for (let i = 1; i < chain.length; i += 1) {
          const parentEntry = chain[i - 1];
          const childEntry = chain[i];
          const pIdx = indexById.get(parentEntry.id);
          const cIdx = indexById.get(childEntry.id);
          const x = trunkX(childEntry.depth);
          const yParentJoin = i === 1
            ? pIdx * rowHeight + Math.round(rowHeight * 0.72)
            : pIdx * rowHeight + Math.round(rowHeight * 0.5);
          const yChildCenter = cIdx * rowHeight + Math.round(rowHeight * 0.5);
          const isFinal = i === chain.length - 1;
          const xHorizEnd = isFinal ? x + stepX - 2 : trunkX(chain[i + 1].depth);

          if (i === 1) {
            segments.push(`M ${x} ${yParentJoin}`);
          }
          const yElbowStart = Math.max(yParentJoin, yChildCenter - r);
          if (yElbowStart > yParentJoin) {
            segments.push(`V ${yElbowStart}`);
          }
          segments.push(`Q ${x} ${yChildCenter} ${x + r} ${yChildCenter}`);
          if (xHorizEnd > x + r) {
            if (!isFinal) {
              // Smooth corner turning downward into the next child trunk!
              const nextR = Math.min(r, Math.max(1, xHorizEnd - (x + r)));
              if (xHorizEnd - nextR > x + r) {
                segments.push(`H ${xHorizEnd - nextR}`);
              }
              segments.push(`Q ${xHorizEnd} ${yChildCenter} ${xHorizEnd} ${yChildCenter + nextR}`);
            } else {
              segments.push(`H ${xHorizEnd}`);
            }
          }
        }
        activeTracePath = segments.join(' ');
      }
    }
  }

  const maxDepth = flatRows.reduce((acc, row) => Math.max(acc, row.depth), 0);
  const svgWidth = basePad + Math.max(1, maxDepth + 1) * stepX + 16;
  const svgHeight = flatRows.length * rowHeight;

  return {
    structuralPath: structuralPaths.join(' '),
    activeTracePath,
    svgWidth,
    svgHeight,
  };
}

/**
 * Standardized clean-room React Bits Branched Menu multi-level hierarchy tree
 * wrapped in @base-ui/react/scroll-area for auto-hiding X & Y overlay scrollbars.
 */
export function ScratchBranchedTree({
  items = [],
  label = 'Navigation tree',
  selectedId: controlledSelectedId,
  defaultSelectedId = null,
  expandedIds: controlledExpandedIds,
  defaultExpandedIds,
  onSelect,
  onActivate,
  onToggle,
  onContextMenu,
  onDragStart,
  checkable = false,
  checkedIds = [],
  onCheckedChange,
  stepX: stepXProp,
  radius: radiusProp,
  rowHeight: rowHeightProp,
  stickyAncestors: stickyAncestorsProp,
  virtualizeThreshold = 250,
  emptyMessage = 'No items available',
  renderIcon,
  renderBadge,
  className = '',
  style,
}) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);

  const [prefs, setPrefs] = useState(() => readBranchedTreePreferences());
  useEffect(() => {
    const onPrefs = (event) => {
      if (event?.detail) setPrefs(event.detail);
      else setPrefs(readBranchedTreePreferences());
    };
    if (typeof window !== 'undefined') {
      window.addEventListener('scratchrobin:branched-tree-prefs', onPrefs);
      return () => window.removeEventListener('scratchrobin:branched-tree-prefs', onPrefs);
    }
    return undefined;
  }, []);

  const stepX = stepXProp ?? prefs.stepX ?? DEFAULT_BRANCHED_TREE_OPTIONS.stepX;
  const radius = radiusProp ?? prefs.radius ?? DEFAULT_BRANCHED_TREE_OPTIONS.radius;
  const rowHeight = rowHeightProp ?? prefs.rowHeight ?? DEFAULT_BRANCHED_TREE_OPTIONS.rowHeight;
  const stickyAncestors = stickyAncestorsProp ?? prefs.stickyAncestors ?? DEFAULT_BRANCHED_TREE_OPTIONS.stickyAncestors;

  const [uncontrolledSelectedId, setUncontrolledSelectedId] = useState(defaultSelectedId);
  const selectedId = controlledSelectedId !== undefined ? controlledSelectedId : uncontrolledSelectedId;

  const [uncontrolledExpanded, setUncontrolledExpanded] = useState(() => {
    if (Array.isArray(defaultExpandedIds)) return new Set(defaultExpandedIds);
    // Default expand depth 0 roots that declare defaultExpanded !== false
    const initial = new Set();
    for (const root of items) {
      if (root.defaultExpanded || root.expanded) initial.add(root.id);
    }
    return initial;
  });

  const expandedSet = useMemo(
    () => (controlledExpandedIds !== undefined ? new Set(controlledExpandedIds) : uncontrolledExpanded),
    [controlledExpandedIds, uncontrolledExpanded]
  );

  const checkedSet = useMemo(() => new Set(checkedIds), [checkedIds]);

  const flatRows = useMemo(() => {
    const out = [];
    const walk = (nodes, depth, parentId, ancestors) => {
      if (!Array.isArray(nodes)) return;
      for (const node of nodes) {
        const children = Array.isArray(node.children) ? node.children : [];
        const expandable = Boolean(node.hasChildren || node.expandable || children.length > 0);
        const expanded = expandable && expandedSet.has(node.id);
        const entry = {
          id: node.id,
          node,
          label: node.label ?? node.name ?? String(node.id),
          depth,
          parentId,
          ancestors,
          expandable,
          expanded,
          disabled: Boolean(node.disabled),
          loading: Boolean(node.loading),
        };
        out.push(entry);
        if (expanded && children.length > 0) {
          walk(children, depth + 1, node.id, [...ancestors, {id: node.id, label: entry.label, node}]);
        }
      }
    };
    walk(items, 0, null, []);
    return out;
  }, [items, expandedSet]);

  const selectedEntry = useMemo(
    () => flatRows.find((r) => r.id === selectedId) || null,
    [flatRows, selectedId]
  );

  const basePad = 8;
  const geometry = useMemo(
    () => computeBranchedTreeGeometry(flatRows, selectedId, {stepX, radius, rowHeight, basePad}),
    [flatRows, selectedId, stepX, radius, rowHeight]
  );

  // Lightweight scroll windowing when visible rows exceed virtualizeThreshold
  const viewportRef = useRef(null);
  const [scrollTop, setScrollTop] = useState(0);
  const isVirtualized = flatRows.length > virtualizeThreshold;

  const visibleSlice = useMemo(() => {
    if (!isVirtualized) {
      return {startIndex: 0, endIndex: flatRows.length, rows: flatRows};
    }
    const viewportHeight = viewportRef.current?.clientHeight || 600;
    const overscan = 16;
    const startIndex = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
    const endIndex = Math.min(flatRows.length, Math.ceil((scrollTop + viewportHeight) / rowHeight) + overscan);
    return {
      startIndex,
      endIndex,
      rows: flatRows.slice(startIndex, endIndex),
    };
  }, [isVirtualized, flatRows, scrollTop, rowHeight]);

  const handleSelect = useCallback((entry, event) => {
    if (entry.disabled) return;
    if (controlledSelectedId === undefined) {
      setUncontrolledSelectedId(entry.id);
    }
    onSelect?.(entry.node, event);
  }, [controlledSelectedId, onSelect]);

  const handleToggle = useCallback((entry, nextExpanded, event) => {
    if (entry.disabled || !entry.expandable) return;
    const targetState = typeof nextExpanded === 'boolean' ? nextExpanded : !entry.expanded;
    if (controlledExpandedIds === undefined) {
      setUncontrolledExpanded((prev) => {
        const next = new Set(prev);
        if (targetState) next.add(entry.id);
        else next.delete(entry.id);
        return next;
      });
    }
    onToggle?.(entry.node, targetState, event);
  }, [controlledExpandedIds, onToggle]);

  const handleCheckToggle = useCallback((entry, nextChecked) => {
    if (entry.disabled) return;
    const next = new Set(checkedSet);
    const affected = [entry.id, ...collectDescendantIds(entry.node)];
    for (const id of affected) {
      if (nextChecked) next.add(id);
      else next.delete(id);
    }
    onCheckedChange?.(Array.from(next), entry.node, nextChecked);
  }, [checkedSet, onCheckedChange]);

  const rowRefs = useRef(new Map());
  const focusRowByIndex = (idx) => {
    const clamped = Math.max(0, Math.min(flatRows.length - 1, idx));
    const target = flatRows[clamped];
    if (!target) return;
    const el = rowRefs.current.get(target.id);
    el?.focus?.();
  };

  return (
    <div
      className={['sr-branched-tree', className].filter(Boolean).join(' ')}
      style={{'--sr-tree-row-height': `${rowHeight}px`, ...style}}
    >
      {stickyAncestors && selectedEntry && selectedEntry.ancestors.length > 0 && (
        <div className="sr-branched-sticky-ancestors" aria-label="Selected ancestor path">
          {selectedEntry.ancestors.map((anc, idx) => (
            <span key={anc.id} style={{display: 'inline-flex', alignItems: 'center', gap: 2}}>
              {idx > 0 && <span aria-hidden="true" style={{opacity: 0.5}}>›</span>}
              <button
                type="button"
                className="sr-branched-ancestor-crumb"
                onClick={(e) => {
                  const ancEntry = flatRows.find((r) => r.id === anc.id);
                  if (ancEntry) handleSelect(ancEntry, e);
                }}
              >
                {anc.label}
              </button>
            </span>
          ))}
        </div>
      )}

      <ScratchScrollArea
        orientation="both"
        viewportRef={viewportRef}
        onScroll={(e) => {
          if (isVirtualized) {
            setScrollTop(e.currentTarget.scrollTop);
          }
        }}
        style={{flex: '1 1 auto', minHeight: 0}}
      >
        {flatRows.length === 0 ? (
          <div style={{padding: '16px 12px', color: 'var(--sr-text-muted)', fontSize: '0.8rem'}}>
            {emptyMessage}
          </div>
        ) : (
          <div
            role="tree"
            aria-label={label}
            className="sr-branched-canvas"
            style={{
              minHeight: geometry.svgHeight,
              position: 'relative',
              paddingTop: isVirtualized ? visibleSlice.startIndex * rowHeight : 0,
              paddingBottom: isVirtualized ? Math.max(0, (flatRows.length - visibleSlice.endIndex) * rowHeight) : 0,
            }}
          >
            <svg
              aria-hidden="true"
              className="sr-branched-svg"
              width={geometry.svgWidth}
              height={geometry.svgHeight}
              viewBox={`0 0 ${geometry.svgWidth} ${geometry.svgHeight}`}
            >
              {geometry.structuralPath && (
                <path d={geometry.structuralPath} className="sr-branched-path-structural" />
              )}
              {geometry.activeTracePath && (
                <path d={geometry.activeTracePath} className="sr-branched-path-active" />
              )}
            </svg>

            {visibleSlice.rows.map((entry, localIdx) => {
              const globalIdx = visibleSlice.startIndex + localIdx;
              const isSelected = entry.id === selectedId;
              const indentPx = basePad + entry.depth * stepX;
              const checkState = checkable ? computeCheckState(entry.node, checkedSet) : null;
              const delta = entry.node.delta; // 'add' | 'modify' | 'drop'
              const badgeText = entry.node.badge ?? (entry.node.count !== undefined ? String(entry.node.count) : null);

              return (
                <div
                  key={String(entry.id)}
                  ref={(el) => {
                    if (el) rowRefs.current.set(entry.id, el);
                    else rowRefs.current.delete(entry.id);
                  }}
                  role="treeitem"
                  aria-level={entry.depth + 1}
                  aria-selected={isSelected}
                  aria-expanded={entry.expandable ? entry.expanded : undefined}
                  aria-disabled={entry.disabled || undefined}
                  aria-busy={entry.loading || undefined}
                  tabIndex={isSelected || (selectedId == null && globalIdx === 0) ? 0 : -1}
                  draggable={!entry.disabled && Boolean(onDragStart || entry.node.draggable)}
                  className="sr-branched-row"
                  style={{
                    height: rowHeight,
                    paddingLeft: indentPx,
                    opacity: entry.disabled ? 0.48 : 1,
                  }}
                  onClick={(event) => {
                    handleSelect(entry, event);
                    if (entry.expandable && entry.node.toggleOnRowClick) {
                      handleToggle(entry, !entry.expanded, event);
                    }
                  }}
                  onDoubleClick={(event) => {
                    if (entry.disabled) return;
                    if (entry.expandable && !entry.node.activateWithoutToggle) {
                      handleToggle(entry, !entry.expanded, event);
                    }
                    onActivate?.(entry.node, event);
                  }}
                  onContextMenu={(event) => {
                    if (entry.disabled) return;
                    handleSelect(entry, event);
                    if (onContextMenu) {
                      event.preventDefault();
                      onContextMenu(entry.node, event);
                    }
                  }}
                  onDragStart={(event) => {
                    if (!entry.disabled) onDragStart?.(entry.node, event);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'ArrowDown') {
                      event.preventDefault();
                      focusRowByIndex(globalIdx + 1);
                      if (flatRows[globalIdx + 1]) handleSelect(flatRows[globalIdx + 1], event);
                    } else if (event.key === 'ArrowUp') {
                      event.preventDefault();
                      focusRowByIndex(globalIdx - 1);
                      if (flatRows[globalIdx - 1]) handleSelect(flatRows[globalIdx - 1], event);
                    } else if (event.key === 'ArrowRight') {
                      event.preventDefault();
                      if (entry.expandable && !entry.expanded) {
                        handleToggle(entry, true, event);
                      } else if (entry.expandable && entry.expanded && flatRows[globalIdx + 1]?.parentId === entry.id) {
                        focusRowByIndex(globalIdx + 1);
                        handleSelect(flatRows[globalIdx + 1], event);
                      }
                    } else if (event.key === 'ArrowLeft') {
                      event.preventDefault();
                      if (entry.expandable && entry.expanded) {
                        handleToggle(entry, false, event);
                      } else if (entry.parentId != null) {
                        const pIdx = flatRows.findIndex((r) => r.id === entry.parentId);
                        if (pIdx >= 0) {
                          focusRowByIndex(pIdx);
                          handleSelect(flatRows[pIdx], event);
                        }
                      }
                    } else if (event.key === 'Home') {
                      event.preventDefault();
                      focusRowByIndex(0);
                      if (flatRows[0]) handleSelect(flatRows[0], event);
                    } else if (event.key === 'End') {
                      event.preventDefault();
                      focusRowByIndex(flatRows.length - 1);
                      if (flatRows[flatRows.length - 1]) handleSelect(flatRows[flatRows.length - 1], event);
                    } else if (event.key === 'Enter') {
                      event.preventDefault();
                      if (entry.expandable && !onActivate) {
                        handleToggle(entry, !entry.expanded, event);
                      } else {
                        onActivate?.(entry.node, event);
                      }
                    } else if (event.key === ' ') {
                      event.preventDefault();
                      if (checkable) {
                        handleCheckToggle(entry, !checkState?.checked);
                      } else {
                        handleSelect(entry, event);
                      }
                    }
                  }}
                >
                  {entry.expandable ? (
                    <button
                      type="button"
                      tabIndex={-1}
                      aria-label={`${entry.expanded ? 'Collapse' : 'Expand'} ${entry.label}`}
                      className="sr-branched-expander"
                      onClick={(event) => {
                        event.stopPropagation();
                        handleToggle(entry, !entry.expanded, event);
                      }}
                    >
                      <svg
                        width="11"
                        height="11"
                        viewBox="0 0 12 12"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        aria-hidden="true"
                        style={{transform: entry.expanded ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 160ms ease'}}
                      >
                        <polyline points="4 2.5 8 6 4 9.5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </button>
                  ) : (
                    <span style={{width: 16, flexShrink: 0}} aria-hidden="true" />
                  )}

                  {checkable && (
                    <Checkbox
                      label=""
                      checked={checkState.checked}
                      indeterminate={checkState.indeterminate}
                      disabled={entry.disabled}
                      inputProps={{'aria-label': `Select ${entry.label}`}}
                      onChange={(nextChecked) => handleCheckToggle(entry, nextChecked)}
                    />
                  )}

                  {(renderIcon || entry.node.icon) && (
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        width: 16,
                        height: 16,
                        flexShrink: 0,
                      }}
                    >
                      {renderIcon ? renderIcon(entry.node, entry) : entry.node.icon}
                    </span>
                  )}

                  <span style={{fontSize: '0.8125rem', lineHeight: 1.25}}>
                    {entry.label}
                  </span>

                  {entry.node.secondaryLabel && (
                    <span className="sr-bui-mono" style={{color: 'var(--sr-text-muted)', fontSize: '0.72rem'}}>
                      {entry.node.secondaryLabel}
                    </span>
                  )}

                  {entry.loading && (
                    <span style={{fontSize: '0.7rem', color: 'var(--sr-accent)'}}>…</span>
                  )}

                  {delta && (
                    <span
                      className="sr-branched-badge"
                      data-delta={delta}
                      aria-label={delta === 'add' ? 'Added' : delta === 'modify' ? 'Modified' : 'Dropped'}
                    >
                      {delta === 'add' ? '+' : delta === 'modify' ? '~' : '−'}
                    </span>
                  )}

                  {entry.node.suspect && (
                    <span className="sr-branched-badge" data-delta="modify">suspect</span>
                  )}

                  {renderBadge
                    ? renderBadge(entry.node, entry)
                    : badgeText !== null && (
                      <span className="sr-branched-badge">{badgeText}</span>
                    )}
                </div>
              );
            })}
          </div>
        )}
      </ScratchScrollArea>
    </div>
  );
}

ScratchBranchedTree.propTypes = {
  items: PropTypes.array,
  label: PropTypes.string,
  selectedId: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  defaultSelectedId: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  expandedIds: PropTypes.array,
  defaultExpandedIds: PropTypes.array,
  onSelect: PropTypes.func,
  onActivate: PropTypes.func,
  onToggle: PropTypes.func,
  onContextMenu: PropTypes.func,
  onDragStart: PropTypes.func,
  checkable: PropTypes.bool,
  checkedIds: PropTypes.array,
  onCheckedChange: PropTypes.func,
  stepX: PropTypes.number,
  radius: PropTypes.number,
  rowHeight: PropTypes.number,
  stickyAncestors: PropTypes.bool,
  virtualizeThreshold: PropTypes.number,
  emptyMessage: PropTypes.node,
  renderIcon: PropTypes.func,
  renderBadge: PropTypes.func,
  className: PropTypes.string,
  style: PropTypes.object,
};

export default ScratchBranchedTree;
