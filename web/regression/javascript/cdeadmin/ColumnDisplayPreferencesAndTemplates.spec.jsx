/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import UnifiedDataGrid from '../../../pgadmin/static/js/cdeadmin_ui/data/UnifiedDataGrid';
import ColumnDisplaySettingsDialog from '../../../pgadmin/static/js/cdeadmin_ui/surfaces/ColumnDisplaySettingsDialog';
import {defaultLayoutState} from '../../../pgadmin/static/js/cdeadmin_ui/surfaces/RecordForm';

const COLUMNS = [
  {name: 'id', label: 'ID', native_type: 'INTEGER', key: true},
  {name: 'notes', label: 'NOTES', native_type: 'TEXT'},
  {name: 'amount', label: 'AMOUNT', native_type: 'NUMERIC(12,2)'},
];

const ROWS = [
  {
    id: 1,
    notes: 'Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6',
    amount: 1250.5,
  },
  {
    id: 2,
    notes: 'Second row note entry',
    amount: 42.0,
  },
];

describe('Per-Column Display Preferences & Templates', () => {
  it('applies font, colour, alignment, wrap, max-displayed-lines-in-wrap, and min/max width bounds including drag-resize clamping', async () => {
    const {container} = render(
      <UnifiedDataGrid
        columns={COLUMNS}
        rows={ROWS}
        caption="CUSTOMERS_VIEW"
        allowModeSwitch
      />
    );

    // Right-click a cell in the `notes` column to open Column Display Settings
    const notesCell = container.querySelector('[data-grid-nav-cell="0:notes"]');
    expect(notesCell).not.toBeNull();
    fireEvent.contextMenu(notesCell, {clientX: 120, clientY: 140});

    const menuBtn = await screen.findByText('Column Display Settings…');
    fireEvent.click(menuBtn);

    expect(
      await screen.findByText(/Column Display Settings — notes/i)
    ).toBeInTheDocument();

    // Configure all 7 column properties:
    fireEvent.change(screen.getByLabelText('Font Family'), {
      target: {value: 'serif'},
    });
    fireEvent.change(screen.getByLabelText('Font Size'), {
      target: {value: 'lg'},
    });
    fireEvent.change(screen.getByLabelText('Text Colour'), {
      target: {value: '#1d4ed8'},
    });
    fireEvent.change(screen.getByLabelText('Cell Background Colour'), {
      target: {value: '#eff6ff'},
    });
    fireEvent.change(screen.getByLabelText('Horizontal Alignment'), {
      target: {value: 'center'},
    });
    fireEvent.change(screen.getByLabelText('Vertical Alignment'), {
      target: {value: 'top'},
    });
    fireEvent.change(screen.getByLabelText('Text Wrap'), {
      target: {value: 'clamp'},
    });
    fireEvent.change(screen.getByLabelText('Max Displayed Lines in Wrap'), {
      target: {value: '5'},
    });
    fireEvent.change(screen.getByLabelText('Minimum Width (px)'), {
      target: {value: '190'},
    });
    fireEvent.change(screen.getByLabelText('Maximum Width (px)'), {
      target: {value: '260'},
    });

    fireEvent.click(screen.getByRole('button', {name: 'Apply'}));

    await waitFor(() => {
      const header = container.querySelector('[data-grid-col-header="notes"]');
      expect(header).toHaveAttribute('data-col-min-width', '190');
      expect(header).toHaveAttribute('data-col-max-width', '260');
      // Default 156px width is automatically clamped up to minWidth=190px!
      expect(header.style.width).toBe('190px');
    });

    const updatedCell = container.querySelector('[data-grid-nav-cell="0:notes"]');
    const row1NotesCell = container.querySelector('[data-grid-nav-cell="1:notes"]');
    expect(updatedCell.style.fontFamily).toContain('Georgia');
    expect(updatedCell.style.textAlign).toBe('center');
    expect(updatedCell.style.alignItems).toBe('flex-start'); // vAlign === 'top'
    expect(row1NotesCell.style.background).toBe('rgb(239, 246, 255)'); // #eff6ff on non-active cell

    const textSpan = updatedCell.querySelector('[data-col-wrap-mode="clamp"]');
    expect(textSpan).not.toBeNull();
    expect(textSpan).toHaveAttribute('data-col-max-lines', '5');
    expect(textSpan.style.color).toBe('rgb(29, 78, 216)'); // #1d4ed8
    expect(textSpan.style.fontSize).toBe('0.95rem');

    // Drag-resize separator beyond maxWidth (e.g. +300px) and below minWidth (e.g. -200px)
    const header = container.querySelector('[data-grid-col-header="notes"]');
    const resizeHandle = header.querySelector('[role="separator"]');
    fireEvent.mouseDown(resizeHandle, {clientX: 200});
    fireEvent.mouseMove(window, {clientX: 500});
    fireEvent.mouseUp(window);
    expect(header.style.width).toBe('260px'); // strictly capped at maxWidth=260px!

    fireEvent.mouseDown(resizeHandle, {clientX: 260});
    fireEvent.mouseMove(window, {clientX: 20});
    fireEvent.mouseUp(window);
    expect(header.style.width).toBe('190px'); // strictly floored at minWidth=190px!
  });

  it('persists table/view preferences to UserConfigurationDatabase and saves/applies templates', async () => {
    const onApplyLayout = jest.fn();
    const onSaveObjectLayout = jest.fn().mockResolvedValue({saved: 'specific'});
    const onSaveTemplate = jest.fn().mockResolvedValue({saved: 'template'});
    const onClose = jest.fn();

    const templates = [
      {
        template_id: 'tpl-finance',
        name: 'Finance Accounting Template',
        layout: {
          gridColPrefs: {
            amount: {
              font: 'mono',
              color: '#047857',
              hAlign: 'right',
              minWidth: 120,
              maxWidth: 240,
            },
          },
        },
      },
    ];

    render(
      <ColumnDisplaySettingsDialog
        open
        columns={COLUMNS}
        initialColumnName="amount"
        layout={defaultLayoutState()}
        objectLabel="public.invoices"
        canPersistObjectLayout
        templates={templates}
        onClose={onClose}
        onApplyLayout={onApplyLayout}
        onSaveObjectLayout={onSaveObjectLayout}
        onSaveTemplate={onSaveTemplate}
      />
    );

    // Apply existing template first
    fireEvent.change(screen.getByLabelText('Apply saved template'), {
      target: {value: 'tpl-finance'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Apply Template'}));
    expect(onApplyLayout).toHaveBeenCalledWith(
      expect.objectContaining({
        gridColPrefs: expect.objectContaining({
          amount: expect.objectContaining({
            font: 'mono',
            color: '#047857',
            hAlign: 'right',
            minWidth: 120,
            maxWidth: 240,
          }),
        }),
      })
    );

    // Save customized settings as a new template
    fireEvent.change(screen.getByLabelText('Max Displayed Lines in Wrap'), {
      target: {value: '4'},
    });
    fireEvent.change(
      screen.getByLabelText('Save preferences as template name'),
      {target: {value: 'Executive Summary Template'}}
    );
    fireEvent.click(screen.getByRole('button', {name: 'Save as Template'}));
    await waitFor(() =>
      expect(onSaveTemplate).toHaveBeenCalledWith(
        'Executive Summary Template',
        expect.any(Object)
      )
    );

    // Click Apply & Save Preferences to persist to UserConfigurationDatabase for public.invoices
    fireEvent.click(
      screen.getByRole('button', {name: 'Apply & Save Preferences'})
    );
    await waitFor(() =>
      expect(onSaveObjectLayout).toHaveBeenCalledWith(
        expect.objectContaining({
          gridColPrefs: expect.objectContaining({
            amount: expect.objectContaining({
              font: 'mono',
              color: '#047857',
              hAlign: 'right',
              minWidth: 120,
              maxWidth: 240,
            }),
          }),
        })
      )
    );
    expect(onClose).toHaveBeenCalled();
  });
});
