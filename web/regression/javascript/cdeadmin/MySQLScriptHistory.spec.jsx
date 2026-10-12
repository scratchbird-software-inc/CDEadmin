import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import LanguageSourceEditor from 'sources/cdeadmin_ui/editors/LanguageSourceEditor';
import {withTheme} from '../fake_theme';

jest.mock('sources/cdeadmin_ui/editors/CodeEditor', () => () => null);

const Component = withTheme(LanguageSourceEditor);

describe('MySQL retained script source history', () => {
  it('carries explicit sensitive-source intent without adding a Firebird dialect', async () => {
    const post = jest.fn().mockResolvedValue({plan_id: 'review', state: 'ready'});
    render(<Component language={{language_profile: 'mysql-sql', tooling: {script_framing: true}}}
      source="SELECT 'private';" onChange={jest.fn()} post={post}
      ensureSession={jest.fn().mockResolvedValue('mysql-session')} databaseTargetId="mysql-target"
      historySensitive onScriptLock={jest.fn()} />);
    fireEvent.click(screen.getByRole('button', {name: 'Preview script'}));
    await waitFor(() => expect(post).toHaveBeenCalledWith({
      action: 'native_script_prepare', session_id: 'mysql-session',
      source: "SELECT 'private';", database_target_id: 'mysql-target', history_sensitive: true,
    }));
    expect(post).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', {name: 'Run / resume retained script'})).toBeEnabled();
  });
});
