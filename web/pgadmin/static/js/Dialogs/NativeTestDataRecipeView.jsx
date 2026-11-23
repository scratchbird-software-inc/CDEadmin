/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useId, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Box, Stack} from '../cdeadmin_ui/primitives/Layout';
import {Button} from '../cdeadmin_ui/primitives/Button';
import {NumberField, TextField} from '../cdeadmin_ui/primitives/Field';
import {Select} from '../cdeadmin_ui/primitives/Choice';
import {Banner} from '../cdeadmin_ui/feedback/Indicators';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import RecipeRevisions from '../cdeadmin_ui/editors/RecipeRevisions';
import UnifiedDataGrid from '../cdeadmin_ui/data/UnifiedDataGrid';
import RecordGrid from '../cdeadmin_ui/objects/RecordGrid';
import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';

const ENGINE_LABELS = Object.freeze({
  postgresql: 'PostgreSQL',
  duckdb: 'DuckDB',
  sqlite: 'SQLite',
  mysql: 'MySQL',
  mariadb: 'MariaDB',
});

const initialRecipe = (engine) =>
  JSON.stringify(
    {format: `scratchrobin.${engine}.test-data@1`, scope: null, seed: 1, tables: []},
    null,
    2
  );

const saveBlob = (source, filename, type) => {
  const url = URL.createObjectURL(new Blob([source], {type}));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

export default function NativeTestDataRecipeView({
  post,
  databaseTargetId,
  engine = 'postgresql',
  notesText,
}) {
  const label = ENGINE_LABELS[engine] || engine;
  const useMysqlInlineRevisions = engine === 'mysql' || engine === 'mariadb';
  const formId = useId();
  const [tables, setTables] = useState([]);
  const [selected, setSelected] = useState('');
  const [count, setCount] = useState(10);
  const [source, setSource] = useState(() => initialRecipe(engine));
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [recipeId, setRecipeId] = useState('default');
  const [recipeVersion, setRecipeVersion] = useState(0);
  const [revision, setRevision] = useState('');

  const selectedTable = tables.find((table) => table.resource_id === selected);
  const columns = selectedTable?.columns || [];

  const serial = useRef(0);
  const scope = useRef(null);

  useEffect(() => {
    serial.current++;
    scope.current = null;
    setTables([]);
    setSelected('');
    setSource(initialRecipe(engine));
    setResult(null);
    setError('');
    setBusy(false);
    setRecipeId('default');
    setRecipeVersion(0);
    setRevision('');
    return () => {
      serial.current++;
    };
  }, [post, databaseTargetId, engine]);

  const change = (value) => {
    setSource(value);
    setResult(null);
  };

  const run = async (generate) => {
    const token = ++serial.current;
    setBusy(true);
    setError('');
    setResult(null);
    try {
      const response = await post({
        action: `${engine}_test_data`,
        request: {
          database_target_id: databaseTargetId,
          ...(generate ? {recipe: JSON.parse(source)} : {}),
        },
      });
      if (token !== serial.current) return;
      if (generate) {
        setResult(response);
      } else {
        scope.current = response.scope;
        setTables(response.tables || []);
        setSelected(response.tables?.[0]?.resource_id || '');
      }
    } catch (failure) {
      if (token === serial.current) {
        setError(
          failure?.response?.data?.errormsg || failure?.message || 'Recipe generation failed'
        );
      }
    } finally {
      if (token === serial.current) setBusy(false);
    }
  };

  const add = () => {
    try {
      const recipe = JSON.parse(source);
      const table = tables.find((item) => item.resource_id === selected);
      if (!table || !Number.isInteger(Number(count)) || Number(count) < 1 || Number(count) > 1000) {
        throw new Error('Select a table and 1–1000 rows.');
      }
      if (recipe.scope === null && recipe.tables.length === 0) recipe.scope = scope.current;
      if (
        recipe.scope?.endpoint_id !== scope.current?.endpoint_id ||
        recipe.scope?.database_target_id !== scope.current?.database_target_id
      ) {
        throw new Error('Recipe belongs to another endpoint or database.');
      }
      if (recipe.tables.some((item) => item.table === selected)) {
        throw new Error('Table already appears in the recipe.');
      }
      recipe.tables.push({
        table: selected,
        count: Number(count),
        columns: Object.fromEntries(
          (table.columns || []).map((column) => [column.name, {kind: 'default'}])
        ),
      });
      change(JSON.stringify(recipe, null, 2));
      setError('');
    } catch (failure) {
      setError(failure.message);
    }
  };

  const loadFile = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    const token = serial.current;
    try {
      if (file.size > 4 * 1024 * 1024) throw new Error('Recipe exceeds 4 MiB.');
      const text = await file.text();
      JSON.parse(text);
      if (token === serial.current) {
        change(text);
        setError('');
      }
    } catch (failure) {
      if (token === serial.current) setError(failure.message);
    }
  };

  const persistMysqlRecipe = async (write) => {
    const token = ++serial.current;
    setBusy(true);
    setError('');
    try {
      const response = await post({
        action: `${engine}_recipe_${write ? 'save' : 'read'}`,
        request: {
          database_target_id: databaseTargetId,
          recipe_id: recipeId,
          ...(write
            ? {expected_version: recipeVersion, recipe: JSON.parse(source)}
            : revision
              ? {version: Number(revision)}
              : {}),
        },
      });
      if (token !== serial.current) return;
      setRecipeVersion(response.current_version);
      if (response.recipe) change(JSON.stringify(response.recipe, null, 2));
      else setError('No saved recipe with this name in this database.');
    } catch (failure) {
      if (token === serial.current) {
        setError(
          failure?.response?.data?.errormsg || failure?.message || 'Recipe storage unavailable'
        );
      }
    } finally {
      if (token === serial.current) setBusy(false);
    }
  };

  const activeRecipeEntryRows = useMemo(() => {
    if (!selected) return [];
    try {
      const parsed = JSON.parse(source);
      const entry = (parsed?.tables || []).find((t) => t.table === selected);
      if (!entry || !entry.columns) return [];
      return Object.entries(entry.columns).map(([colName, spec]) => ({
        column_name: colName,
        kind: spec?.kind || 'default',
        param:
          spec?.value !== undefined
            ? String(spec.value)
            : spec?.start !== undefined
              ? `${spec.start}:${spec.step ?? 1}`
              : spec?.min !== undefined
                ? `${spec.min}:${spec.max ?? 100}`
                : '',
      }));
    } catch {
      return [];
    }
  }, [source, selected]);

  const updateRecipeColumnRows = (nextRows) => {
    try {
      const parsed = JSON.parse(source);
      const entry = (parsed?.tables || []).find((t) => t.table === selected);
      if (!entry) return;
      const nextCols = {};
      for (const row of nextRows) {
        if (!row.column_name) continue;
        const kind = row.kind || 'default';
        if (kind === 'constant') {
          nextCols[row.column_name] = {kind, value: row.param ?? ''};
        } else if (kind === 'sequential') {
          const [start = '1', step = '1'] = String(row.param || '1:1').split(':');
          nextCols[row.column_name] = {kind, start, step};
        } else if (kind === 'random-integer') {
          const [min = '0', max = '100'] = String(row.param || '0:100').split(':');
          nextCols[row.column_name] = {kind, min, max};
        } else {
          nextCols[row.column_name] = {kind};
        }
      }
      entry.columns = nextCols;
      change(JSON.stringify(parsed, null, 2));
    } catch {
      // Ignore transient parse failures while raw JSON editor is mid-edit.
    }
  };

  const tableOptions = useMemo(
    () =>
      tables.map((table) => ({
        value: table.resource_id,
        label:
          engine === 'duckdb'
            ? `${table.catalog}.${table.schema}.${table.name}`
            : `${table.schema}.${table.name}`,
      })),
    [tables, engine]
  );

  const editorStyle = {
    display: 'block',
    boxSizing: 'border-box',
    width: '100%',
    minHeight: 150,
    height: 190,
    maxHeight: 360,
    overflow: 'auto',
    resize: 'vertical',
    fontFamily: 'var(--sr-font-mono, monospace)',
    fontSize: '0.8125rem',
    padding: 8,
    borderRadius: 6,
    border: '1px solid var(--sr-border-default, rgba(128,128,128,0.3))',
    background: 'var(--sr-surface-card, transparent)',
    color: 'inherit',
  };

  const fileInputRef = useRef(null);

  return (
    <Box sx={{...compactFormSx, gridAutoRows: 'max-content', p: 1, overflow: 'auto'}}>
      <FormReference formKey={`${engine}-test-data`} />
      <Banner status="info">
        Generate and review SQL, then open the saved script in the shared Query Tool on this
        database. Generation executes no SQL writes. The Query Tool owns autocommit, commit and
        rollback.
      </Banner>
      {error && <Banner status="error">{error}</Banner>}

      {useMysqlInlineRevisions ? (
        <Stack direction="row" gap="compact" sx={{alignItems: 'flex-end', flexWrap: 'wrap', my: 0.5}}>
          <TextField
            label="Saved recipe name"
            value={recipeId}
            disabled={busy}
            onChange={(event) => {
              const val = event?.target ? event.target.value : String(event ?? '');
              setRecipeId(val);
              setRecipeVersion(0);
              setRevision('');
            }}
          />
          <NumberField
            label="Revision (blank for latest)"
            value={revision}
            disabled={busy}
            onChange={(event) =>
              setRevision(event?.target ? event.target.value : String(event ?? ''))
            }
          />
          <Button disabled={busy || !recipeId} onClick={() => persistMysqlRecipe(false)}>
            Load saved recipe
          </Button>
          <Button disabled={busy || !recipeId} onClick={() => persistMysqlRecipe(true)}>
            Store recipe revision
          </Button>
          <Box sx={{fontSize: '0.8125rem'}}>Current saved revision: {recipeVersion}</Box>
        </Stack>
      ) : (
        <RecipeRevisions
          post={post}
          engine={engine}
          databaseTargetId={databaseTargetId}
          source={source}
          onChange={change}
          disabled={busy}
        />
      )}

      <Stack direction="row" gap="compact" sx={{alignItems: 'flex-end', flexWrap: 'wrap', my: 1}}>
        <Button disabled={busy} onClick={() => run(false)}>
          Load native tables
        </Button>
        <Box sx={{minWidth: 260}}>
          <Select
            label="Native table"
            value={selected}
            options={tableOptions}
            disabled={busy || !tables.length}
            onChange={(val) => setSelected(val)}
          />
        </Box>
        <Box sx={{width: 110}}>
          <NumberField
            label="Rows"
            value={count}
            min={1}
            max={1000}
            disabled={busy}
            onChange={(event) =>
              setCount(event?.target ? event.target.value : event)
            }
          />
        </Box>
        <Button disabled={busy || !selected} onClick={add}>
          Add table
        </Button>
      </Stack>

      {selected && (
        <Box sx={{mb: 1}}>
          <UnifiedDataGrid
            gridRole="table"
            ariaLabel="Native recipe columns"
            searchable
            pagination={columns.length > 10}
            defaultPageSize={10}
            minHeight={130}
            maxHeight={240}
            rows={columns}
            rowKeyGetter={(col) => col.name}
            columns={[
              {name: 'name', label: 'Column', width: 180, mono: true},
              {
                name: 'data_type',
                label: 'Native type',
                width: 160,
                accessorFn: (col) => col.data_type || 'Unavailable',
              },
              {
                name: 'values_policy',
                label: 'Values',
                width: 240,
                accessorFn: (col) =>
                  engine === 'duckdb' || engine === 'sqlite'
                    ? col.has_default
                      ? 'Native default available'
                      : col.nullable
                        ? 'Nullable'
                        : 'Explicit value needed'
                    : col.insertable
                      ? 'Explicit values or default'
                      : 'Native default only',
              },
            ]}
          />
        </Box>
      )}

      {activeRecipeEntryRows.length > 0 && (
        <Box sx={{mb: 1}}>
          <RecordGrid
            field={{
              field_id: 'column_generators',
              label: 'Column Generator Rules',
              control: 'grid',
              columns: [
                {field_id: 'column_name', label: 'Column', control: 'text', readonly: true},
                {
                  field_id: 'kind',
                  label: 'Generator',
                  control: 'select',
                  default: 'default',
                  options: [
                    {value: 'default', label: 'Default'},
                    {value: 'constant', label: 'Constant'},
                    {value: 'sequential', label: 'Sequential (start:step)'},
                    {value: 'random-integer', label: 'Random Int (min:max)'},
                  ],
                },
                {field_id: 'param', label: 'Value / Bounds', control: 'text'},
              ],
            }}
            rows={activeRecipeEntryRows}
            onChange={updateRecipeColumnRows}
            fixedItems
            disabled={busy}
          />
        </Box>
      )}

      <Box sx={{display: 'flex', flexDirection: 'column', gap: 0.5}}>
        <Box component="label" htmlFor={`${formId}-recipe`}>
          Test-data recipe JSON
        </Box>
        <textarea
          id={`${formId}-recipe`}
          value={source}
          onChange={(event) => change(event.target.value)}
          disabled={busy}
          style={editorStyle}
        />
      </Box>

      <Stack direction="row" gap="compact" sx={{my: 1, flexWrap: 'wrap'}}>
        <Button disabled={busy} onClick={() => run(true)}>
          Generate SQL preview
        </Button>
        <input
          ref={fileInputRef}
          hidden
          type="file"
          accept=".json,application/json"
          aria-label={`${label} recipe file`}
          disabled={busy}
          onChange={loadFile}
        />
        <Button disabled={busy} onClick={() => fileInputRef.current?.click()}>
          Read recipe
        </Button>
        <Button
          disabled={busy}
          onClick={() => saveBlob(source, `${engine}-test-data-recipe.json`, 'application/json')}
        >
          Save recipe
        </Button>
        <Button
          disabled={busy || !result}
          onClick={() => saveBlob(result.source, `${engine}-test-data.sql`, 'text/plain')}
        >
          Save SQL script
        </Button>
      </Stack>

      {notesText && (
        <Box component="details">
          <summary>Recipe sources and limits</summary>
          {notesText}
        </Box>
      )}

      {result && (
        <>
          <Banner status="success">
            {result.rows} rows in {result.tables} tables generated; not executed.
          </Banner>
          <Box sx={{display: 'flex', flexDirection: 'column', gap: 0.5}}>
            <Box component="label" htmlFor={`${formId}-sql`}>
              Generated {label} SQL
            </Box>
            <textarea id={`${formId}-sql`} value={result.source} readOnly style={editorStyle} />
          </Box>
        </>
      )}
    </Box>
  );
}

NativeTestDataRecipeView.propTypes = {
  post: PropTypes.func.isRequired,
  databaseTargetId: PropTypes.string.isRequired,
  engine: PropTypes.oneOf(['postgresql', 'duckdb', 'sqlite', 'mysql', 'mariadb']),
  notesText: PropTypes.string,
};
