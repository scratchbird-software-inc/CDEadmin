/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import PropTypes from 'prop-types';
import {Box} from '../../primitives/Layout';
import {Tab} from '../../navigation/TabsAndBreadcrumbs';

/**
 * A tab strip with the keyboard model of the ARIA tabs pattern: only the
 * selected tab is in the tab order and the arrow keys, Home and End move the
 * selection (and the focus) between tabs. `extra` is rendered after the tabs.
 */
export default function PanelTabs({label, ids, labelOf, active, onChange, extra}) {
  const onKeyDown = (event) => {
    const index = ids.indexOf(active);
    let next = null;
    if(event.key === 'ArrowRight') next = (index + 1) % ids.length;
    else if(event.key === 'ArrowLeft') next = (index - 1 + ids.length) % ids.length;
    else if(event.key === 'Home') next = 0;
    else if(event.key === 'End') next = ids.length - 1;
    if(next === null || !ids.length) return;
    event.preventDefault();
    const list = event.currentTarget;
    onChange(ids[next]);
    setTimeout(() => list.querySelector('[role="tab"][aria-selected="true"]')?.focus(), 0);
  };
  return <Box role="tablist" aria-label={label} onKeyDown={onKeyDown}
    sx={{display: 'flex', alignItems: 'center', flexWrap: 'wrap', borderBottom: '1px solid', borderColor: 'divider'}}>
    {ids.map((id) => <Tab key={id} label={labelOf(id)} active={active === id} onActivate={() => onChange(id)} />)}
    {extra}
  </Box>;
}

PanelTabs.propTypes = {
  label: PropTypes.string.isRequired,
  ids: PropTypes.array.isRequired,
  labelOf: PropTypes.func.isRequired,
  active: PropTypes.string.isRequired,
  onChange: PropTypes.func.isRequired,
  extra: PropTypes.node,
};
