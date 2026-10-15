import {duckdbExecution} from '../../../pgadmin/static/js/cdeadmin_ui/editors/duckdbExecution';

test('prepares native DuckDB statement spans around Unicode and quoted semicolons', async () => {
  const first = 'SELECT \'😀;\'', second = 'SELECT 2';
  const source = first + ';\n' + second + ';';
  const validate = jest.fn().mockResolvedValue({syntax_valid: true, statements: [
    {source: first, start: 0, end: Array.from(first).length},
    {source: second, start: Array.from(first).length + 2,
      end: Array.from(first).length + 2 + second.length},
  ]});
  expect(await duckdbExecution(source, 'current', source.indexOf(second), source.indexOf(second), validate))
    .toEqual({source: second, scriptMode: false});
  expect(await duckdbExecution(source, 'from-cursor', 0, 0, validate))
    .toEqual({source: first + '\n;\n' + second, scriptMode: true});
  expect(validate).toHaveBeenCalledWith(source);
});

test('validates a selection alone and rejects parser failure without execution', async () => {
  const validate = jest.fn().mockResolvedValue({syntax_valid: true,
    statements: [{source: 'SELECT 1', start: 0, end: 8}]});
  expect(await duckdbExecution('invalid SELECT 1', 'selection', 8, 16, validate))
    .toEqual({source: 'SELECT 1', scriptMode: false});
  expect(validate).toHaveBeenCalledWith('SELECT 1');
  validate.mockResolvedValueOnce({syntax_valid: false,
    diagnostics: [{message: 'Native DuckDB parser rejected the source.'}]});
  await expect(duckdbExecution('bad', 'current', 0, 0, validate))
    .rejects.toThrow('Native DuckDB parser rejected');
});
