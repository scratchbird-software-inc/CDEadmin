/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {waitFor} from '@testing-library/react';
import pgAdmin from 'sources/pgadmin';
import getApiInstance from '../../../pgadmin/static/js/api_instance';
import {showEndpointVerification, showProviderWorkspace} from
  '../../../pgadmin/static/js/Dialogs/index';
import {BROWSER_PANELS} from '../../../pgadmin/browser/static/js/constants';
import endpointProfiles from 'pgadmin.cdeadmin.endpoint_profiles';

jest.mock('../../../pgadmin/static/js/api_instance');

describe('provider endpoint verification', () => {
  let api;
  let node;

  beforeEach(() => {
    api = {post: jest.fn().mockResolvedValue({data: {success: 1}})};
    getApiInstance.mockReturnValue(api);
    pgAdmin.Browser.notifier.showModal = jest.fn();
    pgAdmin.Browser.docker = {default_workspace: {
      openTab: jest.fn(), close: jest.fn(),
    }};
    node = {generate_url: jest.fn().mockReturnValue('/verify/1')};
  });

  it('does not invent a password prompt for a passwordless provider',
    async () => {
      const onSuccess = jest.fn();
      showEndpointVerification(
        'Verify Endpoint', node,
        {cde_profile_id: 'embedded-native', label: 'SQLite'},
        {}, {}, onSuccess, jest.fn()
      );
      await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
      expect(api.post.mock.calls[0][1]).toBeInstanceOf(FormData);
      expect(pgAdmin.Browser.notifier.showModal).not.toHaveBeenCalled();
      expect(onSuccess).toHaveBeenCalledTimes(1);
    });

  it('does not prompt for an explicit passwordless account', async () => {
    // Owner direction 2026-10-29: passwordless accounts are supported even on
    // providers whose accounts normally need a password.
    const onSuccess = jest.fn();
    showEndpointVerification(
      'Verify Endpoint', node,
      {cde_profile_id: 'qualified-native', label: 'Secured engine',
        cde_passwordless: true},
      {}, {}, onSuccess, jest.fn()
    );
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    expect(pgAdmin.Browser.notifier.showModal).not.toHaveBeenCalled();
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it('prompts before verification when the provider requires a secret',
    () => {
      showEndpointVerification(
        'Verify Endpoint', node,
        {cde_profile_id: 'qualified-native', label: 'Secured engine'},
        {}, {}, jest.fn(), jest.fn()
      );
      expect(pgAdmin.Browser.notifier.showModal).toHaveBeenCalledTimes(1);
      expect(api.post).not.toHaveBeenCalled();
    });

  it('uses the selected registration principal for its password prompt', async () => {
    const profile = jest.spyOn(endpointProfiles, 'get').mockReturnValue({
      profile_id: 'firebird-native', route_kind: 'network', requires_secret: false,
    });
    try {
      api.post.mockResolvedValueOnce({data: {data: {targets: [{target_id: 'alias',
        registration_credentials: true, registration_user: 'ALICE', display_name: 'Private alias'}]}}})
        .mockRejectedValueOnce({response: {status: 401}});
      await showEndpointVerification('Verify', node, {cde_profile_id: 'firebird-native',
        username: 'SYSDBA', label: 'Server'}, {}, {}, jest.fn(), jest.fn(), 'alias');
      await waitFor(() => expect(pgAdmin.Browser.notifier.showModal).toHaveBeenCalled());
      const form = pgAdmin.Browser.notifier.showModal.mock.calls[0][1](jest.fn());
      expect(form.props.data.username).toBe('ALICE');
      expect(form.props.data.server_label).toBe('Server / Private alias');
      expect(api.post.mock.calls[1][1].get('database_target_id')).toBe('alias');
    } finally {profile.mockRestore();}
  });

  it('opens registration transfer locally with the exact target and operation', () => {
    showProviderWorkspace('Move registration', node, {_id: 7}, {}, 'firebird-registration', {
      database_target_id: 'alias', registration_operation: 'move',
    });
    const content = pgAdmin.Browser.docker.default_workspace.openTab.mock.calls[0][0].content.props.children.props.children;
    expect(content.props.targetId).toBe('alias');
    expect(content.props.operation).toBe('move');
  });

  it.each([null, 'database-one'])(
    'retains the focused service task with database scope %s', (targetId) => {
      showProviderWorkspace('Recover shadow', node, {}, {}, 'administration', {
        resource_kind: 'database', operation_id: 'activate_shadow',
        database_target_id: targetId,
      });
      const content = pgAdmin.Browser.docker.default_workspace.openTab
        .mock.calls[0][0].content.props.children.props.children;
      const url = new URL(content.props.endpointUrl, 'http://localhost');
      expect(url.searchParams.get('focused_operation_id'))
        .toBe('activate_shadow');
      expect(url.searchParams.get('database_target_id')).toBe(targetId);
    });

  it.each(['monitoring', 'monitoring_policy'])(
    'routes %s to the selected native monitoring scope', (tab) => {
      showProviderWorkspace('Monitoring', node, {_id: 7}, {}, tab, {
        database_target_id: 'target-one',
      });
      const content = pgAdmin.Browser.docker.default_workspace.openTab
        .mock.calls[0][0].content.props.children.props.children;
      expect(content.props.serverId).toBe(7);
      expect(content.props.targetId).toBe('target-one');
      expect(content.props.policyMode).toBe(tab === 'monitoring_policy');
    });

  it('wires committed profile changes to only the owning navigator endpoint', () => {
    const item = {id: 'owned-endpoint'};
    const data = {cde_endpoint: true, runtime_verification_state: 'verified',
      cde_session_authenticated: true, is_password_saved: true};
    const other = {cde_endpoint: true, runtime_verification_state: 'verified'};
    const previousTree = pgAdmin.Browser.tree;
    pgAdmin.Browser.tree = {
      itemData: jest.fn((value) => value === item ? data : other),
      addIcon: jest.fn(), setLabel: jest.fn(),
    };
    try {
      showProviderWorkspace('Edit endpoint', node, data, item, 'connections', {
        server_mode: 'edit',
      });
      const content = pgAdmin.Browser.docker.default_workspace.openTab
        .mock.calls[0][0].content.props.children.props.children;
      expect(data.runtime_verification_state).toBe('verified');
      content.props.onEndpointProfileSaved({display_name: 'Owned Firebird'});
      expect(data.runtime_verification_state).toBe('stale');
      expect(data.cde_session_authenticated).toBe(false);
      expect(data.is_password_saved).toBe(true);
      expect(other.runtime_verification_state).toBe('verified');
      expect(pgAdmin.Browser.tree.addIcon).toHaveBeenCalledWith(item, {
        icon: 'icon-server-not-connected'});
    } finally {
      pgAdmin.Browser.tree = previousTree;
    }
  });

  it.each(['table', 'view', 'procedure', 'function', 'sequence', 'collection'])(
    'opens the %s editor in the main dock with independent close ownership', (kind) => {
      const workspace = pgAdmin.Browser.docker.default_workspace;
      const context = {resource_kind: kind, resource_id: 'object-one',
        database_target_id: 'database-one'};
      const first = showProviderWorkspace('Editor', node, {}, {}, 'object', context);
      const second = showProviderWorkspace('Editor', node, {}, {}, 'object', context);
      expect(first).not.toBe(second);
      expect(pgAdmin.Browser.notifier.showModal).not.toHaveBeenCalled();
      expect(workspace.openTab).toHaveBeenNthCalledWith(1,
        expect.objectContaining({id: first, title: 'Editor', closable: true,
          floatable: true}), BROWSER_PANELS.MAIN, 'middle');
      const content = workspace.openTab.mock.calls[0][0].content.props.children.props.children;
      expect(content.props.initialContext).toBe(context);
      expect(content.props.initialTab).toBe('object');
      content.props.closeModal();
      expect(workspace.close).toHaveBeenCalledWith(first);
      expect(workspace.close).not.toHaveBeenCalledWith(second);
    });
});
