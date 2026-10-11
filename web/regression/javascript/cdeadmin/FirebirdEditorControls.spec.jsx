import {TextEncoder} from 'util';
import {fireEvent, render, screen} from '@testing-library/react';
import LanguageSourceEditor from 'sources/cdeadmin_ui/editors/LanguageSourceEditor';
import {withTheme} from '../fake_theme';

describe('Firebird prepared execution controls', () => {
  const Component = withTheme(LanguageSourceEditor);
  let encoder;
  beforeEach(() => {encoder = global.TextEncoder; global.TextEncoder = TextEncoder;});
  afterEach(() => {global.TextEncoder = encoder;});
  it('requires a preview and explicit run, and invalidates it when source changes', () => {
    const onExecute = jest.fn(), post = jest.fn();
    const props = {language: {language_profile: 'firebird-sql'}, source: 'select 1; select 2;',
      onChange: jest.fn(), post, ensureSession: jest.fn(), onScriptLock: jest.fn(), onExecute};
    const {rerender} = render(<Component {...props} />);
    const source = screen.getByLabelText('Query source');
    source.setSelectionRange(11, 13);
    fireEvent.click(screen.getByText('Prepare current statement'));
    expect(screen.getByLabelText('Prepared execution source')).toHaveValue('select 2');
    expect(onExecute).not.toHaveBeenCalled(); expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Run prepared source'));
    expect(onExecute).toHaveBeenCalledTimes(1);
    expect(onExecute).toHaveBeenCalledWith('select 2', false);
    expect(screen.queryByText('Run prepared source')).toBeNull();
    fireEvent.click(screen.getByText('Prepare current statement'));
    rerender(<Component {...props} source="select 3;" />);
    expect(screen.queryByText('Run prepared source')).toBeNull();
  });
});
