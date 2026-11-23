/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Grid, Panel, Stack} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {TextField} from '../primitives/Field';
import {Select} from '../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../feedback/Indicators';
import {Dialog} from '../overlays/Dialog';
import FormReference from '../navigation/FormReference';
import CodeEditor from '../editors/CodeEditor';

function quoteSqliteIdent(name) {
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

function formatSqliteLiteral(val) {
  if (val === null || val === undefined) return 'NULL';
  if (typeof val === 'boolean') return val ? '1' : '0';
  if (typeof val === 'number') {
    if (!Number.isFinite(val)) return 'NULL';
    return String(val);
  }
  if (typeof val === 'object') {
    if (val.encoding === 'base64' && typeof val.data === 'string') {
      return `X'${bytesToHex(val.data)}'`;
    }
    if (typeof val.decimal === 'string' || typeof val.int64 === 'string') {
      return val.decimal || val.int64;
    }
    return `'${JSON.stringify(val).replace(/'/g, '\'\'')}'`;
  }
  return `'${String(val).replace(/'/g, '\'\'')}'`;
}

/**
 * SR-F-030569: SQLite Row SQL Generator (ON CONFLICT DO UPDATE, INSERT OR REPLACE,
 * INSERT OR IGNORE, UPDATE, DELETE with X'...' hex BLOBs and 64-bit integer literals).
 */
export function DataSqliteRowSqlDialog({
  open,
  tableLabel = 'main.table',
  columns = [],
  row = null,
  callHost = null,
  onClose,
}) {
  const [mode, setMode] = useState('upsert');
  const [keyCol, setKeyCol] = useState(columns?.[0]?.name || 'rowid');
  const [hostSql, setHostSql] = useState(null);

  useEffect(() => {
    let active = true;
    if (!open || !callHost || !row || !columns?.length) {
      setHostSql(null);
      return undefined;
    }
    callHost('generate_row_sql', {
      table_label: tableLabel,
      columns,
      rows: [row],
      mode,
      key_columns: [keyCol || columns?.[0]?.name || 'rowid'],
      inline_literals: true,
    })
      .then((res) => {
        if (active && typeof res?.sql === 'string') setHostSql(res.sql);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [callHost, columns, keyCol, mode, open, row, tableLabel]);

  const fallbackSql = useMemo(() => {
    const colNames = (columns || []).map((c) => c.name).filter(Boolean);
    if (!colNames.length || !row) return '-- Select a row to generate SQLite SQL';
    const valuesMap = Array.isArray(row)
      ? Object.fromEntries(colNames.map((n, idx) => [n, row[idx]]))
      : row;
    const quotedCols = colNames.map(quoteSqliteIdent).join(', ');
    const formattedVals = colNames.map((n) => formatSqliteLiteral(valuesMap[n])).join(', ');
    const pkName = keyCol || colNames[0];
    const pk = quoteSqliteIdent(pkName);
    const pkVal = formatSqliteLiteral(valuesMap[pkName] ?? 1);

    switch (mode) {
    case 'replace':
      return `INSERT OR REPLACE INTO ${tableLabel} (${quotedCols})\nVALUES (${formattedVals});`;
    case 'ignore':
      return `INSERT OR IGNORE INTO ${tableLabel} (${quotedCols})\nVALUES (${formattedVals});`;
    case 'update': {
      const sets = colNames
        .filter((c) => c !== pkName)
        .map((c) => `${quoteSqliteIdent(c)} = ${formatSqliteLiteral(valuesMap[c])}`)
        .join(',\n    ');
      return `UPDATE ${tableLabel}\nSET ${sets || `${pk} = ${pkVal}`}\nWHERE ${pk} = ${pkVal};`;
    }
    case 'delete':
      return `DELETE FROM ${tableLabel}\nWHERE ${pk} = ${pkVal};`;
    default: {
      const updates = colNames
        .filter((c) => c !== pkName)
        .map((c) => `${quoteSqliteIdent(c)} = excluded.${quoteSqliteIdent(c)}`)
        .join(',\n    ');
      return `INSERT INTO ${tableLabel} (${quotedCols})\nVALUES (${formattedVals})\nON CONFLICT (${pk}) DO UPDATE\nSET ${updates || `${pk} = excluded.${pk}`};`;
    }
    }
  }, [columns, keyCol, mode, row, tableLabel]);
  const sqlText = hostSql ?? fallbackSql;

  if (!open) return null;

  return (
    <Dialog
      open={open}
      title={gettext('Generate SQLite Row SQL')}
      onClose={onClose}
      size="lg"
    >
      <Stack gap="md">
        <FormReference reference="SR-F-030569" />
        <Grid columns={2} gap="sm">
          <Select
            label={gettext('SQLite Statement Variant')}
            value={mode}
            options={[
              {value: 'upsert', label: 'INSERT ... ON CONFLICT DO UPDATE'},
              {value: 'replace', label: 'INSERT OR REPLACE INTO ...'},
              {value: 'ignore', label: 'INSERT OR IGNORE INTO ...'},
              {value: 'update', label: 'UPDATE ... WHERE key = ...'},
              {value: 'delete', label: 'DELETE FROM ... WHERE key = ...'},
            ]}
            onChange={setMode}
          />
          <TextField
            label={gettext('Conflict / Rowid / Primary Key Column')}
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

DataSqliteRowSqlDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  tableLabel: PropTypes.string,
  columns: PropTypes.array,
  row: PropTypes.oneOfType([PropTypes.object, PropTypes.array]),
  callHost: PropTypes.func,
  onClose: PropTypes.func.isRequired,
};

function classifySqliteCell(value) {
  if (value === null || value === undefined) {
    return {storageClass: 'NULL', detail: 'SQL NULL', formatted: 'NULL', unsafeInt64: false, hasNul: false};
  }
  if (typeof value === 'number') {
    const isInt = Number.isInteger(value);
    const unsafe = isInt && !Number.isSafeInteger(value);
    return {
      storageClass: isInt ? 'INTEGER' : 'REAL',
      detail: isInt ? `64-bit signed integer${unsafe ? ' (> MAX_SAFE_INTEGER)' : ''}` : 'IEEE-754 8-byte float',
      formatted: String(value),
      unsafeInt64: unsafe,
      hasNul: false,
    };
  }
  if (typeof value === 'string') {
    const isExactIntStr = /^-?\d{16,20}$/.test(value);
    let unsafe = false;
    if (isExactIntStr) {
      try {
        const bi = window.BigInt(value);
        unsafe = bi > window.BigInt(Number.MAX_SAFE_INTEGER) || bi < window.BigInt(Number.MIN_SAFE_INTEGER);
      } catch {
        unsafe = false;
      }
    }
    const hasNul = value.includes('\u0000');
    const utf8Bytes = new TextEncoder().encode(value).length;
    return {
      storageClass: unsafe ? 'INTEGER (64-bit exact string)' : 'TEXT',
      detail: `${utf8Bytes} UTF-8 bytes${hasNul ? ' (contains embedded NUL 0x00)' : ''}`,
      formatted: value,
      unsafeInt64: unsafe,
      hasNul,
    };
  }
  if (typeof value === 'object') {
    if (value.encoding === 'base64' && typeof value.data === 'string') {
      const hex = bytesToHex(value.data);
      return {
        storageClass: 'BLOB',
        detail: `${hex.length / 2} raw bytes`,
        formatted: `X'${hex}'`,
        unsafeInt64: false,
        hasNul: false,
      };
    }
    return {
      storageClass: 'STRUCTURED / ENVELOPE',
      detail: 'Exact provider value envelope',
      formatted: JSON.stringify(value, null, 2),
      unsafeInt64: Boolean(value.int64 || value.decimal),
      hasNul: false,
    };
  }
  return {
    storageClass: typeof value,
    detail: 'Scalar value',
    formatted: String(value),
    unsafeInt64: false,
    hasNul: false,
  };
}

/**
 * SR-F-030570: SQLite Dynamic Storage-Class, Int64, UTF-8/NUL & Incremental BLOB Cell Inspector.
 */
export function DataSqliteCellInspectorModal({
  open,
  column = null,
  value = null,
  tableName = '',
  post = null,
  databaseTargetId = '',
  onClose,
}) {
  const [streamRowid, setStreamRowid] = useState('1');
  const [blobMeta, setBlobMeta] = useState(null);
  const [streamError, setStreamError] = useState('');
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  const info = classifySqliteCell(value);

  const handleInspectLiveBlob = async () => {
    if (!post || !tableName || !column?.name) return;
    setBusy(true);
    setStreamError('');
    try {
      const res = await post({
        action: 'sqlite_ops_blob_inspect',
        request: {
          ...(databaseTargetId ? {database_target_id: databaseTargetId} : {}),
          schema_name: 'main',
          table_name: tableName,
          column_name: column.name,
          rowid: Number(streamRowid),
        },
      });
      setBlobMeta(res);
    } catch (err) {
      setStreamError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      title={gettext('Inspect SQLite Dynamic Storage Class, Bytes & BLOB Handle')}
      onClose={onClose}
      size="md"
    >
      <Stack gap="md">
        <Stack direction="row" gap="sm">
          <FormReference reference="SR-F-030570" />
          <Badge status="info" label={`Affinity: ${column?.native_type || column?.type || 'ANY'}`} />
          <Badge status="success" label={`Storage: ${info.storageClass}`} />
          {info.unsafeInt64 && <Badge status="warning" label={gettext('> 53-bit Exact Int64')} />}
          {info.hasNul && <Badge status="warning" label={gettext('Embedded NUL (0x00)')} />}
        </Stack>
        <Banner status="info">
          {gettext(
            'SQLite stores per-cell dynamic types (NULL, INTEGER, REAL, TEXT, BLOB) independently of column affinity. Exact 64-bit integers and hex BLOB bytes are preserved without narrowing.'
          )}
        </Banner>
        <div>
          <strong>{gettext('Representation')}:</strong> {info.detail}
        </div>
        <CodeEditor value={info.formatted} language="text" readOnly minHeight={130} />

        {post && tableName && column?.name && (
          <Panel style={{padding: 10}}>
            <strong>{gettext('Live sqlite3_blob_open Cell Handle Probe')}</strong>
            {streamError && <ValidationMessage status="error">{streamError}</ValidationMessage>}
            <Grid columns={2} gap="sm">
              <TextField
                label={gettext('Physical rowid')}
                value={streamRowid}
                onChange={(e) => setStreamRowid(e?.target ? e.target.value : String(e ?? ''))}
              />
              <div style={{display: 'flex', alignItems: 'flex-end'}}>
                <Button disabled={busy} onClick={handleInspectLiveBlob}>
                  {gettext('Probe sqlite3_blob_open Metadata')}
                </Button>
              </div>
            </Grid>
            {blobMeta && (
              <Stack direction="row" gap="sm">
                <Badge status="info" label={`typeof=${blobMeta.typeof}`} />
                <Badge status="info" label={`bytes=${blobMeta.byte_length ?? blobMeta.text_or_scalar_bytes ?? 0}`} />
                <Badge
                  status={blobMeta.streamable_blob ? 'success' : 'warning'}
                  label={blobMeta.streamable_blob ? gettext('Streamable BLOB') : gettext('Non-BLOB')}
                />
              </Stack>
            )}
          </Panel>
        )}

        <Button variant="secondary" onClick={onClose}>
          {gettext('Close')}
        </Button>
      </Stack>
    </Dialog>
  );
}

DataSqliteCellInspectorModal.propTypes = {
  open: PropTypes.bool.isRequired,
  column: PropTypes.object,
  value: PropTypes.any,
  tableName: PropTypes.string,
  post: PropTypes.func,
  databaseTargetId: PropTypes.string,
  onClose: PropTypes.func.isRequired,
};
