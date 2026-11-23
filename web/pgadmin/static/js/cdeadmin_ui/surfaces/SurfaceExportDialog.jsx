/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {TextArea, TextField} from '../primitives/Field';
import {Dialog} from '../overlays/Dialog';
import {formatRowsForExport} from './dataEditSurfaceHelpers';

const EXPORT_FORMATS = Object.freeze([
  {id: 'csv', label: 'CSV (.csv)'},
  {id: 'tsv', label: 'TSV (.tsv)'},
  {id: 'xlsx', label: 'Excel (.xlsx)'},
  {id: 'ods', label: 'OpenDocument (.ods)'},
  {id: 'pdf', label: 'PDF Report (.pdf)'},
  {id: 'json', label: 'JSON (.json)'},
  {id: 'sql_insert', label: 'SQL INSERT (.sql)'},
  {id: 'sql_update', label: 'SQL UPDATE (.sql)'},
]);

function triggerBrowserDownload(bytesOrText, filename, mimeType) {
  if (typeof Blob === 'undefined' || typeof URL?.createObjectURL !== 'function') {
    return;
  }
  const blob =
    bytesOrText instanceof Uint8Array
      ? new Blob([bytesOrText], {type: mimeType || 'application/octet-stream'})
      : new Blob([String(bytesOrText ?? '')], {
        type: mimeType || 'text/plain;charset=utf-8',
      });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename || 'export.dat';
  anchor.click();
  URL.revokeObjectURL(url);
}

function decodeBase64ToBytes(b64) {
  const bin = typeof atob === 'function' ? atob(b64) : '';
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) {
    arr[i] = bin.charCodeAt(i);
  }
  return arr;
}

/**
 * Shared Surface 1 & Surface 2 Multi-Format Export Dialog with format-specific
 * settings for CSV/TSV, XLSX, ODS, PDF, JSON, SQL INSERT, and SQL UPDATE.
 */
