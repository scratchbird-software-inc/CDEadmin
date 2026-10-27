import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import Controlled, {MySQLAlterPolicy} from 'sources/Dialogs/MySQLControlledChange';
import {withTheme} from '../fake_theme';
const Component=withTheme(Controlled),Policy=withTheme(MySQLAlterPolicy);
const viewport=window.innerHeight;
beforeAll(() => {window.innerHeight=1200;});
afterAll(() => {window.innerHeight=viewport;});
const execution={method:'native',algorithm:'INPLACE',lock:'NONE',lock_wait_seconds:5,timeout_seconds:30};
const receipt={review_id:'review',review_digest:'exact-review',state:'reviewed',plan:{operations:[{execution}]}};

describe('controlled MySQL DDN execution',() => {
  it('binds explicit execution to the exact reviewed token and registered database',async () => {
    const post=jest.fn().mockResolvedValue({...receipt,state:'unknown_outcome',controlled_job:{state:'running'}}),onReceipt=jest.fn();
    const mounted=render(<Component post={post} databaseTargetId="target" review={receipt} confirmed={false} onReceipt={onReceipt} />);
    expect(post).not.toHaveBeenCalled();expect(screen.getByRole('button',{name:'Start controlled ALTER'})).toBeDisabled();
    mounted.rerender(<Component post={post} databaseTargetId="target" review={receipt} confirmed onReceipt={onReceipt} />);
    fireEvent.click(screen.getByRole('button',{name:'Start controlled ALTER'}));
    await waitFor(() => expect(onReceipt).toHaveBeenCalledTimes(1));
    expect(post).toHaveBeenCalledWith({action:'mysql_online_ddl_start',request:{database_target_id:'target',review_id:'review',review_digest:'exact-review',confirmed:true}});
  });

  it('changes native INSTANT to its required DEFAULT lock and invalidates the policy explicitly',async () => {
    const onChange=jest.fn();render(<Policy value={execution} onChange={onChange} />);
    fireEvent.mouseDown(screen.getByRole('combobox',{name:'Native ALTER algorithm'}));
    fireEvent.click(await screen.findByRole('option',{name:'INSTANT'}));
    expect(onChange).toHaveBeenCalledWith({...execution,algorithm:'INSTANT',lock:'DEFAULT'});
  });

  it('requires a separate cutover action for a native utility copy',async () => {
    const review={...receipt,state:'unknown_outcome',controlled_job:{state:'running',copy_stage:'cutover-waiting'}};
    const post=jest.fn().mockResolvedValue(review),onReceipt=jest.fn();
    render(<Component post={post} databaseTargetId="target" review={review} onReceipt={onReceipt} />);
    expect(post).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'Allow reviewed copy cutover'}));
    await waitFor(() => expect(onReceipt).toHaveBeenCalled());
    expect(post).toHaveBeenCalledWith({action:'mysql_online_ddl_cutover',request:{database_target_id:'target',review_id:'review'}});
  });

  it('does not interpret cancellation as rollback or enable a second dispatch',async () => {
    const review={...receipt,state:'unknown_outcome',controlled_job:{state:'running',events:[]}};
    const post=jest.fn().mockResolvedValue({...review,controlled_job:{state:'running',cancel_requested:true}}),onReceipt=jest.fn();
    render(<Component post={post} databaseTargetId="target" review={review} onReceipt={onReceipt} />);
    expect(screen.getByRole('button',{name:'Start controlled ALTER'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button',{name:'Cancel controlled ALTER'}));
    await waitFor(() => expect(onReceipt).toHaveBeenCalled());
    expect(post.mock.calls[0][0].action).toBe('mysql_online_ddl_cancel');
    expect(screen.getByText(/does not establish rollback/)).toBeVisible();
  });

  it('discards late private receipt responses after target replacement',async () => {
    let resolve;
    const post=jest.fn().mockImplementation(() => new Promise(reply => {resolve=reply;})),onReceipt=jest.fn();
    const mounted=render(<Component post={post} databaseTargetId="first" review={receipt} confirmed onReceipt={onReceipt} />);
    fireEvent.click(screen.getByRole('button',{name:'Start controlled ALTER'}));
    mounted.rerender(<Component post={post} databaseTargetId="second" review={null} confirmed={false} onReceipt={onReceipt} />);
    await act(async () => {resolve(receipt);});expect(onReceipt).not.toHaveBeenCalled();
  });
});

it('preserves native algorithm refusal diagnostics without offering a fallback or retry',() => {
  const review={...receipt,state:'unknown_outcome',controlled_terminal:true,controlled_job:{state:'terminal'},outcome:{error_code:1846,sqlstate:'0A000'}};
  render(<Component post={jest.fn()} databaseTargetId="target" review={review} onReceipt={jest.fn()} />);
  expect(screen.getByText(/Native MySQL error 1846; SQLSTATE 0A000/)).toBeVisible();
  expect(screen.getByRole('button',{name:'Start controlled ALTER'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'Observe current native table'})).toBeEnabled();
});
