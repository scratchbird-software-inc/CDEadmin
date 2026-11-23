/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {ensureScratchBaseStyles} from '../../base/ScratchBaseStyles';
import {ScratchScrollArea} from '../../base/ScratchScrollArea';
import {Switch} from '../../primitives/Choice';
import {Button, IconButton} from '../../primitives/Button';
import {SearchField} from '../../primitives/AdvancedControls';
import {serializeGridData} from '../gridIO';

export function normalizeDiffKind(kind) {
  const k = String(kind || '').toLowerCase();
  if (
    k === 'add' ||
    k === 'added' ||
    k === 'create' ||
    k === 'source_only' ||
    k === '+' ||
    k.startsWith('add_') ||
    k.startsWith('create_')
  ) {
    return 'add';
  }
  if (
    k === 'drop' ||
    k === 'dropped' ||
    k === 'remove' ||
    k === 'removed' ||
    k === 'delete' ||
    k === 'deleted' ||
    k === 'target_only' ||
    k === '-' ||
    k.startsWith('drop_') ||
    k.startsWith('remove_') ||
    k.startsWith('delete_')
  ) {
    return 'drop';
  }
  if (
    k === 'modify' ||
    k === 'modified' ||
    k === 'alter' ||
    k === 'changed' ||
    k === 'different' ||
    k === 'rename' ||
    k === '~' ||
    k.startsWith('modify_') ||
    k.startsWith('alter_') ||
    k.startsWith('rename_') ||
    k.startsWith('review_')
  ) {
    return 'modify';
  }
  return 'identical';
}

const DIFF_LABELS = Object.freeze({
  add: {symbol: '+', label: 'ADDED', tone: 'success'},
  modify: {symbol: '~', label: 'MODIFIED', tone: 'warning'},
  drop: {symbol: '−', label: 'DROPPED', tone: 'danger'},
  identical: {symbol: '=', label: 'IDENTICAL', tone: undefined},
});

/**
 * Canonical Single Diff Mode Component across ScratchRobin:
 * Used for Schema Comparison, Native Operation Impact Previews, ERD Alter Plans,
 * Design Checkpoints, Screen Mesh Visual Diffs, Data Contract Version Diffs,
 * BI Model Revisions, and Catalog Comparison Diffs.
 */
