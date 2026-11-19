/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Dialog} from '../overlays/Dialog';
import {Button} from '../primitives/Button';
import {Box} from '../primitives/Layout';

export default function ColumnOrderDialog({
  open,
  scope,
  allColumns,
  columnLabels,
  visibleNames,
  orderNames,
  onClose,
  onApply,
}) {
  const [order, setOrder] = useState([]);
  const [checkedSet, setCheckedSet] = useState(new Set());

  useEffect(() => {
    if (!open) return;
    const allNames = (allColumns || []).map((c) => c.name);
    const mergedOrder = [
      ...(orderNames || []).filter((n) => allNames.includes(n)),
      ...allNames.filter((n) => !(orderNames || []).includes(n)),
    ];
    setOrder(mergedOrder);
    setCheckedSet(new Set(visibleNames || allNames));
  }, [open, allColumns, visibleNames, orderNames]);

  const move = (idx, dir) => {
    const dst = idx + dir;
    if (dst < 0 || dst >= order.length) return;
    const copy = [...order];
    const [item] = copy.splice(idx, 1);
    copy.splice(dst, 0, item);
    setOrder(copy);
  };

  return (
    <Dialog
      open={open}
      title={
        scope === 'form'
          ? gettext('Mini-Form / Single-Form Fields & Order')
          : gettext('Grid Columns & Field Order')
      }
      size="small"
      onClose={onClose}
      actions={
        <>
          <Button onClick={onClose}>{gettext('Cancel')}</Button>
          <Button
            intent="primary"
            onClick={() => {
              const vis = order.filter((n) => checkedSet.has(n));
              onApply(order, vis.length > 0 ? vis : [order[0]].filter(Boolean));
            }}
          >
            {gettext('Apply')}
          </Button>
        </>
      }
    >
      <Box sx={{display: 'grid', gap: 0.75, maxHeight: '55vh', overflowY: 'auto'}}>
        <Box sx={{display: 'flex', gap: 1, mb: 0.5}}>
          <Button size="small" onClick={() => setCheckedSet(new Set(order))}>
            {gettext('Select All')}
          </Button>
          <Button
            size="small"
            onClick={() => setOrder((allColumns || []).map((c) => c.name))}
          >
            {gettext('Reset Order')}
          </Button>
        </Box>
        {order.map((name, idx) => (
          <div
            key={name}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '4px 8px',
              borderRadius: 6,
              border: '1px solid var(--sr-border-subtle)',
            }}
          >
            <label style={{display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.82rem'}}>
              <input
                type="checkbox"
                checked={checkedSet.has(name)}
                onChange={(e) => {
                  const next = new Set(checkedSet);
                  if (e.target.checked) next.add(name);
                  else next.delete(name);
                  setCheckedSet(next);
                }}
              />
              <span>{columnLabels?.[name] || name}</span>
            </label>
            <div style={{display: 'flex', gap: 4}}>
              <button
                type="button"
                className="sr-btn"
                aria-label={gettext('Move %s up', columnLabels?.[name] || name)}
                style={{minHeight: 22, padding: '0 6px'}}
                disabled={idx === 0}
                onClick={() => move(idx, -1)}
              >
                ↑
              </button>
              <button
                type="button"
                className="sr-btn"
                aria-label={gettext('Move %s down', columnLabels?.[name] || name)}
                style={{minHeight: 22, padding: '0 6px'}}
                disabled={idx === order.length - 1}
                onClick={() => move(idx, 1)}
              >
                ↓
              </button>
            </div>
          </div>
        ))}
      </Box>
    </Dialog>
  );
}

ColumnOrderDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  scope: PropTypes.string,
  allColumns: PropTypes.array,
  columnLabels: PropTypes.object,
  visibleNames: PropTypes.array,
  orderNames: PropTypes.array,
  onClose: PropTypes.func.isRequired,
  onApply: PropTypes.func.isRequired,
};
