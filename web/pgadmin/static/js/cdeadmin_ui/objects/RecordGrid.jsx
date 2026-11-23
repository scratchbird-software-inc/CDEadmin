/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Standardized editable record collection grid for descriptor `grid` (and
 * `privileges`) fields, DDN designer child tables, ContractForm editable grids,
 * and VisualAdministration record lists:
 *   - Supports switchable Grid, Hybrid (active row expanded), Mini-Form, and
 *     Full-Form (single-record with First/Prev/Next/Last navigation) modes.
 *   - Uses AdaptiveFieldPlacementGrid (DN-11 `computeCellGridLayout`) for
 *     Hybrid detail rows, Mini-Forms, and Full-Form so SQL `code` editors and
 *     nested grids span full width (`1 / -1`).
 *   - Keeps Area 3b/3c Right-Drawer inspection live and reactive on edit.
 */

import {useCallback, useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {useLocaleRevision} from '../actions/t_actions';
import {Icon} from '../icons';
import {Box, Stack} from '../primitives/Layout';
import {Button, IconButton} from '../primitives/Button';
import {ValidationMessage} from '../feedback/Indicators';
import {ScratchScrollArea} from '../base/ScratchScrollArea';
import {ensureScratchBaseStyles} from '../base/ScratchBaseStyles';
import {activeFields} from './descriptors';
import AdaptiveFieldPlacementGrid from './AdaptiveFieldPlacementGrid';
import FieldControl from './FieldControl';

/** Columns shown inline in Grid mode; overflow columns open in Hybrid detail / drawer. */
export const MAX_INLINE_COLUMNS = 6;

export const RECORD_GRID_MODES = Object.freeze({
  GRID: 'grid',
  HYBRID: 'hybrid',
  MINI: 'mini',
  FORM: 'form',
});

const CELL_MIN_WIDTH = {
  text: 160,
  number: 96,
  boolean: 72,
  select: 150,
  multiselect: 200,
  reference: 180,
  code: 240,
  password: 150,
  keyvalue: 220,
  grid: 260,
};

function resolveEffectiveColumns(field) {
  if (Array.isArray(field.columns) && field.columns.length > 0) {
    return field.columns;
  }
  if (field.item_kind === 'string') {
    return [
      {
        field_id: 'value',
        label: field.item_label || field.label || gettext('Value'),
        control: 'text',
        required: Boolean(field.required),
      },
    ];
  }
  return [];
}

function emptyRow(columns) {
  const row = {};
  for (const column of columns) {
    if (column.default !== undefined) row[column.field_id] = column.default;
    else if (column.control === 'boolean') row[column.field_id] = false;
    else if (column.control === 'grid') row[column.field_id] = [];
  }
  return row;
}

/**
 * A cell the engine cannot change once its row exists: in alter mode, rows
 * loaded from the record carry an _id; rows added in this edit do not.
 */
export function lockedCell(column, row, mode) {
  return mode === 'alter' && column.editable_after_create === false && row?._id !== undefined;
}

/**
 * The columns a grid shows: excludes `hidden` columns, columns outside the
 * active `mode`, and conditional columns that apply to no row. When more than
 * MAX_INLINE_COLUMNS non-detail columns exist, editable columns take priority
 * over read-only catalog metadata (`oid`, `is_sys_obj`, `inheritedfrom`) so
 * primary editable inputs stay inline.
 */
export function gridColumns(columns, rows = [], draft = {}, mode = 'create', maxInline = MAX_INLINE_COLUMNS) {
  const normalizedRows = (rows || []).map((r) =>
    typeof r === 'object' && r !== null ? r : {value: r}
  );
  const shown = (columns || [])
    .filter((column) => column.hidden !== true)
    .filter((column) => !column.modes || column.modes.includes(mode))
    .filter(
      (column) =>
        !column.visible_when ||
        normalizedRows.some(
          (row) => activeFields([column], {mode, draft: {...draft, ...row}}).length > 0
        )
    );
  const candidates = shown.filter((column) => !column.detail);
  let inline;
  if (candidates.length <= maxInline) {
    inline = candidates;
  } else {
    const editableFirst = candidates.filter((column) => !column.readonly);
    const readonlyRest = candidates.filter((column) => column.readonly);
    const chosenSet = new Set(
      [...editableFirst, ...readonlyRest]
        .slice(0, maxInline)
        .map((c) => c.field_id)
    );
    inline = candidates.filter((c) => chosenSet.has(c.field_id));
  }
  return {inline, detail: shown.filter((column) => !inline.includes(column))};
}

export default function RecordGrid({
  field,
  rows = [],
  onChange,
  draft = {},
  context = {},
  resourceKind,
  disabled = false,
  error,
  cellErrors = {},
  help,
  mode = 'create',
  defaultPresentation = RECORD_GRID_MODES.GRID,
  allowPresentationSwitch = true,
  maxInlineColumns = MAX_INLINE_COLUMNS,
  addLabel,
  emptyText,
  cellLabelFormat,
  fixedItems = false,
  primitiveStrings = false,
}) {
  useLocaleRevision();
  const [selected, setSelected] = useState(0);
  const [drawerRowIndex, setDrawerRowIndex] = useState(null);
  const [expanded, setExpanded] = useState(() => new Set());
  const [presentation, setPresentation] = useState(defaultPresentation);

  const columns = useMemo(() => resolveEffectiveColumns(field), [field]);
  const isPrimitiveStringList =
    primitiveStrings ||
    (field.item_kind === 'string' &&
      rows.length > 0 &&
      rows.every((r) => typeof r === 'string'));

  const objectRows = useMemo(
    () =>
      rows.map((r) =>
        typeof r === 'object' && r !== null ? r : {[columns[0]?.field_id || 'value']: r ?? ''}
      ),
    [rows, columns]
  );

  const emitRows = useCallback(
    (nextObjectRows) => {
      if (isPrimitiveStringList) {
        const key = columns[0]?.field_id || 'value';
        onChange(nextObjectRows.map((r) => String(r?.[key] ?? '')));
      } else {
        onChange(nextObjectRows);
      }
    },
    [isPrimitiveStringList, columns, onChange]
  );

  const {inline, detail} = useMemo(
    () => gridColumns(columns, objectRows, draft, mode, maxInlineColumns),
    [columns, objectRows, draft, mode, maxInlineColumns]
  );

  const safeSelected = objectRows.length > 0 ? Math.min(Math.max(0, selected ?? 0), objectRows.length - 1) : 0;

  const toggleDetail = (index) =>
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });

  const cellError = useCallback(
    (index, column) => (cellErrors || {})[`${field.field_id}[${index}].${column.field_id}`],
    [cellErrors, field.field_id]
  );

  const formatCellAriaLabel = useCallback(
    (column, index) => {
      if (typeof cellLabelFormat === 'function') {
        return cellLabelFormat(column.label, index + 1, column);
      }
      return `${column.label} (row ${index + 1})`;
    },
    [cellLabelFormat]
  );

  const update = useCallback(
    (index, columnId, value) => {
      const next = objectRows.map((row, position) => {
        if (position !== index) return row;
        const updated = {...row, [columnId]: value};
        // Reset dependent select options that are no longer valid for updated row state
        for (const col of columns) {
          if (col.field_id === columnId || !Array.isArray(col.options) || !col.options.length) {
            continue;
          }
          const curVal = updated[col.field_id];
          if (curVal === undefined) continue;
          const hasConditional = col.options.some((opt) => opt?.visible_when);
          if (!hasConditional) continue;
          const stillAllowed = col.options.some(
            (opt) =>
              opt?.value === curVal &&
              (!opt.visible_when ||
                activeFields([{...col, visible_when: opt.visible_when}], {
                  mode,
                  draft: {...draft, ...updated},
                }).length > 0)
          );
          if (!stillAllowed) {
            updated[col.field_id] = col.default !== undefined ? col.default : '';
          }
        }
        return updated;
      });
      emitRows(next);
    },
    [objectRows, columns, mode, draft, emitRows]
  );

  const renderCell = useCallback(
    (row, index, column, {inGrid = true} = {}) => (
      <FieldControl
        field={{...column, label: inGrid ? formatCellAriaLabel(column, index) : column.label}}
        ariaLabel={formatCellAriaLabel(column, index)}
        value={row[column.field_id]}
        dense={inGrid}
        inGrid={inGrid}
        mode={mode}
        error={cellError(index, column)}
        disabled={disabled || fixedItems || lockedCell(column, row, mode)}
        draft={{...draft, ...row}}
        context={context}
        resourceKind={resourceKind}
        onChange={(value) => update(index, column.field_id, value)}
      />
    ),
    [formatCellAriaLabel, mode, cellError, disabled, fixedItems, draft, context, resourceKind, update]
  );

  const label = field.label || '';
  const remove = (index) => {
    emitRows(objectRows.filter((_row, position) => position !== index));
    if (drawerRowIndex === index) setDrawerRowIndex(null);
    setSelected((prev) => Math.max(0, Math.min(prev ?? 0, objectRows.length - 2)));
  };
  const move = (index, delta) => {
    const target = index + delta;
    if (target < 0 || target >= objectRows.length) return;
    const next = objectRows.slice();
    [next[index], next[target]] = [next[target], next[index]];
    emitRows(next);
    setSelected(target);
    if (drawerRowIndex === index) setDrawerRowIndex(target);
  };
  const add = () => {
    const nextRow = emptyRow(columns);
    emitRows([...objectRows, nextRow]);
    setSelected(objectRows.length);
  };

  const reorderable = field.reorderable !== false;
  const isReadOnlyGrid = Boolean(disabled || field.readonly);
  const canAddRemove = !isReadOnlyGrid && !fixedItems;
  const headingId = `grid-${field.field_id}`;
  ensureScratchBaseStyles();

  // Live reactive Right-Drawer (`Area 3b/3c`) synchronization on row/field edit
  useEffect(() => {
    if (drawerRowIndex === null || drawerRowIndex < 0 || drawerRowIndex >= objectRows.length) {
      return;
    }
    if (typeof window === 'undefined') return;
    if (!document?.querySelector?.('[data-cdeadmin-qa-key="project-shell-backdrop"]')) return;
    const row = objectRows[drawerRowIndex];
    const visible = activeFields(columns, {mode, draft: {...draft, ...row}});
    const rowDetail = detail.filter((column) => visible.includes(column));
    if (rowDetail.length === 0) return;
    try {
      window.dispatchEvent(
        new CustomEvent('scratchrobin:inspect-right-drawer', {
          detail: {
            open: true,
            node: (
              <Box
                sx={{p: 1.5}}
                data-cdeadmin-qa-key={`subnode-inspector.${field.field_id}.${drawerRowIndex}`}
              >
                <Box component="h4" sx={{m: 0, mb: 1, fontSize: '0.82rem', fontWeight: 700}}>
                  {singular(label)} #{drawerRowIndex + 1} — {gettext('Extended Attributes')}
                </Box>
                <AdaptiveFieldPlacementGrid
                  fields={rowDetail}
                  draft={{...draft, ...row}}
                  context={context}
                  resourceKind={resourceKind}
                  qaKey={`subnode-inspector-grid.${field.field_id}.${drawerRowIndex}`}
                  renderField={(column) => renderCell(row, drawerRowIndex, column, {inGrid: true})}
                />
              </Box>
            ),
          },
        })
      );
    } catch {
      // Non-DOM or restricted test environment.
    }
  }, [drawerRowIndex, objectRows, columns, detail, mode, draft, context, resourceKind, field.field_id, label, renderCell]);

  const inspectRowInDrawer = (index, rowDetailCount) => {
    setSelected(index);
    if (rowDetailCount > 0) {
      setDrawerRowIndex(index);
    }
  };

  const renderAdaptiveRowForm = (row, index, fieldsToShow, qaPrefix) => (
    <AdaptiveFieldPlacementGrid
      fields={fieldsToShow}
      draft={{...draft, ...row}}
      context={context}
      resourceKind={resourceKind}
      qaKey={`${qaPrefix}.${field.field_id}.${index}`}
      renderField={(column) => renderCell(row, index, column, {inGrid: true})}
    />
  );

  const renderRowActionButtons = (index, rowDetail, open, detailErrors) => (
    <>
      {presentation === RECORD_GRID_MODES.GRID && rowDetail.length > 0 && (
        <Button
          size="small"
          intent={detailErrors ? 'destructive' : 'neutral'}
          aria-expanded={open}
          onClick={(ev) => {
            ev.stopPropagation();
            toggleDetail(index);
            inspectRowInDrawer(index, rowDetail.length);
          }}
          data-cdeadmin-qa-key={`object-editor.grid.${field.field_id}.details.${index}`}
        >
          {open ? gettext('Hide details') : gettext('Details (%s)', rowDetail.length)}
        </Button>
      )}
      {reorderable && (
        <IconButton
          label={gettext('Move row %s up', index + 1)}
          disabled={isReadOnlyGrid || index === 0}
          onClick={() => move(index, -1)}
        >
          <Icon iconKey="action.move_up" decorative />
        </IconButton>
      )}
      {reorderable && (
        <IconButton
          label={gettext('Move row %s down', index + 1)}
          disabled={isReadOnlyGrid || index === objectRows.length - 1}
          onClick={() => move(index, 1)}
        >
          <Icon iconKey="action.move_down" decorative />
        </IconButton>
      )}
      {canAddRemove && (
        <IconButton
          label={gettext('Remove row %s', index + 1)}
          disabled={isReadOnlyGrid}
          onClick={() => remove(index)}
        >
          <Icon iconKey="action.close" decorative />
        </IconButton>
      )}
    </>
  );

  return (
    <Box
      role="group"
      aria-labelledby={headingId}
      data-cdeadmin-qa-key={`object-editor.grid.${field.field_id}`}
      className="sr-bui-table-card"
      sx={{borderColor: error ? 'var(--sr-danger)' : undefined}}
    >
      <Stack
        direction="row"
        gap="compact"
        className="sr-bui-toolbar"
        sx={{alignItems: 'center', flexWrap: 'wrap'}}
      >
        <Box id={headingId} component="span" className="sr-bui-toolbar-title" sx={{flex: 1}}>
          {label}
          {field.required ? ' *' : ''}
        </Box>

        {allowPresentationSwitch && objectRows.length > 0 && columns.length > 1 && (
          <div
            role="group"
            aria-label={gettext('%s display mode', label || 'Grid')}
            style={{
              display: 'inline-flex',
              border: '1px solid var(--sr-border-subtle, rgba(128,128,128,0.28))',
              borderRadius: 5,
              overflow: 'hidden',
            }}
          >
            {[
              {id: RECORD_GRID_MODES.GRID, text: gettext('Grid'), aria: gettext('Grid view')},
              {id: RECORD_GRID_MODES.HYBRID, text: gettext('Hybrid'), aria: gettext('Hybrid view')},
              {id: RECORD_GRID_MODES.MINI, text: gettext('Mini'), aria: gettext('Mini-form view')},
              {id: RECORD_GRID_MODES.FORM, text: gettext('Form'), aria: gettext('Full-form view')},
            ].map((opt) => {
              const active = presentation === opt.id;
              return (
                <button
                  key={opt.id}
                  type="button"
                  aria-label={opt.aria}
                  aria-pressed={active}
                  onClick={() => setPresentation(opt.id)}
                  style={{
                    border: 'none',
                    padding: '2px 7px',
                    fontSize: '0.7rem',
                    fontWeight: active ? 700 : 500,
                    cursor: 'pointer',
                    background: active ? 'var(--sr-accent, #0284c7)' : 'transparent',
                    color: active ? '#ffffff' : 'var(--sr-text-secondary, inherit)',
                  }}
                >
                  {opt.text}
                </button>
              );
            })}
          </div>
        )}

        {canAddRemove && (
          <Button
            size="small"
            intent="neutral"
            disabled={isReadOnlyGrid}
            onClick={add}
            data-cdeadmin-qa-key={`object-editor.grid.${field.field_id}.add`}
          >
            {addLabel || gettext('Add %s', singular(label))}
          </Button>
        )}
      </Stack>

      {objectRows.length === 0 && (
        <Box sx={{fontSize: '0.75rem', color: 'text.secondary', px: 1.5, py: 1}}>
          {emptyText || gettext('No %s yet.', label.toLowerCase())}
        </Box>
      )}

      {/* (a) GRID & (b) HYBRID MODES */}
      {objectRows.length > 0 &&
        (presentation === RECORD_GRID_MODES.GRID || presentation === RECORD_GRID_MODES.HYBRID) && (
        <ScratchScrollArea orientation="both" style={{width: '100%'}}>
          <Box
            component="table"
            className="sr-bui-table"
            sx={{borderCollapse: 'collapse', width: '100%'}}
            aria-label={label}
          >
            <Box component="thead">
              <Box component="tr">
                {reorderable && (
                  <Box component="th" scope="col" className="sr-bui-th" sx={headerSx}>
                    #
                  </Box>
                )}
                {inline.map((column) => (
                  <Box
                    key={column.field_id}
                    component="th"
                    scope="col"
                    className="sr-bui-th"
                    sx={{...headerSx, minWidth: column.minWidth || CELL_MIN_WIDTH[column.control] || 140}}
                  >
                    {column.label}
                    {column.required ? ' *' : ''}
                  </Box>
                ))}
                <Box component="th" scope="col" className="sr-bui-th" sx={{...headerSx, ...stickySx}}>
                  {gettext('Actions')}
                </Box>
              </Box>
            </Box>
            <Box component="tbody">
              {objectRows.map((row, index) => {
                const visible = activeFields(columns, {mode, draft: {...draft, ...row}});
                const rowDetail = detail.filter((column) => visible.includes(column));
                const isRowSelected = safeSelected === index;
                const open =
                    presentation === RECORD_GRID_MODES.HYBRID
                      ? isRowSelected
                      : expanded.has(index);
                const expandedFields =
                    presentation === RECORD_GRID_MODES.HYBRID ? visible : rowDetail;
                const detailErrors = rowDetail.some((column) => cellError(index, column));

                return [
                  <Box
                    component="tr"
                    key={index}
                    className="sr-bui-tr"
                    data-selected={isRowSelected ? 'true' : undefined}
                    aria-selected={isRowSelected || undefined}
                    onFocus={() => setSelected(index)}
                    onClick={() => inspectRowInDrawer(index, rowDetail.length)}
                  >
                    {reorderable && (
                      <Box
                        component="td"
                        className="sr-bui-td"
                        sx={{...cellSx, textAlign: 'center', fontSize: '0.75rem', color: 'text.secondary'}}
                      >
                        {isRowSelected ? `▶ ${index + 1}` : index + 1}
                      </Box>
                    )}
                    {inline.map((column) => (
                      <Box key={column.field_id} component="td" className="sr-bui-td" sx={cellSx}>
                        {visible.includes(column) ? (
                          renderCell(row, index, column, {inGrid: true})
                        ) : (
                          <Box aria-hidden="true" />
                        )}
                      </Box>
                    ))}
                    <Box
                      component="td"
                      className="sr-bui-td"
                      sx={{...cellSx, ...stickySx, whiteSpace: 'nowrap'}}
                    >
                      {renderRowActionButtons(index, rowDetail, open, detailErrors)}
                    </Box>
                  </Box>,
                  open && expandedFields.length > 0 && (
                    <Box component="tr" key={`${index}-detail`} data-cdeadmin-detail-row="true">
                      <Box
                        component="td"
                        colSpan={inline.length + (reorderable ? 2 : 1)}
                        sx={{...cellSx, bgcolor: 'var(--sr-surface-subtle)', p: 1.25}}
                        aria-label={gettext('Row %s details', index + 1)}
                      >
                        {renderAdaptiveRowForm(row, index, expandedFields, 'record-grid-detail')}
                      </Box>
                    </Box>
                  ),
                ];
              })}
            </Box>
          </Box>
        </ScratchScrollArea>
      )}

      {/* (c) MINI-FORMS MODE */}
      {objectRows.length > 0 && presentation === RECORD_GRID_MODES.MINI && (
        <ScratchScrollArea orientation="vertical" style={{width: '100%', maxHeight: 520}}>
          <Stack gap="compact" sx={{p: 1}}>
            {objectRows.map((row, index) => {
              const visible = activeFields(columns, {mode, draft: {...draft, ...row}});
              const isRowSelected = safeSelected === index;
              return (
                <Box
                  key={index}
                  onClick={() => setSelected(index)}
                  sx={{
                    display: 'flex',
                    alignItems: 'stretch',
                    border: '1px solid var(--sr-border-subtle, rgba(128,128,128,0.24))',
                    borderRadius: 1,
                    bgcolor: isRowSelected ? 'var(--sr-surface-selected, rgba(2,132,199,0.06))' : 'transparent',
                  }}
                >
                  <Box
                    sx={{
                      width: 54,
                      flex: '0 0 54px',
                      p: 0.75,
                      borderRight: '1px solid var(--sr-border-subtle, rgba(128,128,128,0.2))',
                      bgcolor: 'var(--sr-surface-subtle)',
                      fontSize: '0.75rem',
                      fontWeight: isRowSelected ? 700 : 500,
                      textAlign: 'center',
                    }}
                  >
                    <div>{isRowSelected ? `▶ ${index + 1}` : index + 1}</div>
                  </Box>
                  <Box sx={{flex: 1, minWidth: 0, p: 1}}>
                    {renderAdaptiveRowForm(row, index, visible, 'record-grid-mini')}
                  </Box>
                  <Box sx={{p: 0.75, display: 'flex', alignItems: 'flex-start', gap: 0.25}}>
                    {renderRowActionButtons(index, [], false, false)}
                  </Box>
                </Box>
              );
            })}
          </Stack>
        </ScratchScrollArea>
      )}

      {/* (d) FULL-FORM (SINGLE RECORD) MODE */}
      {objectRows.length > 0 && presentation === RECORD_GRID_MODES.FORM && (
        <Box sx={{p: 1.25}}>
          <Stack
            direction="row"
            gap="compact"
            sx={{
              alignItems: 'center',
              justifyContent: 'space-between',
              mb: 1,
              pb: 0.75,
              borderBottom: '1px solid var(--sr-border-subtle, rgba(128,128,128,0.2))',
            }}
          >
            <Stack direction="row" gap="compact" sx={{alignItems: 'center'}}>
              <Button
                size="small"
                intent="neutral"
                aria-label={gettext('First record')}
                disabled={safeSelected <= 0}
                onClick={() => setSelected(0)}
              >
                |&lt;
              </Button>
              <Button
                size="small"
                intent="neutral"
                aria-label={gettext('Previous record')}
                disabled={safeSelected <= 0}
                onClick={() => setSelected(safeSelected - 1)}
              >
                &lt;
              </Button>
              <Box component="span" sx={{fontSize: '0.76rem', fontWeight: 600, px: 0.5}}>
                {gettext('Record %s of %s', safeSelected + 1, objectRows.length)}
              </Box>
              <Button
                size="small"
                intent="neutral"
                aria-label={gettext('Next record')}
                disabled={safeSelected >= objectRows.length - 1}
                onClick={() => setSelected(safeSelected + 1)}
              >
                &gt;
              </Button>
              <Button
                size="small"
                intent="neutral"
                aria-label={gettext('Last record')}
                disabled={safeSelected >= objectRows.length - 1}
                onClick={() => setSelected(objectRows.length - 1)}
              >
                &gt;|
              </Button>
            </Stack>
            <Stack direction="row" gap="compact" sx={{alignItems: 'center'}}>
              {renderRowActionButtons(safeSelected, [], false, false)}
            </Stack>
          </Stack>
          {renderAdaptiveRowForm(
            objectRows[safeSelected],
            safeSelected,
            activeFields(columns, {mode, draft: {...draft, ...objectRows[safeSelected]}}),
            'record-grid-full'
          )}
        </Box>
      )}

      {error && (
        <Box sx={{px: 1.5, py: 0.75}}>
          <ValidationMessage status="error">{error}</ValidationMessage>
        </Box>
      )}
      {!error && help && (
        <Box sx={{fontSize: '0.75rem', color: 'text.secondary', px: 1.5, py: 0.75}}>
          {help}
        </Box>
      )}
    </Box>
  );
}

