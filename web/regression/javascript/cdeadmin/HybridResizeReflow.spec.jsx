/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {createRef} from 'react';
import {act, render} from '@testing-library/react';
import {Box} from '../../../pgadmin/static/js/cdeadmin_ui/primitives/Layout';
import UnifiedDataGrid from '../../../pgadmin/static/js/cdeadmin_ui/data/UnifiedDataGrid';
import RecordGrid, {RECORD_GRID_MODES} from '../../../pgadmin/static/js/cdeadmin_ui/objects/RecordGrid';
import {DISPLAY_MODES} from '../../../pgadmin/static/js/cdeadmin_ui/surfaces/dataEditSurfaceHelpers';

const ACCOUNT_COLUMNS = [
  {name: 'DOC_NAME', label: 'DOC_NAME', native_type: 'VARCHAR', key: true, editable: true},
  {name: 'ACCOUNT_NAME', label: 'ACCOUNT_NAME', native_type: 'VARCHAR', key: true, editable: true},
  {name: 'COMPANY', label: 'COMPANY', native_type: 'VARCHAR', key: true, editable: true},
  {name: 'ROOT_TYPE', label: 'ROOT_TYPE', native_type: 'VARCHAR', key: true, editable: true},
  {name: 'REPORT_TYPE', label: 'REPORT_TYPE', native_type: 'VARCHAR', key: true, editable: true},
  {name: 'ACCOUNT_TYPE', label: 'ACCOUNT_TYPE', native_type: 'VARCHAR', key: true, editable: true},
  {name: 'ACCOUNT_CURRENCY', label: 'ACCOUNT_CURRENCY', native_type: 'VARCHAR', key: true, editable: true},
];

const ACCOUNT_ROWS = [
  {
    identity_token: 'row-14',
    row_number: 14,
    values: {
      DOC_NAME: 'COA-CA-111 - MTM',
      ACCOUNT_NAME: '[CA] Avances sur commandes',
      COMPANY: 'Maple Tech Manufacturing',
      ROOT_TYPE: 'Asset',
      REPORT_TYPE: 'Balance Sheet',
      ACCOUNT_TYPE: 'Expense Account',
      ACCOUNT_CURRENCY: 'CAD',
    },
  },
  {
    identity_token: 'row-15',
    row_number: 15,
    values: {
      DOC_NAME: 'COA-CA-112 - NCS',
      ACCOUNT_NAME: '[CA] Comptes clients',
      COMPANY: 'Northstar Cloud Services',
      ROOT_TYPE: 'Asset',
      REPORT_TYPE: 'Balance Sheet',
      ACCOUNT_TYPE: 'Receivable',
      ACCOUNT_CURRENCY: 'USD',
    },
  },
];

