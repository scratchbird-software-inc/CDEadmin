import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import SQLiteCaptureExports from 'sources/Dialogs/SQLiteCaptureExports';
import {startBrowserFileDownload} from 'sources/Dialogs/browserFileDownload';
import {withTheme} from '../fake_theme';

jest.mock('sources/Dialogs/browserFileDownload',() => ({startBrowserFileDownload:jest.fn(() => jest.fn())}));
const Component=withTheme(SQLiteCaptureExports);
const reviewed={job_id:'owned-job',state:'reviewed',review_digest:'review-hash',source:{studio_session_id:'query',capture_id:'capture'},warnings:[]};

it('confirms the exact review and retains offline artifact downloads after the query connection closes',async () => {
  const post=jest.fn().mockResolvedValue(reviewed);
  const props={post,databaseTargetId:'file',endpointUrl:'/owned/workspace',sessionId:'query',captureId:'capture'};
  const {rerender}=render(<Component {...props} />);
  fireEvent.click(screen.getByText('SQLite capture exports and receipts'));
  fireEvent.change(screen.getByLabelText('Capture export maximum seconds'),{target:{value:'45'}});
  fireEvent.click(screen.getByRole('button',{name:'Review native capture export'}));
  await screen.findByRole('button',{name:'Start reviewed capture export'});
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_capture_export_review',request:{database_target_id:'file',session_id:'query',capture_id:'capture',kind:'changeset',timeout_seconds:45}});
  expect(screen.getByRole('button',{name:'Start reviewed capture export'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Confirm the reviewed native capture export'));
  post.mockResolvedValue({...reviewed,state:'completed',native_returned:true,native_returned_bytes:'9007199254740993'});
  fireEvent.click(screen.getByRole('button',{name:'Start reviewed capture export'}));
  await screen.findByRole('button',{name:'Load verified capture files'});
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_capture_export_start',request:{database_target_id:'file',job_id:'owned-job',review_digest:'review-hash',confirmed:true}});
  rerender(<Component {...props} sessionId={null} captureId={null} />);
  expect(screen.getByRole('button',{name:'Review native capture export'})).toBeDisabled();
  post.mockResolvedValue({files:[{path:'capture.changeset',size:'9007199254740993'}],offset:0,more:false});
  fireEvent.click(screen.getByRole('button',{name:'Load verified capture files'}));
  fireEvent.click(await screen.findByRole('button',{name:'Download capture.changeset'}));
  expect(startBrowserFileDownload).toHaveBeenLastCalledWith('/owned/workspace',{database_target_id:'file',job_id:'owned-job',path:'capture.changeset'},
    {action:'sqlite_capture_export_download',prefix:'sqlite-capture',title:'SQLite native capture download'});
});

it('invalidates an unconsumed review when its capture changes and scopes receipt pages to the selected file',async () => {
  const post=jest.fn().mockResolvedValue(reviewed),props={post,databaseTargetId:'file',sessionId:'query',captureId:'capture'};
  const {rerender}=render(<Component {...props} />);
  fireEvent.click(screen.getByText('SQLite capture exports and receipts'));
  fireEvent.click(screen.getByRole('button',{name:'Review native capture export'}));
  await screen.findByRole('button',{name:'Start reviewed capture export'});
  rerender(<Component {...props} captureId="another-capture" />);
  await waitFor(() => expect(screen.queryByRole('button',{name:'Start reviewed capture export'})).not.toBeInTheDocument());
  post.mockResolvedValue({jobs:[],offset:0,more:false});
  fireEvent.click(screen.getByRole('button',{name:'Load capture export receipts'}));
  await waitFor(() => expect(post).toHaveBeenLastCalledWith({action:'sqlite_capture_export_list',request:{database_target_id:'file',offset:0,limit:25}}));
});
