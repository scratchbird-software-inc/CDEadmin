import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {TextDecoder} from 'util';
import {Buffer} from 'buffer';
import FirebirdSchemaPlan from 'sources/Dialogs/FirebirdSchemaPlan';
import {withTheme} from '../fake_theme';

describe('Firebird structured schema preview', () => {
  const Component = withTheme(FirebirdSchemaPlan);
  let decoder;
  beforeEach(() => {decoder = global.TextDecoder; global.TextDecoder = TextDecoder;});
  afterEach(() => {global.TextDecoder = decoder;});
  const read = async () => {
    fireEvent.change(screen.getByLabelText('Desired DDN file'), {target: {files: [
      {name: 'desired.ddn', size: 7, arrayBuffer: async () => Buffer.from('desired')},
    ]}});
    await screen.findByText('desired.ddn');
  };
  it('retains the relational original baseline for the ordinary explicit preview path', async () => {
    const post = jest.fn().mockResolvedValue({status: 'no-op', blockers: [], operations: [], warnings: [], statistics: {}});
    render(<Component post={post} generation="g" baseline="live catalog"
      designRequest={{baseline: 'original relational facts', desired: 'edited relational facts'}} />);
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Preview native changes'));
    await waitFor(() => expect(post).toHaveBeenCalledWith({action: 'firebird_schema_plan', request: {
      generation: 'g', baseline: 'original relational facts', desired: 'edited relational facts', refresh: true,
    }}));
  });
  it('requires both documents and only requests a preview on an explicit click', async () => {
    const post = jest.fn().mockResolvedValue({status: 'review-ready', engine_version: '5.0.4',
      blockers: [], operations: [{resource_id: 'sequence:S', operation: 'alter', statements: ['ALTER SEQUENCE "S" INCREMENT BY 2']}],
      statistics: {unchanged: 2}, warnings: ['Preview does not execute SQL.'], script: 'review sql'});
    const refresh = jest.fn();
    render(<Component post={post} generation="current" baseline="baseline" onCatalogRefresh={refresh} />);
    expect(screen.getByText('SR-F-001371')).toBeVisible();
    expect(screen.getByRole('button', {name: 'Preview native changes'})).toBeDisabled();
    await read();
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: 'Preview native changes'}));
    await screen.findByText('ALTER SEQUENCE "S" INCREMENT BY 2');
    expect(post).toHaveBeenCalledWith({action: 'firebird_schema_plan', request: {
      generation: 'current', baseline: 'baseline', desired: 'desired', refresh: true,
    }});
    expect(refresh).toHaveBeenCalled();
    expect(screen.getByRole('button', {name: 'Download review SQL'})).toBeEnabled();
    expect(screen.queryByRole('button', {name: /^apply/i})).toBeNull();
  });
  it('shows deferred constraints as a final phase before application', async () => {
    const post = jest.fn().mockResolvedValue({status: 'review-ready', engine_version: '5.0.4',
      blockers: [], operations: [{resource_id: 'table:T', operation: 'create',
        statements: ['CREATE TABLE "T" (ID INTEGER)'],
        deferred_statements: ['ALTER TABLE "T" ADD CONSTRAINT "FK" FOREIGN KEY (ID) REFERENCES "P" (ID)']}],
      statistics: {}, warnings: [], script: 'complete two-phase script'});
    render(<Component post={post} generation="current" baseline="baseline" />);
    await read();
    fireEvent.click(screen.getByRole('button', {name: 'Preview native changes'}));
    await screen.findByText(/Final definition phase.*after primary definitions/);
    expect(screen.getByText(/ALTER TABLE "T" ADD CONSTRAINT "FK"/)).toBeVisible();
    expect(post).toHaveBeenCalledTimes(1);
  });
  it('requires explicit confirmation and retrieves a lost-response receipt without replaying', async () => {
    const plan = {status: 'review-ready', engine_version: '5.0.4', blockers: [], operations: [],
      statistics: {}, warnings: [], script: 'review sql', execution_sha256: 'execution', target: {database_target_id: 'target'}};
    const review = {review_id: 'receipt', review_digest: 'digest', state: 'reviewed', database: 'db.fdb', plan};
    const post = jest.fn().mockResolvedValueOnce(plan).mockResolvedValueOnce(review)
      .mockRejectedValueOnce(new Error('Response lost'))
      .mockResolvedValueOnce({...review, state: 'native_commit_returned'});
    render(<Component post={post} generation="current" baseline="baseline" />);
    await read();
    fireEvent.click(screen.getByRole('button', {name: 'Preview native changes'}));
    fireEvent.click(await screen.findByRole('button', {name: 'Prepare application'}));
    const apply = await screen.findByRole('button', {name: 'Apply reviewed changes'});
    expect(apply).toBeDisabled();
    fireEvent.click(screen.getByLabelText('I have reviewed these changes and authorize applying them to this database'));
    expect(apply).toBeEnabled();
    fireEvent.click(apply);
    await screen.findByText('Response lost');
    expect(screen.queryByRole('button', {name: 'Apply reviewed changes'})).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'Retrieve application receipt'}));
    await screen.findByText(/Application state.*native_commit_returned/);
    expect(post.mock.calls.filter(([value]) => value.action === 'firebird_schema_apply')).toHaveLength(1);
    expect(post).toHaveBeenLastCalledWith({action: 'firebird_schema_receipt', request: {
      review_id: 'receipt', database_target_id: 'target',
    }});
  });
  it('shows privilege additions and removals separately from generated SQL', async () => {
    const post = jest.fn().mockResolvedValue({status: 'review-ready', engine_version: '5.0.4',
      blockers: [], operations: [{resource_id: 'role:R', operation: 'alter',
        statements: ['ALTER ROLE "R" SET SYSTEM PRIVILEGES TO READ_RAW_PAGES'],
        security_changes: {added_system_privileges: ['READ_RAW_PAGES'],
          removed_system_privileges: ['MONITOR_ANY_ATTACHMENT'], ownership: 'preserve',
          memberships: 'preserve; not changed by this plan'},
        permissions: 'Native role authority required'}],
      statistics: {}, warnings: [], script: 'review sql'});
    render(<Component post={post} generation="current" baseline="baseline" />);
    await read();
    fireEvent.click(screen.getByRole('button', {name: 'Preview native changes'}));
    await screen.findByText('System privileges added: READ_RAW_PAGES');
    expect(screen.getByText('System privileges removed: MONITOR_ANY_ATTACHMENT')).toBeInTheDocument();
    expect(screen.getByText('Memberships: preserve; not changed by this plan')).toBeInTheDocument();
    expect(screen.getByText('Required authority: Native role authority required')).toBeInTheDocument();
    expect(screen.queryByRole('button', {name: /^apply/i})).toBeNull();
  });
  it('shows blockers and never offers SQL download for a blocked plan', async () => {
    const post = jest.fn().mockResolvedValue({status: 'blocked', engine_version: '5.0.4',
      blockers: [{resource_id: 'sequence:S', reason: 'Competing changes', fields: ['increment']}],
      operations: [], statistics: {}, warnings: [], script: null});
    const {rerender} = render(<Component post={post} generation="current" baseline="baseline" />);
    await read();
    fireEvent.click(screen.getByRole('button', {name: 'Preview native changes'}));
    await screen.findByText('Competing changes increment');
    expect(screen.queryByRole('button', {name: 'Download review SQL'})).toBeNull();
    expect(screen.getByRole('button', {name: 'Download review plan'})).toBeEnabled();
    rerender(<Component post={post} generation="current" baseline="replacement baseline" />);
    await waitFor(() => expect(screen.queryByText('Competing changes increment')).toBeNull());
    expect(screen.getByRole('button', {name: 'Preview native changes'})).toBeDisabled();
  });
  it('clears the prior plan when preview fails', async () => {
    const post = jest.fn().mockRejectedValue(new Error('Generation changed'));
    render(<Component post={post} generation="current" baseline="baseline" />);
    await read();
    fireEvent.click(screen.getByRole('button', {name: 'Preview native changes'}));
    await screen.findByText('Generation changed');
    expect(screen.queryByRole('button', {name: 'Download review SQL'})).toBeNull();
  });
});
