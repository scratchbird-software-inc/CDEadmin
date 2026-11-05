/////////////////////////////////////////////////////////////
//
// Scratch notebook bar: model, layout and stylesheet rules.
//
//////////////////////////////////////////////////////////////

import {
  CUSTOMIZATION_SCHEMA, applyCustomization, assignAccessKeys, foldGroups,
  isGroupVisible, matchAccessKey, mergeContributions, normalizeModel,
  NOTEBOOKBAR_CSS, visibleTabs,
} from 'sources/scratch_notebookbar';

const button = (id, extra={}) => ({id, label: id, command: `cmd.${id}`, ...extra});

function model() {
  return {
    tabs: [
      {id: 'home', label: 'Home', groups: [
        {id: 'clipboard', label: 'Clipboard', controls: [button('cut'), button('copy')]},
        {id: 'font', label: 'Font', controls: [button('bold', {type: 'toggle'})]},
      ]},
      {id: 'insert', label: 'Insert', groups: [
        {id: 'objects', label: 'Objects', controls: [button('table')]},
      ]},
      {id: 'table', label: 'Table', context: 'table', selectOnContext: true, groups: [
        {id: 'rows', label: 'Rows', controls: [button('row')]},
      ]},
    ],
    quickAccess: [button('save'), button('undo')],
  };
}

describe('notebook bar model', () => {
  it('fills defaults and refuses malformed models', () => {
    const value = normalizeModel(model());
    expect(value.defaultTab).toBe('home');
    expect(value.tabs[0].groups[0].controls[0]).toMatchObject({type: 'button',
      size: 'small'});
    expect(() => normalizeModel({tabs: [{id: 'a', label: 'A', groups: [
      {id: 'g', controls: [button('x'), button('x')]}]}]})).toThrow('used twice');
    expect(() => normalizeModel({tabs: [{id: 'a', label: 'A', groups: [
      {id: 'g', controls: [{id: 'x', label: 'X'}]}]}]})).toThrow('needs a command');
    expect(() => normalizeModel({tabs: [{id: 'a', label: 'A', groups: [
      {id: 'g', controls: [button('x', {type: 'menu'})]}]}]})).toThrow('needs items');
    expect(() => normalizeModel({tabs: [{id: 'a', label: 'A', groups: [
      {id: 'g', controls: [button('x', {type: 'dial'})]}]}]})).toThrow('unknown type');
    expect(() => normalizeModel({tabs: [{id: 'bad id', label: 'A'}]}))
      .toThrow('needs an id');
  });

  it('shows contextual tabs only in their context', () => {
    const value = normalizeModel(model());
    expect(visibleTabs(value).map((tab) => tab.id)).toEqual(['home', 'insert']);
    expect(visibleTabs(value, ['table', 'x']).map((tab) => tab.id))
      .toEqual(['home', 'insert', 'table']);
  });

  it('hides a group whose controls are all hidden', () => {
    const group = normalizeModel(model()).tabs[0].groups[0];
    expect(isGroupVisible(group, {})).toBe(true);
    expect(isGroupVisible(group, {'cmd.cut': {hidden: true},
      'cmd.copy': {hidden: true}})).toBe(false);
  });

  it('places contributed tabs and groups without replacing existing ones', () => {
    const value = mergeContributions(normalizeModel(model()), [
      {tab: {id: 'ext', label: 'Extension', groups: []}, insertAfter: 'home'},
      {groupsFor: 'home', insertBefore: 'font',
        groups: [{id: 'extra', label: 'Extra', controls: [button('ext.one')]}]},
    ]);
    expect(value.tabs.map((tab) => tab.id)).toEqual(['home', 'ext', 'insert', 'table']);
    expect(value.tabs[0].groups.map((group) => group.id))
      .toEqual(['clipboard', 'extra', 'font']);
    expect(() => mergeContributions(normalizeModel(model()),
      [{tab: {id: 'home', label: 'Again'}}])).toThrow('already exists');
  });

  it('applies a customization using only catalogued commands', () => {
    const catalog = {'cmd.query': {label: 'Query tool'},
      'cmd.save': {label: 'Save'}};
    const value = applyCustomization(normalizeModel(model()), {
      schema: CUSTOMIZATION_SCHEMA,
      tabs: {insert: {order: 0, label: 'Add'},
        home: {groups: {font: {hidden: true}, clipboard: {order: 5}}}},
      added: [{tab: 'mine', label: 'Mine', order: 1, groups: [
        {id: 'fav', label: 'Favourites', controls: ['cmd.query', 'cmd.unknown',
          'cmd.query']}]}],
      quickAccess: ['cmd.save', 'cmd.not-offered'],
    }, catalog);
    expect(value.tabs.map((tab) => tab.id)).toEqual(['insert', 'mine', 'home', 'table']);
    expect(value.tabs[0].label).toBe('Add');
    const home = value.tabs.find((tab) => tab.id === 'home');
    expect(home.groups.find((group) => group.id === 'font').hidden).toBe(true);
    // Groups the customization orders come first; the rest keep their order.
    expect(home.groups.map((group) => group.id)).toEqual(['clipboard', 'font']);
    const fav = value.tabs[1].groups[0].controls;
    expect(fav.map((control) => control.command)).toEqual(['cmd.query', 'cmd.query']);
    expect(new Set(fav.map((control) => control.id)).size).toBe(2);
    expect(value.quickAccess.map((control) => control.command)).toEqual(['cmd.save']);
    expect(() => applyCustomization(normalizeModel(model()), {schema: 'x'}))
      .toThrow('unknown schema');
  });
});

