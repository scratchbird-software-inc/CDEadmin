import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import FirebirdDocker from 'sources/Dialogs/FirebirdDocker';
import {withTheme} from '../fake_theme';

const Component = withTheme(FirebirdDocker);
const review = {review_id: 'owned-review', state: 'prepared', daemon: {endpoint: 'unix:///var/run/docker.sock', id: 'daemon'},
  configuration: {container: 'owned-firebird', port: 13050, database: 'test.fdb'}};
describe('Firebird desktop Docker form', () => {
  it('displays the discovered context before preparing its daemon', async () => {
    const bridge = {available: true, contexts: jest.fn().mockResolvedValue({contexts: [{name: 'desktop-linux', current: true, endpoint: 'unix:///owned/docker.sock'}]}),
      prepare: jest.fn().mockResolvedValue(review)};
    render(<Component bridge={bridge} />);
    fireEvent.click(screen.getByRole('button', {name: 'Read Docker contexts'}));
    await screen.findByText('desktop-linux — unix:///owned/docker.sock');
    fireEvent.click(screen.getByRole('button', {name: 'Prepare Docker deployment'}));
    await waitFor(() => expect(bridge.prepare).toHaveBeenCalledWith(expect.objectContaining({context: 'desktop-linux'})));
  });
  it('never provisions on the web application server', () => {
    render(<Component bridge={undefined} />);
    expect(screen.getByText(/web server does not start Docker/)).toBeVisible();
    expect(screen.getByRole('button', {name: 'Prepare Docker deployment'})).toBeDisabled();
  });
  it('requires resolved review, separate password and explicit creation confirmation', async () => {
    const bridge = {available: true, prepare: jest.fn().mockResolvedValue(review), apply: jest.fn().mockResolvedValue({...review, state: 'container_running'})};
    const register = jest.fn();
    render(<Component bridge={bridge} onRegister={register} />);
    fireEvent.click(screen.getByRole('button', {name: 'Prepare Docker deployment'}));
    const create = await screen.findByRole('button', {name: 'Create reviewed Firebird container'});
    expect(create).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Bootstrap SYSDBA password'), {target: {value: 'one-bootstrap'}});
    fireEvent.click(screen.getByLabelText('I approve creating these resources on the reviewed Docker daemon'));
    fireEvent.click(create);
    await screen.findByRole('button', {name: 'Open native registration form'});
    expect(bridge.apply).toHaveBeenCalledWith({review_id: 'owned-review', password: 'one-bootstrap', confirmed: true});
    expect(register).not.toHaveBeenCalled();
    expect(screen.getByRole('button', {name: 'Open native registration form'})).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Database host reachable by ScratchRobin'), {target: {value: '127.0.0.1'}});
    fireEvent.click(screen.getByRole('button', {name: 'Open native registration form'}));
    expect(register).toHaveBeenCalledWith({profile_id: 'firebird-native', registration_intent: 'register_existing',
      host: '127.0.0.1', port: 13050, database: '/var/lib/firebird/data/test.fdb', name: 'owned-firebird', username: 'SYSDBA'});
    expect(screen.queryByLabelText('Bootstrap SYSDBA password')).toBeNull();
  });
  it('retrieves a lost-response receipt without retrying a consumed review', async () => {
    const bridge = {available: true, prepare: jest.fn().mockResolvedValue(review), apply: jest.fn().mockRejectedValue(new Error('lost')),
      receipt: jest.fn().mockResolvedValue({...review, state: 'creating_container'})};
    render(<Component bridge={bridge} />);
    fireEvent.click(screen.getByRole('button', {name: 'Prepare Docker deployment'}));
    fireEvent.change(await screen.findByLabelText('Bootstrap SYSDBA password'), {target: {value: 'one-bootstrap'}});
    fireEvent.click(screen.getByLabelText('I approve creating these resources on the reviewed Docker daemon'));
    fireEvent.click(screen.getByRole('button', {name: 'Create reviewed Firebird container'}));
    await screen.findByText(/provisioning response was not received/);
    expect(screen.queryByRole('button', {name: 'Create reviewed Firebird container'})).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'Open Docker receipt'}));
    await waitFor(() => expect(bridge.receipt).toHaveBeenCalledWith('owned-review'));
    expect(bridge.apply).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', {name: 'Prepare Docker deployment'})).toBeDisabled();
  });
});