export default function SurfaceExportDialog({
  open,
  onClose,
  initialFormat = 'csv',
  defaultFilename = 'query_result',
  defaultTitle = '',
  tableName = 'EXPORT_TABLE',
  rows = [],
  columns = [],
  selectedRows = null,
  selectedColumns = null,
  hasMultiSelection = false,
  allRowsSelected = false,
  selectionLabel = '',
  onExportHost = null,
}) {
  const canUseSelection =
    Array.isArray(selectedRows) &&
    selectedRows.length > 0 &&
    Array.isArray(selectedColumns) &&
    selectedColumns.length > 0;
  const [format, setFormat] = useState(initialFormat || 'csv');
  const [filename, setFilename] = useState(defaultFilename || 'query_result');
  const [scope, setScope] = useState(
    hasMultiSelection && canUseSelection ? 'selection' : 'filtered'
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  // CSV / TSV settings
  const [delimiter, setDelimiter] = useState(',');
  const [quoteChar, setQuoteChar] = useState('"');
  const [quoting, setQuoting] = useState('minimal');
  const [includeHeader, setIncludeHeader] = useState(true);
  const [nullString, setNullString] = useState('');
  const [encoding, setEncoding] = useState('utf-8');
  const [lineEnding, setLineEnding] = useState('lf');

  // XLSX / ODS settings
  const [sheetName, setSheetName] = useState('Data');
  const [freezeHeader, setFreezeHeader] = useState(true);
  const [autoFilter, setAutoFilter] = useState(true);
  const [typedCells, setTypedCells] = useState(true);
  const [includeSqlSheet, setIncludeSqlSheet] = useState(true);

  // PDF settings
  const [pageSize, setPageSize] = useState('letter');
  const [orientation, setOrientation] = useState('landscape');
  const [pdfTitle, setPdfTitle] = useState(defaultTitle || defaultFilename || 'Query Report');
  const [pdfSubtitle, setPdfSubtitle] = useState('');
  const [fontSize, setFontSize] = useState('8.5');
  const [showFooter, setShowFooter] = useState(true);
  const [includeSqlAppendix, setIncludeSqlAppendix] = useState(false);

  // SQL settings
  const [sqlTable, setSqlTable] = useState(tableName || 'EXPORT_TABLE');

  useEffect(() => {
    if (!open) return;
    const fmt = initialFormat || 'csv';
    setFormat(fmt);
    if (fmt === 'tsv') setDelimiter('\t');
    else if (fmt === 'csv' && delimiter === '\t') setDelimiter(',');
    setFilename(defaultFilename || 'query_result');
    setPdfTitle(defaultTitle || defaultFilename || 'Query Report');
    setSqlTable(tableName || 'EXPORT_TABLE');
    setScope(hasMultiSelection && canUseSelection ? 'selection' : 'filtered');
    setError('');
  }, [
    open,
    initialFormat,
    defaultFilename,
    defaultTitle,
    tableName,
    hasMultiSelection,
    canUseSelection,
  ]);

  const effectiveRows =
    scope === 'selection' && canUseSelection ? selectedRows : rows;
  const effectiveColumns =
    scope === 'selection' && canUseSelection ? selectedColumns : columns;

  const selectFormat = (nextFmt) => {
    setFormat(nextFmt);
    if (nextFmt === 'tsv') setDelimiter('\t');
    else if (nextFmt === 'csv' && delimiter === '\t') setDelimiter(',');
  };

  const isTextPreviewable = ['csv', 'tsv', 'json', 'sql_insert', 'sql_update'].includes(format);

  const handleRunExport = async () => {
    setError('');
    if (format === 'sql_insert' || format === 'sql_update' || !onExportHost) {
      const content = formatRowsForExport(
        effectiveRows,
        effectiveColumns,
        format,
        sqlTable || tableName || 'EXPORT_TABLE'
      );
      navigator.clipboard?.writeText?.(content).catch(() => {});
      const ext = format.startsWith('sql') ? 'sql' : format;
      triggerBrowserDownload(content, `${filename || 'export'}.${ext}`, 'text/plain;charset=utf-8');
      onClose?.();
      return;
    }

    setBusy(true);
    try {
      const settings = {scope};
      if (scope === 'selection' && canUseSelection) {
        settings.selected_column_names = effectiveColumns.map((c) => c.name);
        if (!allRowsSelected) {
          settings.selected_rows_payload = effectiveRows.map((r) => ({
            values: r?.values || r || {},
          }));
        }
      }
      if (format === 'csv' || format === 'tsv') {
        Object.assign(settings, {
          delimiter: format === 'tsv' && delimiter === ',' ? '\t' : delimiter,
          quotechar: quoteChar || '"',
          quoting,
          include_header: includeHeader,
          null_string: nullString,
          encoding,
          lineterminator: lineEnding === 'crlf' ? '\r\n' : '\n',
        });
      } else if (format === 'xlsx' || format === 'ods') {
        Object.assign(settings, {
          sheet_name: sheetName || 'Data',
          freeze_header: freezeHeader,
          auto_filter: autoFilter,
          typed_cells: typedCells,
          include_sql_sheet: includeSqlSheet,
        });
      } else if (format === 'pdf') {
        Object.assign(settings, {
          page_size: pageSize,
          orientation,
          title: pdfTitle,
          subtitle: pdfSubtitle,
          font_size: Number(fontSize) || 8.5,
          show_footer: showFooter,
          include_sql_appendix: includeSqlAppendix,
        });
      }
      const res = await onExportHost({
        format,
        filename: filename || defaultFilename || 'export',
        settings,
      });
      if (res?.content_base64) {
        const bytes = decodeBase64ToBytes(res.content_base64);
        triggerBrowserDownload(
          bytes,
          res.filename || `${filename || 'export'}.${format}`,
          res.mime_type || 'application/octet-stream'
        );
      }
      onClose?.();
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      title={gettext('Export Data & Format Settings')}
      size="medium"
      onClose={onClose}
      actions={
        <>
          <Button onClick={onClose} disabled={busy}>
            {gettext('Cancel')}
          </Button>
          <Button
            intent="primary"
            disabled={busy}
            data-cdeadmin-qa-key="surface-export-confirm"
            onClick={handleRunExport}
          >
            {busy ? gettext('Generating…') : gettext('Export File')}
          </Button>
        </>
      }
    >
      <Box
        data-cdeadmin-qa-key="surface-export-dialog"
        sx={{display: 'grid', gap: 1.5}}
      >
        {error && (
          <div
            role="alert"
            style={{
              padding: '8px 10px',
              borderRadius: 6,
              background: 'rgba(220, 38, 38, 0.1)',
              border: '1px solid var(--sr-status-danger, #dc2626)',
              color: 'var(--sr-status-danger, #dc2626)',
              fontSize: '0.8rem',
            }}
          >
            {error}
          </div>
        )}

        {/* Format Selector */}
        <div
          role="group"
          aria-label={gettext('Export Format')}
          style={{display: 'flex', gap: 6, flexWrap: 'wrap'}}
        >
          {EXPORT_FORMATS.map((item) => (
            <Button
              key={item.id}
              size="small"
              intent={format === item.id ? 'primary' : 'neutral'}
              data-cdeadmin-qa-key={`export-fmt-${item.id}`}
              onClick={() => selectFormat(item.id)}
            >
              {item.label}
            </Button>
          ))}
        </div>

        {/* Common Filename & Row Scope */}
        <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10}}>
          <TextField
            label={gettext('Base Filename')}
            value={filename}
            onChange={(e) => setFilename(e.target.value)}
          />
          <div className="sr-field">
            <label className="sr-field-label">{gettext('Row Scope')}</label>
            <select
              className="sr-input"
              aria-label={gettext('Row Scope')}
              value={scope}
              onChange={(e) => setScope(e.target.value)}
            >
              <option value="filtered">{gettext('Current Filtered / Sorted View')}</option>
              <option value="all">{gettext('All Host-Buffered Rows')}</option>
              {canUseSelection && (
                <option value="selection">
                  {selectionLabel
                    ? `${gettext('Current Selection')} (${selectionLabel})`
                    : `${gettext('Current Selection')} (${selectedRows.length} × ${selectedColumns.length})`}
                </option>
              )}
            </select>
          </div>
        </div>

        {/* CSV / TSV Settings */}
        {(format === 'csv' || format === 'tsv') && (
          <div
            data-cdeadmin-qa-key="export-settings-delimited"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
              gap: 10,
              padding: 10,
              borderRadius: 8,
              border: '1px solid var(--sr-border-subtle)',
            }}
          >
            <div className="sr-field">
              <label className="sr-field-label">{gettext('Delimiter')}</label>
              <select
                className="sr-input"
                aria-label={gettext('Delimiter')}
                value={delimiter}
                onChange={(e) => setDelimiter(e.target.value)}
              >
                <option value=",">{gettext('Comma (,)')}</option>
                <option value={'\t'}>{gettext('Tab (\\t)')}</option>
                <option value=";">{gettext('Semicolon (;)')}</option>
                <option value="|">{gettext('Pipe (|)')}</option>
              </select>
            </div>
            <div className="sr-field">
              <label className="sr-field-label">{gettext('Quoting Policy')}</label>
              <select
                className="sr-input"
                aria-label={gettext('Quoting Policy')}
                value={quoting}
                onChange={(e) => setQuoting(e.target.value)}
              >
                <option value="minimal">{gettext('Quote Minimal')}</option>
                <option value="all">{gettext('Quote All Fields')}</option>
                <option value="nonnumeric">{gettext('Quote Non-Numeric')}</option>
              </select>
            </div>
            <div className="sr-field">
              <label className="sr-field-label">{gettext('Encoding')}</label>
              <select
                className="sr-input"
                aria-label={gettext('Encoding')}
                value={encoding}
                onChange={(e) => setEncoding(e.target.value)}
              >
                <option value="utf-8">UTF-8</option>
                <option value="utf-8-sig">UTF-8 with BOM (Excel)</option>
                <option value="iso-8859-1">ISO-8859-1 (Latin-1)</option>
                <option value="cp1252">Windows-1252</option>
              </select>
            </div>
            <TextField
              label={gettext('Quote Character')}
              value={quoteChar}
              onChange={(e) => setQuoteChar(e.target.value.slice(0, 1) || '"')}
            />
            <TextField
              label={gettext('NULL Representation')}
              value={nullString}
              placeholder={gettext('(empty)')}
              onChange={(e) => setNullString(e.target.value)}
            />
            <div className="sr-field">
              <label className="sr-field-label">{gettext('Line Endings')}</label>
              <select
                className="sr-input"
                aria-label={gettext('Line Endings')}
                value={lineEnding}
                onChange={(e) => setLineEnding(e.target.value)}
              >
                <option value="lf">LF (\n)</option>
                <option value="crlf">CRLF (\r\n)</option>
              </select>
            </div>
            <label style={{display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', gridColumn: '1 / -1'}}>
              <input
                type="checkbox"
                checked={includeHeader}
                onChange={(e) => setIncludeHeader(e.target.checked)}
              />
              {gettext('Include column header row')}
            </label>
          </div>
        )}

        {/* XLSX / ODS Settings */}
        {(format === 'xlsx' || format === 'ods') && (
          <div
            data-cdeadmin-qa-key="export-settings-spreadsheet"
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: 10,
              padding: 10,
              borderRadius: 8,
              border: '1px solid var(--sr-border-subtle)',
            }}
          >
            <TextField
              label={gettext('Worksheet Name')}
              value={sheetName}
              onChange={(e) => setSheetName(e.target.value)}
            />
            <div style={{display: 'grid', gap: 6, alignContent: 'center'}}>
              {format === 'xlsx' && (
                <>
                  <label style={{display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem'}}>
                    <input
                      type="checkbox"
                      checked={freezeHeader}
                      onChange={(e) => setFreezeHeader(e.target.checked)}
                    />
                    {gettext('Freeze top header row')}
                  </label>
                  <label style={{display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem'}}>
                    <input
                      type="checkbox"
                      checked={autoFilter}
                      onChange={(e) => setAutoFilter(e.target.checked)}
                    />
                    {gettext('Enable column Auto-Filter')}
                  </label>
                </>
              )}
              <label style={{display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem'}}>
                <input
                  type="checkbox"
                  checked={typedCells}
                  onChange={(e) => setTypedCells(e.target.checked)}
                />
                {gettext('Preserve native numeric / boolean cell types')}
              </label>
              <label style={{display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem'}}>
                <input
                  type="checkbox"
                  checked={includeSqlSheet}
                  onChange={(e) => setIncludeSqlSheet(e.target.checked)}
                />
                {gettext('Include SQL_Metadata worksheet')}
              </label>
            </div>
          </div>
        )}

        {/* PDF Settings */}
        {format === 'pdf' && (
          <div
            data-cdeadmin-qa-key="export-settings-pdf"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
              gap: 10,
              padding: 10,
              borderRadius: 8,
              border: '1px solid var(--sr-border-subtle)',
            }}
          >
            <div className="sr-field">
              <label className="sr-field-label">{gettext('Page Size')}</label>
              <select
                className="sr-input"
                aria-label={gettext('Page Size')}
                value={pageSize}
                onChange={(e) => setPageSize(e.target.value)}
              >
                <option value="letter">Letter</option>
                <option value="legal">Legal</option>
                <option value="a4">A4</option>
                <option value="a3">A3</option>
              </select>
            </div>
            <div className="sr-field">
              <label className="sr-field-label">{gettext('Orientation')}</label>
              <select
                className="sr-input"
                aria-label={gettext('Orientation')}
                value={orientation}
                onChange={(e) => setOrientation(e.target.value)}
              >
                <option value="landscape">{gettext('Landscape')}</option>
                <option value="portrait">{gettext('Portrait')}</option>
              </select>
            </div>
            <TextField
              label={gettext('Font Size (pt)')}
              value={fontSize}
              onChange={(e) => setFontSize(e.target.value)}
            />
            <div style={{gridColumn: '1 / 3'}}>
              <TextField
                label={gettext('Report Title')}
                value={pdfTitle}
                onChange={(e) => setPdfTitle(e.target.value)}
              />
            </div>
            <TextField
              label={gettext('Subtitle')}
              value={pdfSubtitle}
              onChange={(e) => setPdfSubtitle(e.target.value)}
            />
            <label style={{display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', gridColumn: '1 / 2'}}>
              <input
                type="checkbox"
                checked={showFooter}
                onChange={(e) => setShowFooter(e.target.checked)}
              />
              {gettext('Show Page X of Y footer')}
            </label>
            <label style={{display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', gridColumn: '2 / 4'}}>
              <input
                type="checkbox"
                checked={includeSqlAppendix}
                onChange={(e) => setIncludeSqlAppendix(e.target.checked)}
              />
              {gettext('Include SQL Query Appendix page')}
            </label>
          </div>
        )}

        {/* SQL INSERT / UPDATE Settings */}
        {(format === 'sql_insert' || format === 'sql_update') && (
          <TextField
            label={gettext('Target Table Name')}
            value={sqlTable}
            onChange={(e) => setSqlTable(e.target.value)}
          />
        )}

        {/* Text Preview when applicable */}
        {isTextPreviewable && effectiveRows.length > 0 && (
          <TextArea
            rows={6}
            label={gettext('Preview (first 15 rows)')}
            value={formatRowsForExport(
              effectiveRows.slice(0, 15),
              effectiveColumns,
              format,
              sqlTable || tableName || 'EXPORT_TABLE'
            )}
            onChange={() => {}}
          />
        )}
      </Box>
    </Dialog>
  );
}

SurfaceExportDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  initialFormat: PropTypes.string,
  defaultFilename: PropTypes.string,
  defaultTitle: PropTypes.string,
  tableName: PropTypes.string,
  rows: PropTypes.array,
  columns: PropTypes.array,
  selectedRows: PropTypes.array,
  selectedColumns: PropTypes.array,
  hasMultiSelection: PropTypes.bool,
  allRowsSelected: PropTypes.bool,
  selectionLabel: PropTypes.string,
  onExportHost: PropTypes.func,
};