const headerSx = {
  textAlign: 'left',
  fontSize: '0.75rem',
  fontWeight: 600,
  p: 0.5,
  borderBottom: '1px solid',
  borderColor: 'divider',
  whiteSpace: 'nowrap',
};
const cellSx = {p: 0.5, verticalAlign: 'top', borderBottom: '1px solid', borderColor: 'divider'};
const stickySx = {
  position: 'sticky',
  right: 0,
  bgcolor: 'background.paper',
  borderLeft: '1px solid',
  borderColor: 'divider',
  zIndex: 1,
};

function singular(label) {
  const lower = String(label || 'row').toLowerCase();
  if (lower.endsWith('ies')) return lower.slice(0, -3) + 'y';
  if (lower.endsWith('s') && !lower.endsWith('ss')) return lower.slice(0, -1);
  return lower;
}

RecordGrid.propTypes = {
  field: PropTypes.object.isRequired,
  rows: PropTypes.array,
  onChange: PropTypes.func.isRequired,
  draft: PropTypes.object,
  context: PropTypes.object,
  resourceKind: PropTypes.string,
  disabled: PropTypes.bool,
  error: PropTypes.string,
  cellErrors: PropTypes.object,
  help: PropTypes.string,
  mode: PropTypes.string,
  defaultPresentation: PropTypes.string,
  allowPresentationSwitch: PropTypes.bool,
  maxInlineColumns: PropTypes.number,
  addLabel: PropTypes.string,
  emptyText: PropTypes.string,
  cellLabelFormat: PropTypes.func,
  fixedItems: PropTypes.bool,
  primitiveStrings: PropTypes.bool,
};
