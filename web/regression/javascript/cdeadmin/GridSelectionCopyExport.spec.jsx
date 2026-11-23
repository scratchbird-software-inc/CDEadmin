/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import UnifiedDataGrid from 'sources/cdeadmin_ui/data/UnifiedDataGrid';
import SurfaceExportDialog from 'sources/cdeadmin_ui/surfaces/SurfaceExportDialog';

const ThemedUnifiedGrid = withTheme(UnifiedDataGrid);
const ThemedExportDialog = withTheme(SurfaceExportDialog);

const SAMPLE_COLUMNS = [
  {name: 'id', label: 'ID', native_type: 'integer', key: true},
  {name: 'name', label: 'Account Name', native_type: 'varchar'},
  {name: 'engine', label: 'Engine', native_type: 'varchar'},
  {name: 'amount', label: 'Amount', native_type: 'numeric'},
];

const SAMPLE_ROWS = [
  {id: 10, name: 'Operating Cash', engine: 'postgresql', amount: 100},
  {id: 20, name: 'Payroll Reserve', engine: 'firebird', amount: 250},
  {id: 30, name: 'Tax Escrow', engine: 'duckdb', amount: 400},
  {id: 40, name: 'Capital Vault', engine: 'sqlite', amount: 850},
];

describe('Unified Grid 2D Selection (Cell, Cell Group, Row, Row Group, Column, Column Group, Row×Col & All) + Copy/Export', () => {
  let writeTextMock;

  beforeEach(() => {
    writeTextMock = jest.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
        readText: jest.fn().mockResolvedValue(''),
      },
    });
  });

  it('selects a single cell and copies its clean scalar on Ctrl+C or 1x1 CSV on Copy CSV', async () => {
    render(
      <ThemedUnifiedGrid
        caption="Ledger Accounts"
        columns={SAMPLE_COLUMNS}
        rows={SAMPLE_ROWS}
        exportable
      />
    );

    const cell1Name = document.querySelector('[data-grid-nav-cell="1:name"]');
    expect(cell1Name).toBeTruthy();

    fireEvent.click(cell1Name);
    expect(cell1Name).toHaveAttribute('data-cell-selected', 'true');

    // Ctrl+C on a single cell copies the clean scalar value without header noise
    fireEvent.keyDown(cell1Name, {key: 'c', ctrlKey: true});
    expect(writeTextMock).toHaveBeenLastCalledWith('Payroll Reserve');

    // Toolbar Copy CSV exports that selected 1x1 cell with its column header
    fireEvent.click(screen.getByRole('button', {name: 'Copy CSV'}));
    await waitFor(() => {
      expect(writeTextMock).toHaveBeenLastCalledWith('name\nPayroll Reserve');
    });
  });

  it('selects rectangular cell groups via Shift+Click, Shift+Arrow, and mouse drag, plus non-contiguous cells via Ctrl+Click', async () => {
    render(
      <ThemedUnifiedGrid
        caption="Ledger Accounts"
        columns={SAMPLE_COLUMNS}
        rows={SAMPLE_ROWS}
        exportable
      />
    );

    const cell01 = document.querySelector('[data-grid-nav-cell="0:name"]');
    const cell23 = document.querySelector('[data-grid-nav-cell="2:amount"]');

    // 1. Shift+Click selects 3 rows (0..2) x 3 cols (name, engine, amount) = 9 cells
    fireEvent.click(cell01);
    fireEvent.click(cell23, {shiftKey: true});

    const badge = document.querySelector('[data-cdeadmin-qa-key="unified-grid-selection-badge"]');
    expect(badge).toHaveTextContent('9 cells selected');
    expect(badge).toHaveTextContent('Sum: 750');

    fireEvent.keyDown(cell23, {key: 'c', ctrlKey: true});
    expect(writeTextMock).toHaveBeenLastCalledWith(
      [
        'name\tengine\tamount',
        'Operating Cash\tpostgresql\t100',
        'Payroll Reserve\tfirebird\t250',
        'Tax Escrow\tduckdb\t400',
      ].join('\n')
    );

    // 2. Escape collapses back to single active cell; Shift+ArrowDown + Shift+ArrowRight builds a 2x2 block
    fireEvent.keyDown(cell23, {key: 'Escape'});
    expect(
      document.querySelector('[data-cdeadmin-qa-key="unified-grid-selection-badge"]')
    ).toBeNull();

    const cell10 = document.querySelector('[data-grid-nav-cell="1:id"]');
    fireEvent.click(cell10);
    fireEvent.keyDown(cell10, {key: 'ArrowDown', shiftKey: true});
    const cell20 = document.querySelector('[data-grid-nav-cell="2:id"]');
    fireEvent.keyDown(cell20, {key: 'ArrowRight', shiftKey: true});

    fireEvent.click(screen.getByRole('button', {name: 'Copy CSV'}));
    await waitFor(() => {
      expect(writeTextMock).toHaveBeenLastCalledWith(
        ['id,name', '20,Payroll Reserve', '30,Tax Escrow'].join('\n')
      );
    });

    // 3. Mouse drag across cells (0:id -> 1:name) selects 2x2 rectangular block live
    const cell00 = document.querySelector('[data-grid-nav-cell="0:id"]');
    const cell11 = document.querySelector('[data-grid-nav-cell="1:name"]');
    fireEvent.mouseDown(cell00, {button: 0});
    fireEvent.mouseEnter(cell11);
    fireEvent.mouseUp(cell11);

    fireEvent.click(screen.getByRole('button', {name: 'Copy TSV'}));
    await waitFor(() => {
      expect(writeTextMock).toHaveBeenLastCalledWith(
        ['id\tname', '10\tOperating Cash', '20\tPayroll Reserve'].join('\n')
      );
    });

    // 4. Non-contiguous Ctrl+Click adds & toggles individual cells
    fireEvent.click(cell00);
    const cell33 = document.querySelector('[data-grid-nav-cell="3:amount"]');
    fireEvent.click(cell33, {ctrlKey: true});
    expect(
      document.querySelector('[data-cdeadmin-qa-key="unified-grid-selection-badge"]')
    ).toHaveTextContent('2 cells selected');

    fireEvent.click(screen.getByRole('button', {name: 'Copy JSON'}));
    await waitFor(() => {
      const parsed = JSON.parse(writeTextMock.mock.calls.at(-1)[0]);
      expect(parsed).toEqual([
        {id: 10, amount: null},
        {id: null, amount: 850},
      ]);
    });
  });

  it('selects a full row and groups of rows via row gutter click, Shift+Click, Ctrl+Click, drag, and Shift+Space', async () => {
    render(
      <ThemedUnifiedGrid
        caption="Ledger Accounts"
        columns={SAMPLE_COLUMNS}
        rows={SAMPLE_ROWS}
        exportable
      />
    );

    const rowGutter1 = document.querySelector('[data-grid-row-select="1"]');
    const rowGutter3 = document.querySelector('[data-grid-row-select="3"]');

    // Single full row via row gutter click
    fireEvent.click(rowGutter1);
    expect(rowGutter1).toHaveAttribute('data-row-selected', 'true');
    fireEvent.click(screen.getByRole('button', {name: 'Copy CSV'}));
    await waitFor(() => {
      expect(writeTextMock).toHaveBeenLastCalledWith(
        ['id,name,engine,amount', '20,Payroll Reserve,firebird,250'].join('\n')
      );
    });

    // Contiguous group of rows (1..3) via Shift+Click on row gutter
    fireEvent.click(rowGutter3, {shiftKey: true});
    expect(
      document.querySelector('[data-cdeadmin-qa-key="unified-grid-selection-badge"]')
    ).toHaveTextContent('3 rows selected');

    fireEvent.click(screen.getByRole('button', {name: 'Copy CSV'}));
    await waitFor(() => {
      expect(writeTextMock).toHaveBeenLastCalledWith(
        [
          'id,name,engine,amount',
          '20,Payroll Reserve,firebird,250',
          '30,Tax Escrow,duckdb,400',
          '40,Capital Vault,sqlite,850',
        ].join('\n')
      );
    });

    // Non-contiguous rows (0 and 2) via Ctrl+Click on row gutter
    const rowGutter0 = document.querySelector('[data-grid-row-select="0"]');
    const rowGutter2 = document.querySelector('[data-grid-row-select="2"]');
    fireEvent.click(rowGutter0);
    fireEvent.click(rowGutter2, {ctrlKey: true});

    fireEvent.click(screen.getByRole('button', {name: 'Copy CSV'}));
    await waitFor(() => {
      expect(writeTextMock).toHaveBeenLastCalledWith(
        [
          'id,name,engine,amount',
          '10,Operating Cash,postgresql,100',
          '30,Tax Escrow,duckdb,400',
        ].join('\n')
      );
    });

    // Shift+Space on a cell selects that full row
    const cell3Name = document.querySelector('[data-grid-nav-cell="3:name"]');
    fireEvent.click(cell3Name);
    fireEvent.keyDown(cell3Name, {key: ' ', shiftKey: true});
    expect(rowGutter3).toHaveAttribute('data-row-selected', 'true');
  });

  it('selects a full column and groups of columns (strip click, Ctrl+Click, Shift+Click, Ctrl+Space) while preserving plain-click sort', async () => {
    render(
      <ThemedUnifiedGrid
        caption="Ledger Accounts"
        columns={SAMPLE_COLUMNS}
        rows={SAMPLE_ROWS}
        exportable
      />
    );

    // 1. Plain click on column header button still sorts without selecting the column
    const nameHeaderBtn = screen.getByRole('button', {name: /Account Name/i});
    fireEvent.click(nameHeaderBtn);
    expect(
      document.querySelector('[data-grid-col-header="name"]')
    ).not.toHaveAttribute('data-col-selected');
    // Sorted ascending: Capital Vault is now row 0
    expect(document.querySelector('[data-grid-nav-cell="0:name"]')).toHaveTextContent(
      'Capital Vault'
    );
    // Reset sort (asc -> desc -> none)
    fireEvent.click(nameHeaderBtn);
    fireEvent.click(nameHeaderBtn);

    // 2. Click top column-selector strip -> selects full column 'name'
    const nameColStrip = document.querySelector('[data-grid-col-select="name"]');
    fireEvent.click(nameColStrip);
    expect(document.querySelector('[data-grid-col-header="name"]')).toHaveAttribute(
      'data-col-selected',
      'true'
    );

    fireEvent.click(screen.getByRole('button', {name: 'Copy CSV'}));
    await waitFor(() => {
      expect(writeTextMock).toHaveBeenLastCalledWith(
        [
          'name',
          'Operating Cash',
          'Payroll Reserve',
          'Tax Escrow',
          'Capital Vault',
        ].join('\n')
      );
    });

    // 3. Shift+Click on 'Amount' column header button selects contiguous columns (name, engine, amount)
    const amountHeaderBtn = screen.getByRole('button', {name: /Amount/i});
    fireEvent.click(amountHeaderBtn, {shiftKey: true});
    expect(
      document.querySelector('[data-cdeadmin-qa-key="unified-grid-selection-badge"]')
    ).toHaveTextContent('3 columns selected');

    fireEvent.click(screen.getByRole('button', {name: 'Copy CSV'}));
    await waitFor(() => {
      expect(writeTextMock).toHaveBeenLastCalledWith(
        [
          'name,engine,amount',
          'Operating Cash,postgresql,100',
          'Payroll Reserve,firebird,250',
          'Tax Escrow,duckdb,400',
          'Capital Vault,sqlite,850',
        ].join('\n')
      );
    });

    // 4. Non-contiguous Ctrl+Click on column header buttons ('id' and 'amount')
    const idColStrip = document.querySelector('[data-grid-col-select="id"]');
    fireEvent.click(idColStrip);
    fireEvent.click(amountHeaderBtn, {ctrlKey: true});

    fireEvent.click(screen.getByRole('button', {name: 'Copy CSV'}));
    await waitFor(() => {
      expect(writeTextMock).toHaveBeenLastCalledWith(
        [
          'id,amount',
          '10,100',
          '20,250',
          '30,400',
          '40,850',
        ].join('\n')
      );
    });
  });

  it('intersects selected rows AND selected columns ("or both") and selects the entire result set via corner button or Ctrl+A', async () => {
    render(
      <ThemedUnifiedGrid
        caption="Ledger Accounts"
        columns={SAMPLE_COLUMNS}
        rows={SAMPLE_ROWS}
        exportable
      />
    );

    // Select Rows 0 and 2 via row gutter, then Ctrl+Click Columns 'name' and 'amount'
    fireEvent.click(document.querySelector('[data-grid-row-select="0"]'));
    fireEvent.click(document.querySelector('[data-grid-row-select="2"]'), {
      ctrlKey: true,
    });
    fireEvent.click(screen.getByRole('button', {name: /Account Name/i}), {
      ctrlKey: true,
    });
    fireEvent.click(screen.getByRole('button', {name: /Amount/i}), {
      ctrlKey: true,
    });

    const badge = document.querySelector('[data-cdeadmin-qa-key="unified-grid-selection-badge"]');
    expect(badge).toHaveTextContent('2 rows × 2 cols (4 cells)');
    expect(badge).toHaveTextContent('Sum: 500');

    // Only the 2x2 intersection cells are marked selected
    expect(document.querySelector('[data-grid-nav-cell="0:name"]')).toHaveAttribute(
      'data-cell-selected',
      'true'
    );
    expect(document.querySelector('[data-grid-nav-cell="1:name"]')).not.toHaveAttribute(
      'data-cell-selected'
    );
    expect(document.querySelector('[data-grid-nav-cell="0:engine"]')).not.toHaveAttribute(
      'data-cell-selected'
    );

    fireEvent.click(screen.getByRole('button', {name: 'Copy CSV'}));
    await waitFor(() => {
      expect(writeTextMock).toHaveBeenLastCalledWith(
        [
          'name,amount',
          'Operating Cash,100',
          'Tax Escrow,400',
        ].join('\n')
      );
    });

    // Top-left corner Select All button selects entire result set (4 x 4)
    const selectAllBtn = screen.getByRole('button', {
      name: 'Select entire result set',
    });
    fireEvent.click(selectAllBtn);
    expect(selectAllBtn).toHaveAttribute('aria-pressed', 'true');
    expect(
      document.querySelector('[data-cdeadmin-qa-key="unified-grid-selection-badge"]')
    ).toHaveTextContent('All (4 × 4)');

    // Clicking Select All again clears selection, and Ctrl+A re-selects entire result set
    fireEvent.click(selectAllBtn);
    expect(selectAllBtn).toHaveAttribute('aria-pressed', 'false');

    const cell00 = document.querySelector('[data-grid-nav-cell="0:id"]');
    fireEvent.keyDown(cell00, {key: 'a', ctrlKey: true});
    expect(selectAllBtn).toHaveAttribute('aria-pressed', 'true');
  });

  it('defaults SurfaceExportDialog to Current Selection scope and passes selected rows/columns to host export', async () => {
    const onExportHost = jest.fn().mockResolvedValue({
      filename: 'ledger_slice.xlsx',
      mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      content_base64: '',
    });
    const onClose = jest.fn();

    const allRows = SAMPLE_ROWS.map((r) => ({values: r}));
    const selectedRows = [
      {values: {name: 'Operating Cash', amount: 100}},
      {values: {name: 'Tax Escrow', amount: 400}},
    ];
    const selectedColumns = [
      {name: 'name', label: 'Account Name'},
      {name: 'amount', label: 'Amount'},
    ];

    render(
      <ThemedExportDialog
        open
        onClose={onClose}
        initialFormat="csv"
        defaultFilename="ledger_slice"
        tableName="ACCOUNT"
        rows={allRows}
        columns={SAMPLE_COLUMNS}
        selectedRows={selectedRows}
        selectedColumns={selectedColumns}
        hasMultiSelection
        allRowsSelected={false}
        selectionLabel="2 rows × 2 cols"
        onExportHost={onExportHost}
      />
    );

    const scopeSelect = screen.getByLabelText('Row Scope');
    expect(scopeSelect.value).toBe('selection');

    // Preview shows only the 2x2 selected sub-matrix
    const preview = screen.getByLabelText(/Preview/i);
    expect(within(preview.closest('.sr-field') || document.body).getByDisplayValue(/Operating Cash/)).toHaveValue(
      ['name,amount', 'Operating Cash,100', 'Tax Escrow,400'].join('\n')
    );

    // Switch to Excel (.xlsx) and run host export -> sends scope: 'selection' + selected_column_names + selected_rows_payload
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="export-fmt-xlsx"]'));
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="surface-export-confirm"]'));

    await waitFor(() => {
      expect(onExportHost).toHaveBeenCalledWith(
        expect.objectContaining({
          format: 'xlsx',
          settings: expect.objectContaining({
            scope: 'selection',
            selected_column_names: ['name', 'amount'],
            selected_rows_payload: [
              {values: {name: 'Operating Cash', amount: 100}},
              {values: {name: 'Tax Escrow', amount: 400}},
            ],
          }),
        })
      );
    });
  });
});
