/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Grid, Panel, Stack} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {TextArea} from '../primitives/Field';
import {Checkbox, Select} from '../primitives/Choice';
import {Banner, ValidationMessage} from '../feedback/Indicators';
import {Dialog} from '../overlays/Dialog';
import CodeEditor from '../editors/CodeEditor';
import {BLOB_EDIT_LIMIT, blobBytes, blobDraft, blobImport} from '../../Dialogs/firebirdBlobValue';
import {generateRowSql} from '../../Dialogs/firebirdRowSqlHelpers';

function renderHexPreview(bytes, maxBytes = 4096) {
  const view = bytes.subarray(0, maxBytes);
  const lines = [];
  for (let offset = 0; offset < view.length; offset += 16) {
    const slice = view.subarray(offset, offset + 16);
    const hex = Array.from(slice, (b) => b.toString(16).padStart(2, '0')).join(' ');
    const ascii = Array.from(slice, (b) => (b >= 32 && b <= 126 ? String.fromCharCode(b) : '.')).join('');
    lines.push(`${offset.toString(16).padStart(8, '0')}  ${hex.padEnd(47, ' ')}  |${ascii}|`);
  }
  if (bytes.length > maxBytes) {
    lines.push(`... (${bytes.length - maxBytes} additional bytes omitted from preview; export to save full value)`);
  }
  return lines.join('\n') || gettext('-- Empty BLOB (0 bytes) --');
}

function normalizeIncomingBlobValue(rawValue, kind) {
  if (rawValue === null || rawValue === undefined) {
    return {isNull: true, text: ''};
  }
  if (typeof rawValue === 'object' && rawValue.encoding === 'base64') {
    return {isNull: false, text: String(rawValue.data || '')};
  }
  return {isNull: false, text: String(rawValue)};
}

/**
 * FB-UI-11 / FB-COMP-12: Dedicated Firebird BLOB Editor Dialog (SR-F-001360)
 * using 100% cdeadmin_ui primitives.
 */
