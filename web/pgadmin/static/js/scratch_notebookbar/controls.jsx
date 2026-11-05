/////////////////////////////////////////////////////////////
//
// Scratch notebook bar
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// The bar's controls and its popup menu. Plain elements and ARIA; no
// dependency beyond React.

import {useEffect, useLayoutEffect, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import PropTypes from 'prop-types';
import {commandState, isControlEnabled, isControlVisible} from './model';
import {message} from './messages';

export function renderIcon(icon, size) {
  if(!icon) return null;
  return <span className="snb-icon" aria-hidden="true">
    {typeof icon === 'function' ? icon(size) : icon}
  </span>;
}

function tooltip(control, state) {
  const label = commandState(state, control).label ?? control.label;
  const text = control.tooltip ?? label;
  return control.shortcut ? `${text} (${control.shortcut})` : text;
}

function Hint({value}) {
  return value ? <span className="snb-hint" aria-hidden="true">{value}</span> : null;
}
Hint.propTypes = {value: PropTypes.string};

/**
 * A popup menu anchored to an element. Up/Down/Home/End move, Enter or Space
 * chooses, Escape or a click outside closes and returns focus to the anchor.
 */
export function Popup({anchor, label, onClose, children, role='menu'}) {
  const ref = useRef(null);
  const [position, setPosition] = useState(null);
  useLayoutEffect(() => {
    const rect = anchor?.getBoundingClientRect?.();
    if(!rect) return;
    const rtl = getComputedStyle(anchor).direction === 'rtl';
    setPosition({top: rect.bottom, ...(rtl ?
      {right: window.innerWidth - rect.right} : {left: rect.left})});
  }, [anchor]);
  // Focus the first item once the popup is positioned (it renders nothing
  // before that).
  useEffect(() => {
    if(!position) return;
    ref.current?.querySelector(
      '[role^="menuitem"]:not([aria-disabled="true"]), [role="option"], button')
      ?.focus();
  }, [Boolean(position)]);
  useEffect(() => {
    const outside = (event) => {
      if(!ref.current?.contains(event.target) && !anchor?.contains(event.target)) {
        onClose(false);
      }
    };
    document.addEventListener('mousedown', outside);
    return () => document.removeEventListener('mousedown', outside);
  }, []);
  const onKeyDown = (event) => {
    const items = [...ref.current.querySelectorAll(
      '[role^="menuitem"]:not([aria-disabled="true"]), [role="option"]')];
    const index = items.indexOf(document.activeElement);
    const move = {ArrowDown: index + 1, ArrowUp: index - 1, Home: 0,
      End: items.length - 1}[event.key];
    if(move !== undefined && items.length) {
      event.preventDefault();
      items[(move + items.length) % items.length].focus();
    } else if(event.key === 'Escape' || event.key === 'Tab') {
      event.preventDefault();
      event.stopPropagation();
      onClose(true);
    }
  };
  if(!position) return null;
  return createPortal(<div ref={ref} className="snb-popup" role={role}
    aria-label={label} style={position} onKeyDown={onKeyDown}>
    {children}
  </div>, document.body);
}
Popup.propTypes = {
  anchor: PropTypes.object, label: PropTypes.string,
  onClose: PropTypes.func.isRequired, children: PropTypes.node,
  role: PropTypes.string,
};

function MenuItems({items, onChoose}) {
  return items.map((item, index) => item.type === 'separator' ?
    <div key={`separator-${index}`} className="snb-popup-separator" role="separator" /> :
    <button key={item.id} type="button" className="snb-popup-item"
      role={item.checked === undefined ? 'menuitem' : 'menuitemcheckbox'}
      aria-checked={item.checked === undefined ? undefined : Boolean(item.checked)}
      aria-disabled={item.disabled ? 'true' : undefined} tabIndex={-1}
      onClick={() => !item.disabled && onChoose(item)}>
      {renderIcon(item.icon, 'small')}<span>{item.label}</span>
    </button>);
}

/** The props every control receives from its group. */
export const controlProps = {
  control: PropTypes.object.isRequired,
  state: PropTypes.object,
  onCommand: PropTypes.func.isRequired,
  hints: PropTypes.object,
  inMenu: PropTypes.bool,
  messages: PropTypes.object,
};

function buttonClass(control, extra='') {
  return `snb-control${control.size === 'large' ? ' snb-large' : ''}${extra}`;
}

function ButtonBody({control, state, showLabel}) {
  const label = commandState(state, control).label ?? control.label;
  return <>
    {renderIcon(control.icon, control.size)}
    {showLabel && <span className="snb-label">{label}</span>}
  </>;
}
ButtonBody.propTypes = {control: PropTypes.object, state: PropTypes.object,
  showLabel: PropTypes.bool};

function showsLabel(control, inMenu) {
  return inMenu || control.size === 'large' || control.showLabel !== false ||
    !control.icon;
}

export function CommandButton({control, state, onCommand, hints, inMenu}) {
  const enabled = isControlEnabled(control, state);
  const toggle = control.type === 'toggle';
  const checked = Boolean(commandState(state, control).checked);
  const label = commandState(state, control).label ?? control.label;
  return <button type="button" className={buttonClass(control)}
    data-snb-control={control.id} data-snb-focusable=""
    aria-label={showsLabel(control, inMenu) ? undefined : label}
    aria-pressed={toggle ? checked : undefined}
    aria-disabled={enabled ? undefined : 'true'}
    aria-keyshortcuts={control.shortcut}
    title={tooltip(control, state)} tabIndex={-1}
    onClick={() => enabled && onCommand(control.command,
      toggle ? {checked: !checked} : {})}>
    <ButtonBody control={control} state={state}
      showLabel={showsLabel(control, inMenu)} />
    <Hint value={hints?.[control.id]} />
  </button>;
}
CommandButton.propTypes = controlProps;

function itemCommand(control, item) {
  return item.command ?? control.command;
}

export function MenuControl({control, state, onCommand, hints, inMenu, messages}) {
  const [open, setOpen] = useState(false);
  const main = useRef(null);
  const arrow = useRef(null);
  const enabled = isControlEnabled(control, state);
  const split = control.type === 'split';
  const label = commandState(state, control).label ?? control.label;
  const close = (restore) => {
    setOpen(false);
    if(restore) (split ? arrow : main).current?.focus();
  };
  const choose = (item) => {
    close(true);
    onCommand(itemCommand(control, item), {item: item.id});
  };
  const opener = {
    'aria-haspopup': 'menu', 'aria-expanded': open,
    onClick: () => enabled && setOpen(!open),
    onKeyDown: (event) => {
      if(enabled && (event.key === 'ArrowDown' && (event.altKey || !split))) {
        event.preventDefault();
        event.stopPropagation();
        setOpen(true);
      }
    },
  };
  const popup = open && <Popup anchor={(split ? arrow : main).current}
    label={label} onClose={close}>
    <MenuItems items={control.items} onChoose={choose} />
  </Popup>;
  if(!split) {
    return <>
      <button ref={main} type="button" className={buttonClass(control)}
        data-snb-control={control.id} data-snb-focusable=""
        aria-label={showsLabel(control, inMenu) ? undefined : label}
        aria-disabled={enabled ? undefined : 'true'} title={tooltip(control, state)}
        tabIndex={-1} {...opener}>
        <ButtonBody control={control} state={state}
          showLabel={showsLabel(control, inMenu)} />
        <span className="snb-arrow" aria-hidden="true" />
        <Hint value={hints?.[control.id]} />
      </button>
      {popup}
    </>;
  }
  return <span className={`snb-split${control.size === 'large' ?
    ' snb-large-split' : ''}`} data-snb-control={control.id}>
    <button ref={main} type="button" className={buttonClass(control)}
      data-snb-focusable="" aria-disabled={enabled ? undefined : 'true'}
      aria-label={showsLabel(control, inMenu) ? undefined : label}
      aria-keyshortcuts={control.shortcut}
      title={tooltip(control, state)} tabIndex={-1}
      onKeyDown={opener.onKeyDown}
      onClick={() => enabled && onCommand(control.command, {})}>
      <ButtonBody control={control} state={state}
        showLabel={showsLabel(control, inMenu)} />
      <Hint value={hints?.[control.id]} />
    </button>
    <button ref={arrow} type="button" className="snb-control snb-arrow"
      data-snb-focusable="" aria-label={message(messages, 'options', {label})}
      aria-disabled={enabled ? undefined : 'true'} tabIndex={-1} {...opener} />
    {popup}
  </span>;
}
MenuControl.propTypes = controlProps;

export function SelectControl({control, state, onCommand, hints}) {
  const enabled = isControlEnabled(control, state);
  const value = commandState(state, control).value ?? '';
  return <span className="snb-control-wrap" style={{position: 'relative'}}>
    <select className="snb-select" data-snb-control={control.id}
      data-snb-focusable="" aria-label={control.label} title={tooltip(control, state)}
      disabled={!enabled} value={value} tabIndex={-1}
      style={control.width ? {width: control.width} : undefined}
      onChange={(event) => onCommand(control.command, {value: event.target.value})}>
      {!control.options.some((option) => option.value === value) &&
        <option value={value} disabled>{value}</option>}
      {control.options.map((option) => <option key={option.value}
        value={option.value}>{option.label}</option>)}
    </select>
    <Hint value={hints?.[control.id]} />
  </span>;
}
SelectControl.propTypes = controlProps;

export function ColorControl({control, state, onCommand, hints, messages}) {
  const [open, setOpen] = useState(false);
  const arrow = useRef(null);
  const enabled = isControlEnabled(control, state);
  const value = commandState(state, control).value ?? control.defaultValue ?? '';
  const choose = (color) => {
    setOpen(false);
    arrow.current?.focus();
    onCommand(control.command, {value: color});
  };
  return <span className="snb-split" data-snb-control={control.id}>
    <button type="button" className={buttonClass(control)} data-snb-focusable=""
      aria-label={`${control.label} ${value}`.trim()}
      aria-disabled={enabled && value ? undefined : 'true'} tabIndex={-1}
      title={tooltip(control, state)}
      onClick={() => enabled && value && onCommand(control.command, {value})}>
      <span style={{display: 'inline-flex', flexDirection: 'column',
        alignItems: 'stretch'}}>
        {renderIcon(control.icon, control.size)}
        <span className="snb-swatch" style={{background: value || 'transparent'}} />
      </span>
      {control.size === 'large' && <span className="snb-label">{control.label}</span>}
      <Hint value={hints?.[control.id]} />
    </button>
    <button ref={arrow} type="button" className="snb-control snb-arrow"
      data-snb-focusable=""
      aria-label={message(messages, 'options', {label: control.label})}
      aria-haspopup="menu" aria-expanded={open}
      aria-disabled={enabled ? undefined : 'true'} tabIndex={-1}
      onClick={() => enabled && setOpen(!open)} />
    {open && <Popup anchor={arrow.current} label={control.label}
      onClose={(restore) => { setOpen(false); if(restore) arrow.current?.focus(); }}>
      <div className="snb-palette">
        {(control.palette ?? []).map((color) => <button key={color} type="button"
          role="menuitemradio" aria-checked={color === value} aria-label={color}
          title={color} tabIndex={-1} style={{background: color}}
          onClick={() => choose(color)} />)}
      </div>
    </Popup>}
  </span>;
}
ColorControl.propTypes = controlProps;

export function GalleryControl({control, state, onCommand, hints, messages}) {
  const [open, setOpen] = useState(false);
  const more = useRef(null);
  const enabled = isControlEnabled(control, state);
  const value = commandState(state, control).value;
  const inline = control.items.slice(0, control.inlineItems ?? 4);
  const choose = (item) => {
    setOpen(false);
    onCommand(item.command ?? control.command, {item: item.id});
  };
  const item = (entry, inPopup) => <button key={entry.id} type="button"
    className="snb-gallery-item" role={inPopup ? 'menuitemradio' : 'radio'}
    aria-checked={entry.id === value} aria-disabled={enabled ? undefined : 'true'}
    title={entry.label} tabIndex={-1} data-snb-focusable={inPopup ? undefined : ''}
    onClick={() => enabled && choose(entry)}>
    {renderIcon(entry.icon, 'large')}<span>{entry.label}</span>
  </button>;
  return <span className="snb-split" data-snb-control={control.id}
    style={{position: 'relative'}}>
    <span className="snb-gallery" role="radiogroup" aria-label={control.label}>
      {inline.map((entry) => item(entry, false))}
    </span>
    <button ref={more} type="button" className="snb-control snb-arrow"
      data-snb-focusable=""
      aria-label={message(messages, 'moreItems', {label: control.label})}
      aria-haspopup="menu" aria-expanded={open} tabIndex={-1}
      aria-disabled={enabled ? undefined : 'true'}
      onClick={() => enabled && setOpen(!open)} />
    <Hint value={hints?.[control.id]} />
    {open && <Popup anchor={more.current} label={control.label}
      onClose={(restore) => { setOpen(false); if(restore) more.current?.focus(); }}>
      <div className="snb-palette" style={{gridTemplateColumns: 'repeat(4, auto)'}}>
        {control.items.map((entry) => item(entry, true))}
      </div>
    </Popup>}
  </span>;
}
GalleryControl.propTypes = controlProps;

export function Control(props) {
  const {control, state} = props;
  if(!isControlVisible(control, state)) return null;
  switch(control.type) {
  case 'separator':
    return <span className="snb-separator" role="separator" aria-orientation="vertical" />;
  case 'stack':
    return <span className="snb-stack">
      {control.controls.map((child) => <Control key={child.id} {...props}
        control={child} />)}
    </span>;
  case 'menu':
  case 'split':
    return <MenuControl {...props} />;
  case 'select':
    return <SelectControl {...props} />;
  case 'color':
    return <ColorControl {...props} />;
  case 'gallery':
    return <GalleryControl {...props} />;
  default:
    return <CommandButton {...props} />;
  }
}
Control.propTypes = controlProps;
