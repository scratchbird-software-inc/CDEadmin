//////////////////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////////////////

import gettext from 'sources/gettext';
import pgAdmin from 'sources/pgadmin';

export function retrieveAncestorOfTypeServer(pgBrowser, item, errorAlertTitle) {
  let serverInformation = null;
  let treeItem = item || pgBrowser.tree.selected();
  let treeNode = pgBrowser.tree.findNodeByDomElement(treeItem);

  if (treeNode) {
    let nodeData;
    let databaseNode = treeNode.ancestorNode(
      (node) => {
        nodeData = node.getData();
        return (nodeData._type === 'database');
      }
    );

    let isServerNode = (node) => {
      nodeData = node.getData();
      return nodeData._type === 'server';
    };

    if (databaseNode !== null) {
      if (nodeData._label.indexOf('=') >= 0) {
        pgAdmin.Browser.notifier.alert(
          gettext(errorAlertTitle),
          gettext(
            'Databases with = symbols in the name cannot be backed up or restored using this utility.'
          )
        );
      } else if (databaseNode.anyParent(isServerNode))
        serverInformation = nodeData;
    } else  if (treeNode.anyFamilyMember(isServerNode))
      serverInformation = nodeData;
  }

  if (serverInformation === null) {
    pgAdmin.Browser.notifier.alert(
      gettext(errorAlertTitle),
      gettext('Please select server or child node from the object explorer.')
    );
  }

  return serverInformation;
}

export function retrieveAncestorOfTypeDatabase(pgBrowser, item, errorAlertTitle) {
  let databaseInfo = null;
  let treeItem = item || pgBrowser.tree.selected();
  let treeNode = pgBrowser.tree.findNodeByDomElement(treeItem);
  if (treeNode) {
    if(treeNode.getData()._type === 'database') {
      databaseInfo = treeNode.getData();
    } else {
      let nodeData = null;
      treeNode.ancestorNode(
        (node) => {
          nodeData = node.getData();
          if(nodeData._type === 'database') {
            databaseInfo = nodeData;
            return true;
          }
          return false;
        }
      );
    }
  }

  if (databaseInfo === null) {
    pgAdmin.Browser.notifier.alert(
      gettext(errorAlertTitle),
      gettext('Please select a database or its child node from the browser.')
    );
  }

  return databaseInfo;
}

const PG_DATABASE_TARGET = /^postgresql-database:(\d+)$/;

/**
 * The inherited node data a PostgreSQL provider-tree item stands for (the
 * M2 identity bridge, consumed client side since M6, 2026-11-11). A
 * provider database target becomes a `database` node keyed by its OID; a
 * provider resource becomes the legacy node its `cde_legacy_route` names
 * (schema, table, ...). Other items come back unchanged, so the inherited
 * tools (backup, restore, import/export, psql, maintenance) read the same
 * `_type`/`_id`/`_label` they read on the inherited tree.
 */
export function legacyNodeData(data) {
  if(!data || typeof data !== 'object') return data;
  if(data._type === 'cde_database_target') {
    const match = PG_DATABASE_TARGET.exec(String(data._id ?? ''));
    if(!match) return data;
    const label = data.cde_database ?? data.label ?? data._label;
    // The provider tree attaches to a database when it is browsed, so the
    // inherited Dashboard tab (activity with cancel and terminate, locks,
    // prepared transactions) treats it as connected; the dashboard routes
    // resolve the OID through the maintenance connection either way.
    return {...data, _type: 'database', _id: Number(match[1]), _label: label, label, connected: true,
      cde_bridged_from: 'cde_database_target'};
  }
  const route = data.cde_legacy_route;
  if(data._type === 'cde_resource' && route && typeof route.node_type === 'string' && route.oid != null) {
    const label = data.label ?? data._label;
    const parentId = route.tid ?? route.scid ?? route.did;
    return {...data, _type: route.node_type, _id: route.oid, _pid: parentId, _label: label, label,
      cde_bridged_from: 'cde_resource'};
  }
  return data;
}
