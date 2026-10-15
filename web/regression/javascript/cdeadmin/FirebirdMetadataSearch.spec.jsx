import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import FirebirdMetadataSearch from 'sources/Dialogs/FirebirdMetadataSearch';
import {withTheme} from '../fake_theme';

describe('Firebird multi-database search', () => {
  const Component = withTheme(FirebirdMetadataSearch);
  const targets = [{target_id: 'a', label: 'First'}, {target_id: 'b', label: 'Second'}];
  it('keeps partial successes and opens the exact database/object identity', async () => {
    const onOpen = jest.fn();
    const match = {resource_id: 'p', resource_kind: 'procedure', display_name: 'P', display_path: ['P'], matched_fields: ['name'], snippet: 'P'};
    const post = jest.fn().mockResolvedValueOnce({target_id: 'a', matches: [match], match_count: 1}).mockRejectedValueOnce(new Error('credential secret'));
    render(<Component targets={targets} post={post} onOpen={onOpen} />);
    fireEvent.click(screen.getByLabelText('First')); fireEvent.click(screen.getByLabelText('Second'));
    fireEvent.change(screen.getByLabelText('Metadata search text'), {target: {value: 'P'}});
    fireEvent.click(screen.getByText('Search metadata'));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post.mock.calls.map(call => call[0].request.target_id)).toEqual(['a', 'b']);
    expect(await screen.findByText(/Database search unavailable/)).toBeVisible();
    expect(screen.queryByText('credential secret')).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'procedure: P'})); expect(onOpen).toHaveBeenCalledWith('a', match);
  });
  it('stops between catalogs without claiming to cancel the active request', async () => {
    let resolve;
    const post = jest.fn(() => new Promise(done => {resolve = done;}));
    render(<Component targets={targets} post={post} />);
    fireEvent.click(screen.getByLabelText('First')); fireEvent.click(screen.getByLabelText('Second'));
    fireEvent.change(screen.getByLabelText('Metadata search text'), {target: {value: 'P'}});
    fireEvent.click(screen.getByText('Search metadata'));
    fireEvent.click(screen.getByText('Stop after current database'));
    resolve({target_id: 'a', matches: [], match_count: 0});
    expect(await screen.findByText('Search stopped. Completed database results remain visible.')).toBeVisible();
    expect(post).toHaveBeenCalledTimes(1);
  });
  it('drops a late old-endpoint result and stops the remaining catalog requests', async () => {
    let finish;
    const post = jest.fn(() => new Promise(resolve => {finish = resolve;}));
    const nextPost = jest.fn();
    const {rerender} = render(<Component targets={targets} post={post} />);
    fireEvent.click(screen.getByLabelText('First')); fireEvent.click(screen.getByLabelText('Second'));
    fireEvent.change(screen.getByLabelText('Metadata search text'), {target: {value: 'OLD'}});
    fireEvent.click(screen.getByText('Search metadata'));
    rerender(<Component targets={targets} post={nextPost} />);
    finish({target_id: 'a', matches: [{resource_id: 'old', display_name: 'OLD'}], match_count: 1});
    await waitFor(() => expect(screen.getByText('Search metadata')).toBeDisabled());
    expect(screen.queryByText('OLD')).toBeNull();
    expect(post).toHaveBeenCalledTimes(1); expect(nextPost).not.toHaveBeenCalled();
  });
  it('displays native catalog coverage gaps and warnings alongside matches', async () => {
    const post = jest.fn().mockResolvedValue({target_id: 'a', matches: [], match_count: 0,
      catalog_coverage: [{state: 'partial', unavailable_sections: ['database creation authority']}],
      catalog_warnings: ['Role administration is not visible to this attachment.']});
    render(<Component targets={targets} post={post} />);
    fireEvent.click(screen.getByLabelText('First'));
    fireEvent.change(screen.getByLabelText('Metadata search text'), {target: {value: 'name'}});
    fireEvent.click(screen.getByText('Search metadata'));
    expect(await screen.findByText(/Partial native catalog.*database creation authority/)).toBeVisible();
    expect(screen.getByText('Role administration is not visible to this attachment.')).toBeVisible();
  });

});
