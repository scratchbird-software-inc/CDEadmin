/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useState} from 'react';
import {fireEvent, render, screen, within} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import UnifiedDataGrid from 'sources/cdeadmin_ui/data/UnifiedDataGrid';
import {DiffDataGrid, normalizeDiffKind} from 'sources/cdeadmin_ui/data/DiffDataGrid';
import {safeSpreadsheetValue, serializeGridData} from 'sources/cdeadmin_ui/data/gridIO';
import {formatRowsForExport} from 'sources/cdeadmin_ui/surfaces/dataEditSurfaceHelpers';
import RecordGrid, {gridColumns} from 'sources/cdeadmin_ui/objects/RecordGrid';
import ContractForm from 'sources/cdeadmin_ui/foundations/ContractForm';
import discoverySynonymsForm from 'sources/cdeadmin_ui/specifications/ai_discovery_zero_grey/machine/forms/discovery_synonyms.form.json';

const ThemedUnifiedGrid = withTheme(UnifiedDataGrid);
const ThemedDiffGrid = withTheme(DiffDataGrid);
const ThemedRecordGrid = withTheme(RecordGrid);
const ThemedContractForm = withTheme(ContractForm);

describe('Standardized Application Grid, Editable RecordGrid, ContractForm & Diff Mode Parity', () => {
  it('switches UnifiedDataGrid cleanly between Grid, Mini-Forms, Hybrid Grid, and Full-Form modes and sorts/filters rows', () => {
    const columns = [
      {name: 'id', label: 'ID', native_type: 'integer', key: true},
      {name: 'name', label: 'Table Name', native_type: 'varchar'},
      {name: 'engine', label: 'Engine', native_type: 'varchar'},
      {name: 'definition', label: 'SQL Definition', native_type: 'text'},
    ];
    const rows = [
      {id: 1, name: 'orders', engine: 'postgresql', definition: 'CREATE TABLE orders (id INT);'},
      {id: 2, name: 'accounts', engine: 'firebird', definition: 'CREATE TABLE accounts (id INT);'},
    ];

    render(
      <ThemedUnifiedGrid
        caption="Catalog tables"
        columns={columns}
        rows={rows}
        searchable
        facets={[{id: 'engine', column: 'engine', label: 'Engine'}]}
        exportable
      />
    );

    expect(screen.getByRole('grid', {name: 'Catalog tables'})).toBeInTheDocument();

    // Sort by Table Name ascending -> accounts first
    fireEvent.click(screen.getByRole('button', {name: /Table Name/i}));
    const gridRows = screen.getAllByRole('row');
    expect(gridRows[1]).toHaveTextContent('accounts');

    // Switch to Mini-Forms mode
    fireEvent.click(screen.getByRole('button', {name: 'Mini-Forms'}));
    expect(screen.getAllByText('SQL Definition').length).toBeGreaterThanOrEqual(2);

    // Switch to Hybrid Grid mode
    fireEvent.click(screen.getByRole('button', {name: 'Hybrid Grid'}));
    expect(screen.getByRole('grid', {name: 'Catalog tables'})).toBeInTheDocument();

    // Switch to Full-Form mode and check record indicator
    fireEvent.click(screen.getByRole('button', {name: 'Full-Form'}));
    expect(screen.getByText(/Row 1 of 2/i)).toBeInTheDocument();
  });

  it('neutralizes spreadsheet formula-injection prefixes across both gridIO and formatRowsForExport', () => {
    expect(safeSpreadsheetValue('=CMD|\' /C calc\'!A0')).toBe('\'=CMD|\' /C calc\'!A0');
    expect(safeSpreadsheetValue('+SUM(A1:A2)')).toBe('\'+SUM(A1:A2)');
    expect(safeSpreadsheetValue(-10)).toBe(-10);
    expect(safeSpreadsheetValue('-10')).toBe('\'-10');
    expect(safeSpreadsheetValue('-BAD()')).toBe('\'-BAD()');
    expect(safeSpreadsheetValue('@IMPORTXML()')).toBe('\'@IMPORTXML()');

    const cols = [{name: 'formula', label: 'Formula'}];
    const csv = serializeGridData(
      [{key: 'formula', label: 'Formula'}],
      [{formula: '=HYPERLINK("http://evil")'}],
      'csv'
    );
    expect(csv).toContain('\'=HYPERLINK');

    const surfaceCsv = formatRowsForExport(
      [{values: {formula: '=HYPERLINK("http://evil")'}}],
      cols,
      'csv'
    );
    expect(surfaceCsv).toContain('\'=HYPERLINK');
  });

  it('supports RecordGrid [Grid | Hybrid | Mini | Form] modes, 1-col string items, and mode-aware inline columns', () => {
    // 1. Mode-aware inline columns: alter-only / readonly columns do not push primary editable columns out of create mode
    const eightCols = [
      {field_id: 'attnum', label: 'Pos', control: 'number', modes: ['alter'], readonly: true},
      {field_id: 'oid', label: 'OID', control: 'text', readonly: true},
      {field_id: 'name', label: 'Column Name', control: 'text', required: true},
      {field_id: 'type', label: 'Data Type', control: 'text', required: true},
      {field_id: 'length', label: 'Length', control: 'number'},
      {field_id: 'scale', label: 'Scale', control: 'number'},
      {field_id: 'nullable', label: 'Nullable', control: 'boolean'},
      {field_id: 'default_val', label: 'Default', control: 'text'},
    ];
    const createLayout = gridColumns(eightCols, [{}], {}, 'create');
    expect(createLayout.inline.map((c) => c.field_id)).toEqual([
      'name',
      'type',
      'length',
      'scale',
      'nullable',
      'default_val',
    ]);

    // 2. 1-column item_kind: "string" support + multi-column mode switching
    function GridsHarness() {
      const [items, setItems] = useState(['alpha', 'beta']);
      const [cols, setCols] = useState([
        {name: 'id', type: 'integer'},
        {name: 'email', type: 'varchar'},
      ]);
      return (
        <>
          <ThemedRecordGrid
            field={{
              field_id: 'tags',
              label: 'Search Tags',
              control: 'grid',
              item_kind: 'string',
            }}
            rows={items}
            onChange={setItems}
          />
          <ThemedRecordGrid
            field={{
              field_id: 'columns',
              label: 'Table Columns',
              control: 'grid',
              columns: [
                {field_id: 'name', label: 'Col Name', control: 'text'},
                {field_id: 'type', label: 'Col Type', control: 'text'},
              ],
            }}
            rows={cols}
            onChange={setCols}
          />
        </>
      );
    }

    render(<GridsHarness />);
    const firstInput = screen.getByLabelText('Search Tags (row 1)');
    expect(firstInput).toHaveValue('alpha');
    fireEvent.change(firstInput, {target: {value: 'alpha_updated'}});
    expect(screen.getByLabelText('Search Tags (row 1)')).toHaveValue('alpha_updated');

    // Switch multi-column RecordGrid to Full-form view
    fireEvent.click(screen.getByRole('button', {name: 'Full-form view'}));
    expect(screen.getByText(/Record 1 of 2/i)).toBeInTheDocument();
  });

  it('renders ContractForm DataGrid controls as editable RecordGrids when not readonly', () => {
    render(
      <ThemedContractForm
        form={discoverySynonymsForm}
        initialValues={{
          entries: [{canonical_term: 'revenue', synonyms: 'sales, turnover'}],
        }}
      />
    );
    const canonicalInput = screen.getByLabelText(/Canonical term \(row 1\)/);
    expect(canonicalInput).toHaveValue('revenue');
    fireEvent.change(canonicalInput, {target: {value: 'gross_revenue'}});
    expect(screen.getByLabelText(/Canonical term \(row 1\)/)).toHaveValue('gross_revenue');
  });

  it('normalizes diff deltas, filters by delta chip/search, sorts, and toggles Carry switches in DiffDataGrid', () => {
    expect(normalizeDiffKind('drop_column')).toBe('drop');
    expect(normalizeDiffKind('add_table')).toBe('add');
    expect(normalizeDiffKind('rename_table')).toBe('modify');

    const onToggle = jest.fn();
    render(
      <ThemedDiffGrid
        title="Schema Diff"
        searchable
        filterable
        exportable
        includedIds={['d1', 'd2']}
        onToggleInclude={onToggle}
        items={[
          {id: 'd1', name: 'public.orders', kind: 'table', delta: 'add', after: 'CREATE TABLE orders'},
          {
            id: 'd2',
            name: 'public.legacy_tmp',
            kind: 'table',
            delta: 'drop_table',
            destructive: true,
            before: 'TABLE legacy_tmp',
          },
        ]}
      />
    );

    const table = screen.getByRole('table', {name: 'Schema Diff'});
    expect(within(table).getByText('ADDED')).toBeInTheDocument();
    expect(within(table).getByText('DROPPED')).toBeInTheDocument();
    expect(within(table).getByText('destructive')).toBeInTheDocument();

    // Filter to DROPPED only
    fireEvent.click(screen.getByRole('button', {name: /DROPPED/i}));
    expect(within(table).queryByText('public.orders')).not.toBeInTheDocument();
    expect(within(table).getByText('public.legacy_tmp')).toBeInTheDocument();

    // Toggle Carry switch
    fireEvent.click(screen.getByRole('switch', {name: 'Carry public.legacy_tmp'}));
    expect(onToggle).toHaveBeenCalledWith('d2', false, expect.objectContaining({id: 'd2'}));
  });
});
