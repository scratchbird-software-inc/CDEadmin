import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeMenuTemplate} from './menuTemplate.js';

test('application command IDs cannot replace native Electron command IDs', () => {
  const click = () => {};
  const application = [{name: 'application', label: 'Application', submenu: [{
    name: 'mnu_preferences', commandId: 'legacy.application.mnu_preferences',
    commandVersion: 1, priority: 10, label: 'Preferences', type: 'checkbox',
    checked: false, enabled: true, click,
  }, {type: 'separator'}, {role: 'quit'}]}];
  const template = nativeMenuTemplate(application);
  assert.deepEqual(template, [{label: 'Application', submenu: [{
    label: 'Preferences', type: 'checkbox', checked: false, enabled: true, click,
  }, {type: 'separator'}, {role: 'quit'}]}]);
  template[0].submenu[0].click();
  assert.equal(application[0].submenu[0].commandId, 'legacy.application.mnu_preferences');
});
