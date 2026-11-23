/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {act, render} from '@testing-library/react';
import pgAdmin from 'sources/pgadmin';
import {
  activateSQLConnection,
  removeSQLConnections,
  requestSQLSource,
  sqlConnectionKey,
  takeSQLSourceRequest,
  useSQLConnections,
  useSQLSourceRequest,
} from 'sources/cdeadmin_ui/editors/SQLConnections';
import useFirebirdDataSession, {
  releaseSharedFirebirdDataSession,
} from 'sources/Dialogs/firebirdDataSession';
import {makePost} from 'sources/cdeadmin_ui/objects/ProviderObjectEditorHost';
import {descriptorClient, resetDescriptorClient, resolveBundle} from 'sources/cdeadmin_ui/objects';
import engineObjectFamily from '../../../pgadmin/cdeadmin/ui_descriptors/families/engine_object.family.json';
import realExceptionForm from '../../../pgadmin/cdeadmin/ui_descriptors/firebird/forms/exception.form.json';
import realServiceOpForm from '../../../pgadmin/cdeadmin/ui_descriptors/firebird/forms/service-operation.form.json';
import {
  cachedDescriptorBundle,
  familyCoversKind,
  withTargetOperationDefaults,
} from 'pgbrowser/ProviderObjectEditor';
import {
  openNodeDatabaseProperties,
  providerContextMenuItems,
  providerTreeContextActions,
} from 'pgbrowser/ProviderContextMenu';
import {resolveExplorerDescriptorVersion} from 'sources/tree/ObjectExplorer';
import {
  BI_DESIGN_OPEN_EVENT,
  CUBE_OPEN_EVENT,
  ERD_MODEL_OPEN_EVENT,
  SCREEN_MESH_OPEN_EVENT,
} from 'sources/cdeadmin_ui/integrations/ddn';

const action = (overrides = {}) => ({
  schema: 'cdeadmin.context-action.v1',
  command_id: 'database.firebird.connect',
  command_version: 1,
  label: 'Connect database...',
  handler: 'open_workspace',
  icon_key: 'action.connect',
  menu_group: 'connection',
  priority: 10,
  mutation_class: 'admin',
  arguments: {},
  enabled: true,
  macro_callable: true,
  ...overrides,
});

