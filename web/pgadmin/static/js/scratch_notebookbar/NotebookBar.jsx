/////////////////////////////////////////////////////////////
//
// Scratch notebook bar
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// A tabbed command bar; see README.md for the model, props, keyboard and
// theme contract.

import {
  useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState,
} from 'react';
import PropTypes from 'prop-types';
import {
  applyCustomization, flattenControls, isControlVisible, isGroupVisible,
  mergeContributions, normalizeModel, visibleTabs,
} from './model';
import {assignAccessKeys, foldGroups, matchAccessKey} from './layout';
import {Control, Popup} from './controls';
import {useNotebookBarStyles} from './styles';
import {message} from './messages';

const OVERFLOW_ID = '__snb_overflow__';

function useControlled(value, fallback) {
  const [internal, setInternal] = useState(fallback);
  return [value === undefined ? internal : value, setInternal];
}

function focusables(root) {
  return root ? [...root.querySelectorAll('[data-snb-focusable]')]
    .filter((element) => element.getAttribute('aria-disabled') !== 'true' &&
      !element.disabled) : [];
}

// Model ids allow only [\w.:-], so they are safe inside a quoted selector.
const byAttribute = (name, value) => `[${name}="${value}"]`;

// Roving focus: one element of a container is tabbable at a time.
function setRoving(root, active) {
  for(const element of focusables(root)) {
    element.tabIndex = element === active ? 0 : -1;
  }
}

function Group({group, state, onCommand, hints, folded, measure, messages}) {
  const ref = useRef(null);
  useLayoutEffect(() => {
    if(!folded && ref.current) measure(group.id, ref.current.offsetWidth);
  });
  if(folded || !isGroupVisible(group, state)) return null;
  return <div ref={ref} className="snb-group" role="group"
    aria-label={group.label || undefined} data-snb-group={group.id}>
    <div className="snb-group-body">
      {group.controls.map((control, index) => <Control
        key={control.id ?? `separator-${index}`} control={control}
        state={state} onCommand={onCommand} hints={hints} messages={messages} />)}
    </div>
    {group.label && <div className="snb-group-label" aria-hidden="true">
      {group.label}</div>}
  </div>;
}
Group.propTypes = {
  group: PropTypes.object.isRequired, state: PropTypes.object,
  onCommand: PropTypes.func.isRequired, hints: PropTypes.object,
  folded: PropTypes.bool, measure: PropTypes.func.isRequired,
  messages: PropTypes.object,
};

function OverflowMenu({groups, state, onCommand, hints, open, setOpen, messages}) {
  const ref = useRef(null);
  if(groups.length === 0) return null;
  return <>
    <button ref={ref} type="button" className="snb-control snb-large snb-overflow"
      data-snb-control={OVERFLOW_ID} data-snb-focusable="" tabIndex={-1}
      aria-haspopup="menu" aria-expanded={open}
      onClick={() => setOpen(!open)}>
      <span className="snb-label">{message(messages, 'more')}</span>
      <span className="snb-arrow" aria-hidden="true" />
      {hints?.[OVERFLOW_ID] && <span className="snb-hint" aria-hidden="true">
        {hints[OVERFLOW_ID]}</span>}
    </button>
    {open && <Popup anchor={ref.current} label={message(messages, 'moreCommands')}
      role="dialog"
      onClose={(restore) => { setOpen(false); if(restore) ref.current?.focus(); }}>
      {groups.map((group) => <div key={group.id} className="snb-overflow-group"
        role="group" aria-label={group.label || undefined}>
        {group.label && <div className="snb-group-label">{group.label}</div>}
        <div className="snb-group-body" style={{flexWrap: 'wrap'}}>
          {group.controls.map((control, index) => <Control
            key={control.id ?? `separator-${index}`} control={control}
            state={state} onCommand={(command, detail) => {
              setOpen(false);
              onCommand(command, detail);
            }} hints={hints} messages={messages} inMenu />)}
        </div>
      </div>)}
    </Popup>}
  </>;
}
OverflowMenu.propTypes = {
  groups: PropTypes.array.isRequired, state: PropTypes.object,
  onCommand: PropTypes.func.isRequired, hints: PropTypes.object,
  open: PropTypes.bool, setOpen: PropTypes.func.isRequired,
  messages: PropTypes.object,
};

