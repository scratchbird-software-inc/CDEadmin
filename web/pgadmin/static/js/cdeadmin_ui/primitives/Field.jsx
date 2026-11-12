/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {forwardRef, useEffect, useId, useState} from 'react';
import PropTypes from 'prop-types';
import {Field as BaseField} from '@base-ui/react/field';
import {Input as BaseInput} from '@base-ui/react/input';
import {ensureScratchBaseStyles} from '../base/ScratchBaseStyles';
import {IconButton} from './Button';

function EyeIcon({off = false}) {
  return off ? (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  ) : (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

export const TextField = forwardRef(function TextField({
  id: idProp,
  label,
  validationMessage,
  error = false,
  helperText,
  multiline = false,
  minRows = 3,
  rows,
  disabled = false,
  required = false,
  readOnly: readOnlyProp,
  InputProps,
  inputProps,
  // Strip legacy MUI-only props cleanly
  // eslint-disable-next-line no-unused-vars
  InputLabelProps,
  // eslint-disable-next-line no-unused-vars
  fullWidth,
  // eslint-disable-next-line no-unused-vars
  size,
  // eslint-disable-next-line no-unused-vars
  variant,
  // eslint-disable-next-line no-unused-vars
  sx,
  className = '',
  style,
  ...props
}, ref) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);

  const generatedId = useId();
  const controlId = idProp || inputProps?.id || generatedId;
  const helpId = `${controlId}-help`;
  const isInvalid = Boolean(validationMessage) || Boolean(error);
  const effectiveHelp = validationMessage || helperText;
  const isReadOnly = Boolean(readOnlyProp ?? InputProps?.readOnly ?? inputProps?.readOnly);

  return (
    <BaseField.Root
      invalid={isInvalid}
      disabled={disabled}
      className={['sr-field', className].filter(Boolean).join(' ')}
      style={style}
    >
      {label && (
        <label htmlFor={controlId} className="sr-field-label">
          {label}
          {required ? ' *' : ''}
        </label>
      )}
      <div
        className="sr-input-wrap"
        data-invalid={isInvalid ? 'true' : undefined}
        data-disabled={disabled ? 'true' : undefined}
        style={multiline ? {alignItems: 'flex-start', paddingTop: 4, paddingBottom: 4} : undefined}
      >
        {InputProps?.startAdornment}
        {multiline ? (
          <textarea
            ref={ref}
            id={controlId}
            rows={rows ?? minRows}
            disabled={disabled}
            required={required}
            readOnly={isReadOnly}
            aria-invalid={isInvalid ? 'true' : undefined}
            aria-describedby={effectiveHelp ? helpId : undefined}
            className="sr-input sr-textarea"
            {...inputProps}
            {...props}
          />
        ) : (
          <BaseInput
            ref={ref}
            id={controlId}
            disabled={disabled}
            required={required}
            readOnly={isReadOnly}
            aria-invalid={isInvalid ? 'true' : undefined}
            aria-describedby={effectiveHelp ? helpId : undefined}
            className="sr-input"
            {...inputProps}
            {...props}
          />
        )}
        {InputProps?.endAdornment}
      </div>
      {effectiveHelp && (
        <div
          id={helpId}
          className="sr-field-help"
          data-error={isInvalid ? 'true' : undefined}
        >
          {effectiveHelp}
        </div>
      )}
    </BaseField.Root>
  );
});

export function NumberField(props) {
  return <TextField {...props} type="number" inputMode="decimal" />;
}

export function TextArea({rows = 4, ...props}) {
  return <TextField {...props} multiline rows={rows} minRows={rows} />;
}

export function SecretField({
  allowReveal = false,
  revealed,
  onRevealChange,
  allowCopy = false,
  autoComplete = 'current-password',
  InputProps,
  ...props
}) {
  const [internalRevealed, setInternalRevealed] = useState(false);
  const isRevealed = revealed ?? internalRevealed;
  const toggle = () => {
    const next = !isRevealed;
    if (revealed === undefined) setInternalRevealed(next);
    onRevealChange?.(next);
  };
  return (
    <TextField
      {...props}
      type={allowReveal && isRevealed ? 'text' : 'password'}
      autoComplete={autoComplete}
      onCopy={(event) => {
        if (!allowCopy) event.preventDefault();
        props.onCopy?.(event);
      }}
      InputProps={{
        ...InputProps,
        endAdornment: allowReveal ? (
          <IconButton
            label={isRevealed ? 'Hide secret' : 'Reveal secret'}
            onClick={toggle}
          >
            <EyeIcon off={isRevealed} />
          </IconButton>
        ) : InputProps?.endAdornment,
      }}
    />
  );
}

TextField.propTypes = {
  id: PropTypes.string,
  label: PropTypes.node,
  error: PropTypes.bool,
  helperText: PropTypes.node,
  validationMessage: PropTypes.node,
  multiline: PropTypes.bool,
  minRows: PropTypes.number,
  rows: PropTypes.number,
  disabled: PropTypes.bool,
  required: PropTypes.bool,
  readOnly: PropTypes.bool,
  InputProps: PropTypes.object,
  inputProps: PropTypes.object,
  InputLabelProps: PropTypes.object,
  fullWidth: PropTypes.bool,
  size: PropTypes.string,
  variant: PropTypes.string,
  sx: PropTypes.object,
  className: PropTypes.string,
  style: PropTypes.object,
};

NumberField.propTypes = TextField.propTypes;

TextArea.propTypes = {
  ...TextField.propTypes,
  rows: PropTypes.number,
};

SecretField.propTypes = {
  ...TextField.propTypes,
  allowReveal: PropTypes.bool,
  revealed: PropTypes.bool,
  onRevealChange: PropTypes.func,
  allowCopy: PropTypes.bool,
  autoComplete: PropTypes.string,
  onCopy: PropTypes.func,
  InputProps: PropTypes.object,
};
