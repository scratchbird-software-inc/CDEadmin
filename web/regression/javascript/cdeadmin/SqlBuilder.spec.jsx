/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Visual SQL builder (owner direction 2026-11-06, option b; SQLite and
 * DuckDB first, 2026-11-08). The form sends a neutral query model; the
 * server writes the SQL (tools/tests/test_sql_builder.py runs it on the
 * engines). Every option is shown, and the ones the connection lacks are
 * disabled with the reason the engine declares.
 */

import {act, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import SqlBuilderDialog from 'sources/cdeadmin_ui/editors/SqlBuilderDialog';
import {
  BuilderDraftError, emptyColumn, emptyCondition, emptyCte, emptyDraft, emptyJoin,
  emptyOrder, emptySelect, cteSource, relationSource, toModel,
} from 'sources/cdeadmin_ui/editors/sqlBuilderModel';

const OPTION_IDS = ['cte', 'cte.recursive', 'cte.materialized', 'distinct', 'distinct_on',
  'join.inner', 'join.left', 'join.right', 'join.full', 'join.cross', 'join.natural',
  'join.using', 'where', 'where.or', 'aggregate', 'aggregate.distinct', 'group_by',
  'group_by.rollup', 'group_by.cube', 'group_by.grouping_sets', 'group_by.all', 'having',
  'order_by', 'order_by.nulls', 'limit', 'offset', 'set.union', 'set.union_all',
  'set.intersect', 'set.except'];

const LACKS = {
  distinct_on: 'SQLite has no DISTINCT ON.',
  'group_by.rollup': 'SQLite has no ROLLUP.',
  'join.right': 'Needs a newer SQLite: 3.35.0 refuses RIGHT and FULL joins.',
};

function optionsResponse() {
  return {
    runtime_version: '3.35.0',
    options: Object.fromEntries(OPTION_IDS.map((id) => [id, {label: id,
      available: !LACKS[id], reason: LACKS[id] || ''}])),
    relations: [
      {path: ['main', 'customers'], kind: 'table', name: 'customers', columns: ['id', 'name']},
      {path: ['main', 'orders'], kind: 'table', name: 'orders', columns: ['id', 'customer_id', 'amount']},
    ],
  };
}

const ORDERS = relationSource(['main', 'orders']);
const CUSTOMERS = relationSource(['main', 'customers']);

describe('SQL builder drafts', () => {
  it('turn into the neutral query model, never SQL text', () => {
    const draft = emptyDraft(ORDERS);
    const cte = emptyCte('totals', ORDERS);
    cte.materialized = 'yes';
    const inner = cte.query.selects[0];
    inner.columns = [{...emptyColumn(), column: JSON.stringify(['orders', 'customer_id'])},
      {...emptyColumn('aggregate'), func: 'sum', star: false,
        column: JSON.stringify(['orders', 'amount']), alias: 'total'}];
    inner.group = {kind: 'columns', columns: [JSON.stringify(['orders', 'customer_id'])], sets: []};
    inner.having.items = [{...emptyCondition('aggregate'), op: '>',
      right: {kind: 'number', value: '3'}}];
    draft.ctes = [cte];
    const main = draft.query.selects[0];
    main.source = CUSTOMERS;
    main.alias = 'c';
    const join = emptyJoin(cteSource('totals'));
    join.type = 'left';
    join.alias = 't';
    join.on.left.column = JSON.stringify(['t', 'customer_id']);
    join.on.right.column = JSON.stringify(['c', 'id']);
    main.joins = [join];
    main.where = {combine: 'any', items: [
      {...emptyCondition(), left: {kind: 'column', column: JSON.stringify(['c', 'name'])},
        op: 'LIKE', right: {kind: 'text', value: '%o\'%'}},
      {...emptyCondition(), left: {kind: 'column', column: JSON.stringify(['t', 'total'])},
        op: 'IS NOT NULL'}]};
    draft.query.order = [{...emptyOrder(), operand: {kind: 'column',
      column: JSON.stringify(['t', 'total'])}, direction: 'desc', nulls: 'last'}];
    draft.query.limit = '10';
    draft.query.offset = '5';
    expect(toModel(draft)).toEqual({
      with: [{name: 'totals', materialized: true, query: {selects: [{
        from: {source: {relation: ['main', 'orders']}},
        columns: [{expr: {column: ['orders', 'customer_id']}},
          {expr: {aggregate: {function: 'sum', distinct: false,
            argument: {column: ['orders', 'amount']}}}, alias: 'total'}],
        group_by: {kind: 'columns', items: [{column: ['orders', 'customer_id']}]},
        having: {compare: {left: {aggregate: {function: 'count', distinct: false, argument: '*'}},
          op: '>', right: {value: 3}}},
      }]}}],
      query: {selects: [{
        from: {source: {relation: ['main', 'customers']}, alias: 'c'},
        joins: [{type: 'left', source: {cte: 'totals'}, alias: 't', on: {compare: {
          left: {column: ['t', 'customer_id']}, op: '=', right: {column: ['c', 'id']}}}}],
        where: {any: [
          {compare: {left: {column: ['c', 'name']}, op: 'LIKE', right: {value: '%o\'%'}}},
          {is_not_null: {column: ['t', 'total']}}]},
      }], order_by: [{expr: {column: ['t', 'total']}, direction: 'desc', nulls: 'last'}],
      limit: 10, offset: 5},
    });
  });

  it('name what is missing instead of sending an incomplete model', () => {
    const draft = emptyDraft(ORDERS);
    draft.query.selects[0].columns = [emptyColumn()];
    expect(() => toModel(draft)).toThrow(new BuilderDraftError('Query column 1: choose a column.'));
    draft.query.selects[0].columns = [];
    draft.query.limit = '-1';
    expect(() => toModel(draft)).toThrow('Query LIMIT must be a whole number of 0 or more.');
    draft.query.limit = '';
    draft.query.selects = [emptySelect(ORDERS), emptySelect('')];
    draft.query.operators = ['union'];
    expect(() => toModel(draft)).toThrow('Query SELECT 2 FROM: choose a table, view or CTE.');
  });
});

describe('SqlBuilderDialog', () => {
  // jsdom gives every element an 800px offsetHeight (setup-jest.js); with
  // its default 768px window MUI reports every open menu as too tall. As in
  // DuckDBAttachment.spec, the window is made tall enough for the menus.
  const originalHeight = window.innerHeight;
  beforeAll(() => {window.innerHeight = 1800;});
  afterAll(() => {window.innerHeight = originalHeight;});

  function renderDialog(post) {
    const onInsert = jest.fn();
    const onClose = jest.fn();
    const Dialog = withTheme(SqlBuilderDialog);
    render(<Dialog open post={post} onInsert={onInsert} onClose={onClose} />);
    return {onInsert, onClose};
  }

  function chooseIn(label) {
    fireEvent.mouseDown(screen.getByRole('combobox', {name: label}));
    return screen.getByRole('listbox');
  }

  it('shows every option and disables the ones this connection lacks, with the reason', async () => {
    const post = jest.fn().mockResolvedValue(optionsResponse());
    renderDialog(post);
    await screen.findByRole('combobox', {name: 'Query FROM'});
    expect(post).toHaveBeenCalledWith({action: 'sql_builder', request: {operation: 'options'}});
    const listed = screen.getByLabelText('Options for this connection');
    for(const id of OPTION_IDS) {
      const item = listed.querySelector(`[data-option="${id}"]`);
      expect(item).not.toBeNull();
      expect(item.getAttribute('data-available')).toBe(LACKS[id] ? 'false' : 'true');
      if(LACKS[id]) expect(item).toHaveTextContent(LACKS[id]);
    }
    // A field the connection lacks is disabled and says why.
    expect(screen.getByLabelText('Query DISTINCT ON')).toBeDisabled();
    expect(screen.getByText('SQLite has no DISTINCT ON.', {selector: 'p'})).toBeInTheDocument();
  });

  it('disables join types the connection lacks', async () => {
    renderDialog(jest.fn().mockResolvedValue(optionsResponse()));
    await screen.findByRole('combobox', {name: 'Query FROM'});
    fireEvent.click(screen.getByRole('button', {name: 'Add join'}));
    const listbox = chooseIn('Query join 1 type');
    expect(within(listbox).getByRole('option', {name: `Right join (${LACKS['join.right']})`}))
      .toHaveAttribute('aria-disabled', 'true');
    expect(within(listbox).getByRole('option', {name: 'Full join'})).not.toHaveAttribute('aria-disabled');
    fireEvent.click(within(listbox).getByRole('option', {name: 'Left join'}));
    expect(screen.getByRole('combobox', {name: 'Query join 1 type'})).toHaveTextContent('Left join');
  });

  it('disables groupings the connection lacks', async () => {
    renderDialog(jest.fn().mockResolvedValue(optionsResponse()));
    await screen.findByRole('combobox', {name: 'Query FROM'});
    const listbox = chooseIn('Query grouping');
    expect(within(listbox).getByRole('option', {name: 'GROUP BY ROLLUP (SQLite has no ROLLUP.)'}))
      .toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(within(listbox).getByRole('option', {name: 'GROUP BY CUBE'}));
    expect(screen.getByRole('combobox', {name: 'Query grouping'})).toHaveTextContent('GROUP BY CUBE');
  });

  it('inserts the statement the server wrote and runs nothing', async () => {
    const post = jest.fn((payload) => Promise.resolve(payload.request.operation === 'options' ?
      optionsResponse() : {source: 'SELECT\n  *\nFROM main.customers', language_profile: 'sqlite-sql'}));
    const {onInsert, onClose} = renderDialog(post);
    await screen.findByRole('combobox', {name: 'Query FROM'});
    fireEvent.click(screen.getByRole('button', {name: 'Preview SQL'}));
    expect(await screen.findByLabelText('SQL preview')).toHaveTextContent('FROM main.customers');
    fireEvent.click(screen.getByRole('button', {name: 'Insert into editor'}));
    await waitFor(() => expect(onInsert).toHaveBeenCalledWith({
      source: 'SELECT\n  *\nFROM main.customers', languageProfile: 'sqlite-sql'}));
    expect(onClose).toHaveBeenCalled();
    expect(post.mock.calls.map(([payload]) => payload.request.operation))
      .toEqual(['options', 'source', 'source']);
    expect(post.mock.calls[2][0].request.model).toEqual({query: {selects: [{
      from: {source: {relation: ['main', 'customers']}}}]}});
  });

  it('shows the server refusal and keeps the dialog open', async () => {
    const refusal = Object.assign(new Error('Request failed'), {response: {data: {
      errormsg: 'Right outer join is not available here: Needs a newer SQLite.'}}});
    const post = jest.fn((payload) => payload.request.operation === 'options' ?
      Promise.resolve(optionsResponse()) : Promise.reject(refusal));
    const {onInsert, onClose} = renderDialog(post);
    await screen.findByRole('combobox', {name: 'Query FROM'});
    await act(async () => {
      fireEvent.click(screen.getByRole('button', {name: 'Insert into editor'}));
    });
    expect(await screen.findByText('Right outer join is not available here: Needs a newer SQLite.'))
      .toBeInTheDocument();
    expect(onInsert).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });
});
