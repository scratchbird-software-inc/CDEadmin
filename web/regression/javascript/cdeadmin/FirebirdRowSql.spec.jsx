import {TextEncoder} from 'util';
import {fireEvent, render, screen} from '@testing-library/react';
import FirebirdRowSql from 'sources/Dialogs/FirebirdRowSql';
import {generateRowSql, firebirdLiteral} from 'sources/Dialogs/firebirdRowSql';
import {withTheme} from '../fake_theme';

describe('Firebird selected-row SQL', () => {
  let encoder;
  beforeEach(() => {encoder = global.TextEncoder; global.TextEncoder = TextEncoder;});
  afterEach(() => {global.TextEncoder = encoder;});
  const columns = [{name: 'ID', key: true, input_kind: 'integer'}, {name: 'Text"field', input_kind: 'text'}];
  const rows = [{values: {ID: '9007199254740993', 'Text"field': "O'Brien"}}];
  const args = {table: 'Odd"Table', columns, rows, keys: ['ID']};
  it('quotes native identifiers and preserves exact parameter values', () => {
    expect(generateRowSql({...args, operation: 'insert'})).toEqual([{source: 'INSERT INTO "Odd""Table" ("ID", "Text""field") VALUES (?, ?);', parameters: ['9007199254740993', "O'Brien"]}]);
    const update = generateRowSql({...args, operation: 'update'})[0];
    expect(update.source).toContain('WHERE "ID" IS NOT DISTINCT FROM ?');
    expect(update.parameters).toEqual(["O'Brien", '9007199254740993']);
    expect(generateRowSql({...args, operation: 'upsert', inline: true})[0].source).toContain("VALUES (9007199254740993, 'O''Brien') MATCHING (\"ID\")");
  });
  it('handles NULL in predicates and refuses missing matching keys', () => {
    const result = generateRowSql({...args, rows: [...rows, {values: {ID: null}}], operation: 'in', inColumn: 'ID'})[0];
    expect(result.source).toContain('("ID" IN (?) OR "ID" IS NULL)');
    expect(result.parameters).toEqual(['9007199254740993']);
    expect(() => generateRowSql({...args, operation: 'update', keys: []})).toThrow('matching');
    expect(() => generateRowSql({...args, operation: 'insert', rows: Array(101).fill(rows[0])})).toThrow('100');
  });
  it('refuses approximate or unsupported literals rather than changing data', () => {
    expect(() => firebirdLiteral('1); DROP TABLE X;', {input_kind: 'decimal'})).toThrow();
    expect(() => firebirdLiteral(9007199254740992, {input_kind: 'integer'})).toThrow('exact');
    expect(() => firebirdLiteral([1, 2], {input_kind: 'array'})).toThrow('parameters');
    expect(firebirdLiteral('-0.0', {input_kind: 'float64'})).toBe("CAST('-0.0' AS DOUBLE PRECISION)");
    expect(() => firebirdLiteral('1.234e30', {input_kind: 'decimal'})).toThrow('parameters');
    expect(firebirdLiteral('12:34:56.1234', {input_kind: 'time'})).toBe("TIME '12:34:56.1234'");
    expect(firebirdLiteral({encoding: 'base64', data: 'AP8=', byte_length: 2}, {input_kind: 'binary'})).toBe("x'00ff'");
  });
  it('requires selection and explicit preview before loading, with no execution callback', () => {
    const Component = withTheme(FirebirdRowSql), onLoad = jest.fn();
    render(<Component page={{columns, rows}} table="T" onLoad={onLoad} />);
    expect(screen.getByText('Generate row SQL')).toBeDisabled();
    fireEvent.click(screen.getByLabelText('Fetched row 1'));
    fireEvent.click(screen.getByText('Generate row SQL'));
    expect(onLoad).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Load statement into SQL editor'));
    expect(onLoad).toHaveBeenCalledWith(expect.objectContaining({parameters: ['9007199254740993', "O'Brien"]}));
    fireEvent.click(screen.getByLabelText('Fetched row 1'));
    expect(screen.queryByText('Load statement into SQL editor')).toBeNull();
  });
});
