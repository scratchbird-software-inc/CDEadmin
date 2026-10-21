import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import MySQLHost from 'sources/Dialogs/MySQLHost';
import {withTheme} from '../fake_theme';

const Component=withTheme(MySQLHost);
const review={job_id:'host-job',review_digest:'exact',state:'reviewed',warnings:['Native database host only'],source:{server_uuid:'native'},
  execution_host:{kind:'database-server-ssh-host',hostname:'database'},remote_observation:{},
  options:{connection:{host:'database',port:22,username:'operator',host_key:'expected',authentication:'password',platform:'posix',python:'python3'}}};

it('separates SSH secrets from review facts and requires exact native host confirmation',async () => {
  const post=jest.fn().mockResolvedValue(review);render(<Component post={post} />);
  fireEvent.change(screen.getByLabelText('SSH password'),{target:{value:'native-private-secret'}});
  fireEvent.click(screen.getByRole('button',{name:'Review native host configuration check'}));
  await screen.findByLabelText('Native host diagnostic review');
  expect(screen.getByLabelText('Native host diagnostic review')).not.toHaveTextContent('native-private-secret');
  expect(screen.getByRole('button',{name:'Confirm native host configuration check'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Authorize the reviewed native mysqld configuration check on this database SSH host'));
  post.mockResolvedValue({...review,state:'native_process_returned',remote_receipt:{result:{return_code:0}}});
  fireEvent.click(screen.getByRole('button',{name:'Confirm native host configuration check'}));
  await screen.findByText(/Native host job host-job: native_process_returned/);
  expect(post).toHaveBeenLastCalledWith({action:'mysql_host_start',request:{job_id:'host-job',review_digest:'exact',confirmed:true,credentials:{password:'native-private-secret'}}});
  fireEvent.change(screen.getByLabelText('Native mysqld executable'),{target:{value:'/different/mysqld'}});
  expect(screen.queryByLabelText('Native host diagnostic review')).not.toBeInTheDocument();
});

it('loads an uncertain offline receipt and reconciles without issuing another native command',async () => {
  const post=jest.fn().mockResolvedValue({jobs:[{...review,state:'unknown'}],total:1,offset:0});render(<Component post={post} />);
  fireEvent.click(screen.getByRole('button',{name:'Load native host receipts'}));
  await screen.findByRole('table',{name:'Native host diagnostic receipts'});
  post.mockResolvedValue({...review,state:'unknown'});fireEvent.click(screen.getByRole('button',{name:'Inspect native host job host-job'}));
  await screen.findByText(/original SSH reply is unconfirmed/);
  fireEvent.change(screen.getByLabelText('SSH password'),{target:{value:'renewed-native-secret'}});
  fireEvent.click(screen.getByRole('button',{name:'Reconcile native host receipt'}));
  await waitFor(() => expect(post).toHaveBeenLastCalledWith({action:'mysql_host_reconcile',request:{job_id:'host-job',credentials:{password:'renewed-native-secret'}}}));
  expect(post.mock.calls.some(([value])=>value.action==='mysql_host_start')).toBe(false);
});
