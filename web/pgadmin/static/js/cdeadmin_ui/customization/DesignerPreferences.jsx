/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// Preferences > Interface designer (owner direction 2026-11-05: the
// interface designer is part of Preferences): artwork and icon assignments,
// menu and command presentation, the tabbed command bar, and interface
// profiles. Customization can only restrict or rearrange what commands
// already allow; it never grants a permission.

import {useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import pgAdmin from 'sources/pgadmin';
import usePreferences from '../../../../preferences/static/js/store';
import {Button} from '../primitives/Button';
import {Checkbox, Select} from '../primitives/Choice';
import {NumberField, TextField} from '../primitives/Field';
import {ValidationMessage} from '../feedback/Indicators';
import {Icon, inferActionIconKey} from '../icons';
import {listIconDefinitions} from '../icons/registry';
import {commandRegistry} from '../commands/CommandRegistry';
import {CDEADMIN_MENU_STRUCTURE, menuStructureRegistry} from '../commands/MenuStructure';
import packagedStandardProfile from
  '../../../assets/cdeadmin/profiles/cdeadmin-standard.json';
import {NotebookBarCustomizer} from '../../scratch_notebookbar';
import {buildCommandBarModel} from '../shell/commandBarModel';
import {
  COMMAND_BAR_MESSAGES, COMMAND_BAR_THEME, saveCommandBarCustomization,
} from '../shell/commandBarSettings';
import {
  exportCustomizationProfile, importCustomizationProfile,
  normalizeAppearanceCustomizations, saveCustomizationDraft,
} from './profile';
import {APPEARANCE_KEYS, readAppearance} from './appearance';
import {errorText, preferenceRecord, useInterfaceDrafts} from './interfaceDrafts';

const PAGE = {display: 'grid', gap: 16, padding: 16, alignContent: 'start'};
const GRID = {display: 'grid', gap: 12,
  gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', alignItems: 'start'};
const MASTER_DETAIL = {display: 'grid', gap: 12, minHeight: 360,
  gridTemplateColumns: 'minmax(220px, 32%) minmax(320px, 1fr)'};
const BORDER = '1px solid var(--cde-color-border, currentColor)';
const LIST = {border: BORDER, overflow: 'auto', maxHeight: 420, minHeight: 0};
const DETAIL = {border: BORDER, overflow: 'auto', padding: 12, minWidth: 0};
const ROW = {display: 'flex', flexWrap: 'wrap', alignItems: 'center',
  gap: 'var(--cde-target-spacing, 8px)'};

function listButtonStyle(selected) {
  return {width: '100%', border: 0, borderBottom: BORDER, color: 'inherit',
    background: selected ? 'var(--cde-color-selection, Highlight)' : 'transparent',
    textAlign: 'start', padding: 8, cursor: 'pointer', display: 'flex',
    alignItems: 'center', gap: 8, font: 'inherit'};
}

// Former designer profiles never held the theme or the command bar mode, so
// restoring or importing one leaves those alone.
const DESIGNER_APPEARANCE_KEYS = APPEARANCE_KEYS.filter((name) =>
  !['theme', 'accessibility_command_bar'].includes(name));

function iconDefinitions() {
  return [...listIconDefinitions()].sort((left, right) =>
    left.key.localeCompare(right.key));
}

/** Save and discard for the designer's shared draft, shown on its pages. */
function DesignerFooter({message, setMessage}) {
  const drafts = useInterfaceDrafts();
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    setMessage({status: 'info', text: ''});
    try {
      if(drafts.stagedAppearance) {
        const values = readAppearance(drafts.stagedAppearance);
        await usePreferences.getState().setPreferences(DESIGNER_APPEARANCE_KEYS
          .map((name) => preferenceRecord('misc', name, values[name])));
      }
      await saveCustomizationDraft(usePreferences.getState(), drafts.designer);
      drafts.discardDesigner();
      setMessage({status: 'success', text: gettext(
        'Interface customization saved. Open menus and icons update immediately.')});
    } catch(error) {
      setMessage({status: 'error', text: errorText(error)});
    } finally {
      setBusy(false);
    }
  };
  return <div style={{...ROW, borderTop: BORDER, paddingTop: 8}}>
    <div style={{flex: 1}}>
      {message.text ? <ValidationMessage status={message.status}>{message.text}</ValidationMessage> :
        drafts.designerChanged && <ValidationMessage status="info">
          {gettext('Unsaved interface designer changes.')}</ValidationMessage>}
    </div>
    <Button disabled={!drafts.designerChanged || busy}
      onClick={() => { drafts.discardDesigner(); setMessage({status: 'info', text: ''}); }}>
      {gettext('Discard changes')}
    </Button>
    <Button intent="primary" loading={busy} disabled={!drafts.designerChanged}
      onClick={save}>{gettext('Save interface customization')}</Button>
  </div>;
}

DesignerFooter.propTypes = {message: PropTypes.object.isRequired,
  setMessage: PropTypes.func.isRequired};

export function ArtworkEditor() {
  const drafts = useInterfaceDrafts();
  const definitions = useMemo(iconDefinitions, []);
  const [message, setMessage] = useState({status: 'info', text: ''});
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(definitions[0]?.key || '');
  const value = drafts.designer.icons;
  const filtered = definitions.filter((item) => `${item.key} ${item.label}`
    .toLowerCase().includes(query.toLowerCase()));
  const source = definitions.find((item) => item.key === selected);
  const target = value[selected] || '';
  const options = [{value: '', label: gettext('Use packaged default')},
    ...definitions.map((item) => ({value: item.key, label: `${item.label} — ${item.key}`}))];
  const assign = (next) => {
    const updated = {...value};
    if(next && next !== selected) updated[selected] = next;
    else delete updated[selected];
    drafts.updateDesigner({icons: updated});
  };
  return <section aria-labelledby="designer-artwork-heading" style={PAGE}
    data-cdeadmin-qa-key="designer.artwork">
    <h2 id="designer-artwork-heading" style={{margin: 0}}>
      {gettext('Artwork and icon assignments')}</h2>
    <div style={MASTER_DETAIL}>
      <div style={LIST}>
        <div style={{padding: 8}}>
          <TextField fullWidth label={gettext('Find semantic icon')} value={query}
            onChange={(event) => setQuery(event.target.value)} />
        </div>
        {filtered.map((item) => <button type="button" key={item.key}
          style={listButtonStyle(item.key === selected)}
          aria-pressed={item.key === selected} onClick={() => setSelected(item.key)}>
          <Icon iconKey={value[item.key] || item.key} decorative />
          <span>{item.label}<br /><small>{item.key}</small></span>
        </button>)}
      </div>
      <div style={DETAIL}>
        {source ? <>
          <h3 style={{marginTop: 0}}>{source.label}</h3>
          <p><code>{source.key}</code></p>
          <div aria-label={gettext('Icon preview')}
            style={{display: 'flex', alignItems: 'center', gap: 16, minHeight: 80,
              fontSize: 44}}>
            <Icon iconKey={source.key} label={gettext('%s packaged default', source.label)} />
            <span aria-hidden="true">→</span>
            <Icon iconKey={target || source.key}
              label={gettext('%s assigned icon', source.label)} />
          </div>
          <Select fullWidth label={gettext('Assigned catalog artwork')} value={target}
            options={options} onChange={assign} />
          <p>{gettext('Assignments use catalog identities, not paths or SVG markup. Resetting this assignment restores the packaged and attributed default.')}</p>
        </> : <p>{gettext('No matching icon.')}</p>}
      </div>
    </div>
    <DesignerFooter message={message} setMessage={setMessage} />
  </section>;
}

export function MenusEditor() {
  const drafts = useInterfaceDrafts();
  const definitions = useMemo(iconDefinitions, []);
  const [message, setMessage] = useState({status: 'info', text: ''});
  const menus = drafts.designer.menus;
  const commands = drafts.designer.commands;
  const onMenusChange = (next) => drafts.updateDesigner({menus: next});
  const onCommandsChange = (next) => drafts.updateDesigner({commands: next});
  const resolvedMenus = menuStructureRegistry.resolve(menus);
  const allNames = [...new Set([
    ...CDEADMIN_MENU_STRUCTURE.map((item) => item.name), ...Object.keys(menus),
  ])];
  const [selectedMenu, setSelectedMenu] = useState(allNames[0] || 'file');
  const [selectedCommand, setSelectedCommand] = useState('');
  const [newMenu, setNewMenu] = useState({name: '', label: ''});
  const base = CDEADMIN_MENU_STRUCTURE.find((item) => item.name === selectedMenu);
  const menu = menus[selectedMenu] ?? {name: selectedMenu,
    label: base?.label ?? selectedMenu, visible: true, index: base?.index ?? 100,
    iconKey: '', presentation: {}};
  const updateMenu = (patch) => onMenusChange({...menus,
    [selectedMenu]: {...menu, ...patch}});
  const commandList = commandRegistry.list().sort((left, right) =>
    left.label.localeCompare(right.label));
  const command = commandList.find((item) => item.id === selectedCommand) ??
    commandList[0];
  const commandValue = commands[command?.id] ?? {};
  const updateCommand = (patch) => onCommandsChange({...commands,
    [command.id]: {...commandValue, ...patch}});
  const iconOptions = [{value: '', label: gettext('Use packaged default')},
    ...definitions.map((item) => ({value: item.key, label: `${item.label} — ${item.key}`}))];
  const surfaceOptions = [{value: '', label: gettext('Use command default')},
    ...resolvedMenus.map((item) => ({value: item.name, label: item.label}))];
  const positionOptions = [{value: 'before', label: gettext('Before label')},
    {value: 'after', label: gettext('After label')},
    {value: 'hidden', label: gettext('Hide icon')}];
  const addMenu = () => {
    const name = newMenu.name.trim().toLowerCase();
    if(!/^[a-z][a-z0-9_-]*$/.test(name)) return;
    onMenusChange({...menus, [name]: {name, label: newMenu.label.trim() || name,
      visible: true, index: 100, iconKey: '', presentation: {}}});
    setSelectedMenu(name);
    setNewMenu({name: '', label: ''});
  };
  const removeMenu = () => {
    if(base) return;
    const updated = {...menus};
    delete updated[selectedMenu];
    onMenusChange(updated);
    setSelectedMenu(CDEADMIN_MENU_STRUCTURE[0].name);
  };
  const menuPresentation = (patch) => updateMenu({presentation: {
    ...menu.presentation, ...patch}});
  const commandPresentation = (patch) => updateCommand({presentation: {
    ...commandValue.presentation, ...patch}});
  return <section aria-labelledby="designer-menus-heading" style={PAGE}
    data-cdeadmin-qa-key="designer.menus">
    <h2 id="designer-menus-heading" style={{margin: 0}}>{gettext('Menus and commands')}</h2>
    <h3 style={{margin: 0}}>{gettext('Top-level menus')}</h3>
    <div style={MASTER_DETAIL}>
      <div style={LIST}>
        {allNames.map((name) => <button type="button" key={name}
          style={listButtonStyle(name === selectedMenu)}
          aria-pressed={name === selectedMenu}
          onClick={() => setSelectedMenu(name)}>{menus[name]?.label ??
            CDEADMIN_MENU_STRUCTURE.find((item) => item.name === name)?.label ?? name}
        </button>)}
      </div>
      <div style={{...DETAIL, ...GRID}}>
        <TextField label={gettext('Menu label')} value={menu.label}
          onChange={(event) => updateMenu({label: event.target.value})} />
        <NumberField label={gettext('Order')} value={menu.index}
          onChange={(event) => updateMenu({index: Number(event.target.value)})} />
        <Select label={gettext('Menu icon')} value={menu.iconKey || ''}
          options={iconOptions} onChange={(iconKey) => updateMenu({iconKey})} />
        <Checkbox label={gettext('Show menu')} checked={menu.visible !== false}
          onChange={(visible) => updateMenu({visible})} />
        {!base && <Button intent="destructive" onClick={removeMenu}>
          {gettext('Remove custom menu')}
        </Button>}
        <TextField label={gettext('Menu font family')}
          value={menu.presentation?.fontFamily || ''}
          onChange={(event) => menuPresentation({fontFamily: event.target.value})} />
        <NumberField label={gettext('Menu font size')}
          value={menu.presentation?.fontSize ?? -1}
          helperText={gettext('-1 inherits the active profile')}
          inputProps={{min: -1, max: 32}}
          onChange={(event) => menuPresentation({fontSize: Number(event.target.value)})} />
        <NumberField label={gettext('Menu font weight')}
          value={menu.presentation?.fontWeight ?? -1}
          helperText={gettext('-1 inherits the active profile')}
          inputProps={{min: -1, max: 900, step: 100}}
          onChange={(event) => menuPresentation({fontWeight: Number(event.target.value)})} />
        <Select label={gettext('Menu icon position')}
          value={menu.presentation?.iconPosition || 'before'} options={positionOptions}
          onChange={(iconPosition) => menuPresentation({iconPosition})} />
        <TextField label={gettext('Text colour')} value={menu.presentation?.color || ''}
          placeholder="#RRGGBB"
          onChange={(event) => menuPresentation({color: event.target.value})} />
        <TextField label={gettext('Background colour')}
          value={menu.presentation?.backgroundColor || ''} placeholder="#RRGGBB"
          onChange={(event) => menuPresentation({backgroundColor: event.target.value})} />
      </div>
    </div>
    <div style={ROW}>
      <TextField label={gettext('New menu ID')} value={newMenu.name}
        onChange={(event) => setNewMenu({...newMenu, name: event.target.value})} />
      <TextField label={gettext('New menu label')} value={newMenu.label}
        onChange={(event) => setNewMenu({...newMenu, label: event.target.value})} />
      <Button onClick={addMenu}>{gettext('Add menu')}</Button>
    </div>
    <h3 style={{margin: 0}}>{gettext('Command placement and presentation')}</h3>
    {command && <div style={MASTER_DETAIL}>
      <div style={LIST}>
        {commandList.map((item) => <button type="button" key={item.id}
          style={listButtonStyle(item.id === command.id)}
          aria-pressed={item.id === command.id}
          onClick={() => setSelectedCommand(item.id)}>
          <span>{item.label}<br /><small>{item.id}</small></span>
        </button>)}
      </div>
      <div style={{...DETAIL, ...GRID}}>
        <TextField label={gettext('Command label')}
          value={commandValue.label ?? command.label}
          onChange={(event) => updateCommand({label: event.target.value})} />
        <Select label={gettext('Top-level menu')} value={commandValue.surface || ''}
          options={surfaceOptions} onChange={(surface) => updateCommand({surface})} />
        <Select label={gettext('Command icon')} value={commandValue.iconKey || ''}
          options={iconOptions} onChange={(iconKey) => updateCommand({iconKey})} />
        <NumberField label={gettext('Order within menu')}
          value={commandValue.priority ?? 1000} inputProps={{min: 0, max: 10000}}
          onChange={(event) => updateCommand({priority: Number(event.target.value)})} />
        <TextField label={gettext('Keyboard shortcut')} value={commandValue.shortcut || ''}
          onChange={(event) => updateCommand({shortcut: event.target.value})} />
        <TextField label={gettext('Command font family')}
          value={commandValue.presentation?.fontFamily || ''}
          onChange={(event) => commandPresentation({fontFamily: event.target.value})} />
        <NumberField label={gettext('Command font size')}
          value={commandValue.presentation?.fontSize ?? -1}
          helperText={gettext('-1 inherits the active profile')}
          inputProps={{min: -1, max: 32}}
          onChange={(event) => commandPresentation({fontSize: Number(event.target.value)})} />
        <NumberField label={gettext('Command font weight')}
          value={commandValue.presentation?.fontWeight ?? -1}
          helperText={gettext('-1 inherits the active profile')}
          inputProps={{min: -1, max: 900, step: 100}}
          onChange={(event) => commandPresentation({fontWeight: Number(event.target.value)})} />
        <TextField label={gettext('Command text colour')}
          value={commandValue.presentation?.color || ''} placeholder="#RRGGBB"
          onChange={(event) => commandPresentation({color: event.target.value})} />
        <TextField label={gettext('Command background colour')}
          value={commandValue.presentation?.backgroundColor || ''} placeholder="#RRGGBB"
          onChange={(event) => commandPresentation({backgroundColor: event.target.value})} />
        <Select label={gettext('Command icon position')}
          value={commandValue.presentation?.iconPosition || 'before'}
          options={positionOptions}
          onChange={(iconPosition) => commandPresentation({iconPosition})} />
        <Checkbox label={gettext('Show command')} checked={commandValue.visible !== false}
          onChange={(visible) => updateCommand({visible})} />
        <Checkbox label={gettext('Enable command')} checked={commandValue.enabled !== false}
          onChange={(enabled) => updateCommand({enabled})} />
        <p>{gettext('Customization can further restrict visibility or availability. It cannot grant a permission or bypass command and backend authorization.')}</p>
      </div>
    </div>}
    <DesignerFooter message={message} setMessage={setMessage} />
  </section>;
}

export function ProfilesEditor() {
  const drafts = useInterfaceDrafts();
  const [message, setMessage] = useState({status: 'info', text: ''});
  const restore = () => {
    const packaged = importCustomizationProfile(packagedStandardProfile);
    drafts.updateDesigner(packaged.draft);
    drafts.stageAppearance(readAppearance({theme: drafts.savedAppearance.theme,
      ...packaged.appearance}));
    setMessage({status: 'info', text: gettext(
      'Packaged defaults are staged. Choose Save interface customization to apply them.')});
  };
  const exportProfile = () => {
    const data = JSON.stringify(exportCustomizationProfile(drafts.designer,
      drafts.stagedAppearance ?? drafts.savedAppearance), null, 2);
    const url = URL.createObjectURL(new Blob([data], {type: 'application/json'}));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'scratchrobin-interface-profile.json';
    anchor.click();
    URL.revokeObjectURL(url);
  };
  const importProfile = async (event) => {
    try {
      const imported = importCustomizationProfile(await event.target.files?.[0]?.text());
      drafts.updateDesigner(imported.draft);
      drafts.stageAppearance({...drafts.savedAppearance,
        ...normalizeAppearanceCustomizations(imported.appearance)});
      setMessage({status: 'info', text: gettext(
        'Profile imported and validated. Choose Save interface customization to apply it.')});
    } catch(error) {
      setMessage({status: 'error', text: error.message});
    } finally {
      event.target.value = '';
    }
  };
  return <section aria-labelledby="designer-profiles-heading" style={PAGE}
    data-cdeadmin-qa-key="designer.profiles">
    <h2 id="designer-profiles-heading" style={{margin: 0}}>{gettext('Interface profiles')}</h2>
    <p style={{margin: 0}}>{gettext(
      'An interface profile holds your artwork, menu and command customization and your appearance. Export it to share a team baseline; importing or restoring one stages it here until you save.')}</p>
    <div style={ROW}>
      <Button onClick={restore}>{gettext('Restore packaged defaults')}</Button>
      <Button onClick={exportProfile}>{gettext('Export profile')}</Button>
      <Button component="label">{gettext('Import profile')}<input type="file" hidden
        accept="application/json,.json" onChange={importProfile} /></Button>
    </div>
    <DesignerFooter message={message} setMessage={setMessage} />
  </section>;
}

function commandIcon(item) {
  return <Icon iconKey={item.iconKey || inferActionIconKey(item) || 'command.default'}
    decorative size="100%" />;
}

export function CommandBarEditor({menus}) {
  const drafts = useInterfaceDrafts();
  const source = menus ?? pgAdmin.Browser?.MainMenus ?? [];
  const bar = useMemo(() => buildCommandBarModel(source, commandIcon), [source]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState({status: 'info', text: ''});
  const save = async () => {
    setBusy(true);
    setMessage({status: 'info', text: ''});
    try {
      await saveCommandBarCustomization(usePreferences.getState(), drafts.commandBar);
      drafts.discardCommandBar();
      setMessage({status: 'success', text: gettext('Tabbed bar saved.')});
    } catch(error) {
      setMessage({status: 'error', text: errorText(error)});
    } finally {
      setBusy(false);
    }
  };
  return <section aria-labelledby="designer-command-bar-heading"
    data-cdeadmin-qa-key="designer.command-bar" style={{...PAGE, ...COMMAND_BAR_THEME}}>
    <h2 id="designer-command-bar-heading" style={{margin: 0}}>{gettext('Tabbed bar')}</h2>
    <p style={{margin: 0}}>{gettext(
      'Arrange the tabbed command bar (Appearance and accessibility > Menu and activity bar > Command bar). It shows the commands of the menus; a command you cannot run stays unavailable wherever you place it.')}</p>
    <NotebookBarCustomizer model={bar.model} catalog={bar.catalog}
      customization={drafts.commandBar} onChange={drafts.updateCommandBar}
      messages={COMMAND_BAR_MESSAGES} />
    <div style={{...ROW, borderTop: BORDER, paddingTop: 8}}>
      <div style={{flex: 1}}>
        {message.text && <ValidationMessage status={message.status}>{message.text}</ValidationMessage>}
      </div>
      <Button disabled={!drafts.commandBarChanged || busy}
        onClick={() => { drafts.discardCommandBar(); setMessage({status: 'info', text: ''}); }}>
        {gettext('Discard changes')}
      </Button>
      <Button intent="primary" loading={busy} disabled={!drafts.commandBarChanged}
        onClick={save}>{gettext('Save')}</Button>
    </div>
  </section>;
}

CommandBarEditor.propTypes = {menus: PropTypes.array};
