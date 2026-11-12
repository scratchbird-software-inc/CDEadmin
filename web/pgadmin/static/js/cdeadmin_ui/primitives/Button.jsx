/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {forwardRef, useEffect, useRef} from 'react';
import PropTypes from 'prop-types';
import {Button as BaseButton} from '@base-ui/react/button';
import {ensureScratchBaseStyles} from '../base/ScratchBaseStyles';

function InlineSpinner() {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
      style={{flexShrink: 0}}
    >
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
      <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function normalizeSxStyle(sx, style) {
  if (!sx || typeof sx !== 'object') return style;
  const mapped = {};
  if (sx.display) mapped.display = sx.display;
  if (sx.width) mapped.width = sx.width;
  if (sx.minWidth !== undefined) mapped.minWidth = sx.minWidth;
  if (sx.minHeight !== undefined) mapped.minHeight = sx.minHeight;
  if (sx.justifyContent) mapped.justifyContent = sx.justifyContent;
  if (sx.alignSelf) mapped.alignSelf = sx.alignSelf;
  if (sx.ml === 'auto') mapped.marginLeft = 'auto';
  return {...mapped, ...style};
}

export const Button = forwardRef(function Button({
  intent = 'neutral',
  loading = false,
  children,
  onClick,
  startIcon,
  endIcon,
  className = '',
  style,
  sx,
  disabled = false,
  // Strip legacy MUI-only presentation props so DOM attributes stay clean
  // eslint-disable-next-line no-unused-vars
  variant,
  // eslint-disable-next-line no-unused-vars
  size,
  // eslint-disable-next-line no-unused-vars
  color,
  // eslint-disable-next-line no-unused-vars
  disableElevation,
  ...props
}, ref) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);

  const lastMouseActivation = useRef(0);
  const isDisabled = Boolean(loading || disabled);
  const invokeOnce = (event) => {
    if (isDisabled) return;
    if (event.detail > 0) {
      const now = Date.now();
      if (now - lastMouseActivation.current <= 500) return;
      lastMouseActivation.current = now;
    }
    onClick?.(event);
  };

  const intentClass = intent === 'primary'
    ? 'sr-btn-primary'
    : (intent === 'destructive' || intent === 'error')
      ? 'sr-btn-destructive'
      : '';

  return (
    <BaseButton
      ref={ref}
      type={props.type || 'button'}
      {...props}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      onClick={invokeOnce}
      className={['sr-btn', intentClass, className].filter(Boolean).join(' ')}
      style={normalizeSxStyle(sx, style)}
    >
      {loading ? <InlineSpinner /> : startIcon}
      {children}
      {endIcon}
    </BaseButton>
  );
});

Button.propTypes = {
  intent: PropTypes.oneOf([
    'neutral', 'primary', 'destructive', 'error', 'success', 'warning',
  ]),
  loading: PropTypes.bool,
  disabled: PropTypes.bool,
  children: PropTypes.node,
  onClick: PropTypes.func,
  startIcon: PropTypes.node,
  endIcon: PropTypes.node,
  className: PropTypes.string,
  style: PropTypes.object,
  sx: PropTypes.object,
  type: PropTypes.string,
  variant: PropTypes.string,
  size: PropTypes.string,
  color: PropTypes.string,
  disableElevation: PropTypes.bool,
};

export const IconButton = forwardRef(function IconButton({
  label,
  title,
  icon,
  children,
  className = '',
  style,
  sx,
  disabled = false,
  // Strip legacy MUI-only presentation props
  // eslint-disable-next-line no-unused-vars
  edge,
  // eslint-disable-next-line no-unused-vars
  size,
  // eslint-disable-next-line no-unused-vars
  color,
  ...props
}, ref) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);

  const accessibleLabel = label || title;
  if (!accessibleLabel) {
    throw new TypeError('IconButton requires a label or title.');
  }

  return (
    <BaseButton
      ref={ref}
      type={props.type || 'button'}
      {...props}
      disabled={disabled}
      aria-label={accessibleLabel}
      title={title || accessibleLabel}
      className={['sr-icon-btn', className].filter(Boolean).join(' ')}
      style={normalizeSxStyle(sx, style)}
    >
      {icon ?? children}
    </BaseButton>
  );
});

IconButton.propTypes = {
  label: PropTypes.string,
  title: PropTypes.string,
  icon: PropTypes.node,
  children: PropTypes.node,
  className: PropTypes.string,
  style: PropTypes.object,
  sx: PropTypes.object,
  disabled: PropTypes.bool,
  type: PropTypes.string,
  edge: PropTypes.string,
  size: PropTypes.string,
  color: PropTypes.string,
};
