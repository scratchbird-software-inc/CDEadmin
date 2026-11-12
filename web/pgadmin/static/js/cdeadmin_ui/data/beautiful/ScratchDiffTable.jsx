/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect} from 'react';
import PropTypes from 'prop-types';
import {ensureScratchBaseStyles} from '../../base/ScratchBaseStyles';
import {ScratchScrollArea} from '../../base/ScratchScrollArea';
import {Switch} from '../../primitives/Choice';
import {Button, IconButton} from '../../primitives/Button';

function normalizeDiffKind(kind) {
  const k = String(kind || '').toLowerCase();
  if (k === 'add' || k === 'added' || k === 'create' || k === 'source_only' || k === '+') return 'add';
  if (k === 'drop' || k === 'dropped' || k === 'delete' || k === 'target_only' || k === '-') return 'drop';
  if (k === 'modify' || k === 'modified' || k === 'alter' || k === 'changed' || k === 'different' || k === '~') return 'modify';
  return 'identical';
}

const DIFF_LABELS = Object.freeze({
  add: {symbol: '+', label: 'ADDED', tone: 'success'},
  modify: {symbol: '~', label: 'MODIFIED', tone: 'warning'},
  drop: {symbol: '−', label: 'DROPPED', tone: 'danger'},
  identical: {symbol: '=', label: 'IDENTICAL', tone: undefined},
});

/**
 * Clean-room Beautiful UI Semantic Diff Table for Schema Comparison,
 * Native Operation Impact Previews, Staged Data Edits, and DDN Version Checkpoints.
 */
export function ScratchDiffTable({
  items = [],
  includedIds,
  onToggleInclude,
  onIncludeAll,
  onExcludeAll,
  inspectedId = null,
  onInspectItem,
  caption = 'Comparison differences',
  emptyMessage = 'No differences detected',
  showIncludeToggle = true,
  className = '',
  style,
}) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);

  const includedSet = includedIds ? new Set(includedIds.map(String)) : null;

  return (
    <div className={['sr-bui-card', className].filter(Boolean).join(' ')} style={style}>
      {showIncludeToggle && (onIncludeAll || onExcludeAll) && items.length > 0 && (
        <div className="sr-bui-toolbar" style={{justifyContent: 'space-between'}}>
          <span style={{fontSize: '0.76rem', color: 'var(--sr-text-secondary)', fontWeight: 600}}>
            {includedSet ? `${includedSet.size} of ${items.length} changes selected to carry` : `${items.length} changes`}
          </span>
          <div style={{display: 'inline-flex', gap: 6}}>
            {onIncludeAll && <Button onClick={onIncludeAll}>Include all</Button>}
            {onExcludeAll && <Button onClick={onExcludeAll}>Exclude all</Button>}
          </div>
        </div>
      )}

      <ScratchScrollArea orientation="both" style={{flex: '1 1 auto', minHeight: 0}}>
        <table className="sr-bui-table" aria-label={caption}>
          <thead>
            <tr>
              <th className="sr-bui-th" style={{width: 110}}>Delta</th>
              <th className="sr-bui-th">Object / Element</th>
              <th className="sr-bui-th">Kind</th>
              <th className="sr-bui-th">Before → After</th>
              {showIncludeToggle && onToggleInclude && (
                <th className="sr-bui-th" style={{width: 96, textAlign: 'center'}}>Carry</th>
              )}
              {onInspectItem && (
                <th className="sr-bui-th" style={{width: 48, textAlign: 'right'}}>Inspect</th>
              )}
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td
                  colSpan={4 + (showIncludeToggle && onToggleInclude ? 1 : 0) + (onInspectItem ? 1 : 0)}
                  className="sr-bui-td"
                  style={{padding: '22px 16px', textAlign: 'center', color: 'var(--sr-text-muted)'}}
                >
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              items.map((item, idx) => {
                const id = String(item.id ?? item.objectId ?? item.name ?? idx);
                const diffKind = normalizeDiffKind(item.delta ?? item.status ?? item.changeType ?? item.action);
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
                      {item.label ?? item.name ?? item.target ?? id}
                      {item.destructive && (
                        <span className="sr-bui-pill" data-tone="danger" style={{marginLeft: 6}}>
                          destructive
                        </span>
                      )}
                    </td>
                    <td className="sr-bui-td">
                      <span className="sr-bui-pill">{item.objectType ?? item.kind ?? 'object'}</span>
                    </td>
                    <td className="sr-bui-td sr-bui-mono">
                      {item.before !== undefined || item.after !== undefined ? (
                        <span>
                          {item.before !== undefined && (
                            <span style={{color: 'var(--sr-danger)', textDecoration: diffKind === 'drop' ? 'line-through' : 'none'}}>
                              {String(item.before)}
                            </span>
                          )}
                          {item.before !== undefined && item.after !== undefined && (
                            <span style={{marginInline: 6, color: 'var(--sr-text-muted)'}}>→</span>
                          )}
                          {item.after !== undefined && (
                            <span style={{color: 'var(--sr-success)'}}>{String(item.after)}</span>
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
                          inputProps={{'aria-label': `Carry ${item.label ?? item.name ?? id}`}}
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
                          label={`Inspect ${item.label ?? item.name ?? id}`}
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
  caption: PropTypes.string,
  emptyMessage: PropTypes.node,
  showIncludeToggle: PropTypes.bool,
  className: PropTypes.string,
  style: PropTypes.object,
};

export default ScratchDiffTable;
