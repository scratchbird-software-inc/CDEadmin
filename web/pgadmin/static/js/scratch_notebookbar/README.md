# Scratch notebook bar

A tabbed command bar ("notebook bar", "ribbon") for React applications. It
is self-contained: it needs only React 18 or 19 (with react-dom) and
prop-types, imports nothing from the application that hosts it, and takes every colour, font and size from CSS
custom properties the host sets. Any Scratch\* project can copy this folder
unchanged.

Behaviour follows the NotebookBar of Collabora Online (MPL-2.0), used as the
design reference only; no Collabora code is included.

Released under the PostgreSQL licence, like CDEadmin.

## Use

```jsx
import {NotebookBar} from './scratch_notebookbar';

<NotebookBar
  model={model}                 // tabs, groups and controls (below)
  state={state}                 // {[commandId]: {enabled, checked, value, hidden}}
  context={['table']}           // shows tabs whose context matches
  onCommand={(command, detail) => run(command, detail)}
  label="Commands"/>
```

The bar injects its stylesheet once (a `<style data-scratch-notebookbar>`
element). A host that bundles CSS itself can import `NOTEBOOKBAR_CSS` and
pass `injectStyles={false}`.

## Model

```js
{
  tabs: [{
    id: 'home', label: 'Home', accessKey: 'H',
    context: 'table',          // optional: shown only in this context (string or list)
    selectOnContext: true,     // optional: selected when its context appears
    groups: [{
      id: 'clipboard', label: 'Clipboard',   // caption under the group ('' for none)
      title: 'Clipboard',      // optional name in the customizer (else label, else id)
      priority: 10,            // higher folds into the overflow menu later
      controls: [/* controls */],
    }],
  }],
  quickAccess: [/* controls */],  // small controls left of the tabs
  defaultTab: 'home',
}
```

### Controls

Every control has `id` (unique in the bar), `label` and, except separators,
a `command` sent to `onCommand`. Optional on all: `icon` (a React node or a
render function `(size) => node`), `accessKey`, `tooltip`, `shortcut` (shown
in the tooltip and as `aria-keyshortcuts`), `size: 'large' | 'small'`
(default `small`), `showLabel` (small controls show their label unless
false).

| `type` | Shows | `onCommand(command, detail)` |
|---|---|---|
| `button` | a button | `detail = {}` |
| `toggle` | a button with on/off state (`state.checked`) | `{checked: !checked}` |
| `menu` | a button opening `items` | `{item: itemId}`, using the item's own `command` when it has one |
| `split` | a primary action and an arrow opening `items` | primary: `{}`; item: as `menu` |
| `select` | a drop-down list of `options: [{value, label}]` (`state.value`) | `{value}` |
| `color` | a split button: apply the current colour, or pick from `palette` | `{value: '#RRGGBB'}` |
| `gallery` | a row of `items` with previews, expandable to a grid | `{item: itemId}` |
| `stack` | `controls` stacked vertically (two or three small controls) | as each control |
| `separator` | a divider | none |

A menu or gallery item is `{id, label, icon?, command?, checked?, disabled?}`;
`{type: 'separator'}` divides a menu.

### State

`state[command]` may give `enabled` (default true), `checked`, `value`,
`hidden` and `label`. The bar never decides these itself; the host pushes
them. A hidden control takes no space; a group whose controls are all hidden
is hidden.

### Context

Tabs without `context` are always shown. A tab with `context` is shown only
while `context` (a string or list) contains it. When such a tab appears and
has `selectOnContext`, it becomes selected; when it disappears while
selected, the previous tab returns.

## Props

| Prop | Meaning |
|---|---|
| `model`, `state`, `context`, `onCommand` | above |
| `selectedTab`, `onSelectTab` | controlled selection (else internal) |
| `collapsed`, `onCollapsedChange` | controlled collapse (else internal); collapsed shows the tabs only and a tab click opens its panel over the content until a command runs or focus leaves |
| `start`, `end` | React nodes before the quick-access bar (for a logo) and after the tabs (an options area) |
| `contributions` | tabs and groups added by extensions; see `mergeContributions` |
| `customization` | user changes applied by `applyCustomization` (below) |
| `label` | accessible name of the bar |
| `dir` | `ltr` or `rtl` (else inherited) |
| `injectStyles` | default true |
| `accessKeyTrigger` | `'Alt'` (default) or `null` to disable access-key hints |

