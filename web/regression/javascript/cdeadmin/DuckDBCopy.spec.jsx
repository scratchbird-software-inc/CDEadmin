import {fireEvent, render, screen} from '@testing-library/react';
import DuckDBCopy from 'sources/Dialogs/DuckDBCopy';
import {withTheme} from '../fake_theme';

const Component = withTheme(DuckDBCopy);
const originalHeight = window.innerHeight;
beforeAll(() => {window.innerHeight = 1800;});
afterAll(() => {window.innerHeight = originalHeight;});

describe('DuckDB native COPY preview', () => {
  it('binds one registered table and never dispatches SQL', async () => {
    const post = jest.fn().mockResolvedValueOnce({tables: [{resource_id: 'native-table',
      catalog: 'demo', schema: 'main', name: 'facts'}]})
      .mockResolvedValueOnce({source: 'COPY "demo"."main"."facts" TO \'/owned/facts.parquet\' (FORMAT PARQUET);',
        native_format: 'PARQUET', executed: false});
    render(<Component post={post} databaseTargetId="file-1" resourceId="native-table" />);
    expect(screen.getByText('SR-F-010006')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Load native tables'}));
    await screen.findByText('demo.main.facts');
    fireEvent.change(screen.getByRole('textbox', {name: 'Absolute file path'}),
      {target: {value: '/owned/facts.parquet'}});
    fireEvent.click(screen.getByRole('button', {name: 'Preview native COPY'}));
    await screen.findByText('One native PARQUET COPY statement generated; not executed.');
    expect(post).toHaveBeenLastCalledWith({action: 'duckdb_copy_plan', request: {
      database_target_id: 'file-1', resource_id: 'native-table', direction: 'to',
      format: 'PARQUET', path: '/owned/facts.parquet'}});
    expect(post.mock.calls.every(([request]) => ['duckdb_test_data', 'duckdb_copy_plan'].includes(request.action))).toBe(true);
  });

  it('probes format capabilities and plans JSON/NDJSON, reader_ctas, and Hive-partitioned exports', async () => {
    const post = jest.fn()
      .mockResolvedValueOnce({schema: 'scratchrobin.duckdb.copy-capabilities@1', formats: {CSV: {loaded: true}, PARQUET: {loaded: true}, JSON: {loaded: true}}})
      .mockResolvedValueOnce({source: 'CREATE TABLE "demo"."main"."ingested" AS SELECT * FROM read_json(\'/owned/events.ndjson\', format = \'newline_delimited\', auto_detect = true);',
        native_format: 'JSON', executed: false})
      .mockResolvedValueOnce({tables: [{resource_id: 'native-table', catalog: 'demo', schema: 'main', name: 'facts'}]})
      .mockResolvedValueOnce({source: 'COPY "demo"."main"."facts" TO \'/owned/out\' (FORMAT PARQUET, PARTITION_BY ("region"), OVERWRITE_OR_IGNORE, COMPRESSION ZSTD);',
        native_format: 'PARQUET', executed: false});

    render(<Component post={post} databaseTargetId="file-1" resourceId="native-table" />);
    fireEvent.click(screen.getByRole('button', {name: 'Inspect format capabilities'}));
    const caps = await screen.findByLabelText('DuckDB COPY format capabilities');
    expect(JSON.parse(caps.textContent)).toMatchObject({schema: 'scratchrobin.duckdb.copy-capabilities@1'});

    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Direction'}));
    fireEvent.click(screen.getByRole('option', {name: 'Create table from reader (CTAS)'}));
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Format'}));
    fireEvent.click(screen.getByRole('option', {name: 'JSON / NDJSON'}));
    fireEvent.change(screen.getByRole('textbox', {name: 'New target table'}), {target: {value: 'ingested'}});
    fireEvent.change(screen.getByRole('textbox', {name: 'Absolute file path'}), {target: {value: '/owned/events.ndjson'}});
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'JSON layout'}));
    fireEvent.click(screen.getByRole('option', {name: 'NEWLINE_DELIMITED'}));
    fireEvent.click(screen.getByRole('checkbox', {name: 'Auto-detect JSON schema'}));
    fireEvent.click(screen.getByRole('checkbox', {name: 'Partitioned source directory'}));
    fireEvent.click(screen.getByRole('button', {name: 'Preview native COPY'}));
    await screen.findByText('One native JSON COPY statement generated; not executed.');
    expect(post).toHaveBeenLastCalledWith({
      action: 'duckdb_copy_plan',
      request: {
        database_target_id: 'file-1',
        direction: 'reader_ctas',
        format: 'JSON',
        path: '/owned/events.ndjson',
        target_schema: 'main',
        target_table: 'ingested',
        partitioned_source: true,
        options: {json_format: 'NEWLINE_DELIMITED', auto_detect: true},
      },
    });

    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Direction'}));
    fireEvent.click(screen.getByRole('option', {name: 'Export table to file'}));
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Format'}));
    fireEvent.click(screen.getByRole('option', {name: 'PARQUET'}));
    fireEvent.click(screen.getByRole('button', {name: 'Load native tables'}));
    await screen.findByText('demo.main.facts');
    fireEvent.change(screen.getByRole('textbox', {name: 'Absolute file path'}), {target: {value: '/owned/out'}});
    fireEvent.change(screen.getByRole('textbox', {name: 'Partition columns (comma-separated)'}), {target: {value: 'region'}});
    fireEvent.click(screen.getByRole('checkbox', {name: 'Overwrite or ignore'}));
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Parquet compression'}));
    fireEvent.click(screen.getByRole('option', {name: 'ZSTD'}));
    fireEvent.click(screen.getByRole('button', {name: 'Preview native COPY'}));
    await screen.findByText('One native PARQUET COPY statement generated; not executed.');
    expect(post).toHaveBeenLastCalledWith({
      action: 'duckdb_copy_plan',
      request: {
        database_target_id: 'file-1',
        resource_id: 'native-table',
        direction: 'to',
        format: 'PARQUET',
        path: '/owned/out',
        options: {partition_by: ['region'], overwrite_or_ignore: true, compression: 'ZSTD'},
      },
    });
  });
});
