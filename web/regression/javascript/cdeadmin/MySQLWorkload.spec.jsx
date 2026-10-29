import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import MySQLWorkload, { workloadDashboardFiles } from 'sources/Dialogs/MySQLWorkload';
import { withTheme } from '../fake_theme';
import viewer, { setupDDNDOM } from './ddnTestRuntime';
jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({
  DDNViewerSurface: props => <div data-testid="workload-viewer">{props.files['dashboard.ddn']}</div>
}));
const Component = withTheme(MySQLWorkload);
const row = {
  schema_name: 'demo',
  digest: 'a'.repeat(64),
  digest_text: 'SELECT ? <img src=x>',
  count_star: '9007199254740993',
  sum_timer_wait: '18446744073709551615',
  first_seen: {
    temporal: '2026-10-22T12:00:00'
  }
};
const snapshot = {
  groups: {
    workload_digests: {
      status: 'available',
      rows: [row],
      truncated: true
    }
  }
};
describe('MySQL workload investigation', () => {
  beforeAll(setupDDNDOM);
  it('does no native I/O until refresh and preserves exact native counters and escaped normalized SQL', async () => {
    const post = jest.fn(async () => snapshot);
    render(<Component post={post} />);
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {
      name: 'Refresh workload'
    }));
    await screen.findByText('9007199254740993');
    expect(screen.getByText('18446744073709551615')).toBeVisible();
    expect(document.querySelector('img')).toBeNull();
    expect(screen.getByTestId('workload-viewer')).toHaveTextContent('undetected resets remain possible');
    expect(post).toHaveBeenCalledWith({
      action: 'mysql_workload_snapshot',
      request: {
        database_target_id: null,
        schema_name: null,
        rank: 'total_latency'
      }
    });
    fireEvent.click(screen.getByRole('button', {
      name: 'Inspect digest 1'
    }));
    expect(post).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', {
      name: 'Inspect private native sample'
    })).toBeDisabled();
  });
  it('requires private consent, binds the current sample fingerprint and uses the native graphical plan', async () => {
    const post = jest.fn(async ({
      action
    }) => action.endsWith('_snapshot') ? snapshot : action.endsWith('_sample') ? {
      query_sample_text: 'SELECT \'private\'',
      sample_sha256: 'fingerprint'
    } : {
      rendered: {
        view_model: {
          columns: [{
            name: 'EXPLAIN'
          }],
          rows: [['{"query_block":{"message":"No tables used"}}']]
        }
      }
    });
    render(<Component post={post} />);
    fireEvent.click(screen.getByRole('button', {
      name: 'Refresh workload'
    }));
    fireEvent.click(await screen.findByRole('button', {
      name: 'Inspect digest 1'
    }));
    fireEvent.click(screen.getByRole('checkbox', {
      name: /Allow private SQL/
    }));
    fireEvent.click(screen.getByRole('button', {
      name: 'Inspect private native sample'
    }));
    await screen.findByLabelText('Private native SQL sample');
    fireEvent.click(screen.getByRole('button', {
      name: 'Capture native estimated plan'
    }));
    await screen.findByRole('tree', {
      name: 'Native MySQL operator graph'
    });
    expect(post.mock.calls[2][0]).toEqual({
      action: 'mysql_workload_plan',
      request: {
        database_target_id: null,
        schema_name: 'demo',
        digest: row.digest,
        confirmed: true,
        sample_sha256: 'fingerprint'
      }
    });
    fireEvent.click(screen.getByRole('button', {
      name: 'Clear private SQL'
    }));
    expect(screen.queryByLabelText('Private native SQL sample')).toBeNull();
    expect(screen.queryByRole('tree')).toBeNull();
  });
  it('does not restore private SQL from a late response after clearing consent', async () => {
    let reply;
    const post = jest.fn().mockResolvedValueOnce(snapshot).mockImplementation(() => new Promise(resolve => {
      reply = resolve;
    }));
    const mounted = render(<Component post={post} />);
    fireEvent.click(screen.getByRole('button', {
      name: 'Refresh workload'
    }));
    fireEvent.click(await screen.findByRole('button', {
      name: 'Inspect digest 1'
    }));
    fireEvent.click(screen.getByRole('checkbox', {
      name: /Allow private SQL/
    }));
    fireEvent.click(screen.getByRole('button', {
      name: 'Inspect private native sample'
    }));
    mounted.rerender(<Component post={post} databaseTargetId="another" />);
    await act(async () => reply({
      query_sample_text: 'late-private'
    }));
    expect(screen.queryByText('late-private')).toBeNull();
    expect(screen.queryByLabelText('Private native SQL sample')).toBeNull();
  });
  it('discloses denied digest observations and never infers zero workload', async () => {
    render(<Component post={async () => ({
      groups: {
        workload_digests: {
          status: 'unavailable',
          error_code: 1142
        }
      }
    })} />);
    fireEvent.click(screen.getByRole('button', {
      name: 'Refresh workload'
    }));
    await waitFor(() => expect(screen.getByRole('table', {
      name: 'Ranked native statement digests'
    })).toBeVisible());
    expect(screen.getByText(/Empty or disabled instrumentation does not mean no workload/)).toBeVisible();
    expect(screen.queryByRole('button', {
      name: 'Inspect digest 1'
    })).toBeNull();
  });
  it('separates retained direct waits from server-wide waits and surfaces coverage', async () => {
    const post = jest.fn().mockResolvedValueOnce(snapshot).mockResolvedValueOnce({
      coverage: 'Only retained direct waits; empty is incomplete',
      groups: {
        direct_statement_waits: {
          status: 'available',
          rows: [{
            event_name: 'wait/io/file',
            count_star: '9'
          }]
        }
      }
    });
    render(<Component post={post} />);
    fireEvent.click(screen.getByRole('button', {
      name: 'Refresh workload'
    }));
    fireEvent.click(await screen.findByRole('button', {
      name: 'Inspect digest 1'
    }));
    fireEvent.click(screen.getByRole('button', {
      name: 'Inspect retained direct waits'
    }));
    await screen.findByText('Only retained direct waits; empty is incomplete');
    expect(within(screen.getByRole('table', {
      name: 'Selected digest waits'
    })).getByText('9')).toBeVisible();
    expect(post.mock.calls[1][0].action).toBe('mysql_workload_waits');
  });
  it('uses DDN data-only quoting and does not label cumulative counts as rates', async () => {
    const files = workloadDashboardFiles({
      groups: {
        workload_waits: {
          status: 'available',
          rows: [{
            event_name: 'wait "quoted" <script>',
            sum_timer_wait: '999999999999999999',
            count_star: '3'
          }]
        }
      }
    });
    expect(files['dashboard.ddn']).toContain('999999999999999999');
    expect(files['dashboard.ddn']).toContain('picoseconds; count 3');
    expect(files['dashboard.ddn']).not.toContain('x_record.rate: "3"');
    const workspace = await viewer.createWorkspace(files);
    try {
      expect((await workspace.render({
        entry: 'dashboard.ddn',
        view: 'dashboard'
      })).diagnostics.filter(row => row.severity === 'error')).toEqual([]);
    } finally {
      workspace.destroy();
    }
  });
});
