import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import FirebirdTemplates from 'sources/Dialogs/FirebirdTemplates';
import {withTheme} from '../fake_theme';

describe('Firebird object templates', () => {
  const Component = withTheme(FirebirdTemplates);
  it('renders explicit source without executing and invalidates a changed preview', async () => {
    const post = jest.fn().mockResolvedValueOnce({templates: {select: 'SELECT {{columns}} FROM {{object}};'}})
      .mockResolvedValueOnce({source: 'SELECT "V" FROM "T";', parameters: [], executed: false});
    const onLoad = jest.fn();
    render(<Component post={post} resource={{resource_id: 't', display_name: 'T'}} generation="g" databaseTargetId="db" onLoad={onLoad} />);
    await screen.findByLabelText('Reusable SQL template');
    expect(onLoad).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Render template preview'));
    await screen.findByLabelText('Rendered native SQL');
    fireEvent.click(screen.getByText('Load rendered SQL into editor'));
    expect(onLoad).toHaveBeenCalledWith(expect.objectContaining({executed: false}));
    expect(post.mock.calls.every(([request]) => request.action === 'firebird_object_templates')).toBe(true);
    expect(post.mock.calls[1][0].request).toEqual(expect.objectContaining({generation: 'g', database_target_id: 'db', resource_id: 't'}));
    fireEvent.change(screen.getByLabelText('New object name'), {target: {value: 'OTHER'}});
    await waitFor(() => expect(screen.queryByLabelText('Rendered native SQL')).toBeNull());
  });
  it('does not expose failed context data or enable loading', async () => {
    const post = jest.fn().mockRejectedValue(new Error('private secret'));
    render(<Component post={post} resource={{resource_id: 't'}} generation="g" />);
    expect(await screen.findByText(/Native template context is unavailable/)).toBeVisible();
    expect(screen.queryByText('private secret')).toBeNull();
    expect(screen.queryByText('Load rendered SQL into editor')).toBeNull();
  });
});
