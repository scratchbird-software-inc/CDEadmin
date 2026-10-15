import BaseUISchema from 'sources/SchemaView/base_schema.ui';
import {validateSchema} from 'sources/SchemaView/SchemaState/common';

class ConditionalSchema extends BaseUISchema {
  constructor() {
    super();
    this.requiredKind = 'native';
  }

  get baseFields() {
    return [{id: 'detail', label: 'Detail', type: 'text', noEmpty: true,
      visible: function(state) { return state.kind === this.requiredKind; }}];
  }

  validate() { return false; }
}

describe('Conditional validation schema context', () => {
  it('validates visible fields and skips hidden fields with their schema context', () => {
    const schema = new ConditionalSchema();
    const error = jest.fn();
    expect(validateSchema(schema, {kind: 'other'}, error)).toBe(false);
    expect(error).not.toHaveBeenCalled();
    expect(validateSchema(schema, {kind: 'native'}, error)).toBe(true);
    expect(error).toHaveBeenCalledWith(['detail'], expect.any(String));
    expect(validateSchema(schema, {kind: 'native', detail: 'value'}, error)).toBe(false);
  });

  it('uses the child context and retains collection row error paths', () => {
    const child = new ConditionalSchema();
    class Parent extends BaseUISchema {
      get baseFields() {
        return [{id: 'items', label: 'Items', type: 'collection', schema: child}];
      }
      validate() { return false; }
    }
    const error = jest.fn();
    expect(validateSchema(new Parent(), {items: [
      {kind: 'other'}, {kind: 'native'},
    ]}, error)).toBe(true);
    expect(error).toHaveBeenCalledWith(['items', 1, 'detail'], expect.any(String));
  });
});
