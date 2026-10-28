import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import SQLiteRetainedSchema from 'sources/Dialogs/SQLiteRetainedSchema';
import {withTheme} from '../fake_theme';

jest.mock('sources/Dialogs/FirebirdCatalogDesigner',()=>()=>null);
const Component=withTheme(SQLiteRetainedSchema);
const snapshot={format:'ddn-source-workspace@1',entry:'catalog.ddn',view:'inventory_1',files:{'catalog.ddn':'retained native facts'}};
const capture={document:{snapshot},resources:[{resource_id:'temporary',resource_kind:'table',display_name:'owned',display_path:['temp','owned'],native:{}}]};

it('generates and reviews native TEMP columns on the captured original session without commit',async()=>{
  const changed={...snapshot,files:{'catalog.ddn':'native desired columns'}};
  const post=jest.fn().mockResolvedValueOnce(capture).mockResolvedValueOnce({snapshot:changed})
    .mockResolvedValueOnce({operations:[{source:'ALTER TABLE "temp"."owned" ADD COLUMN extra'}],ready_for_review:true,execution_sha256:'native',warnings:[]})
    .mockResolvedValueOnce({review_id:'review',review_digest:'digest',state:'reviewed',native_session_release_confirmed:true})
    .mockResolvedValueOnce({review_id:'review',state:'applied_pending_caller_transaction',native_session_release_confirmed:true,
      outcome:{commit_dispatched:false,native_ddl_acknowledged:true}});
  const busy=jest.fn(),connect=jest.fn();
  render(<Component post={post} ensureSession={connect} sessionId="original" databaseTargetId="file" onBusyChange={busy} />);
  fireEvent.click(screen.getByText('Original-session SQLite design'));
  fireEvent.click(screen.getByRole('button',{name:'Capture original-session DDN'}));
  fireEvent.click(await screen.findByText('Native column additions'));
  fireEvent.change(screen.getByRole('textbox',{name:'Column 1 name'}),{target:{value:'extra'}});
  fireEvent.click(screen.getByRole('button',{name:'Generate column design'}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Preview original-session changes'})).toBeEnabled());
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_retained_schema',database_target_id:'file',session_id:'original',
    request:{operation:'columns',baseline:JSON.stringify(snapshot),resource_id:'temporary',
      columns:[{name:'extra',data_type:'',nullable:true,constraint_names:{}}]}});
  fireEvent.click(screen.getByRole('button',{name:'Preview original-session changes'}));
  await screen.findByText('ALTER TABLE "temp"."owned" ADD COLUMN extra');
  fireEvent.click(screen.getByRole('button',{name:'Prepare original-session review'}));
  await screen.findByText(/Original-session receipt review: reviewed/);
  expect(screen.getByRole('button',{name:'Apply original-session DDL'})).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox',{name:'Confirm this DDL on the original caller transaction'}));
  fireEvent.click(screen.getByRole('button',{name:'Apply original-session DDL'}));
  await screen.findByText(/applied_pending_caller_transaction/);
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_retained_schema',database_target_id:'file',session_id:'original',
    request:{operation:'start',review_id:'review',review_digest:'digest',confirmed:true}});
  await waitFor(()=>expect(busy).toHaveBeenLastCalledWith(false));
  expect(connect).not.toHaveBeenCalled();
  expect(post.mock.calls.some(([value])=>value.action==='transaction_action')).toBe(false);
});

it('reads archived uncertainty without opening or blocking the current query connection',async()=>{
  const post=jest.fn().mockResolvedValueOnce({receipts:[{review_id:'old',state:'unknown_outcome'}],total:1,more:false})
    .mockResolvedValueOnce({review_id:'old',state:'unknown_outcome',native_session_release_confirmed:false,worker_active:false});
  const connect=jest.fn(),busy=jest.fn(),blocked=jest.fn();
  render(<Component post={post} ensureSession={connect} databaseTargetId="file" onBusyChange={busy} onBlocked={blocked} />);
  fireEvent.click(screen.getByText('Original-session SQLite design'));fireEvent.click(screen.getByText('Retained DDL receipts'));
  fireEvent.click(screen.getByRole('button',{name:'List retained DDL receipts'}));
  const select=await screen.findByRole('combobox',{name:'Retained DDL receipt'});
  fireEvent.change(select.parentElement.querySelector('input'),{target:{value:'old'}});
  fireEvent.click(screen.getByRole('button',{name:'Inspect archived DDL receipt'}));
  await screen.findByText(/Original-session receipt old: unknown_outcome/);
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_retained_schema_receipts',database_target_id:'file',
    request:{operation:'receipt',review_id:'old'}});
  expect(connect).not.toHaveBeenCalled();expect(blocked).not.toHaveBeenCalled();expect(busy).not.toHaveBeenCalled();
});

