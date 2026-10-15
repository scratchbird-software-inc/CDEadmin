import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {generatorTable, materializeTestData, parseRecipe, stageTestData} from 'sources/Dialogs/firebirdTestDataHelpers';
import FirebirdTestData from 'sources/Dialogs/FirebirdTestData';
import {withTheme} from '../fake_theme';

const resource = name => ({resource_kind: 'table', resource_id: 'table:' + name, display_name: name, display_path: [name], native: {constraints: []}});
const catalog = (name, foreignKeys=[]) => ({resource: resource(name), columns: [{name: 'ID', input_kind: 'integer', insertable: true}, {name: 'REF', input_kind: 'integer', insertable: true}],
  rows: [{values: {ID: '7', REF: '8'}}, {values: {ID: '9', REF: '10'}}], foreignKeys});
const recipe = tables => ({format: 'scratchrobin.firebird.test-data@1', seed: 42, tables});
const sequence = {kind: 'sequential', start: '9007199254740993', step: '1'};

describe('Firebird test data materialization', () => {
  it('uses native system classification rather than guessing from user names', () => {
    expect(generatorTable(resource('MON$CUSTOM'))).toBe(true);
    expect(generatorTable({...resource('T'), native: {system_object: true}})).toBe(false);
    expect(generatorTable({...resource('T'), resource_kind: 'view'})).toBe(false);
  });
  it('orders generated foreign keys and preserves exact composite source row positions', () => {
    const input = recipe([{table: 'A', count: 3, columns: {ID: {kind: 'generated', table: 'Z', column: 'ID'}, REF: {kind: 'generated', table: 'Z', column: 'REF'}}},
      {table: 'Z', count: 2, columns: {ID: sequence, REF: {kind: 'sequential', start: '100', step: '2'}}}]);
    const catalogs = {A: catalog('A', [{table: 'Z', columns: ['ID', 'REF']}]), Z: catalog('Z')};
    const result = materializeTestData(input, catalogs);
    expect(result.order).toEqual(['Z', 'A']);
    expect(result.operations.slice(2).map(item => item.values)).toEqual([
      {ID: '9007199254740993', REF: '100'}, {ID: '9007199254740994', REF: '102'}, {ID: '9007199254740993', REF: '100'}]);
    expect(materializeTestData(input, catalogs)).toEqual(result);
  });
  it('supports random, sequential, file and sampled sources without modifying inputs', () => {
    const catalogs = {T: catalog('T'), S: catalog('S')};
    for (const source of [{kind: 'random-integer', min: '-3', max: '3'}, {kind: 'choice', values: ['a', 'b']},
      {kind: 'file', values: [null, 'x']}, {kind: 'existing', table: 'S', column: 'ID'}]) {
      const input = recipe([{table: 'T', count: 10, columns: {ID: source, REF: {kind: 'constant', value: 'x', nullPercent: 100}}}]);
      const before = JSON.stringify(input), result = materializeTestData(input, catalogs);
      expect(materializeTestData(input, catalogs)).toEqual(result);
      expect(result.operations.every(item => item.values.REF === null)).toBe(true);
      expect(JSON.stringify(input)).toBe(before);
    }
  });
  it('rejects cycles before dispatch and accepts an explicit NULL break', () => {
    const catalogs = {T: catalog('T', [{table: 'T', columns: ['REF']}])};
    const input = recipe([{table: 'T', count: 1, columns: {ID: sequence, REF: {kind: 'constant', value: '1'}}}]);
    expect(() => materializeTestData(input, catalogs)).toThrow(/Cyclic/);
    input.tables[0].columns.REF.value = null;
    expect(materializeTestData(input, catalogs).operations).toHaveLength(1);
  });
  it('rejects unavailable sources, noninsertable columns and excessive row counts', () => {
    for (const input of [recipe([{table: 'T', count: 1001, columns: {}}]),
      recipe([{table: 'missing', count: 1, columns: {}}]),
      recipe([{table: 'T', count: 1, columns: {ID: {kind: 'existing', table: 'missing', column: 'ID'}}}]),
      recipe([{table: 'T', count: 1, columns: {ID: {kind: 'sequential', start: 9007199254740992, step: '1'}}}])]) {
      expect(() => materializeTestData(input, {T: catalog('T')})).toThrow();
    }
    expect(() => parseRecipe('{}')).toThrow();
  });
  it('refuses rounded values and bounds repeated file data before building excessive output', () => {
    const catalogs = {T: catalog('T')};
    expect(() => materializeTestData(recipe([{table: 'T', count: 1, columns: {ID: {kind: 'constant', value: 0.1}}}]), catalogs)).toThrow(/exact/);
    expect(() => materializeTestData(recipe([{table: 'T', count: 1000, columns: {ID: {kind: 'file', values: ['x'.repeat(8000)]}}}]), catalogs)).toThrow(/4 MiB/);
    expect(materializeTestData(recipe([{table: 'T', count: 1, columns: {ID: {kind: 'constant', value: '1', nullPercent: 0.5}}}]), catalogs).operations).toHaveLength(1);
  });
});

