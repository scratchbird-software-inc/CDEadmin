import {registerPostgresqlCompletion} from '../../../pgadmin/static/js/cdeadmin_ui/editors/postgresqlCompletion';

function fixture(source='SELECT * FROM ord', wordFrom=source.length - 3) {
  const state = {doc: {toString: () => source}, sliceDoc: (start, end) => source.slice(start, end), selection: {main: {head: source.length}}};
  const editor = {state, registerAutocomplete: jest.fn()};
  const settings = {active: true, blocked: false, scope: 'pg:one', databaseTargetId: 'one',
    ensureSession: jest.fn().mockResolvedValue('owned'), post: jest.fn().mockResolvedValue({orders: {object_type: 'table'}}), onError: jest.fn()};
  registerPostgresqlCompletion(editor, () => settings);
  return {editor, settings, callback: editor.registerAutocomplete.mock.calls[0][0],
    context: {state, pos: source.length, matchBefore: () => ({from: wordFrom}), aborted: false}};
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

test('native insertion and quote replacement span reach the editor', async () => {
  const {settings, callback, context} = fixture('SELECT * FROM "Mi',15);
  settings.post.mockResolvedValue({completions:{Mixed:{object_type:'column',insert_text:'"Mixed"',replacement_start:14}}});
  const result=await callback(context,jest.fn());
  expect(result).toEqual({from:14,options:[{label:'Mixed',type:'column',apply:'"Mixed"'}]});
});

test('native star expansion replaces the asterisk with the returned column list', async () => {
  const {settings,callback,context}=fixture('SELECT *',8);
  settings.post.mockResolvedValue({completions:{'*':{object_type:'columns',insert_text:'id, value',replacement_start:7}}});
  expect(await callback(context,jest.fn())).toEqual({from:7,options:[{label:'*',type:'columns',apply:'id, value'}]});
});

test('candidates can retain distinct native replacement starts', async () => {
  const {settings, callback, context}=fixture();
  settings.post.mockResolvedValue({completions:{value:{object_type:'column',insert_text:'value',replacement_start:16}}});
  const result=await callback(context,jest.fn());
  expect(result.from).toBe(14);
  const view={state:context.state,dispatch:jest.fn()};
  // Use a real state so CodeMirror builds its native completion transaction.
  const {EditorState}=await import('@codemirror/state');
  view.state=EditorState.create({doc:context.state.doc.toString()});
  result.options[0].apply(view,result.options[0],result.from,context.pos);
  const updated=view.state.update(view.dispatch.mock.calls[0][0]).state;
  expect(updated.doc.toString()).toBe('SELECT * FROM orvalue');
});
