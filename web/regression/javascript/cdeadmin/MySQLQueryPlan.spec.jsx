import {fireEvent, render, screen, within} from '@testing-library/react';
import MySQLQueryPlan from '../../../pgadmin/static/js/Dialogs/MySQLQueryPlan';
import {mysqlPlanText, parseMySQLPlan, PLAN_LIMITS} from '../../../pgadmin/static/js/Dialogs/mysqlQueryPlan';

const rendered = text => ({view_model: {columns: [{name: 'EXPLAIN', native_name: 'EXPLAIN'}], rows: [{EXPLAIN: text}]}});
const nativeJSON = '{"query_plan":{"operation":"Filter: café <img src=x>","estimated_rows":9007199254740993,"estimated_total_cost":0.1234567890123456789,"inputs":[{"operation":"Table scan on t","actual_rows":2,"actual_loops":0,"actual_first_row_ms":null}]},"json_schema_version":"2.0"}';

describe('native MySQL graphical plans', () => {
  it('keeps JSON version 2 exact numeric tokens, native edges and null/zero observations', () => {
    const plan = parseMySQLPlan(nativeJSON);
    expect(plan.available).toBe(true);
    expect(plan.format).toBe('JSON version 2');
    expect(plan.nodes).toHaveLength(2);
    expect(plan.nodes[0].children).toEqual([1]);
    expect(plan.nodes[0].facts).toContainEqual({name: 'estimated_rows', value: '9007199254740993'});
    expect(plan.nodes[0].facts).toContainEqual({name: 'estimated_total_cost', value: '0.1234567890123456789'});
    expect(plan.nodes[1].facts).toEqual(expect.arrayContaining([
      {name: 'actual_rows', value: '2'}, {name: 'actual_loops', value: '0'}, {name: 'actual_first_row_ms', value: 'null'},
    ]));
  });

  it('keeps version 1 query blocks, joins, subqueries and cost metadata without inventing actual measurements', () => {
    const plan = parseMySQLPlan('{"query_block":{"select_id":1,"cost_info":{"query_cost":"19.01"},"nested_loop":[{"table":{"table_name":"a","access_type":"ALL","rows_examined_per_scan":3}},{"table":{"table_name":"b","attached_subqueries":[{"query_block":{"message":"No tables used"}}]}}]}}');
    expect(plan.available).toBe(true);
    expect(plan.format).toBe('JSON version 1');
    expect(plan.hasActual).toBe(false);
    expect(plan.nodes[0].facts).toContainEqual({name: 'cost_info', value: '{"query_cost":"19.01"}'});
    expect(plan.nodes.some(node => node.path.includes('attached_subqueries[0].query_block'))).toBe(true);
  });

  it('uses TREE indentation and exact native estimates/actuals, including repeated operators and never-executed branches', () => {
    const source = '-> Nested loop (cost=1.20 rows=2) (actual time=0.001..0.010 rows=2 loops=1)\n    -> Table scan on t (cost=1 rows=2)\n    -> Table scan on t (cost=1 rows=2)\n        -> Filter (never executed)\n';
    const plan = parseMySQLPlan(source);
    expect(plan.format).toBe('TREE');
    expect(plan.nodes[0].children).toEqual([1, 2]);
    expect(plan.nodes[2].path).toBe('line 3');
    expect(plan.nodes[3].parent).toBe(2);
    expect(plan.nodes[3].facts).toContainEqual({name: 'native actuals', value: '(never executed)'});
    expect(plan.nodes[0].facts).toContainEqual({name: 'native actuals', value: '(actual time=0.001..0.010 rows=2 loops=1)'});
  });

  it.each(['SELECT 1', '{"not_a_plan":1}', '{"query_plan":',
    '{"query_plan":{"operation":"a","operation":"b"}}',
    '{"query_plan":{"operation":"a","__pro\\u0074o__":{"operation":"b"}}}',
  ])('retains unsupported or malformed text without claiming a graphical plan: %s', source => {
    expect(parseMySQLPlan(source).available).toBe(false);
  });

  it('refuses oversized, overly deep and overly large node graphs', () => {
    expect(parseMySQLPlan('x'.repeat(PLAN_LIMITS.bytes + 1))).toMatchObject({available: false});
    const nested = '{"query_block":' + '{"table":'.repeat(70) + '{}' + '}'.repeat(71);
    expect(parseMySQLPlan(nested)).toMatchObject({available: false});
    expect(parseMySQLPlan(Array.from({length: 501}, () => '-> Table scan').join('\n'))).toMatchObject({available: false});
  });

  it('accepts only one named native EXPLAIN text cell, including array rows', () => {
    expect(mysqlPlanText(rendered(nativeJSON))).toBe(nativeJSON);
    expect(mysqlPlanText({view_model: {columns: [{name: 'EXPLAIN'}], rows: [[nativeJSON]]}})).toBe(nativeJSON);
    expect(mysqlPlanText(rendered({plan: true}))).toBeNull();
    expect(mysqlPlanText({view_model: {columns: [{name: 'body'}], rows: [{body: nativeJSON}]}})).toBeNull();
    expect(mysqlPlanText({view_model: {columns: [{name: 'EXPLAIN'}], rows: [[nativeJSON], [nativeJSON]]}})).toBeNull();
  });

  it('renders connected native operators, exact facts and escaped source; selection/collapse never execute SQL', () => {
    render(<MySQLQueryPlan rendered={rendered(nativeJSON)} />);
    expect(screen.getByRole('tree', {name: 'Native MySQL operator graph'})).toBeVisible();
    expect(screen.getByLabelText('Original MySQL plan text').textContent).toBe(nativeJSON);
    expect(document.querySelector('img')).toBeNull();
    expect(screen.getByLabelText('Selected native operator')).toHaveTextContent('9007199254740993');
    fireEvent.click(screen.getByRole('button', {name: 'Inspect operator 2'}));
    expect(within(screen.getByLabelText('Selected native operator')).getByText('actual_loops')).toBeVisible();
    fireEvent.click(screen.getByRole('button', {name: 'Collapse operator'}));
    expect(screen.queryByRole('button', {name: 'Inspect operator 2'})).toBeNull();
    expect(screen.getByText(/Costs are not elapsed milliseconds/)).toBeVisible();
  });

  it('separates requested execution and incomplete delivery from native plan observations', () => {
    render(<MySQLQueryPlan rendered={rendered(nativeJSON)} analyzeRequested pending failed />);
    expect(screen.getByText(/EXPLAIN ANALYZE was requested and executes/)).toBeVisible();
    expect(screen.getByText(/does not establish successful completion/)).toBeVisible();
    expect(screen.getByRole('tree')).toBeVisible();
  });

  it('keeps the original text for a native plan that cannot be graphed', () => {
    render(<MySQLQueryPlan rendered={rendered('{broken native text')} />);
    expect(screen.getByText(/Graphical presentation is unavailable/)).toBeVisible();
    expect(screen.getByLabelText('Original MySQL plan text').textContent).toBe('{broken native text');
    expect(screen.queryByRole('tree')).toBeNull();
  });
});
