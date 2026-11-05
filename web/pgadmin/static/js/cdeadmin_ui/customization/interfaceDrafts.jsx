/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// Unsaved interface changes for the Preferences tab: appearance, the
// interface designer's artwork/menu/command customization, and the tabbed
// command bar. They live for the whole tab, so moving between its sections
// keeps them; the appearance preview ends when the tab closes.

import {createContext, useContext, useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import usePreferences from '../../../../preferences/static/js/store';
import {previewAppearance} from '../foundations/presentation';
import {readAppearance} from './appearance';
import {readCustomizationDraft} from './profile';
import {readCommandBarCustomization} from '../shell/commandBarSettings';

const InterfaceDraftContext = createContext(null);

export function InterfacePreferencesProvider({children, changedRef}) {
  const version = usePreferences((state) => state.version);
  const store = () => usePreferences.getState();
  const savedAppearance = useMemo(() =>
    readAppearance(store().getPreferencesForModule('misc')), [version]);
  const savedDesigner = useMemo(() => readCustomizationDraft(store()), [version]);
  const savedCommandBar = useMemo(() => readCommandBarCustomization(store()),
    [version]);
  // null = unchanged from what is saved.
  const [appearanceDraft, setAppearanceDraft] = useState(null);
  const [designerDraft, setDesignerDraft] = useState(null);
  // Appearance carried by an imported or restored designer profile; written
  // with the designer customization.
  const [stagedAppearance, setStagedAppearance] = useState(null);
  const [commandBarDraft, setCommandBarDraft] = useState(undefined);

  useEffect(() => { previewAppearance(appearanceDraft); }, [appearanceDraft]);
  useEffect(() => () => previewAppearance(null), []);
  // Lets the host warn before unsaved changes are lost (Preferences close).
  if(changedRef) {
    changedRef.current = appearanceDraft !== null || designerDraft !== null ||
      stagedAppearance !== null || commandBarDraft !== undefined;
  }

  const value = useMemo(() => ({
    savedAppearance,
    appearance: appearanceDraft ?? savedAppearance,
    appearanceChanged: appearanceDraft !== null,
    updateAppearance: (changes) => setAppearanceDraft((current) =>
      ({...(current ?? savedAppearance), ...changes})),
    discardAppearance: () => setAppearanceDraft(null),
    savedDesigner,
    designer: designerDraft ?? savedDesigner,
    designerChanged: designerDraft !== null || stagedAppearance !== null,
    updateDesigner: (changes) => setDesignerDraft((current) =>
      ({...(current ?? savedDesigner), ...changes})),
    stagedAppearance,
    stageAppearance: setStagedAppearance,
    discardDesigner: () => { setDesignerDraft(null); setStagedAppearance(null); },
    savedCommandBar,
    commandBar: commandBarDraft === undefined ? savedCommandBar : commandBarDraft,
    commandBarChanged: commandBarDraft !== undefined,
    updateCommandBar: setCommandBarDraft,
    discardCommandBar: () => setCommandBarDraft(undefined),
  }), [savedAppearance, appearanceDraft, savedDesigner, designerDraft,
    stagedAppearance, savedCommandBar, commandBarDraft]);
  return <InterfaceDraftContext.Provider value={value}>
    {children}
  </InterfaceDraftContext.Provider>;
}

InterfacePreferencesProvider.propTypes = {children: PropTypes.node,
  changedRef: PropTypes.object};

export function useInterfaceDrafts() {
  const drafts = useContext(InterfaceDraftContext);
  if(!drafts) {
    throw new Error('Interface preference editors need InterfacePreferencesProvider.');
  }
  return drafts;
}

/** A Preferences record for one setting, as the preferences endpoint takes it. */
export function preferenceRecord(module, name, value) {
  const preference = usePreferences.getState().getPreferences(module, name);
  if(!preference) {
    throw new Error(`The setting ${module}:${name} is unavailable.`);
  }
  return {category_id: preference.cid, id: preference.id, mid: preference.mid,
    name: preference.name, value};
}

export function errorText(error) {
  return error?.response?.data?.errormsg || error?.message || String(error);
}
