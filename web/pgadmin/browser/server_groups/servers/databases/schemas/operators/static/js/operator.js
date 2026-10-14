/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {postgresqlAdministrationContext} from 'sources/cdeadmin_ui/navigation/postgresqlAdministration';
import {showProviderWorkspace} from 'sources/Dialogs';
import OperatorSchema from './operator.ui';

define('pgadmin.node.operator', [
  'sources/gettext',
  'sources/pgadmin', 'pgadmin.browser',
  'pgadmin.node.schema.dir/child', 'pgadmin.browser.collection',
], function(gettext, pgAdmin, pgBrowser, schemaChild) {

  if (!pgBrowser.Nodes['coll-operator']) {
    pgAdmin.Browser.Nodes['coll-operator'] =
      pgAdmin.Browser.Collection.extend({
        node: 'operator',
        label: gettext('Operators'),
        type: 'coll-operator',
        columns: ['name', 'owner', 'description'],
        canDrop: false,
        canDropCascade: false,
        canSelect: false
      });
  }

  if (!pgBrowser.Nodes['operator']) {
    pgAdmin.Browser.Nodes['operator'] = schemaChild.SchemaChildNode.extend({
      type: 'operator',
      sqlAlterHelp: 'sql-alteroperator.html',
      sqlCreateHelp: 'sql-createoperator.html',
      label: gettext('Operator'),
      collection_type: 'coll-operator',
      hasSQL: true,
      hasDepends: false,
      canDrop: false,
      canDropCascade: false,
      Init: function() {
        /* Avoid mulitple registration of menus */
        if (this.initialized)
          return;

        this.initialized = true;
        pgBrowser.add_menus(['operator', 'coll-operator'].map(node => ({
          name: 'postgresql_operator_administration_' + node, node, module: this,
          applies: ['object', 'context'], callback: 'open_native_administration', priority: 12,
          label: gettext('Native operator administration...'),
          enable: (data, item) => Boolean(postgresqlAdministrationContext(
            pgBrowser.tree, item || pgBrowser.tree.selected(), 'operator')),
        })));
      },
      callbacks: {
        open_native_administration: function(args) {
          const selected = postgresqlAdministrationContext(pgBrowser.tree,
            args?.item || pgBrowser.tree.selected(), 'operator');
          if (!selected) return false;
          showProviderWorkspace(gettext('PostgreSQL operator administration'),
            pgBrowser.Nodes.server, selected.server, selected.serverItem,
            'administration', selected.context);
          return false;
        },
      },
      getSchema: ()=>{
        return new OperatorSchema();
      }
    });
  }
  return pgBrowser.Nodes['operator'];
});