describe('Hybrid form dynamic resize & wrap recalculation', () => {
  let originalResizeObserver;
  let activeObservers;

  beforeEach(() => {
    originalResizeObserver = global.ResizeObserver;
    activeObservers = [];
    global.ResizeObserver = class MockResizeObserver {
      constructor(callback) {
        this.callback = callback;
        this.targets = new Set();
        activeObservers.push(this);
      }
      observe(target) {
        this.targets.add(target);
      }
      unobserve(target) {
        this.targets.delete(target);
      }
      disconnect() {
        this.targets.clear();
      }
    };
  });

  afterEach(() => {
    global.ResizeObserver = originalResizeObserver;
  });

  const emitResizeWidth = (widthPx) => {
    act(() => {
      for (const obs of activeObservers) {
        if (obs.targets.size === 0) continue;
        const entries = Array.from(obs.targets).map((target) => {
          Object.defineProperty(target, 'clientWidth', {
            configurable: true,
            value: widthPx,
          });
          return {
            target,
            contentRect: {width: widthPx, height: 640},
          };
        });
        obs.callback(entries);
      }
    });
  };

  it('forwards DOM refs through Box so ResizeObserver attaches to Box containers', () => {
    const boxRef = createRef();
    render(
      <Box ref={boxRef} data-cdeadmin-qa-key="box-ref-check" sx={{minWidth: 0}}>
        content
      </Box>
    );
    expect(boxRef.current).toBeInstanceOf(HTMLElement);
    expect(boxRef.current.getAttribute('data-cdeadmin-qa-key')).toBe('box-ref-check');
    expect(['0', '0px']).toContain(boxRef.current.style.minWidth);
  });

  it('recalculates Hybrid pinned form width and field column wrap on both shrink and expand', () => {
    const {container} = render(
      <UnifiedDataGrid
        columns={ACCOUNT_COLUMNS}
        rows={ACCOUNT_ROWS}
        defaultDisplayMode={DISPLAY_MODES.HYBRID}
        editable
      />
    );

    // 1. Wide viewport (1320px)
    emitResizeWidth(1320);
    let hybridForm = container.querySelector('[data-cdeadmin-qa-key="data-surface-hybrid-pinned-form"]');
    expect(hybridForm).toBeTruthy();
    expect(hybridForm.style.width).toBe('1320px');
    expect(hybridForm.style.maxWidth).toBe('1320px');
    const wideCols = Number(
      hybridForm.querySelector('[data-cell-columns]').getAttribute('data-cell-columns')
    );
    expect(wideCols).toBeGreaterThanOrEqual(5);

    // 2. Medium-narrow shrink (920px) — reproduces shrinking window / opening side drawer
    emitResizeWidth(920);
    hybridForm = container.querySelector('[data-cdeadmin-qa-key="data-surface-hybrid-pinned-form"]');
    expect(hybridForm.style.width).toBe('920px');
    expect(hybridForm.style.maxWidth).toBe('920px');
    const mediumCols = Number(
      hybridForm.querySelector('[data-cell-columns]').getAttribute('data-cell-columns')
    );
    expect(mediumCols).toBeLessThan(wideCols);

    // 3. Compact shrink (520px)
    emitResizeWidth(520);
    hybridForm = container.querySelector('[data-cdeadmin-qa-key="data-surface-hybrid-pinned-form"]');
    expect(hybridForm.style.width).toBe('520px');
    expect(hybridForm.style.maxWidth).toBe('520px');
    const compactCols = Number(
      hybridForm.querySelector('[data-cell-columns]').getAttribute('data-cell-columns')
    );
    expect(compactCols).toBeLessThan(mediumCols);
    expect(compactCols).toBeGreaterThanOrEqual(1);

    // 4. Re-expand back to 1280px — must immediately unwrap back up without hysteresis lock
    emitResizeWidth(1280);
    hybridForm = container.querySelector('[data-cdeadmin-qa-key="data-surface-hybrid-pinned-form"]');
    expect(hybridForm.style.width).toBe('1280px');
    expect(hybridForm.style.maxWidth).toBe('1280px');
    const reExpandedCols = Number(
      hybridForm.querySelector('[data-cell-columns]').getAttribute('data-cell-columns')
    );
    expect(reExpandedCols).toBeGreaterThan(compactCols);
    expect(reExpandedCols).toBeGreaterThanOrEqual(5);
  });

  it('constrains RecordGrid Hybrid detail row to scroll viewport width and reflows on resize', () => {
    const field = {
      field_id: 'accounts',
      label: 'Accounts',
      control: 'grid',
      columns: ACCOUNT_COLUMNS.map((c) => ({
        field_id: c.name,
        label: c.label,
        control: 'text',
      })),
    };
    const rows = ACCOUNT_ROWS.map((r) => ({...r.values}));

    const {container} = render(
      <RecordGrid
        field={field}
        rows={rows}
        defaultPresentation={RECORD_GRID_MODES.HYBRID}
        onChange={() => {}}
      />
    );

    emitResizeWidth(1200);
    let wrap = container.querySelector('[data-cdeadmin-qa-key="record-grid-hybrid-wrap.accounts.0"]');
    expect(wrap).toBeTruthy();
    expect(wrap.style.width).toBe('1180px');
    const wideCols = Number(
      wrap.querySelector('[data-cell-columns]').getAttribute('data-cell-columns')
    );

    emitResizeWidth(500);
    wrap = container.querySelector('[data-cdeadmin-qa-key="record-grid-hybrid-wrap.accounts.0"]');
    expect(wrap.style.width).toBe('480px');
    const narrowCols = Number(
      wrap.querySelector('[data-cell-columns]').getAttribute('data-cell-columns')
    );
    expect(narrowCols).toBeLessThan(wideCols);
  });
});
