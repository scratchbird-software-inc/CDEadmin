/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import React from 'react';
import {ProjectAssetClient} from '../../projects/ProjectAssetClient';
import {PROJECT_ASSET_SERVICE_ID} from './module';
import {DesignStoreClient} from './sharedDesignLibrary';
import {ERDDesignerSurface} from './ERDDesignerSurface';
import {
  ERDModelsNavigator,
  requestERDModelCreate,
} from './ERDModelsNavigator';

export const ERD_MODULE_ID = 'cdeadmin.erd';
export const DESIGN_STORE_SERVICE_ID = 'design.store';
export const ERD_DESIGN_ASSET_TYPE = 'cdeadmin.design.erd';

function toolbarActionCommand(id, label, description, iconKey) {
  return {
    // Open-design actions belong on the open designer toolbar, never on the
    // Tools menu (owner direction 2026-11-08, docs/en_US/menu_bar.rst).
    id,
    label,
    description,
    iconKey,
    surfaces: ['toolbar'],
    macroCallable: false,
    enabledWhen: (context) => context.enabled !== false,
    execute: (_args, context) => {
      if (typeof context.invoke !== 'function') {
        throw new Error(
          `Command ${id} requires an active ERD designer surface.`
        );
      }
      return context.invoke();
    },
  };
}

function surfaceCommandExecutor(context) {
  return (id, commandContext) => {
    if (!context.commands?.execute) {
      return commandContext.invoke?.();
    }
    return context.commands.execute(id, {}, commandContext);
  };
}

function validateDesignArguments(args) {
  return args &&
    typeof args.projectId === 'string' &&
    typeof args.designId === 'string'
    ? true
    : 'A projectId and designId are required.';
}

export function erdModuleDefinition() {
  return {
    id: ERD_MODULE_ID,
    version: '1.0.0',
    title: 'Data Model (ERD) Designer',
    iconKey: 'tool.erd',
    serviceRequirements: [PROJECT_ASSET_SERVICE_ID, DESIGN_STORE_SERVICE_ID],
    contributions: {
      surfaces: [
        {
          id: 'diagram.erd.designer',
          title: 'Data Model (ERD) Designer',
          iconKey: 'tool.erd',
          assetTypes: [ERD_DESIGN_ASSET_TYPE],
          readOnly: false,
          editable: true,
          detachable: true,
          duplicable: false,
          fullscreen: true,
          restore: async (descriptor, context) => {
            const client =
              context.services?.[DESIGN_STORE_SERVICE_ID] ??
              context.designStoreClient ??
              new DesignStoreClient();
            return React.createElement(ERDDesignerSurface, {
              projectId: descriptor.projectId,
              designId: descriptor.restoreRef,
              client,
              readOnly: context.readOnly === true,
              executeCommand: surfaceCommandExecutor(context),
              onStateChange: (state) =>
                context.setSurfaceState?.({
                  erdDesignState: state,
                  persistence: state.status ?? 'draft',
                }),
              onExport: context.onExport,
              onError: context.onError,
            });
          },
        },
      ],
      commands: [
        {
          id: 'erd.designer.new',
          label: 'New Data Model (ERD)…',
          description:
            'Create a data model (conceptual whiteboard, logical or physical ERD) in the design store.',
          iconKey: 'tool.erd',
          surfaces: ['tools', 'project'],
          permission: ['project.asset.edit'],
          execute: (_args, context) => {
            context.showActivity?.('activity.erd_models');
            requestERDModelCreate();
          },
        },
        {
          id: 'erd.designer.show',
          label: 'Data Models (ERD)',
          description: 'List and open data models across your projects.',
          iconKey: 'tool.erd',
          surfaces: ['tools', 'view'],
          execute: (_args, context) => {
            if (typeof context.showActivity !== 'function') {
              throw new Error('Workbench activity authority is unavailable.');
            }
            return context.showActivity('activity.erd_models');
          },
        },
        {
          id: 'erd.designer.open',
          label: 'Open in ERD Designer',
          description: 'Open a versioned ERD design from the design store.',
          iconKey: 'tool.erd',
          surfaces: ['toolbar'],
          validateArguments: validateDesignArguments,
          execute: async (args, context) => {
            if (typeof context.openSurface !== 'function') {
              throw new Error(
                'Workbench surface opening authority is unavailable.'
              );
            }
            return context.openSurface('diagram.erd.designer', {
              toolInstanceId:
                args.toolInstanceId ??
                `diagram.erd.designer:${args.projectId}:${args.designId}`,
              restoreRef: args.designId,
              projectId: args.projectId,
              title: args.title,
            });
          },
        },
        toolbarActionCommand(
          'erd.designer.save',
          'Save ERD Checkpoint',
          'Save a directed save-point version of the active data model.',
          'action.save'
        ),
        toolbarActionCommand(
          'erd.designer.convert',
          'Convert ERD Engine',
          'Convert the active data model between engines via neutral logical types.',
          'tool.schema-compare'
        ),
        toolbarActionCommand(
          'erd.designer.alter_plan',
          'Preview ERD Alter Plan',
          'Compare ERD versions and preview the change plan for native review.',
          'tool.schema-compare'
        ),
        toolbarActionCommand(
          'erd.designer.accept',
          'Accept ERD Version',
          'Accept a save-point version with ScratchRobin and optional Git review policy.',
          'action.save'
        ),
      ],
      activity: [
        {
          id: 'activity.erd_models',
          label: 'Data Models (ERD)',
          iconKey: 'tool.erd',
          priority: 52,
          surfaceId: 'diagram.erd.designer',
          render: () => React.createElement(ERDModelsNavigator),
        },
      ],
      inspector: [
        {
          id: 'inspector.erd.bindings',
          label: 'ERD bindings',
          priority: 72,
          when: (context) => context.surfaceId === 'diagram.erd.designer',
          render: (context) => context.erdDesignState?.bindings ?? [],
        },
      ],
      status: [
        {
          id: 'status.erd.version',
          label: 'ERD version state',
          priority: 42,
          when: (context) => context.surfaceId === 'diagram.erd.designer',
          value: (context) =>
            context.erdDesignState?.loaded
              ? `v${context.erdDesignState.currentVersion} (${context.erdDesignState.status})`
              : 'loading',
        },
      ],
    },
  };
}

export function registerERDModule({modules, services, api} = {}) {
  if (!modules || !services) {
    throw new TypeError(
      'ERD designer registration requires module and service registries.'
    );
  }
  const removers = [];
  if (!services.has(PROJECT_ASSET_SERVICE_ID)) {
    removers.push(
      services.register({
        id: PROJECT_ASSET_SERVICE_ID,
        version: '1.0.0',
        factory: () => new ProjectAssetClient(api),
      })
    );
  }
  if (!services.has(DESIGN_STORE_SERVICE_ID)) {
    removers.push(
      services.register({
        id: DESIGN_STORE_SERVICE_ID,
        version: '1.0.0',
        factory: () => new DesignStoreClient(api),
      })
    );
  }
  const removeModule = modules.register(erdModuleDefinition());
  return () => {
    removeModule();
    removers.reverse().forEach((remove) => remove());
  };
}
