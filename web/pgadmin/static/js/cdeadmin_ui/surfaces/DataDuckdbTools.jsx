/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Grid, Panel, Stack} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {TextField} from '../primitives/Field';
import {Select} from '../primitives/Choice';
import {Badge, Banner} from '../feedback/Indicators';
import {Dialog} from '../overlays/Dialog';
import FormReference from '../navigation/FormReference';
import CodeEditor from '../editors/CodeEditor';

function quoteDuckdbIdent(name) {
  return `"${String(name || '').replace(/"/g, '""')}"`;
}

function bytesToHex(b64) {
  try {
    const bin = atob(String(b64 || ''));
    return Array.from(bin, (ch) => ch.charCodeAt(0).toString(16).padStart(2, '0').toUpperCase()).join('');
  } catch {
    return '';
  }
}

function formatDuckdbLiteral(val) {
  if (val === null || val === undefined) return 'NULL';
  if (typeof val === 'boolean') return val ? 'TRUE' : 'FALSE';
  if (typeof val === 'number') {
    if (!Number.isFinite(val)) return 'NULL';
    return String(val);
  }
  if (Array.isArray(val)) {
    return `[${val.map(formatDuckdbLiteral).join(', ')}]`;
  }
  if (typeof val === 'object') {
    if (val.encoding === 'base64' && typeof val.data === 'string') {
      return `from_hex('${bytesToHex(val.data)}')`;
    }
    if (typeof val.hugeint === 'string' || typeof val.uhugeint === 'string' || typeof val.decimal === 'string') {
      return val.hugeint || val.uhugeint || val.decimal;
    }
    if (val.duckdb_type === 'MAP' && Array.isArray(val.entries)) {
      const keys = val.entries.map((e) => formatDuckdbLiteral(e.key)).join(', ');
      const vals = val.entries.map((e) => formatDuckdbLiteral(e.value)).join(', ');
      return `MAP([${keys}], [${vals}])`;
    }
    if (val.duckdb_type === 'UNION' && val.tag) {
      return `union_value(${quoteDuckdbIdent(val.tag)} := ${formatDuckdbLiteral(val.value)})`;
    }
    const entries = Object.entries(val).map(([k, v]) => `${quoteDuckdbIdent(k)}: ${formatDuckdbLiteral(v)}`);
    return `{${entries.join(', ')}}`;
  }
  return `'${String(val).replace(/'/g, "''")}'`;
}

/**
 * SR-F-030594: DuckDB Row SQL Generator (INSERT, ON CONFLICT DO UPDATE, INSERT OR REPLACE,
 * COPY TO PARQUET/JSON, and nested LIST/STRUCT/MAP/UNION/BLOB literals).
 */
export function DataDuckdbRowSqlDialog({
  open,
  tableLabel = 'main.table',
  columns = [],
  row = null,
  onClose,
}) {
  const [mode, setMode] = useState('upsert');
  const [keyCol, setKeyCol] = useState(columns?.[0]?.name || 'id');

  const sqlText = useMemo(() => {
    const colNames = (columns || []).map((c) => c.name).filter(Boolean);
    if (!colNames.length || !row) return '-- Select a row to generate DuckDB SQL';
    const valuesMap = Array.isArray(row)
      ? Object.fromEntries(colNames.map((n, idx) => [n, row[idx]]))
      : row;
    const quotedCols = colNames.map(quoteDuckdbIdent).join(', ');
    const formattedVals = colNames.map((n) => formatDuckdbLiteral(valuesMap[n])).join(', ');
    const pkName = keyCol || colNames[0];
    const pk = quoteDuckdbIdent(pkName);
    const pkVal = formatDuckdbLiteral(valuesMap[pkName] ?? 1);

    switch (mode) {
      case 'insert':
        return `INSERT INTO ${tableLabel} (${quotedCols})\nVALUES (${formattedVals});`;
      case 'replace':
        return `INSERT OR REPLACE INTO ${tableLabel} (${quotedCols})\nVALUES (${formattedVals});`;
      case 'update': {
        const sets = colNames
          .filter((c) => c !== pkName)
          .map((c) => `${quoteDuckdbIdent(c)} = ${formatDuckdbLiteral(valuesMap[c])}`)
          .join(',\n    ');
        return `UPDATE ${tableLabel}\nSET ${sets || `${pk} = ${pkVal}`}\nWHERE ${pk} = ${pkVal};`;
      }
      case 'delete':
        return `DELETE FROM ${tableLabel}\nWHERE ${pk} = ${pkVal};`;
      case 'copy_parquet':
        return `COPY (SELECT * FROM ${tableLabel} WHERE ${pk} = ${pkVal}) TO 'row_export.parquet' (FORMAT PARQUET);`;
      default: {
        const updates = colNames
          .filter((c) => c !== pkName)
          .map((c) => `${quoteDuckdbIdent(c)} = EXCLUDED.${quoteDuckdbIdent(c)}`)
          .join(',\n    ');
        return `INSERT INTO ${tableLabel} (${quotedCols})\nVALUES (${formattedVals})\nON CONFLICT (${pk}) DO UPDATE\nSET ${updates || `${pk} = EXCLUDED.${pk}`};`;
      }
    }
  }, [columns, keyCol, mode, row, tableLabel]);

  if (!open) return null;

  return (
    <Dialog
      open={open}
      title={gettext('Generate DuckDB Row SQL & COPY Snippet')}
      onClose={onClose}
      size="lg"
    >
      <Stack gap="md">
        <FormReference reference="SR-F-030594" />
        <Grid columns={2} gap="sm">
          <Select
            label={gettext('DuckDB Statement Variant')}
            value={mode}
            options={[
              {value: 'upsert', label: 'INSERT ... ON CONFLICT DO UPDATE'},
              {value: 'insert', label: 'INSERT INTO ... VALUES (...)'},
              {value: 'replace', label: 'INSERT OR REPLACE INTO ...'},
              {value: 'update', label: 'UPDATE ... WHERE key = ...'},
              {value: 'delete', label: 'DELETE FROM ... WHERE key = ...'},
              {value: 'copy_parquet', label: 'COPY (SELECT ...) TO Parquet'},
            ]}
            onChange={setMode}
          />
          <TextField
            label={gettext('Conflict / Primary Key Column')}
            value={keyCol}
            onChange={(e) => setKeyCol(e?.target ? e.target.value : String(e ?? ''))}
          />
        </Grid>
        <CodeEditor value={sqlText} language="sql" readOnly minHeight={180} />
        <Button variant="secondary" onClick={onClose}>
          {gettext('Close')}
        </Button>
      </Stack>
    </Dialog>
  );
}

DataDuckdbRowSqlDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  tableLabel: PropTypes.string,
  columns: PropTypes.array,
  row: PropTypes.oneOfType([PropTypes.object, PropTypes.array]),
  onClose: PropTypes.func.isRequired,
};

function classifyDuckdbCell(value, column) {
  const nativeType = column?.native_type || column?.data_type || column?.type || 'UNKNOWN';
  const envelope = column?.input_envelope || null;
  if (value === null || value === undefined) {
    return {family: 'NULL', detail: `SQL NULL (${nativeType})`, formatted: 'NULL', envelope};
  }
  if (Array.isArray(value)) {
    return {
      family: 'LIST / ARRAY',
      detail: `${value.length} element(s), native type ${nativeType}`,
      formatted: JSON.stringify(value, null, 2),
      envelope,
    };
  }
  if (typeof value === 'object') {
    if (value.encoding === 'base64' && typeof value.data === 'string') {
      const hex = bytesToHex(value.data);
      return {
        family: 'BLOB / BIT',
        detail: `${hex.length / 2} raw bytes`,
        formatted: `from_hex('${hex}')`,
        envelope,
      };
    }
    return {
      family: value.duckdb_type || 'STRUCT / MAP / UNION / ENVELOPE',
      detail: `Lossless Arrow provider value (${nativeType})`,
      formatted: JSON.stringify(value, null, 2),
      envelope,
    };
  }
  return {
    family: typeof value === 'string' && /^-?\d{16,39}(\.\d+)?$/.test(value) ? 'EXACT NUMERIC (BIGINT / HUGEINT / DECIMAL)' : typeof value,
    detail: `Native type ${nativeType}`,
    formatted: String(value),
    envelope,
  };
}

/**
 * SR-F-030595: DuckDB Arrow 19-Family Value & Input Envelope Cell Inspector.
 */
export function DataDuckdbCellInspectorModal({
  open,
  column = null,
  value = null,
  onClose,
}) {
  if (!open) return null;

  const info = classifyDuckdbCell(value, column);

  return (
    <Dialog
      open={open}
      title={gettext('Inspect DuckDB Arrow Value, Nested Container & Input Envelope')}
      onClose={onClose}
      size="md"
    >
      <Stack gap="md">
        <Stack direction="row" gap="sm">
          <FormReference reference="SR-F-030595" />
          <Badge status="info" label={`Type: ${column?.native_type || column?.type || 'UNKNOWN'}`} />
          <Badge status="success" label={`Family: ${info.family}`} />
          {column?.generated && <Badge status="warning" label={gettext('GENERATED ALWAYS')} />}
        </Stack>
        <Banner status="info">
          {gettext(
            'DuckDB cells stream through lossless Arrow vectors preserving 128-bit HUGEINT/UHUGEINT, exact DECIMAL, BLOB/BIT, TIME_TZ, INTERVAL, LIST/ARRAY, STRUCT, MAP, UNION and VARIANT values alongside column input_envelope write specs.'
          )}
        </Banner>
        <div>
          <strong>{gettext('Representation')}:</strong> {info.detail}
        </div>
        <CodeEditor value={info.formatted} language="text" readOnly minHeight={130} />
        {info.envelope && (
          <Panel style={{padding: 10}}>
            <strong>{gettext('Admitted Column Write Envelope (input_envelope)')}</strong>
            <pre style={{margin: 0, maxHeight: 120, overflow: 'auto', whiteSpace: 'pre-wrap'}}>
              {JSON.stringify(info.envelope, null, 2)}
            </pre>
          </Panel>
        )}
        <Button variant="secondary" onClick={onClose}>
          {gettext('Close')}
        </Button>
      </Stack>
    </Dialog>
  );
}

DataDuckdbCellInspectorModal.propTypes = {
  open: PropTypes.bool.isRequired,
  column: PropTypes.object,
  value: PropTypes.any,
  onClose: PropTypes.func.isRequired,
};
