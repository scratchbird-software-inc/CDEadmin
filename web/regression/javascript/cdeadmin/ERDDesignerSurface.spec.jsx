/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import {libraries, setupDDNDOM} from './ddnTestRuntime';
import {
  ERDDesignerSurface,
  ERDModelsNavigator,
  erdModuleDefinition,
  resetDDNLibraryLoaderForTests,
  setDDNLibraryLoaderForTests,
} from 'sources/cdeadmin_ui/integrations/ddn';

const SAMPLE_DDN = [
  'version ddn-next-1',
  '// ScratchRobin mapping: scratchrobin.erd.model',
  '',
  'view "erd_all_levels" as "ddn@1"',
  '    with',
  '        id "erd_all_levels"',
  '        title "Billing ERD"',
  '        selection',
  '            include empty list',
  '',
].join('\n');

function makeSession({suspect = true} = {}) {
  return {
    design: {
      id: '019a0000-0000-7000-8000-000000000010',
      project_id: 'models',
      key: 'billing-erd',
      kind: 'erd',
      title: 'Billing ERD',
      head_version: 2,
      active_version: 1,
      version: {
        version: 2,
        status: 'draft',
        ddn_text: SAMPLE_DDN,
      },
      bindings: suspect
        ? [
            {
              id: '019a0000-0000-7000-8000-000000000099',
              state: 'suspect',
              target_ref: 'sqlite:table:main.customers',
            },
          ]
        : [],
    },
    workspace: {
      format: 'ddn-source-workspace@1',
      entry: 'billing-erd.ddn',
      view: 'erd_all_levels',
      files: {'billing-erd.ddn': SAMPLE_DDN},
    },
    layout: {
      algorithm: 'scratchrobin-server-layered@1',
      nodes: [{id: 'node-1', name: 'accounts', x: 48, y: 48}],
      edges: [],
      tiles: [{tx: 0, ty: 0, tile_key: 'tile-0'}],
    },
    resolved_includes: [],
    binding_summary: {
      total: 1,
      valid: suspect ? 0 : 1,
      suspect: suspect ? 1 : 0,
      unknown: 0,
    },
  };
}

