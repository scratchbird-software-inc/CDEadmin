import {compareFirebirdNodes} from '../../../pgadmin/static/js/cdeadmin_ui/navigation/firebirdTreeOrder';

const node = (fileName, data = {}) => ({fileName, _metadata: {data: {cde_engine_id: 'firebird', ...data}}});

describe('Firebird explorer ordering', () => {
  it('places virtual folders first even when table names sort earlier', () => {
    const nodes = [node('ASSETS'), node('system', {_type: 'cde_resource_group'}),
      node('monitoring', {_type: 'cde_resource_group'}), node('customers')];
    expect(nodes.sort(compareFirebirdNodes).map((item) => item.fileName)).toEqual([
      'monitoring', 'system', 'ASSETS', 'customers']);
  });
  it('sorts section leaves together with section folders', () => {
    const nodes = [node('indexes', {_type: 'cde_resource_group'}),
      node('comments', {cde_section: 'comments'}), node('columns', {_type: 'cde_resource_group'})];
    expect(nodes.sort(compareFirebirdNodes).map((item) => item.fileName)).toEqual(['columns', 'comments', 'indexes']);
  });
  it('leaves other engine sorting to the existing comparator', () => {
    expect(compareFirebirdNodes(node('a'), node('b', {cde_engine_id: 'mysql'}))).toBeNull();
  });
});
