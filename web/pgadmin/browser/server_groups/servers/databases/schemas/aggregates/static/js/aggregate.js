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
import AggregateSchema from './aggregate.ui';

define('pgadmin.node.aggregate', [
  'sources/gettext', 'sources/pgadmin', 'pgadmin.browser',
  'pgadmin.node.schema.dir/child', 'pgadmin.browser.collection',
], function(gettext, pgAdmin, pgBrowser, schemaChild) {

  if (!pgBrowser.Nodes['coll-aggregate']) {
    pgAdmin.Browser.Nodes['coll-aggregate'] =
      pgAdmin.Browser.Collection.extend({
        node: 'aggregate',
        label: gettext('Aggregates'),
        type: 'coll-aggregate',
        columns: ['name', 'owner', 'description'],
        canDrop: false,
        canDropCascade: false,
      });
  }

  if (!pgBrowser.Nodes['aggregate']) {
    pgAdmin.Browser.Nodes['aggregate'] = schemaChild.SchemaChildNode.extend({
      type: 'aggregate',
      sqlAlterHelp: 'sql-alteraggregate.html',
      sqlCreateHelp: 'sql-createaggregate.html',
      label: gettext('Aggregate'),
      collection_type: 'coll-aggregate',
      hasSQL: true,
      hasDepends: false,
      canDrop: false,
      canDropCascade: false,
      Init: function() {
        /* Avoid mulitple registration of menus */
        if (this.initialized)
          return;

        this.initialized = true;
        pgBrowser.add_menus(['aggregate', 'coll-aggregate'].map(node => ({
          name: 'postgresql_aggregate_administration_' + node, node, module: this,
          applies: ['object', 'context'], callback: 'open_native_administration', priority: 12,
          label: gettext('Native aggregate administration...'),
          enable: (data, item) => Boolean(postgresqlAdministrationContext(
            pgBrowser.tree, item || pgBrowser.tree.selected(), 'aggregate')),
        })));
      },
      callbacks: {
        open_native_administration: function(args) {
          const selected = postgresqlAdministrationContext(pgBrowser.tree,
            args?.item || pgBrowser.tree.selected(), 'aggregate');
          if (!selected) return false;
          showProviderWorkspace(gettext('PostgreSQL aggregate administration'),
            pgBrowser.Nodes.server, selected.server, selected.serverItem,
            'administration', selected.context);
          return false;
        },
      },
      getSchema: ()=>{
        return new AggregateSchema();
      }
    });
  }
  return pgBrowser.Nodes['aggregate'];
});
