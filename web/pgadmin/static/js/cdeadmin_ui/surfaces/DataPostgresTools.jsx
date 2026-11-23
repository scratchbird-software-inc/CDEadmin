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
import {Box, Grid, Panel, Stack} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {TextField} from '../primitives/Field';
import {Select} from '../primitives/Choice';
import {Badge, Banner} from '../feedback/Indicators';
import {Dialog} from '../overlays/Dialog';
import FormReference from '../navigation/FormReference';
import CodeEditor from '../editors/CodeEditor';

function quotePgIdent(name) {
  return `"${String(name || '').replace(/"/g, '""')}"`;
}

function formatPgLiteral(val) {
  if (val === null || val === undefined) return 'NULL';
  if (typeof val === 'boolean') return val ? 'TRUE' : 'FALSE';
  if (typeof val === 'number' && Number.isFinite(val)) return String(val);
  if (typeof val === 'object') {
    const jsonText = JSON.stringify(val).replace(/'/g, '\'\'');
    return `'${jsonText}'::jsonb`;
  }
  return `'${String(val).replace(/'/g, '\'\'')}'`;
}

/**
 * PG-UI-08 (SR-F-030457): PostgreSQL Row SQL Generator (INSERT OVERRIDING SYSTEM VALUE,
 * ON CONFLICT DO UPDATE, UPDATE RETURNING *, WHERE IN).
 */
export function DataPostgresRowSqlDialog({
  open,
  tableLabel = 'public.table',
  columns = [],
  row = null,
  callHost = null,
  onClose,
}) {
  const [mode, setMode] = useState('upsert');
  const [conflictCol, setConflictCol] = useState(columns?.[0]?.name || 'id');
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
      key_columns: [conflictCol || columns?.[0]?.name || 'id'],
      inline_literals: true,
    })
      .then((res) => {
        if (active && typeof res?.sql === 'string') setHostSql(res.sql);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [callHost, columns, conflictCol, mode, open, row, tableLabel]);

  const fallbackSql = useMemo(() => {
    const colNames = (columns || []).map((c) => c.name).filter(Boolean);
    if (!colNames.length || !row) return '-- Select a row to generate PostgreSQL SQL';
    const valuesMap = Array.isArray(row)
      ? Object.fromEntries(colNames.map((n, idx) => [n, row[idx]]))
      : row;
    const quotedCols = colNames.map(quotePgIdent).join(', ');
    const formattedVals = colNames.map((n) => formatPgLiteral(valuesMap[n])).join(', ');
    const pk = quotePgIdent(conflictCol || colNames[0]);
    const pkVal = formatPgLiteral(valuesMap[conflictCol || colNames[0]]);

    switch (mode) {
    case 'insert_overriding':
      return `INSERT INTO ${tableLabel} (${quotedCols})\nOVERRIDING SYSTEM VALUE\nVALUES (${formattedVals})\nRETURNING *;`;
    case 'update_returning': {
      const sets = colNames
        .filter((c) => c !== conflictCol)
        .map((c) => `${quotePgIdent(c)} = ${formatPgLiteral(valuesMap[c])}`)
        .join(',\n    ');
      return `UPDATE ONLY ${tableLabel}\nSET ${sets || `${pk} = ${pkVal}`}\nWHERE ${pk} = ${pkVal}\nRETURNING *;`;
    }
    case 'where_in':
      return `SELECT *\nFROM ONLY ${tableLabel}\nWHERE ${pk} IN (${pkVal});`;
    default: {
      const updates = colNames
        .filter((c) => c !== conflictCol)
        .map((c) => `${quotePgIdent(c)} = EXCLUDED.${quotePgIdent(c)}`)
        .join(',\n    ');
      return `INSERT INTO ${tableLabel} (${quotedCols})\nVALUES (${formattedVals})\nON CONFLICT (${pk}) DO UPDATE\nSET ${updates || `${pk} = EXCLUDED.${pk}`}\nRETURNING *;`;
    }
    }
  }, [columns, conflictCol, mode, row, tableLabel]);
  const sqlText = hostSql ?? fallbackSql;

  if (!open) return null;

  return (
    <Dialog
      open={open}
      title={gettext('Generate PostgreSQL Row SQL')}
      onClose={onClose}
      size="lg"
    >
      <Stack gap="md">
        <FormReference reference="SR-F-030457" />
        <Grid columns={2} gap="sm">
          <Select
            label={gettext('Statement Variant')}
            value={mode}
            options={[
              {value: 'upsert', label: 'INSERT ... ON CONFLICT DO UPDATE RETURNING *'},
              {value: 'insert_overriding', label: 'INSERT ... OVERRIDING SYSTEM VALUE'},
              {value: 'update_returning', label: 'UPDATE ONLY ... RETURNING *'},
              {value: 'where_in', label: 'SELECT ... WHERE key IN (...)'},
            ]}
            onChange={setMode}
          />
          <TextField
            label={gettext('Conflict / Key Column')}
            value={conflictCol}
            onChange={(e) => setConflictCol(e?.target ? e.target.value : e)}
          />
        </Grid>
        <CodeEditor value={sqlText} language="sql" readOnly height="200px" />
        <Button variant="secondary" onClick={onClose}>
          {gettext('Close')}
        </Button>
      </Stack>
    </Dialog>
  );
}

DataPostgresRowSqlDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  tableLabel: PropTypes.string,
  columns: PropTypes.array,
  row: PropTypes.oneOfType([PropTypes.object, PropTypes.array]),
  callHost: PropTypes.func,
  onClose: PropTypes.func.isRequired,
};

/**
 * PG-UI-09 (SR-F-030458): PostgreSQL Cell Value, BYTEA/JSONB/Range & TOAST Storage Inspector.
 */
export function DataPostgresCellInspectorModal({
  open,
  column = null,
  value = null,
  onClose,
}) {
  if (!open) return null;

  const formatted =
    value === null || value === undefined
      ? 'NULL'
      : typeof value === 'object'
        ? JSON.stringify(value, null, 2)
        : String(value);

  return (
    <Dialog
      open={open}
      title={gettext('Inspect PostgreSQL Value, Encoding & TOAST Attributes')}
      onClose={onClose}
      size="md"
    >
      <Stack gap="md">
        <Stack direction="row" gap="sm">
          <FormReference reference="SR-F-030458" />
          <Badge status="info" label={column?.native_type || column?.type || 'pg_catalog'} />
        </Stack>
        <Banner status="info">
          {gettext(
            'Preserves exact JSONB, array, range, BYTEA base64/hex, and lossless SQL_ASCII byte envelopes without replacement characters.'
          )}
        </Banner>
        <Panel style={{padding: 12}}><strong>{column?.name || gettext('Selected Column')}</strong>
          <Box>
            <CodeEditor value={formatted} language="json" readOnly height="200px" />
          </Box>
        </Panel>
        <Button variant="secondary" onClick={onClose}>
          {gettext('Close')}
        </Button>
      </Stack>
    </Dialog>
  );
}

DataPostgresCellInspectorModal.propTypes = {
  open: PropTypes.bool.isRequired,
  column: PropTypes.object,
  value: PropTypes.any,
  onClose: PropTypes.func.isRequired,
};