export function DataFirebirdBlobDialog({
  open,
  column,
  rawValue,
  readOnly = false,
  onApplyValue,
  onClose,
}) {
  const kind = column?.input_kind === 'binary' || column?.sub_type === 0 ? 'binary' : 'text';
  const initial = useMemo(() => normalizeIncomingBlobValue(rawValue, kind), [rawValue, kind]);

  const [draft, setDraft] = useState(initial);
  const [originalText, setOriginalText] = useState(initial.text);
  const [changed, setChanged] = useState(false);
  const [endings, setEndings] = useState('preserve');
  const [viewMode, setViewMode] = useState(kind === 'binary' ? 'hex' : 'edit'); // 'edit' | 'hex'
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const fileRef = useRef(null);
  const genRef = useRef(0);

  useEffect(() => {
    genRef.current += 1;
    setDraft(initial);
    setOriginalText(initial.text);
    setChanged(false);
    setEndings('preserve');
    setViewMode(kind === 'binary' ? 'hex' : 'edit');
    setError('');
    setBusy(false);
  }, [initial, kind, open]);

  if (!open || !column) return null;

  let currentBytes = new Uint8Array(0);
  let oversized = false;
  try {
    if (!draft.isNull) {
      currentBytes = blobBytes(draft.text, kind);
      oversized = currentBytes.byteLength > BLOB_EDIT_LIMIT;
    }
  } catch {
    // Validated explicitly on Apply / Export
  }

  const handleImportFile = async (e) => {
    const file = e.target.files?.[0];
    if (e.target) e.target.value = '';
    if (!file || readOnly) return;
    const token = ++genRef.current;
    setBusy(true);
    setError('');
    try {
      if (file.size > BLOB_EDIT_LIMIT) {
        throw new Error(gettext('File exceeds the 1 MiB editor limit. Use chunked query stream transfer.'));
      }
      const importedText = blobImport(new Uint8Array(await file.arrayBuffer()), kind);
      if (token === genRef.current) {
        setDraft({isNull: false, text: importedText});
        setOriginalText(importedText);
        setChanged(true);
        setEndings('preserve');
      }
    } catch (err) {
      if (token === genRef.current) setError(err?.message || String(err));
    } finally {
      if (token === genRef.current) setBusy(false);
    }
  };

  const handleExportFile = () => {
    setError('');
    try {
      const resolved = blobDraft(originalText, draft, kind, endings, changed);
      const bytes = blobBytes(resolved.text, kind);
      const url = URL.createObjectURL(
        new Blob([bytes], {
          type: kind === 'text' ? 'text/plain;charset=utf-8' : 'application/octet-stream',
        })
      );
      const a = document.createElement('a');
      a.href = url;
      a.download = `${column.name || 'firebird-blob'}.${kind === 'text' ? 'txt' : 'bin'}`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      setError(err?.message || String(err));
    }
  };

  const handleApply = () => {
    setError('');
    try {
      const resolved = blobDraft(originalText, draft, kind, endings, changed);
      if (resolved.isNull) {
        onApplyValue(null);
      } else if (kind === 'binary') {
        const bytes = blobBytes(resolved.text, 'binary');
        onApplyValue({
          encoding: 'base64',
          data: resolved.text,
          byte_length: bytes.byteLength,
        });
      } else {
        onApplyValue(resolved.text);
      }
      onClose();
    } catch (err) {
      setError(err?.message || String(err));
    }
  };

  return (
    <Dialog
      open={open}
      title={gettext('%s — Dedicated Firebird BLOB Editor', column.name)}
      formReference="SR-F-001360"
      size="large"
      busy={busy}
      onClose={busy ? undefined : onClose}
      actions={
        <>
          <Button intent="neutral" disabled={busy} onClick={onClose}>
            {gettext('Cancel')}
          </Button>
          {!readOnly && (
            <Button intent="primary" disabled={busy || oversized} onClick={handleApply}>
              {gettext('Stage in Row')}
            </Button>
          )}
        </>
      }
    >
      <Stack gap="standard" data-cdeadmin-qa-key="data-surface.firebird-blob-dialog">
        <Banner status="info">
          {gettext(
            'Stages materialized text (strict UTF-8) or binary BLOB values up to 1 MiB without dispatching SQL immediately. NULL and empty 0-byte values remain distinct.'
          )}
        </Banner>
        {oversized && (
          <Banner status="warning">
            {gettext('This BLOB exceeds the 1 MiB inline editor limit. Use the SQL Editor Stream Reader for chunked inspection.')}
          </Banner>
        )}
        {error && <ValidationMessage status="error">{error}</ValidationMessage>}

        <Grid columns="repeat(auto-fit, minmax(200px, 1fr))">
          <Select
            label={gettext('BLOB value state')}
            size="small"
            options={[
              {value: 'value', label: gettext('Non-NULL value (may be 0 bytes)')},
              {value: 'null', label: 'NULL'},
            ]}
            value={draft.isNull ? 'null' : 'value'}
            disabled={readOnly || busy || oversized}
            onChange={(val) => {
              setChanged(true);
              setDraft((cur) => ({...cur, isNull: val === 'null'}));
            }}
          />
          {kind === 'text' && (
            <Select
              label={gettext('Line endings')}
              size="small"
              options={[
                {value: 'preserve', label: gettext('Preserve original (refuses ambiguous CR edits)')},
                {value: 'lf', label: 'LF (\\n)'},
                {value: 'crlf', label: 'CRLF (\\r\\n)'},
              ]}
              value={endings}
              disabled={readOnly || busy || oversized || draft.isNull}
              onChange={(val) => setEndings(val)}
            />
          )}
          <Select
            label={gettext('Representation')}
            size="small"
            options={[
              {value: 'edit', label: kind === 'text' ? gettext('UTF-8 Text') : gettext('Canonical Base64')},
              {value: 'hex', label: gettext('Hexadecimal + ASCII Inspector')},
            ]}
            value={viewMode}
            disabled={busy || draft.isNull}
            onChange={(val) => setViewMode(val)}
          />
        </Grid>

        {!draft.isNull && !oversized && (
          viewMode === 'hex' ? (
            <CodeEditor
              label={gettext('Hexadecimal / ASCII inspection (%s bytes)', currentBytes.byteLength)}
              readonly
              language="text"
              value={renderHexPreview(currentBytes)}
            />
          ) : (
            <TextArea
              label={kind === 'text' ? gettext('BLOB UTF-8 text') : gettext('BLOB Base64 payload')}
              rows={10}
              readOnly={readOnly}
              value={draft.text}
              onChange={(e) => {
                setChanged(true);
                setDraft((cur) => ({...cur, text: e.target.value}));
              }}
            />
          )
        )}

        <Stack direction="row" gap="standard" style={{flexWrap: 'wrap'}}>
          <input
            ref={fileRef}
            type="file"
            hidden
            aria-label={gettext('Import BLOB file')}
            disabled={readOnly || busy}
            onChange={handleImportFile}
          />
          {!readOnly && (
            <Button size="small" intent="neutral" disabled={busy} onClick={() => fileRef.current?.click()}>
              {gettext('Import File (≤ 1 MiB)')}
            </Button>
          )}
          <Button size="small" intent="neutral" disabled={busy || draft.isNull || oversized} onClick={handleExportFile}>
            {gettext('Export File')}
          </Button>
        </Stack>
      </Stack>
    </Dialog>
  );
}

DataFirebirdBlobDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  column: PropTypes.object,
  rawValue: PropTypes.any,
  readOnly: PropTypes.bool,
  onApplyValue: PropTypes.func.isRequired,
  onClose: PropTypes.func.isRequired,
};

/**
 * FB-UI-11 / FB-COMP-06: Selected-Row Native Firebird SQL Generator Dialog (SR-F-001362).
 */
export function DataFirebirdRowSqlDialog({
  open,
  tableName,
  columns = [],
  fetchedRows = [],
  initialSelectedIndices = [],
  clientSqlDialect = 3,
  callHost = null,
  onOpenInSqlEditor,
  onClose,
}) {
  const cleanRows = useMemo(
    () =>
      fetchedRows
        .filter((r) => !r?.isDraftInsert && r?.stage_state !== 'inserted')
        .map((r) => (r && typeof r.values === 'object' && r.values !== null ? r : {values: r || {}})),
    [fetchedRows]
  );

  const normalizedCols = useMemo(
    () =>
      columns.map((c) => {
        const typeStr = c.native_type || c.data_type || '';
        return {
          ...c,
          input_kind:
            c.input_kind ||
            (/INT|SMALLINT|BIGINT|INT128/i.test(typeStr)
              ? 'integer'
              : /DECFLOAT/i.test(typeStr)
                ? 'decfloat'
                : /NUMERIC|DECIMAL/i.test(typeStr)
                  ? 'decimal'
                  : /BOOL/i.test(typeStr)
                    ? 'boolean'
                    : 'text'),
        };
      }),
    [columns]
  );

  const [selectedIndices, setSelectedIndices] = useState([]);
  const [operation, setOperation] = useState('insert');
  const [inlineLiterals, setInlineLiterals] = useState(false);
  const [matchingKeys, setMatchingKeys] = useState([]);
  const [inColumn, setInColumn] = useState('');
  const [plans, setPlans] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    setSelectedIndices(
      initialSelectedIndices.length
        ? initialSelectedIndices.filter((i) => i >= 0 && i < cleanRows.length).slice(0, 100)
        : cleanRows.length
          ? [0]
          : []
    );
    setMatchingKeys(
      normalizedCols
        .filter((c) => c.key === true || c.primary_key === true || c.identity_key)
        .map((c) => c.name)
    );
    setInColumn(normalizedCols[0]?.name || '');
    setPlans([]);
    setError('');
  }, [cleanRows.length, initialSelectedIndices, normalizedCols, open]);

  if (!open) return null;

  const toggleIndex = (idx) => {
    setPlans([]);
    setError('');
    setSelectedIndices((cur) =>
      cur.includes(idx) ? cur.filter((x) => x !== idx) : [...cur, idx]
    );
  };

  const toggleKey = (colName) => {
    setPlans([]);
    setError('');
    setMatchingKeys((cur) =>
      cur.includes(colName) ? cur.filter((x) => x !== colName) : [...cur, colName]
    );
  };

  const handleGenerate = async () => {
    setError('');
    try {
      const chosenRows = cleanRows.filter((_r, idx) => selectedIndices.includes(idx));
      if (!chosenRows.length) throw new Error(gettext('Select at least one fetched row.'));
      if ((operation === 'update' || operation === 'upsert') && !matchingKeys.length) {
        throw new Error(gettext('Select at least one explicit matching key column.'));
      }
      if (callHost) {
        const hostRes = await callHost('generate_row_sql', {
          table_label: tableName,
          columns: normalizedCols,
          rows: chosenRows,
          mode: operation,
          key_columns: matchingKeys,
          in_column: inColumn,
          inline_literals: inlineLiterals,
        });
        if (Array.isArray(hostRes?.plans) && hostRes.plans.length) {
          setPlans(hostRes.plans);
          return;
        }
      }
      const generated = generateRowSql({
        table: tableName,
        columns: normalizedCols,
        rows: chosenRows,
        operation,
        keys: matchingKeys,
        inColumn,
        inline: inlineLiterals,
        dialect: clientSqlDialect,
      });
      setPlans(generated);
    } catch (err) {
      setError(err?.message || String(err));
      setPlans([]);
    }
  };

  return (
    <Dialog
      open={open}
      title={gettext('Generate Native Firebird Row SQL — %s', tableName)}
      formReference="SR-F-001362"
      size="large"
      onClose={onClose}
      actions={
        <>
          <Button intent="neutral" onClick={onClose}>
            {gettext('Close')}
          </Button>
          <Button intent="primary" disabled={!selectedIndices.length} onClick={handleGenerate}>
            {gettext('Generate SQL Preview')}
          </Button>
        </>
      }
    >
      <Stack gap="standard" data-cdeadmin-qa-key="data-surface.firebird-row-sql-dialog">
        <Banner status="info">
          {gettext(
            'Generates native INSERT, UPDATE, UPDATE OR INSERT, or IN-list predicates from fetched rows (excluding unsaved drafts). Preview never executes mutations automatically.'
          )}
        </Banner>
        {error && <ValidationMessage status="error">{error}</ValidationMessage>}

        <Grid columns="repeat(auto-fit, minmax(220px, 1fr))">
          <Select
            label={gettext('SQL operation')}
            size="small"
            options={[
              {value: 'insert', label: 'INSERT INTO … VALUES'},
              {value: 'update', label: 'UPDATE … SET … WHERE (IS NOT DISTINCT FROM)'},
              {value: 'upsert', label: 'UPDATE OR INSERT INTO … MATCHING'},
              {value: 'in', label: 'SELECT … WHERE col IN (…) / IS NULL'},
            ]}
            value={operation}
            onChange={(val) => {
              setOperation(val);
              setPlans([]);
            }}
          />
          {operation === 'in' && (
            <Select
              label={gettext('IN-list column')}
              size="small"
              options={normalizedCols.map((c) => ({value: c.name, label: c.name}))}
              value={inColumn}
              onChange={(val) => {
                setInColumn(val);
                setPlans([]);
              }}
            />
          )}
          <Checkbox
            label={gettext('Inline admitted scalar literals (instead of ? bound parameters)')}
            checked={inlineLiterals}
            onChange={(v) => {
              setInlineLiterals(Boolean(v));
              setPlans([]);
            }}
          />
        </Grid>

        {(operation === 'update' || operation === 'upsert') && (
          <Panel variant="outlined" style={{padding: 10}}>
            <Stack gap="tight">
              <strong style={{fontSize: '0.8rem'}}>{gettext('Explicit Matching Key Columns')}</strong>
              <Stack direction="row" gap="standard" style={{flexWrap: 'wrap'}}>
                {normalizedCols.map((c) => (
                  <Checkbox
                    key={c.name}
                    label={c.name}
                    checked={matchingKeys.includes(c.name)}
                    onChange={() => toggleKey(c.name)}
                  />
                ))}
              </Stack>
            </Stack>
          </Panel>
        )}

        <Panel variant="outlined" style={{padding: 10}}>
          <Stack gap="tight">
            <Stack direction="row" gap="standard" style={{justifyContent: 'space-between', alignItems: 'center'}}>
              <strong style={{fontSize: '0.8rem'}}>
                {gettext('Fetched Page Rows')} ({selectedIndices.length} / {Math.min(cleanRows.length, 100)} {gettext('selected')})
              </strong>
              <Stack direction="row" gap="tight">
                <Button
                  size="small"
                  intent="neutral"
                  onClick={() => setSelectedIndices(cleanRows.slice(0, 100).map((_r, i) => i))}
                >
                  {gettext('Select First 100')}
                </Button>
                <Button size="small" intent="neutral" onClick={() => setSelectedIndices([])}>
                  {gettext('Clear')}
                </Button>
              </Stack>
            </Stack>
            <Box sx={{maxHeight: 140, overflow: 'auto', display: 'flex', flexWrap: 'wrap', gap: 1}}>
              {cleanRows.slice(0, 100).map((row, idx) => (
                <Checkbox
                  key={row.identity_token || idx}
                  label={gettext('Row #%s', row.row_number || idx + 1)}
                  checked={selectedIndices.includes(idx)}
                  onChange={() => toggleIndex(idx)}
                />
              ))}
            </Box>
          </Stack>
        </Panel>

        {plans.length > 0 && (
          <Stack gap="standard">
            <CodeEditor
              label={gettext('Generated Firebird SQL (%s statement(s))', plans.length)}
              readonly
              language="sql"
              value={plans.map((p) => p.source).join('\n')}
            />
            {!inlineLiterals && (
              <CodeEditor
                label={gettext('Ordered bound wire parameter arrays')}
                readonly
                language="json"
                value={JSON.stringify(plans.map((p) => p.parameters), null, 2)}
              />
            )}
            {onOpenInSqlEditor && (
              <Stack direction="row" gap="standard" style={{justifyContent: 'flex-end'}}>
                <Button
                  size="small"
                  intent="primary"
                  onClick={() => {
                    const combinedSql = plans.map((p) => p.source).join('\n');
                    onOpenInSqlEditor({
                      source: combinedSql,
                      initial_sql: combinedSql,
                      parameters: plans.length === 1 ? plans[0].parameters : plans.map((p) => p.parameters),
                    });
                    onClose();
                  }}
                >
                  {gettext('Load into SQL Editor (Without Executing)')}
                </Button>
              </Stack>
            )}
          </Stack>
        )}
      </Stack>
    </Dialog>
  );
}

DataFirebirdRowSqlDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  tableName: PropTypes.string.isRequired,
  columns: PropTypes.array,
  fetchedRows: PropTypes.array,
  initialSelectedIndices: PropTypes.array,
  clientSqlDialect: PropTypes.number,
  callHost: PropTypes.func,
  onOpenInSqlEditor: PropTypes.func,
  onClose: PropTypes.func.isRequired,
};
