import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import FirebirdCatalogDesigner from 'sources/Dialogs/FirebirdCatalogDesigner';
import {withTheme} from '../fake_theme';

jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({
  DDNDesignerSurface: ({snapshot, onReady}) => <div data-testid="catalog-designer" data-seed={JSON.stringify(snapshot)}>
    <button onClick={() => onReady({snapshot: () => ({...snapshot,
      files: {...snapshot.files, 'catalog.ddn': 'edited'}, layoutState: {positions: {}}})})}>Edit native facts</button>
    <button onClick={() => onReady({snapshot: () => {throw new Error('Invalid current source');}})}>Invalid source</button>
  </div>,
}));

describe('DDN catalog design review boundary', () => {
  const Component = withTheme(FirebirdCatalogDesigner);
  const snapshot = {format: 'ddn-workspace@1', entry: 'catalog.ddn', view: 'inventory_1',
    files: {'catalog.ddn': 'original', 'catalog-2.ddn': 'second page'}};
  it('captures all files synchronously and only hands metadata to explicit review', async () => {
    const review = jest.fn();
    render(<Component baseline={JSON.stringify(snapshot)} onReview={review} />);
    fireEvent.click(screen.getByText('Edit catalog design in DDN'));
    expect(screen.getByText('SR-F-001375')).toBeVisible();
    expect(screen.getByText('Use design for native review')).toBeDisabled();
    fireEvent.click(screen.getByText('Edit native facts'));
    expect(review).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Use design for native review'));
    expect(JSON.parse(review.mock.calls[0][0])).toEqual({...snapshot,
      files: {...snapshot.files, 'catalog.ddn': 'edited'}});
    await waitFor(() => expect(screen.queryByTestId('catalog-designer')).toBeNull());
    fireEvent.click(screen.getByText('Edit catalog design in DDN'));
    expect(JSON.parse(screen.getByTestId('catalog-designer').dataset.seed).files['catalog.ddn']).toBe('edited');
  });
  it('keeps invalid source open when a newer native baseline arrives', async () => {
    const review = jest.fn();
    const {rerender} = render(<Component baseline={JSON.stringify(snapshot)} onReview={review} />);
    fireEvent.click(screen.getByText('Edit catalog design in DDN'));
    fireEvent.click(screen.getByText('Invalid source'));
    fireEvent.click(screen.getByText('Use design for native review'));
    expect(screen.getByText('Invalid current source')).toBeVisible();
    expect(review).not.toHaveBeenCalled();
    rerender(<Component baseline="replacement source" onReview={review} />);
    await waitFor(() => expect(screen.getByTestId('catalog-designer')).toBeVisible());
    expect(JSON.parse(screen.getByTestId('catalog-designer').dataset.seed).files['catalog.ddn']).toBe('original');
  });
});
