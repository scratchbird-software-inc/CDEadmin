/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Editable grid of records for a descriptor `grid` (or `privileges`) field:
 * one row per record, one typed cell per declared column, add / remove /
 * move. Used for columns, constraints, parameters, membership and privilege
 * grids on every engine; the engine only declares the columns.
 */

import {useState} from 'react';
import PropTypes from 'prop-types';
import {Box, Stack} from '../primitives/Layout';
import {Button, IconButton} from '../primitives/Button';
import {ValidationMessage} from '../feedback/Indicators';
import {ScratchScrollArea} from '../base/ScratchScrollArea';
import {ensureScratchBaseStyles} from '../base/ScratchBaseStyles';
import {activeFields} from './descriptors';
import FieldControl from './FieldControl';

/** Columns shown in the row; the rest open in the row's details drawer. */
export const MAX_INLINE_COLUMNS = 6;

const CELL_MIN_WIDTH = {text: 160, number: 96, boolean: 72, select: 150, multiselect: 200,
  reference: 180, code: 240, password: 150, keyvalue: 220, grid: 260};

function emptyRow(columns) {
  const row = {};
  for(const column of columns) {
    if(column.default !== undefined) row[column.field_id] = column.default;
    else if(column.control === 'boolean') row[column.field_id] = false;
    else if(column.control === 'grid') row[column.field_id] = [];
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
 * The columns a grid shows: not `hidden` (provider bookkeeping the editor
 * carries but nobody edits), and not conditional columns that apply to no
 * row. The first MAX_INLINE_COLUMNS not marked `detail` are inline.
 */
export function gridColumns(columns, rows, draft={}) {
  const shown = (columns || []).filter((column) => column.hidden !== true).filter((column) =>
    !column.visible_when || rows.some((row) => activeFields([column], {draft: {...draft, ...row}}).length > 0));
  const inline = shown.filter((column) => !column.detail).slice(0, MAX_INLINE_COLUMNS);
  return {inline, detail: shown.filter((column) => !inline.includes(column))};
}

export default function RecordGrid({field, rows, onChange, draft={}, context={}, resourceKind,
  disabled=false, error, cellErrors={}, help, mode='create'}) {
  const [selected, setSelected] = useState(null);
  const [expanded, setExpanded] = useState(() => new Set());
  const columns = field.columns || [];
  const {inline, detail} = gridColumns(columns, rows, draft);
  const toggleDetail = (index) => setExpanded((current) => {
    const next = new Set(current);
    if(next.has(index)) next.delete(index); else next.add(index);
    return next;
  });
  const cellError = (index, column) => (cellErrors || {})[`${field.field_id}[${index}].${column.field_id}`];
  const cell = (row, index, column) => <FieldControl field={{...column, label: `${column.label} (row ${index + 1})`}}
    value={row[column.field_id]} dense inGrid mode={mode} error={cellError(index, column)}
    disabled={disabled || lockedCell(column, row, mode)}
    draft={{...draft, ...row}} context={context} resourceKind={resourceKind}
    onChange={(value) => update(index, column.field_id, value)} />;
  const label = field.label;
  const update = (index, columnId, value) => {
    const next = rows.map((row, position) => position === index ? {...row, [columnId]: value} : row);
    onChange(next);
  };
  const remove = (index) => {
    onChange(rows.filter((_row, position) => position !== index));
    setSelected(null);
  };
  const move = (index, delta) => {
    const target = index + delta;
    if(target < 0 || target >= rows.length) return;
    const next = rows.slice();
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
    setSelected(target);
  };
  const add = () => {
    onChange([...rows, emptyRow(columns)]);
    setSelected(rows.length);
  };
  const reorderable = field.reorderable !== false;
  const headingId = `grid-${field.field_id}`;
  ensureScratchBaseStyles();

  const inspectRowInDrawer = (index, row, rowDetail) => {
    setSelected(index);
    if (rowDetail.length === 0 || typeof window === 'undefined') return;
    if (!document?.querySelector?.('[data-cdeadmin-qa-key="project-shell-backdrop"]')) return;
    try {
      window.dispatchEvent(
        new CustomEvent('scratchrobin:inspect-right-drawer', {
          detail: {
            open: true,
            node: (
              <Box sx={{p: 1.5}} data-cdeadmin-qa-key={`subnode-inspector.${field.field_id}.${index}`}>
                <Box component="h4" sx={{m: 0, mb: 1, fontSize: '0.82rem', fontWeight: 700}}>
                  {singular(label)} #{index + 1} — Extended Attributes
                </Box>
                <Stack gap="compact">
                  {rowDetail.map((column) => (
                    <Box key={column.field_id}>{cell(row, index, column)}</Box>
                  ))}
                </Stack>
              </Box>
            ),
          },
        })
      );
    } catch {
      // Non-DOM or restricted test environment.
    }
  };

  return <Box role="group" aria-labelledby={headingId} data-cdeadmin-qa-key={`object-editor.grid.${field.field_id}`}
    className="sr-bui-table-card"
    sx={{borderColor: error ? 'var(--sr-danger)' : undefined}}>
    <Stack direction="row" gap="compact" className="sr-bui-toolbar" sx={{alignItems: 'center'}}>
      <Box id={headingId} component="span" className="sr-bui-toolbar-title" sx={{flex: 1}}>
        {label}{field.required ? ' *' : ''}
      </Box>
      <Button size="small" intent="neutral" disabled={disabled} onClick={add}
        data-cdeadmin-qa-key={`object-editor.grid.${field.field_id}.add`}>
        Add {singular(label)}
      </Button>
    </Stack>
    {rows.length === 0 && <Box sx={{fontSize: '0.75rem', color: 'text.secondary', px: 1.5, py: 1}}>
      No {label.toLowerCase()} yet.
    </Box>}
    {rows.length > 0 && <ScratchScrollArea orientation="both" style={{width: '100%'}}>
      <Box component="table" className="sr-bui-table" sx={{borderCollapse: 'collapse', width: '100%'}}
        aria-label={label}>
        <Box component="thead">
          <Box component="tr">
            {reorderable && <Box component="th" scope="col" className="sr-bui-th" sx={headerSx}>#</Box>}
            {inline.map((column) => <Box key={column.field_id} component="th" scope="col" className="sr-bui-th"
              sx={{...headerSx, minWidth: CELL_MIN_WIDTH[column.control] || 140}}>
              {column.label}{column.required ? ' *' : ''}
            </Box>)}
            <Box component="th" scope="col" className="sr-bui-th" sx={{...headerSx, ...stickySx}}>Actions</Box>
          </Box>
        </Box>
        <Box component="tbody">
          {rows.map((row, index) => {
            const visible = activeFields(columns, {draft: {...draft, ...row}});
            const rowDetail = detail.filter((column) => visible.includes(column));
            const open = expanded.has(index);
            const detailErrors = rowDetail.some((column) => cellError(index, column));
            return [<Box component="tr" key={index} className="sr-bui-tr"
              data-selected={selected === index ? 'true' : undefined}
              aria-selected={selected === index || undefined}
              onFocus={() => setSelected(index)}
              onClick={() => inspectRowInDrawer(index, row, rowDetail)}>
              {reorderable && <Box component="td" className="sr-bui-td" sx={{...cellSx, textAlign: 'center', fontSize: '0.75rem',
                color: 'text.secondary'}}>{index + 1}</Box>}
              {inline.map((column) => <Box key={column.field_id} component="td" className="sr-bui-td" sx={cellSx}>
                {visible.includes(column) ? cell(row, index, column) : <Box aria-hidden="true" />}
              </Box>)}
              <Box component="td" className="sr-bui-td" sx={{...cellSx, ...stickySx, whiteSpace: 'nowrap'}}>
                {rowDetail.length > 0 && <Button size="small" intent={detailErrors ? 'destructive' : 'neutral'}
                  aria-expanded={open} onClick={(ev) => {
                    ev.stopPropagation();
                    toggleDetail(index);
                    inspectRowInDrawer(index, row, rowDetail);
                  }}
                  data-cdeadmin-qa-key={`object-editor.grid.${field.field_id}.details.${index}`}>
                  {open ? 'Hide details' : `Details (${rowDetail.length})`}
                </Button>}
                {reorderable && <IconButton label={`Move row ${index + 1} up`} disabled={disabled || index === 0}
                  onClick={() => move(index, -1)}>↑</IconButton>}
                {reorderable && <IconButton label={`Move row ${index + 1} down`}
                  disabled={disabled || index === rows.length - 1} onClick={() => move(index, 1)}>↓</IconButton>}
                <IconButton label={`Remove row ${index + 1}`} disabled={disabled}
                  onClick={() => remove(index)}>×</IconButton>
              </Box>
            </Box>, open && rowDetail.length > 0 && <Box component="tr" key={`${index}-detail`}>
              <Box component="td" colSpan={inline.length + (reorderable ? 2 : 1)}
                sx={{...cellSx, bgcolor: 'var(--sr-surface-subtle)'}} aria-label={`Row ${index + 1} details`}>
                <Box sx={{display: 'grid', gap: 1, p: 1, gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))'}}>
                  {rowDetail.map((column) => <Box key={column.field_id}>{cell(row, index, column)}</Box>)}
                </Box>
              </Box>
            </Box>];
          })}
        </Box>
      </Box>
    </ScratchScrollArea>}
    {error && <Box sx={{px: 1.5, py: 0.75}}><ValidationMessage status="error">{error}</ValidationMessage></Box>}
    {!error && help && <Box sx={{fontSize: '0.75rem', color: 'text.secondary', px: 1.5, py: 0.75}}>{help}</Box>}
  </Box>;
}

const headerSx = {textAlign: 'left', fontSize: '0.75rem', fontWeight: 600, p: 0.5, borderBottom: '1px solid',
  borderColor: 'divider', whiteSpace: 'nowrap'};
const cellSx = {p: 0.5, verticalAlign: 'top', borderBottom: '1px solid', borderColor: 'divider'};
// The actions column stays in view while a wide grid scrolls sideways.
const stickySx = {position: 'sticky', right: 0, bgcolor: 'background.paper', borderLeft: '1px solid',
  borderColor: 'divider', zIndex: 1};

function singular(label) {
  const lower = String(label || 'row').toLowerCase();
  if(lower.endsWith('ies')) return lower.slice(0, -3) + 'y';
  if(lower.endsWith('s') && !lower.endsWith('ss')) return lower.slice(0, -1);
  return lower;
}

RecordGrid.propTypes = {
  field: PropTypes.object.isRequired,
  rows: PropTypes.array.isRequired,
  onChange: PropTypes.func.isRequired,
  draft: PropTypes.object,
  context: PropTypes.object,
  resourceKind: PropTypes.string,
  disabled: PropTypes.bool,
  error: PropTypes.string,
  cellErrors: PropTypes.object,
  help: PropTypes.string,
  mode: PropTypes.string,
};
