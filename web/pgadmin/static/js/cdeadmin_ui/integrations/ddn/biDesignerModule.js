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
import {BIDesignerSurface} from './BIDesignerSurface';
import {BIDesignsNavigator, requestBIDesignCreate} from './BIDesignsNavigator';

export const BI_DESIGNER_MODULE_ID = 'cdeadmin.bi_designer';
export const BI_QUESTION_DESIGN_ASSET_TYPE = 'cdeadmin.design.question';
export const BI_DASHBOARD_DESIGN_ASSET_TYPE = 'cdeadmin.design.dashboard';

function toolbarActionCommand(id, label, description, iconKey) {
  return {
    // Open-design actions stay on the open designer toolbar, never on the
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
          `Command ${id} requires an active BI designer surface.`
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

export function biDesignerModuleDefinition() {
  return {
    id: BI_DESIGNER_MODULE_ID,
    version: '1.0.0',
    title: 'BI Questions & Dashboards Designer',
    iconKey: 'tool.bi',
    serviceRequirements: [PROJECT_ASSET_SERVICE_ID, DESIGN_STORE_SERVICE_ID],
    contributions: {
      surfaces: [
        {
          id: 'diagram.bi.designer',
          title: 'BI Question & Dashboard Designer',
          iconKey: 'tool.bi',
          assetTypes: [
            BI_QUESTION_DESIGN_ASSET_TYPE,
            BI_DASHBOARD_DESIGN_ASSET_TYPE,
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
            return React.createElement(BIDesignerSurface, {
              projectId: descriptor.projectId,
              designId: descriptor.restoreRef,
              kind:
                descriptor.assetType === BI_DASHBOARD_DESIGN_ASSET_TYPE
                  ? 'dashboard'
                  : context.kind || descriptor.kind || 'question',
              client,
              readOnly: context.readOnly === true,
              executeCommand: surfaceCommandExecutor(context),
              onStateChange: (state) =>
                context.setSurfaceState?.({
                  biDesignState: state,
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
          id: 'bi.designer.new',
          label: 'New BI Question or Dashboard…',
          description:
            'Create a BI question or dashboard design, or import Superset / Metabase content into Draft DDN.',
          iconKey: 'tool.bi',
          surfaces: ['tools', 'project'],
          permission: ['project.asset.edit'],
          execute: (_args, context) => {
            context.showActivity?.('activity.bi_designs');
            requestBIDesignCreate();
          },
        },
        {
          id: 'bi.designer.show',
          label: 'BI Questions & Dashboards',
          description:
            'List and open BI question and dashboard designs across projects.',
          iconKey: 'tool.bi',
          surfaces: ['tools', 'view'],
          execute: (_args, context) => {
            if (typeof context.showActivity !== 'function') {
              throw new Error('Workbench activity authority is unavailable.');
            }
            return context.showActivity('activity.bi_designs');
          },
        },
        {
          id: 'bi.designer.open',
          label: 'Open in BI Designer',
          description:
            'Open a versioned BI question or dashboard design from the design store.',
          iconKey: 'tool.bi',
          surfaces: ['toolbar'],
          validateArguments: validateDesignArguments,
          execute: async (args, context) => {
            if (typeof context.openSurface !== 'function') {
              throw new Error(
                'Workbench surface opening authority is unavailable.'
              );
            }
            return context.openSurface(
              'diagram.bi.designer',
              {
                toolInstanceId:
                  args.toolInstanceId ??
                  `diagram.bi.designer:${args.projectId}:${args.designId}`,
                restoreRef: args.designId,
                projectId: args.projectId,
                title: args.title,
              },
              {kind: args.kind ?? 'question'}
            );
          },
        },
        toolbarActionCommand(
          'bi.designer.save',
          'Save BI Checkpoint',
          'Save a directed save-point version of the active BI question or dashboard.',
          'action.save'
        ),
        toolbarActionCommand(
          'bi.designer.sql_bridge',
          'Open SQL Bridge',
          'Compile SBsql to dialect SQL with bound parameters or map SQL onto SBsql.',
          'tool.query'
        ),
        toolbarActionCommand(
          'bi.designer.outward_review',
          'Review Outward Effects',
          'Review subscriptions, embeds and remote dashboard-server publication separately from acceptance.',
          'action.settings'
        ),
        toolbarActionCommand(
          'bi.designer.accept',
          'Accept BI Version',
          'Accept a save-point version and activate it without switching on outward effects.',
          'action.save'
        ),
      ],
      activity: [
        {
          id: 'activity.bi_designs',
          label: 'BI Questions & Dashboards',
          iconKey: 'tool.bi',
          priority: 54,
          surfaceId: 'diagram.bi.designer',
          render: () => React.createElement(BIDesignsNavigator),
        },
      ],
      inspector: [
        {
          id: 'inspector.bi.bindings',
          label: 'BI bindings',
          priority: 74,
          when: (context) => context.surfaceId === 'diagram.bi.designer',
          render: (context) => context.biDesignState?.bindings ?? [],
        },
      ],
      status: [
        {
          id: 'status.bi.version',
          label: 'BI design version state',
          priority: 44,
          when: (context) => context.surfaceId === 'diagram.bi.designer',
          value: (context) =>
            context.biDesignState?.loaded
              ? `v${context.biDesignState.currentVersion} (${context.biDesignState.status})`
              : 'loading',
        },
      ],
    },
  };
}

export function registerBIDesignerModule({modules, services, api} = {}) {
  if (!modules || !services) {
    throw new TypeError(
      'BI designer registration requires module and service registries.'
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
  const removeModule = modules.register(biDesignerModuleDefinition());
  return () => {
    removeModule();
    removers.reverse().forEach((remove) => remove());
  };
}
