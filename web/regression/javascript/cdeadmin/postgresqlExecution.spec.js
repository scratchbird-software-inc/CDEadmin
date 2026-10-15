import {postgresqlExecution} from '../../../pgadmin/static/js/cdeadmin_ui/editors/postgresqlExecution';

test('uses native spans around dollar-quoted bodies and Unicode cursor offsets', async () => {
  const first = 'SELECT \'😀;\';', second = 'DO $$ BEGIN PERFORM 1; END $$';
  const source = first + '\n' + second;
  const validate = jest.fn().mockResolvedValue({syntax_valid:true, statements:[
    {source:first.slice(0,-1),start:0,end:Array.from(first).length-1},
    {source:second,start:Array.from(first).length+1,end:Array.from(source).length},
  ]});
  expect(await postgresqlExecution(source,'current',source.length,source.length,validate))
    .toEqual({source:second,scriptMode:false});
  expect(await postgresqlExecution(source,'from-cursor',0,0,validate))
    .toEqual({source:first.slice(0,-1)+'\n;\n'+second,scriptMode:true});
});

test('validates selected source independently of an unfinished surrounding draft', async () => {
  const validate = jest.fn().mockResolvedValue({syntax_valid:true,statements:[{source:'SELECT 1',start:0,end:8}]});
  expect(await postgresqlExecution('bad SELECT 1 unfinished','selection',4,12,validate))
    .toEqual({source:'SELECT 1',scriptMode:false});
  expect(validate).toHaveBeenCalledWith('SELECT 1');
});

test('refuses empty selections and parser failures without manufacturing boundaries', async () => {
  const validate = jest.fn().mockResolvedValue({syntax_valid:false,diagnostics:[{message:'Invalid SQL'}]});
  await expect(postgresqlExecution('SELECT','selection',0,0,validate)).rejects.toThrow('Select SQL');
  expect(validate).not.toHaveBeenCalled();
  await expect(postgresqlExecution('SELECT','current',0,0,validate)).rejects.toThrow('Invalid SQL');
});

test('terminates trailing line comments before inserting statement separators', async () => {
  const validate = async () => ({syntax_valid:true,statements:[
    {source:'SELECT 1 -- trailing comment',start:0,end:28},
    {source:'SELECT 2',start:31,end:39},
  ]});
  expect((await postgresqlExecution('SELECT 1 -- trailing comment\n; SELECT 2','from-cursor',0,0,validate)).source)
    .toBe('SELECT 1 -- trailing comment\n;\nSELECT 2');
});
