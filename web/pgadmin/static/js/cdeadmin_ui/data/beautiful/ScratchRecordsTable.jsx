/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {ensureScratchBaseStyles} from '../../base/ScratchBaseStyles';
import {ScratchScrollArea} from '../../base/ScratchScrollArea';
import {Checkbox, Select} from '../../primitives/Choice';
import {IconButton} from '../../primitives/Button';

function resolveCellValue(row, col) {
  if (!row) return undefined;
  const key = col.accessorKey ?? col.key ?? col.name ?? col.id;
  if (typeof col.accessorFn === 'function') return col.accessorFn(row);
  if (key && row[key] !== undefined) return row[key];
  if (key && row.values && row.values[key] !== undefined) return row.values[key];
  return undefined;
}

function compareValues(a, b) {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b), undefined, {numeric: true, sensitivity: 'base'});
}

/**
 * Clean-room Beautiful UI Records Table built with ScratchScrollArea,
 * @base-ui/react Checkbox/Select, sortable uppercase headers, monospace
 * technical cells, row-hover quick actions, Area 3c inspector row binding,
 * and automatic row windowing for large datasets.
 */
export function ScratchRecordsTable({
  columns = [],
  rows = [],
  rowKeyGetter,
  caption,
  emptyMessage = 'No records to display',
  selectable = false,
  selectedRowIds = [],
  onSelectionChange,
  inspectedRowId = null,
  onInspectRow,
  onRowDoubleClick,
  rowActions = [],
  pagination = false,
  defaultPageSize = 50,
  pageSizeOptions = [25, 50, 100, 250, 500],
  toolbarSlot = null,
  footerSlot = null,
  virtualizeThreshold = 200,
  rowHeight = 34,
  maxHeight,
  dense = false,
  className = '',
  style,
}) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);

  const [sortState, setSortState] = useState(null); // { colId, desc }
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(defaultPageSize);

  const normalizedCols = useMemo(
    () =>
      columns.map((col, idx) => ({
        ...col,
        colId: String(col.id ?? col.accessorKey ?? col.key ?? col.name ?? idx),
        headerLabel: col.header ?? col.label ?? col.name ?? col.key ?? '',
        sortable: col.sortable !== false,
      })),
    [columns]
  );

  const getRowId = (row, index) => {
    if (typeof rowKeyGetter === 'function') return String(rowKeyGetter(row, index));
    if (row?.id !== undefined && row?.id !== null) return String(row.id);
    if (row?.identity_token !== undefined) return String(row.identity_token);
    if (row?.oid !== undefined) return String(row.oid);
    return String(index);
  };

  const sortedRows = useMemo(() => {
    if (!sortState) return rows;
    const col = normalizedCols.find((c) => c.colId === sortState.colId);
    if (!col) return rows;
    const copy = [...rows];
    copy.sort((rA, rB) => {
      const cmp = compareValues(resolveCellValue(rA, col), resolveCellValue(rB, col));
      return sortState.desc ? -cmp : cmp;
    });
    return copy;
  }, [rows, normalizedCols, sortState]);

  const totalPages = pagination ? Math.max(1, Math.ceil(sortedRows.length / pageSize)) : 1;
  const safePage = pagination ? Math.min(page, totalPages - 1) : 0;

  const pagedRows = useMemo(() => {
    if (!pagination) return sortedRows;
    const start = safePage * pageSize;
    return sortedRows.slice(start, start + pageSize);
  }, [sortedRows, pagination, safePage, pageSize]);

  // Windowing when unpaged row count > virtualizeThreshold
  const viewportRef = useRef(null);
  const [scrollTop, setScrollTop] = useState(0);
  const isVirtualized = !pagination && pagedRows.length > virtualizeThreshold;

  const {startIndex, endIndex, renderedRows} = useMemo(() => {
    if (!isVirtualized) {
      return {startIndex: 0, endIndex: pagedRows.length, renderedRows: pagedRows};
    }
    const vh = viewportRef.current?.clientHeight || 500;
    const overscan = 14;
    const s = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
    const e = Math.min(pagedRows.length, Math.ceil((scrollTop + vh) / rowHeight) + overscan);
    return {startIndex: s, endIndex: e, renderedRows: pagedRows.slice(s, e)};
  }, [isVirtualized, pagedRows, scrollTop, rowHeight]);

  const selectedSet = useMemo(() => new Set(selectedRowIds.map(String)), [selectedRowIds]);
  const allVisibleSelected = pagedRows.length > 0 && pagedRows.every((r, idx) => selectedSet.has(getRowId(r, idx)));
  const someVisibleSelected = !allVisibleSelected && pagedRows.some((r, idx) => selectedSet.has(getRowId(r, idx)));

  const toggleAllVisible = (checked) => {
    const next = new Set(selectedSet);
    pagedRows.forEach((r, idx) => {
      const id = getRowId(r, idx);
      if (checked) next.add(id);
      else next.delete(id);
    });
    onSelectionChange?.(Array.from(next));
  };

  const toggleSingleRow = (rowId, checked) => {
    const next = new Set(selectedSet);
    if (checked) next.add(rowId);
    else next.delete(rowId);
    onSelectionChange?.(Array.from(next));
  };

  const hasActionsCol = rowActions.length > 0 || Boolean(onInspectRow);
  const cellPad = dense ? '5px 10px' : '7px 12px';

  return (
    <div
      className={['sr-bui-card', className].filter(Boolean).join(' ')}
      style={style}
    >
      {toolbarSlot && <div className="sr-bui-toolbar">{toolbarSlot}</div>}

      <ScratchScrollArea
        orientation="both"
        viewportRef={viewportRef}
        onScroll={(e) => {
          if (isVirtualized) setScrollTop(e.currentTarget.scrollTop);
        }}
        style={{flex: '1 1 auto', minHeight: 0, ...(maxHeight ? {maxHeight} : {})}}
      >
        <table className="sr-bui-table" aria-label={caption || 'Data table'}>
          <thead>
            <tr>
              {selectable && (
                <th className="sr-bui-th" style={{width: 36, padding: cellPad}}>
                  <Checkbox
                    label=""
                    checked={allVisibleSelected}
                    indeterminate={someVisibleSelected}
                    inputProps={{'aria-label': 'Select all rows'}}
                    onChange={toggleAllVisible}
                  />
                </th>
              )}
              {normalizedCols.map((col) => {
                const isSorted = sortState?.colId === col.colId;
                const ariaSort = isSorted ? (sortState.desc ? 'descending' : 'ascending') : 'none';
                return (
                  <th
                    key={col.colId}
                    scope="col"
                    aria-sort={col.sortable ? ariaSort : undefined}
                    data-sortable={col.sortable ? 'true' : undefined}
                    className="sr-bui-th"
                    style={{
                      padding: cellPad,
                      width: col.width,
                      textAlign: col.align || (col.numeric ? 'right' : 'left'),
                    }}
                    onClick={() => {
                      if (!col.sortable) return;
                      setSortState((prev) => {
                        if (!prev || prev.colId !== col.colId) return {colId: col.colId, desc: false};
                        if (!prev.desc) return {colId: col.colId, desc: true};
                        return null;
                      });
                    }}
                  >
                    <span style={{display: 'inline-flex', alignItems: 'center', gap: 4}}>
                      <span>{col.headerLabel}</span>
                      {col.typeBadge && (
                        <span className="sr-bui-mono" style={{fontSize: '0.64rem', opacity: 0.7, textTransform: 'none'}}>
                          {col.typeBadge}
                        </span>
                      )}
                      {isSorted && <span aria-hidden="true">{sortState.desc ? '↓' : '↑'}</span>}
                    </span>
                  </th>
                );
              })}
              {hasActionsCol && (
                <th className="sr-bui-th" style={{width: 1, textAlign: 'right', padding: cellPad}}>
                  Actions
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {pagedRows.length === 0 ? (
              <tr>
                <td
                  colSpan={normalizedCols.length + (selectable ? 1 : 0) + (hasActionsCol ? 1 : 0)}
                  className="sr-bui-td"
                  style={{padding: '22px 16px', textAlign: 'center', color: 'var(--sr-text-muted)'}}
                >
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              <>
                {isVirtualized && startIndex > 0 && (
                  <tr aria-hidden="true">
                    <td colSpan={normalizedCols.length + (selectable ? 1 : 0) + (hasActionsCol ? 1 : 0)} style={{height: startIndex * rowHeight, padding: 0, border: 'none'}} />
                  </tr>
                )}
                {renderedRows.map((row, localIdx) => {
                  const rowIndex = startIndex + localIdx;
                  const rowId = getRowId(row, rowIndex);
                  const isSelected = selectedSet.has(rowId);
                  const isInspected = inspectedRowId !== null && String(inspectedRowId) === rowId;

                  return (
                    <tr
                      key={rowId}
                      className="sr-bui-tr"
                      data-selected={isSelected ? 'true' : undefined}
                      data-inspected={isInspected ? 'true' : undefined}
                      onClick={() => onInspectRow?.(row, rowId)}
                      onDoubleClick={() => onRowDoubleClick?.(row, rowId)}
                      style={{cursor: onInspectRow || onRowDoubleClick ? 'pointer' : undefined}}
                    >
                      {selectable && (
                        <td className="sr-bui-td" style={{padding: cellPad, width: 36}}>
                          <Checkbox
                            label=""
                            checked={isSelected}
                            inputProps={{'aria-label': `Select row ${rowId}`}}
                            onChange={(checked) => toggleSingleRow(rowId, checked)}
                          />
                        </td>
                      )}
                      {normalizedCols.map((col) => {
                        const raw = resolveCellValue(row, col);
                        const rendered = typeof col.render === 'function'
                          ? col.render(raw, row, rowIndex)
                          : typeof col.cell === 'function'
                            ? col.cell({getValue: () => raw, row: {original: row, index: rowIndex}})
                            : raw === null
                              ? <span className="sr-bui-mono" style={{color: 'var(--sr-text-muted)', fontStyle: 'italic'}}>NULL</span>
                              : typeof raw === 'boolean'
                                ? <span className="sr-bui-pill" data-tone={raw ? 'success' : undefined}>{raw ? 'true' : 'false'}</span>
                                : col.badgeTone
                                  ? <span className="sr-bui-pill" data-tone={typeof col.badgeTone === 'function' ? col.badgeTone(raw, row) : col.badgeTone}>{String(raw ?? '')}</span>
                                  : String(raw ?? '');

                        return (
                          <td
                            key={col.colId}
                            className={['sr-bui-td', col.mono || col.numeric ? 'sr-bui-mono' : ''].filter(Boolean).join(' ')}
                            style={{
                              padding: cellPad,
                              textAlign: col.align || (col.numeric ? 'right' : 'left'),
                            }}
                          >
                            {rendered}
                          </td>
                        );
                      })}
                      {hasActionsCol && (
                        <td
                          className="sr-bui-td"
                          style={{padding: cellPad, textAlign: 'right', whiteSpace: 'nowrap'}}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <div className="sr-bui-row-actions">
                            {onInspectRow && (
                              <IconButton
                                label={`Inspect row ${rowId} in right drawer`}
                                onClick={() => onInspectRow(row, rowId)}
                                style={{minWidth: 24, minHeight: 24, padding: 2}}
                              >
                                ◨
                              </IconButton>
                            )}
                            {rowActions.map((act) => (
                              <IconButton
                                key={act.id || act.label}
                                label={act.label}
                                disabled={typeof act.disabled === 'function' ? act.disabled(row) : act.disabled}
                                onClick={() => act.onClick?.(row, rowId)}
                                style={{minWidth: 24, minHeight: 24, padding: 2}}
                              >
                                {act.icon ?? act.label}
                              </IconButton>
                            ))}
                          </div>
                        </td>
                      )}
                    </tr>
                  );
                })}
                {isVirtualized && endIndex < pagedRows.length && (
                  <tr aria-hidden="true">
                    <td colSpan={normalizedCols.length + (selectable ? 1 : 0) + (hasActionsCol ? 1 : 0)} style={{height: (pagedRows.length - endIndex) * rowHeight, padding: 0, border: 'none'}} />
                  </tr>
                )}
              </>
            )}
          </tbody>
        </table>
      </ScratchScrollArea>

      {(pagination || footerSlot) && (
        <div className="sr-bui-footer">
          {pagination ? (
            <>
              <div style={{display: 'flex', alignItems: 'center', gap: 8}}>
                <span>
                  {sortedRows.length === 0
                    ? '0 rows'
                    : `${safePage * pageSize + 1}–${Math.min(sortedRows.length, (safePage + 1) * pageSize)} of ${sortedRows.length} rows`}
                </span>
                <Select
                  aria-label="Rows per page"
                  value={pageSize}
                  options={pageSizeOptions.map((n) => ({value: n, label: `${n} / page`}))}
                  onChange={(val) => {
                    setPageSize(Number(val));
                    setPage(0);
                  }}
                  style={{minWidth: 108}}
                />
              </div>
              <div style={{display: 'flex', alignItems: 'center', gap: 4}}>
                <IconButton label="First page" disabled={safePage <= 0} onClick={() => setPage(0)}>«</IconButton>
                <IconButton label="Previous page" disabled={safePage <= 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>‹</IconButton>
                <span style={{paddingInline: 6}}>Page {safePage + 1} of {totalPages}</span>
                <IconButton label="Next page" disabled={safePage >= totalPages - 1} onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}>›</IconButton>
                <IconButton label="Last page" disabled={safePage >= totalPages - 1} onClick={() => setPage(totalPages - 1)}>»</IconButton>
              </div>
            </>
          ) : null}
          {footerSlot}
        </div>
      )}
    </div>
  );
}

ScratchRecordsTable.propTypes = {
  columns: PropTypes.array,
  rows: PropTypes.array,
  rowKeyGetter: PropTypes.func,
  caption: PropTypes.string,
  emptyMessage: PropTypes.node,
  selectable: PropTypes.bool,
  selectedRowIds: PropTypes.array,
  onSelectionChange: PropTypes.func,
  inspectedRowId: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  onInspectRow: PropTypes.func,
  onRowDoubleClick: PropTypes.func,
  rowActions: PropTypes.array,
  pagination: PropTypes.bool,
  defaultPageSize: PropTypes.number,
  pageSizeOptions: PropTypes.array,
  toolbarSlot: PropTypes.node,
  footerSlot: PropTypes.node,
  virtualizeThreshold: PropTypes.number,
  rowHeight: PropTypes.number,
  maxHeight: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
  dense: PropTypes.bool,
  className: PropTypes.string,
  style: PropTypes.object,
};

export default ScratchRecordsTable;
