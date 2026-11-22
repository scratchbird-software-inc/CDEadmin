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
import getApiInstance from 'sources/api_instance';
import {Box, Grid, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {TextArea, TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import {SqliteSectionCard, createSqliteWorkspaceCaller} from './sqliteAdminHelpers';

const textVal = (e) => (e?.target ? e.target.value : String(e ?? ''));

/**
 * SQ-AUD-12 (SR-F-030563): Native SQLite Incremental Large-BLOB Transfer (`sqlite3_blob_*`).
 */
export default function SqliteBlobStreamWorkspace({
  endpointUrl,
  databaseTargetId = '',
  api: injectedApi = null,
}) {
  const api = useMemo(() => injectedApi || getApiInstance(), [injectedApi]);
  const callSqlite = useMemo(
    () => createSqliteWorkspaceCaller(api, endpointUrl, databaseTargetId),
    [api, endpointUrl, databaseTargetId]
  );

  const [schemaName, setSchemaName] = useState('main');
  const [tableName, setTableName] = useState('');
  const [columnName, setColumnName] = useState('');
  const [rowid, setRowid] = useState('1');
  const [offset, setOffset] = useState('0');
  const [chunkLength, setChunkLength] = useState('65536');
  const [encoding, setEncoding] = useState('hex');
  const [allocLength, setAllocLength] = useState('1024');
  const [writeData, setWriteData] = useState('');

  const [cellInfo, setCellInfo] = useState(null);
  const [chunkResult, setChunkResult] = useState(null);
  const [reviewedOp, setReviewedOp] = useState(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const targetPayload = () => ({
    schema_name: schemaName.trim() || 'main',
    table_name: tableName.trim(),
    column_name: columnName.trim(),
    rowid: Number(rowid),
  });

  const handleInspect = async () => {
    setBusy(true);
    setError('');
    try {
      const info = await callSqlite({action: 'sqlite_ops_blob_inspect', request: targetPayload()});
      setCellInfo(info);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReadChunk = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callSqlite({
        action: 'sqlite_ops_blob_read_chunk',
        request: {
          ...targetPayload(),
          offset: Number(offset) || 0,
          length: Number(chunkLength) || 65536,
          encoding,
        },
      });
      setChunkResult(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReviewAlloc = async () => {
    setBusy(true);
    setError('');
    try {
      const rev = await callSqlite({
        action: 'sqlite_ops_blob_allocate_review',
        request: {
          ...targetPayload(),
          byte_length: Number(allocLength) || 0,
        },
      });
      setReviewedOp({kind: 'alloc', ...rev});
      setConfirmed(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReviewWrite = async () => {
    setBusy(true);
    setError('');
    try {
      const rev = await callSqlite({
        action: 'sqlite_ops_blob_write_review',
        request: {
          ...targetPayload(),
          offset: Number(offset) || 0,
          encoding,
          data: writeData.trim(),
        },
      });
      setReviewedOp({kind: 'write', ...rev});
      setConfirmed(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleApplyReviewed = async () => {
    if (!reviewedOp || !confirmed) return;
    setBusy(true);
    setError('');
    try {
      const act = reviewedOp.kind === 'alloc' ? 'sqlite_ops_blob_allocate_apply' : 'sqlite_ops_blob_write_apply';
      await callSqlite({
        action: act,
        request: {
          review_id: reviewedOp.review_id,
          review_digest: reviewedOp.review_digest,
          confirmed: true,
        },
      });
      setReviewedOp(null);
      await handleInspect();
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box style={{padding: 16}}>
      <Stack gap="md">
        <Stack direction="row" gap="sm" style={{justifyContent: 'space-between', alignItems: 'center'}}>
          <strong>{gettext('SQLite Incremental Large-BLOB Transfer')}</strong>
          <FormReference reference="SR-F-030563" />
        </Stack>

        <Banner status="info">
          {gettext('Streams BLOB chunks via sqlite3_blob_open using proved 64-bit integer rowids. WITHOUT ROWID tables and SQL NULL cells are refused; allocate zeroblob(N) before writing chunks.')}
        </Banner>

        {error && <ValidationMessage status="error">{error}</ValidationMessage>}

        <SqliteSectionCard title={gettext('Rowid Target & Cell Inspection')}>
          <Grid columns={4} gap="sm">
            <TextField label={gettext('Schema')} value={schemaName} onChange={(e) => setSchemaName(textVal(e))} />
            <TextField label={gettext('Rowid Table')} value={tableName} onChange={(e) => setTableName(textVal(e))} />
            <TextField label={gettext('BLOB Column')} value={columnName} onChange={(e) => setColumnName(textVal(e))} />
            <TextField label={gettext('Integer Rowid')} value={rowid} onChange={(e) => setRowid(textVal(e))} />
          </Grid>
          <Grid columns={3} gap="sm">
            <TextField label={gettext('Byte Offset')} value={offset} onChange={(e) => setOffset(textVal(e))} />
            <TextField label={gettext('Chunk Length (bytes)')} value={chunkLength} onChange={(e) => setChunkLength(textVal(e))} />
            <Select
              label={gettext('Transfer Encoding')}
              value={encoding}
              onChange={(val) => setEncoding(val)}
              options={[
                {value: 'hex', label: 'Hexadecimal'},
                {value: 'base64', label: 'Base64'},
              ]}
            />
          </Grid>
          <Stack direction="row" gap="sm">
            <Button variant="primary" disabled={busy || !tableName.trim() || !columnName.trim()} onClick={handleInspect}>
              {gettext('Inspect Cell')}
            </Button>
            <Button disabled={busy || !tableName.trim() || !columnName.trim()} onClick={handleReadChunk}>
              {gettext('Read BLOB Chunk')}
            </Button>
          </Stack>
          {cellInfo && (
            <Stack direction="row" gap="sm">
              <Badge status="info" label={`${gettext('Storage Class')}: ${cellInfo.typeof}`} />
              <Badge status="info" label={`${gettext('Bytes')}: ${cellInfo.byte_length ?? 'NULL'}`} />
              <Badge
                status={cellInfo.streamable_blob ? 'success' : 'warning'}
                label={cellInfo.streamable_blob ? gettext('Streamable BLOB') : gettext('Allocate Zeroblob First')}
              />
            </Stack>
          )}
          {chunkResult && (
            <Stack gap="sm">
              <div>SHA-256: <code>{chunkResult.chunk_sha256}</code> ({chunkResult.chunk_bytes} / {chunkResult.total_bytes} bytes)</div>
              <TextArea label={gettext('Chunk Payload')} rows={3} value={chunkResult.data} readOnly />
            </Stack>
          )}
        </SqliteSectionCard>

        <SqliteSectionCard title={gettext('Reviewed Zeroblob Allocation & Chunk Write')}>
          <Grid columns={2} gap="sm">
            <TextField
              label={gettext('Allocate / Resize Zeroblob Byte Length')}
              value={allocLength}
              onChange={(e) => setAllocLength(textVal(e))}
            />
            <div style={{display: 'flex', alignItems: 'flex-end'}}>
              <Button disabled={busy || !tableName.trim() || !columnName.trim()} onClick={handleReviewAlloc}>
                {gettext('Review Zeroblob Allocation')}
              </Button>
            </div>
          </Grid>
          <TextArea
            label={gettext('Chunk Payload to Write at Offset')}
            rows={3}
            value={writeData}
            onChange={(e) => setWriteData(textVal(e))}
          />
          <Stack direction="row" gap="sm">
            <Button disabled={busy || !tableName.trim() || !columnName.trim()} onClick={handleReviewWrite}>
              {gettext('Review Chunk Write')}
            </Button>
          </Stack>

          {reviewedOp && (
            <Stack gap="sm">
              <Checkbox
                label={gettext('Confirm reviewed BLOB modification')}
                checked={confirmed}
                onChange={setConfirmed}
              />
              <Button variant="primary" disabled={busy || !confirmed} onClick={handleApplyReviewed}>
                {gettext('Apply Reviewed BLOB Operation')}
              </Button>
            </Stack>
          )}
        </SqliteSectionCard>
      </Stack>
    </Box>
  );
}

SqliteBlobStreamWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  databaseTargetId: PropTypes.string,
  api: PropTypes.object,
};
