import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import PostgresqlLogicalStream from 'sources/Dialogs/PostgresqlLogicalStream';
import {startBrowserFileDownload} from 'sources/Dialogs/browserFileDownload';
import {withTheme} from '../fake_theme';
const Component=withTheme(PostgresqlLogicalStream),target='postgresql-database:123';
jest.mock('sources/Dialogs/browserFileDownload',() => ({startBrowserFileDownload:jest.fn(() => jest.fn())}));
const reviewed={job_id:'stream',state:'reviewed',review_digest:'digest',operation:'logical_stream_capture'};

it('preserves exact LSNs and ordered native options and confirms consumption separately',async () => {
  const post=jest.fn().mockResolvedValue(reviewed);render(<Component post={post} databaseTargetId={target} />);
  fireEvent.click(screen.getByText('PostgreSQL logical replication streams'));
  fireEvent.change(screen.getByLabelText('Logical receiver slot'),{target:{value:'native_slot'}});
  fireEvent.change(screen.getByLabelText('Logical receiver end lsn'),{target:{value:'FFFFFFFF/FFFFFFFF'}});
  fireEvent.click(screen.getByRole('button',{name:'Add ordered logical receiver option'}));
  fireEvent.change(screen.getByLabelText('Logical receiver option 1 name'),{target:{value:'publication_names'}});
  fireEvent.change(screen.getByLabelText('Logical receiver option 1 value'),{target:{value:'"Native publication ü"'}});
  fireEvent.click(screen.getByRole('button',{name:'Review logical replication stream'}));
  await screen.findByRole('button',{name:'Start reviewed logical stream'});
  expect(post).toHaveBeenCalledWith({action:'postgresql_continuity_review',request:{operation:'logical_stream_capture',database_target_id:target,options:{slot:'native_slot',start_lsn:'0/0',end_lsn:'FFFFFFFF/FFFFFFFF',plugin_options:[{name:'publication_names',value:'"Native publication ü"'}],status_interval_seconds:10,fsync_interval_seconds:1,timeout_seconds:null}}});
  expect(screen.getByRole('button',{name:'Start reviewed logical stream'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Confirm native logical stream consumption'));
  post.mockResolvedValue({...reviewed,state:'active'});fireEvent.click(screen.getByRole('button',{name:'Start reviewed logical stream'}));
  await screen.findByRole('button',{name:'Stop logical replication stream'});
  expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_start',request:{job_id:'stream',review_digest:'digest',confirmed:true}});
  expect(screen.getByRole('button',{name:'Stop logical replication stream'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Stop this native logical receiver'));post.mockResolvedValue({...reviewed,state:'cancelled'});
  fireEvent.click(screen.getByRole('button',{name:'Stop logical replication stream'}));
  await screen.findByRole('button',{name:'Seal retained logical stream bytes'});
  expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_cancel',request:{job_id:'stream'}});
});

it('opens interrupted bytes offline and uses streamed downloads without retrying the receiver',async () => {
  const captured={...reviewed,state:'unknown',logical_stream_artifact:{state:'sealed',bytes:'9007199254740993'}};
  const post=jest.fn(request => Promise.resolve(request.action.endsWith('_list') ? {jobs:[captured],more:false} : request.action.endsWith('_preview') ? {data_base64:'AID/',next_offset:'9007199254740993'} : captured));
  render(<Component post={post} databaseTargetId={target} endpointUrl="/owned/workspace" />);
  fireEvent.click(screen.getByText('PostgreSQL logical replication streams'));fireEvent.click(screen.getByRole('button',{name:'Load logical stream receipts'}));
  fireEvent.click(await screen.findByRole('button',{name:'Inspect logical stream stream'}));
  fireEvent.click(await screen.findByRole('button',{name:'Preview native logical bytes'}));await screen.findByLabelText('Native logical byte preview');
  fireEvent.click(screen.getByRole('button',{name:'Next native logical bytes'}));
  await waitFor(() => expect(post).toHaveBeenCalledWith({action:'postgresql_continuity_logical_stream_preview',request:{job_id:'stream',offset:'9007199254740993',limit:4096}}));
  fireEvent.click(screen.getByRole('button',{name:'Download native logical stream'}));
  expect(startBrowserFileDownload).toHaveBeenCalledWith('/owned/workspace',{job_id:'stream'},expect.objectContaining({action:'postgresql_continuity_logical_stream_download'}));
  expect(post.mock.calls.some(([request]) => request.action==='postgresql_continuity_start')).toBe(false);
});

it('continues polling after native return until the stopped file is sealed',async () => {
  const sealed={...reviewed,state:'captured',native_receiver_returned:true,logical_stream_artifact:{state:'sealed',bytes:'17'}};
  const post=jest.fn(request => Promise.resolve(request.action.endsWith('_review') ? reviewed : request.action.endsWith('_start') ? {...sealed,logical_stream_artifact:{state:'sealing'}} : sealed));
  render(<Component post={post} databaseTargetId={target} endpointUrl="/owned/workspace" />);
  fireEvent.click(screen.getByText('PostgreSQL logical replication streams'));
  fireEvent.change(screen.getByLabelText('Logical receiver slot'),{target:{value:'native_slot'}});
  fireEvent.click(screen.getByRole('button',{name:'Review logical replication stream'}));
  await screen.findByRole('button',{name:'Start reviewed logical stream'});
  fireEvent.click(screen.getByLabelText('Confirm native logical stream consumption'));
  fireEvent.click(screen.getByRole('button',{name:'Start reviewed logical stream'}));
  await screen.findByRole('button',{name:'Download native logical stream'});
  expect(post).toHaveBeenCalledWith({action:'postgresql_continuity_status',request:{job_id:'stream'}});
});

it('uses registered replication admission without loading a SQL catalog and clears private credentials on start',async () => {
  const job={...reviewed,source:{admission_interface:'logical-replication',database:'native'}};
  const post=jest.fn().mockResolvedValue(job);render(<Component post={post} />);
  fireEvent.click(screen.getByText('PostgreSQL logical replication streams'));
  fireEvent.click(screen.getByLabelText('Use registered logical replication database without SQL admission'));
  expect(screen.getByRole('button',{name:'Load logical stream databases'})).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Logical replication principal password'),{target:{value:'private database password'}});
  fireEvent.change(screen.getByLabelText('Logical receiver slot'),{target:{value:'known_slot'}});
  fireEvent.click(screen.getByRole('button',{name:'Review logical replication stream'}));
  await screen.findByRole('button',{name:'Start reviewed logical stream'});
  expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_review',request:expect.objectContaining({
    database_target_id:'registered-replication-database',replication_access:{password:'private database password'}})});
  fireEvent.click(screen.getByLabelText('Confirm native logical stream consumption'));
  post.mockResolvedValue({...job,state:'captured',logical_stream_artifact:{state:'sealed',bytes:'17'}});
  fireEvent.click(screen.getByRole('button',{name:'Start reviewed logical stream'}));
  await screen.findByRole('button',{name:'Preview native logical bytes'});
  expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_start',request:{job_id:'stream',review_digest:'digest',confirmed:true,replication_access:{password:'private database password'}}});
  expect(screen.getByLabelText('Logical replication principal password')).toHaveValue('');
  expect(post.mock.calls.some(([request]) => request.action==='postgresql_continuity_slot_databases')).toBe(false);
});
