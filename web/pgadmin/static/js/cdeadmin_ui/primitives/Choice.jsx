/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useId, useState} from 'react';
import PropTypes from 'prop-types';
import {Checkbox as BaseCheckbox} from '@base-ui/react/checkbox';
import {Switch as BaseSwitch} from '@base-ui/react/switch';
import {Select as BaseSelect} from '@base-ui/react/select';
import {ensureScratchBaseStyles} from '../base/ScratchBaseStyles';

export function Checkbox({
  label,
  checked = false,
  indeterminate = false,
  disabled = false,
  onChange,
  inputProps,
  className = '',
  style,
  // eslint-disable-next-line no-unused-vars
  sx,
  ...props
}) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);

  const ariaLabel = props['aria-label'] || inputProps?.['aria-label'] || undefined;
  const ariaDescribedBy = props['aria-describedby'] || inputProps?.['aria-describedby'] || undefined;
  const qaKey = props['data-cdeadmin-qa-key'] || inputProps?.['data-cdeadmin-qa-key'] || undefined;

  return (
    <label
      className={['sr-choice-label', className].filter(Boolean).join(' ')}
      data-disabled={disabled ? 'true' : undefined}
      style={style}
      onClick={(e) => e.stopPropagation()}
    >
      <BaseCheckbox.Root
        ref={(el) => {
          if (el) el.checked = Boolean(checked);
        }}
        nativeButton
        render={<button type="button" />}
        checked={Boolean(checked)}
        indeterminate={Boolean(indeterminate)}
        disabled={Boolean(disabled)}
        aria-label={ariaLabel}
        aria-describedby={ariaDescribedBy}
        data-cdeadmin-qa-key={qaKey}
        onCheckedChange={(nextChecked, details) => {
          onChange?.(nextChecked, details?.event);
        }}
        className="sr-checkbox-root"
        {...props}
      >
        <BaseCheckbox.Indicator style={{display: 'inline-flex', alignItems: 'center', justifyContent: 'center'}}>
          {indeterminate ? (
            <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
              <line x1="2.5" y1="6" x2="9.5" y2="6" strokeLinecap="round" />
            </svg>
          ) : (
            <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
              <polyline points="2 6.5 4.8 9.2 10 3" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </BaseCheckbox.Indicator>
      </BaseCheckbox.Root>
      {label ? <span>{label}</span> : null}
    </label>
  );
}

Checkbox.propTypes = {
  label: PropTypes.node.isRequired,
  checked: PropTypes.bool,
  indeterminate: PropTypes.bool,
  disabled: PropTypes.bool,
  onChange: PropTypes.func,
  inputProps: PropTypes.object,
  'aria-label': PropTypes.string,
  className: PropTypes.string,
  style: PropTypes.object,
  sx: PropTypes.object,
};

export function Switch({
  label,
  checked = false,
  disabled = false,
  onChange,
  inputProps,
  className = '',
  style,
  // eslint-disable-next-line no-unused-vars
  sx,
  ...props
}) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);

  const ariaLabel = props['aria-label'] || inputProps?.['aria-label'] || undefined;

  return (
    <label
      className={['sr-choice-label', className].filter(Boolean).join(' ')}
      data-disabled={disabled ? 'true' : undefined}
      style={style}
      onClick={(e) => e.stopPropagation()}
    >
      <BaseSwitch.Root
        nativeButton
        render={<button type="button" />}
        checked={Boolean(checked)}
        disabled={Boolean(disabled)}
        aria-label={ariaLabel}
        onCheckedChange={(nextChecked, details) => {
          onChange?.(nextChecked, details?.event);
        }}
        className="sr-switch-root"
        {...props}
      >
        <BaseSwitch.Thumb className="sr-switch-thumb" />
      </BaseSwitch.Root>
      {label ? <span>{label}</span> : null}
    </label>
  );
}

Switch.propTypes = {
  label: PropTypes.node.isRequired,
  checked: PropTypes.bool,
  disabled: PropTypes.bool,
  onChange: PropTypes.func,
  inputProps: PropTypes.object,
  'aria-label': PropTypes.string,
  className: PropTypes.string,
  style: PropTypes.object,
  sx: PropTypes.object,
};

