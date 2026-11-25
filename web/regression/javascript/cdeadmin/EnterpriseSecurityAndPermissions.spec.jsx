/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import Theme from 'sources/Theme';
import PrincipalSecurityManager from '../../../pgadmin/static/js/cdeadmin_ui/security/PrincipalSecurityManager';
import ObjectPermissionsMatrix, {
  computeGrantChanges,
} from '../../../pgadmin/static/js/cdeadmin_ui/security/ObjectPermissionsMatrix';
import {buildNavigatorSelectionConfig} from '../../../pgadmin/static/js/BrowserComponent';

describe('Enterprise Security Manager, Per-Object Permissions Matrix & Standard TiB Sections', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
  });

  describe('ObjectPermissionsMatrix', () => {
    it('computes granular grant, revoke, and grant-option changes per privilege', () => {
      const baselineRows = [
        {
          grantee: 'ALICE',
          grantee_kind: 'user',
          grantee_host: null,
          privileges: {
            SELECT: {granted: true, grant_option: false},
            INSERT: {granted: true, grant_option: false},
            UPDATE: {granted: false, grant_option: false},
          },
        },
      ];
      const draftRows = [
        {
          grantee: 'ALICE',
          grantee_kind: 'user',
          grantee_host: null,
          privileges: {
            SELECT: {granted: true, grant_option: true},
            INSERT: {granted: false, grant_option: false},
            UPDATE: {granted: true, grant_option: false},
          },
        },
      ];
      const changes = computeGrantChanges(baselineRows, draftRows, [
        'SELECT',
        'INSERT',
        'UPDATE',
      ]);
      expect(changes).toEqual([
        {
          action: 'revoke',
          grantee: 'ALICE',
          grantee_kind: 'user',
          grantee_host: null,
          privileges: ['INSERT'],
          columns: [],
          grant_option: false,
        },
        {
          action: 'grant',
          grantee: 'ALICE',
          grantee_kind: 'user',
          grantee_host: null,
          privileges: ['UPDATE'],
          columns: [],
          grant_option: false,
        },
        {
          action: 'grant',
          grantee: 'ALICE',
          grantee_kind: 'user',
          grantee_host: null,
          privileges: ['SELECT'],
          columns: [],
          grant_option: true,
        },
      ]);
    });

    it('renders Principal × Privilege matrix, adds grantee, previews SQL, and applies grant/revoke', async () => {
      const fetchMock = jest.fn(async (url) => {
        if (String(url).includes('/cdeadmin/api/security/object_grants/plan')) {
          return {
            ok: true,
            json: async () => ({
              preview_sql: 'GRANT SELECT ON "ASSETS" TO "REPORT_READER";',
            }),
          };
        }
        if (String(url).includes('/cdeadmin/api/security/object_grants/apply')) {
          return {
            ok: true,
            json: async () => ({applied: true, statement_count: 1}),
          };
        }
        return {
          ok: true,
          json: async () => ({
            supported: true,
            capabilities: {
              can_edit: true,
              supported_privileges: ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'REFERENCES'],
              supports_grant_option: true,
            },
            principals: [
              {name: 'SYSDBA', kind: 'user'},
              {name: 'REPORT_READER', kind: 'role'},
              {name: 'PUBLIC', kind: 'special'},
            ],
            grants: [
              {
                grantee: 'SYSDBA',
                grantee_kind: 'user',
                grantor: 'SYSDBA',
                privileges: {
                  SELECT: {granted: true, grant_option: true, columns: []},
                  INSERT: {granted: false, grant_option: false, columns: []},
                  UPDATE: {granted: false, grant_option: false, columns: []},
                  DELETE: {granted: false, grant_option: false, columns: []},
                  REFERENCES: {granted: false, grant_option: false, columns: []},
                },
              },
            ],
          }),
        };
      });
      global.fetch = fetchMock;

      render(
        <Theme>
          <ObjectPermissionsMatrix
            boundNodeData={{
              _type: 'cde_resource',
              cde_engine_id: 'firebird',
              cde_endpoint_id: 1,
              cde_database_target_id: 'fb-demo',
              cde_resource_id: 'table:ASSETS',
              cde_resource_kind: 'table',
              label: 'ASSETS',
            }}
          />
        </Theme>
      );

      await waitFor(() => {
        expect(screen.getByLabelText('SYSDBA SELECT')).toBeInTheDocument();
      });

      // Add REPORT_READER role as a new grantee
      const grantSelect = screen.getByLabelText('Grant Access To');
      fireEvent.mouseDown(grantSelect);
      fireEvent.click(await screen.findByRole('option', {name: /REPORT_READER/}));
      fireEvent.click(screen.getByText('+ Add Grantee'));

      await waitFor(() => {
        expect(screen.getByLabelText('REPORT_READER SELECT')).toBeChecked();
      });

      // Preview SQL
      fireEvent.click(screen.getByText('Preview SQL'));
      await waitFor(() => {
        expect(screen.getByText(/GRANT SELECT ON "ASSETS" TO "REPORT_READER";/)).toBeInTheDocument();
      });

      // Apply Permissions
      fireEvent.click(screen.getByText('Apply Permissions'));
      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          '/cdeadmin/api/security/object_grants/apply',
          expect.objectContaining({method: 'POST'})
        );
      });
    });

    it('renders graceful read-only banner when connected user lacks grant privilege', async () => {
      global.fetch = jest.fn(async () => ({
        ok: true,
        json: async () => ({
          supported: true,
          capabilities: {
            can_edit: false,
            reason: 'Connected user lacks GRANT OPTION on invoices.',
            supported_privileges: ['SELECT', 'INSERT'],
            supports_grant_option: true,
          },
          principals: [],
          grants: [
            {
              grantee: 'postgres',
              grantee_kind: 'role',
              grantor: 'postgres',
              privileges: {SELECT: {granted: true, grant_option: true, columns: []}},
            },
          ],
        }),
      }));

      render(
        <Theme>
          <ObjectPermissionsMatrix
            boundNodeData={{
              _type: 'table',
              cde_engine_id: 'postgresql',
              server_id: 4,
              label: 'invoices',
            }}
          />
        </Theme>
      );

      await waitFor(() => {
        expect(
          screen.getByText('Connected user lacks GRANT OPTION on invoices.')
        ).toBeInTheDocument();
      });
      expect(screen.queryByText('Apply Permissions')).not.toBeInTheDocument();
    });
  });

  describe('PrincipalSecurityManager (engines whose security descriptor is still a draft)', () => {
    it('loads MySQL accounts, opens the requested one and previews its redacted SQL', async () => {
      const fetchMock = jest.fn(async (url) => {
        if (String(url).includes('/cdeadmin/api/security/principal/plan')) {
          return {ok: true, json: async () => ({preview_sql: 'ALTER USER `app`@`%` ACCOUNT LOCK;'})};
        }
        return {
          ok: true,
          json: async () => ({
            engine: 'mysql',
            capabilities: {effective_user: 'root', can_manage_users: true, can_manage_roles: true},
            users: [
              {id: 'user:root@localhost', name: 'root', host: 'localhost', plugin: 'caching_sha2_password', locked: false},
              {id: 'user:app@%', name: 'app', host: '%', plugin: 'caching_sha2_password', locked: false,
                comment: 'API worker', member_of: []},
            ],
            roles: [],
          }),
        };
      });
      global.fetch = fetchMock;

      render(
        <Theme>
          <PrincipalSecurityManager
            instanceId="sec-my-srv"
            sid={1}
            engine="mysql"
            scope="server"
            initialKind="user"
            initialPrincipalId="user:app@%"
            endpointLabel="MySQL 9.7 on localhost"
            fetchImpl={fetchMock}
          />
        </Theme>
      );

      await waitFor(() => {
        expect(screen.getByDisplayValue('API worker')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Preview SQL'));
      await waitFor(() => {
        expect(screen.getByText('ALTER USER `app`@`%` ACCOUNT LOCK;')).toBeInTheDocument();
      });
    });
  });

  describe('BrowserComponent Standard TiB Sections (Zero Deprecated Segmented Pills)', () => {
    const mockPgAdmin = {
      Browser: {
        Nodes: {},
        tree: {
          itemData: () => null,
          hasParent: () => false,
        },
      },
    };

    it('replaces deprecated segmented pills with standard SEC-INSPECTOR and Time Window TiB sections and scopes SEC-SECURITY per engine', () => {
      // 1. Firebird Server -> Manage Server Users ONLY (Roles are database-scoped on Firebird)
      const fbServerCfg = buildNavigatorSelectionConfig(
        mockPgAdmin,
        'nav-1',
        'srv-fb',
        {
          _type: 'server',
          _id: 1,
          cde_engine_id: 'firebird',
          label: 'Firebird 5.0 on localhost',
          cde_context_actions: [],
        },
        'properties'
      );
      const allControlsFlat = fbServerCfg.ribbonTabs.flatMap((t) =>
        t.groups.flatMap((g) => g.controls)
      );
      // Zero deprecated segmented pill objects anywhere!
      expect(allControlsFlat.filter((c) => typeof c === 'object' && c?.type === 'segmented')).toEqual([]);

      const fbSrvPropsGroups = fbServerCfg.ribbonTabs.find((t) => t.label === 'Properties').groups;
      expect(fbSrvPropsGroups.find((g) => g.sectionId === 'SEC-INSPECTOR')).toBeDefined();
      const fbSrvSecGroup = fbSrvPropsGroups.find((g) => g.sectionId === 'SEC-SECURITY');
      expect(fbSrvSecGroup).toBeDefined();
      expect(fbSrvSecGroup.controls).toEqual(['data-navigator.sec_manage_users.nav_1']);

      // 2. Firebird Database -> Manage Database Roles + Object Permissions (NO server users on DB node)
      const fbDbCfg = buildNavigatorSelectionConfig(
        mockPgAdmin,
        'nav-1',
        'db-fb',
        {
          _type: 'cde_database_target',
          _id: 'fb-demo',
          cde_engine_id: 'firebird',
          cde_database_target_id: 'fb-demo',
          label: 'cdeadmin_demo.fdb',
          cde_context_actions: [],
        },
        'properties'
      );
      const fbDbPropsGroups = fbDbCfg.ribbonTabs.find((t) => t.label === 'Properties').groups;
      const fbDbSecGroup = fbDbPropsGroups.find((g) => g.sectionId === 'SEC-SECURITY');
      expect(fbDbSecGroup.controls).toEqual([
        'data-navigator.sec_manage_roles.nav_1',
        'data-navigator.sec_object_permissions.nav_1',
      ]);

      // 3. PostgreSQL Server -> Both Manage Users and Manage Roles at cluster scope
      const pgServerCfg = buildNavigatorSelectionConfig(
        mockPgAdmin,
        'nav-1',
        'srv-pg',
        {
          _type: 'server',
          _id: 4,
          cde_engine_id: 'postgresql',
          label: 'PostgreSQL 18 on localhost',
          cde_context_actions: [],
        },
        'dashboard'
      );
      const pgDashGroups = pgServerCfg.ribbonTabs.find((t) => t.label === 'Dashboard').groups;
      expect(pgDashGroups.find((g) => g.id === 'dashboard-time-window').controls).toHaveLength(5);
      const pgSecGroup = pgDashGroups.find((g) => g.sectionId === 'SEC-SECURITY');
      expect(pgSecGroup.controls).toEqual([
        'data-navigator.sec_manage_users.nav_1',
        'data-navigator.sec_manage_roles.nav_1',
      ]);

      // 4. SQLite Table -> Embedded file engine has NO SEC-SECURITY and NO Permissions filter button
      const sqliteTblCfg = buildNavigatorSelectionConfig(
        mockPgAdmin,
        'nav-1',
        'tbl-sq',
        {
          _type: 'cde_resource',
          cde_engine_id: 'sqlite',
          cde_resource_kind: 'table',
          cde_resource_id: 'table:items',
          label: 'items',
          cde_context_actions: [],
        },
        'properties'
      );
      const sqlitePropsGroups = sqliteTblCfg.ribbonTabs.find((t) => t.label === 'Properties').groups;
      expect(sqlitePropsGroups.find((g) => g.sectionId === 'SEC-SECURITY')).toBeUndefined();
      const sqliteInspectorControls = sqlitePropsGroups.find(
        (g) => g.sectionId === 'SEC-INSPECTOR'
      ).controls;
      expect(sqliteInspectorControls).not.toContain('data-navigator.props_sec_permissions.nav_1');
    });
  });
});
