/////////////////////////////////////////////////////////////
//
// ScratchRobin
//
// Copyright (C) 2026, ScratchBird Developers
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Badge, Box, Button, Stack, TextField} from 'sources/cdeadmin_ui';

const ACRONYMS = new Set([
  'id', 'uuid', 'sql', 'ddn', 'url', 'uri', 'api', 'cdc', 'etl', 'fts',
  'gtid', 'sha256', 'tls', 'ssl', 'ip', 'cpu', 'ram', 'io', 'db', 'ddl',
  'dml', 'json', 'csv', 'oid', 'pid', 'lsn', 'scn', 'wal',
]);

export function humanizePayloadKey(rawKey) {
  const text = String(rawKey ?? '').trim();
  if (!text) return '';
  const words = text
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_\-.]+/g, ' ')
    .split(/\s+/)
    .filter(Boolean);
  if (!words.length) return text;
  return words
    .map((word, idx) => {
      const lower = word.toLowerCase();
      if (ACRONYMS.has(lower)) return lower.toUpperCase();
      if (idx === 0) return lower.charAt(0).toUpperCase() + lower.slice(1);
      return lower;
    })
    .join(' ');
}

function isPlainObject(val) {
  return Boolean(val) && typeof val === 'object' && !Array.isArray(val);
}

function isScalar(val) {
  return val === null || val === undefined || ['string', 'number', 'boolean'].includes(typeof val);
}

function parsePayloadInput(value, rawText) {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
      try {
        const parsed = JSON.parse(trimmed);
        return {
          parsed,
          raw: rawText ?? value,
        };
      } catch {
        return {parsed: value, raw: rawText ?? value};
      }
    }
    return {parsed: value, raw: rawText ?? value};
  }
  if (value === undefined) {
    return {parsed: null, raw: rawText ?? ''};
  }
  let serialized = rawText;
  if (serialized === undefined) {
    try {
      serialized = JSON.stringify(value, null, 2);
    } catch {
      serialized = String(value);
    }
  }
  return {parsed: value, raw: serialized ?? ''};
}

function statusToneForScalar(key, val) {
  if (typeof val === 'boolean') {
    return val ? 'success' : 'neutral';
  }
  const k = String(key || '').toLowerCase();
  if (!['state', 'status', 'verdict', 'validity', 'severity', 'outcome', 'health'].includes(k)) {
    return null;
  }
  const s = String(val || '').toLowerCase();
  if (['ok', 'valid', 'completed', 'active', 'ready', 'healthy', 'passed', 'reviewed', 'accepted', 'artifact_verified', 'true'].includes(s)) {
    return 'success';
  }
  if (['warning', 'suspect', 'pending', 'degraded', 'dispatching', 'cancel_requested', 'lossy', 'unknown'].includes(s)) {
    return 'warning';
  }
  if (['error', 'failed', 'invalid', 'blocked', 'rejected', 'critical'].includes(s)) {
    return 'danger';
  }
  return 'info';
}

function formatCellText(val) {
  if (val === null || val === undefined) return '—';
  if (typeof val === 'boolean') return val ? gettext('Yes') : gettext('No');
  if (typeof val === 'number') return String(val);
  if (typeof val === 'string') return val === '' ? '—' : val;
  if (Array.isArray(val)) {
    if (!val.length) return gettext('None');
    if (val.every(isScalar)) return val.map((item) => (item === null || item === undefined ? 'null' : String(item))).join(', ');
    return gettext('%s items', val.length);
  }
  if (isPlainObject(val)) {
    const entries = Object.entries(val);
    if (!entries.length) return gettext('Empty');
    return entries
      .slice(0, 4)
      .map(([k, v]) => `${k}: ${isScalar(v) ? (v ?? 'null') : Array.isArray(v) ? `[${v.length}]` : '{…}'}`)
      .join(', ') + (entries.length > 4 ? ', …' : '');
  }
  return String(val);
}

function ScalarOrBadge({fieldKey, value}) {
  if (value === null || value === undefined || value === '') {
    return <span style={{opacity: 0.6}}>—</span>;
  }
  const tone = statusToneForScalar(fieldKey, value);
  if (typeof value === 'boolean') {
    return <Badge tone={tone}>{value ? gettext('Yes') : gettext('No')}</Badge>;
  }
  if (tone) {
    return <Badge tone={tone}>{String(value)}</Badge>;
  }
  return <span style={{wordBreak: 'break-word', fontFamily: String(fieldKey || '').match(/(id|uuid|sha|digest|sql|path|uri|url|host|lsn)/i) ? 'monospace' : 'inherit'}}>{String(value)}</span>;
}

