/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// The interface pages of Preferences (owner direction 2026-11-05: the
// interface designer is part of Preferences). Two categories join the
// Preferences tree: Appearance and accessibility, and Interface designer.
// Their pages are editors rather than lists of preference fields; each has
// its own Apply or Save, while the Preferences Save keeps saving the
// ordinary settings.

import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {APPEARANCE_SECTIONS} from './appearance';
import {AppearanceSectionEditor} from './AppearancePreferences';
import {
  ArtworkEditor, CommandBarEditor, MenusEditor, ProfilesEditor,
} from './DesignerPreferences';

export const APPEARANCE_PREFERENCES_ID = 'cde-appearance';
export const DESIGNER_PREFERENCES_ID = 'cde-designer';
export const PREFERENCES_SECTION_EVENT = 'cdeadmin:preferences-section';

/** Tree categories, in the shape the Preferences tree uses. */
export function interfacePreferenceCategories() {
  return [
    {id: APPEARANCE_PREFERENCES_ID, name: gettext('Appearance and accessibility'),
      key: APPEARANCE_PREFERENCES_ID,
      children: APPEARANCE_SECTIONS.map((section) => ({
        id: `${APPEARANCE_PREFERENCES_ID}-${section.id}`, name: section.label,
        key: section.id, editor: 'appearance', section: section.id,
        keywords: `${section.keywords || ''} ${section.fields.map(
          (field) => field.label).join(' ')}`,
      }))},
    {id: DESIGNER_PREFERENCES_ID, name: gettext('Interface designer'),
      key: DESIGNER_PREFERENCES_ID,
      children: [
        {id: `${DESIGNER_PREFERENCES_ID}-artwork`, name: gettext('Artwork and icons'),
          key: 'artwork', editor: 'artwork',
          keywords: gettext('icon artwork assignment catalog')},
        {id: `${DESIGNER_PREFERENCES_ID}-menus`, name: gettext('Menus and commands'),
          key: 'menus', editor: 'menus',
          keywords: gettext('menu command label shortcut order hide font colour')},
        {id: `${DESIGNER_PREFERENCES_ID}-command-bar`, name: gettext('Tabbed bar'),
          key: 'command-bar', editor: 'command-bar',
          keywords: gettext('tabbed command bar ribbon notebook tabs groups quick access')},
        {id: `${DESIGNER_PREFERENCES_ID}-profiles`, name: gettext('Interface profiles'),
          key: 'profiles', editor: 'profiles',
          keywords: gettext('profile export import restore defaults team')},
      ]},
  ];
}

/** Whether a page matches the Preferences search text. */
export function interfacePreferenceMatches(child, search) {
  const text = String(search ?? '').trim().toLowerCase();
  return !text || `${child.name} ${child.keywords || ''}`.toLowerCase().includes(text);
}

export function InterfacePreferenceEditor({item}) {
  switch(item?.editor) {
  case 'appearance':
    return <AppearanceSectionEditor sectionId={item.section} />;
  case 'artwork':
    return <ArtworkEditor />;
  case 'menus':
    return <MenusEditor />;
  case 'command-bar':
    return <CommandBarEditor />;
  case 'profiles':
    return <ProfilesEditor />;
  default:
    return null;
  }
}

InterfacePreferenceEditor.propTypes = {item: PropTypes.object};

// A request to show a page. Preferences may not be mounted yet when it is
// made, so the request is kept until the Preferences tab takes it.
let pendingSection = null;

export function requestPreferencesSection(sectionId, target=window) {
  pendingSection = sectionId;
  target.dispatchEvent(new CustomEvent(PREFERENCES_SECTION_EVENT,
    {detail: {sectionId}}));
}

export function takePendingPreferencesSection() {
  const value = pendingSection;
  pendingSection = null;
  return value;
}
