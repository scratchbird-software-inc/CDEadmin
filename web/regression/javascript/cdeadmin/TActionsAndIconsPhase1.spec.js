/////////////////////////////////////////////////////////////
//
// ScratchRobin — Phase 1 Unified Action, Icon, i18n & RBAC Tests
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  CommandRegistry,
  TActionsRegistry,
  T_ACTION_STATUS,
} from 'sources/cdeadmin_ui';
import {
  inferActionIconKey,
  resolveIconDefinition,
} from 'sources/cdeadmin_ui/icons/registry';
import {CANONICAL_ACTION_CATALOG} from 'sources/cdeadmin_ui/shell/actionPlacementEngine';
import uiCatalogs from '../../../pgadmin/static/js/cdeadmin_ui/i18n/ui_catalogs.json';

describe('Phase 1 — Unified t_actions, 71+ Semantic Icons, 15-Locale i18n & RBAC', () => {
  it('resolves every broken and newly added semantic icon without falling back to command.default', () => {
    const requiredKeys = [
      // Previously broken 17+ keys
      'navigation.sidebar',
      'view.toolbar',
      'view.status',
      'action.external',
      'security.lock',
      'help.docs',
      'help.info',
      'action.play',
      'action.pause',
      'action.stop',
      'action.tune',
      'action.history',
      'action.source_endpoint',
      'action.target_endpoint',
      'action.customize',
      'action.preferences',
      'action.menu',
      'action.operation',
      'tool.schema-diff',
      'object.folder',
      // Newly designed semantic icons
      'action.drawer_close',
      'action.sign_out',
      'action.unlock',
      'action.external_link',
      'action.status_in_progress',
      'action.status_in_review',
      'action.accept_version',
      'action.branch_draft',
      'action.git_sync',
      'action.where_used',
      'action.recompute_layout',
      'action.sketch_look',
      'action.promote_whiteboard',
      'action.level_conceptual',
      'action.level_logical',
      'action.level_physical',
      'action.level_deployment',
      'action.pin_node',
      'action.naming_standards',
      'action.engine_convert',
      'action.system_drift',
      'action.env_matrix',
      'object.dimension',
      'object.hierarchy',
      'object.measure',
      'action.usage_matrix',
      'action.ai_draft',
      'action.lattice_reducer',
      'action.perspective',
      'action.locale_translation',
      'action.dashboard_cards',
      'action.axis_format',
      'action.accessible_table',
      'action.collector_snapshot',
      'action.subscriptions_alerts',
      'action.embed_switch',
      'action.kiosk_device',
      'ui.screen_frame',
      'ui.grid_control',
      'ui.dropdown_control',
      'ui.radio_control',
      'ui.tabs_control',
      'ui.region_hotspot',
      'ui.data_binding',
      'ui.screen_navigation',
      'action.screenshot_upload',
      'action.redact_region',
      'action.trace_mesh',
      'action.sql_builder',
      'action.savepoint',
      'action.export_csv',
      'action.export_json',
      'action.connect_as',
      'action.manage_routes',
      'action.browse_data',
      'action.engines',
      'action.truncate',
      'action.count_rows',
      'tool.docker',
      'tool.profiler',
      'tool.isql',
      'tool.psql',
      'tool.binlog_replay',
    ];

    for (const key of requiredKeys) {
      const resolved = resolveIconDefinition(key);
      expect(resolved.key).toBe(key);
      expect(resolved.key).not.toBe('command.default');
      expect(resolved.key).not.toBe('object.unknown');
      expect(resolved.kind).toBe('component');
    }

    for (const entry of CANONICAL_ACTION_CATALOG) {
      const resolved = resolveIconDefinition(entry.icon);
      expect(resolved.key).toBe(entry.icon);
      expect(resolved.key).not.toBe('command.default');
    }
  });

  it('infers dedicated icons for provider context and SQL actions', () => {
    expect(inferActionIconKey({label: 'Connect as user'})).toBe('action.connect_as');
    expect(inferActionIconKey({label: 'Manage routes'})).toBe('action.manage_routes');
    expect(inferActionIconKey({label: 'Browse data'})).toBe('action.browse_data');
    expect(inferActionIconKey({label: 'Build query…'})).toBe('action.sql_builder');
    expect(inferActionIconKey({name: 'open_firebird_docker'})).toBe('tool.docker');
    expect(inferActionIconKey({name: 'open_firebird_profiler'})).toBe('tool.profiler');
    expect(inferActionIconKey({name: 'open_firebird_isql'})).toBe('tool.isql');
  });

  it('delegates canonical t_actions to the active focused instance and enforces RBAC', async () => {
    const executed = [];
    const registry = new TActionsRegistry({
      translate: Object.assign((s) => s, {retranslate: (s) => `TR:${s}`}),
    });

    registry.register({
      id: 'sql.execute',
      defaultText: 'Execute SQL Statement',
      delegated: true,
      permission: ['sql_execute'],
      allowedSecurityGroups: ['analysts', 'admins'],
      deniedSecurityGroups: ['suspended'],
      execute: () => executed.push('fallback'),
    });

    // Unbound delegated action defaults to disabled
    expect(registry.resolve('sql.execute').status).toBe(T_ACTION_STATUS.DISABLED);

    // Bind two instances
    registry.register({
      id: 'sql.execute.inst-1',
      defaultText: 'Execute 1',
      status: T_ACTION_STATUS.ENABLED,
      execute: () => executed.push('inst-1'),
    });
    registry.bindInstanceActions('inst-2', {
      'sql.execute': {
        status: T_ACTION_STATUS.ENABLED,
        invoke: () => executed.push('inst-2'),
      },
    });

    // Authorize user
    registry.setCurrentUser({
      permissions: ['sql_execute'],
      security_groups: ['analysts'],
    });

    registry.setActiveInstance('inst-1');
    expect(registry.resolve('sql.execute').enabled).toBe(true);
    expect(registry.resolve('sql.execute').text).toBe('TR:Execute SQL Statement');
    await registry.execute('sql.execute');

    registry.setActiveInstance('inst-2');
    await registry.execute('sql.execute');
    expect(executed).toEqual(['inst-1', 'inst-2']);

    // Missing permission disables action
    registry.setCurrentUser({
      permissions: [],
      security_groups: ['analysts'],
    });
    expect(registry.resolve('sql.execute').status).toBe(T_ACTION_STATUS.DISABLED);

    // Denied group hides action
    registry.setCurrentUser({
      permissions: ['sql_execute'],
      security_groups: ['analysts', 'suspended'],
    });
    expect(registry.resolve('sql.execute').status).toBe(T_ACTION_STATUS.INVISIBLE);
  });

  it('auto-syncs newly registered CommandRegistry descriptors and supports actions/controls in toNotebookBar', async () => {
    const cmdReg = new CommandRegistry();
    const actReg = new TActionsRegistry();
    actReg.attachCommandRegistry(cmdReg);

    const spy = jest.fn(() => 'accepted');
    cmdReg.register({
      id: 'erd.designer.accept',
      label: 'Accept',
      iconKey: 'action.accept_version',
      permission: 'design_accept',
      execute: spy,
    });

    expect(actReg.has('erd.designer.accept')).toBe(true);
    expect(actReg.resolve('erd.designer.accept').icon).toBe('action.accept_version');
    expect(actReg.hasPermission('design_accept')).toBe(true);
    actReg.setCurrentUser({permissions: ['sql_execute']});
    expect(actReg.hasPermission('design_accept')).toBe(false);
    actReg.setCurrentUser({permissions: ['design_accept']});
    expect(actReg.hasPermission('design_accept')).toBe(true);
    await expect(actReg.execute('erd.designer.accept')).resolves.toBe('accepted');

    const nb = actReg.toNotebookBar([
      {
        id: 'modelling',
        label: 'Modelling',
        groups: [{id: 'g1', label: 'Lifecycle', actions: ['erd.designer.accept']}],
      },
    ]);
    expect(nb.model.tabs[0].groups[0].controls).toHaveLength(1);
    expect(nb.model.tabs[0].groups[0].controls[0].command).toBe('erd.designer.accept');
  });

  it('translates every CANONICAL_ACTION_CATALOG label across all 14 non-English locales', () => {
    const locales = Object.keys(uiCatalogs.gettext);
    expect(locales).toHaveLength(14);
    for (const entry of CANONICAL_ACTION_CATALOG) {
      for (const loc of locales) {
        expect(typeof uiCatalogs.gettext[loc][entry.label]).toBe('string');
        expect(uiCatalogs.gettext[loc][entry.label].length).toBeGreaterThan(0);
      }
    }
  });
});
