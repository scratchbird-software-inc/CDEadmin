/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {Tree} from '../tree';
import * as pgadminUtils from '../../utils';

import { Directory, FileType } from 'react-aspen';
import { ManageTreeNodes } from '../tree_nodes';
import {
  Tree as CDETree,
  TreeModel as CDETreeModel,
} from 'sources/cdeadmin_ui/navigation/Tree';
import ContextMenu from 'sources/cdeadmin_ui/navigation/ContextMenu';
import {compareFirebirdNodes} from 'sources/cdeadmin_ui/navigation/firebirdTreeOrder';
import {
  descriptorFromTreeMetadata,
} from 'sources/cdeadmin_ui/navigation/TreeNode';
import {
  treeActionRegistry,
} from 'sources/cdeadmin_ui/navigation/TreeActions';
import { generateNodeUrl } from '../../../../browser/static/js/node_ajax';
import { copyToClipboard } from '../../clipboard';
import { usePgAdmin } from '../../PgAdminProvider';
import ObjectExplorerFilter from './ObjectExplorerFilter';
import usePreferences from '../../../../preferences/static/js/store';
import gettext from 'sources/gettext';
import {
  isProviderContextNode,
  providerTreeContextActions,
} from 'pgbrowser/ProviderContextMenu';

function postTreeReady(b) {
  const draggableTypes = [
    'collation domain domain_constraints fts_configuration fts_dictionary fts_parser fts_template synonym table partition type sequence package view mview foreign_table edbvar',
    'schema column database cast event_trigger extension language foreign_data_wrapper foreign_server user_mapping compound_trigger index index_constraint primary_key unique_constraint check_constraint exclusion_constraint foreign_key rule publication subscription',
    'trigger trigger_function',
    'edbfunc function edbproc procedure',
    'coll-column'
  ];
  const getQualifiedName = (data, item)=>{
    if(draggableTypes[0].includes(data._type)) {
      return pgadminUtils.fully_qualify(b, data, item);
    } else if(draggableTypes[1].includes(data._type)) {
      return pgadminUtils.quote_ident(data._label);
    } else if(draggableTypes[3].includes(data._type)) {
      let newData = {...data};
      let parsedFunc = pgadminUtils.parseFuncParams(newData._label);
      newData._label = parsedFunc.func_name;
      return pgadminUtils.fully_qualify(b, newData, item);
    } else {
      return data._label;
    }
  };

  b.tree.registerDraggableType({
    [draggableTypes[0]] : (data, item, treeNodeInfo)=>{
      let text = getQualifiedName(data, item);
      return {
        text: text,
        objUrl: generateNodeUrl.call(b.Nodes[data._type], treeNodeInfo, 'properties', data, true),
        nodeType: data._type,
        cur: {
          from: text.length,
          to: text.length,
        },
      };
    },
    [draggableTypes[1]] : (data)=>{
      return getQualifiedName(data);
    },
    [draggableTypes[2]] : (data)=>{
      return getQualifiedName(data);
    },
    [draggableTypes[3]] : (data, item)=>{
      let parsedFunc = pgadminUtils.parseFuncParams(data._label),
        dropVal = getQualifiedName(data, item),
        curPos = {from: 0, to: 0};

      if(parsedFunc.params.length > 0) {
        dropVal = dropVal + '(';
        curPos.from =  dropVal.length;
        dropVal = dropVal + parsedFunc.params[0][0];
        curPos.to = dropVal.length;

        for(let i=1; i<parsedFunc.params.length; i++) {
          dropVal = dropVal + ', ' + parsedFunc.params[i][0];
        }

        dropVal = dropVal + ')';
      } else {
        dropVal = dropVal + '()';
        curPos.from = curPos.to = dropVal.length;
      }

      return {
        text: dropVal,
        cur: curPos,
      };
    },
    [draggableTypes[4]] : (_data, item)=>{
      return item?.children?.map((ci)=>{
        return getQualifiedName(ci._metadata.data);
      }).join(', ') ?? '';
    }
  });

  b.tree.onNodeCopy((data, item)=>{
    copyToClipboard(getQualifiedName(data, item));
  });
}