ScalarOrBadge.propTypes = {
  fieldKey: PropTypes.string,
  value: PropTypes.any,
};

function ObjectArrayTable({rows, maxRows = 50}) {
  const columns = [];
  const seen = new Set();
  for (const row of rows) {
    if (!isPlainObject(row)) continue;
    for (const key of Object.keys(row)) {
      if (!seen.has(key) && columns.length < 10) {
        seen.add(key);
        columns.push(key);
      }
    }
  }
  const visibleRows = rows.slice(0, maxRows);
  if (!columns.length) {
    return <Box style={{fontSize: 12, opacity: 0.75}}>{gettext('No structured columns')}</Box>;
  }

  return (
    <Box style={{overflowX: 'auto'}}>
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontSize: 12,
        }}
      >
        <thead>
          <tr style={{borderBottom: '1px solid var(--sr-border, rgba(128,128,128,0.25))', textAlign: 'left'}}>
            {columns.map((col) => (
              <th key={col} style={{padding: '4px 8px', fontWeight: 600, whiteSpace: 'nowrap', opacity: 0.85}}>
                {humanizePayloadKey(col)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {visibleRows.map((row, idx) => (
            <tr key={row?.id ?? row?.name ?? row?.key ?? row?.path ?? idx} style={{borderBottom: '1px solid var(--sr-border, rgba(128,128,128,0.12))'}}>
              {columns.map((col) => (
                <td key={col} style={{padding: '4px 8px', verticalAlign: 'top', wordBreak: 'break-word'}}>
                  {isScalar(row?.[col]) ? <ScalarOrBadge fieldKey={col} value={row?.[col]} /> : formatCellText(row?.[col])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > maxRows && (
        <Box style={{fontSize: 11, opacity: 0.7, paddingTop: 4}}>
          {gettext('Showing first %s of %s rows.', maxRows, rows.length)}
        </Box>
      )}
    </Box>
  );
}

ObjectArrayTable.propTypes = {
  rows: PropTypes.array.isRequired,
  maxRows: PropTypes.number,
};

function PayloadBody({data, depth = 0, maxRows = 50, emptyMessage}) {
  if (data === null || data === undefined) {
    return <Box style={{fontSize: 12, opacity: 0.7}}>{emptyMessage || gettext('No details recorded.')}</Box>;
  }

  if (isScalar(data)) {
    return (
      <Box style={{fontSize: 13}}>
        <ScalarOrBadge value={data} />
      </Box>
    );
  }

  if (Array.isArray(data)) {
    if (!data.length) {
      return <Box style={{fontSize: 12, opacity: 0.7}}>{emptyMessage || gettext('None')}</Box>;
    }
    if (data.every(isPlainObject)) {
      return <ObjectArrayTable rows={data} maxRows={maxRows} />;
    }
    if (data.every(isScalar)) {
      return (
        <Stack direction="row" gap={1} style={{flexWrap: 'wrap'}}>
          {data.slice(0, maxRows).map((item, idx) => (
            <Badge key={`${idx}-${String(item)}`} tone="neutral">
              {item === null || item === undefined ? 'null' : String(item)}
            </Badge>
          ))}
        </Stack>
      );
    }
    return (
      <Stack gap={1}>
        {data.slice(0, maxRows).map((item, idx) => (
          <Box key={idx} style={{padding: '4px 8px', borderLeft: '2px solid rgba(128,128,128,0.25)', fontSize: 12}}>
            {formatCellText(item)}
          </Box>
        ))}
      </Stack>
    );
  }

  if (isPlainObject(data)) {
    const entries = Object.entries(data);
    if (!entries.length) {
      return <Box style={{fontSize: 12, opacity: 0.7}}>{emptyMessage || gettext('No properties configured.')}</Box>;
    }

    // Detect standard tabular {columns: [...], rows: [...]} shape
    if (Array.isArray(data.columns) && Array.isArray(data.rows) && data.columns.every(isScalar)) {
      const colNames = data.columns.map((c) => String(c));
      const normalizedRows = data.rows.map((r) => {
        if (isPlainObject(r)) return r;
        if (Array.isArray(r)) {
          const obj = {};
          colNames.forEach((col, i) => {
            obj[col] = r[i];
          });
          return obj;
        }
        return {value: r};
      });
      const restEntries = entries.filter(([k]) => k !== 'columns' && k !== 'rows');
      return (
        <Stack gap={1.5}>
          {restEntries.length > 0 && (
            <PayloadBody data={Object.fromEntries(restEntries)} depth={depth + 1} maxRows={maxRows} />
          )}
          <ObjectArrayTable rows={normalizedRows} maxRows={maxRows} />
        </Stack>
      );
    }

    const inlineEntries = [];
    const nestedEntries = [];
    for (const [k, v] of entries) {
      if (isScalar(v) || (Array.isArray(v) && (v.length === 0 || v.every(isScalar)))) {
        inlineEntries.push([k, v]);
      } else if (depth >= 2) {
        inlineEntries.push([k, formatCellText(v)]);
      } else {
        nestedEntries.push([k, v]);
      }
    }

    return (
      <Stack gap={1.5}>
        {inlineEntries.length > 0 && (
          <dl
            style={{
              margin: 0,
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: '6px 14px',
              fontSize: 12,
            }}
          >
            {inlineEntries.map(([k, v]) => (
              <div key={k} style={{minWidth: 0}}>
                <dt style={{fontWeight: 600, opacity: 0.72, fontSize: 11, marginBottom: 2}}>
                  {humanizePayloadKey(k)}
                </dt>
                <dd style={{margin: 0, minWidth: 0}}>
                  {Array.isArray(v) ? (
                    v.length ? (
                      <Stack direction="row" gap={0.5} style={{flexWrap: 'wrap'}}>
                        {v.map((item, idx) => (
                          <Badge key={`${k}-${idx}`} tone="neutral">{String(item ?? 'null')}</Badge>
                        ))}
                      </Stack>
                    ) : (
                      <span style={{opacity: 0.6}}>{gettext('None')}</span>
                    )
                  ) : (
                    <ScalarOrBadge fieldKey={k} value={v} />
                  )}
                </dd>
              </div>
            ))}
          </dl>
        )}
        {nestedEntries.map(([k, v]) => (
          <Box
            key={k}
            style={{
              borderTop: inlineEntries.length > 0 ? '1px solid var(--sr-border, rgba(128,128,128,0.16))' : 'none',
              paddingTop: inlineEntries.length > 0 ? 8 : 0,
            }}
          >
            <Box style={{fontWeight: 600, fontSize: 11, opacity: 0.8, marginBottom: 4}}>
              {humanizePayloadKey(k)}
            </Box>
            <PayloadBody data={v} depth={depth + 1} maxRows={maxRows} />
          </Box>
        ))}
      </Stack>
    );
  }

  return <Box style={{fontSize: 12}}>{String(data)}</Box>;
}

PayloadBody.propTypes = {
  data: PropTypes.any,
  depth: PropTypes.number,
  maxRows: PropTypes.number,
  emptyMessage: PropTypes.string,
};

export function StructuredPayloadCard({
  title,
  value,
  rawText,
  rawAriaLabel,
  rawDisclosureLabel,
  emptyMessage,
  maxRows = 50,
  compact = false,
  showRawDisclosure = true,
  defaultRawOpen = false,
  style,
}) {
  const {parsed, raw} = parsePayloadInput(value, rawText);
  const disclosureTitle = rawDisclosureLabel || gettext('Raw diagnostic payload');

  return (
    <Box
      style={{
        border: '1px solid var(--sr-border, rgba(128,128,128,0.22))',
        borderRadius: 6,
        padding: compact ? '8px 10px' : '10px 12px',
        background: 'var(--sr-surface-subtle, rgba(128,128,128,0.03))',
        ...style,
      }}
    >
      <Stack gap={1}>
        {title && (
          <Box style={{fontWeight: 600, fontSize: 12}}>
            {title}
          </Box>
        )}
        <PayloadBody data={parsed} maxRows={maxRows} emptyMessage={emptyMessage} />
        {showRawDisclosure && raw !== '' && (
          <details open={defaultRawOpen || undefined} style={{fontSize: 12, marginTop: 2}}>
            <summary style={{cursor: 'pointer', opacity: 0.78, userSelect: 'none'}}>
              {disclosureTitle}
            </summary>
            <pre
              aria-label={rawAriaLabel || undefined}
              style={{
                margin: '6px 0 0',
                padding: 8,
                fontSize: 11,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                maxHeight: 300,
                overflow: 'auto',
                background: 'rgba(128,128,128,0.06)',
                borderRadius: 4,
              }}
            >
              {raw}
            </pre>
          </details>
        )}
      </Stack>
    </Box>
  );
}

StructuredPayloadCard.propTypes = {
  title: PropTypes.node,
  value: PropTypes.any,
  rawText: PropTypes.string,
  rawAriaLabel: PropTypes.string,
  rawDisclosureLabel: PropTypes.string,
  emptyMessage: PropTypes.string,
  maxRows: PropTypes.number,
  compact: PropTypes.bool,
  showRawDisclosure: PropTypes.bool,
  defaultRawOpen: PropTypes.bool,
  style: PropTypes.object,
};

function coerceTypedScalar(text, parseValues) {
  if (!parseValues) return text;
  const trimmed = text.trim();
  if (trimmed === 'true') return true;
  if (trimmed === 'false') return false;
  if (trimmed === 'null') return null;
  if (/^-?\d+(\.\d+)?$/.test(trimmed)) {
    const num = Number(trimmed);
    if (Number.isSafeInteger(num) || !Number.isNaN(num)) return num;
  }
  if ((trimmed.startsWith('[') && trimmed.endsWith(']')) || (trimmed.startsWith('{') && trimmed.endsWith('}'))) {
    try {
      return JSON.parse(trimmed);
    } catch {
      return text;
    }
  }
  return text;
}

export function KeyValueJsonEditor({
  title,
  valueJson = '{}',
  onChangeJson,
  disabled = false,
  keyLabel,
  valueLabel,
  addLabel,
  parseValues = true,
}) {
  const [draftKey, setDraftKey] = useState('');
  const [draftVal, setDraftVal] = useState('');

  let parsedObj = null;
  try {
    const candidate = JSON.parse(valueJson || '{}');
    if (isPlainObject(candidate)) {
      parsedObj = candidate;
    }
  } catch {
    parsedObj = null;
  }

  const entries = parsedObj ? Object.entries(parsedObj) : [];

  const emitUpdated = (nextObj) => {
    onChangeJson?.(JSON.stringify(nextObj, null, 2));
  };

  const handleAdd = () => {
    const cleanKey = draftKey.trim();
    if (!cleanKey) return;
    const base = parsedObj ? {...parsedObj} : {};
    base[cleanKey] = coerceTypedScalar(draftVal, parseValues);
    emitUpdated(base);
    setDraftKey('');
    setDraftVal('');
  };

  const handleUpdateValue = (existingKey, nextRaw) => {
    if (!parsedObj) return;
    const base = {...parsedObj, [existingKey]: coerceTypedScalar(nextRaw, parseValues)};
    emitUpdated(base);
  };

  const handleRemove = (existingKey) => {
    if (!parsedObj) return;
    const base = {...parsedObj};
    delete base[existingKey];
    emitUpdated(base);
  };

  return (
    <Box
      style={{
        border: '1px solid var(--sr-border, rgba(128,128,128,0.2))',
        borderRadius: 6,
        padding: '8px 10px',
      }}
    >
      <Stack gap={1}>
        {title && <Box style={{fontWeight: 600, fontSize: 12}}>{title}</Box>}
        {parsedObj === null ? (
          <Box style={{fontSize: 12, opacity: 0.8}}>
            {gettext('Custom JSON syntax active in advanced overrides below.')}
          </Box>
        ) : (
          <>
            {entries.length > 0 && (
              <Stack gap={0.75}>
                {entries.map(([k, v]) => (
                  <Stack key={k} direction="row" gap={1} align="center" style={{flexWrap: 'wrap'}}>
                    <Badge tone="neutral">{k}</Badge>
                    <TextField
                      aria-label={`${title || gettext('Parameter')} ${k}`}
                      value={isScalar(v) ? String(v ?? '') : JSON.stringify(v)}
                      disabled={disabled}
                      onChange={(e) => handleUpdateValue(k, e.target.value)}
                      style={{flex: 1, minWidth: 140}}
                    />
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={disabled}
                      onClick={() => handleRemove(k)}
                    >
                      {gettext('Remove')}
                    </Button>
                  </Stack>
                ))}
              </Stack>
            )}
            <Stack direction="row" gap={1} align="flex-end" style={{flexWrap: 'wrap'}}>
              <TextField
                label={keyLabel || gettext('Parameter key')}
                value={draftKey}
                disabled={disabled}
                onChange={(e) => setDraftKey(e.target.value)}
                style={{minWidth: 150, flex: 1}}
              />
              <TextField
                label={valueLabel || gettext('Parameter value')}
                value={draftVal}
                disabled={disabled}
                onChange={(e) => setDraftVal(e.target.value)}
                style={{minWidth: 150, flex: 1}}
              />
              <Button
                size="sm"
                variant="secondary"
                disabled={disabled || !draftKey.trim()}
                onClick={handleAdd}
              >
                {addLabel || gettext('Set parameter')}
              </Button>
            </Stack>
          </>
        )}
      </Stack>
    </Box>
  );
}

KeyValueJsonEditor.propTypes = {
  title: PropTypes.node,
  valueJson: PropTypes.string,
  onChangeJson: PropTypes.func,
  disabled: PropTypes.bool,
  keyLabel: PropTypes.string,
  valueLabel: PropTypes.string,
  addLabel: PropTypes.string,
  parseValues: PropTypes.bool,
};

export default StructuredPayloadCard;
