import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import FirebirdERD from 'sources/Dialogs/FirebirdERD';
import {withTheme} from '../fake_theme';

jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({
  DDNViewerSurface: ({snapshot}) => <div data-testid="viewer">{snapshot.files['relations.ddn']}</div>,
  DDNDesignerSurface: ({snapshot, onChange, onReady}) => <div data-testid="designer" data-seed={snapshot.files['relations.ddn']}>
    <button onClick={() => onReady({snapshot: () => ({...snapshot, files: {'relations.ddn': 'instant edit'}})})}>Edit before notification</button>
    <button onClick={() => onChange({...snapshot, files: {'relations.ddn': 'edited design'}})}>Change design</button>
  </div>,
}));

describe('Native relational DDN handoff', () => {
  const Component = withTheme(FirebirdERD);
  const diagram = {snapshot: {format: 'ddn-workspace@1', entry: 'relations.ddn', view: 'relations_1', files: {'relations.ddn': 'native design'}},
    views: [{id: 'relations_1', label: 'Native relations'}], warnings: ['Missing referenced object']};
  it('edits only the diagram draft, retains changes and keeps editor seed stable', async () => {
    render(<Component diagram={diagram} />);
    expect(screen.getByTestId('viewer')).toHaveTextContent('native design');
    expect(screen.getByText('Missing referenced object')).toBeVisible();
    fireEvent.click(screen.getByText('Edit relational diagram in DDN'));
    fireEvent.click(screen.getByText('Change design'));
    expect(screen.getByTestId('designer')).toHaveAttribute('data-seed', 'native design');
    fireEvent.click(screen.getByText('Return to diagram viewer'));
    expect(screen.getByTestId('viewer')).toHaveTextContent('edited design');
    await waitFor(() => expect(screen.getAllByText('SR-F-001365')).toHaveLength(1));
  });
  it('captures the editor synchronously before a delayed change notification', () => {
    render(<Component diagram={diagram} />);
    fireEvent.click(screen.getByText('Edit relational diagram in DDN'));
    fireEvent.click(screen.getByText('Edit before notification'));
    fireEvent.click(screen.getByText('Return to diagram viewer'));
    expect(screen.getByTestId('viewer')).toHaveTextContent('instant edit');
  });
  it('discloses a bounded diagram refusal without claiming catalog failure', () => {
    render(<Component diagram={{unavailable: 'view limit'}} />);
    expect(screen.getByText('Relational diagram unavailable: view limit')).toBeVisible();
    expect(screen.queryByTestId('viewer')).toBeNull();
  });
  it('hands original and edited relational native facts to explicit review without execution', async () => {
    const value = {baseline: 'native baseline', desired: 'native desired', executed: false};
    const post = jest.fn().mockResolvedValue(value), onReview = jest.fn();
    render(<Component diagram={diagram} post={post} databaseTargetId="db" generation="g" onReview={onReview} />);
    fireEvent.click(screen.getByText('Edit relational diagram in DDN'));
    fireEvent.click(screen.getByText('Edit before notification'));
    fireEvent.click(screen.getByText('Return to diagram viewer'));
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Review relational metadata changes'));
    await waitFor(() => expect(onReview).toHaveBeenCalledWith(value));
    expect(post).toHaveBeenCalledWith({action: 'firebird_relational_review', request: {
      generation: 'g', original: diagram.snapshot,
      snapshot: {...diagram.snapshot, files: {'relations.ddn': 'instant edit'}},
    }});
  });
  it('uses the paired designer and MySQL form identity without sending Firebird operations', () => {
    const post = jest.fn();
    render(<Component diagram={diagram} engine="mysql" databaseTargetId="mysql-db" post={post} />);
    expect(screen.getByText('SR-F-001398')).toBeVisible();
    fireEvent.click(screen.getByText('Edit relational diagram in DDN'));
    fireEvent.click(screen.getByText('Change design'));
    fireEvent.click(screen.getByText('Return to diagram viewer'));
    expect(screen.getByTestId('viewer')).toHaveTextContent('edited design');
    expect(post).not.toHaveBeenCalled();
    expect(screen.queryByText('Review relational metadata changes')).toBeNull();
  });

});

it('binds MySQL relational review to the registered database target without Firebird generation admission', async () => {
  const Component = withTheme(FirebirdERD);
  const diagram = {snapshot: {format:'ddn-workspace@1',entry:'relations.ddn',view:'relations_1',files:{'relations.ddn':'native design'}},views:[]};
  const post=jest.fn().mockResolvedValue({baseline:'before',desired:'after'}),onReview=jest.fn();
  render(<Component diagram={diagram} engine="mysql" databaseTargetId="mysql-target" post={post} onReview={onReview} />);
  fireEvent.click(screen.getByText('Review relational metadata changes'));
  await waitFor(() => expect(onReview).toHaveBeenCalledWith({baseline:'before',desired:'after'}));
  expect(post).toHaveBeenCalledWith({action:'mysql_relational_review',request:{database_target_id:'mysql-target',original:diagram.snapshot,snapshot:diagram.snapshot}});
});