describe('Phase 3 session continuity, context menus, and descriptor guards', () => {
  afterEach(() => {
    act(() => {
      removeSQLConnections('srv-phase3');
    });
    document.body.innerHTML = '';
  });

  it('isolates SQLConnections entries and Browse Data requests per (endpointUrl, databaseTargetId)', () => {
    expect(sqlConnectionKey('/cdeadmin/ws/1', 'db-1')).toBe('/cdeadmin/ws/1::db-1');
    expect(sqlConnectionKey('/cdeadmin/ws/1?database_target_id=db-2')).toBe('/cdeadmin/ws/1::db-2');

    let observed = null;
    let sourceDb1 = null;
    let sourceDb2 = null;
    function Probe() {
      observed = useSQLConnections();
      sourceDb1 = useSQLSourceRequest('/cdeadmin/ws/1', 'db-1');
      sourceDb2 = useSQLSourceRequest('/cdeadmin/ws/1', 'db-2');
      return null;
    }

    const view = render(<Probe />);
    act(() => {
      activateSQLConnection({
        id: '/cdeadmin/ws/1',
        serverId: 'srv-phase3',
        databaseTargetId: 'db-1',
        label: 'DB 1',
        content: <div>DB1</div>,
      });
      activateSQLConnection({
        id: '/cdeadmin/ws/1',
        serverId: 'srv-phase3',
        databaseTargetId: 'db-2',
        label: 'DB 2',
        content: <div>DB2</div>,
      });
    });

    expect(observed.entries).toHaveLength(2);
    expect(observed.entries.map((e) => e.id)).toEqual([
      '/cdeadmin/ws/1::db-1',
      '/cdeadmin/ws/1::db-2',
    ]);
    expect(observed.selected).toBe('/cdeadmin/ws/1::db-2');

    act(() => {
      requestSQLSource('/cdeadmin/ws/1', {sql: 'SELECT * FROM T1'}, 'db-1');
    });
    expect(sourceDb1?.sql).toBe('SELECT * FROM T1');
    expect(sourceDb2).toBeNull();
    act(() => {
      takeSQLSourceRequest('/cdeadmin/ws/1', sourceDb1.nonce, 'db-1');
      removeSQLConnections('srv-phase3', 'db-2');
    });

    // Removing DB2 leaves DB1 untouched and selected.
    expect(observed.entries.map((e) => e.id)).toEqual(['/cdeadmin/ws/1::db-1']);
    expect(observed.selected).toBe('/cdeadmin/ws/1::db-1');
    view.unmount();
  });

  it('retains reusable/shared Firebird data sessions across sub-panel unmounts until explicit release', async () => {
    let seq = 0;
    const post = jest.fn(async (payload) => {
      if (payload.action === 'open_session') {
        seq += 1;
        return {session_id: `fb-sess-${seq}`};
      }
      if (payload.action === 'close_session') {
        return {provider_closed: true, session_id: payload.session_id};
      }
      return {};
    });

    let sessionApi = null;
    function Panel() {
      sessionApi = useFirebirdDataSession({
        post,
        databaseTargetId: 'db-1',
        purpose: 'browse',
        reusable: true,
      });
      return <div>panel</div>;
    }

    const view = render(<Panel />);
    const sid = await sessionApi.ensure();
    expect(sid).toBe('fb-sess-1');

    view.unmount();
    expect(post).not.toHaveBeenCalledWith(expect.objectContaining({action: 'close_session'}));

    await releaseSharedFirebirdDataSession(post, {databaseTargetId: 'db-1', purpose: 'browse'});
    expect(post).toHaveBeenCalledWith({
      action: 'close_session',
      session_id: 'fb-sess-1',
      database_target_id: 'db-1',
    });
  });

  it('normalizes DescriptorClient version keys and guards familyCoversKind when bundle is null or inspect-only', async () => {
    expect(
      resolveExplorerDescriptorVersion(
        {_type: 'cde_resource'},
        {server: {verified_runtime_version: '5.0.4'}}
      )
    ).toBe('5.0.4');

    expect(familyCoversKind(null, 'table')).toBe(false);
    expect(familyCoversKind(undefined, 'exception')).toBe(false);

    resetDescriptorClient();
    const resolvedServerBundle = resolveBundle({
      engine: 'firebird',
      families: {engine_object: engineObjectFamily},
      capabilities: {
        engine: 'firebird',
        kinds: [
          {
            resource_kind: 'exception',
            family: 'engine_object',
            title: 'Exception',
            operations: [
              {operation_id: 'inspect'},
              {operation_id: 'create'},
              {operation_id: 'alter'},
              {operation_id: 'drop'},
            ],
          },
          {
            resource_kind: 'service-operation',
            family: 'engine_object',
            title: 'Service operation',
            operations: [{operation_id: 'inspect'}],
          },
        ],
      },
      forms: {
        exception: realExceptionForm,
        serviceOperation: realServiceOpForm,
      },
    });
    const api = {
      get: jest.fn().mockResolvedValue({data: {success: 1, data: resolvedServerBundle}}),
    };
    const loadedBundle = await descriptorClient(api).bundle('firebird');
    expect(cachedDescriptorBundle(api, 'firebird', '5.0.4')).toEqual(loadedBundle);
    expect(familyCoversKind(loadedBundle, 'exception', null, 'create')).toBe(true);
    expect(familyCoversKind(loadedBundle, 'exception', null, 'alter')).toBe(true);
    expect(familyCoversKind(loadedBundle, 'service-operation', null, 'alter')).toBe(false);
    expect(familyCoversKind(loadedBundle, 'service-operation', null, 'create')).toBe(false);
    expect(realExceptionForm.status).toBe('complete');
    expect(realServiceOpForm.status).toBe('complete');
  });

  it('populates target object names across operation descriptor field variants without touching child-naming ops', () => {
    const opTable = withTargetOperationDefaults(
      {operation_id: 'analyze_table', fields: [{field_id: 'table_name', control: 'text'}]},
      'ORDERS',
      'table'
    );
    expect(opTable.fields[0].default).toBe('ORDERS');

    const opSeq = withTargetOperationDefaults(
      {operation_id: 'set_current', fields: [{field_id: 'sequence_name', control: 'text'}]},
      'GEN_ORDER_ID',
      'sequence'
    );
    expect(opSeq.fields[0].default).toBe('GEN_ORDER_ID');

    const childOp = withTargetOperationDefaults(
      {operation_id: 'create-partition', fields: [{field_id: 'name', control: 'text'}]},
      'ORDERS',
      'table'
    );
    expect(childOp.fields[0].default).toBeUndefined();
  });

  it('deduplicates database connect actions, opens Properties over inline tabs, and routes live designer events', () => {
    const dbNode = {
      _type: 'cde_database_target',
      cde_engine_id: 'firebird',
      cde_database_target_id: 'db-1',
      cde_context_actions: [
        action({command_id: 'database.firebird.connect', label: 'Connect database...'}),
        action({command_id: 'database.firebird.connect_database', label: 'Connect to database...'}),
      ],
    };
    const deduped = providerContextMenuItems(dbNode);
    expect(deduped).toHaveLength(1);
    expect(deduped[0].commandId).toBe('database.firebird.connect');

    // Simulate ProjectShell active with an inline tab mounted (data-navigator-work-area unmounted).
    const backdrop = document.createElement('div');
    backdrop.setAttribute('data-cdeadmin-qa-key', 'project-shell-backdrop');
    document.body.appendChild(backdrop);

    const surfaceEvents = [];
    const tabEvents = [];
    const erdEvents = [];
    const cubeEvents = [];
    const biEvents = [];
    const meshEvents = [];
    const onSurface = (e) => surfaceEvents.push(e.detail);
    const onTab = (e) => tabEvents.push(e.detail);
    const onErd = (e) => erdEvents.push(e.detail);
    const onCube = (e) => cubeEvents.push(e.detail);
    const onBi = (e) => biEvents.push(e.detail);
    const onMesh = (e) => meshEvents.push(e.detail);

    window.addEventListener('scratchrobin:open-app-surface', onSurface);
    window.addEventListener('scratchrobin:navigator-select-tab', onTab);
    window.addEventListener(ERD_MODEL_OPEN_EVENT, onErd);
    window.addEventListener(CUBE_OPEN_EVENT, onCube);
    window.addEventListener(BI_DESIGN_OPEN_EVENT, onBi);
    window.addEventListener(SCREEN_MESH_OPEN_EVENT, onMesh);

    pgAdmin.Browser = pgAdmin.Browser || {};
    pgAdmin.Browser.tree = {
      select: jest.fn(),
      itemData: jest.fn((node) =>
        node?.id === 'srv-1'
          ? {_type: 'server', _id: 1, label: 'Firebird 5.0', cde_engine_id: 'firebird'}
          : dbNode
      ),
      hasParent: (node) => node?.id === 'tbl-orders',
      parent: () => ({id: 'srv-1'}),
    };

    try {
      expect(openNodeDatabaseProperties(dbNode, {id: 'db-node-1'})).toBe(true);
      expect(surfaceEvents[0]).toEqual({
        appId: 'data-navigator',
        payload: {tab: 'properties', focusEditor: true},
      });
      expect(tabEvents[0]).toEqual({tab: 'properties', focusEditor: true});

      const designNode = {
        _type: 'cde_resource',
        cde_engine_id: 'firebird',
        cde_database_target_id: 'db-1',
        cde_resource_id: 'table:ORDERS',
        cde_resource_kind: 'table',
        label: 'ORDERS',
        cde_context_actions: [
          action({
            command_id: 'resource.firebird.design_erd',
            label: 'Design from this database...',
            handler: 'open_tool',
            menu_group: 'common',
            arguments: {activity: 'activity.erd-models', design_shortcut: 'erd_from_database'},
          }),
          action({
            command_id: 'resource.firebird.design_cube',
            label: 'New cube from this table...',
            handler: 'open_tool',
            menu_group: 'common',
            arguments: {activity: 'activity.cubes', design_shortcut: 'cube_from_table'},
          }),
          action({
            command_id: 'resource.firebird.design_bi',
            label: 'New BI question from this table...',
            handler: 'open_tool',
            menu_group: 'common',
            arguments: {activity: 'activity.bi-designs', design_shortcut: 'bi_question_from_table'},
          }),
          action({
            command_id: 'resource.firebird.design_mesh',
            label: 'New screen mesh from this table...',
            handler: 'open_tool',
            menu_group: 'common',
            arguments: {activity: 'activity.screen-meshes', design_shortcut: 'screen_mesh_from_table'},
          }),
        ],
      };
      const entries = providerTreeContextActions(designNode, {id: 'tbl-orders'});
      for (const entry of entries) {
        if (typeof entry.execute === 'function') {
          entry.execute();
        } else if (Array.isArray(entry.children)) {
          entry.children.forEach((child) => child.execute?.());
        }
      }
      expect(surfaceEvents.map((d) => d.appId)).toEqual(
        expect.arrayContaining([
          'erd-designer',
          'cube-designer',
          'bi-designer',
          'screen-mesh-designer',
        ])
      );
      expect(erdEvents.length).toBeGreaterThanOrEqual(1);
      expect(cubeEvents.length).toBeGreaterThanOrEqual(1);
      expect(biEvents.length).toBeGreaterThanOrEqual(1);
      expect(meshEvents.length).toBeGreaterThanOrEqual(1);
    } finally {
      window.removeEventListener('scratchrobin:open-app-surface', onSurface);
      window.removeEventListener('scratchrobin:navigator-select-tab', onTab);
      window.removeEventListener(ERD_MODEL_OPEN_EVENT, onErd);
      window.removeEventListener(CUBE_OPEN_EVENT, onCube);
      window.removeEventListener(BI_DESIGN_OPEN_EVENT, onBi);
      window.removeEventListener(SCREEN_MESH_OPEN_EVENT, onMesh);
    }
  });

  it('prompts for endpoint verification and retries pending call on HTTP 401 CREDENTIAL_REQUIRED', async () => {
    let attempts = 0;
    const api = {
      post: jest.fn(async (_url, body) => {
        attempts += 1;
        if (attempts === 1) {
          const err = new Error('Endpoint credentials are required');
          err.response = {
            status: 401,
            data: {success: 0, errormsg: 'Endpoint credentials are required', data: {code: 'CREDENTIAL_REQUIRED'}},
          };
          throw err;
        }
        return {data: {success: 1, data: {resource_id: body.request.resource_id, ok: true}}};
      }),
    };
    const onAuthRequired = jest.fn().mockResolvedValue(true);
    const post = makePost(api, '/cdeadmin/ws/1', 'db-1', {onAuthRequired});

    const result = await post({action: 'resource_inspect', request: {resource_id: 'table:ORDERS'}});
    expect(onAuthRequired).toHaveBeenCalledTimes(1);
    expect(attempts).toBe(2);
    expect(result).toEqual({resource_id: 'table:ORDERS', ok: true});
  });
});
