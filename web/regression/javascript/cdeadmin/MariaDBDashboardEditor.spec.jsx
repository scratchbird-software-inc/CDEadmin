import { render, screen } from '@testing-library/react';
import Editor from 'sources/Dialogs/FirebirdDashboardEditor';
import getApiInstance from 'sources/api_instance';
import pgAdmin from 'sources/pgadmin';
import { libraries } from './ddnTestRuntime';
import { loadDDNLibraries } from 'sources/cdeadmin_ui/integrations/ddn/library';
import { withTheme } from '../fake_theme';
jest.mock('sources/api_instance');
jest.mock('sources/cdeadmin_ui/integrations/ddn/library');
jest.mock('sources/url_for', () => (name, params) => '/' + name + (params ? '/' + params.sid : ''));
let mockProps;
jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({
  DDNDesignerSurface: props => {
    mockProps = props;
    return <div>Native MariaDB designer</div>;
  }
}));
describe('MariaDB dashboard editor delegation', () => {
  const Component = withTheme(Editor);
  it('seeds the paired designer with native identities and strips sampled values', async () => {
    pgAdmin.Browser = {
      docker: {
        default_workspace: {
          eventBus: {
            registerListener: () => jest.fn()
          }
        }
      }
    };
    loadDDNLibraries.mockResolvedValue(libraries);
    const api = {
      get: jest.fn().mockResolvedValueOnce({
        data: {
          data: {
            assetRef: {
              assetVersion: 0
            },
            snapshot: null
          }
        }
      }).mockResolvedValueOnce({
        data: {
          data: {
            state: 'collecting',
            sample_age_seconds: 1,
            stale_after_seconds: 15,
            samples: [{
              scope: 'database',
              status: 'partial',
              transaction_completed: true,
              groups: {
                status: {
                  status: 'available',
                  scope: 'server',
                  rows: [{
                    variable_name: 'Questions',
                    variable_value: 'PRIVATE_SAMPLE_123'
                  }]
                }
              }
            }]
          }
        }
      })
    };
    getApiInstance.mockReturnValue(api);
    render(<Component engine="mariadb" serverId={7} targetId="mysql:demo" panelId="mysql-editor" />);
    await screen.findByText('Native MariaDB designer');
    expect(api.get).toHaveBeenCalledWith('/cdeadmin_mariadb_monitoring.definition?sid=7&target_id=mysql%3Ademo');
    expect(api.get).toHaveBeenCalledWith('/cdeadmin_mariadb_monitoring.monitoring/7?target_id=mysql%3Ademo');
    expect(mockProps.snapshot.files['dashboard.ddn']).toContain('Questions: variable_value');
    expect(mockProps.snapshot.files['dashboard.ddn']).not.toContain('PRIVATE_SAMPLE_123');
    expect(screen.getByText('SR-F-001405')).toBeVisible();
  });
});