describe('notebook bar layout rules', () => {
  const groups = [{id: 'a', width: 100, priority: 5}, {id: 'b', width: 100},
    {id: 'c', width: 100, priority: 5}];

  it('folds nothing when everything fits', () => {
    expect(foldGroups(300, groups)).toEqual(new Set());
  });

  it('folds lowest priority first, then rightmost, leaving room for More', () => {
    expect(foldGroups(299, groups)).toEqual(new Set(['b']));
    expect(foldGroups(150, groups)).toEqual(new Set(['b', 'c']));
    expect(foldGroups(10, groups)).toEqual(new Set(['a', 'b', 'c']));
  });

  it('keeps declared access keys and derives the rest from labels', () => {
    const keys = assignAccessKeys([{id: 'file', label: 'File', accessKey: 'f'},
      {id: 'format', label: 'Format'}, {id: 'home', label: 'Home'},
      {id: 'help', label: 'Help'}, {id: 'h2', label: 'H'}]);
    expect(keys.get('file')).toBe('F');
    expect(keys.get('format')).toBe('O');
    expect(keys.get('home')).toBe('H');
    expect(keys.get('help')).toBe('E');
    expect(keys.get('h2')).toHaveLength(2);
    expect([...keys.values()].every((key, index, all) => all.every((other, at) =>
      at === index || !other.startsWith(key)))).toBe(true);
  });

  it('matches typed prefixes', () => {
    const keys = new Map([['a', 'ZN'], ['b', 'ZT'], ['c', 'Q']]);
    expect(matchAccessKey(keys, 'z')).toEqual({match: null, candidates: ['a', 'b']});
    expect(matchAccessKey(keys, 'zt').match).toBe('b');
    expect(matchAccessKey(keys, 'x')).toEqual({match: null, candidates: []});
  });
});

describe('notebook bar stylesheet', () => {
  it('takes every colour from a variable or a system colour', () => {
    expect(NOTEBOOKBAR_CSS).not.toMatch(/#[0-9a-f]{3,8}\b/i);
    expect(NOTEBOOKBAR_CSS).not.toMatch(/\b(rgb|rgba|hsl|hsla)\(/i);
    expect(NOTEBOOKBAR_CSS).not.toMatch(
      /:\s*(white|black|red|blue|green|gray|grey|silver|yellow)\b/i);
    for (const use of NOTEBOOKBAR_CSS.match(/var\(--snb-[\w-]+[^)]*\)/g)) {
      expect(use).toMatch(/,/); // every variable has a fallback
    }
  });
});
