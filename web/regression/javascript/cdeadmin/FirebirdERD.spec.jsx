import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import FirebirdERD from 'sources/Dialogs/FirebirdERD';
import {withTheme} from '../fake_theme';

jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({
  DDNViewerSurface: ({snapshot}) => <div data-testid="viewer">{snapshot.files['relations.ddn']}</div>,
  DDNDesignerSurface: ({snapshot, onChange, onReady}) => <div data-testid="designer" data-seed={snapshot.files['relations.ddn']}>
    <button onClick={() => onReady({snapshot: async () => ({...snapshot, files: {'relations.ddn': 'instant edit'}})})}>Edit before notification</button>
    <button onClick={() => onChange({...snapshot, files: {'relations.ddn': 'edited design'}})}>Change design</button>
  </div>,
}));

it('binds MariaDB graphical edits and temporal acceptance to its own target', async () => {
  const Component = withTheme(FirebirdERD);
  const snapshot = {format:'ddn-source-workspace@1', entry:'relations.ddn', view:'relations_1', files:{'relations.ddn':'native design'}};
  const post = jest.fn().mockResolvedValue({baseline:'before', desired:'after'}), onReview = jest.fn();
  render(<Component diagram={{snapshot, views:[]}} engine="mariadb" databaseTargetId="maria-target" post={post} onReview={onReview} />);
  fireEvent.click(screen.getByLabelText('Include graphical column renames'));
  fireEvent.click(screen.getByLabelText('Accept native KEEP-history semantics for temporal schema changes'));
  fireEvent.click(screen.getByText('Review relational metadata changes'));
  await waitFor(() => expect(onReview).toHaveBeenCalledWith({baseline:'before', desired:'after'}));
  expect(post).toHaveBeenCalledWith({action:'mariadb_relational_review', request:{database_target_id:'maria-target',
    original:snapshot, snapshot, allow_column_renames:true, allow_temporal_history:true}});
});

describe('Native relational DDN handoff', () => {
  const Component = withTheme(FirebirdERD);
  const diagram = {snapshot: {format: 'ddn-source-workspace@1', entry: 'relations.ddn', view: 'relations_1', files: {'relations.ddn': 'native design'}},
    views: [{id: 'relations_1', label: 'Native relations'}], warnings: ['Missing referenced object']};
  it('edits only the diagram draft, retains changes and keeps editor seed stable', async () => {
    render(<Component diagram={diagram} />);
    expect(screen.getByTestId('viewer')).toHaveTextContent('native design');
    expect(screen.getByText('Missing referenced object')).toBeVisible();
    fireEvent.click(screen.getByText('Edit relational diagram in DDN'));
    fireEvent.click(screen.getByText('Change design'));
    expect(screen.getByTestId('designer')).toHaveAttribute('data-seed', 'native design');
    fireEvent.click(screen.getByText('Return to diagram viewer'));
    expect(await screen.findByTestId('viewer')).toHaveTextContent('edited design');
    await waitFor(() => expect(screen.getAllByText('SR-F-001365')).toHaveLength(1));
  });
  it('awaits editor capture before a delayed change notification', async () => {
    render(<Component diagram={diagram} />);
    fireEvent.click(screen.getByText('Edit relational diagram in DDN'));
    fireEvent.click(screen.getByText('Edit before notification'));
    fireEvent.click(screen.getByText('Return to diagram viewer'));
    expect(await screen.findByTestId('viewer')).toHaveTextContent('instant edit');
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
    await screen.findByTestId('viewer');
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Review relational metadata changes'));
    await waitFor(() => expect(onReview).toHaveBeenCalledWith(value));
    expect(post).toHaveBeenCalledWith({action: 'firebird_relational_review', request: {
      generation: 'g', original: diagram.snapshot,
      snapshot: {...diagram.snapshot, files: {'relations.ddn': 'instant edit'}},
    }});
  });
  it('uses the paired designer and MySQL form identity without sending Firebird operations', async () => {
    const post = jest.fn();
    render(<Component diagram={diagram} engine="mysql" databaseTargetId="mysql-db" post={post} />);
    expect(screen.getByText('SR-F-001398')).toBeVisible();
    fireEvent.click(screen.getByText('Edit relational diagram in DDN'));
    fireEvent.click(screen.getByText('Change design'));
    fireEvent.click(screen.getByText('Return to diagram viewer'));
    expect(await screen.findByTestId('viewer')).toHaveTextContent('edited design');
    expect(post).not.toHaveBeenCalled();
    expect(screen.queryByText('Review relational metadata changes')).toBeNull();
  });

});

