/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import { useEffect, useMemo } from 'react';
import PropTypes from 'prop-types';
import { Resizable } from 're-resizable';
// Import helpers from new file


import PgTreeView from '../../../../static/js/PgTreeView';
import {interfacePreferenceMatches} from '../../../../static/js/cdeadmin_ui/customization/InterfacePreferences';

export default function LeftTree({prefTreeData, selectedItem, setSelectedItem, filteredList,
  searchVal=''}) {
  const filteredTreeData = useMemo(() => {
    const parentIds = filteredList.map((item) => item.parentId);
    const filteredTreeData = prefTreeData.reduce((retVal, category) => {
      // Interface pages are editors without preference fields; they match on
      // their names and keywords.
      const filteredChildren = category.children.filter((child) => child.editor ?
        interfacePreferenceMatches(child, searchVal) : parentIds.includes(child.id));
      if( filteredChildren.length > 0) {
        retVal.push({
          ...category,
          children: filteredChildren,
        });
      }
      return retVal;
    }, []);
    return filteredTreeData;
  }, [prefTreeData, filteredList, searchVal]);

  useEffect(() => {
    // When the filtered list changes, select the first entry it shows,
    // unless the selected entry is still shown (a page opened on request).
    const shown = filteredTreeData.some((category) => category.children
      .some((child) => child.id === selectedItem?.id));
    if (filteredTreeData.length > 0 && !shown) {
      setSelectedItem(filteredTreeData[0]?.children[0] ?? null);
    }
  }, [filteredList.length, searchVal]);

  return (
    <Resizable className='PreferencesComponent-treeContainer'
      enable={{ top:false, right:true, bottom:false, left:false, topRight:false, bottomRight:false, bottomLeft:false, topLeft:false }}
      maxWidth='50%' minWidth='10%'
      defaultSize={{ width: '25%', height: '100%' }}
      id='treeContainer'
    >
      <PgTreeView
        idAccessor='id'
        data={filteredTreeData}
        openByDefault={true}
        disableMultiSelection={true}
        selection={selectedItem?.id}
        onFocus={(item) => {
          setSelectedItem(item.data);
        }}
        // don't need virtualization for preferences tree
        overscanCount={50}
      />
    </Resizable>
  );
}

LeftTree.propTypes = {
  prefTreeData: PropTypes.arrayOf(PropTypes.shape({
    id: PropTypes.string.isRequired,
    name: PropTypes.string.isRequired,
    key: PropTypes.string.isRequired,
    children: PropTypes.array.isRequired,
  })).isRequired,
  selectedItem: PropTypes.object,
  setSelectedItem: PropTypes.func.isRequired,
  filteredList: PropTypes.array,
  searchVal: PropTypes.string,
};
