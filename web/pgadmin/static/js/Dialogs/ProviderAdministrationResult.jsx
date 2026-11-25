/////////////////////////////////////////////////////////////
// CDEadmin - Multi-engine Database Administration
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//////////////////////////////////////////////////////////////

import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Alert, Box} from '@mui/material';
import FirebirdServiceObservation from './FirebirdServiceObservation';
import FirebirdLimboObservation from './FirebirdLimboObservation';
import {PostgresqlBinaryResult} from './PostgresqlBinaryChunk';

function formatScalarValue(val) {
  if (val === null || val === undefined) return '—';
  if (typeof val === 'boolean') return val ? gettext('Yes') : gettext('No');
  if (typeof val === 'object') return JSON.stringify(val);
  return String(val);
}

function humanizeKey(key) {
  const spaced = String(key || '').replaceAll('_', ' ').trim();
  return spaced ? spaced.charAt(0).toUpperCase() + spaced.slice(1) : '';
}

function StructuredOperationSummary({payload, binaryCount}) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return (
      <Box sx={{mt: 1, p: 1.5, border: 1, borderColor: 'divider', borderRadius: 1, bgcolor: 'background.paper'}}>
        {formatScalarValue(payload)}
      </Box>
    );
  }

  const inner = payload.result && typeof payload.result === 'object' && !Array.isArray(payload.result)
    ? payload.result
    : null;

  const summaryEntries = [];
  const seenKeys = new Set(['result', 'rows', 'columns', 'statements', 'statement_results']);

  const pickScalar = (key, label) => {
    const val = payload[key] !== undefined ? payload[key] : inner?.[key];
    if (val !== undefined && val !== null && typeof val !== 'object') {
      summaryEntries.push([key, label, formatScalarValue(val)]);
      seenKeys.add(key);
    }
  };

  pickScalar('status', gettext('Status'));
  pickScalar('state', gettext('State'));
  pickScalar('message', gettext('Message'));
  pickScalar('error', gettext('Error'));
  pickScalar('affected_rows', gettext('Affected rows'));
  pickScalar('rowcount', gettext('Affected rows'));

  if (payload.resource_identity_change?.resource_id) {
    summaryEntries.push([
      'resource_identity_change',
      gettext('Updated resource'),
      String(payload.resource_identity_change.resource_id),
    ]);
    seenKeys.add('resource_identity_change');
  }

  Object.entries(payload).forEach(([key, val]) => {
    if (seenKeys.has(key)) return;
    if (val !== null && val !== undefined && typeof val !== 'object') {
      summaryEntries.push([key, gettext(humanizeKey(key)), formatScalarValue(val)]);
    }
  });

  const rawStatements = Array.isArray(payload.statements)
    ? payload.statements
    : Array.isArray(inner?.statements)
      ? inner.statements
      : Array.isArray(payload.statement_results)
        ? payload.statement_results
        : [];
  const statementTexts = rawStatements
    .map((item) => {
      if (typeof item === 'string') return item;
      if (item && typeof item === 'object') {
        return item.sql || item.statement || item.source || JSON.stringify(item);
      }
      return '';
    })
    .filter(Boolean);

  const candidateRows = Array.isArray(inner?.rows)
    ? inner.rows
    : Array.isArray(payload.rows)
      ? payload.rows
      : [];
  const tableRows = binaryCount
    ? candidateRows.filter(
      (row) => !(typeof row?.data_base64 === 'string' && row.sha256 && row.oid !== undefined && row.offset !== undefined)
    )
    : candidateRows;

  const rawColumns = Array.isArray(inner?.columns)
    ? inner.columns
    : Array.isArray(payload.columns)
      ? payload.columns
      : null;

  const columnNames = [];
  if (rawColumns?.length) {
    rawColumns.forEach((col) => {
      const colName = typeof col === 'string' ? col : col?.name || col?.key;
      if (colName && !columnNames.includes(colName)) columnNames.push(colName);
    });
  }
  tableRows.forEach((row) => {
    if (row && typeof row === 'object' && !Array.isArray(row)) {
      Object.keys(row).forEach((k) => {
        if (!columnNames.includes(k)) columnNames.push(k);
      });
    }
  });

  return (
    <Box
      sx={{
        mt: 1.5,
        p: 1.5,
        border: 1,
        borderColor: 'divider',
        borderRadius: 1,
        bgcolor: 'background.paper',
        display: 'flex',
        flexDirection: 'column',
        gap: 1.25,
      }}
    >
      {summaryEntries.length > 0 && (
        <Box
          component="dl"
          sx={{
            m: 0,
            display: 'grid',
            gridTemplateColumns: 'minmax(140px, max-content) minmax(0, 1fr)',
            columnGap: 2,
            rowGap: 0.5,
            fontSize: '0.8125rem',
          }}
        >
          {summaryEntries.map(([key, label, text]) => (
            <Box key={key} sx={{display: 'contents'}}>
              <Box component="dt" sx={{fontWeight: 600, color: 'text.secondary'}}>
                {label}
              </Box>
              <Box component="dd" sx={{m: 0, overflowWrap: 'anywhere'}}>
                {text}
              </Box>
            </Box>
          ))}
        </Box>
      )}

      {statementTexts.length > 0 && (
        <Box>
          <Box sx={{fontSize: '0.75rem', fontWeight: 600, color: 'text.secondary', mb: 0.5}}>
            {gettext('Statements')}
          </Box>
          <Box
            component="pre"
            sx={{
              m: 0,
              p: 1,
              borderRadius: 0.5,
              border: 1,
              borderColor: 'divider',
              bgcolor: 'background.default',
              fontFamily: 'monospace',
              fontSize: '0.8125rem',
              whiteSpace: 'pre-wrap',
              overflow: 'auto',
              maxHeight: 180,
            }}
          >
            {statementTexts.join('\n')}
          </Box>
        </Box>
      )}

      {tableRows.length > 0 && columnNames.length > 0 && (
        <Box sx={{overflowX: 'auto', maxHeight: 240}}>
          <Box
            component="table"
            sx={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: '0.8125rem',
              '& th, & td': {
                p: 0.75,
                textAlign: 'left',
                borderBottom: 1,
                borderColor: 'divider',
                verticalAlign: 'top',
              },
              '& th': {
                fontWeight: 600,
                color: 'text.secondary',
                bgcolor: 'background.default',
              },
            }}
          >
            <thead>
              <tr>
                {columnNames.map((col) => (
                  <th key={col}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tableRows.map((row, idx) => (
                <tr key={idx}>
                  {columnNames.map((col) => (
                    <td key={col}>{formatScalarValue(row?.[col])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </Box>
        </Box>
      )}

      <Box component="details">
        <Box
          component="summary"
          sx={{cursor: 'pointer', fontSize: '0.75rem', color: 'text.secondary', userSelect: 'none'}}
        >
          {gettext('Raw response payload')}
        </Box>
        <Box
          component="pre"
          aria-label={gettext('Provider operation result')}
          sx={{
            mt: 1,
            mb: 0,
            p: 1,
            overflow: 'auto',
            maxHeight: 280,
            bgcolor: 'background.default',
            fontSize: '0.75rem',
          }}
        >
          {JSON.stringify(
            payload,
            (key, value) => (binaryCount && key === 'data_base64' ? gettext('Available as binary download') : value),
            2
          )}
        </Box>
      </Box>
    </Box>
  );
}

StructuredOperationSummary.propTypes = {
  payload: PropTypes.any,
  binaryCount: PropTypes.number,
};

export default function ProviderAdministrationResult({result, title, target}) {
  if (!result) return null;
  const observation = result.provider_result?.driver_observation;
  const binary =
    result.provider_result?.result?.rows?.filter(
      (row) =>
        typeof row.data_base64 === 'string' &&
        row.sha256 &&
        row.oid !== undefined &&
        row.offset !== undefined
    ) || [];
  const payload = result.provider_result ?? result;

  return (
    <>
      {target?.resource_id && (
        <Box
          component="p"
          sx={{mt: 2, overflowWrap: 'anywhere'}}
          aria-label={gettext('Provider response target')}
        >
          {title} — {target.display_name || target.resource_kind} [{target.resource_id}]
        </Box>
      )}
      {observation?.service_release?.service_handle_released === false && (
        <Alert
          severity="warning"
          sx={{mt: 2}}
          aria-label={gettext('Firebird service cleanup required')}
        >
          {gettext(
            'Firebird service handle release is unconfirmed. Do not replay the operation. Review its returned outcome separately from cleanup, then explicitly close the provider connection to retry handle release.'
          )}
        </Alert>
      )}
      {(result.workspace_follow_up || [])
        .filter((item) => item.state === 'failed' && typeof item.message === 'string')
        .map((item, index) => (
          <Alert
            key={`${item.action}-${index}`}
            severity="warning"
            sx={{mt: 2}}
            aria-label={gettext('Connection registration follow-up required')}
          >
            {item.message}
          </Alert>
        ))}
      <Alert severity="info" sx={{mt: 2}}>
        {gettext(
          'The provider response was recorded. Finality remains provider-owned; review the returned state and any required post-state validation.'
        )}
      </Alert>
      {binary.map((row, index) => (
        <PostgresqlBinaryResult key={`${row.oid}:${row.offset}:${index}`} row={row} />
      ))}
      {observation?.schema === 'cdeadmin.firebird-limbo-result.v1' ? (
        <FirebirdLimboObservation observation={observation} />
      ) : observation?.schema === 'cdeadmin.firebird-service-result.v1' ? (
        <FirebirdServiceObservation title={title} observation={observation} />
      ) : (
        <StructuredOperationSummary payload={payload} binaryCount={binary.length} />
      )}
    </>
  );
}

ProviderAdministrationResult.propTypes = {
  result: PropTypes.object,
  title: PropTypes.string,
  target: PropTypes.object,
};
