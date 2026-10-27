import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import MySQLContentSearch from 'sources/Dialogs/MySQLContentSearch';
import {withTheme} from '../fake_theme';

const Component=withTheme(MySQLContentSearch);
const viewportHeight=window.innerHeight;
beforeAll(() => {window.innerHeight=1200;});
afterAll(() => {window.innerHeight=viewportHeight;});
const terminal={job_id:'private-job',terminal:true,state:'completed',matches:[{match_id:'match',table_name:'t`雪',column_name:'note',
  preview:'<img src=x> private value',preview_encoding:'native text',value_bytes:'23',navigation_available:true}],
coverage:[{table_name:'t`雪',state:'observed',columns:[{column_name:'note',state:'searched'}]}],
identity:{server_uuid:'native-source'},cancellation:{requested:false},elapsed_seconds:1};

function backend(extra) {
  return jest.fn(async payload => {
    const op=payload.action.replace('mysql_content_search_','');
    if(extra) {const result=extra(op,payload.request);if(result!==undefined)return result;}
    if(op==='tables')return {rows:[{name:'t`雪',kind:'BASE TABLE',engine:'InnoDB'}],next_offset:null};
    if(op==='columns')return {table_name:'t`雪',fingerprint:'a'.repeat(64),key:['id'],next_offset:null,
      rows:[{COLUMN_NAME:'note',COLUMN_TYPE:'varchar(80)',PRIVILEGES:'select',COLLATION_NAME:'utf8mb4_0900_ai_ci'}]};
    if(op==='start')return terminal;
    if(op==='row')return {state:'current-row',table_name:'t`雪',basis:'fresh native key read',values:[{column_name:'id',data_type:'bigint unsigned',preview:'18446744073709551615'}]};
    return {state:'cleared'};
  });
}
async function select() {
  fireEvent.change(screen.getByLabelText('Search database'),{target:{value:'demo'}});
  fireEvent.click(screen.getByRole('button',{name:'Discover tables'}));
  fireEvent.click(await screen.findByRole('button',{name:'t`雪'}));
  await screen.findByText('1 selected tables; 1 columns');
  fireEvent.click(screen.getByRole('checkbox',{name:'Allow private table-value search'}));
}

describe('MySQL database content search',() => {
  it('requires explicit scope and consent, binds exact names and safely renders native match previews',async () => {
    const post=backend();render(<Component post={post} />);
    expect(post).not.toHaveBeenCalled();
    expect(screen.getByRole('button',{name:'Start native content search'})).toBeDisabled();
    await select();
    fireEvent.change(screen.getByLabelText('Private search value'),{target:{value:'%\' OR 1=1'}});
    fireEvent.click(screen.getByRole('button',{name:'Start native content search'}));
    await screen.findByText('<img src=x> private value (native text)');
    expect(document.querySelector('img')).toBeNull();
    expect(post.mock.calls.find(([p]) => p.action.endsWith('_start'))[0].request).toEqual({
      database_target_id:null,schema_name:'demo',tables:[{table_name:'t`雪',fingerprint:'a'.repeat(64),columns:['note']}],confirmed:true,
      options:{mode:'text_contains',value:'%\' OR 1=1',indexed_only:false,limit:200,seconds:30}});
    fireEvent.click(screen.getByRole('button',{name:'Open current row'}));
    await screen.findByText('18446744073709551615');
    expect(screen.getByLabelText('Current native search row')).toHaveTextContent('fresh native key read');
  });

  it('keeps exact numeric search text as a string and reports native key absence',async () => {
    const post=backend(op => op==='start' ? {...terminal,matches:[{...terminal.matches[0],navigation_available:false}]} : undefined);
    render(<Component post={post} />);await select();
    fireEvent.mouseDown(screen.getByRole('combobox',{name:'Value comparison'}));
    fireEvent.click(await screen.findByRole('option',{name:'Numeric equals'}));
    fireEvent.change(screen.getByLabelText('Private search value'),{target:{value:'18446744073709551615'}});
    fireEvent.click(screen.getByRole('button',{name:'Start native content search'}));
    await screen.findByText('No readable native unique key');
    expect(screen.getByRole('button',{name:'Open current row'})).toBeDisabled();
    expect(post.mock.calls.find(([p]) => p.action.endsWith('_start'))[0].request.options.value).toBe('18446744073709551615');
  });

  it('continues polling cancellation until the native worker is terminal',async () => {
    let poll;
    const interval=global.setInterval;
    const timer=jest.spyOn(global,'setInterval').mockImplementation((fn,ms) => {
      if(ms===500) {poll=fn;return 999;} return interval(fn,ms);
    });
    const running={...terminal,terminal:false,state:'running',matches:[]};
    const post=backend(op => op==='start' || op==='cancel' ? running : op==='status' ? {...terminal,state:'cancelled',matches:[]} : undefined);
    const mounted=render(<Component post={post} />);
    try {
      await select();fireEvent.click(screen.getByRole('button',{name:'Start native content search'}));
      await waitFor(() => expect(screen.getByRole('button',{name:'Cancel search'})).toBeEnabled());
      fireEvent.click(screen.getByRole('button',{name:'Cancel search'}));
      await waitFor(() => expect(post.mock.calls.some(([p]) => p.action.endsWith('_cancel'))).toBe(true));
      await waitFor(() => expect(screen.getByRole('button',{name:'Cancel search'})).toBeEnabled());
      await act(async () => {await poll();});
      expect(screen.getByRole('button',{name:'Clear private results'})).toBeEnabled();
      expect(screen.getByText(/Search: cancelled/)).toBeVisible();
    } finally {mounted.unmount();timer.mockRestore();}
  });

  it('clears private values locally even when server removal is unavailable',async () => {
    const post=backend(op => op==='forget' ? Promise.reject(new Error('unavailable')) : undefined);
    render(<Component post={post} />);await select();
    fireEvent.change(screen.getByLabelText('Private search value'),{target:{value:'private needle'}});
    fireEvent.click(screen.getByRole('button',{name:'Start native content search'}));
    await screen.findByRole('button',{name:'Open current row'});
    fireEvent.click(screen.getByRole('button',{name:'Clear private results'}));
    expect(screen.queryByRole('table',{name:'Native content matches'})).toBeNull();
    expect(screen.getByLabelText('Private search value')).toHaveValue('');
    await screen.findByText(/Private results were cleared here/);
  });

  it('rejects late private start responses after the registered target changes and requests cancellation',async () => {
    let resolve;
    const post=backend(op => op==='start' ? new Promise(reply => {resolve=reply;}) : undefined);
    const mounted=render(<Component post={post} />);await select();
    fireEvent.click(screen.getByRole('button',{name:'Start native content search'}));
    mounted.rerender(<Component post={post} databaseTargetId="new-target" />);
    await act(async () => {resolve(terminal);});
    expect(screen.queryByRole('table',{name:'Native content matches'})).toBeNull();
    expect(post.mock.calls.some(([p]) => p.action==='mysql_content_search_cancel' && p.request.job_id==='private-job')).toBe(true);
    expect(screen.getByLabelText('Search database')).toHaveValue('');
  });
});
