import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import FirebirdEDSPool from '../../../pgadmin/static/js/Dialogs/FirebirdEDSPool';

const reviewed={review_id:'owned-review',review_digest:'owned-digest',state:'reviewed',
  source:'ALTER EXTERNAL CONNECTIONS POOL SET SIZE 31',native_before:{server_process_id:'123'},
  native_acknowledged:false,warnings:['This native setting survives rollback.']};
function setup(post,extra={}) {
  const props={post,databaseTargetId:'owned-target',sessionId:'original',ensureSession:jest.fn(),onBusyChange:jest.fn(),onBlocked:jest.fn(),...extra};
  const result=render(<FirebirdEDSPool {...props}/>);
  fireEvent.click(screen.getByText('Firebird external connection pool'));
  return {...result,props};
}
async function review() {
  fireEvent.change(screen.getByLabelText('Native EDS pool quantity'),{target:{value:'31'}});
  fireEvent.click(screen.getByRole('button',{name:'Review native EDS pool change'}));
  await screen.findByLabelText('Reviewed Firebird EDS SQL');
}
function confirm() {
  fireEvent.change(screen.getByLabelText('Confirm native EDS engine process ID'),{target:{value:'123'}});
  fireEvent.click(screen.getByRole('checkbox'));
}

it('binds typed options, original attachment and explicit process confirmation',async () => {
  const post=jest.fn().mockResolvedValueOnce(reviewed).mockResolvedValueOnce({...reviewed,state:'acknowledged',native_acknowledged:true});
  const {props}=setup(post);await review();
  expect(post).toHaveBeenLastCalledWith({action:'firebird_eds_pool',database_target_id:'owned-target',session_id:'original',
    request:{operation:'review',draft:{action:'set_size',value:31}}});
  const apply=screen.getByRole('button',{name:'Apply reviewed EDS change once'});
  expect(apply).toBeDisabled();confirm();fireEvent.click(apply);
  await waitFor(() => expect(screen.getByText(/Native EDS change: acknowledged/)).toBeVisible());
  expect(post).toHaveBeenLastCalledWith({action:'firebird_eds_pool',database_target_id:'owned-target',session_id:'original',
    request:{operation:'apply',review_id:'owned-review',review_digest:'owned-digest',confirmation:'123',confirmed:true}});
  expect(props.ensureSession).not.toHaveBeenCalled();
  expect(screen.getByText('SR-F-010012')).toBeVisible();
});

it('opens one attachment before inspection and ignores results from a changed registration',async () => {
  let resolve;const post=jest.fn(() => new Promise(done => {resolve=done;}));
  const ensureSession=jest.fn().mockResolvedValue('opened-once');
  const {rerender,props}=setup(post,{sessionId:null,ensureSession});
  fireEvent.click(screen.getByRole('button',{name:'Inspect native EDS pool'}));
  await waitFor(() => expect(post).toHaveBeenCalled());
  expect(post.mock.calls[0][0].session_id).toBe('opened-once');
  rerender(<FirebirdEDSPool {...props} databaseTargetId="other"/>);
  await act(async () => resolve({native_pool:{size:'32'}}));
  expect(screen.queryByLabelText('Native Firebird EDS pool')).not.toBeInTheDocument();
  expect(ensureSession).toHaveBeenCalledTimes(1);
});

it('loses no receipt identity after an apply response is lost and never retries automatically',async () => {
  const post=jest.fn().mockResolvedValueOnce(reviewed).mockRejectedValueOnce(new Error('Owned lost reply'))
    .mockResolvedValueOnce({...reviewed,state:'unknown_outcome',native_dispatch_admitted:true});
  setup(post);await review();confirm();fireEvent.click(screen.getByRole('button',{name:'Apply reviewed EDS change once'}));
  await screen.findByText('Owned lost reply');
  expect(screen.getByRole('button',{name:'Review native EDS pool change'})).toBeDisabled();
  expect(post).toHaveBeenCalledTimes(2);
  fireEvent.click(screen.getByRole('button',{name:'Read native EDS receipt'}));
  await screen.findByText(/Native EDS change: unknown_outcome/);
  expect(post.mock.calls[2][0].request.operation).toBe('receipt');
  expect(screen.queryByRole('button',{name:'Apply reviewed EDS change once'})).not.toBeInTheDocument();
});