it('discards a capture reply after the original query session changes',async()=>{
  let resolve;
  const post=jest.fn().mockImplementation(()=>new Promise(done=>{resolve=done;}));
  const props={post,ensureSession:jest.fn(),databaseTargetId:'file'};
  const view=render(<Component {...props} sessionId="first" />);
  fireEvent.click(screen.getByText('Original-session SQLite design'));
  fireEvent.click(screen.getByRole('button',{name:'Capture original-session DDN'}));
  view.rerender(<Component {...props} sessionId="second" />);resolve(capture);
  await waitFor(()=>expect(screen.getByRole('button',{name:'Capture original-session DDN'})).toBeEnabled());
  expect(screen.queryByText('Native column additions')).not.toBeInTheDocument();
  expect(post).toHaveBeenCalledTimes(1);
});

it.each([
  ['rename-table',{name:'new:雪'}],['rename-column',{column:'payload',name:'new:雪'}],
  ['drop-column',{column:'payload'}],['drop-constraint',{name:'positive'}],
  ['drop-not-null',{column:'payload'}],['set-not-null',{column:'payload',conflict:''}],
  ['add-check',{name:'positive',expression:'payload IS NOT NULL',conflict:''}],
])('generates the native %s design and preserves its typed intent through review',async(action,fields)=>{
  const generated={...snapshot,files:{'catalog.ddn':'native altered '+action}};
  const observed={...capture,resources:[...capture.resources,{resource_id:'payload',resource_kind:'column',
    display_name:'payload',display_path:['temp','owned','payload'],native:{}}]};
  const post=jest.fn().mockResolvedValueOnce(observed).mockResolvedValueOnce({snapshot:generated})
    .mockResolvedValueOnce({operations:[{source:'Native '+action}],ready_for_review:true,execution_sha256:'altered',warnings:[]})
    .mockResolvedValueOnce({review_id:'alter',review_digest:'digest',state:'reviewed',native_session_release_confirmed:true});
  render(<Component post={post} ensureSession={jest.fn()} sessionId="original" databaseTargetId="file" />);
  fireEvent.click(screen.getByText('Original-session SQLite design'));
  fireEvent.click(screen.getByRole('button',{name:'Capture original-session DDN'}));
  fireEvent.click(await screen.findByText('Native table alterations'));
  fireEvent.change(screen.getByRole('combobox',{name:'Native table alteration'}).parentElement.querySelector('input'),{target:{value:action}});
  if(fields.name)fireEvent.change(screen.getByRole('textbox',{name:action==='drop-constraint' ? 'Native constraint name':action==='add-check' ? 'CHECK name (optional)':'New native name'}),{target:{value:fields.name}});
  if(fields.expression)fireEvent.change(screen.getByRole('textbox',{name:'Native CHECK expression'}),{target:{value:fields.expression}});
  fireEvent.click(screen.getByRole('button',{name:'Generate native alteration design'}));
  const changes=[{action,resource_id:'temporary',...fields}];
  await waitFor(()=>expect(post).toHaveBeenLastCalledWith({action:'sqlite_retained_schema',database_target_id:'file',session_id:'original',
    request:{operation:'alter',baseline:JSON.stringify(snapshot),alterations:changes}}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Preview original-session changes'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'Preview original-session changes'}));
  await screen.findByText('Native '+action);
  fireEvent.click(screen.getByRole('button',{name:'Prepare original-session review'}));
  await screen.findByText(/Original-session receipt alter: reviewed/);
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_retained_schema',database_target_id:'file',session_id:'original',
    request:{operation:'review',baseline:JSON.stringify(snapshot),desired:JSON.stringify(generated),deletions:[],alterations:changes,execution_sha256:'altered'}});
});

it('discards a generated native alteration after changing original sessions',async()=>{
  let resolve;
  const pending=new Promise(done=>{resolve=done;});
  const post=jest.fn().mockResolvedValueOnce(capture).mockReturnValueOnce(pending);
  const props={post,ensureSession:jest.fn(),databaseTargetId:'file'};
  const view=render(<Component {...props} sessionId="first" />);
  fireEvent.click(screen.getByText('Original-session SQLite design'));
  fireEvent.click(screen.getByRole('button',{name:'Capture original-session DDN'}));
  fireEvent.click(await screen.findByText('Native table alterations'));
  fireEvent.change(screen.getByRole('textbox',{name:'New native name'}),{target:{value:'late_name'}});
  fireEvent.click(screen.getByRole('button',{name:'Generate native alteration design'}));
  view.rerender(<Component {...props} sessionId="second" />);resolve({snapshot});
  await waitFor(()=>expect(screen.getByRole('button',{name:'Capture original-session DDN'})).toBeEnabled());
  expect(screen.queryByRole('button',{name:'Preview original-session changes'})).not.toBeInTheDocument();
  expect(post).toHaveBeenCalledTimes(2);
});
