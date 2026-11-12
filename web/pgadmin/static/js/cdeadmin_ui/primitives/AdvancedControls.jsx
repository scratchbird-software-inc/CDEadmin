/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useId, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {RadioGroup as BaseRadioGroup} from '@base-ui/react/radio-group';
import {Radio as BaseRadio} from '@base-ui/react/radio';
import {Slider as BaseSlider} from '@base-ui/react/slider';
import {ToggleGroup as BaseToggleGroup} from '@base-ui/react/toggle-group';
import {Toggle as BaseToggle} from '@base-ui/react/toggle';
import {Progress as BaseProgress} from '@base-ui/react/progress';
import {ensureScratchBaseStyles} from '../base/ScratchBaseStyles';
import {Button, IconButton} from './Button';
import {TextField} from './Field';

function optionLabel(option) {
  return typeof option === 'object' && option !== null
    ? String(option.label ?? option.value ?? '')
    : String(option ?? '');
}

function optionValue(option) {
  return typeof option === 'object' && option !== null
    ? option.value ?? option.label
    : option;
}

export function SplitButton({
  children,
  options = [],
  onClick,
  onSelect,
  disabled = false,
  label = 'More actions',
}) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);
  const [open, setOpen] = useState(false);

  return (
    <div style={{position: 'relative', display: 'inline-flex', alignItems: 'center'}}>
      <div style={{display: 'inline-flex', borderRadius: 'var(--sr-control-radius, 7px)'}}>
        <Button
          disabled={disabled}
          onClick={onClick}
          style={{borderTopRightRadius: 0, borderBottomRightRadius: 0}}
        >
          {children}
        </Button>
        <IconButton
          label={label}
          disabled={disabled}
          onClick={() => setOpen((current) => !current)}
          style={{
            border: '1px solid var(--sr-border-default)',
            borderLeft: 'none',
            borderTopLeftRadius: 0,
            borderBottomLeftRadius: 0,
            background: 'var(--sr-surface-card)',
            minHeight: 'var(--cde-control-height, 30px)',
          }}
        >
          ▾
        </IconButton>
      </div>
      {open && (
        <div
          role="menu"
          className="sr-popover-popup"
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            right: 0,
            minWidth: 200,
          }}
        >
          {options.map((option) => (
            <Button
              key={option.value}
              role="menuitem"
              disabled={option.disabled}
              style={{
                display: 'flex',
                width: '100%',
                justifyContent: 'flex-start',
                border: 'none',
                background: 'transparent',
              }}
              onClick={() => {
                setOpen(false);
                onSelect?.(option.value);
              }}
            >
              {option.label}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}

SplitButton.propTypes = {
  children: PropTypes.node,
  options: PropTypes.array,
  onClick: PropTypes.func,
  onSelect: PropTypes.func,
  disabled: PropTypes.bool,
  label: PropTypes.string,
};

export function ComboBox({
  options = [],
  value = null,
  onChange,
  freeEntry = false,
  label,
  required = false,
  disabled = false,
  helperText,
  validationMessage,
  placeholder = '',
}) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);

  const inputId = useId();
  const listId = `${inputId}-listbox`;
  const [open, setOpen] = useState(false);
  const [inputValue, setInputValue] = useState(() => (value == null ? '' : optionLabel(value)));

  useEffect(() => {
    setInputValue(value == null ? '' : optionLabel(value));
  }, [value, freeEntry]);

  const filtered = options.filter((opt) =>
    optionLabel(opt).toLowerCase().includes(inputValue.toLowerCase())
  );
  const isInvalid = Boolean(validationMessage);
  const effectiveHelp = validationMessage || helperText;

  return (
    <div className="sr-field" style={{position: 'relative'}}>
      {label && (
        <label htmlFor={inputId} className="sr-field-label">
          {label}
          {required ? ' *' : ''}
        </label>
      )}
      <div className="sr-input-wrap" data-invalid={isInvalid ? 'true' : undefined} data-disabled={disabled ? 'true' : undefined}>
        <input
          id={inputId}
          role="combobox"
          aria-expanded={open}
          aria-controls={open ? listId : undefined}
          aria-autocomplete="list"
          aria-invalid={isInvalid ? 'true' : undefined}
          disabled={disabled}
          required={required}
          placeholder={placeholder}
          value={inputValue}
          className="sr-input"
          onFocus={() => !disabled && setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          onChange={(event) => {
            const nextText = event.target.value;
            setInputValue(nextText);
            setOpen(true);
            if (freeEntry) {
              onChange?.(nextText);
            } else {
              const exact = options.find((opt) => optionLabel(opt) === nextText);
              if (exact !== undefined) onChange?.(exact);
            }
          }}
        />
      </div>
      {open && filtered.length > 0 && (
        <div
          id={listId}
          role="listbox"
          className="sr-select-popup"
          style={{position: 'absolute', top: 'calc(100% + 2px)', left: 0, right: 0}}
        >
          {filtered.map((opt) => {
            const optText = optionLabel(opt);
            const optKey = String(optionValue(opt));
            return (
              <div
                key={optKey}
                role="option"
                aria-selected={optionLabel(value) === optText}
                className="sr-select-item"
                onMouseDown={(event) => {
                  event.preventDefault();
                  setInputValue(optText);
                  onChange?.(opt);
                  setOpen(false);
                }}
              >
                {optText}
              </div>
            );
          })}
        </div>
      )}
      {effectiveHelp && (
        <div className="sr-field-help" data-error={isInvalid ? 'true' : undefined}>
          {effectiveHelp}
        </div>
      )}
    </div>
  );
}

ComboBox.propTypes = {
  options: PropTypes.array,
  value: PropTypes.any,
  onChange: PropTypes.func,
  freeEntry: PropTypes.bool,
  label: PropTypes.node,
  required: PropTypes.bool,
  disabled: PropTypes.bool,
  helperText: PropTypes.node,
  validationMessage: PropTypes.node,
  placeholder: PropTypes.string,
};

export function Radio({label, value, options = [], onChange, disabled = false}) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);
  const groupLabelId = useId();

  return (
    <div className="sr-field">
      {label && <span id={groupLabelId} className="sr-field-label">{label}</span>}
      <BaseRadioGroup
        aria-labelledby={label ? groupLabelId : undefined}
        value={value}
        disabled={disabled}
        onValueChange={(nextVal) => onChange?.(nextVal)}
        style={{display: 'flex', flexDirection: 'column', gap: 6}}
      >
        {options.map((option) => (
          <label
            key={String(option.value)}
            className="sr-choice-label"
            data-disabled={disabled || option.disabled ? 'true' : undefined}
          >
            <BaseRadio.Root
              value={option.value}
              disabled={disabled || option.disabled}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 16,
                height: 16,
                borderRadius: '50%',
                border: '1.5px solid var(--sr-border-default)',
                background: 'var(--sr-surface-card)',
              }}
            >
              <BaseRadio.Indicator
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: 'var(--sr-accent)',
                }}
              />
            </BaseRadio.Root>
            <span>{option.label}</span>
          </label>
        ))}
      </BaseRadioGroup>
    </div>
  );
}

