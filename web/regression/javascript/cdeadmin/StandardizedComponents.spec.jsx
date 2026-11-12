/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {act, fireEvent, render, screen} from '@testing-library/react';
import {
  QueryExecutionToolbarCluster,
  QueryStepStatusFooter,
  ScratchBranchedTree,
  ScratchDiffTable,
  ScratchFilterTable,
  ScratchRecordsTable,
  ScratchScrollArea,
  resolveQueryEngineCapabilities,
  sliceRowsForStep,
} from 'sources/cdeadmin_ui';

const DEEP_CATALOG_TREE = [
  {
    id: 'eng-pg',
    label: 'PostgreSQL',
    children: [
      {
        id: 'srv-prod',
        label: 'pg17-prod.internal:5432',
        children: [
          {
            id: 'db-commerce',
            label: 'commerce_prod',
            children: [
              {
                id: 'sch-billing',
                label: 'billing',
                children: [
                  {
                    id: 'coll-tables',
                    label: 'Tables',
                    count: 2,
                    children: [
                      {
                        id: 'tbl-invoices',
                        label: 'customer_invoices',
                        children: [
                          {
                            id: 'coll-cols',
                            label: 'Columns',
                            count: 2,
                            children: [
                              {id: 'col-id', label: 'invoice_id', secondaryLabel: 'uuid PK'},
                              {id: 'col-total', label: 'amount_cents', secondaryLabel: 'bigint'},
                            ],
                          },
                        ],
                      },
                    ],
                  },
                ],
              },
            ],
          },
        ],
      },
    ],
  },
];

