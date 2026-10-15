import {render, screen} from '@testing-library/react';
import MySQLQueryOptions from 'sources/cdeadmin_ui/editors/MySQLQueryOptions';
import {withTheme} from '../fake_theme';
const Component = withTheme(MySQLQueryOptions);

describe('Native MySQL-family query observations', () => {
  it('shows MariaDB native analysis and parameter syntax without inventing unavailable observations', () => {
    const {rerender} = render(<Component engine="mariadb" />);
    expect(screen.getByRole('table', {name: 'MariaDB session observation'})).toBeVisible();
    expect(screen.getAllByText('Not observed')).toHaveLength(3);
    expect(screen.getByText(/ANALYZE FORMAT=JSON executes/)).toBeVisible();
    expect(screen.getByText(/Parameters use \? or %s/)).toBeVisible();
    expect(screen.queryByText(/EXPLAIN ANALYZE executes/)).toBeNull();
    rerender(<Component engine="mariadb" transaction={{provider_payload: {state: 'active', autocommit: false, in_transaction: true}}} />);
    expect(screen.getByText('active')).toBeVisible();
    expect(screen.getByText('Off')).toBeVisible();
    expect(screen.getByText('On')).toBeVisible();
  });
  it('retains native MySQL labels, analysis and parameter syntax', () => {
    render(<Component />);
    expect(screen.getByRole('table', {name: 'MySQL session observation'})).toBeVisible();
    expect(screen.getByText(/EXPLAIN ANALYZE executes/)).toBeVisible();
    expect(screen.queryByText(/ANALYZE FORMAT=JSON executes/)).toBeNull();
  });
});