export function Select({
  options = [],
  value = '',
  onChange,
  label,
  disabled = false,
  required = false,
  validationMessage,
  error = false,
  helperText,
  placeholder = '',
  inputProps,
  className = '',
  style,
  sx,
  // Strip legacy MUI-only props
  // eslint-disable-next-line no-unused-vars
  InputLabelProps,
  // eslint-disable-next-line no-unused-vars
  size,
  // eslint-disable-next-line no-unused-vars
  fullWidth,
  ...props
}) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);

  const [open, setOpen] = useState(false);
  const labelId = useId();
  const helpId = inputProps?.['aria-describedby'] || `${labelId}-help`;
  const isInvalid = Boolean(validationMessage) || Boolean(error);
  const effectiveHelp = validationMessage || helperText;
  const currentOption = options.find((opt) => opt.value === value);
  const wrapperStyle = {
    ...(sx?.minWidth ? {minWidth: sx.minWidth} : {}),
    ...(sx?.maxWidth ? {maxWidth: sx.maxWidth} : {}),
    ...style,
  };

  return (
    <div className={['sr-field', className].filter(Boolean).join(' ')} style={wrapperStyle}>
      {label && (
        <span id={labelId} className="sr-field-label">
          {label}
          {required ? ' *' : ''}
        </span>
      )}
      <BaseSelect.Root
        items={options}
        value={value}
        open={open}
        onOpenChange={(nextOpen) => {
          if (!disabled) setOpen(nextOpen);
        }}
        disabled={disabled}
        required={required}
        modal={false}
        onValueChange={(nextValue, details) => {
          onChange?.(nextValue, details?.event);
        }}
      >
        <BaseSelect.Trigger
          render={<div />}
          nativeButton={false}
          {...inputProps}
          aria-labelledby={label ? labelId : props['aria-labelledby']}
          aria-label={!label ? props['aria-label'] : undefined}
          aria-describedby={effectiveHelp ? helpId : undefined}
          aria-invalid={isInvalid ? 'true' : undefined}
          className="sr-select-trigger"
          onMouseDown={(event) => {
            if (!disabled && !open && event.button === 0) {
              setOpen(true);
            }
          }}
        >
          <BaseSelect.Value>
            {currentOption ? (
              currentOption.label
            ) : (
              <span style={{color: 'var(--sr-text-muted)', opacity: 0.72}}>{placeholder || ''}</span>
            )}
          </BaseSelect.Value>
          <BaseSelect.Icon style={{display: 'inline-flex', opacity: 0.65}}>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
              <polyline points="2.5 4.5 6 8 9.5 4.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </BaseSelect.Icon>
        </BaseSelect.Trigger>
        <BaseSelect.Portal>
          <BaseSelect.Positioner sideOffset={4} alignItemWithTrigger={false} style={{zIndex: 'var(--cde-layer-popover, 2400)'}}>
            <BaseSelect.Popup className="sr-select-popup">
              <BaseSelect.List>
                {options.map((option) => (
                  <BaseSelect.Item
                    key={String(option.value)}
                    value={option.value}
                    disabled={option.disabled}
                    className="sr-select-item"
                    onClick={(event) => {
                      if (!disabled && !option.disabled && event.detail === 0 && !event.currentTarget.hasAttribute('data-highlighted')) {
                        onChange?.(option.value, event);
                        setOpen(false);
                      }
                    }}
                  >
                    <BaseSelect.ItemText>{option.label}</BaseSelect.ItemText>
                    <BaseSelect.ItemIndicator style={{display: 'inline-flex', color: 'var(--sr-accent)'}}>
                      ✓
                    </BaseSelect.ItemIndicator>
                  </BaseSelect.Item>
                ))}
              </BaseSelect.List>
            </BaseSelect.Popup>
          </BaseSelect.Positioner>
        </BaseSelect.Portal>
      </BaseSelect.Root>
      {effectiveHelp && (
        <div id={helpId} className="sr-field-help" data-error={isInvalid ? 'true' : undefined}>
          {effectiveHelp}
        </div>
      )}
    </div>
  );
}

Select.propTypes = {
  label: PropTypes.node,
  disabled: PropTypes.bool,
  required: PropTypes.bool,
  placeholder: PropTypes.string,
  inputProps: PropTypes.object,
  validationMessage: PropTypes.node,
  error: PropTypes.bool,
  helperText: PropTypes.node,
  options: PropTypes.arrayOf(PropTypes.shape({
    value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).isRequired,
    label: PropTypes.node.isRequired,
    disabled: PropTypes.bool,
  })),
  value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  onChange: PropTypes.func,
  InputLabelProps: PropTypes.object,
  size: PropTypes.string,
  fullWidth: PropTypes.bool,
  sx: PropTypes.object,
  style: PropTypes.object,
  className: PropTypes.string,
  'aria-label': PropTypes.string,
  'aria-labelledby': PropTypes.string,
};