describe('Standardized Phase 1 UI Kit', () => {
  it('renders 8-level ScratchBranchedTree with continuous stepped active trace and sticky ancestors', () => {
    const onSelect = jest.fn();
    const {container} = render(
      <ScratchBranchedTree
        label="Catalog navigator"
        items={DEEP_CATALOG_TREE}
        defaultExpandedIds={[
          'eng-pg', 'srv-prod', 'db-commerce', 'sch-billing',
          'coll-tables', 'tbl-invoices', 'coll-cols',
        ]}
        defaultSelectedId="col-total"
        onSelect={onSelect}
      />
    );

    const activeItem = screen.getByRole('treeitem', {name: /amount_cents/});
    expect(activeItem).toHaveAttribute('aria-level', '8');
    expect(activeItem).toHaveAttribute('aria-selected', 'true');

    // Continuous active trace SVG path and structural trunk paths both exist
    expect(container.querySelector('.sr-branched-path-structural')).toBeInTheDocument();
    const activePath = container.querySelector('.sr-branched-path-active');
    expect(activePath).toBeInTheDocument();
    expect(activePath.getAttribute('d')).toContain('Q');

    // Sticky ancestor breadcrumb bar exposes clickable ancestor path
    const stickyNav = screen.getByLabelText('Selected ancestor path');
    expect(stickyNav).toHaveTextContent('PostgreSQL');
    expect(stickyNav).toHaveTextContent('customer_invoices');
    fireEvent.click(screen.getByRole('button', {name: 'commerce_prod'}));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({id: 'db-commerce'}), expect.anything());
  });

  it('cascades checkable selections across parent and child nodes in ScratchBranchedTree', () => {
    const onCheckedChange = jest.fn();
    render(
      <ScratchBranchedTree
        items={[
          {
            id: 'schema-public',
            label: 'public',
            defaultExpanded: true,
            children: [
              {id: 'tbl-orders', label: 'orders'},
              {id: 'tbl-users', label: 'users'},
            ],
          },
        ]}
        checkable
        checkedIds={['tbl-orders']}
        onCheckedChange={onCheckedChange}
      />
    );

    // Parent checkbox is mixed when one child is selected; clicking checks entire subtree
    fireEvent.click(screen.getByRole('checkbox', {name: 'Select public'}));
    expect(onCheckedChange).toHaveBeenCalledWith(
      expect.arrayContaining(['schema-public', 'tbl-orders', 'tbl-users']),
      expect.objectContaining({id: 'schema-public'}),
      true
    );
  });

  it('mounts @base-ui/react ScrollArea with bidirectional X and Y scrollbars', async () => {
    let container;
    await act(async () => {
      const rendered = render(
        <ScratchScrollArea label="Tree scroll" orientation="both" forceBaseScrollArea>
          <div style={{width: 900, height: 900}}>Deep wide content</div>
        </ScratchScrollArea>
      );
      container = rendered.container;
      await new Promise((resolve) => setTimeout(resolve, 25));
    });
    expect(screen.getByRole('region', {name: 'Tree scroll'})).toHaveTextContent('Deep wide content');
    expect(container.querySelector('.sr-scroll-viewport')).toBeInTheDocument();
  });

  it('sorts, filters, selects, and inspects rows in Beautiful UI tables', () => {
    const onInspectRow = jest.fn();
    render(
      <ScratchFilterTable
        caption="Catalog tables"
        columns={[
          {key: 'name', header: 'Table', mono: true},
          {key: 'engine', header: 'Engine'},
          {key: 'rows', header: 'Rows', numeric: true},
        ]}
        rows={[
          {id: 't1', name: 'orders', engine: 'PostgreSQL', rows: 1200},
          {id: 't2', name: 'events', engine: 'DuckDB', rows: 95000},
        ]}
        facets={[{id: 'engine', label: 'Engine', column: 'engine'}]}
        selectable
        onInspectRow={onInspectRow}
      />
    );

    expect(screen.getByText('orders')).toBeInTheDocument();
    expect(screen.getByText('events')).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('Filter rows…'), {target: {value: 'DuckDB'}});
    expect(screen.queryByText('orders')).not.toBeInTheDocument();
    expect(screen.getByText('events')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Inspect row t2 in right drawer'}));
    expect(onInspectRow).toHaveBeenCalledWith(expect.objectContaining({id: 't2'}), 't2');
  });

  it('renders semantic diffs and toggles carry switches in ScratchDiffTable', () => {
    const onToggleInclude = jest.fn();
    render(
      <ScratchDiffTable
        items={[
          {id: 'd1', delta: 'add', name: 'billing.ledger', kind: 'table', after: 'CREATE TABLE billing.ledger'},
          {id: 'd2', delta: 'modify', name: 'billing.invoices.amount', kind: 'column', before: 'integer', after: 'bigint'},
          {id: 'd3', delta: 'drop', name: 'billing.legacy_tmp', kind: 'table', destructive: true},
        ]}
        includedIds={['d1', 'd2']}
        onToggleInclude={onToggleInclude}
      />
    );

    expect(screen.getByText('ADDED')).toBeInTheDocument();
    expect(screen.getByText('MODIFIED')).toBeInTheDocument();
    expect(screen.getByText('DROPPED')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('switch', {name: 'Carry billing.legacy_tmp'}));
    expect(onToggleInclude).toHaveBeenCalledWith('d3', true, expect.objectContaining({id: 'd3'}));
  });

  it('enforces Max Rows, Rows per Step, and engine-gated Pause/Cancel in QueryExecutionController', () => {
    const rows = Array.from({length: 620}, (_, idx) => ({id: idx + 1}));
    const step1 = sliceRowsForStep(rows, {maxRows: 500, rowsPerStep: 200, stepsCompleted: 1});
    expect(step1.visibleCount).toBe(200);
    expect(step1.cappedTotal).toBe(500);
    expect(step1.hasMoreSteps).toBe(true);
    expect(step1.truncatedByMaxRows).toBe(true);

    const pgCaps = resolveQueryEngineCapabilities('postgresql');
    const redisCaps = resolveQueryEngineCapabilities('redis');
    expect(pgCaps.supportsCancel).toBe(true);
    expect(redisCaps.supportsCancel).toBe(false);

    const onFetchNext = jest.fn();
    const {rerender} = render(
      <>
        <QueryExecutionToolbarCluster
          status="running"
          maxRows={500}
          rowsPerStep={200}
          capabilities={pgCaps}
        />
        <QueryStepStatusFooter
          visibleCount={200}
          totalAvailable={620}
          rowsPerStep={200}
          maxRows={500}
          hasMoreSteps
          truncatedByMaxRows
          capabilities={pgCaps}
          onFetchNextStep={onFetchNext}
        />
      </>
    );

    expect(screen.getByRole('button', {name: 'Cancel query'})).not.toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: /Next 200 rows/}));
    expect(onFetchNext).toHaveBeenCalledTimes(1);

    rerender(
      <QueryExecutionToolbarCluster
        status="running"
        maxRows={500}
        rowsPerStep={200}
        capabilities={redisCaps}
      />
    );
    expect(screen.getByRole('button', {name: 'Cancel query'})).toBeDisabled();
  });
});
