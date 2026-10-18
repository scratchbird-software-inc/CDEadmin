import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import PostgresqlContinuity from 'sources/Dialogs/PostgresqlContinuity';
import {withTheme} from '../fake_theme';
const Component=withTheme(PostgresqlContinuity);
const reviewed={job_id:'native-job',review_digest:'native-digest',state:'reviewed',operation:'full_backup',
  source:{system_identifier:'18446744073709551615'},options:{format:'plain'},inputs:[],tool_identities:{},warnings:['Complete cluster backup']};
let originalHeight;
beforeEach(() => {originalHeight=window.innerHeight;window.innerHeight=1200;});
afterEach(() => {window.innerHeight=originalHeight;});

describe('PostgreSQL native continuity jobs',() => {
  it('does not start a backup until the displayed review is explicitly confirmed',async () => {
    const post=jest.fn().mockResolvedValue(reviewed);
    render(<Component post={post} />);
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
    await screen.findByText('Complete cluster backup');
    expect(post.mock.calls[0][0].action).toBe('postgresql_continuity_review');
    expect(screen.getByLabelText('Native backup review')).toHaveTextContent('18446744073709551615');
    post.mockResolvedValue({...reviewed,state:'verified',verification_scope:{files:true,wal:true},recovery_drill_complete:false});
    fireEvent.click(screen.getByRole('button',{name:'Confirm and start reviewed operation'}));
    await screen.findByText(/Recovery drill: not completed/);
    expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_start',request:{job_id:'native-job',review_digest:'native-digest',confirmed:true}});
    expect(screen.getByRole('button',{name:'Confirm and start reviewed operation'})).toBeDisabled();
  });
  it('loads offline receipts directly and never bootstraps a connected workspace',async () => {
    const post=jest.fn().mockResolvedValue({jobs:[{...reviewed,state:'unknown'}],total:1,unavailable_job_ids:[]});
    render(<Component post={post} />);
    fireEvent.click(screen.getByRole('button',{name:'Load backup jobs'}));
    await screen.findByRole('table',{name:'Native physical backup jobs'});
    expect(post).toHaveBeenCalledWith({action:'postgresql_continuity_list',request:{offset:0,limit:25}});
    post.mockResolvedValue({...reviewed,state:'unknown',observation_blocker:'Inspect the artifact before repeating'});
    fireEvent.click(screen.getByRole('button',{name:'Inspect backup native-job'}));
    await screen.findByText(/Inspect the artifact before repeating/, {selector:'.MuiAlert-message'});
    expect(screen.getByRole('button',{name:'Cancel native job'})).toBeDisabled();
  });
  it('drops the previous endpoint review and ignores its late response',async () => {
    let finish;
    const first=jest.fn(() => new Promise(resolve => {finish=resolve;}));
    const mounted=render(<Component post={first} />);
    fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
    mounted.rerender(<Component post={jest.fn()} />);
    finish(reviewed);
    await waitFor(() => expect(screen.getByRole('button',{name:'Review native operation'})).toBeEnabled());
    expect(screen.queryByText('Complete cluster backup')).not.toBeInTheDocument();
  });
  it('requires explicit writer cleanup confirmation and keeps an uncertain backup unverified',async () => {
    const post=jest.fn().mockResolvedValue({jobs:[{...reviewed,state:'unknown'}],total:1,unavailable_job_ids:[]});
    render(<Component post={post} />);
    fireEvent.click(screen.getByRole('button',{name:'Load backup jobs'}));
    await screen.findByRole('table',{name:'Native physical backup jobs'});
    post.mockResolvedValue({...reviewed,state:'unknown'});
    fireEvent.click(screen.getByRole('button',{name:'Inspect backup native-job'}));
    const reconcile=await screen.findByRole('button',{name:'Reconcile native writer'});
    expect(reconcile).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox',{name:'Confirm stopping this job\'s remaining native utilities'}));
    post.mockResolvedValue({...reviewed,state:'unknown',writer_reconciliation:{process_scope_stopped:true,artifact_verified:false}});
    fireEvent.click(reconcile);
    await screen.findByText('Owned native utilities are stopped. Backup verification and recovery retain separate receipts.');
    expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_reconcile_writer',request:{job_id:'native-job',confirmed:true}});
    expect(screen.getByRole('button',{name:'Reconcile native writer'})).toBeDisabled();
    expect(screen.queryByText(/Native file verification: yes/)).not.toBeInTheDocument();
  });
});

