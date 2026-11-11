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
import {ScreenMeshDesignerSurface} from './ScreenMeshDesignerSurface';
import {
  ScreenMeshesNavigator,
  requestScreenMeshCreate,
} from './ScreenMeshesNavigator';

export const SCREEN_MESH_MODULE_ID = 'cdeadmin.screen_mesh';
export const SCREEN_MESH_DESIGN_ASSET_TYPE = 'cdeadmin.design.screen';
export const SCREEN_FLOW_DESIGN_ASSET_TYPE = 'cdeadmin.design.screen_flow';

function toolbarActionCommand(id, label, description, iconKey) {
  return {
    // Open-mesh actions stay on the open designer toolbar, never on the Tools
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
          `Command ${id} requires an active Screen Mesh designer surface.`
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

export function screenMeshModuleDefinition() {
  return {
    id: SCREEN_MESH_MODULE_ID,
    version: '1.0.0',
    title: 'Screen Mesh Designer',
    iconKey: 'tool.erd',
    serviceRequirements: [PROJECT_ASSET_SERVICE_ID, DESIGN_STORE_SERVICE_ID],
    contributions: {
      surfaces: [
        {
          id: 'diagram.screen_mesh.designer',
          title: 'Screen Mesh Designer',
          iconKey: 'tool.erd',
          assetTypes: [
            SCREEN_MESH_DESIGN_ASSET_TYPE,
            SCREEN_FLOW_DESIGN_ASSET_TYPE,
          ],
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
            return React.createElement(ScreenMeshDesignerSurface, {
              projectId: descriptor.projectId,
              designId: descriptor.restoreRef,
              client,
              readOnly: context.readOnly === true,
              executeCommand: surfaceCommandExecutor(context),
              onStateChange: (state) =>
                context.setSurfaceState?.({
                  screenMeshState: state,
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
          id: 'screen_mesh.designer.new',
          label: 'New Screen Mesh…',
          description:
            'Create a wireframe Screen Mesh or import a ScratchRobin SR-F UI descriptor form into Draft DDN.',
          iconKey: 'tool.erd',
          surfaces: ['tools', 'project'],
          permission: ['project.asset.edit'],
          execute: (_args, context) => {
            context.showActivity?.('activity.screen_meshes');
            requestScreenMeshCreate();
          },
        },
        {
          id: 'screen_mesh.designer.show',
          label: 'Screen Meshes',
          description:
            'List and open wireframe Screen Meshes and annotated screenshots across projects.',
          iconKey: 'tool.erd',
          surfaces: ['tools', 'view'],
          execute: (_args, context) => {
            if (typeof context.showActivity !== 'function') {
              throw new Error('Workbench activity authority is unavailable.');
            }
            return context.showActivity('activity.screen_meshes');
          },
        },
        {
          id: 'screen_mesh.designer.open',
          label: 'Open in Screen Mesh Designer',
          description:
            'Open a versioned Screen Mesh design from the design store.',
          iconKey: 'tool.erd',
          surfaces: ['toolbar'],
          validateArguments: validateDesignArguments,
          execute: async (args, context) => {
            if (typeof context.openSurface !== 'function') {
              throw new Error(
                'Workbench surface opening authority is unavailable.'
              );
            }
            return context.openSurface('diagram.screen_mesh.designer', {
              toolInstanceId:
                args.toolInstanceId ??
                `diagram.screen_mesh.designer:${args.projectId}:${args.designId}`,
              restoreRef: args.designId,
              projectId: args.projectId,
              title: args.title,
            });
          },
        },
        toolbarActionCommand(
          'screen_mesh.designer.save',
          'Save Screen Mesh Checkpoint',
          'Save a directed save-point version of the active Screen Mesh.',
          'action.save'
        ),
        toolbarActionCommand(
          'screen_mesh.designer.redact',
          'Redact Screenshot Regions',
          'Destructively redact sensitive PNG regions and purge original bytes from asset_blob.',
          'action.settings'
        ),
        toolbarActionCommand(
          'screen_mesh.designer.accept',
          'Accept Screen Mesh Version',
          'Accept a save-point version of the active Screen Mesh.',
          'action.save'
        ),
      ],
      activity: [
        {
          id: 'activity.screen_meshes',
          label: 'Screen Meshes',
          iconKey: 'tool.erd',
          priority: 56,
          surfaceId: 'diagram.screen_mesh.designer',
          render: () => React.createElement(ScreenMeshesNavigator),
        },
      ],
      inspector: [
        {
          id: 'inspector.screen_mesh.bindings',
          label: 'Screen Mesh bindings',
          priority: 76,
          when: (context) =>
            context.surfaceId === 'diagram.screen_mesh.designer',
          render: (context) => context.screenMeshState?.bindings ?? [],
        },
      ],
      status: [
        {
          id: 'status.screen_mesh.version',
          label: 'Screen Mesh version state',
          priority: 46,
          when: (context) =>
            context.surfaceId === 'diagram.screen_mesh.designer',
          value: (context) =>
            context.screenMeshState?.loaded
              ? `v${context.screenMeshState.currentVersion} (${context.screenMeshState.status})`
              : 'loading',
        },
      ],
    },
  };
}

export function registerScreenMeshModule({modules, services, api} = {}) {
  if (!modules || !services) {
    throw new TypeError(
      'Screen Mesh registration requires module and service registries.'
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
  const removeModule = modules.register(screenMeshModuleDefinition());
  return () => {
    removeModule();
    removers.reverse().forEach((remove) => remove());
  };
}
