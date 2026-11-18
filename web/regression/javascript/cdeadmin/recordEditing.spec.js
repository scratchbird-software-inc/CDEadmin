import {coerceEditedValue} from '../../../pgadmin/static/js/cdeadmin_ui/surfaces/dataEditSurfaceHelpers';

describe('record edit values shared by data and SQL surfaces', () => {
  test('infers metadata while preserving unset insert values and explicit NULL', () => {
    const column = {name: 'VALUE', native_type: 'VARCHAR', client_type: 'text'};
    expect(coerceEditedValue(undefined, column)).toBeUndefined();
    expect(coerceEditedValue(null, column)).toBeNull();
    expect(coerceEditedValue('<null>', column)).toBeNull();
    expect(coerceEditedValue('', column)).toBe('');
  });
  test('preserves exact numeric input and parses typed JSON without losing invalid drafts', () => {
    expect(coerceEditedValue('9223372036854775807', {name: 'ID', native_type: 'BIGINT', input_kind: 'integer'})).toBe('9223372036854775807');
    const json = {name: 'PAYLOAD', native_type: 'JSON', client_type: 'json'};
    expect(coerceEditedValue('{"enabled":true}', json)).toEqual({enabled: true});
    expect(coerceEditedValue('{unfinished', json)).toBe('{unfinished');
  });
});