it('preserves an explicit no-deadline selection in native review',async () => {
  const post=jest.fn().mockResolvedValue(reviewed);
  render(<Component post={post} />);
  fireEvent.change(screen.getByLabelText('Timeout seconds (blank: no limit)'),{target:{value:''}});
  fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
  await screen.findByText('Complete cluster backup');
  expect(post.mock.calls[0][0].request.options.timeout_seconds).toBeNull();
});

it('reviews structured recovery counts without rounding int64 text',async () => {
  const post=jest.fn().mockResolvedValue({jobs:[{...reviewed,state:'verified'}],total:1,unavailable_job_ids:[]});
  render(<Component post={post} />);
  fireEvent.mouseDown(screen.getByLabelText('Continuity operation'));
  fireEvent.click(await screen.findByRole('option',{name:'Recover isolated backup copy'}));
  fireEvent.click(screen.getByRole('button',{name:'Load backup jobs'}));
  fireEvent.click(await screen.findByRole('button',{name:'Select input'}));
  fireEvent.click(screen.getByRole('button',{name:'Add recovery table check'}));
  fireEvent.change(screen.getByLabelText('table 1'),{target:{value:'Exact "😀"'}});
  fireEvent.change(screen.getByLabelText('expected rows 1'),{target:{value:'9007199254740993'}});
  post.mockResolvedValue({...reviewed,operation:'recovery_drill'});
  fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
  await screen.findByText('Complete cluster backup');
  expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_review',request:{operation:'recovery_drill',base_job_id:'native-job',options:{database:'postgres',checks:[{schema:'public',table:'Exact "😀"',expected_rows:'9007199254740993'}],timeout_seconds:3600}}});
  post.mockResolvedValue({...reviewed,state:'recovered',recovery_drill_complete:true,verification_scope:{selected_heap_counts:1}});
  fireEvent.click(screen.getByRole('button',{name:'Confirm and start reviewed operation'}));
  await screen.findByText(/Isolated native recovery completed/);
  expect(screen.getByRole('button',{name:'Cancel native job'})).toBeDisabled();
});

it('reviews a native restore point and the selected owner-scoped WAL archive',async () => {
  const post=jest.fn().mockResolvedValue({jobs:[{...reviewed,state:'verified'}],total:1,unavailable_job_ids:[]});
  render(<Component post={post} />);
  fireEvent.mouseDown(screen.getByLabelText('Continuity operation'));
  fireEvent.click(await screen.findByRole('option',{name:'Recover isolated backup copy'}));
  fireEvent.click(screen.getByRole('button',{name:'Load backup jobs'}));
  fireEvent.click(await screen.findByRole('button',{name:'Select input'}));
  fireEvent.mouseDown(screen.getByLabelText('Recovery target'));
  fireEvent.click(await screen.findByRole('option',{name:'Named restore point'}));
  fireEvent.change(screen.getByLabelText('Exact native target value'),{target:{value:'Exact ü \' restore point'}});
  post.mockResolvedValue({archives:['completed'],owner_endpoint_directory:'/owned/native/archives'});
  fireEvent.click(screen.getByRole('button',{name:'Load WAL archives'}));
  await screen.findByText(/Archive directory: \/owned\/native\/archives/);
  fireEvent.mouseDown(screen.getByLabelText('Native WAL archive'));
  fireEvent.click(await screen.findByRole('option',{name:'completed'}));
  post.mockResolvedValue({...reviewed,operation:'recovery_drill'});
  fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
  await screen.findByText('Complete cluster backup');
  expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_review',request:{operation:'recovery_drill',base_job_id:'native-job',
    options:{database:'postgres',checks:[],timeout_seconds:3600,wal_archive:'completed',target:{kind:'name',value:'Exact ü \' restore point',inclusive:true,timeline:'current'}}}});
  fireEvent.change(screen.getByLabelText('Exact native target value'),{target:{value:'new target'}});
  expect(screen.queryByRole('button',{name:'Confirm and start reviewed operation'})).not.toBeInTheDocument();
});