Radio.propTypes = {
  label: PropTypes.node,
  value: PropTypes.any,
  options: PropTypes.array,
  onChange: PropTypes.func,
  disabled: PropTypes.bool,
};

export function Slider({
  label,
  value = 0,
  min = 0,
  max = 100,
  step = 1,
  disabled = false,
  onChange,
  showValue = true,
}) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);
  const labelId = useId();
  const numericValue = Array.isArray(value) ? value[0] ?? min : Number(value ?? min);

  return (
    <div className="sr-field">
      <div style={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8}}>
        {label && <span id={labelId} className="sr-field-label">{label}</span>}
        {showValue && (
          <span className="sr-bui-mono" style={{fontSize: '0.75rem', color: 'var(--sr-text-secondary)'}}>
            {numericValue}
          </span>
        )}
      </div>
      <BaseSlider.Root
        value={numericValue}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        aria-labelledby={label ? labelId : undefined}
        onValueChange={(nextValue) => onChange?.(nextValue)}
      >
        <BaseSlider.Control className="sr-slider-control">
          <BaseSlider.Track className="sr-slider-track">
            <BaseSlider.Indicator className="sr-slider-indicator" />
            <BaseSlider.Thumb
              aria-labelledby={label ? labelId : undefined}
              className="sr-slider-thumb"
            />
          </BaseSlider.Track>
        </BaseSlider.Control>
      </BaseSlider.Root>
    </div>
  );
}

