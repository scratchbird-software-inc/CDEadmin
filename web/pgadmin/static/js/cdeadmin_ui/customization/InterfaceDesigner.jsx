/////////////////////////////////////////////////////////////
// ScratchRobin user-facing interface, icon and menu designer.
/////////////////////////////////////////////////////////////

import {useEffect, useMemo, useState} from 'react';
import {Box} from '@mui/material';
import {styled} from '@mui/material/styles';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import usePreferences from '../../../../preferences/static/js/store';
import {Button} from '../primitives/Button';
import {Checkbox, Select} from '../primitives/Choice';
import {NumberField, TextField} from '../primitives/Field';
import {Icon} from '../icons';
import {listIconDefinitions} from '../icons/registry';
import {commandRegistry} from '../commands/CommandRegistry';
import packagedStandardProfile from
  '../../../assets/cdeadmin/profiles/cdeadmin-standard.json';
import {
  CDEADMIN_MENU_STRUCTURE,
  menuStructureRegistry,
} from '../commands/MenuStructure';
import {
  exportCustomizationProfile,
  importCustomizationProfile,
  normalizeAppearanceCustomizations,
  readCustomizationDraft,
  saveCustomizationDraft,
} from './profile';
import {APPEARANCE_KEYS, readAppearance} from './appearance';

const Root = styled(Box)(({theme}) => ({
  height: '100%',
  minHeight: 0,
  display: 'grid',
  gridTemplateRows: 'auto 1fr auto',
  background: theme.palette.background.default,
  '& .InterfaceDesigner-header, & .InterfaceDesigner-footer': {
    display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8,
    padding: 8, borderBottom: `1px solid ${theme.otherVars.borderColor}`,
  },
  '& .InterfaceDesigner-footer': {
    borderBottom: 0, borderTop: `1px solid ${theme.otherVars.borderColor}`,
  },
  '& .InterfaceDesigner-body': {
    minHeight: 0, display: 'grid', gridTemplateColumns: '190px minmax(0, 1fr)',
  },
  '& .InterfaceDesigner-nav': {
    padding: 8, borderRight: `1px solid ${theme.otherVars.borderColor}`,
    display: 'flex', flexDirection: 'column', gap: 6,
  },
  '& .InterfaceDesigner-page': {minHeight: 0, overflow: 'auto', padding: 12},
  '& .InterfaceDesigner-grid': {
    display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
    gap: 12,
  },
  '& .InterfaceDesigner-masterDetail': {
    height: '100%', minHeight: 420, display: 'grid',
    gridTemplateColumns: 'minmax(220px, 32%) minmax(320px, 1fr)', gap: 12,
  },
  '& .InterfaceDesigner-list': {
    minHeight: 0, overflow: 'auto', border: `1px solid ${theme.otherVars.borderColor}`,
  },
  '& .InterfaceDesigner-listButton': {
    width: '100%', border: 0, borderBottom: `1px solid ${theme.otherVars.borderColor}`,
    background: 'transparent', color: 'inherit', textAlign: 'left', padding: 8,
    cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8,
    '&[aria-selected="true"]': {background: theme.palette.primary.light},
  },
  '& .InterfaceDesigner-detail': {
    minWidth: 0, overflow: 'auto', border: `1px solid ${theme.otherVars.borderColor}`,
    padding: 12,
  },
  '& .InterfaceDesigner-preview': {
    display: 'flex', alignItems: 'center', gap: 16, minHeight: 80,
    fontSize: 44,
  },
  '& h2, & h3': {marginTop: 0},
  '@media (max-width: 720px)': {
    '& .InterfaceDesigner-body': {gridTemplateColumns: '1fr'},
    '& .InterfaceDesigner-nav': {
      borderRight: 0, borderBottom: `1px solid ${theme.otherVars.borderColor}`,
      flexDirection: 'row', overflowX: 'auto',
    },
    '& .InterfaceDesigner-masterDetail': {gridTemplateColumns: '1fr'},
  },
}));

function currentAppearance(store) {
  return readAppearance(store.getPreferencesForModule('misc'));
}

function preferenceUpdate(store, name, value) {
  const preference = store.getPreferences('misc', name);
  if(!preference) throw new Error(`Appearance preference is unavailable: ${name}`);
  return {category_id: preference.cid, id: preference.id, mid: preference.mid,
    name: preference.name, value};
}

