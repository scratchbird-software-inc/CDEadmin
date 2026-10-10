import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import FirebirdScript from '../../../pgadmin/static/js/Dialogs/FirebirdScript';

const preview = {total_entries: 2, entries: [
  {index: 1, line: 1, kind: 'bail', value: false},
  {index: 2, line: 2, kind: 'sql', value: null},
]};

describe('Firebird script workspace', () => {
  it('requires a current preview and invalidates it when source changes or runs', async () => {
    const props = {source: 'SELECT 1;', onPreview: jest.fn().mockResolvedValue(preview), onRun: jest.fn()};
    const {rerender} = render(<FirebirdScript {...props} />);
    expect(screen.getByRole('button', {name: 'Run script'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Preview script'}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'Run script'})).toBeEnabled());
    expect(props.onRun).not.toHaveBeenCalled();
    rerender(<FirebirdScript {...props} source="SELECT 2;" />);
    expect(screen.getByRole('button', {name: 'Run script'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Preview script'}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'Run script'})).toBeEnabled());
    fireEvent.click(screen.getByRole('button', {name: 'Run script'}));
    expect(props.onRun).toHaveBeenCalledTimes(1);
    expect(props.onRun).toHaveBeenCalledWith('SELECT 2;');
    expect(screen.getByRole('button', {name: 'Run script'})).toBeDisabled();
  });

  it('refuses execution after a failed preview or while busy', async () => {
    const props = {source: 'SHELL;', onPreview: jest.fn().mockRejectedValue({message: 'Request failed with status code 400', response: {data: {errormsg: 'Client command refused'}}}), onRun: jest.fn()};
    const {rerender} = render(<FirebirdScript {...props} />);
    fireEvent.click(screen.getByRole('button', {name: 'Preview script'}));
    expect(await screen.findByText('Client command refused')).toBeVisible();
    expect(screen.getByRole('button', {name: 'Run script'})).toBeDisabled();
    rerender(<FirebirdScript {...props} disabled />);
    expect(screen.getByRole('button', {name: 'Preview script'})).toBeDisabled();
    expect(props.onRun).not.toHaveBeenCalled();
  });

  it('pages retained typed results without executing SQL and shows uncertainty', () => {
    const props = {source: 'SELECT 1;', onPreview: jest.fn(), onRun: jest.fn(), result: {
      unknown_outcome: true, stopped_before_end: true,
      entries: [{index: 1, line: 1, kind: 'sql', state: 'succeeded', result: {
        schema: {columns: [{name: 'V', native_type: 'BIGINT'}]},
        payload: {rows: Array.from({length: 201}, (_, i) => [i])},
      }}, {index: 2, line: 2, kind: 'sql', state: 'not_run'}],
    }};
    render(<FirebirdScript {...props} />);
    expect(screen.getByText(/A script outcome is unknown/)).toBeVisible();
    expect(screen.getByText(/Entries marked not_run/)).toBeVisible();
    expect(screen.getByRole('table').querySelectorAll('tbody tr')).toHaveLength(100);
    fireEvent.click(screen.getByRole('button', {name: 'Next result page'}));
    expect(screen.getByRole('table').querySelector('tbody td')).toHaveTextContent('100');
    fireEvent.click(screen.getByRole('button', {name: 'Next result page'}));
    expect(screen.getByRole('table').querySelectorAll('tbody tr')).toHaveLength(1);
    expect(props.onRun).not.toHaveBeenCalled();
    expect(props.onPreview).not.toHaveBeenCalled();
  });
});
