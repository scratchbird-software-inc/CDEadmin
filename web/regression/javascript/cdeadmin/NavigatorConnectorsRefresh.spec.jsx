/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {act, render, waitFor} from '@testing-library/react';
import {ItemType} from 'react-aspen';
import getApiInstance from 'sources/api_instance';
import {FileTreeItem} from 'sources/components/PgTree/FileTreeItem';
import {PgAdminProvider} from 'sources/PgAdminProvider';
import pgAdmin from 'sources/pgadmin';
import ObjectExplorer from 'sources/tree/ObjectExplorer';
import {ManageTreeNodes} from 'sources/tree/tree_nodes';
import Theme from 'sources/Theme';

jest.mock('sources/url_for', () => ({
  __esModule: true,
  default: (endpoint) => (endpoint === 'browser.nodes' ? '/browser/nodes/' : `/${endpoint}`),
}));

jest.mock('sources/api_instance', () => {
  const fn = jest.fn();
  return {
    __esModule: true,
    default: fn,
    parseApiError: (err) => String(err?.message || err || ''),
  };
});

describe('Data Navigator Connectors live refresh on engine availability changes', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('stamps resolvedPathCache on direct children of /browser where parent.parent is null', () => {
    const groupData = {
      id: 'server_group_1',
      _id: 1,
      _type: 'server_group',
      _label: 'Connectors',
      label: 'Connectors',
      inode: true,
    };
    const groupItem = {
      id: 1,
      depth: 1,
      expanded: false,
      children: [],
      parent: {parent: null, path: '/browser', children: []},
      _metadata: {data: groupData},
      getMetadata: () => groupData,
    };
    groupItem.parent.children.push(groupItem);

    render(
      <FileTreeItem
        item={groupItem}
        itemType={ItemType.Directory}
        decorations={{
          classlist: [],
          addChangeListener: jest.fn(),
          removeChangeListener: jest.fn(),
        }}
        onClick={jest.fn()}
        onDoubleClick={jest.fn()}
        onContextMenu={jest.fn()}
        onMouseEnter={jest.fn()}
        onMouseLeave={jest.fn()}
        changeDirectoryCount={jest.fn()}
        events={{dispatch: jest.fn()}}
      />
    );

    expect(groupItem.resolvedPathCache).toBe('/browser/server_group_1');
  });

  it('resolves root server_group in ManageTreeNodes by both canonical id path and display label path', async () => {
    const mtree = new ManageTreeNodes();
    await mtree.init('/browser');
    await mtree.addNode('/browser', '/browser/server_group_1', {
      id: 'server_group_1',
      _id: 1,
      _type: 'server_group',
      label: 'Connectors',
      inode: true,
    });

    const byId = mtree.findNode('/browser/server_group_1');
    const byLabel = mtree.findNode('/browser/Connectors');
    expect(byId).not.toBeNull();
    expect(byLabel).toBe(byId);
  });

  it('reloads and expands Connectors across repeated scratchrobin:connectors-changed updates', async () => {
    let activeEngines = ['postgresql', 'firebird', 'sqlite'];

    const apiGet = jest.fn(async (url) => {
      if (String(url).includes('server_group/children/1')) {
        return {
          data: {
            data: activeEngines.map((eid) => ({
              id: `engine_type_${eid}`,
              _id: eid,
              _pid: 1,
              _type: 'engine_type',
              label: eid.toUpperCase(),
              inode: true,
              engine_id: eid,
              icon_key: `engine.${eid}`,
            })),
          },
        };
      }
      return {
        data: {
          data: [
            {
              id: 'server_group_1',
              _id: 1,
              _pid: null,
              _type: 'server_group',
              label: 'Connectors',
              inode: true,
              children_url: '/browser/server_group/children/1',
            },
          ],
        },
      };
    });
    getApiInstance.mockReturnValue({get: apiGet, put: jest.fn().mockResolvedValue({data: {}}), post: jest.fn()});

    pgAdmin.Browser = pgAdmin.Browser || {};
    pgAdmin.Browser.URL = '/browser/';
    pgAdmin.Browser.Nodes = pgAdmin.Browser.Nodes || {
      server_group: {type: 'server_group', hasId: true, callbacks: {}},
      engine_type: {type: 'engine_type', hasId: false, callbacks: {}},
    };
    pgAdmin.Browser.Events = pgAdmin.Browser.Events || {
      on: jest.fn(() => jest.fn()),
      off: jest.fn(),
      trigger: jest.fn(),
    };
    pgAdmin.Browser.BrowserContextMenu = [];
    pgAdmin.natural_sort = (a, b) => String(a).localeCompare(String(b));

    render(
      <Theme>
        <PgAdminProvider value={pgAdmin}>
          <div style={{width: 320, height: 480}}>
            <ObjectExplorer />
          </div>
        </PgAdminProvider>
      </Theme>
    );

    await waitFor(() => {
      const root = pgAdmin.Browser.tree?.tree?.getModel?.()?.root;
      expect(root?.isExpanded).toBe(true);
      const group = root?.children?.[0];
      expect(group?.children?.map((c) => c._metadata.data._id).sort()).toEqual([
        'firebird',
        'postgresql',
        'sqlite',
      ]);
    });

    // Turn all engines off -> Connectors cleanly empties without breaking root
    activeEngines = [];
    await act(async () => {
      window.dispatchEvent(
        new CustomEvent('scratchrobin:connectors-changed', {
          detail: {enabled_engines: []},
        })
      );
    });

    await waitFor(() => {
      const root = pgAdmin.Browser.tree.tree.getModel().root;
      expect(root.isExpanded).toBe(true);
      const group = root.children[0];
      expect(group.children.length).toBe(0);
    });

    // Turn 6 engines back on -> Connectors reloads and expands with all 6!
    activeEngines = ['postgresql', 'firebird', 'mysql', 'mariadb', 'sqlite', 'duckdb'];
    await act(async () => {
      window.dispatchEvent(
        new CustomEvent('scratchrobin:connectors-changed', {
          detail: {enabled_engines: activeEngines},
        })
      );
    });

    await waitFor(() => {
      const root = pgAdmin.Browser.tree.tree.getModel().root;
      expect(root.isExpanded).toBe(true);
      const group = root.children[0];
      expect(group.isExpanded).toBe(true);
      expect(group.children.map((c) => c._metadata.data._id).sort()).toEqual([
        'duckdb',
        'firebird',
        'mariadb',
        'mysql',
        'postgresql',
        'sqlite',
      ]);
    });
  });
});
