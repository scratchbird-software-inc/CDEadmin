/////////////////////////////////////////////////////////////
//
// Scratch notebook bar
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// A form for a user's notebook-bar customization: reorder, hide and rename
// tabs and groups, add their own tabs and groups, place commands from the
// host's catalog, and choose the quick-access commands. It edits the
// customization document only; the host decides where to store it and which
// dialog shows this form.

import {useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import {applyCustomization, emptyCustomization, normalizeModel} from './model';
import {message} from './messages';
import {useNotebookBarStyles} from './styles';

const ROW = {display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap'};
const COLUMN = {display: 'grid', gap: 6, alignContent: 'start', minWidth: 0};
const LIST = {border: '1px solid var(--snb-color-border, GrayText)',
  maxHeight: 240, overflow: 'auto', minHeight: 80};

function clone(document) {
  return JSON.parse(JSON.stringify(document));
}

function uniqueId(base, taken) {
  let id = base;
  for(let copy = 2; taken.has(id); copy++) id = `${base}-${copy}`;
  return id;
}

function ListBox({label, items, selected, onSelect, render}) {
  return <div role="listbox" aria-label={label} style={LIST}
    onKeyDown={(event) => {
      const index = items.findIndex((item) => item.id === selected);
      const next = {ArrowDown: index + 1, ArrowUp: index - 1}[event.key];
      if(next !== undefined && items[next]) {
        event.preventDefault();
        onSelect(items[next].id);
      }
    }}>
    {items.map((item) => <div key={item.id} role="option"
      aria-selected={item.id === selected} tabIndex={item.id === selected ? 0 : -1}
      className="snb-popup-item" style={{cursor: 'pointer',
        fontWeight: item.id === selected ? 600 : undefined}}
      onClick={() => onSelect(item.id)}>{render(item)}</div>)}
  </div>;
}
ListBox.propTypes = {label: PropTypes.string, items: PropTypes.array,
  selected: PropTypes.string, onSelect: PropTypes.func, render: PropTypes.func};

export function NotebookBarCustomizer({model, customization, catalog={},
  onChange, messages, injectStyles=true}) {
  useNotebookBarStyles(injectStyles);
  const text = (key, values) => message(messages, key, values);
  const document = customization ?? emptyCustomization();
  const base = useMemo(() => normalizeModel(model), [model]);
  const resolved = useMemo(() => applyCustomization(base, document, catalog),
    [base, document, catalog]);
  const [tabId, setTabId] = useState(resolved.tabs[0]?.id ?? '');
  const [groupId, setGroupId] = useState('');
  const [query, setQuery] = useState('');
  const [commandId, setCommandId] = useState('');
  const tab = resolved.tabs.find((item) => item.id === tabId);
  const group = tab?.groups.find((item) => item.id === groupId);
  const addedTab = document.added.find((item) => item.tab === tabId);
  const addedGroup = addedTab?.groups.find((item) => item.id === groupId);
  const update = (change) => {
    const next = clone(document);
    next.tabs ??= {};
    next.added ??= [];
    change(next);
    onChange(next);
  };
  const tabSettings = (next, id) => {
    next.tabs[id] ??= {};
    return next.tabs[id];
  };

  const moveTab = (step) => update((next) => {
    const order = resolved.tabs.map((item) => item.id);
    const index = order.indexOf(tabId);
    const target = index + step;
    if(index < 0 || target < 0 || target >= order.length) return;
    [order[index], order[target]] = [order[target], order[index]];
    order.forEach((id, position) => {
      const added = next.added.find((item) => item.tab === id);
      if(added) added.order = position;
      else tabSettings(next, id).order = position;
    });
  });
  const moveGroup = (step) => update((next) => {
    const groups = tab.groups.map((item) => item.id);
    const index = groups.indexOf(groupId);
    const target = index + step;
    if(index < 0 || target < 0 || target >= groups.length) return;
    [groups[index], groups[target]] = [groups[target], groups[index]];
    const added = next.added.find((item) => item.tab === tabId);
    if(added) {
      added.groups = groups.map((id) => added.groups.find((item) => item.id === id));
    } else {
      const settings = tabSettings(next, tabId);
      settings.groups ??= {};
      groups.forEach((id, position) => {
        settings.groups[id] = {...settings.groups[id], order: position};
      });
    }
  });
  const toggleTab = (id, shown) => update((next) => {
    tabSettings(next, id).hidden = !shown;
  });
  const toggleGroup = (id, shown) => update((next) => {
    const settings = tabSettings(next, tabId);
    settings.groups ??= {};
    settings.groups[id] = {...settings.groups[id], hidden: !shown};
  });
  const renameTab = (label) => update((next) => {
    const added = next.added.find((item) => item.tab === tabId);
    if(added) added.label = label;
    else tabSettings(next, tabId).label = label;
  });
  const renameGroup = (label) => update((next) => {
    const added = next.added.find((item) => item.tab === tabId)
      ?.groups.find((item) => item.id === groupId);
    if(added) added.label = label;
    else {
      const settings = tabSettings(next, tabId);
      settings.groups ??= {};
      settings.groups[groupId] = {...settings.groups[groupId], label};
    }
  });
  const addTab = () => {
    const id = uniqueId('custom', new Set(resolved.tabs.map((item) => item.id)));
    update((next) => {
      next.added.push({tab: id, label: text('newTab'), order: resolved.tabs.length,
        groups: [{id: 'group', label: text('newGroup'), controls: []}]});
    });
    setTabId(id);
    setGroupId('group');
  };
  const removeTab = () => {
    update((next) => {
      next.added = next.added.filter((item) => item.tab !== tabId);
    });
    setTabId(base.tabs[0]?.id ?? '');
    setGroupId('');
  };
  const addGroup = () => {
    const id = uniqueId('group', new Set(addedTab.groups.map((item) => item.id)));
    update((next) => {
      next.added.find((item) => item.tab === tabId).groups.push(
        {id, label: text('newGroup'), controls: []});
    });
    setGroupId(id);
  };
  const removeGroup = () => {
    update((next) => {
      const added = next.added.find((item) => item.tab === tabId);
      added.groups = added.groups.filter((item) => item.id !== groupId);
    });
    setGroupId('');
  };
  const editGroupCommands = (change) => update((next) => {
    const target = next.added.find((item) => item.tab === tabId)
      .groups.find((item) => item.id === groupId);
    target.controls = change(target.controls);
  });
  const quick = document.quickAccess ??
    base.quickAccess.map((control) => control.command).filter((id) => catalog[id]);
  const editQuick = (change) => update((next) => {
    next.quickAccess = change([...quick]);
  });
  const move = (items, index, step) => {
    const target = index + step;
    if(target < 0 || target >= items.length) return items;
    const copy = [...items];
    [copy[index], copy[target]] = [copy[target], copy[index]];
    return copy;
  };

  const commands = Object.entries(catalog)
    .map(([id, control]) => ({id, label: control.label ?? id}))
    .filter((item) => `${item.label} ${item.id}`.toLowerCase()
      .includes(query.toLowerCase()))
    .sort((left, right) => left.label.localeCompare(right.label));
  const labelOf = (id) => catalog[id]?.label ?? id;

  return <div className="snb-customizer" role="group"
    aria-label={text('customizer')}
    style={{display: 'grid', gap: 12,
      gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
      fontFamily: 'var(--snb-font-family, inherit)',
      fontSize: 'var(--snb-font-size, 0.875rem)',
      color: 'var(--snb-color-text, CanvasText)'}}>
    <section style={COLUMN} aria-label={text('tabs')}>
      <strong>{text('tabs')}</strong>
      <ListBox label={text('tabs')} items={resolved.tabs} selected={tabId}
        onSelect={(id) => { setTabId(id); setGroupId(''); }}
        render={(item) => <span style={ROW}>
          <input type="checkbox" aria-label={`${text('show')} ${item.label}`}
            checked={!item.hidden} onClick={(event) => event.stopPropagation()}
            onChange={(event) => toggleTab(item.id, event.target.checked)} />
          {item.label}
        </span>} />
      <div style={ROW}>
        <button type="button" onClick={() => moveTab(-1)} disabled={!tab}>
          {text('moveUp')}</button>
        <button type="button" onClick={() => moveTab(1)} disabled={!tab}>
          {text('moveDown')}</button>
        <button type="button" onClick={addTab}>{text('addTab')}</button>
        <button type="button" onClick={removeTab} disabled={!addedTab}>
          {text('removeTab')}</button>
      </div>
      {tab && <label style={ROW}>{text('rename')}
        <input type="text" value={tab.label} maxLength={60}
          onChange={(event) => renameTab(event.target.value)} /></label>}
    </section>

    <section style={COLUMN} aria-label={text('groups', {tab: tab?.label ?? ''})}>
      <strong>{text('groups', {tab: tab?.label ?? ''})}</strong>
      <ListBox label={text('groups', {tab: tab?.label ?? ''})}
        items={tab?.groups ?? []} selected={groupId} onSelect={setGroupId}
        render={(item) => <span style={ROW}>
          <input type="checkbox" aria-label={`${text('show')} ${item.label}`}
            checked={!item.hidden} onClick={(event) => event.stopPropagation()}
            onChange={(event) => toggleGroup(item.id, event.target.checked)}
            disabled={Boolean(addedTab)} />
          {item.label || item.id}
        </span>} />
      <div style={ROW}>
        <button type="button" onClick={() => moveGroup(-1)} disabled={!group}>
          {text('moveUp')}</button>
        <button type="button" onClick={() => moveGroup(1)} disabled={!group}>
          {text('moveDown')}</button>
        <button type="button" onClick={addGroup} disabled={!addedTab}>
          {text('addGroup')}</button>
        <button type="button" onClick={removeGroup} disabled={!addedGroup}>
          {text('removeGroup')}</button>
      </div>
      {group && <label style={ROW}>{text('rename')}
        <input type="text" value={group.label ?? ''} maxLength={60}
          onChange={(event) => renameGroup(event.target.value)} /></label>}
      {addedGroup && <div role="list" aria-label={addedGroup.label} style={LIST}>
        {addedGroup.controls.length === 0 && <div style={{padding: 6}}>
          {text('emptyGroup')}</div>}
        {addedGroup.controls.map((id, index) => <div key={`${id}-${index}`}
          role="listitem" style={{...ROW, padding: 4}}>
          <span style={{flex: 1}}>{labelOf(id)}</span>
          <button type="button" aria-label={`${text('moveUp')} ${labelOf(id)}`}
            onClick={() => editGroupCommands((items) => move(items, index, -1))}>↑</button>
          <button type="button" aria-label={`${text('moveDown')} ${labelOf(id)}`}
            onClick={() => editGroupCommands((items) => move(items, index, 1))}>↓</button>
          <button type="button" aria-label={`${text('remove')} ${labelOf(id)}`}
            onClick={() => editGroupCommands((items) =>
              items.filter((_item, at) => at !== index))}>×</button>
        </div>)}
      </div>}
    </section>

    <section style={COLUMN} aria-label={text('commands')}>
      <strong>{text('commands')}</strong>
      <input type="search" aria-label={text('search')} placeholder={text('search')}
        value={query} onChange={(event) => setQuery(event.target.value)} />
      <ListBox label={text('commands')} items={commands} selected={commandId}
        onSelect={setCommandId} render={(item) => item.label} />
      <div style={ROW}>
        <button type="button" disabled={!addedGroup || !commandId}
          onClick={() => editGroupCommands((items) => [...items, commandId])}>
          {text('addToGroup')}</button>
        <button type="button" disabled={!commandId || quick.includes(commandId)}
          onClick={() => editQuick((items) => [...items, commandId])}>
          {text('addToQuickAccess')}</button>
      </div>
      {!addedGroup && <small>{text('noCustomGroup')}</small>}
    </section>

    <section style={COLUMN} aria-label={text('quickAccessList')}>
      <strong>{text('quickAccessList')}</strong>
      <div role="list" aria-label={text('quickAccessList')} style={LIST}>
        {quick.map((id, index) => <div key={id} role="listitem"
          style={{...ROW, padding: 4}}>
          <span style={{flex: 1}}>{labelOf(id)}</span>
          <button type="button" aria-label={`${text('moveUp')} ${labelOf(id)}`}
            onClick={() => editQuick((items) => move(items, index, -1))}>↑</button>
          <button type="button" aria-label={`${text('moveDown')} ${labelOf(id)}`}
            onClick={() => editQuick((items) => move(items, index, 1))}>↓</button>
          <button type="button" aria-label={`${text('remove')} ${labelOf(id)}`}
            onClick={() => editQuick((items) => items.filter((item) => item !== id))}>
            ×</button>
        </div>)}
      </div>
      <div style={ROW}>
        <button type="button" onClick={() => { onChange(emptyCustomization());
          setTabId(base.tabs[0]?.id ?? ''); setGroupId(''); }}>
          {text('reset')}</button>
      </div>
    </section>
  </div>;
}

NotebookBarCustomizer.propTypes = {
  model: PropTypes.object.isRequired,
  customization: PropTypes.object,
  catalog: PropTypes.object,
  onChange: PropTypes.func.isRequired,
  messages: PropTypes.object,
  injectStyles: PropTypes.bool,
};