describe('Firebird generator dispatch and native transaction controls', () => {
  const catalogs = {T: catalog('T')};
  const preview = materializeTestData(recipe([{table: 'T', count: 3, columns: {ID: sequence}}]), catalogs);
  const admitted = request => request.action === 'visual_admin_validate' ? {valid: true} : request.action === 'visual_admin_plan' ?
    {state: 'ready', execution_available: true, plan_id: 'p', plan_digest: 'd'} : {provider_result: {staged_in_provider_session: true}};
  it('stops after an in-flight row without committing or replaying', async () => {
    let stopped = false;
    const post = jest.fn(async request => {if (request.action === 'visual_admin_apply') stopped = true; return admitted(request);});
    const result = await stageTestData({preview, catalogs, post, sessionId: 's', databaseTargetId: 'db', stopped: () => stopped, onProgress: jest.fn()});
    expect(result).toEqual({state: 'stopped', staged: 1, dispatched: 1});
    expect(post.mock.calls.map(([request]) => request.action)).toEqual(['visual_admin_validate', 'visual_admin_plan', 'visual_admin_apply']);
    expect(post.mock.calls.every(([request]) => request.request.session_id === 's' && request.request.database_target_id === 'db')).toBe(true);
  });
  it('does not continue after a lost response', async () => {
    const post = jest.fn(async request => {if (request.action === 'visual_admin_apply') throw new Error('lost'); return admitted(request);});
    const result = await stageTestData({preview, catalogs, post, sessionId: 's', databaseTargetId: 'db', stopped: () => false, onProgress: jest.fn()});
    expect(result.state).toBe('stopped_after_error'); expect(result.staged).toBe(0);
    expect(post).toHaveBeenCalledTimes(3);
  });
  it('requires preview and confirmation, samples with rollback, then explicitly finalizes staged rows', async () => {
    const post = jest.fn(async request => {
      if (request.action === 'open_session') return {session_id: 'generator'};
      if (request.action === 'visual_admin_rows') return {...catalog('T'), row_operations: ['insert'], complete: true};
      if (request.action === 'transaction_action') return {provider_payload: {state: 'inactive'}};
      return admitted(request);
    });
    const Component = withTheme(FirebirdTestData);
    render(<Component resources={[resource('T')]} post={post} databaseTargetId="db" languageProfile="firebird-sql" />);
    fireEvent.click(screen.getByLabelText('T'));
    fireEvent.click(screen.getByRole('button', {name: 'Load table columns and existing samples'}));
    await waitFor(() => expect(screen.getByLabelText('Test-data recipe JSON').value).toContain('scratchrobin.firebird.test-data'));
    expect(post.mock.calls.filter(([request]) => request.action === 'transaction_action').map(([request]) => request.transaction_action)).toEqual(['rollback']);
    fireEvent.change(screen.getByLabelText('Test-data recipe JSON'), {target: {value: JSON.stringify(recipe([{table: 'T', count: 2, columns: {ID: sequence}}]))}});
    fireEvent.click(screen.getByRole('button', {name: 'Preview generated rows'}));
    expect(screen.getByRole('button', {name: 'Stage generated rows'})).toBeDisabled();
    fireEvent.click(screen.getByLabelText('I authorize staging these generated rows in this database'));
    fireEvent.click(screen.getByRole('button', {name: 'Stage generated rows'}));
    await screen.findByText(/2 rows confirmed staged/);
    expect(post.mock.calls.filter(([request]) => request.action === 'visual_admin_apply')).toHaveLength(2);
    expect(post.mock.calls.some(([request]) => request.transaction_action === 'commit')).toBe(false);
    fireEvent.click(screen.getByRole('button', {name: 'Rollback generated rows'}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'Rollback generated rows'})).toBeDisabled());
  });
});