## Keyboard

- Tab strip: Left/Right (mirrored in RTL), Home, End move between tabs;
  Enter or Space selects; Down moves into the panel.
- Panel and quick-access bar: Left/Right move between controls, Up returns to
  the tab strip, Enter/Space activates, Down or Alt+Down opens a menu.
- Menus: Up/Down move, Enter selects, Escape closes and returns focus.
- Access keys: press and release Alt with no other key. Hints appear on the
  tabs and quick-access controls; typing a tab's key selects it and shows
  hints on its controls; typing a control's key activates it. Keys may be
  more than one letter; hints narrow as you type. Escape steps back one
  level; any click or focus leaving the bar ends the hints. Controls without
  an `accessKey` get one assigned from their label (`assignAccessKeys`).
- Double-clicking a tab, or Ctrl+F1 while focus is in the bar, collapses or
  expands the bar.

## Overflow

When a panel is narrower than its groups, groups fold into a "More" menu,
lowest `priority` first (ties: rightmost first). `foldGroups(available,
groups)` is the pure rule; the bar measures with `ResizeObserver` and
unfolds when space returns. The tab strip scrolls horizontally when its
tabs do not fit.

## Customization

`applyCustomization(model, customization)` returns the model a user sees.
A customization document is:

```js
{
  schema: 'scratch.notebookbar-customization.v1',
  tabs: {                       // per tab id; tabs absent here are unchanged
    home: {hidden: false, label: 'Start', order: 0,
      groups: {clipboard: {hidden: true}}},
  },
  added: [{                     // user tabs and groups
    tab: 'mytools', label: 'My tools', order: 5,
    groups: [{id: 'g1', label: 'Favourites', controls: ['tools.query.open']}],
  }],
  quickAccess: ['file.save', 'edit.undo'],   // replaces the quick-access list
}
```

Tabs and groups given an `order` come first, in that order; the rest follow
in their model order. User-added groups reference commands by id; the host supplies the catalog of
commands a user may place (`NotebookBarCustomizer` `catalog` prop:
`{[commandId]: {label, detail?, icon?, type?}}`, where `detail` tells apart
commands with the same label), so a
customization can only show commands the host already offers.
`NotebookBarCustomizer` is a form for editing this document (reorder, hide,
rename, add tabs and groups, place catalog commands, reset); it renders
inside whatever dialog the host provides.

## Theme variables

Each has a fallback; a host sets the ones it wants to control.

| Variable | Use | Fallback |
|---|---|---|
| `--snb-font-family` | all text | `inherit` |
| `--snb-font-size` | tab and control labels | `0.875rem` |
| `--snb-small-font-size` | large-button labels, group captions | `0.75rem` |
| `--snb-tab-height` | tab strip height | `32px` |
| `--snb-panel-height` | panel height | `88px` |
| `--snb-icon-size` | small control icons | `16px` |
| `--snb-large-icon-size` | large control icons | `32px` |
| `--snb-control-height` | small control height | `28px` |
| `--snb-gap` | spacing | `4px` |
| `--snb-radius` | corner radius | `0px` |
| `--snb-focus-width` | focus outline width | `2px` |
| `--snb-focus-offset` | focus outline offset | `1px` |
| `--snb-color-background` | bar background | `Canvas` |
| `--snb-color-panel` | panel background | `Canvas` |
| `--snb-color-text` | text | `CanvasText` |
| `--snb-color-muted` | captions, disabled text | `GrayText` |
| `--snb-color-border` | borders and separators | `GrayText` |
| `--snb-color-hover` | hovered control | `Highlight` at low opacity |
| `--snb-color-selected` | selected tab, pressed toggle | `Highlight` |
| `--snb-color-selected-text` | text on selected | `HighlightText` |
| `--snb-color-accent` | selected-tab marker | `Highlight` |
| `--snb-color-focus` | focus outline | `Highlight` |
| `--snb-color-hint` / `--snb-color-hint-text` | access-key hint badges | `CanvasText` / `Canvas` |
| `--snb-motion` | transition duration (0s for reduced motion) | `150ms` |

The fallbacks are CSS system colours, so the bar is usable with no host
theme and follows forced-colours (high contrast) modes. The stylesheet has no
literal colours; a test checks this.