export function ScratchDiffTable({
  items = [],
  includedIds,
  onToggleInclude,
  onIncludeAll,
  onExcludeAll,
  inspectedId = null,
  onInspectItem,
  title,
  caption = 'Comparison differences',
  qaKey,
  emptyMessage = 'No differences detected',
  showIncludeToggle = true,
  searchable = false,
  filterable = false,
  exportable = false,
  className = '',
  style,
}) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);

  const [searchQuery, setSearchQuery] = useState('');
  const [deltaFilter, setDeltaFilter] = useState('all');
  const [sortState, setSortState] = useState(null); // { col, desc }

  const effectiveCaption = title || caption;
  const includedSet = includedIds ? new Set(includedIds.map(String)) : null;

  const enrichedItems = useMemo(
    () =>
      items.map((item, idx) => {
        const id = String(item.id ?? item.objectId ?? item.path ?? item.name ?? idx);
        const diffKind = normalizeDiffKind(
          item.delta ?? item.status ?? item.change ?? item.changeType ?? item.action
        );
        const displayName = String(item.label ?? item.name ?? item.path ?? item.target ?? id);
        const displayKind = String(item.objectType ?? item.kind ?? 'object');
        const isDestructive = Boolean(item.destructive || item.risk === 'destructive');
        const summaryText =
          item.before !== undefined || item.after !== undefined
            ? `${item.before ?? ''} -> ${item.after ?? ''}`
            : String(item.summary ?? item.sql ?? item.details ?? '');
        return {
          raw: item,
          id,
          diffKind,
          displayName,
          displayKind,
          isDestructive,
          summaryText,
        };
      }),
    [items]
  );

  const deltaCounts = useMemo(() => {
    const counts = {all: enrichedItems.length, add: 0, modify: 0, drop: 0, identical: 0};
    for (const entry of enrichedItems) {
      counts[entry.diffKind] = (counts[entry.diffKind] || 0) + 1;
    }
    return counts;
  }, [enrichedItems]);

  const filteredItems = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const filtered = enrichedItems.filter((entry) => {
      if (deltaFilter !== 'all' && entry.diffKind !== deltaFilter) return false;
      if (!q) return true;
      return (
        entry.displayName.toLowerCase().includes(q) ||
        entry.displayKind.toLowerCase().includes(q) ||
        entry.summaryText.toLowerCase().includes(q)
      );
    });
    if (!sortState) return filtered;
    const copy = [...filtered];
    copy.sort((a, b) => {
      const av =
        sortState.col === 'delta'
          ? a.diffKind
          : sortState.col === 'kind'
            ? a.displayKind
            : sortState.col === 'summary'
              ? a.summaryText
              : a.displayName;
      const bv =
        sortState.col === 'delta'
          ? b.diffKind
          : sortState.col === 'kind'
            ? b.displayKind
            : sortState.col === 'summary'
              ? b.summaryText
              : b.displayName;
      const cmp = String(av).localeCompare(String(bv), undefined, {
        numeric: true,
        sensitivity: 'base',
      });
      return sortState.desc ? -cmp : cmp;
    });
    return copy;
  }, [enrichedItems, deltaFilter, searchQuery, sortState]);

  const toggleSort = (col) => {
    setSortState((prev) => {
      if (!prev || prev.col !== col) return {col, desc: false};
      if (!prev.desc) return {col, desc: true};
      return null;
    });
  };

  const handleCopyCsv = async () => {
    const cols = [
      {key: 'delta', label: 'Delta'},
      {key: 'name', label: 'Object / Element'},
      {key: 'kind', label: 'Kind'},
      {key: 'summary', label: 'Before -> After'},
    ];
    const rows = filteredItems.map((e) => ({
      delta: DIFF_LABELS[e.diffKind].label,
      name: e.displayName,
      kind: e.displayKind,
      summary: e.summaryText,
    }));
    const csv = serializeGridData(cols, rows, 'csv');
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(csv);
    }
    return csv;
  };

  const showTopToolbar =
    Boolean(title) ||
    searchable ||
    filterable ||
    exportable ||
    (showIncludeToggle && (onIncludeAll || onExcludeAll) && items.length > 0);

  return (
    <div
      data-cdeadmin-qa-key={qaKey}
      className={['sr-bui-card', className].filter(Boolean).join(' ')}
      style={style}
    >
      {showTopToolbar && (
        <div
          className="sr-bui-toolbar"
          style={{
            display: 'flex',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 8,
            justifyContent: 'space-between',
          }}
        >
          <div style={{display: 'inline-flex', alignItems: 'center', flexWrap: 'wrap', gap: 8}}>
            {title && <span className="sr-bui-toolbar-title">{title}</span>}
            {showIncludeToggle && (onIncludeAll || onExcludeAll) && items.length > 0 && (
              <span style={{fontSize: '0.76rem', color: 'var(--sr-text-secondary)', fontWeight: 600}}>
                {includedSet
                  ? `${includedSet.size} of ${items.length} changes selected to carry`
                  : `${items.length} changes`}
              </span>
            )}
            {searchable && (
              <div style={{minWidth: 180, maxWidth: 240}}>
                <SearchField
                  aria-label={gettext('Filter differences')}
                  label=""
                  placeholder={gettext('Filter differences…')}
                  value={searchQuery}
                  onChange={setSearchQuery}
                />
              </div>
            )}
            {filterable && items.length > 0 && (
              <div style={{display: 'inline-flex', gap: 4, flexWrap: 'wrap'}}>
                {[
                  {id: 'all', label: gettext('All'), count: deltaCounts.all},
                  {id: 'add', label: 'ADDED', count: deltaCounts.add},
                  {id: 'modify', label: 'MODIFIED', count: deltaCounts.modify},
                  {id: 'drop', label: 'DROPPED', count: deltaCounts.drop},
                ]
                  .filter((f) => f.id === 'all' || f.count > 0)
                  .map((f) => (
                    <button
                      key={f.id}
                      type="button"
                      className="sr-bui-chip"
                      data-active={deltaFilter === f.id ? 'true' : undefined}
                      onClick={() => setDeltaFilter(f.id)}
                    >
                      <span>{f.label}</span>
                      <span className="sr-bui-pill" style={{padding: '0 5px'}}>
                        {f.count}
                      </span>
                    </button>
                  ))}
              </div>
            )}
          </div>

          <div style={{display: 'inline-flex', gap: 6, flexWrap: 'wrap'}}>
            {exportable && filteredItems.length > 0 && (
              <Button size="small" intent="neutral" onClick={handleCopyCsv}>
                {gettext('Copy CSV')}
              </Button>
            )}
            {showIncludeToggle && onIncludeAll && items.length > 0 && (
              <Button onClick={onIncludeAll}>{gettext('Include all')}</Button>
            )}
            {showIncludeToggle && onExcludeAll && items.length > 0 && (
              <Button onClick={onExcludeAll}>{gettext('Exclude all')}</Button>
            )}
          </div>
        </div>
      )}

      <ScratchScrollArea orientation="both" style={{flex: '1 1 auto', minHeight: 0}}>
        <table className="sr-bui-table" aria-label={effectiveCaption}>
          <thead>
            <tr>
              <th
                className="sr-bui-th"
                style={{width: 110, cursor: 'pointer'}}
                onClick={() => toggleSort('delta')}
              >
                Delta {sortState?.col === 'delta' ? (sortState.desc ? '↓' : '↑') : ''}
              </th>
              <th
                className="sr-bui-th"
                style={{cursor: 'pointer'}}
                onClick={() => toggleSort('name')}
              >
                Object / Element {sortState?.col === 'name' ? (sortState.desc ? '↓' : '↑') : ''}
              </th>
              <th
                className="sr-bui-th"
                style={{cursor: 'pointer'}}
                onClick={() => toggleSort('kind')}
              >
                Kind {sortState?.col === 'kind' ? (sortState.desc ? '↓' : '↑') : ''}
              </th>
              <th
                className="sr-bui-th"
                style={{cursor: 'pointer'}}
                onClick={() => toggleSort('summary')}
              >
                Before → After {sortState?.col === 'summary' ? (sortState.desc ? '↓' : '↑') : ''}
              </th>
              {showIncludeToggle && onToggleInclude && (
                <th className="sr-bui-th" style={{width: 96, textAlign: 'center'}}>
                  Carry
                </th>
              )}
              {onInspectItem && (
                <th className="sr-bui-th" style={{width: 48, textAlign: 'right'}}>
                  Inspect
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {filteredItems.length === 0 ? (
              <tr>
                <td
                  colSpan={
                    4 +
                    (showIncludeToggle && onToggleInclude ? 1 : 0) +
                    (onInspectItem ? 1 : 0)
                  }
                  className="sr-bui-td"
                  style={{padding: '22px 16px', textAlign: 'center', color: 'var(--sr-text-muted)'}}
                >
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              filteredItems.map((entry) => {
                const {raw: item, id, diffKind, displayName, displayKind, isDestructive} = entry;
                const meta = DIFF_LABELS[diffKind];
                const isIncluded = includedSet ? includedSet.has(id) : Boolean(item.included ?? true);
                const isInspected = inspectedId !== null && String(inspectedId) === id;

                return (
                  <tr
                    key={id}
                    className="sr-bui-tr"
                    data-diff={diffKind !== 'identical' ? diffKind : undefined}
                    data-inspected={isInspected ? 'true' : undefined}
                    onClick={() => onInspectItem?.(item, id)}
                    style={{cursor: onInspectItem ? 'pointer' : undefined}}
                  >
                    <td className="sr-bui-td">
                      <span className="sr-bui-pill" data-tone={meta.tone}>
                        <span>{meta.symbol}</span>
                        <span>{meta.label}</span>
                      </span>
                    </td>
                    <td className="sr-bui-td sr-bui-mono" style={{fontWeight: 600}}>
                      {displayName}
                      {isDestructive && (
                        <span className="sr-bui-pill" data-tone="danger" style={{marginLeft: 6}}>
                          destructive
                        </span>
                      )}
                    </td>
                    <td className="sr-bui-td">
                      <span className="sr-bui-pill">{displayKind}</span>
                    </td>
                    <td className="sr-bui-td sr-bui-mono">
                      {item.before !== undefined || item.after !== undefined ? (
                        <span>
                          {item.before !== undefined && (
                            <span
                              style={{
                                color: 'var(--sr-danger)',
                                textDecoration: diffKind === 'drop' ? 'line-through' : 'none',
                              }}
                            >
                              {typeof item.before === 'object' && item.before !== null
                                ? JSON.stringify(item.before)
                                : String(item.before)}
                            </span>
                          )}
                          {item.before !== undefined && item.after !== undefined && (
                            <span style={{marginInline: 6, color: 'var(--sr-text-muted)'}}>→</span>
                          )}
                          {item.after !== undefined && (
                            <span style={{color: 'var(--sr-success)'}}>
                              {typeof item.after === 'object' && item.after !== null
                                ? JSON.stringify(item.after)
                                : String(item.after)}
                            </span>
                          )}
                        </span>
                      ) : (
                        <span style={{color: 'var(--sr-text-secondary)'}}>
                          {item.summary ?? item.sql ?? item.details ?? '—'}
                        </span>
                      )}
                    </td>
                    {showIncludeToggle && onToggleInclude && (
                      <td
                        className="sr-bui-td"
                        style={{textAlign: 'center'}}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Switch
                          label=""
                          checked={isIncluded}
                          inputProps={{'aria-label': `Carry ${displayName}`}}
                          onChange={(nextChecked) => onToggleInclude(id, nextChecked, item)}
                        />
                      </td>
                    )}
                    {onInspectItem && (
                      <td
                        className="sr-bui-td"
                        style={{textAlign: 'right'}}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <IconButton
                          label={`Inspect ${displayName}`}
                          onClick={() => onInspectItem(item, id)}
                          style={{minWidth: 24, minHeight: 24, padding: 2}}
                        >
                          ◨
                        </IconButton>
                      </td>
                    )}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </ScratchScrollArea>
    </div>
  );
}

ScratchDiffTable.propTypes = {
  items: PropTypes.array,
  includedIds: PropTypes.array,
  onToggleInclude: PropTypes.func,
  onIncludeAll: PropTypes.func,
  onExcludeAll: PropTypes.func,
  inspectedId: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  onInspectItem: PropTypes.func,
  title: PropTypes.string,
  caption: PropTypes.string,
  qaKey: PropTypes.string,
  emptyMessage: PropTypes.node,
  showIncludeToggle: PropTypes.bool,
  searchable: PropTypes.bool,
  filterable: PropTypes.bool,
  exportable: PropTypes.bool,
  className: PropTypes.string,
  style: PropTypes.object,
};

export default ScratchDiffTable;
