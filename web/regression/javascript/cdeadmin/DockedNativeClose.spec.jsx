import {LayoutDocker} from 'sources/helpers/Layout';
import {createCloseGuardRegistry} from 'sources/helpers/ModalCloseGuard';

function dock(beforeClose) {
  const value = new LayoutDocker('owned-layout', null);
  const panel = {id: 'native-panel', internal: {closable: true}, beforeClose};
  let present = true;
  value.find = jest.fn(id => present && id === panel.id ? panel : null);
  value.layoutObj = {dockMove: jest.fn(() => {present = false;})};
  return value;
}

it('retains the docked native session until its asynchronous release has returned', async () => {
  let released;
  const registry = createCloseGuardRegistry();
  registry.register(() => new Promise(resolve => {released = resolve;}));
  const value = dock(registry.beforeClose);
  const closing = value.close('native-panel');
  expect(value.close('native-panel')).toBe(closing);
  await Promise.resolve();
  expect(value.layoutObj.dockMove).not.toHaveBeenCalled();
  released(true);
  await expect(closing).resolves.toBe(true);
  expect(value.layoutObj.dockMove).toHaveBeenCalledTimes(1);
  value.workspaceHost.dispose();
});

it.each(['busy', 'failed release'])('keeps the panel after %s instead of losing its native state', async reason => {
  const registry = createCloseGuardRegistry();
  const remove = registry.register(async () => {
    if(reason === 'failed release') throw new Error('Native release unconfirmed');
    return false;
  });
  const value = dock(registry.beforeClose);
  await expect(value.close('native-panel')).resolves.toBe(false);
  expect(value.layoutObj.dockMove).not.toHaveBeenCalled();
  remove();
  await expect(value.close('native-panel')).resolves.toBe(true);
  expect(value.layoutObj.dockMove).toHaveBeenCalledTimes(1);
  value.workspaceHost.dispose();
});

it('preserves a registered close guard when converting a provider panel to dock data', () => {
  const beforeClose = jest.fn();
  const panel = LayoutDocker.getPanel({id: 'native', title: 'Owned native task', closable: true, beforeClose});
  expect(panel.beforeClose).toBe(beforeClose);
});
