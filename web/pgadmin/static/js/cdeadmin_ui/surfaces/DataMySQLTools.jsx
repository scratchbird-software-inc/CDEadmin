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
import {NumberField, TextArea} from '../primitives/Field';
import {Checkbox, Select} from '../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../feedback/Indicators';
import {Dialog} from '../overlays/Dialog';
import CodeEditor from '../editors/CodeEditor';
import {DDNViewerSurface} from '../integrations/ddn';
import {mysqlSpatialFiles} from '../integrations/ddn/mysqlSpatial';

const SPATIAL_TYPE_RE = /\b(GEOMETRY|POINT|LINESTRING|POLYGON|MULTIPOINT|MULTILINESTRING|MULTIPOLYGON|GEOMETRYCOLLECTION)\b/i;

export function isMySQLSpatialType(typeName) {
  return SPATIAL_TYPE_RE.test(String(typeName || ''));
}

function parseSimpleWktOrGeoJson(rawText) {
  const trimmed = String(rawText || '').trim();
  if (!trimmed) return {geometry: null, srid: 0, error: ''};

  let srid = 0;
  let body = trimmed;
  const sridMatch = /^SRID\s*=\s*(\d+)\s*;\s*([\s\S]+)$/i.exec(trimmed);
  if (sridMatch) {
    srid = Number(sridMatch[1]) || 0;
    body = sridMatch[2].trim();
  }

  if (body.startsWith('{')) {
    try {
      const parsed = JSON.parse(body);
      if (parsed && typeof parsed.type === 'string' && Array.isArray(parsed.coordinates)) {
        return {geometry: parsed, srid, error: ''};
      }
      return {geometry: null, srid, error: gettext('GeoJSON must provide type and coordinates[].')};
    } catch (err) {
      return {geometry: null, srid, error: err?.message || gettext('Invalid GeoJSON syntax.')};
    }
  }

  const parsePair = (pairStr) => {
    const parts = pairStr.trim().split(/\s+/).map(Number);
    if (parts.length < 2 || parts.some((n) => !Number.isFinite(n))) {
      throw new Error(gettext('Invalid WKT coordinate pair: %s', pairStr));
    }
    return [parts[0], parts[1]];
  };

  try {
    const pt = /^POINT\s*\(\s*([^()]+)\s*\)$/i.exec(body);
    if (pt) {
      return {geometry: {type: 'Point', coordinates: parsePair(pt[1])}, srid, error: ''};
    }
    const ls = /^LINESTRING\s*\(\s*([^()]+)\s*\)$/i.exec(body);
    if (ls) {
      return {
        geometry: {type: 'LineString', coordinates: ls[1].split(',').map(parsePair)},
        srid,
        error: '',
      };
    }
    const poly = /^POLYGON\s*\(\s*\(([\s\S]+)\)\s*\)$/i.exec(body);
    if (poly) {
      const rings = poly[1]
        .split(/\)\s*,\s*\(/)
        .map((ring) => ring.replace(/[()]/g, '').split(',').map(parsePair));
      return {geometry: {type: 'Polygon', coordinates: rings}, srid, error: ''};
    }
    return {geometry: null, srid, error: ''};
  } catch (err) {
    return {geometry: null, srid, error: err?.message || String(err)};
  }
}

/**
 * MYSQL-UI-07 (SR-F-030202): Dedicated MySQL Spatial WKT / EWKT / GeoJSON / SRID
 * Cell Viewer & Editor with DDN `geo.outline@1` Preview.
 */