export default function ObjectExplorer() {
  const [contextPos, setContextPos] = React.useState(null);
  const [contextNode, setContextNode] = React.useState(null);
  const [contextItem, setContextItem] = React.useState(null);
  const [, setLocaleRev] = useState(0);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const onLang = (ev) => setLocaleRev((prev) => ev?.detail?.revision ?? prev + 1);
    window.addEventListener('scratchrobin:language-changed', onLang);
    return () => window.removeEventListener('scratchrobin:language-changed', onLang);
  }, []);
  const pgAdmin = usePgAdmin();
  const engineTypePrefs = usePreferences().getPreferencesForModule('NODE-engine_type');
  const contextMenuItems = pgAdmin.Browser.BrowserContextMenu;
  const [treeModelLoaded, setTreeModelLoaded] = useState(false);
  const treeModelXRef = useRef();
  const treeHandleRef = useRef(null);
  const MOUNT_POINT = '/browser';
  const mtree = useMemo(()=>new ManageTreeNodes(), []);

  const expandRootServerGroups = React.useCallback(async (handle = treeHandleRef.current) => {
    const root = treeModelXRef.current?.root;
    if (!root || typeof handle?.openDirectory !== 'function') return;
    try {
      await root.ensureLoaded();
      const children = Array.isArray(root.children) ? [...root.children] : [];
      for (const group of children) {
        if (group && group.type === FileType.Directory && !group.isExpanded) {
          await handle.openDirectory(group);
        }
      }
    } catch {
      // Ignore transient load/expand race during unmount or refresh.
    }
  }, []);

  const showEmptyEnginesBanner = useMemo(() => {
    if (!engineTypePrefs || typeof engineTypePrefs !== 'object') return false;
    const keys = Object.keys(engineTypePrefs).filter((k) => k.startsWith('show_connector_'));
    if (keys.length === 0) return false;
    return !keys.some((k) => Boolean(engineTypePrefs[k]));
  }, [engineTypePrefs]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const handleConnectorsChanged = async () => {
      if (mtree?.tempTree) {
        mtree.tempTree.children = [];
      }
      if (treeModelXRef.current?.root?.hardReloadChildren) {
        treeModelXRef.current.root.isExpanded = false;
        await treeModelXRef.current.root.hardReloadChildren();
        await expandRootServerGroups(treeHandleRef.current);
      }
    };
    window.addEventListener('scratchrobin:connectors-changed', handleConnectorsChanged);
    return () => window.removeEventListener('scratchrobin:connectors-changed', handleConnectorsChanged);
  }, [expandRootServerGroups, mtree]);

  useEffect(()=>{
    // Init Tree with the Tree Parent node '/browser'
    mtree.init(MOUNT_POINT);

    const host = {
      pathStyle: 'unix',
      getItems: async (path) => {
        return mtree.readNode(path);
      },
      sortComparator: (a, b) => {
        const firebirdOrder = compareFirebirdNodes(a, b);
        if (firebirdOrder !== null) return firebirdOrder;
        // No need to sort columns
        if (a._metadata && a._metadata.data._type == 'column') return 0;
        // Sort alphabetically
        if (a.constructor === b.constructor) {
          return pgAdmin.natural_sort(a.fileName, b.fileName);
        }
        let retval = 0;
        if (a.constructor === Directory) {
          retval = -1;
        } else if (b.constructor === Directory) {
          retval = 1;
        }
        return retval;
      },
    };

    treeModelXRef.current = new CDETreeModel(host, MOUNT_POINT);

    treeModelXRef.current.root.ensureLoaded().then(()=>{
      setTreeModelLoaded(true);
    });
  }, []);

  const itemHandle = function onReady(handler) {
    treeHandleRef.current = handler;
    pgAdmin.Browser.tree = new Tree(handler, mtree, pgAdmin.Browser);
    postTreeReady(pgAdmin.Browser);
    void expandRootServerGroups(handler);
  };
  // Create Node
  const create = async (parentPath, _data) => {
    try {
      const _node_path = parentPath + '/' + _data.id;
      return mtree.addNode(parentPath, _node_path, _data);
    } catch {
      return null; // or throw error as you see fit
    }
  };

  // Remove Node
  const remove = async (path, _removeOnlyChild) => {
    try {
      await mtree.removeNode(path, _removeOnlyChild);
      return true;
    } catch {
      return false; // or throw error as you see fit
    }
  };

  // Update Node
  const update = async (path, data) => {
    try {
      await mtree.updateNode(path, data);
      return true;
    } catch {
      return false; // or throw error as you see fit
    }
  };

  const onContextMenu = React.useCallback(async (ev, item)=>{
    ev.preventDefault();
    if(item) {
      await pgAdmin.Browser.tree.select(item);
      setContextNode(descriptorFromTreeMetadata(
        item._metadata?.data ?? {}, item.children?.length ?? 0
      ));
      setContextItem(item);
      setContextPos({x: ev.clientX, y: ev.clientY});
    }
  }, []);

  if(!treeModelLoaded) {
    return <span>Loading...</span>;
  }

  const contextMetadata = contextItem?._metadata?.data ?? {};
  const providerMenuItems = contextNode ? (
    isProviderContextNode(contextMetadata) ?
      providerTreeContextActions(contextMetadata, contextItem) :
      treeActionRegistry.resolve({
        node: contextNode,
        item: contextItem,
        tree: pgAdmin.Browser.tree,
      }, contextMenuItems)
  ) : [];

  return (
    <div style={{height: '100%', display: 'flex', flexDirection: 'column'}}>
      {showEmptyEnginesBanner && (
        <div
          data-cdeadmin-qa-key="object-explorer-empty-engines-banner"
          style={{
            margin: '4px 6px',
            padding: '8px 10px',
            borderRadius: 8,
            border: '1px solid var(--sr-accent, #28749e)',
            background: 'var(--sr-accent-subtle, rgba(40,116,158,0.10))',
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
            fontSize: '0.78rem',
          }}
        >
          <div style={{fontWeight: 600}}>
            {gettext('No database engines are enabled yet.')}
          </div>
          <button
            type="button"
            data-cdeadmin-qa-key="object-explorer-enable-engines"
            onClick={() => {
              if (typeof window !== 'undefined') {
                window.dispatchEvent(
                  new CustomEvent('scratchrobin:open-preferences', {
                    detail: {mode: 'global', sectionId: 'engines:connectors'},
                  })
                );
              }
            }}
            style={{
              alignSelf: 'flex-start',
              padding: '4px 10px',
              borderRadius: 6,
              border: '1px solid var(--sr-accent, #28749e)',
              background: 'var(--sr-accent, #28749e)',
              color: '#ffffff',
              fontWeight: 600,
              fontSize: '0.76rem',
              cursor: 'pointer',
            }}
          >
            {gettext('Enable Database Engines…')}
          </button>
        </div>
      )}
      <div style={{flex: 1, minHeight: 0}}>
        <CDETree
          ariaLabel={gettext('Database object explorer')}
          model={treeModelXRef.current}
          onReady={itemHandle}
          create={create} update={update} remove={remove}
          height={'100%'} disableCache={true} onContextMenu={onContextMenu}
          onScroll={()=>{
            contextPos && setContextPos(null);
          }}
        />
      </div>
      <ObjectExplorerFilter />
      <ContextMenu position={contextPos} onClose={()=>{
        setContextPos(null);
        setContextNode(null);
        setContextItem(null);
      }} menuItems={providerMenuItems} label="Object Context Menu" />
    </div>
  );
}
