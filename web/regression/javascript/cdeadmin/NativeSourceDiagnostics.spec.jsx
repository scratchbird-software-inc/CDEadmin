import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import LanguageSourceEditor from '../../../pgadmin/static/js/cdeadmin_ui/editors/LanguageSourceEditor';
import {withTheme} from '../fake_theme';

jest.mock('../../../pgadmin/static/js/cdeadmin_ui/editors/CodeEditor', () => ({
  __esModule: true, default: ({label, value, onChange}) =>
    <textarea aria-label={label} value={value} onChange={event => onChange(event.target.value)} />,
}));

const Editor = withTheme(LanguageSourceEditor);
afterEach(() => {cleanup(); jest.useRealTimers();});

test('retained MySQL scripts send attributes during preview and require a new preview after edits', async () => {
  const props={language:{language_profile:'mysql-sql',tooling:{script_framing:true}},source:'SELECT 1',onChange:jest.fn(),
    mysqlAttributeSource:'{"tag":null}',post:jest.fn().mockResolvedValue({plan_id:'owned',state:'ready',statements:[]}),
    ensureSession:jest.fn().mockResolvedValue('native'),databaseTargetId:'database',onScriptLock:jest.fn()};
  const {rerender}=render(<Editor {...props} />);
  fireEvent.click(screen.getByText('Source tools'));
  await act(async()=>{fireEvent.click(screen.getByText('Preview script'));});
  expect(props.post).toHaveBeenCalledWith(expect.objectContaining({action:'native_script_prepare',mysql_query_attributes:{tag:null}}));
  expect(screen.getByText('Run / resume retained script').closest('button')).not.toBeDisabled();
  rerender(<Editor {...props} mysqlAttributeSource='{"tag":"changed"}' />);
  expect(screen.getByText('Run / resume retained script').closest('button')).toBeDisabled();
  expect(screen.getByText(/Query attributes changed/)).toBeInTheDocument();
});

test('incremental native checking is opt-in and discards replies for earlier source', async () => {
  jest.useFakeTimers();
  let reply;
  const props = {language: {language_profile: 'mysql-sql'}, source: 'SELEC 1', onChange: jest.fn(),
    post: jest.fn(() => new Promise(resolve => {reply = resolve;})), ensureSession: jest.fn().mockResolvedValue('owned'),
    databaseTargetId: 'native-file', onScriptLock: jest.fn()};
  const {rerender} = render(<Editor {...props} />);
  await act(async () => {jest.advanceTimersByTime(1500);});
  expect(props.post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('Source tools'));
  fireEvent.click(screen.getByLabelText('Check while typing'));
  await act(async () => {jest.advanceTimersByTime(1250);});
  expect(props.post).toHaveBeenCalledWith({action: 'source_validate', session_id: 'owned',
    source: 'SELEC 1', database_target_id: 'native-file'});
  rerender(<Editor {...props} source="SELECT 1" />);
  await act(async () => {reply({grammar_valid: false, diagnostics: [{severity: 'error', line: 1, column: 1, message: 'Earlier source rejected'}]});});
  expect(screen.queryByText(/Earlier source rejected/)).toBeNull();
});
