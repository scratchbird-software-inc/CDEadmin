import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import LanguageSourceEditor from '../../../pgadmin/static/js/cdeadmin_ui/editors/LanguageSourceEditor';
import {withTheme} from '../fake_theme';

jest.mock('../../../pgadmin/static/js/cdeadmin_ui/editors/CodeEditor', () => ({
  __esModule: true, default: ({label, value, onChange}) =>
    <textarea aria-label={label} value={value} onChange={event => onChange(event.target.value)} />,
}));

const Editor = withTheme(LanguageSourceEditor);

test('DuckDB prepares one native statement and sends multi-statement work to retained review', async () => {
  const source = 'SELECT 1; SELECT 2';
  const execute = jest.fn();
  const post = jest.fn().mockImplementation(async request => request.action === 'source_validate' ? {
    syntax_valid: true, statements: [
      {source: 'SELECT 1', start: 0, end: 8},
      {source: 'SELECT 2', start: 10, end: 18},
    ],
  } : {plan_id: 'native', state: 'ready', revision: 0,
    statements: [{source: 'SELECT 1'}, {source: 'SELECT 2'}]});
  render(<Editor language={{language_profile: 'duckdb-sql', tooling: {script_framing: true}}}
    source={source} onChange={jest.fn()} post={post} ensureSession={async () => 'owned'}
    databaseTargetId="file" onScriptLock={jest.fn()} onExecute={execute} />);
  fireEvent.click(screen.getByText('Prepare current statement'));
  expect(await screen.findByLabelText('Prepared execution source')).toHaveValue('SELECT 1');
  fireEvent.click(screen.getByText('Run prepared source'));
  expect(execute).toHaveBeenCalledWith('SELECT 1', false);
  execute.mockClear();
  fireEvent.click(screen.getByText('Prepare from cursor'));
  fireEvent.click(await screen.findByText('Preview prepared script'));
  await waitFor(() => expect(post).toHaveBeenCalledWith(expect.objectContaining({
    action: 'native_script_prepare', source: 'SELECT 1\n;\nSELECT 2',
    session_id: 'owned', database_target_id: 'file',
  })));
  expect(execute).not.toHaveBeenCalled();
  expect(post.mock.calls.some(([request]) => request.action === 'native_script_advance')).toBe(false);
});
