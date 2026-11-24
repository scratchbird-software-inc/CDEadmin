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
import {computeCellGridLayout} from './formCellLayout';
import {fieldOptions} from './descriptors';
import {resolveSmartOptions} from './smartFieldDefaults';

export const ADAPTIVE_COL_GAP_PX = 16;
export const ADAPTIVE_ROW_GAP_PX = 12;

/**
 * Shared DN-11 adaptive field-placement grid used across ObjectEditor,
 * OperationDialog, BI ModelFields, and RecordGrid (Hybrid detail rows,
 * Mini-Forms, and Full-Form single-record views).
 *
 * Computes intrinsic field widths from datatype/options via
 * `computeCellGridLayout`, reflows on container resize, and spans `grid`,
 * `privileges`, `keyvalue`, and SQL `code` fields across the full row (`1 / -1`).
 */
export default function AdaptiveFieldPlacementGrid({
  fields,
  draft = {},
  context = {},
  resourceKind,
  qaKey = 'object-editor.cell-grid',
  colGap = ADAPTIVE_COL_GAP_PX,
  rowGap = ADAPTIVE_ROW_GAP_PX,
  renderField,
}) {
  const containerRef = useRef(null);
  const prevColsRef = useRef(null);
  const [availableWidth, setAvailableWidth] = useState(760);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return undefined;
    let rafId = null;
    const win =
      el.ownerDocument?.defaultView ||
      (typeof window !== 'undefined' ? window : null);
    const isJsdom =
      typeof navigator !== 'undefined' && /jsdom/i.test(navigator.userAgent || '');

    const applyWidth = (rawW) => {
      const w = Math.floor(rawW || el.clientWidth || el.getBoundingClientRect?.().width || 0);
      if (w > 80) {
        setAvailableWidth((prev) => (Math.abs(prev - w) >= 1 ? w : prev));
      }
    };

    const scheduleMeasure = (entries) => {
      const entryW = entries?.[0]?.contentRect?.width;
      if (isJsdom || typeof win?.requestAnimationFrame !== 'function') {
        applyWidth(entryW);
        return;
      }
      if (rafId !== null) return;
      rafId = win.requestAnimationFrame(() => {
        rafId = null;
        applyWidth(el.clientWidth || entryW);
      });
    };

    applyWidth(el.clientWidth);
    const ResizeObserverCtor =
      win?.ResizeObserver ||
      (typeof ResizeObserver === 'function' ? ResizeObserver : null);
    const ro = ResizeObserverCtor ? new ResizeObserverCtor(scheduleMeasure) : null;
    if (ro) ro.observe(el);
    const onWinResize = () => scheduleMeasure();
    win?.addEventListener?.('resize', onWinResize);
    return () => {
      if (rafId !== null && typeof win?.cancelAnimationFrame === 'function') {
        win.cancelAnimationFrame(rafId);
      }
      win?.removeEventListener?.('resize', onWinResize);
      ro?.disconnect();
    };
  }, []);

  const optionsByField = useMemo(() => {
    const map = {};
    for (const field of fields) {
      const raw = fieldOptions(field, {context, draft, resourceKind});
      map[field.field_id] = resolveSmartOptions(field, raw);
    }
    return map;
  }, [fields, context, draft, resourceKind]);

  const layout = useMemo(() => {
    const computed = computeCellGridLayout(fields, availableWidth, optionsByField, {
      colGap,
      prevNumCols: null,
    });
    prevColsRef.current = computed.numCols;
    return computed;
  }, [fields, availableWidth, optionsByField, colGap]);

  const placementByField = useMemo(() => {
    const map = new Map();
    for (const p of layout.placements) {
      map.set(p.fieldId, p);
    }
    return map;
  }, [layout.placements]);

  return (
    <div
      ref={containerRef}
      style={{width: '100%', minWidth: 0, overflowX: 'hidden', boxSizing: 'border-box'}}
    >
      <div
        data-cdeadmin-qa-key={qaKey}
        data-cell-columns={layout.numCols}
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${layout.numCols}, minmax(0, 1fr))`,
          columnGap: `${colGap}px`,
          rowGap: `${rowGap}px`,
          alignItems: 'start',
          width: '100%',
        }}
      >
        {fields.map((field) => {
          const placement = placementByField.get(field.field_id) || {
            row: 1,
            colStart: 1,
            span: 1,
          };
          return (
            <div
              key={field.field_id}
              data-cell-span={placement.span}
              style={{
                gridRow: placement.row,
                gridColumn: `${placement.colStart} / span ${placement.span}`,
                minWidth: 0,
              }}
            >
              {renderField(field, placement)}
            </div>
          );
        })}
      </div>
    </div>
  );
}

AdaptiveFieldPlacementGrid.propTypes = {
  fields: PropTypes.array.isRequired,
  draft: PropTypes.object,
  context: PropTypes.object,
  resourceKind: PropTypes.string,
  qaKey: PropTypes.string,
  colGap: PropTypes.number,
  rowGap: PropTypes.number,
  renderField: PropTypes.func.isRequired,
};
