/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import {Popover as BasePopover} from '@base-ui/react/popover';
import {Checkbox} from '../../primitives/Choice';
import {Button} from '../../primitives/Button';
import {SearchField} from '../../primitives/AdvancedControls';
import {ScratchRecordsTable} from './ScratchRecordsTable';

/**
 * Clean-room Beautiful UI Faceted Filter Table:
 * Combines instant text search, @base-ui/react Popover faceted filter chips,
 * bulk selection action strip, and ScratchRecordsTable.
 */
export function ScratchFilterTable({
  columns = [],
  rows = [],
  facets = [],
  searchPlaceholder = 'Filter rows…',
  bulkActions = [],
  toolbarTrailing = null,
  ...tableProps
}) {
  const [searchQuery, setSearchQuery] = useState('');
  const [facetSelections, setFacetSelections] = useState({}); // { [facetId]: string[] }
  const [selectedIds, setSelectedIds] = useState([]);

  const effectiveSelected = tableProps.selectedRowIds ?? selectedIds;
  const handleSelectChange = tableProps.onSelectionChange ?? setSelectedIds;

  const filteredRows = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return rows.filter((row) => {
      // Facet checks
      for (const facet of facets) {
        const chosen = facetSelections[facet.id];
        if (Array.isArray(chosen) && chosen.length > 0) {
          const val = String(row?.[facet.column ?? facet.id] ?? '');
          if (!chosen.includes(val)) return false;
        }
      }
      // Text query check
      if (!q) return true;
      return columns.some((col) => {
        const key = col.accessorKey ?? col.key ?? col.name ?? col.id;
        const cell = key ? (row?.[key] ?? row?.values?.[key]) : '';
        return String(cell ?? '').toLowerCase().includes(q);
      });
    });
  }, [rows, columns, facets, facetSelections, searchQuery]);

  const activeFacetCount = Object.values(facetSelections).reduce(
    (sum, arr) => sum + (Array.isArray(arr) && arr.length > 0 ? 1 : 0),
    0
  );

  const toolbar = (
    <div style={{display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8, width: '100%'}}>
      <div style={{minWidth: 200, maxWidth: 280, flex: '1 1 200px'}}>
        <SearchField
          aria-label={searchPlaceholder}
          label=""
          placeholder={searchPlaceholder}
          value={searchQuery}
          onChange={setSearchQuery}
        />
      </div>

      {facets.map((facet) => {
        const chosen = facetSelections[facet.id] || [];
        const options = facet.options || Array.from(
          new Set(rows.map((r) => String(r?.[facet.column ?? facet.id] ?? '')).filter(Boolean))
        ).map((v) => ({value: v, label: v}));

        return (
          <BasePopover.Root key={facet.id}>
            <BasePopover.Trigger
              className="sr-bui-chip"
              data-active={chosen.length > 0 ? 'true' : undefined}
            >
              <span>+ {facet.label}</span>
              {chosen.length > 0 && (
                <span className="sr-bui-pill" data-tone="info" style={{padding: '0 6px'}}>
                  {chosen.length}
                </span>
              )}
            </BasePopover.Trigger>
            <BasePopover.Portal>
              <BasePopover.Positioner sideOffset={5} align="start" style={{zIndex: 'var(--cde-layer-popover, 2400)'}}>
                <BasePopover.Popup className="sr-popover-popup" style={{minWidth: 200, padding: 8}}>
                  <div style={{fontSize: '0.72rem', fontWeight: 700, marginBottom: 6, color: 'var(--sr-text-secondary)'}}>
                    {facet.label}
                  </div>
                  <div style={{display: 'flex', flexDirection: 'column', gap: 6}}>
                    {options.map((opt) => {
                      const val = String(opt.value);
                      const isChecked = chosen.includes(val);
                      return (
                        <Checkbox
                          key={val}
                          label={opt.label}
                          checked={isChecked}
                          onChange={(checked) => {
                            setFacetSelections((prev) => ({
                              ...prev,
                              [facet.id]: checked
                                ? [...chosen, val]
                                : chosen.filter((item) => item !== val),
                            }));
                          }}
                        />
                      );
                    })}
                  </div>
                </BasePopover.Popup>
              </BasePopover.Positioner>
            </BasePopover.Portal>
          </BasePopover.Root>
        );
      })}

      {(searchQuery || activeFacetCount > 0) && (
        <Button
          onClick={() => {
            setSearchQuery('');
            setFacetSelections({});
          }}
        >
          Reset filters
        </Button>
      )}

      {effectiveSelected.length > 0 && bulkActions.length > 0 && (
        <div style={{display: 'inline-flex', alignItems: 'center', gap: 6, paddingLeft: 6, borderLeft: '1px solid var(--sr-border-subtle)'}}>
          <span className="sr-bui-pill" data-tone="info">{effectiveSelected.length} selected</span>
          {bulkActions.map((act) => (
            <Button
              key={act.id || act.label}
              intent={act.intent || 'neutral'}
              onClick={() => act.onClick?.(effectiveSelected)}
            >
              {act.label}
            </Button>
          ))}
        </div>
      )}

      {toolbarTrailing && <div style={{marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6}}>{toolbarTrailing}</div>}
    </div>
  );

  return (
    <ScratchRecordsTable
      {...tableProps}
      columns={columns}
      rows={filteredRows}
      selectedRowIds={effectiveSelected}
      onSelectionChange={handleSelectChange}
      toolbarSlot={toolbar}
    />
  );
}

ScratchFilterTable.propTypes = {
  columns: PropTypes.array,
  rows: PropTypes.array,
  facets: PropTypes.arrayOf(PropTypes.shape({
    id: PropTypes.string.isRequired,
    label: PropTypes.string.isRequired,
    column: PropTypes.string,
    options: PropTypes.array,
  })),
  searchPlaceholder: PropTypes.string,
  bulkActions: PropTypes.array,
  toolbarTrailing: PropTypes.node,
  selectedRowIds: PropTypes.array,
  onSelectionChange: PropTypes.func,
};

export default ScratchFilterTable;
