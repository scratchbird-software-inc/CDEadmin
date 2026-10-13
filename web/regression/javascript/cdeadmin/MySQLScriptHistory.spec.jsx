import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import LanguageSourceEditor from 'sources/cdeadmin_ui/editors/LanguageSourceEditor';
import {withTheme} from '../fake_theme';

jest.mock('sources/cdeadmin_ui/editors/CodeEditor', () => () => null);

const Component = withTheme(LanguageSourceEditor);

describe('MySQL and MariaDB retained script source history', () => {
  it.each(['mysql', 'mariadb'])('%s carries sensitive-source intent without a Firebird dialect', async engine => {
    const post = jest.fn().mockResolvedValue({plan_id: 'review', state: 'ready'});
    render(<Component language={{language_profile: `${engine}-sql`, tooling: {script_framing: true}}}
      source="SELECT 'private';" onChange={jest.fn()} post={post}
      ensureSession={jest.fn().mockResolvedValue(`${engine}-session`)} databaseTargetId={`${engine}-target`}
      historySensitive onScriptLock={jest.fn()} />);
    fireEvent.click(screen.getByRole('button', {name: 'Preview script'}));
    await waitFor(() => expect(post).toHaveBeenCalledWith({
      action: 'native_script_prepare', session_id: `${engine}-session`,
      source: "SELECT 'private';", database_target_id: `${engine}-target`, history_sensitive: true,
    }));
    expect(post).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', {name: 'Run / resume retained script'})).toBeEnabled();
  });
});