// Appearance is edited in View > Appearance and Accessibility (2026-11-05).
// A profile imported or restored here still carries appearance values; they
// are written only when one of those actions staged them.
// Former designer profiles never held the theme or the command bar mode, so
// restoring or importing one leaves those alone.
const DESIGNER_APPEARANCE_KEYS = APPEARANCE_KEYS.filter((name) =>
  !['theme', 'accessibility_command_bar'].includes(name));

function IconPage({value, onChange, definitions}) {
  const [query, setQuery] = useState('');
  const filtered = definitions.filter((item)=>`${item.key} ${item.label}`
    .toLowerCase().includes(query.toLowerCase()));
  const [selected, setSelected] = useState(definitions[0]?.key || '');
  const source = definitions.find((item)=>item.key === selected);
  const target = value[selected] || '';
  const options = [{value: '', label: gettext('Use packaged default')}, ...definitions.map(
    (item)=>({value: item.key, label: `${item.label} — ${item.key}`}))];
  const assign = (next) => {
    const updated = {...value};
    if(next && next !== selected) updated[selected] = next;
    else delete updated[selected];
    onChange(updated);
  };
  return <Box component="section" aria-labelledby="icons-heading" sx={{height: '100%'}}>
    <h2 id="icons-heading">{gettext('Artwork and icon assignments')}</h2>
    <div className="InterfaceDesigner-masterDetail">
      <div className="InterfaceDesigner-list">
        <TextField fullWidth label={gettext('Find semantic icon')} value={query}
          onChange={(event)=>setQuery(event.target.value)} />
        {filtered.map((item)=><button type="button" key={item.key}
          className="InterfaceDesigner-listButton" aria-selected={item.key === selected}
          onClick={()=>setSelected(item.key)}>
          <Icon iconKey={item.key} decorative /><span>{item.label}<br />
            <small>{item.key}</small></span>
        </button>)}
      </div>
      <div className="InterfaceDesigner-detail">
        {source ? <>
          <h3>{source.label}</h3>
          <p><code>{source.key}</code></p>
          <div className="InterfaceDesigner-preview"
            aria-label={gettext('Icon preview')}>
            <Icon iconKey={source.key}
              label={gettext('%s packaged default', source.label)} />
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
  </Box>;
}

IconPage.propTypes = {
  value: PropTypes.object, onChange: PropTypes.func, definitions: PropTypes.array,
};

function MenuPage({menus, commands, onMenusChange, onCommandsChange,
  definitions}) {
  const resolvedMenus = menuStructureRegistry.resolve(menus);
  const allNames = [...new Set([
    ...CDEADMIN_MENU_STRUCTURE.map((item)=>item.name), ...Object.keys(menus),
  ])];
  const [selectedMenu, setSelectedMenu] = useState(allNames[0] || 'file');
  const [selectedCommand, setSelectedCommand] = useState('');
  const [newMenu, setNewMenu] = useState({name: '', label: ''});
  const base = CDEADMIN_MENU_STRUCTURE.find((item)=>item.name === selectedMenu);
  const menu = menus[selectedMenu] ?? {name: selectedMenu,
    label: base?.label ?? selectedMenu, visible: true, index: base?.index ?? 100,
    iconKey: '', presentation: {}};
  const updateMenu = (patch) => onMenusChange({...menus,
    [selectedMenu]: {...menu, ...patch}});
  const commandList = commandRegistry.list().sort((left, right)=>
    left.label.localeCompare(right.label));
  const command = commandList.find((item)=>item.id === selectedCommand) ?? commandList[0];
  const commandValue = commands[command?.id] ?? {};
  const updateCommand = (patch) => onCommandsChange({...commands,
    [command.id]: {...commandValue, ...patch}});
  const iconOptions = [{value: '', label: gettext('Use packaged default')}, ...definitions.map(
    (item)=>({value: item.key, label: `${item.label} — ${item.key}`}))];
  const surfaceOptions = [{value: '', label: gettext('Use command default')},
    ...resolvedMenus.map((item)=>({value: item.name, label: item.label}))];
  const addMenu = () => {
    const name = newMenu.name.trim().toLowerCase();
    if(!/^[a-z][a-z0-9_-]*$/.test(name)) return;
    onMenusChange({...menus, [name]: {name, label: newMenu.label.trim() || name,
      visible: true, index: 100, iconKey: '', presentation: {}}});
    setSelectedMenu(name); setNewMenu({name: '', label: ''});
  };
  const removeMenu = () => {
    if(base) return;
    const updated = {...menus};
    delete updated[selectedMenu];
    onMenusChange(updated);
    setSelectedMenu(CDEADMIN_MENU_STRUCTURE[0].name);
  };
  return <Box component="section" aria-labelledby="menus-heading">
    <h2 id="menus-heading">{gettext('Menus and commands')}</h2>
    <h3>{gettext('Top-level menus')}</h3>
    <div className="InterfaceDesigner-masterDetail">
      <div className="InterfaceDesigner-list">
        {allNames.map((name)=><button type="button" key={name}
          className="InterfaceDesigner-listButton" aria-selected={name === selectedMenu}
          onClick={()=>setSelectedMenu(name)}>{menus[name]?.label ??
            CDEADMIN_MENU_STRUCTURE.find((item)=>item.name === name)?.label ?? name}</button>)}
      </div>
      <div className="InterfaceDesigner-detail InterfaceDesigner-grid">
        <TextField label={gettext('Menu label')} value={menu.label}
          onChange={(event)=>updateMenu({label: event.target.value})} />
        <NumberField label={gettext('Order')} value={menu.index}
          onChange={(event)=>updateMenu({index: Number(event.target.value)})} />
        <Select label={gettext('Menu icon')} value={menu.iconKey || ''}
          options={iconOptions}
          onChange={(iconKey)=>updateMenu({iconKey})} />
        <Checkbox label={gettext('Show menu')} checked={menu.visible !== false}
          onChange={(visible)=>updateMenu({visible})} />
        {!base && <Button intent="destructive" onClick={removeMenu}>
          {gettext('Remove custom menu')}
        </Button>}
        <TextField label={gettext('Menu font family')}
          value={menu.presentation?.fontFamily || ''}
          onChange={(event)=>updateMenu({presentation: {...menu.presentation,
            fontFamily: event.target.value}})} />
        <NumberField label={gettext('Menu font size')}
          value={menu.presentation?.fontSize ?? -1}
          helperText={gettext('-1 inherits the active profile')}
          inputProps={{min: -1, max: 32}}
          onChange={(event)=>updateMenu({presentation: {...menu.presentation,
            fontSize: Number(event.target.value)}})} />
        <NumberField label={gettext('Menu font weight')}
          value={menu.presentation?.fontWeight ?? -1}
          helperText={gettext('-1 inherits the active profile')}
          inputProps={{min: -1, max: 900, step: 100}}
          onChange={(event)=>updateMenu({presentation: {...menu.presentation,
            fontWeight: Number(event.target.value)}})} />
        <Select label={gettext('Menu icon position')}
          value={menu.presentation?.iconPosition || 'before'}
          options={[{value: 'before', label: gettext('Before label')},
            {value: 'after', label: gettext('After label')},
            {value: 'hidden', label: gettext('Hide icon')}]}
          onChange={(iconPosition)=>updateMenu({presentation: {
            ...menu.presentation, iconPosition}})} />
        <TextField label={gettext('Text colour')}
          value={menu.presentation?.color || ''}
          placeholder="#RRGGBB" onChange={(event)=>updateMenu({presentation: {
            ...menu.presentation, color: event.target.value}})} />
        <TextField label={gettext('Background colour')}
          value={menu.presentation?.backgroundColor || ''} placeholder="#RRGGBB"
          onChange={(event)=>updateMenu({presentation: {...menu.presentation,
            backgroundColor: event.target.value}})} />
      </div>
    </div>
    <Box sx={{display: 'flex', gap: 1, my: 1, flexWrap: 'wrap'}}>
      <TextField label={gettext('New menu ID')} value={newMenu.name}
        onChange={(event)=>setNewMenu({...newMenu, name: event.target.value})} />
      <TextField label={gettext('New menu label')} value={newMenu.label}
        onChange={(event)=>setNewMenu({...newMenu, label: event.target.value})} />
      <Button onClick={addMenu}>{gettext('Add menu')}</Button>
    </Box>
    <h3>{gettext('Command placement and presentation')}</h3>
    {command && <div className="InterfaceDesigner-masterDetail">
      <div className="InterfaceDesigner-list">
        {commandList.map((item)=><button type="button" key={item.id}
          className="InterfaceDesigner-listButton"
          aria-selected={item.id === (selectedCommand || command.id)}
          onClick={()=>setSelectedCommand(item.id)}>{item.label}<br />
          <small>{item.id}</small></button>)}
      </div>
      <div className="InterfaceDesigner-detail InterfaceDesigner-grid">
        <TextField label={gettext('Command label')}
          value={commandValue.label ?? command.label}
          onChange={(event)=>updateCommand({label: event.target.value})} />
        <Select label={gettext('Top-level menu')}
          value={commandValue.surface || ''}
          options={surfaceOptions} onChange={(surface)=>updateCommand({surface})} />
        <Select label={gettext('Command icon')}
          value={commandValue.iconKey || ''}
          options={iconOptions} onChange={(iconKey)=>updateCommand({iconKey})} />
        <NumberField label={gettext('Order within menu')}
          value={commandValue.priority ?? 1000}
          inputProps={{min: 0, max: 10000}}
          onChange={(event)=>updateCommand({priority: Number(event.target.value)})} />
        <TextField label={gettext('Keyboard shortcut')}
          value={commandValue.shortcut || ''}
          onChange={(event)=>updateCommand({shortcut: event.target.value})} />
        <TextField label={gettext('Command font family')}
          value={commandValue.presentation?.fontFamily || ''}
          onChange={(event)=>updateCommand({presentation: {
            ...commandValue.presentation, fontFamily: event.target.value}})} />
        <NumberField label={gettext('Command font size')}
          value={commandValue.presentation?.fontSize ?? -1}
          helperText={gettext('-1 inherits the active profile')}
          inputProps={{min: -1, max: 32}}
          onChange={(event)=>updateCommand({presentation: {
            ...commandValue.presentation, fontSize: Number(event.target.value)}})} />
        <NumberField label={gettext('Command font weight')}
          value={commandValue.presentation?.fontWeight ?? -1}
          helperText={gettext('-1 inherits the active profile')}
          inputProps={{min: -1, max: 900, step: 100}}
          onChange={(event)=>updateCommand({presentation: {
            ...commandValue.presentation, fontWeight: Number(event.target.value)}})} />
        <TextField label={gettext('Command text colour')}
          value={commandValue.presentation?.color || ''} placeholder="#RRGGBB"
          onChange={(event)=>updateCommand({presentation: {
            ...commandValue.presentation, color: event.target.value}})} />
        <TextField label={gettext('Command background colour')}
          value={commandValue.presentation?.backgroundColor || ''}
          placeholder="#RRGGBB"
          onChange={(event)=>updateCommand({presentation: {
            ...commandValue.presentation,
            backgroundColor: event.target.value}})} />
        <Select label={gettext('Command icon position')}
          value={commandValue.presentation?.iconPosition || 'before'}
          options={[{value: 'before', label: gettext('Before label')},
            {value: 'after', label: gettext('After label')},
            {value: 'hidden', label: gettext('Hide icon')}]}
          onChange={(iconPosition)=>updateCommand({presentation: {
            ...commandValue.presentation, iconPosition}})} />
        <Checkbox label={gettext('Show command')}
          checked={commandValue.visible !== false}
          onChange={(visible)=>updateCommand({visible})} />
        <Checkbox label={gettext('Enable command')}
          checked={commandValue.enabled !== false}
          onChange={(enabled)=>updateCommand({enabled})} />
        <p>{gettext('Customization can further restrict visibility or availability. It cannot grant a permission or bypass command and backend authorization.')}</p>
      </div>
    </div>}
  </Box>;
}

MenuPage.propTypes = {
  menus: PropTypes.object, commands: PropTypes.object,
  onMenusChange: PropTypes.func, onCommandsChange: PropTypes.func,
  definitions: PropTypes.array,
};

export default function InterfaceDesigner({panelId: _panelId}) {
  const preferenceStore = usePreferences();
  const [page, setPage] = useState('icons');
  const [appearance, setAppearance] = useState(()=>currentAppearance(
    usePreferences.getState()));
  const [appearanceStaged, setAppearanceStaged] = useState(false);
  const [draft, setDraft] = useState(()=>readCustomizationDraft(
    usePreferences.getState()));
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const definitions = useMemo(()=>[...listIconDefinitions()].sort((left, right)=>
    left.key.localeCompare(right.key)), []);
  useEffect(() => {
    setAppearance(currentAppearance(usePreferences.getState()));
    setAppearanceStaged(false);
    setDraft(readCustomizationDraft(usePreferences.getState()));
  }, [preferenceStore.version]);
  const save = async () => {
    setBusy(true); setMessage('');
    try {
      if(appearanceStaged) {
        const values = readAppearance(appearance);
        await usePreferences.getState().setPreferences(
          DESIGNER_APPEARANCE_KEYS.map((name)=>preferenceUpdate(
            usePreferences.getState(), name, values[name]))
        );
      }
      await saveCustomizationDraft(usePreferences.getState(), draft);
      setMessage(gettext(
        'Interface profile saved. Open menus and icons update immediately.'
      ));
    } catch(error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  };
  const reset = () => {
    const packaged = importCustomizationProfile(packagedStandardProfile);
    setAppearance(readAppearance({
      theme: currentAppearance(usePreferences.getState()).theme,
      ...packaged.appearance,
    }));
    setAppearanceStaged(true);
    setDraft(packaged.draft);
    setMessage(gettext(
      'Packaged defaults are staged. Choose Save profile to apply them.'
    ));
  };
  const exportProfile = () => {
    const data = JSON.stringify(exportCustomizationProfile(draft, appearance), null, 2);
    const url = URL.createObjectURL(new Blob([data], {type: 'application/json'}));
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = 'scratchrobin-interface-profile.json';
    anchor.click(); URL.revokeObjectURL(url);
  };
  const importProfile = async (event) => {
    try {
      const imported = importCustomizationProfile(await event.target.files?.[0]?.text());
      setDraft(imported.draft);
      setAppearance({...appearance, ...normalizeAppearanceCustomizations(
        imported.appearance)});
      setAppearanceStaged(true);
      setMessage(gettext(
        'Profile imported and validated. Choose Save profile to apply it.'
      ));
    } catch(error) {
      setMessage(error.message);
    } finally {
      event.target.value = '';
    }
  };
  const pages = [
    ['icons', gettext('Artwork & icons')],
    ['menus', gettext('Menus & commands')],
  ];
  return <Root data-cdeadmin-qa-key="interface-designer.workspace">
    <header className="InterfaceDesigner-header">
      <Icon iconKey="action.settings" decorative size="1.5rem" />
      <strong>{gettext('Interface Designer')}</strong>
      <span>{gettext('Artwork, menus and commands. Fonts, colours and sizes are in View > Appearance and Accessibility.')}</span>
    </header>
    <div className="InterfaceDesigner-body">
      <nav className="InterfaceDesigner-nav"
        aria-label={gettext('Interface designer sections')}>
        {pages.map(([id, label])=><Button key={id} intent={page === id ?
          'primary' : 'neutral'} aria-current={page === id ? 'page' : undefined}
        onClick={()=>setPage(id)}>{label}</Button>)}
      </nav>
      <main className="InterfaceDesigner-page">
        {page === 'icons' && <IconPage value={draft.icons}
          onChange={(icons)=>setDraft({...draft, icons})} definitions={definitions} />}
        {page === 'menus' && <MenuPage menus={draft.menus} commands={draft.commands}
          onMenusChange={(menus)=>setDraft({...draft, menus})}
          onCommandsChange={(commands)=>setDraft({...draft, commands})}
          definitions={definitions} />}
      </main>
    </div>
    <footer className="InterfaceDesigner-footer">
      <Button onClick={reset}>{gettext('Restore packaged defaults')}</Button>
      <Button onClick={exportProfile}>{gettext('Export profile')}</Button>
      <Button component="label">{gettext('Import profile')}<input type="file" hidden
        accept="application/json,.json" onChange={importProfile} /></Button>
      <Box role={message && /unavailable|not |invalid|failed/i.test(message) ?
        'alert' : 'status'} sx={{flex: 1}}>{message}</Box>
      <Button intent="primary" loading={busy} onClick={save}>
        {gettext('Save profile')}
      </Button>
    </footer>
  </Root>;
}

InterfaceDesigner.propTypes = {panelId: PropTypes.string};
