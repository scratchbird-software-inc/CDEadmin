/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useMemo, useState, useEffect} from 'react';
import PropTypes from 'prop-types';
import {ScratchBranchedTree} from 'sources/cdeadmin_ui/navigation/ScratchBranchedTree';

function normalizeCheckNodes(nodes = []) {
  return (nodes || []).map((node) => ({
    id: String(node.value ?? node.id ?? node.label ?? ''),
    label: node.label ?? String(node.value ?? node.id ?? ''),
    disabled: Boolean(node.disabled),
    children: Array.isArray(node.children) && node.children.length > 0
      ? normalizeCheckNodes(node.children)
      : undefined,
  }));
}

export default function CheckBoxTree({treeData = [], getSelectedServers}) {
  const [checkedIds, setCheckedIds] = useState([]);
  const normalizedNodes = useMemo(() => normalizeCheckNodes(treeData), [treeData]);

  useEffect(() => {
    if (getSelectedServers) {
      getSelectedServers(checkedIds);
    }
  }, [checkedIds, getSelectedServers]);

  return (
    <div style={{height: '100%', minHeight: 160, display: 'flex', flexDirection: 'column'}}>
      <ScratchBranchedTree
        nodes={normalizedNodes}
        checkable
        checkedIds={checkedIds}
        onCheckChange={setCheckedIds}
        defaultExpandAll
        ariaLabel="Server selection tree"
        qaKey="checkbox-branched-tree"
        style={{flex: 1, minHeight: 0}}
      />
    </div>
  );
}

CheckBoxTree.propTypes = {
  treeData: PropTypes.array,
  getSelectedServers: PropTypes.func,
};
