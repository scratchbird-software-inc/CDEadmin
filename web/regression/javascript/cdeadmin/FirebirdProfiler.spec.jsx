import {render, screen} from '@testing-library/react';
import FirebirdProfiler from 'sources/Dialogs/FirebirdProfiler';
import {withTheme} from '../fake_theme';

const Component = withTheme(FirebirdProfiler);

describe('Firebird native diagnostics', () => {
  it('identifies exact attachment samples and unavailable/reset measurements', () => {
    render(<Component statistics={{scope: 'current attachment sampling window', elapsed: '9007199254740993',
      complete: false, before: {attachment_id: '101', counters: {page_reads: 8}},
      after: {attachment_id: '101', counters: {page_reads: 2}}, deltas: {page_reads: null},
      unavailable_reasons: ['counter-reset'], reset_counters: ['page_reads']}} />);
    expect(screen.getByText(/Sampled attachment: before 101; after 101/)).toBeVisible();
    expect(screen.getByText(/9007199254740993 nanoseconds/)).toBeVisible();
    expect(screen.getByText(/Incomplete measurements: counter-reset/)).toHaveTextContent('Reset counters: page_reads');
    expect(screen.getByText('Unavailable / reset')).toBeVisible();
  });
  it('shows profiler admission uncertainty without suggesting a successful profile', () => {
    render(<Component report={{state: 'admission-unknown', profile_id: null, sections: {},
      errors: [{stage: 'admission', error_type: 'RelationalClientError', native_status_codes: []}]}} />);
    expect(screen.getByText(/Native profile unavailable: admission-unknown/)).toBeVisible();
    expect(screen.getByText(/do not rerun SQL/)).toBeVisible();
    expect(screen.queryByRole('table')).toBeNull();
  });
});
