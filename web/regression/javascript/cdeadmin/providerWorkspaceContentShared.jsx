/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/* global beforeAll, afterAll, beforeEach, afterEach */
// Shared setup for the ProviderWorkspaceContent specs. The single 4,670-line spec was
// split on 2026-11-10 so jest can spread its 327 tests across workers; test bodies are
// unchanged. jest.mock calls stay in each spec file because jest hoists them per file.
import {act, configure, getConfig, fireEvent, render as rtlRender, screen, waitFor, within} from '@testing-library/react';
import {useLayoutEffect, useState} from 'react';
import Theme from 'sources/Theme';
export const render = (ui, options) => rtlRender(ui, {wrapper: Theme, ...options});
import ProviderWorkspaceContent, {
  DatabaseTargetWorkspace,
  ObjectInspectorSection,
  ResultControls,
  RecordListAdminField,
  ServerProfileWorkspace,
  VisualAdministration,
  VisualAdminField,
  inspectorSections,
  initialObjectDraft,
  visibleFieldOptions,
  changedFieldDraft,
  administrationResourceId,
  administrationOutcomeValue,
} from '../../../pgadmin/static/js/Dialogs/ProviderWorkspaceContent';
import * as ProviderWorkspaceModule from '../../../pgadmin/static/js/Dialogs/ProviderWorkspaceContent';
import {modelFixtures} from '../bi/modelFixtures';
import getApiInstance from '../../../pgadmin/static/js/api_instance';
import {requestSQLSource} from '../../../pgadmin/static/js/cdeadmin_ui/editors/SQLConnections';
import firebirdManifest from '../../../pgadmin/cdeadmin/providers/firebird/provider_manifest.json';

export {act, configure, getConfig, fireEvent, screen, waitFor, within, useLayoutEffect, useState,
  ProviderWorkspaceContent, DatabaseTargetWorkspace, ObjectInspectorSection, ResultControls,
  RecordListAdminField, ServerProfileWorkspace, VisualAdministration, VisualAdminField,
  inspectorSections, initialObjectDraft, visibleFieldOptions, changedFieldDraft,
  administrationResourceId, administrationOutcomeValue, ProviderWorkspaceModule, modelFixtures,
  getApiInstance, requestSQLSource, firebirdManifest};

// Hosted native renderers need a bounded readiness allowance; assertions and
// provider responses remain identical on every platform.
export function installSharedHooks() {
  const previousAsyncTimeout = getConfig().asyncUtilTimeout;
  beforeAll(() => configure({asyncUtilTimeout: Math.max(previousAsyncTimeout, 5000)}));
  afterAll(() => configure({asyncUtilTimeout: previousAsyncTimeout}));
  let detailsObserver;
  beforeEach(() => {
    detailsObserver = new MutationObserver(() => document.querySelectorAll('details').forEach(node => node.open = true));
    detailsObserver.observe(document.body, {childList: true, subtree: true});
  });
  afterEach(() => detailsObserver.disconnect());
}

// The main describe's per-test state: viewport geometry and the mocked api instance.
export function installWorkspaceHooks() {
  let originalViewportHeight;
  beforeEach(() => {
    originalViewportHeight = window.innerHeight;
    // Shared virtual-grid geometry gives every element an 800px height.
    window.innerHeight = 1200;
  });
  afterEach(() => {
    window.innerHeight = originalViewportHeight;
    if(jest.isMockFunction(console.warn)) console.warn.mockRestore();
  });
  const holder = {api: null};
  beforeEach(() => {
    holder.api = {get: jest.fn(), post: jest.fn()};
    getApiInstance.mockReturnValue(holder.api);
    holder.api.get.mockResolvedValue({data: {data: bootstrap}});
  });
  return holder;
}

export const bootstrap = {
  endpoint: {
    provider_id: 'org.cdeadmin.mysql',
    verified_runtime_family: 'mysql',
  },
  grid_workspace: {
    schema: 'cdeadmin.provider-grid-workspace.v1',
    adoption_state: 'passed',
    activation_gates: [{
      gate_id: 'public_grid_boundary', state: 'passed',
    }],
    runtime_gate: {
      gate_id: 'live_provider_verification', state: 'passed',
    },
  },
  languages: [{
    language_profile: 'mysql-sql', title: 'MySQL SQL',
    starter_source: 'SELECT 42',
    source_presets: [{label: 'MySQL scalar query', source: 'SELECT 42'}],
  }],
  resource_page: {items: [{
    resource_id: 'database:example',
    resource_kind: 'database',
    display_name: 'example',
    authority_path: ['database', 'example'],
  }]},
  visual_admin: {
    engine_id: 'mysql',
    engine_name: 'MySQL',
    objects: [{
      resource_kind: 'database',
      title: 'Database',
      operations: [{
        operation_id: 'create',
        title: 'Create',
        mutation_class: 'admin',
        target_required: false,
        confirmation_required: false,
        blockers: ['provider_native_planner_unavailable'],
        form: {fields: [{
          field_id: 'name', label: 'Name', control: 'text', required: true,
        }]},
      }],
    }],
  },
  operational_workspace: {
    schema: 'cdeadmin.operational-workspace.v1',
    engine_id: 'mysql',
    distributed: false,
    categories: ['runtime'],
    topology: {available: false, resource_kinds: []},
    facets: [{
      facet_id: 'health',
      title: 'Server and cluster health',
      category: 'runtime',
      summary: 'Provider-reported availability and health state.',
      catalog_state: 'operational',
      unavailable_reason: null,
      resource_kinds: ['database'],
      discovered_resource_count: 1,
      operations: [{
        operation_id: 'create', resource_kind: 'database', title: 'Create',
      }],
    }],
  },
  semantic_models: {
    items: [],
    capabilities: {
      designer: true, revision_history: true, validation: true,
      lineage: true, query_builder: true, pivot_cellset: true,
      execution_available: true,
      provider_compiler: {execution_available: true},
      time_intelligence_operations: ['as_of', 'range', 'period_to_date',
        'period_comparison'],
      time_intelligence_periods: ['day', 'week', 'month', 'quarter', 'year',
        'fiscal_quarter', 'fiscal_year'],
      analytical_window_operations: ['running_sum', 'moving_average', 'lag'],
      scheduled_report_execution: false,
      analytical_profile: {
        title: 'Relational and multidimensional',
        semantic_family: 'relational',
        source_kinds: ['table', 'view', 'materialized-view'],
        source_classifications: ['fact', 'dimension', 'bridge', 'lookup'],
        dimension_kinds: ['attribute', 'time', 'geography'],
        relationship_kinds: ['join', 'bridge'],
        measure_kinds: ['aggregate', 'calculated'],
        grain_vocabulary: 'fact-key',
      },
    },
  },
};