it('reads archives and bounded pages without opening any native attachment or offering replay',async () => {
  const post=jest.fn().mockResolvedValueOnce({receipts:[reviewed],offset:0,more:true})
    .mockResolvedValueOnce({...reviewed,archived_read_only:true})
    .mockResolvedValueOnce({receipts:[],offset:25,more:false});
  const {props}=setup(post,{sessionId:null,disabled:true});
  fireEvent.click(screen.getByRole('button',{name:'Load retained EDS receipts'}));
  fireEvent.click(await screen.findByRole('button',{name:'Inspect EDS receipt owned-review'}));
  await screen.findByLabelText('Reviewed Firebird EDS SQL');
  expect(screen.queryByRole('button',{name:'Apply reviewed EDS change once'})).not.toBeInTheDocument();
  expect(props.ensureSession).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Next EDS receipt page'}));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(3));
  expect(post.mock.calls[2][0]).toEqual({action:'firebird_eds_pool_receipts',database_target_id:'owned-target',request:{operation:'list',offset:25,limit:25}});
});

it('invalidates process confirmation when the original native attachment changes',async () => {
  const post=jest.fn().mockResolvedValue(reviewed);const {rerender,props}=setup(post);await review();confirm();
  rerender(<FirebirdEDSPool {...props} sessionId="another"/>);
  expect(screen.queryByRole('button',{name:'Apply reviewed EDS change once'})).not.toBeInTheDocument();
  expect(screen.getByText(/original native attachment changed/)).toBeVisible();
  expect(post).toHaveBeenCalledTimes(1);
});

it('does not block or unlock the current attachment when reading an older cleanup failure',async () => {
  const saved={...reviewed,archived_read_only:true,state:'acknowledged',session_reuse_blocked:true};
  const post=jest.fn().mockResolvedValueOnce({receipts:[saved],offset:0,more:false}).mockResolvedValueOnce(saved);
  const {props}=setup(post);fireEvent.click(screen.getByRole('button',{name:'Load retained EDS receipts'}));
  fireEvent.click(await screen.findByRole('button',{name:'Inspect EDS receipt owned-review'}));
  await screen.findByLabelText('Reviewed Firebird EDS SQL');
  expect(props.onBusyChange).not.toHaveBeenCalled();expect(props.onBlocked).not.toHaveBeenCalled();
  expect(screen.getByRole('button',{name:'Inspect native EDS pool'})).toBeEnabled();
});

it('requires the archived receipt identity before removing completed local evidence',async () => {
  const saved={...reviewed,state:'acknowledged',archived_read_only:true,last_native_phase:'session_release',native_dispatch_admitted:true};
  const post=jest.fn().mockResolvedValueOnce({receipts:[saved],offset:0,more:false}).mockResolvedValueOnce(saved)
    .mockResolvedValueOnce({removed_review_id:'owned-review',native_operation_requested:false});
  setup(post,{sessionId:null});fireEvent.click(screen.getByRole('button',{name:'Load retained EDS receipts'}));
  fireEvent.click(await screen.findByRole('button',{name:'Inspect EDS receipt owned-review'}));
  const remove=await screen.findByRole('button',{name:'Remove retained EDS receipt'});expect(remove).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Confirm EDS receipt ID for removal'),{target:{value:'owned-review'}});fireEvent.click(remove);
  await waitFor(() => expect(screen.queryByLabelText('Firebird EDS operation receipt')).not.toBeInTheDocument());
  expect(post.mock.calls[2][0]).toEqual({action:'firebird_eds_pool_receipts',database_target_id:'owned-target',
    request:{operation:'remove',review_id:'owned-review',review_digest:'owned-digest',confirmed:true}});
});

it('allows cancellation while global controls are busy and reports cleanup uncertainty',async () => {
  const running={...reviewed,state:'unknown_outcome',native_operation_running:true};
  const post=jest.fn().mockResolvedValueOnce(reviewed).mockResolvedValueOnce(running)
    .mockResolvedValueOnce({...running,native_operation_running:false,session_reuse_blocked:true});
  const {props}=setup(post);await review();confirm();fireEvent.click(screen.getByRole('button',{name:'Apply reviewed EDS change once'}));
  const cancel=await screen.findByRole('button',{name:'Cancel active EDS command'});
  await waitFor(() => expect(cancel).toBeEnabled());
  fireEvent.click(cancel);await waitFor(() => expect(props.onBlocked).toHaveBeenCalledTimes(1));
  expect(post.mock.calls[2][0].request.operation).toBe('cancel');
});
