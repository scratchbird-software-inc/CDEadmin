/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// The tabbed command bar, shown instead of the menu bar when View >
// Appearance and Accessibility > Command bar is "Tabbed bar". It shows the
// same main menus, runs commands through the same menu callbacks, and takes
// its look from the appearance settings.

import {useEffect, useMemo, useReducer, useRef} from 'react';
import gettext from 'sources/gettext';
import {NotebookBar} from './scratch_notebookbar';
import {Icon, inferActionIconKey} from 'sources/cdeadmin_ui/icons';
import {buildCommandBarModel} from './cdeadmin_ui/shell/commandBarModel';
import {
  COMMAND_BAR_MESSAGES, COMMAND_BAR_THEME, readCommandBarCustomization,
} from './cdeadmin_ui/shell/commandBarSettings';
import usePreferences from '../../preferences/static/js/store';
import {usePgAdmin} from './PgAdminProvider';
import {AppUserMenu} from './AppMenuBar';

export function commandIcon(item) {
  return <Icon iconKey={item.iconKey || inferActionIconKey(item) ||
    'command.default'} decorative size="100%" />;
}

export default function AppNotebookBar() {
  const pgAdmin = usePgAdmin();
  const ref = useRef(null);
  const [revision, refresh] = useReducer((value) => value + 1, 0);
  const preferenceVersion = usePreferences((state) => state.version);

  useEffect(() => {
    const events = pgAdmin.Browser.Events;
    const update = () => refresh();
    events?.on('pgadmin:enable-disable-menu-items', update);
    events?.on('pgadmin:refresh-app-menu', update);
    return () => {
      events?.off?.('pgadmin:enable-disable-menu-items', update);
      events?.off?.('pgadmin:refresh-app-menu', update);
    };
  }, []);

  // The workbench below sizes itself from the bar's actual height.
  useEffect(() => {
    const element = ref.current;
    if(!element || typeof ResizeObserver === 'undefined') return undefined;
    const update = () => document.documentElement.style.setProperty(
      '--cde-actual-menu-height', `${element.getBoundingClientRect().height}px`);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => {
      observer.disconnect();
      document.documentElement.style.removeProperty('--cde-actual-menu-height');
    };
  }, []);

  const bar = useMemo(() => buildCommandBarModel(
    pgAdmin.Browser.MainMenus ?? [], commandIcon), [revision, preferenceVersion,
    pgAdmin.Browser.MainMenus]);
  const customization = useMemo(() =>
    readCommandBarCustomization(usePreferences.getState()), [preferenceVersion]);

  return <div ref={ref} style={COMMAND_BAR_THEME} data-test="app-command-bar">
    <NotebookBar model={bar.model} state={bar.state} catalog={bar.catalog}
      customization={customization} label={gettext('Commands')}
      messages={COMMAND_BAR_MESSAGES}
      onCommand={(command, detail) => {
        bar.run(command, detail);
        refresh();
      }}
      start={<span data-cdeadmin-qa-key='application.brand.scratchrobin'
        aria-label='ScratchRobin CDE Administrator'
        style={{display: 'inline-flex', alignItems: 'center', gap: 6,
          fontWeight: 700, whiteSpace: 'nowrap'}}>
        <span style={{width: '1.4em', height: '1.4em', display: 'inline-flex'}}>
          <Icon iconKey='tool.scratchrobin' decorative size="100%" />
        </span>
        <span>ScratchRobin</span>
      </span>}
      end={<AppUserMenu />} />
  </div>;
}
