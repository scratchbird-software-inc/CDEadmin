import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import MySQLRetentionSchedule from 'sources/Dialogs/MySQLRetentionSchedule';
import {withTheme} from '../fake_theme';

const Component=withTheme(MySQLRetentionSchedule);
const source={job_id:'anchor',state:'completed',source:{server_uuid:'native-uuid',authenticated_principal:'archive@%',active_role:'NONE'}};
const plan={job_id:'policy',review_digest:'exact-policy',state:'reviewed',warnings:['Future archives are included']};

it('requires a retained source and separate acknowledgement of future removal authority',async () => {
  const post=jest.fn().mockResolvedValue(plan),onOccurrence=jest.fn();
  const {rerender}=render(<Component post={post} prefix="mysql_raw_binlog_" days={30} keep={2} onOccurrence={onOccurrence} />);
  expect(screen.getByRole('button',{name:'Review scheduled retention policy'})).toBeDisabled();
  rerender(<Component post={post} prefix="mysql_raw_binlog_" days={30} keep={2} sourceArchive={source} onOccurrence={onOccurrence} />);
  fireEvent.click(screen.getByText('Scheduled archive retention'));
  fireEvent.click(screen.getByRole('button',{name:'Review scheduled retention policy'}));
  await screen.findByText('Future archives are included');
  expect(post).toHaveBeenLastCalledWith({action:'mysql_raw_binlog_retention_schedule_review',request:{anchor_job_id:'anchor',options:{policy:{retention_days:30,keep_latest:2},interval_seconds:3600,expires_after_days:30}}});
  expect(screen.getByRole('button',{name:'Confirm and enable scheduled retention'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Authorize future archive removal under this reviewed policy'));
  post.mockResolvedValue({...plan,state:'enabled'});fireEvent.click(screen.getByRole('button',{name:'Confirm and enable scheduled retention'}));
  await screen.findByLabelText('Scheduled retention receipt');
  expect(post).toHaveBeenLastCalledWith({action:'mysql_raw_binlog_retention_schedule_enable',request:{job_id:'policy',review_digest:'exact-policy',confirmed:true}});
  post.mockResolvedValue({...plan,state:'disabled'});fireEvent.click(screen.getByRole('button',{name:'Disable scheduled retention'}));
  await waitFor(() => expect(screen.getByRole('button',{name:'Scan archive policy now'})).toBeDisabled());
  expect(post).toHaveBeenLastCalledWith({action:'mysql_raw_binlog_retention_schedule_disable',request:{job_id:'policy',confirmed:true}});
});

it('clears a future-removal review when the policy, source or archive kind changes',async () => {
  const post=jest.fn().mockResolvedValue(plan),onOccurrence=jest.fn();
  const props={post,prefix:'mysql_binlog_',days:30,keep:1,sourceArchive:source,onOccurrence};
  const {rerender}=render(<Component {...props} />);
  fireEvent.click(screen.getByText('Scheduled archive retention'));
  fireEvent.click(screen.getByRole('button',{name:'Review scheduled retention policy'}));
  await screen.findByLabelText('Scheduled retention review');
  rerender(<Component {...props} keep={3} />);
  expect(screen.queryByLabelText('Scheduled retention review')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Review scheduled retention policy'}));
  await screen.findByLabelText('Scheduled retention review');
  rerender(<Component {...props} prefix="mysql_raw_binlog_" />);
  expect(screen.queryByLabelText('Scheduled retention review')).not.toBeInTheDocument();
});