export function DataMySQLSpatialDialog({
  open,
  column,
  rawValue,
  readOnly = false,
  onApplyValue,
  onClose,
}) {
  const [isNull, setIsNull] = useState(rawValue === null || rawValue === undefined);
  const [text, setText] = useState('');
  const [srid, setSrid] = useState(0);

  useEffect(() => {
    if (!open) return;
    const initialNull = rawValue === null || rawValue === undefined;
    setIsNull(initialNull);
    const strVal = initialNull ? '' : typeof rawValue === 'object' ? JSON.stringify(rawValue) : String(rawValue);
    const parsed = parseSimpleWktOrGeoJson(strVal);
    setSrid(parsed.srid || Number(column?.srid) || 0);
    setText(strVal.replace(/^SRID\s*=\s*\d+\s*;\s*/i, ''));
  }, [column, open, rawValue]);

  const parsedPreview = useMemo(
    () => (isNull ? {geometry: null, srid: 0, error: ''} : parseSimpleWktOrGeoJson(text)),
    [isNull, text]
  );

  const ddnSnapshot = useMemo(() => {
    if (!parsedPreview.geometry) return null;
    const files = mysqlSpatialFiles({
      map_mode: srid === 4326 ? 'wgs84' : 'cartesian',
      rows: [{id: column?.name || 'geometry', map_geometry: parsedPreview.geometry}],
    });
    if (!files) return null;
    return {entry: 'spatial.ddn', view: 'spatial', files};
  }, [column?.name, parsedPreview.geometry, srid]);

  if (!open || !column) return null;

  const handleStage = () => {
    if (isNull) {
      onApplyValue(null);
      onClose();
      return;
    }
    const clean = text.trim();
    const staged = srid > 0 && !/^SRID\s*=/i.test(clean) && !clean.startsWith('{') ? `SRID=${srid};${clean}` : clean;
    onApplyValue(staged);
    onClose();
  };

  return (
    <Dialog
      open={open}
      title={gettext('%s — MySQL Spatial WKT / GeoJSON Inspector', column.name)}
      formReference="SR-F-030202"
      size="large"
      onClose={onClose}
      actions={
        <>
          <Button intent="neutral" onClick={onClose}>
            {gettext('Cancel')}
          </Button>
          {!readOnly && (
            <Button intent="primary" disabled={!isNull && Boolean(parsedPreview.error)} onClick={handleStage}>
              {gettext('Stage Spatial Value')}
            </Button>
          )}
        </>
      }
    >
      <Stack gap="standard" data-cdeadmin-qa-key="data-surface.mysql-spatial-dialog">
        <Banner status="info">
          {gettext(
            'Inspect or edit MySQL spatial values as WKT (e.g. POINT(10 20), POLYGON((...))) or GeoJSON, with explicit SRID (e.g. 0 Cartesian or 4326 WGS 84).'
          )}
        </Banner>

        {parsedPreview.error && <ValidationMessage status="error">{parsedPreview.error}</ValidationMessage>}

        <Grid columns="repeat(auto-fit, minmax(200px, 1fr))">
          <Checkbox
            label={gettext('SQL NULL geometry')}
            disabled={readOnly || column.nullable === false}
            checked={isNull}
            onChange={setIsNull}
          />
          <NumberField
            label={gettext('Spatial Reference ID (SRID)')}
            size="small"
            min={0}
            max={4294967295}
            disabled={readOnly || isNull}
            value={srid}
            onChange={(v) => setSrid(v ?? 0)}
          />
        </Grid>

        {!isNull && (
          <TextArea
            label={gettext('WKT or GeoJSON geometry')}
            rows={5}
            readOnly={readOnly}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        )}

        {ddnSnapshot && (
          <Panel variant="outlined" style={{padding: 8}}>
            <Stack gap="compact">
              <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between'}}>
                <strong>{gettext('DDN Geometry Outline Preview')}</strong>
                <Badge label={srid === 4326 ? 'WGS 84 (SRID 4326)' : `Cartesian (SRID ${srid})`} status="info" />
              </Stack>
              <Box style={{height: 220, overflow: 'auto'}}>
                <DDNViewerSurface snapshot={ddnSnapshot} presentation />
              </Box>
            </Stack>
          </Panel>
        )}
      </Stack>
    </Dialog>
  );
}

DataMySQLSpatialDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  column: PropTypes.object,
  rawValue: PropTypes.any,
  readOnly: PropTypes.bool,
  onApplyValue: PropTypes.func.isRequired,
  onClose: PropTypes.func.isRequired,
};

function backtickIdent(name) {
  return '`' + String(name || '').replaceAll('`', '``') + '`';
}

function formatMySQLScalarLiteral(val) {
  if (val === null || val === undefined) return 'NULL';
  if (typeof val === 'boolean') return val ? 'TRUE' : 'FALSE';
  if (typeof val === 'number' && Number.isFinite(val)) return String(val);
  const str = typeof val === 'object' ? JSON.stringify(val) : String(val);
  return "'" + str.replaceAll('\\', '\\\\').replaceAll("'", "''") + "'";
}

