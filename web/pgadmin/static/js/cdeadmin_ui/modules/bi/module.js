/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Registers the "BI questions" tool in the workbench tool registry. The
 * Object Explorer opens it through the engine-neutral `open_tool` handler
 * that each engine's ui_descriptors/<engine>/tools.json entry names, passing
 * the registered surface id below plus the endpoint's workspace route.
 */

import {createElement} from 'react';
import gettext from 'sources/gettext';
import {EmptyState} from '../../feedback/EmptyState';

export const BI_MODULE_ID = 'cdeadmin.bi';
export const BI_QUESTIONS_SURFACE_ID = 'bi.questions';
export const BI_MODELS_SURFACE_ID = 'bi.models';

async function restoreQuestionsTool(descriptor, context) {
  // A restored layout has the descriptor but not the endpoint route; the route
  // is a live handle, so the tool asks to be opened again from the tree.
  if(!context.api || !context.endpointUrl) {
    return createElement(EmptyState, {message: gettext(
      'Open BI questions again from the endpoint in the object tree to reconnect this tool.')});
  }
  // Loaded on first use so the chart and editor libraries stay out of the start-up bundle.
  const {default: BIQuestionsTool} = await import('./BIQuestionsTool');
  return createElement(BIQuestionsTool, {
    api: context.api, endpointUrl: context.endpointUrl,
    onDirtyChange: (dirty) => context.setSurfaceState?.({
      dirty, persistence: dirty ? 'dirty' : 'clean'}),
  });
}

async function restoreModelsTool(descriptor, context) {
  if(!context.api || !context.endpointUrl) {
    return createElement(EmptyState, {message: gettext(
      'Open BI models again from the endpoint in the object tree to reconnect this tool.')});
  }
  const {default: BIModelsTool} = await import('./models/BIModelsTool');
  return createElement(BIModelsTool, {
    api: context.api, endpointUrl: context.endpointUrl,
    onDirtyChange: (dirty) => context.setSurfaceState?.({
      dirty, persistence: dirty ? 'dirty' : 'clean'}),
  });
}

export function biModuleDefinition() {
  return {
    id: BI_MODULE_ID, version: '1.0.0', title: 'BI questions', iconKey: 'tool.data-explorer',
    contributions: {
      surfaces: [{
        id: BI_QUESTIONS_SURFACE_ID, title: 'BI questions', iconKey: 'tool.data-explorer',
        readOnly: false, editable: true, detachable: true, duplicable: false, fullscreen: true,
        restore: restoreQuestionsTool,
        canClose: async (_descriptor, context) => context.dirty ?
          {allowed: false, reason: 'Save or discard the open question or dashboard first.'} :
          {allowed: true, reason: ''},
      }, {
        id: BI_MODELS_SURFACE_ID, title: 'BI models', iconKey: 'tool.data-explorer',
        readOnly: false, editable: true, detachable: true, duplicable: false, fullscreen: true,
        restore: restoreModelsTool,
        canClose: async (_descriptor, context) => context.dirty ?
          {allowed: false, reason: 'Save or discard the open semantic model first.'} :
          {allowed: true, reason: ''},
      }],
    },
  };
}

export function registerBIModule({modules} = {}) {
  if(!modules) throw new TypeError('BI registration requires a module registry.');
  return modules.register(biModuleDefinition());
}
