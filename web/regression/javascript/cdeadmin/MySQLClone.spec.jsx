import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import MySQLClone from 'sources/Dialogs/MySQLClone';
import {withTheme} from '../fake_theme';
const Component=withTheme(MySQLClone);
const viewportHeight=window.innerHeight;
beforeAll(() => {window.innerHeight=1200;});
afterAll(() => {window.innerHeight=viewportHeight;});
const review={job_id:'job',review_digest:'digest',state:'reviewed',source:{server_uuid:'native-uuid'},
  warnings:['Native server directory'],options:{destination:'/server/Clone "ü"'},execution_host:{kind:'database-server'}};

it('reviews exact server paths and requires confirmation before starting a native clone',async () => {
  const post=jest.fn().mockResolvedValue(review);render(<Component post={post} />);
  fireEvent.change(screen.getByLabelText('Destination on database-server host'),{target:{value:'/server/Clone "ü"'}});
  fireEvent.change(screen.getByLabelText('Confirm exact destination'),{target:{value:'/server/Clone "ü"'}});
  fireEvent.change(screen.getByLabelText('Client timeout seconds (blank: no limit)'),{target:{value:''}});
  fireEvent.click(screen.getByRole('button',{name:'Review local clone'}));
  await screen.findByText('Native server directory');
  expect(post).toHaveBeenLastCalledWith({action:'mysql_clone_review',request:{options:{destination:'/server/Clone "ü"',confirmation:'/server/Clone "ü"',timeout_seconds:null}}});
  expect(screen.getByLabelText('Native clone review')).toHaveTextContent('native-uuid');
  post.mockResolvedValue({...review,state:'native_completed',files_verified:false,recovery_drill_complete:false});
  fireEvent.click(screen.getByRole('button',{name:'Confirm and start local clone'}));
  await screen.findByText(/File verification and recovery drill have separate receipts/);
  expect(post).toHaveBeenLastCalledWith({action:'mysql_clone_start',request:{job_id:'job',review_digest:'digest',confirmed:true}});
  expect(screen.getByRole('button',{name:'Confirm and start local clone'})).toBeDisabled();
});

it('loads offline receipts and exposes native reconciliation for an uncertain clone',async () => {
  const post=jest.fn().mockResolvedValue({jobs:[{...review,state:'unknown'}],total:1,unavailable_job_ids:[]});
  render(<Component post={post} />);fireEvent.click(screen.getByRole('button',{name:'Load clone jobs'}));
  await screen.findByRole('table',{name:'Native MySQL clone jobs'});
  post.mockResolvedValue({...review,state:'unknown'});fireEvent.click(screen.getByRole('button',{name:'Inspect clone job'}));
  await screen.findByText(/The server can still be copying/);
  expect(screen.getByRole('button',{name:'Cancel local clone'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'Reconcile native clone'}));
  await waitFor(() => expect(post).toHaveBeenLastCalledWith({action:'mysql_clone_reconcile',request:{job_id:'job'}}));
});

it('selects a registered donor and explicitly delegates its credentials with required TLS',async () => {
  const post=jest.fn().mockResolvedValue({donors:[{server_id:2,name:'Owned donor',host:'app-route',port:13306}],offset:0,limit:25,total:1});
  render(<Component post={post} />);
  fireEvent.click(screen.getByRole('button',{name:'Load registered donors'}));
  const select=await screen.findByLabelText('Clone source');fireEvent.mouseDown(select);
  fireEvent.click(await screen.findByRole('option',{name:'Owned donor'}));
  expect(screen.getByRole('button',{name:'Review remote clone'})).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Donor host reachable from recipient'),{target:{value:'native-donor'}});
  fireEvent.change(screen.getByLabelText('Donor TCP port'),{target:{value:'3306'}});
  fireEvent.click(screen.getByLabelText('Delegate registered donor credentials to recipient'));
  post.mockResolvedValue({...review,operation:'remote_clone',donor:{native_identity:{server_uuid:'donor-uuid'}}});
  fireEvent.click(screen.getByRole('button',{name:'Review remote clone'}));
  await screen.findByRole('button',{name:'Confirm and start remote clone'});
  expect(post).toHaveBeenLastCalledWith({action:'mysql_clone_review',request:{options:{destination:'',confirmation:'',timeout_seconds:3600,
    donor:{server_id:2,host:'native-donor',port:3306,require_ssl:true,delegate_credentials:true}}}});
  expect(screen.getByLabelText('Native clone review')).toHaveTextContent('donor-uuid');
});
