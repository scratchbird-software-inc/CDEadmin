import {administrationResourceLabel} from 'sources/cdeadmin_ui/navigation/resourceLabels';

const resource = (kind, native) => ({resource_id: 'stable-id', display_name: 'sum',
  resource_kind: kind, extensions: {postgresql: {native}}});

describe('native administration target labels', () => {
  it('distinguishes overloads using canonical qualified identity', () => {
    const first = resource('aggregate', {sql_identity: 'app.sum(integer)'});
    const second = resource('aggregate', {sql_identity: 'app.sum(bigint)'});
    expect(administrationResourceLabel(first)).toBe('app.sum(integer)');
    expect(administrationResourceLabel(second)).toBe('app.sum(bigint)');
    expect(first.resource_id).toBe('stable-id');
  });
  it('retains prefix and binary operator operand identities', () => {
    expect(administrationResourceLabel(resource('operator', {schema: 'a', name: '@#',
      left_type: null, right_type: 'integer'}))).toBe('"a".@# (NONE, integer)');
    expect(administrationResourceLabel(resource('operator', {schema: 'a', name: '===',
      left_type: 'integer', right_type: 'integer'}))).toBe('"a".=== (integer, integer)');
  });
  it('quotes significant names and retains native ordered signatures', () => {
    expect(administrationResourceLabel(resource('aggregate', {schema: ' a" ', name: ' sum ',
      identity_arguments: 'ORDER BY integer'}))).toBe('" a"" "." sum " (ORDER BY integer)');
  });
  it('preserves other provider labels', () => {
    expect(administrationResourceLabel({display_name: 'native label'})).toBe('native label');
  });
});