Slider.propTypes = {
  label: PropTypes.node,
  value: PropTypes.oneOfType([PropTypes.number, PropTypes.array]),
  min: PropTypes.number,
  max: PropTypes.number,
  step: PropTypes.number,
  disabled: PropTypes.bool,
  onChange: PropTypes.func,
  showValue: PropTypes.bool,
};

export function MultiSelect({
  label,
  options = [],
  value = [],
  onChange,
  required = false,
  disabled = false,
  helperText,
  validationMessage,
}) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);
  const inputId = useId();
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const isInvalid = Boolean(validationMessage);
  const effectiveHelp = validationMessage || helperText;
  const visibleTokens = value.slice(0, 2);
  const overflowCount = Math.max(0, value.length - 2);
  const filtered = options.filter((opt) =>
    optionLabel(opt).toLowerCase().includes(query.toLowerCase())
  );

  const toggleItem = (opt) => {
    const exists = value.some((item) => optionLabel(item) === optionLabel(opt));
    const next = exists
      ? value.filter((item) => optionLabel(item) !== optionLabel(opt))
      : [...value, opt];
    onChange?.(next);
  };

  return (
    <div className="sr-field" style={{position: 'relative'}}>
      {label && (
        <label htmlFor={inputId} className="sr-field-label">
          {label}
          {required ? ' *' : ''}
        </label>
      )}
      <div
        className="sr-input-wrap"
        data-invalid={isInvalid ? 'true' : undefined}
        data-disabled={disabled ? 'true' : undefined}
        style={{flexWrap: 'wrap', paddingBlock: 3}}
      >
        {visibleTokens.map((item) => (
          <span key={optionLabel(item)} className="sr-bui-pill">
            {optionLabel(item)}
          </span>
        ))}
        {overflowCount > 0 && (
          <span className="sr-bui-pill">+{overflowCount}</span>
        )}
        <input
          id={inputId}
          role="combobox"
          aria-expanded={open}
          aria-invalid={isInvalid ? 'true' : undefined}
          disabled={disabled}
          required={required && value.length === 0}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => !disabled && setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          className="sr-input"
          style={{minWidth: 60}}
        />
      </div>
      {open && filtered.length > 0 && (
        <div role="listbox" aria-multiselectable="true" className="sr-select-popup" style={{position: 'absolute', top: 'calc(100% + 2px)', left: 0, right: 0}}>
          {filtered.map((opt) => {
            const selected = value.some((item) => optionLabel(item) === optionLabel(opt));
            return (
              <div
                key={optionLabel(opt)}
                role="option"
                aria-selected={selected}
                className="sr-select-item"
                onMouseDown={(e) => {
                  e.preventDefault();
                  toggleItem(opt);
                }}
              >
                <span>{optionLabel(opt)}</span>
                {selected && <span>✓</span>}
              </div>
            );
          })}
        </div>
      )}
      {effectiveHelp && (
        <div className="sr-field-help" data-error={isInvalid ? 'true' : undefined}>
          {effectiveHelp}
        </div>
      )}
    </div>
  );
}

MultiSelect.propTypes = ComboBox.propTypes;

