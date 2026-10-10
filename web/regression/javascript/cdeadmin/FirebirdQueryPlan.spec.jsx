import {render, screen} from '@testing-library/react';
import FirebirdQueryPlan from '../../../pgadmin/static/js/Dialogs/FirebirdQueryPlan';

describe('Firebird native plan presentation', () => {
  it('preserves plan formats and warns about native truncation without claiming execution', () => {
    render(<FirebirdQueryPlan result={{statement_type: 'DELETE', parameter_count: 1,
      column_count: 0, client_sql_dialect: 3, transaction_started: false,
      legacy: {text: 'PLAN café ...', supplied: true, truncated: true},
      detailed: {text: null, supplied: false, truncated: false}}} />);
    expect(screen.getByLabelText('Legacy plan text')).toHaveTextContent('PLAN café ...');
    expect(screen.getByText(/displayed text is incomplete/)).toBeVisible();
    expect(screen.getByText(/supplied no plan text/)).toBeVisible();
    expect(screen.getByText(/statement was not executed/)).toHaveTextContent('Preparation used the existing transaction.');
  });
  it('reports a newly retained transaction and renders only returned plan text', () => {
    render(<FirebirdQueryPlan result={{transaction_started: true, statement_type: 'SELECT',
      parameter_count: 0, column_count: 1, client_sql_dialect: 1,
      legacy: {text: 'PLAN (T NATURAL)', supplied: true},
      detailed: {text: 'Select Expression\n  -> Table T Full Scan', supplied: true}}} />);
    expect(screen.getByText(/Preparation started a retained transaction/)).toBeVisible();
    expect(screen.getByLabelText('Detailed plan text').textContent).toBe('Select Expression\n  -> Table T Full Scan');
    expect(screen.queryByText(/incomplete/)).not.toBeInTheDocument();
  });
});