/**
 * MYSQL-UI-07 (SR-F-030203): Selected-Row Native MySQL SQL Generator Dialog
 * (`INSERT`, `INSERT ... ON DUPLICATE KEY UPDATE`, `UPDATE`, `IN`).
 */
export function DataMySQLRowSqlDialog({
  open,
  tableName,
  columns = [],
  fetchedRows = [],
  initialSelectedIndices = [],
  onOpenInSqlEditor,
  onClose,
}) {
  const cleanRows = useMemo(
    () =>
      fetchedRows
        .filter((r) => !r?.isDraftInsert && r?.stage_state !== 'inserted')
        .map((r) => (r && typeof r.values === 'object' && r.values !== null ? r.values : r || {})),
    [fetchedRows]
  );

  const [selectedIndices, setSelectedIndices] = useState([]);
  const [operation, setOperation] = useState('insert');
  const [inlineLiterals, setInlineLiterals] = useState(false);
  const [keyColumns, setKeyColumns] = useState([]);
  const [inColumn, setInColumn] = useState('');
  const [generated, setGenerated] = useState(null);
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
    setKeyColumns(
      columns.filter((c) => c.key === true || c.primary_key === true || c.identity_key).map((c) => c.name)
    );
    setInColumn(columns[0]?.name || '');
    setGenerated(null);
    setError('');
  }, [cleanRows.length, columns, initialSelectedIndices, open]);

  if (!open) return null;

  const handleGenerate = () => {
    setError('');
    try {
      const chosen = cleanRows.filter((_r, idx) => selectedIndices.includes(idx));
      if (!chosen.length) throw new Error(gettext('Select at least one fetched row.'));
      const tbl = backtickIdent(tableName);
      const statements = [];
      const paramsList = [];

      const bindVal = (val, rowParams) => {
        if (inlineLiterals) return formatMySQLScalarLiteral(val);
        rowParams.push(val ?? null);
        return '%s';
      };

      if (operation === 'in') {
        if (!inColumn) throw new Error(gettext('Select a column for IN-list generation.'));
        const rowParams = [];
        const colSql = backtickIdent(inColumn);
        const nonNull = chosen.map((r) => r[inColumn]).filter((v) => v !== null && v !== undefined);
        const clauses = [];
        if (nonNull.length) {
          clauses.push(`${colSql} IN (${nonNull.map((v) => bindVal(v, rowParams)).join(', ')})`);
        }
        if (chosen.some((r) => r[inColumn] === null || r[inColumn] === undefined)) {
          clauses.push(`${colSql} IS NULL`);
        }
        statements.push(`SELECT * FROM ${tbl} WHERE ${clauses.join(' OR ')};`);
        paramsList.push(rowParams);
      } else if (operation === 'update') {
        if (!keyColumns.length) throw new Error(gettext('Select at least one matching key column for UPDATE.'));
        const setCols = columns.filter((c) => c.editable !== false && !keyColumns.includes(c.name));
        if (!setCols.length) throw new Error(gettext('No non-key editable columns available for UPDATE.'));
        for (const row of chosen) {
          const rowParams = [];
          const sets = setCols.map((c) => `${backtickIdent(c.name)} = ${bindVal(row[c.name], rowParams)}`);
          const wheres = keyColumns.map((k) => `${backtickIdent(k)} <=> ${bindVal(row[k], rowParams)}`);
          statements.push(`UPDATE ${tbl} SET ${sets.join(', ')} WHERE ${wheres.join(' AND ')};`);
          paramsList.push(rowParams);
        }
      } else {
        const writeCols = columns.filter((c) => c.insertable !== false);
        if (!writeCols.length) throw new Error(gettext('No insertable columns available.'));
        for (const row of chosen) {
          const rowParams = [];
          const colList = writeCols.map((c) => backtickIdent(c.name)).join(', ');
          const valList = writeCols.map((c) => bindVal(row[c.name], rowParams)).join(', ');
          let sql = `INSERT INTO ${tbl} (${colList}) VALUES (${valList})`;
          if (operation === 'upsert') {
            const updCols = writeCols.filter((c) => !keyColumns.includes(c.name));
            const targets = updCols.length ? updCols : writeCols;
            const updates = targets.map((c) => `${backtickIdent(c.name)} = VALUES(${backtickIdent(c.name)})`);
            sql += ` ON DUPLICATE KEY UPDATE ${updates.join(', ')}`;
          }
          statements.push(`${sql};`);
          paramsList.push(rowParams);
        }
      }

      setGenerated({
        sql: statements.join('\n'),
        parameters: paramsList.length === 1 ? paramsList[0] : paramsList.flat(),
      });
    } catch (err) {
      setError(err?.message || String(err));
      setGenerated(null);
    }
  };

  return (
    <Dialog
      open={open}
      title={gettext('Generate Native MySQL Row SQL — %s', tableName)}
      formReference="SR-F-030203"
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
      <Stack gap="standard" data-cdeadmin-qa-key="data-surface.mysql-row-sql-dialog">
        <Banner status="info">
          {gettext(
            'Generates native MySQL INSERT, INSERT ... ON DUPLICATE KEY UPDATE, null-safe UPDATE (<=>), or IN predicates with %s positional parameters or inline SQL literals.'
          )}
        </Banner>
        {error && <ValidationMessage status="error">{error}</ValidationMessage>}

        <Grid columns="repeat(auto-fit, minmax(220px, 1fr))">
          <Select
            label={gettext('MySQL statement kind')}
            size="small"
            options={[
              {value: 'insert', label: 'INSERT INTO'},
              {value: 'upsert', label: 'INSERT ... ON DUPLICATE KEY UPDATE'},
              {value: 'update', label: 'UPDATE ... WHERE (<=>)'},
              {value: 'in', label: 'SELECT ... WHERE col IN (...)'},
            ]}
            value={operation}
            onChange={(v) => {
              setOperation(v);
              setGenerated(null);
            }}
          />
          {operation === 'in' && (
            <Select
              label={gettext('IN-list column')}
              size="small"
              options={columns.map((c) => ({value: c.name, label: c.name}))}
              value={inColumn}
              onChange={setInColumn}
            />
          )}
          <Checkbox
            label={gettext('Inline SQL scalar literals (instead of %s parameters)')}
            checked={inlineLiterals}
            onChange={(v) => {
              setInlineLiterals(v);
              setGenerated(null);
            }}
          />
        </Grid>

        {(operation === 'update' || operation === 'upsert') && (
          <Panel variant="outlined" style={{padding: 8}}>
            <Stack gap="compact">
              <strong style={{fontSize: '0.78rem'}}>{gettext('Matching Key Columns')}</strong>
              <Box style={{display: 'flex', flexWrap: 'wrap', gap: 8}}>
                {columns.map((c) => (
                  <Checkbox
                    key={c.name}
                    label={c.name}
                    checked={keyColumns.includes(c.name)}
                    onChange={(chk) =>
                      setKeyColumns((cur) => (chk ? [...cur, c.name] : cur.filter((x) => x !== c.name)))
                    }
                  />
                ))}
              </Box>
            </Stack>
          </Panel>
        )}

        {generated && (
          <Stack gap="standard">
            <CodeEditor label={gettext('Generated MySQL SQL')} readonly language="sql" value={generated.sql} />
            {!inlineLiterals && (
              <CodeEditor
                label={gettext('Ordered %s positional parameters')}
                readonly
                language="json"
                value={JSON.stringify(generated.parameters, null, 2)}
              />
            )}
            {onOpenInSqlEditor && (
              <Stack direction="row" gap="standard" style={{justifyContent: 'flex-end'}}>
                <Button
                  size="small"
                  intent="primary"
                  onClick={() => {
                    onOpenInSqlEditor({
                      source: generated.sql,
                      initial_sql: generated.sql,
                      parameters: generated.parameters,
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

DataMySQLRowSqlDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  tableName: PropTypes.string.isRequired,
  columns: PropTypes.array,
  fetchedRows: PropTypes.array,
  initialSelectedIndices: PropTypes.array,
  onOpenInSqlEditor: PropTypes.func,
  onClose: PropTypes.func.isRequired,
};
