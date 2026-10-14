import {registerPostgresqlCompletion} from '../../../pgadmin/static/js/cdeadmin_ui/editors/postgresqlCompletion';

function fixture() {
  const source = 'SELECT * FROM ord';
  const state = {doc: {toString: () => source}, sliceDoc: (start, end) => source.slice(start, end), selection: {main: {head: source.length}}};
  const editor = {state, registerAutocomplete: jest.fn()};
  const settings = {active: true, blocked: false, scope: 'pg:one', databaseTargetId: 'one',
    ensureSession: jest.fn().mockResolvedValue('owned'), post: jest.fn().mockResolvedValue({orders: {object_type: 'table'}}), onError: jest.fn()};
  registerPostgresqlCompletion(editor, () => settings);
  return {editor, settings, callback: editor.registerAutocomplete.mock.calls[0][0],
    context: {state, pos: source.length, matchBefore: () => ({from: source.length - 3}), aborted: false}};
}

test('uses the owned PostgreSQL session and exact cursor prefix without execution', async () => {
  const {settings, callback, context} = fixture(); const available = jest.fn();
  const result = await callback(context, available);
  expect(settings.post).toHaveBeenCalledWith({action: 'source_complete', session_id: 'owned',
    source: 'SELECT * FROM ord', source_before_cursor: 'SELECT * FROM ord', database_target_id: 'one'});
  expect(result).toEqual({from: 14, options: [{label: 'orders', type: 'table'}]});
  expect(available).toHaveBeenCalledTimes(1);
});

test.each(['scope', 'cursor', 'source', 'blocked', 'aborted', 'unmounted'])('drops late completion after %s changes', async change => {
  const {settings, editor, callback, context} = fixture(); let resolve;
  settings.post.mockImplementation(() => new Promise(done => {resolve = done;}));
  const available = jest.fn(); const pending = callback(context, available);
  await Promise.resolve();
  if (change === 'scope') settings.scope = 'pg:two';
  if (change === 'cursor') editor.state = {...editor.state, selection: {main: {head: 0}}};
  if (change === 'source') editor.state = {...editor.state, doc: {toString: () => 'SELECT 2'}};
  if (change === 'blocked') settings.blocked = true;
  if (change === 'aborted') context.aborted = true;
  if (change === 'unmounted') settings.active = false;
  resolve({orders: {object_type: 'table'}});
  expect(await pending).toBeNull();
  expect(available).toHaveBeenCalledTimes(1);
});

test('blocked completion opens no session and sends no request', async () => {
  const {settings, callback, context} = fixture(); settings.blocked = true;
  expect(await callback(context, jest.fn())).toBeNull();
  expect(settings.ensureSession).not.toHaveBeenCalled();
  expect(settings.post).not.toHaveBeenCalled();
});