it('binds MySQL relational review to the registered database target without Firebird generation admission', async () => {
  const Component = withTheme(FirebirdERD);
  const diagram = {snapshot: {format:'ddn-source-workspace@1',entry:'relations.ddn',view:'relations_1',files:{'relations.ddn':'native design'}},views:[]};
  const post=jest.fn().mockResolvedValue({baseline:'before',desired:'after'}),onReview=jest.fn();
  render(<Component diagram={diagram} engine="mysql" databaseTargetId="mysql-target" post={post} onReview={onReview} />);
  fireEvent.click(screen.getByText('Review relational metadata changes'));
  await waitFor(() => expect(onReview).toHaveBeenCalledWith({baseline:'before',desired:'after'}));
  expect(post).toHaveBeenCalledWith({action:'mysql_relational_review',request:{database_target_id:'mysql-target',original:diagram.snapshot,snapshot:diagram.snapshot}});
});


it('admits new MySQL graphical columns only through the explicit review checkbox', async () => {
  const Component = withTheme(FirebirdERD);
  const diagram = {snapshot: {format:'ddn-source-workspace@1',entry:'relations.ddn',view:'relations_1',files:{'relations.ddn':'native design'}},views:[]};
  const post=jest.fn().mockResolvedValue({baseline:'before',desired:'after'}),onReview=jest.fn();
  render(<Component diagram={diagram} engine="mysql" databaseTargetId="mysql-target" post={post} onReview={onReview} />);
  expect(screen.getByLabelText('Include new graphical columns')).not.toBeChecked();
  fireEvent.click(screen.getByLabelText('Include new graphical columns'));
  fireEvent.click(screen.getByText('Review relational metadata changes'));
  await waitFor(() => expect(onReview).toHaveBeenCalled());
  expect(post).toHaveBeenCalledWith({action:'mysql_relational_review',request:{database_target_id:'mysql-target',allow_new_columns:true,original:diagram.snapshot,snapshot:diagram.snapshot}});
});


it('admits MySQL graphical renames only through its separate explicit checkbox', async () => {
  const Component=withTheme(FirebirdERD);
  const diagram={snapshot:{format:'ddn-source-workspace@1',entry:'relations.ddn',view:'relations_1',files:{'relations.ddn':'native design'}},views:[]};
  const post=jest.fn().mockResolvedValue({baseline:'before',desired:'after'}),onReview=jest.fn();
  render(<Component diagram={diagram} engine="mysql" databaseTargetId="mysql-target" post={post} onReview={onReview} />);
  expect(screen.getByLabelText('Include graphical column renames')).not.toBeChecked();
  fireEvent.click(screen.getByLabelText('Include graphical column renames'));
  fireEvent.click(screen.getByText('Review relational metadata changes'));
  await waitFor(() => expect(onReview).toHaveBeenCalled());
  expect(post).toHaveBeenCalledWith({action:'mysql_relational_review',request:{database_target_id:'mysql-target',allow_column_renames:true,original:diagram.snapshot,snapshot:diagram.snapshot}});
});


it('binds explicit foreign-key design admission to the selected MySQL database', async () => {
  const Component=withTheme(FirebirdERD);
  const diagram={snapshot:{format:'ddn-source-workspace@1',entry:'relations.ddn',view:'relations_1',files:{'relations.ddn':'native design'}},views:[]};
  const post=jest.fn().mockResolvedValue({baseline:'before',desired:'after'}),onReview=jest.fn();
  render(<Component diagram={diagram} engine="mysql" databaseTargetId="mysql-target" post={post} onReview={onReview} />);
  expect(screen.getByLabelText('Include foreign key design changes')).not.toBeChecked();
  fireEvent.click(screen.getByLabelText('Include foreign key design changes'));
  fireEvent.click(screen.getByText('Review relational metadata changes'));
  await waitFor(() => expect(onReview).toHaveBeenCalled());
  expect(post).toHaveBeenCalledWith({action:'mysql_relational_review',request:{database_target_id:'mysql-target',allow_foreign_keys:true,original:diagram.snapshot,snapshot:diagram.snapshot}});
});


it('awaits source capture before downloading an edited relational design', async () => {
  const Component=withTheme(FirebirdERD);
  const snapshot={format:'ddn-source-workspace@1',entry:'relations.ddn',view:'relations',files:{'relations.ddn':'native design'}};
  const create=jest.fn(()=> 'blob:owned-test');
  const previousCreate=URL.createObjectURL, previousRevoke=URL.revokeObjectURL;
  URL.createObjectURL=create;URL.revokeObjectURL=jest.fn();
  const click=jest.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
  try {
    render(<Component diagram={{snapshot,views:[]}} />);
    fireEvent.click(screen.getByText('Edit relational diagram in DDN'));
    fireEvent.click(screen.getByText('Edit before notification'));
    fireEvent.click(screen.getByText('Download edited design'));
    await waitFor(()=>expect(create).toHaveBeenCalledTimes(1));
    const text=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsText(create.mock.calls[0][0]);});
    expect(JSON.parse(text).files['relations.ddn']).toBe('instant edit');
  } finally {URL.createObjectURL=previousCreate;URL.revokeObjectURL=previousRevoke;click.mockRestore();}
});
