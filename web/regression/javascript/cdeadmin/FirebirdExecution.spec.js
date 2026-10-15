import {TextEncoder} from 'util';
import {firebirdExecution, firebirdFragments} from 'sources/cdeadmin_ui/editors/firebirdExecution';

describe('Firebird scoped execution framing', () => {
  let encoder;
  beforeEach(() => {encoder = global.TextEncoder; global.TextEncoder = TextEncoder;});
  afterEach(() => {global.TextEncoder = encoder;});
  it('selects a whole PSQL block from an internal cursor', () => {
    const source = 'select 1; execute block returns (v integer) as begin v=case when 1=1 then 2 else 3 end; suspend; end; select 4;';
    const prepared = firebirdExecution(source, 'current', source.indexOf('suspend'));
    expect(prepared.scriptMode).toBe(false);
    expect(prepared.source).toBe('execute block returns (v integer) as begin v=case when 1=1 then 2 else 3 end; suspend; end');
  });
  it('preserves literal/comment delimiters and native terminator changes', () => {
    const source = 'SET TERM ^^ ; execute block returns (v varchar(20)) as begin v=q\'{;^^}\'; /* ^^ */ suspend; end ^^ SET TERM ; ^^ select 4;';
    const entries = firebirdFragments(source);
    expect(entries.map(item => item.kind)).toEqual(['terminator', 'sql', 'terminator', 'sql']);
    expect(firebirdExecution(source, 'current', source.indexOf('suspend')).source).toContain('v=q\'{;^^}\'');
  });
  it('inherits only client settings without replaying prior SQL or transactions', () => {
    const source = 'SET SQL DIALECT 3; SET AUTO OFF; SET BAIL ON; UPDATE BEFORE_T SET X=1; COMMIT; SELECT 2; SELECT 3;';
    const prepared = firebirdExecution(source, 'from-cursor', source.indexOf('SELECT 2') + 4);
    expect(prepared.scriptMode).toBe(true);
    expect(prepared.source).toContain('SET SQL DIALECT 3');
    expect(prepared.source).toContain('SET AUTO OFF');
    expect(prepared.source).toContain('SELECT 2');
    expect(prepared.source).toContain('SELECT 3');
    expect(prepared.source).not.toContain('BEFORE_T');
    expect(prepared.source).not.toContain('COMMIT');
  });
  it('normalizes a selection independently of preceding client settings', () => {
    const source = 'SET AUTODDL ON; SELECT 1; SELECT 2;';
    const from = source.indexOf('SELECT 1');
    expect(firebirdExecution(source, 'selection', from, from + 'SELECT 1;'.length)).toEqual({source: 'SELECT 1', scriptMode: false});
  });
  it('recognizes word delimiters inside unquoted tokens as native ISQL does', () => {
    const source = 'SET TERM xyz ; SELECT 1xyzSELECT 2xyz';
    expect(firebirdFragments(source).map(item => item.source)).toEqual(['SET TERM xyz', 'SELECT 1', 'SELECT 2']);
  });
  it.each(['select \'unclosed', 'execute block as begin suspend;', 'select 1 /* unclosed'])('refuses partial source %s', source => {
    expect(() => firebirdExecution(source, 'current', 0)).toThrow();
  });
  it('does not prepare an empty selection or a standalone client directive', () => {
    expect(() => firebirdExecution('select 1', 'selection', 0, 0)).toThrow();
    expect(() => firebirdExecution('set term ^ ;', 'current', 0)).toThrow();
  });
});