export function SegmentedControl({
  label,
  options = [],
  value,
  onChange,
  disabled = false,
}) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);
  const labelId = useId();

  return (
    <div className="sr-field">
      {label && <span id={labelId} className="sr-field-label">{label}</span>}
      <BaseToggleGroup
        aria-labelledby={label ? labelId : undefined}
        value={value === undefined || value === null ? [] : [value]}
        disabled={disabled}
        onValueChange={(groupValue) => {
          const next = groupValue[groupValue.length - 1];
          if (next !== undefined && next !== value) {
            onChange?.(next);
          }
        }}
        style={{
          display: 'inline-flex',
          padding: 2,
          gap: 2,
          borderRadius: 'var(--sr-control-radius, 7px)',
          border: '1px solid var(--sr-border-default)',
          background: 'var(--sr-surface-subtle)',
        }}
      >
        {options.map((option) => {
          const active = option.value === value;
          return (
            <BaseToggle
              key={String(option.value)}
              value={option.value}
              disabled={disabled || option.disabled}
              style={{
                padding: '4px 10px',
                borderRadius: 5,
                border: 'none',
                fontSize: '0.78rem',
                fontWeight: active ? 600 : 500,
                background: active ? 'var(--sr-surface-card)' : 'transparent',
                color: active ? 'var(--sr-accent)' : 'var(--sr-text-secondary)',
                cursor: disabled || option.disabled ? 'not-allowed' : 'pointer',
                opacity: disabled || option.disabled ? 0.45 : 1,
              }}
            >
              {option.label}
            </BaseToggle>
          );
        })}
      </BaseToggleGroup>
    </div>
  );
}

SegmentedControl.propTypes = Radio.propTypes;

export function SearchField({
  label = 'Filter items',
  value = '',
  onChange,
  loading = false,
  resultCount,
  disabled = false,
  ...props
}) {
  return (
    <TextField
      label={label}
      value={value}
      disabled={disabled}
      onChange={(event) => onChange?.(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === 'Escape' && value) {
          event.stopPropagation();
          onChange?.('');
        }
        props.onKeyDown?.(event);
      }}
      InputProps={{
        startAdornment: (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true" style={{opacity: 0.6, flexShrink: 0}}>
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
        ),
        endAdornment: (
          <span style={{display: 'inline-flex', alignItems: 'center', gap: 4}}>
            {loading && (
              <span role="progressbar" aria-label="Searching" style={{fontSize: '0.7rem', color: 'var(--sr-accent)'}}>
                …
              </span>
            )}
            {value && (
              <IconButton
                label="Clear search"
                onClick={() => onChange?.('')}
                style={{minWidth: 22, minHeight: 22, padding: 2}}
              >
                ×
              </IconButton>
            )}
          </span>
        ),
      }}
      helperText={resultCount === undefined ? undefined : `${resultCount} results`}
      {...props}
    />
  );
}

SearchField.propTypes = {
  label: PropTypes.node,
  value: PropTypes.string,
  onChange: PropTypes.func,
  loading: PropTypes.bool,
  resultCount: PropTypes.number,
  disabled: PropTypes.bool,
  onKeyDown: PropTypes.func,
};

function NativeTemporalField({
  type,
  label,
  value = '',
  onChange,
  validationMessage,
  context,
  ...props
}) {
  const help = [context, validationMessage].filter(Boolean).join(' — ');
  return (
    <TextField
      type={type}
      label={label}
      value={value}
      onChange={(event) => onChange?.(event.target.value)}
      validationMessage={validationMessage}
      helperText={!validationMessage && help ? help : undefined}
      {...props}
    />
  );
}

NativeTemporalField.propTypes = {
  type: PropTypes.string.isRequired,
  label: PropTypes.node,
  value: PropTypes.string,
  onChange: PropTypes.func,
  validationMessage: PropTypes.node,
  context: PropTypes.node,
};

export function DateField(props) {
  return <NativeTemporalField type="date" {...props} />;
}

export function TimeField({timezone, ...props}) {
  return (
    <NativeTemporalField
      type="time"
      context={timezone ? `Timezone: ${timezone}` : undefined}
      {...props}
    />
  );
}

TimeField.propTypes = {timezone: PropTypes.string};

