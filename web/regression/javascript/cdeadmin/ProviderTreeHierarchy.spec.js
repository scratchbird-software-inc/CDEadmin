/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import getApiInstance from 'sources/api_instance';
import pgAdmin from 'sources/pgadmin';
import {ManageTreeNodes} from 'sources/tree/tree_nodes';

jest.mock('sources/api_instance');

describe('CDEadmin provider tree hierarchy', () => {
  it('loads retained databases from the endpoint-owned child URL', async () => {
    const get = jest.fn().mockResolvedValue({data: {data: [{
      id: 'cde_database_target_example',
      _id: 'database-target-id',
      _pid: 7,
      _type: 'cde_database_target',
      label: 'cdeadmin_demo.fdb',
      inode: true,
      children_url: '/browser/server/cde_workspace/1/7?navigator=token',
    }]}});
    getApiInstance.mockReturnValue({get});
    const nodes = new ManageTreeNodes();
    await nodes.addNode(null, '/browser/server-7', {
      id: 'server-7',
      _id: 7,
      _pid: 1,
      _type: 'server',
      label: 'localhost',
      inode: true,
      cde_endpoint: true,
      children_url: '/browser/server/children/1/7',
    });

    const children = await nodes.readNode('/browser/server-7');

    expect(get).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledWith(
      '/browser/server/children/1/7', {timeout: 30000},
    );
    expect(children).toHaveLength(1);
    expect(children[0].metadata.data).toMatchObject({
      _type: 'cde_database_target',
      label: 'cdeadmin_demo.fdb',
    });
  });

  it('returns already-loaded directory children without another request', async () => {
    const get = jest.fn();
    getApiInstance.mockReturnValue({get});
    const nodes = new ManageTreeNodes();
    await nodes.addNode(null, '/browser/firebird', {
      id: 'firebird', _id: 'firebird', _pid: null,
      _type: 'engine_type', label: 'Firebird', inode: true,
    });
    await nodes.addNode('/browser/firebird', '/browser/firebird/localhost', {
      id: 'localhost', _id: 7, _pid: 1,
      _type: 'server', label: 'localhost', inode: true,
    });

    const children = await nodes.readNode('/browser/firebird');

    expect(children).toHaveLength(1);
    expect(get).not.toHaveBeenCalled();
  });

  it('loads databases without the connector folder in the route', async () => {
    const get = jest.fn().mockResolvedValue({data: {data: [{
      id: 'database_16384',
      _id: 16384,
      _pid: 2,
      _type: 'database',
      label: 'cdeadmin',
      inode: true,
    }]}});
    getApiInstance.mockReturnValue({get});
    const previousUrl = pgAdmin.Browser.URL;
    pgAdmin.Browser.URL = '/browser/';
    const nodes = new ManageTreeNodes();
    await nodes.addNode(null, '/browser/server_group_2', {
      id: 'server_group_2', _id: 2, _pid: null,
      _type: 'server_group', label: 'Connectors', inode: true,
    });
    await nodes.addNode(
      '/browser/server_group_2',
      '/browser/server_group_2/engine_type_postgresql',
      {
        id: 'engine_type_postgresql', _id: 'postgresql', _pid: 2,
        _type: 'engine_type', label: 'PostgreSQL', inode: true,
      }
    );
    await nodes.addNode(
      '/browser/server_group_2/engine_type_postgresql',
      '/browser/server_group_2/engine_type_postgresql/server_2',
      {
        id: 'server_2', _id: 2, _pid: 'engine_type_postgresql',
        _type: 'server', label: 'localhost', inode: true, connected: true,
      }
    );
    const databasesPath = '/browser/server_group_2/engine_type_postgresql/server_2/coll-database_2';
    await nodes.addNode(
      '/browser/server_group_2/engine_type_postgresql/server_2',
      databasesPath,
      {
        id: 'coll-database_2', _id: 2, _pid: 2,
        _type: 'coll-database', label: 'Databases', inode: true,
      }
    );

    const children = await nodes.readNode(databasesPath);
    pgAdmin.Browser.URL = previousUrl;

    expect(get).toHaveBeenCalledWith(
      '/browser/database/nodes/2/2/', {timeout: 30000},
    );
    expect(children[0].metadata.data.label).toBe('cdeadmin');
  });
});
