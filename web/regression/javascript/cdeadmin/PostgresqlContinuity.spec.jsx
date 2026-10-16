import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import PostgresqlContinuity from 'sources/Dialogs/PostgresqlContinuity';
import {withTheme} from '../fake_theme';
const Component=withTheme(PostgresqlContinuity);
const reviewed={job_id:'native-job',review_digest:'native-digest',state:'reviewed',operation:'full_backup',
  source:{system_identifier:'18446744073709551615'},options:{format:'plain'},inputs:[],tool_identities:{},warnings:['Complete cluster backup']};

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
});

it('preserves an explicit no-deadline selection in native review',async () => {
  const post=jest.fn().mockResolvedValue(reviewed);
  render(<Component post={post} />);
  fireEvent.change(screen.getByLabelText('Timeout seconds (blank: no limit)'),{target:{value:''}});
  fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
  await screen.findByText('Complete cluster backup');
  expect(post.mock.calls[0][0].request.options.timeout_seconds).toBeNull();
});