describe('Task-specific ERD and data modelling designer', () => {
  beforeEach(() => {
    setupDDNDOM();
    setDDNLibraryLoaderForTests(async () => libraries);
  });

  afterEach(() => {
    resetDDNLibraryLoaderForTests();
  });

  it('renders through the shared DDNViewerSurface, confirms suspect bindings and previews alter plans', async () => {
    let suspect = true;
    const mockClient = {
      openSession: jest.fn(async () => makeSession({suspect})),
      confirmBinding: jest.fn(async () => {
        suspect = false;
        return {state: 'valid'};
      }),
      previewErdAlterPlan: jest.fn(async (_proj, _id, opts) => {
        const allDiffs = [
          {
            difference_id: 'rename_table:t1',
            change_kind: 'rename_table',
            object_name: 'customers -> accounts',
            destructive: false,
            statement: 'ALTER TABLE "customers" RENAME TO "accounts";',
          },
          {
            difference_id: 'drop_column:c1',
            change_kind: 'drop_column',
            object_name: 'accounts.legacy_code',
            destructive: true,
            statement: 'ALTER TABLE "accounts" DROP COLUMN "legacy_code";',
          },
        ];
        const selected = opts?.selectedDifferenceIds ?? [
          'rename_table:t1',
          'drop_column:c1',
        ];
        const chosen = allDiffs.filter((d) =>
          selected.includes(d.difference_id)
        );
        return {
          differences: allDiffs,
          selected_difference_ids: selected,
          script: chosen.map((d) => d.statement).join('\n'),
          has_destructive_changes: chosen.some((d) => d.destructive),
          requires_native_review: true,
          applied_immediately: false,
          destructive_warning:
            'Metadata changes may lose data and are not reversible.',
        };
      }),
      computeErdDrift: jest.fn(async () => ({
        has_drift: true,
        matched: [],
        missing_in_live: [],
        property_drift: [{element_id: 'node-1', name: 'db-primary'}],
      })),
      proposeErdDiagramChange: jest.fn(async () => ({
        proposal_id: 'prop-01',
        requires_native_review: true,
        applied_immediately: false,
      })),
    };

    const Surface = withTheme(ERDDesignerSurface);
    const {container} = render(
      <Surface
        projectId="models"
        designId="019a0000-0000-7000-8000-000000000010"
        client={mockClient}
      />
    );

    // Confirm shared DDNViewerSurface is mounted inside ERDDesignerSurface
    expect(await screen.findByTestId('erd-suspect-bindings')).toBeInTheDocument();
    await waitFor(() =>
      expect(
        container.querySelector('[data-cde-surface="diagram.ddn.viewer"]')
      ).not.toBeNull()
    );

    // Confirm suspect binding (A5/A6)
    fireEvent.click(
      screen.getByRole('button', {
        name: 'Confirm sqlite:table:main.customers',
      })
    );
    await waitFor(() =>
      expect(mockClient.confirmBinding).toHaveBeenCalledWith(
        'models',
        '019a0000-0000-7000-8000-000000000010',
        '019a0000-0000-7000-8000-000000000099',
        {newTargetRef: null}
      )
    );
    await waitFor(() =>
      expect(
        screen.queryByTestId('erd-suspect-bindings')
      ).not.toBeInTheDocument()
    );

    // Open Alter Plan preview dialog and verify destructive warning + subset selection
    fireEvent.click(
      screen.getByRole('button', {name: 'Preview alter plan…'})
    );
    const alterDialog = await screen.findByRole('dialog', {
      name: 'Preview ERD alter plan',
    });
    expect(
      await within(alterDialog).findByTestId('erd-destructive-warning')
    ).toHaveTextContent('not reversible');
    const dropBox = within(alterDialog).getByRole('checkbox', {
      name: /drop_column: accounts\.legacy_code/,
    });
    expect(dropBox).toBeChecked();
    fireEvent.click(dropBox);
    await waitFor(() =>
      expect(mockClient.previewErdAlterPlan).toHaveBeenLastCalledWith(
        'models',
        '019a0000-0000-7000-8000-000000000010',
        expect.objectContaining({
          selectedDifferenceIds: ['rename_table:t1'],
        })
      )
    );
    fireEvent.click(within(alterDialog).getByRole('button', {name: 'Close'}));
    await waitFor(() =>
      expect(
        screen.queryByRole('dialog', {name: 'Preview ERD alter plan'})
      ).not.toBeInTheDocument()
    );

    // Open System Drift & submit diagram change proposal for native review (D1)
    fireEvent.click(screen.getByRole('button', {name: 'System drift…'}));
    const driftDialog = await screen.findByRole('dialog', {
      name: 'System diagram drift and change review',
    });
    fireEvent.click(
      within(driftDialog).getByRole('button', {name: 'Request native review'})
    );
    expect(
      await within(driftDialog).findByTestId('erd-change-proposal')
    ).toHaveTextContent('applied immediately: false');
  });

  it('launches New Data Model (ERD) from Tools menu command and creates an ERD model', async () => {
    const def = erdModuleDefinition();
    const newCmd = def.contributions.commands.find(
      (c) => c.id === 'erd.designer.new'
    );
    expect(newCmd.surfaces).toContain('tools');
    const showActivity = jest.fn();
    newCmd.execute({}, {showActivity});
    expect(showActivity).toHaveBeenCalledWith('activity.erd_models');

    const projectClient = {
      listProjects: jest.fn(async () => [
        {project_id: 'models', name: 'Models', access: 'owner'},
      ]),
      createProject: jest.fn(),
    };
    const createdDesign = {
      id: '019a0000-0000-7000-8000-000000000055',
      title: 'Warehouse Model',
      head_version: 1,
    };
    const models = [];
    const designClient = {
      listDesigns: jest.fn(async () => [...models]),
      createErdDesign: jest.fn(async (_projId, payload) => {
        models.push({...createdDesign, title: payload.title});
        return {...createdDesign, title: payload.title};
      }),
    };
    const onOpenModel = jest.fn();

    const Nav = withTheme(ERDModelsNavigator);
    render(
      <Nav
        projectClient={projectClient}
        designClient={designClient}
        onOpenModel={onOpenModel}
      />
    );

    const dialog = await screen.findByRole('dialog', {
      name: 'New data model (ERD)',
    });
    fireEvent.change(within(dialog).getByLabelText(/Model title/), {
      target: {value: 'Warehouse Model'},
    });
    fireEvent.change(
      within(dialog).getByLabelText(/Initial entity or table name/),
      {target: {value: 'Shipment'}}
    );
    fireEvent.click(
      within(dialog).getByRole('button', {name: 'Create data model'})
    );

    await waitFor(() => expect(onOpenModel).toHaveBeenCalledTimes(1));
    expect(designClient.createErdDesign).toHaveBeenCalledWith(
      'models',
      expect.objectContaining({
        title: 'Warehouse Model',
        conceptualEntities: [{name: 'Shipment'}],
      })
    );
    expect(onOpenModel).toHaveBeenCalledWith(
      'models',
      expect.objectContaining({
        id: '019a0000-0000-7000-8000-000000000055',
        title: 'Warehouse Model',
      })
    );
  });
});
