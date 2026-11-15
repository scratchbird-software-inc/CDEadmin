/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import gettext from 'sources/gettext';

export default class Preferences {
  static instance;

  static getInstance(...args) {
    if (!Preferences.instance) {
      Preferences.instance = new Preferences(...args);
    }
    return Preferences.instance;
  }

  constructor(pgAdmin, pgBrowser) {
    this.pgAdmin = pgAdmin;
    this.pgBrowser = pgBrowser;
  }

  init() {
    if (this.initialized)
      return;
    this.initialized = true;
    // Add Preferences in to file menu
    let menus = [{
      name: 'mnu_preferences',
      module: this,
      applies: ['file'],
      callback: 'show',
      enable: true,
      priority: 3,
      label: gettext('Preferences'),
    }];

    this.pgBrowser.add_menus(menus);
  }

  // Open Personal User Preferences via ProjectShell.
  show() {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('scratchrobin:open-preferences', {
          detail: {mode: 'user'},
        })
      );
    }
  }
}