export function UnitNumberField({
  label,
  value = '',
  unit,
  units = [],
  onChange,
  onUnitChange,
  validationMessage,
  ...props
}) {
  const unitControl = units.length ? (
    <select
      aria-label={`${label || 'Value'} unit`}
      value={unit}
      onChange={(event) => onUnitChange?.(event.target.value)}
      style={{
        border: 'none',
        background: 'transparent',
        color: 'var(--sr-text-secondary)',
        fontSize: '0.78rem',
        fontWeight: 600,
        cursor: 'pointer',
      }}
    >
      {units.map((item) => (
        <option key={item.value ?? item} value={item.value ?? item}>
          {item.label ?? item}
        </option>
      ))}
    </select>
  ) : (
    <span style={{fontSize: '0.78rem', color: 'var(--sr-text-secondary)'}}>{unit}</span>
  );

  return (
    <TextField
      type="number"
      label={label}
      value={value}
      onChange={(event) => {
        const number = event.target.value === '' ? '' : Number(event.target.value);
        onChange?.(number, unit);
      }}
      validationMessage={validationMessage}
      InputProps={{endAdornment: unitControl}}
      {...props}
    />
  );
}

UnitNumberField.propTypes = {
  label: PropTypes.node,
  value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  unit: PropTypes.string.isRequired,
  units: PropTypes.array,
  onChange: PropTypes.func,
  onUnitChange: PropTypes.func,
  validationMessage: PropTypes.node,
};

export function DurationField(props) {
  return (
    <UnitNumberField
      units={[
        {value: 'ms', label: 'ms'},
        {value: 's', label: 'seconds'},
        {value: 'min', label: 'minutes'},
        {value: 'h', label: 'hours'},
        {value: 'd', label: 'days'},
      ]}
      {...props}
    />
  );
}

export function PasswordStrength({state = 'unknown', message}) {
  const values = {unknown: 0, invalid: 25, acceptable: 67, strong: 100};
  const barColor = state === 'invalid'
    ? 'var(--sr-danger)'
    : state === 'strong'
      ? 'var(--sr-success)'
      : 'var(--sr-accent)';
  const text = message || ({
    unknown: 'Strength not evaluated',
    invalid: 'Password does not meet provider policy',
    acceptable: 'Password meets provider policy',
    strong: 'Password exceeds provider policy',
  }[state]);

  return (
    <div role="status" aria-live="polite" style={{display: 'flex', flexDirection: 'column', gap: 4}}>
      <BaseProgress.Root value={values[state]}>
        <BaseProgress.Track
          style={{
            height: 5,
            width: '100%',
            borderRadius: 999,
            background: 'var(--sr-border-subtle)',
            overflow: 'hidden',
          }}
        >
          <BaseProgress.Indicator
            style={{
              height: '100%',
              width: `${values[state]}%`,
              background: barColor,
              transition: 'width 160ms ease',
            }}
          />
        </BaseProgress.Track>
      </BaseProgress.Root>
      <span className="sr-field-help">{text}</span>
    </div>
  );
}

PasswordStrength.propTypes = {
  state: PropTypes.oneOf(['unknown', 'invalid', 'acceptable', 'strong']),
  message: PropTypes.node,
};

export function FilePickerButton({
  label = 'Choose file',
  accept,
  multiple = false,
  directory = false,
  onFiles,
  disabled = false,
  loading = false,
}) {
  const ref = useRef(null);
  return (
    <>
      <input
        ref={ref}
        hidden
        type="file"
        accept={accept}
        multiple={multiple}
        disabled={disabled}
        {...(directory ? {webkitdirectory: ''} : {})}
        onChange={(event) => onFiles?.(Array.from(event.target.files), event)}
      />
      <Button
        disabled={disabled}
        loading={loading}
        onClick={() => ref.current?.click()}
      >
        {label}
      </Button>
    </>
  );
}

FilePickerButton.propTypes = {
  label: PropTypes.node,
  accept: PropTypes.string,
  multiple: PropTypes.bool,
  directory: PropTypes.bool,
  onFiles: PropTypes.func,
  disabled: PropTypes.bool,
  loading: PropTypes.bool,
};