export function NotebookBar({model, state={}, context, onCommand, selectedTab,
  onSelectTab, collapsed, onCollapsedChange, start, end, contributions,
  customization, catalog, label='Commands', dir, injectStyles=true,
  accessKeyTrigger='Alt', messages}) {
  useNotebookBarStyles(injectStyles);
  const id = useId();
  const barRef = useRef(null);
  const stripRef = useRef(null);
  const panelRef = useRef(null);
  const quickRef = useRef(null);
  const resolved = useMemo(() => {
    let value = normalizeModel(model);
    if(contributions?.length) value = mergeContributions(value, contributions);
    if(customization) value = applyCustomization(value, customization, catalog);
    return value;
  }, [model, contributions, customization, catalog]);
  const tabs = useMemo(() => visibleTabs(resolved, context),
    [resolved, context]);
  const [selected, setSelected] = useControlled(selectedTab, resolved.defaultTab);
  const [isCollapsed, setCollapsed] = useControlled(collapsed, false);
  const [peek, setPeek] = useState(false);
  const [overflowOpen, setOverflowOpen] = useState(false);
  const [layer, setLayer] = useState(0); // access-key hints: 0 off, 1 tabs, 2 panel
  const [typed, setTyped] = useState('');
  const previousTab = useRef(null);
  const returnFocus = useRef(null);
  const widths = useRef(new Map());
  const [panelWidth, setPanelWidth] = useState(null);
  const [measured, setMeasured] = useState(0);

  const current = tabs.find((tab) => tab.id === selected) ??
    tabs.find((tab) => tab.id === resolved.defaultTab) ?? tabs[0];
  const select = useCallback((tabId) => {
    setSelected(tabId);
    onSelectTab?.(tabId);
  }, [onSelectTab, setSelected]);
  const setCollapsedState = (value) => {
    setCollapsed(value);
    setPeek(false);
    onCollapsedChange?.(value);
  };

  // Contextual tabs: select one when its context appears, return when it goes.
  const shownIds = tabs.map((tab) => tab.id).join('\u0000');
  const lastShown = useRef(new Set(tabs.map((tab) => tab.id)));
  useEffect(() => {
    const now = new Set(tabs.map((tab) => tab.id));
    const appeared = tabs.find((tab) => !lastShown.current.has(tab.id) &&
      tab.context.length > 0 && tab.selectOnContext);
    if(appeared) {
      previousTab.current = current?.id ?? null;
      select(appeared.id);
    } else if(selected && !now.has(selected) && lastShown.current.has(selected)) {
      const back = previousTab.current && now.has(previousTab.current) ?
        previousTab.current : resolved.defaultTab;
      if(back) select(back);
    }
    lastShown.current = now;
  }, [shownIds]);

  // Overflow: measure group widths, fold what does not fit.
  const measure = useCallback((groupId, width) => {
    if(width > 0 && widths.current.get(groupId) !== width) {
      widths.current.set(groupId, width);
      setMeasured((value) => value + 1);
    }
  }, []);
  useLayoutEffect(() => {
    const panel = panelRef.current;
    if(!panel || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(([entry]) =>
      setPanelWidth(entry.contentRect.width));
    observer.observe(panel);
    return () => observer.disconnect();
  }, [isCollapsed, peek]);
  const visibleGroups = (current?.groups ?? []).filter((group) =>
    isGroupVisible(group, state));
  const folded = useMemo(() => {
    if(panelWidth === null || visibleGroups.some((group) =>
      !widths.current.has(group.id))) return new Set();
    return foldGroups(panelWidth, visibleGroups.map((group) => ({id: group.id,
      width: widths.current.get(group.id), priority: group.priority})));
  }, [panelWidth, measured, current, state]);
  const foldedGroups = visibleGroups.filter((group) => folded.has(group.id));

  // Access keys for the current layer.
  const hintKeys = useMemo(() => {
    if(layer === 1) {
      const quick = flattenControls(resolved.quickAccess)
        .filter((control) => isControlVisible(control, state));
      return assignAccessKeys([...tabs.map((tab) => ({id: `tab:${tab.id}`,
        label: tab.label, accessKey: tab.accessKey})), ...quick]);
    }
    if(layer === 2) {
      const controls = visibleGroups.filter((group) => !folded.has(group.id))
        .flatMap((group) => flattenControls(group.controls))
        .filter((control) => control.type !== 'separator' &&
          isControlVisible(control, state));
      const items = foldedGroups.length ?
        [...controls, {id: OVERFLOW_ID, label: message(messages, 'more')}] : controls;
      return assignAccessKeys(items);
    }
    return new Map();
  }, [layer, tabs, resolved, state, current, folded]);
  const hints = useMemo(() => {
    const result = {};
    for(const [key, value] of hintKeys) {
      if(value.startsWith(typed.toUpperCase())) result[key] = value;
    }
    return result;
  }, [hintKeys, typed]);

  const endHints = (restore) => {
    setLayer(0);
    setTyped('');
    if(restore) returnFocus.current?.focus?.();
    returnFocus.current = null;
  };
  const activate = (controlId) => {
    const element = barRef.current?.querySelector(
      byAttribute('data-snb-control', controlId));
    const target = element?.matches('[data-snb-focusable]') ? element :
      element?.querySelector('[data-snb-focusable]');
    target?.focus();
    target?.click();
  };

  // Alt pressed and released alone shows the hints.
  useEffect(() => {
    if(!accessKeyTrigger) return undefined;
    let alone = false;
    const down = (event) => {
      alone = event.key === accessKeyTrigger && !event.ctrlKey &&
        !event.metaKey && !event.shiftKey;
    };
    const up = (event) => {
      if(event.key === accessKeyTrigger && alone) {
        event.preventDefault();
        if(layer) {
          endHints(true);
        } else {
          returnFocus.current = document.activeElement;
          setTyped('');
          setLayer(1);
          stripRef.current?.querySelector('[aria-selected="true"]')?.focus();
        }
      }
      alone = false;
    };
    // Alt with a click, drag (an editor's column selection), wheel, or a
    // switch away from the window is not a request for hints.
    const cancel = () => { alone = false; };
    window.addEventListener('keydown', down, true);
    window.addEventListener('keyup', up, true);
    window.addEventListener('pointerdown', cancel, true);
    window.addEventListener('mousedown', cancel, true);
    window.addEventListener('wheel', cancel, true);
    window.addEventListener('blur', cancel);
    return () => {
      window.removeEventListener('keydown', down, true);
      window.removeEventListener('keyup', up, true);
      window.removeEventListener('pointerdown', cancel, true);
      window.removeEventListener('mousedown', cancel, true);
      window.removeEventListener('wheel', cancel, true);
      window.removeEventListener('blur', cancel);
    };
  }, [accessKeyTrigger, layer]);

  const onHintKey = (event) => {
    if(!layer || event.ctrlKey || event.metaKey || event.altKey) return false;
    if(event.key === 'Escape') {
      event.preventDefault();
      if(layer === 2) {
        setLayer(1);
        setTyped('');
      } else {
        endHints(true);
      }
      return true;
    }
    if(!/^[a-z0-9]$/i.test(event.key)) return false;
    event.preventDefault();
    const next = typed + event.key.toUpperCase();
    const {match, candidates} = matchAccessKey(hintKeys, next);
    if(match) {
      setTyped('');
      if(match.startsWith('tab:')) {
        const tabId = match.slice(4);
        select(tabId);
        if(isCollapsed) setPeek(true);
        setLayer(2);
        requestAnimationFrame(() => focusables(panelRef.current)[0]?.focus());
      } else {
        endHints(false);
        activate(match);
      }
    } else {
      setTyped(candidates.length ? next : '');
    }
    return true;
  };

  const onBarKeyDown = (event) => {
    if(onHintKey(event)) return;
    if(event.ctrlKey && event.key === 'F1') {
      event.preventDefault();
      setCollapsedState(!isCollapsed);
      return;
    }
    if(event.key === 'Escape' && peek) {
      setPeek(false);
      stripRef.current?.querySelector('[aria-selected="true"]')?.focus();
    }
  };

  const rtl = () => {
    const element = barRef.current;
    const declared = element?.closest('[dir]')?.getAttribute('dir');
    return declared ? declared === 'rtl' :
      Boolean(element) && getComputedStyle(element).direction === 'rtl';
  };
  const onTabKeyDown = (event, index) => {
    const forward = rtl() ? 'ArrowLeft' : 'ArrowRight';
    const back = rtl() ? 'ArrowRight' : 'ArrowLeft';
    const move = {[forward]: index + 1, [back]: index - 1, Home: 0,
      End: tabs.length - 1}[event.key];
    if(move !== undefined) {
      event.preventDefault();
      const target = tabs[(move + tabs.length) % tabs.length];
      stripRef.current?.querySelector(byAttribute('data-snb-tab', target.id))
        ?.focus();
    } else if(event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      select(tabs[index].id);
      if(isCollapsed) setPeek(true);
    } else if(event.key === 'ArrowDown') {
      event.preventDefault();
      if(isCollapsed) setPeek(true);
      requestAnimationFrame(() => {
        const first = focusables(panelRef.current)[0];
        setRoving(panelRef.current, first);
        first?.focus();
      });
    }
  };
  const onControlsKeyDown = (event) => {
    const root = event.currentTarget;
    const items = focusables(root);
    const index = items.indexOf(document.activeElement);
    if(index < 0) return;
    const forward = rtl() ? 'ArrowLeft' : 'ArrowRight';
    const back = rtl() ? 'ArrowRight' : 'ArrowLeft';
    const move = {[forward]: index + 1, [back]: index - 1, Home: 0,
      End: items.length - 1}[event.key];
    if(move !== undefined && document.activeElement.tagName !== 'SELECT') {
      event.preventDefault();
      const next = items[(move + items.length) % items.length];
      setRoving(root, next);
      next.focus();
    } else if(event.key === 'ArrowUp' && root === panelRef.current &&
        document.activeElement.tagName !== 'SELECT') {
      event.preventDefault();
      stripRef.current?.querySelector('[aria-selected="true"]')?.focus();
    }
  };
  // Keep exactly one tabbable control in the panel and the quick bar.
  useLayoutEffect(() => {
    for(const root of [panelRef.current, quickRef.current]) {
      const items = focusables(root);
      if(items.length && !items.some((element) => element.tabIndex === 0)) {
        setRoving(root, items[0]);
      }
    }
  });

  // Hints and peeking end when focus or a click leaves the bar.
  useEffect(() => {
    if(!layer && !peek) return undefined;
    const outside = (event) => {
      if(barRef.current?.contains(event.target) ||
          event.target.closest?.('.snb-popup')) return;
      if(layer) endHints(false);
      setPeek(false);
    };
    document.addEventListener('mousedown', outside);
    document.addEventListener('focusin', outside);
    return () => {
      document.removeEventListener('mousedown', outside);
      document.removeEventListener('focusin', outside);
    };
  }, [layer, peek]);

  const runCommand = (command, detail) => {
    if(layer) endHints(false);
    setPeek(false);
    onCommand?.(command, detail);
  };

  const panelId = `${id}-panel`;
  const showPanel = current && (!isCollapsed || peek);
  return <div ref={barRef} className={`snb-bar${isCollapsed ? ' snb-collapsed' : ''}${
    peek ? ' snb-peek' : ''}`} role="region" aria-label={label} dir={dir}
  data-snb-access-keys={layer ? String(layer) : undefined}
  onKeyDown={onBarKeyDown}>
    <div className="snb-strip">
      {start && <div className="snb-start">{start}</div>}
      {resolved.quickAccess.length > 0 && <div ref={quickRef} className="snb-quick"
        role="toolbar" aria-label={message(messages, 'quickAccess')}
        onKeyDown={onControlsKeyDown}>
        {resolved.quickAccess.map((control, index) => <Control
          key={control.id ?? `separator-${index}`} control={control} state={state}
          onCommand={runCommand} hints={layer === 1 ? hints : undefined}
          messages={messages} />)}
      </div>}
      <div ref={stripRef} className="snb-tabs" role="tablist" aria-label={label}>
        {tabs.map((tab, index) => {
          const isSelected = tab.id === current?.id;
          return <button key={tab.id} type="button" role="tab"
            id={`${id}-tab-${tab.id}`} data-snb-tab={tab.id}
            className={`snb-tab${tab.context.length ? ' snb-contextual' : ''}`}
            aria-selected={isSelected} aria-controls={showPanel && isSelected ?
              panelId : undefined}
            aria-expanded={isCollapsed ? Boolean(peek && isSelected) : undefined}
            tabIndex={isSelected ? 0 : -1}
            onClick={() => {
              if(isCollapsed) setPeek(!(peek && isSelected));
              select(tab.id);
            }}
            onDoubleClick={() => setCollapsedState(!isCollapsed)}
            onKeyDown={(event) => onTabKeyDown(event, index)}>
            {tab.label}
            {layer === 1 && hints[`tab:${tab.id}`] && <span className="snb-hint"
              aria-hidden="true">{hints[`tab:${tab.id}`]}</span>}
          </button>;
        })}
      </div>
      {end && <div className="snb-end">{end}</div>}
    </div>
    {showPanel && <div ref={panelRef} id={panelId} className="snb-panel"
      role="tabpanel" aria-labelledby={`${id}-tab-${current.id}`}
      onKeyDown={onControlsKeyDown}>
      {current.groups.map((group) => <Group key={group.id} group={group}
        state={state} onCommand={runCommand} measure={measure} messages={messages}
        hints={layer === 2 ? hints : undefined} folded={folded.has(group.id)} />)}
      <OverflowMenu groups={foldedGroups} state={state} onCommand={runCommand}
        hints={layer === 2 ? hints : undefined} open={overflowOpen}
        setOpen={setOverflowOpen} messages={messages} />
    </div>}
  </div>;
}

NotebookBar.propTypes = {
  model: PropTypes.object.isRequired,
  state: PropTypes.object,
  context: PropTypes.oneOfType([PropTypes.string, PropTypes.array]),
  onCommand: PropTypes.func,
  selectedTab: PropTypes.string,
  onSelectTab: PropTypes.func,
  collapsed: PropTypes.bool,
  onCollapsedChange: PropTypes.func,
  start: PropTypes.node,
  end: PropTypes.node,
  contributions: PropTypes.array,
  customization: PropTypes.object,
  catalog: PropTypes.object,
  label: PropTypes.string,
  dir: PropTypes.oneOf(['ltr', 'rtl']),
  injectStyles: PropTypes.bool,
  accessKeyTrigger: PropTypes.string,
  messages: PropTypes.object,
};
