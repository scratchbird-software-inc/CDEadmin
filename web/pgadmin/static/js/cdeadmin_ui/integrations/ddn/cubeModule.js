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
import {DESIGN_STORE_SERVICE_ID} from './erdModule';
import {DesignStoreClient} from './sharedDesignLibrary';
import {CubeDesignerSurface} from './CubeDesignerSurface';
import {CubesNavigator, requestCubeCreate} from './CubesNavigator';

export const CUBE_MODULE_ID = 'cdeadmin.cube';
export const CUBE_DESIGN_ASSET_TYPE = 'cdeadmin.design.cube';

function toolbarActionCommand(id, label, description, iconKey) {
  return {
    // Open-cube actions stay on the open designer toolbar, never on the Tools
    // menu (owner direction 2026-11-08, docs/en_US/menu_bar.rst).
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
          `Command ${id} requires an active Cube designer surface.`
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

export function cubeModuleDefinition() {
  return {
    id: CUBE_MODULE_ID,
    version: '1.0.0',
    title: 'Cube Designer',
    iconKey: 'object.cube',
    serviceRequirements: [PROJECT_ASSET_SERVICE_ID, DESIGN_STORE_SERVICE_ID],
    contributions: {
      surfaces: [
        {
          id: 'diagram.cube.designer',
          title: 'Cube Designer',
          iconKey: 'object.cube',
          assetTypes: [CUBE_DESIGN_ASSET_TYPE],
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
            return React.createElement(CubeDesignerSurface, {
              projectId: descriptor.projectId,
              designId: descriptor.restoreRef,
              client,
              readOnly: context.readOnly === true,
              executeCommand: surfaceCommandExecutor(context),
              onStateChange: (state) =>
                context.setSurfaceState?.({
                  cubeDesignState: state,
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
          id: 'cube.designer.new',
          label: 'New Cube…',
          description:
            'Create a dimensional cube design or load one from the semantic-model store.',
          iconKey: 'object.cube',
          surfaces: ['tools', 'project'],
          permission: ['project.asset.edit'],
          execute: (_args, context) => {
            context.showActivity?.('activity.cubes');
            requestCubeCreate();
          },
        },
        {
          id: 'cube.designer.show',
          label: 'Cubes',
          description: 'List and open dimensional cube designs across projects.',
          iconKey: 'object.cube',
          surfaces: ['tools', 'view'],
          execute: (_args, context) => {
            if (typeof context.showActivity !== 'function') {
              throw new Error('Workbench activity authority is unavailable.');
            }
            return context.showActivity('activity.cubes');
          },
        },
        {
          id: 'cube.designer.open',
          label: 'Open in Cube Designer',
          description: 'Open a versioned cube design from the design store.',
          iconKey: 'object.cube',
          surfaces: ['toolbar'],
          validateArguments: validateDesignArguments,
          execute: async (args, context) => {
            if (typeof context.openSurface !== 'function') {
              throw new Error(
                'Workbench surface opening authority is unavailable.'
              );
            }
            return context.openSurface('diagram.cube.designer', {
              toolInstanceId:
                args.toolInstanceId ??
                `diagram.cube.designer:${args.projectId}:${args.designId}`,
              restoreRef: args.designId,
              projectId: args.projectId,
              title: args.title,
            });
          },
        },
        toolbarActionCommand(
          'cube.designer.save',
          'Save Cube Checkpoint',
          'Save a directed save-point version of the active cube design.',
          'action.save'
        ),
        toolbarActionCommand(
          'cube.designer.materialization_plan',
          'Preview Materialized Aggregate Plan',
          'Highlight materialized aggregate database changes for native review.',
          'tool.schema-compare'
        ),
        toolbarActionCommand(
          'cube.designer.accept',
          'Accept & Apply Cube',
          'Accept a save-point version and apply it to the semantic-model store.',
          'action.save'
        ),
      ],
      activity: [
        {
          id: 'activity.cubes',
          label: 'Cubes',
          iconKey: 'object.cube',
          priority: 53,
          surfaceId: 'diagram.cube.designer',
          render: () => React.createElement(CubesNavigator),
        },
      ],
      inspector: [
        {
          id: 'inspector.cube.bindings',
          label: 'Cube bindings',
          priority: 73,
          when: (context) => context.surfaceId === 'diagram.cube.designer',
          render: (context) => context.cubeDesignState?.bindings ?? [],
        },
      ],
      status: [
        {
          id: 'status.cube.version',
          label: 'Cube version state',
          priority: 43,
          when: (context) => context.surfaceId === 'diagram.cube.designer',
          value: (context) =>
            context.cubeDesignState?.loaded
              ? `v${context.cubeDesignState.currentVersion} (${context.cubeDesignState.status})`
              : 'loading',
        },
      ],
    },
  };
}

export function registerCubeModule({modules, services, api} = {}) {
  if (!modules || !services) {
    throw new TypeError(
      'Cube designer registration requires module and service registries.'
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
  const removeModule = modules.register(cubeModuleDefinition());
  return () => {
    removeModule();
    removers.reverse().forEach((remove) => remove());
  };
}
