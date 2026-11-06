/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// Owner direction 2026-11-06: PostgreSQL's View/Edit Data became Browse data,
// one top-level entry that opens the Query Tool holding the relation's SELECT.

import pgAdmin from 'sources/pgadmin';
import pgBrowser from 'pgadmin.browser';

// The browser module is an AMD bundle entry; the menu code needs only these.
jest.mock('pgadmin.browser', () => ({__esModule: true,
  default: {add_menus: () => {}, add_menu_category: () => {}, tree: null}}));
jest.mock('pgadmin.tools.user_management', () => ({}), {virtual: true});
jest.mock('pgadmin.tools.file_manager', () => ({}), {virtual: true});
jest.mock('../../../pgadmin/tools/sqleditor/static/js/components/QueryToolComponent', () => () => null);
import SQLEditor from '../../../pgadmin/tools/sqleditor/static/js/SQLEditorModule';
import {browseDataUrl} from '../../../pgadmin/tools/sqleditor/static/js/show_view_data';

function treeWith(nodeData, hierarchy) {
  return {
    findNodeByDomElement: jest.fn(() => nodeData ? {getData: () => nodeData} : undefined),
    getTreeNodeHierarchy: jest.fn(() => hierarchy),
    selected: jest.fn(() => 'selected-item'),
  };
}

const HIERARCHY = {
  server_group: {_id: 1}, server: {_id: 3}, database: {_id: 5}, schema: {_id: 2200},
};

describe('Browse data for PostgreSQL', () => {
  beforeEach(() => {
    pgAdmin.Browser = pgAdmin.Browser || {};
    pgAdmin.Browser.notifier = {alert: jest.fn()};
  });

  it('asks the server for the SELECT of the selected relation by OID', () => {
    for (const type of ['table', 'partition', 'view', 'mview', 'foreign_table', 'catalog_object']) {
      const browser = {tree: treeWith({_type: type, _id: 16384}, HIERARCHY)};
      expect(browseDataUrl(browser, 'item')).toBe('/sqleditor/browse_data_sql/3/5/16384');
    }
    const catalog = {tree: treeWith({_type: 'catalog_object', _id: 1259},
      {...HIERARCHY, schema: undefined, catalog: {_id: 11}})};
    expect(browseDataUrl(catalog, 'item')).toBe('/sqleditor/browse_data_sql/3/5/1259');
  });

  it('offers nothing outside a relation in a connected database', () => {
    expect(browseDataUrl({tree: treeWith({_type: 'schema', _id: 2200}, HIERARCHY)}, 'item')).toBeNull();
    expect(browseDataUrl({tree: treeWith({_type: 'table', _id: 1}, {...HIERARCHY, database: undefined})}, 'item'))
      .toBeNull();
    expect(browseDataUrl({tree: treeWith({_type: 'table', _id: 1}, {...HIERARCHY, schema: undefined})}, 'item'))
      .toBeNull();
    expect(pgAdmin.Browser.notifier.alert).not.toHaveBeenCalled();
    expect(browseDataUrl({tree: treeWith(undefined, HIERARCHY)}, 'item')).toBeNull();
    expect(pgAdmin.Browser.notifier.alert).toHaveBeenCalledWith('Browse data', 'No object selected.');
  });

  describe('menu', () => {
    let addMenus, addCategory, editor;
    beforeEach(() => {
      addMenus = jest.spyOn(pgBrowser, 'add_menus').mockImplementation(() => {});
      addCategory = jest.fn();
      pgBrowser.add_menu_category = addCategory;
      SQLEditor.instance = undefined;
      editor = SQLEditor.getInstance();
      editor.init();
    });
    afterEach(() => {
      addMenus.mockRestore();
      SQLEditor.instance = undefined;
    });

    it('registers one top-level Browse data entry per relation node and no View/Edit Data', () => {
      const menus = addMenus.mock.calls.flatMap(([items]) => items);
      const browse = menus.filter((menu) => menu.label === 'Browse data');
      expect(browse.map((menu) => menu.node)).toEqual(editor.SUPPORTED_NODES);
      for (const menu of browse) {
        expect(menu.name).toBe('browse_data_context_' + menu.node);
        expect(menu.category).toBeUndefined();
        expect(menu.callback).toBe('showBrowseData');
        expect(menu.applies).toEqual(['context', 'object']);
        expect(menu.shortcut_preference).toEqual(['browser', 'sub_menu_view_data']);
      }
      const retired = ['All Rows', 'First 100 Rows', 'Last 100 Rows', 'Filtered Rows...'];
      expect(menus.some((menu) => menu.category === 'view_data' || retired.includes(menu.label))).toBe(false);
      expect(addCategory).not.toHaveBeenCalledWith(expect.objectContaining({name: 'view_data'}));
    });

    it('opens the Query Tool with the SELECT URL, which the Query Tool loads without running it', () => {
      const tree = treeWith({_type: 'table', _id: 16384}, HIERARCHY);
      pgBrowser.tree = tree;
      const open = jest.spyOn(editor, 'showQueryTool').mockImplementation(() => true);
      expect(editor.showBrowseData({}, 'item')).toBe(true);
      expect(open).toHaveBeenCalledWith('/sqleditor/browse_data_sql/3/5/16384', 'item');
      open.mockClear();
      pgBrowser.tree = treeWith({_type: 'schema', _id: 2200}, HIERARCHY);
      expect(editor.showBrowseData({}, 'item')).toBe(false);
      expect(open).not.toHaveBeenCalled();
    });
  });
});
