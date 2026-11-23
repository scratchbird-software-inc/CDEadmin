/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import ChangeOwnershipContent from 'sources/Dialogs/ChangeOwnershipContent';
import ChangePasswordContent from 'sources/Dialogs/ChangePasswordContent';
import ConfirmSaveContent from 'sources/Dialogs/ConfirmSaveContent';
import NamedRestoreContent from 'sources/Dialogs/NamedRestoreContent';
import RenameTabContent from 'sources/Dialogs/RenameTabContent';
import MasterPasswordContent from 'sources/Dialogs/MasterPasswordContent';
import ConfirmPromotionContent from '../../../pgadmin/tools/sqleditor/static/js/components/dialogs/ConfirmPromotionContent';
import FilterDialog from '../../../pgadmin/tools/sqleditor/static/js/components/dialogs/FilterDialog';
import MacrosDialog from '../../../pgadmin/tools/sqleditor/static/js/components/dialogs/MacrosDialog';
import {QueryToolContext} from '../../../pgadmin/tools/sqleditor/static/js/components/QueryToolComponent';

jest.mock('sources/url_for', () => jest.fn((endpoint) => `/${endpoint}`));
jest.mock(
  '../../../pgadmin/tools/sqleditor/static/js/components/QueryToolComponent',
  () => {
    const React = require('react');
    return {
      QueryToolContext: React.createContext(null),
      getRandomName: () => 'Macro 1',
    };
  }
);

describe('Wave 4 Unified ScratchRobin Dialogs & Standardized Grids', () => {
  it('ChangeOwnershipContent confirms deletion when no user is selected and saves selected owner', async () => {
    const onSave = jest.fn().mockResolvedValue({});
    const onClose = jest.fn();
    render(
      <ChangeOwnershipContent
        deletedUser="alice"
        noOfSharedServers={3}
        userList={[{value: '7', label: 'bob'}]}
        onSave={onSave}
        onClose={onClose}
      />
    );

    // Clicking Change with empty user prompts inline confirmation first
    fireEvent.click(screen.getByRole('button', {name: 'Change'}));
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByRole('button', {name: 'Confirm Delete'})).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Confirm Delete'}));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith(true, {newUser: ''}));
  });

  it('ChangePasswordContent validates password match and submits payload with csrf_token', async () => {
    const onSave = jest.fn().mockResolvedValue({});
    const getInitData = jest.fn().mockResolvedValue({user: 'admin', csrf_token: 'tok-123'});
    render(
      <ChangePasswordContent
        getInitData={getInitData}
        onSave={onSave}
        onClose={jest.fn()}
        hasCsrfToken
        showUser
      />
    );

    await waitFor(() => expect(screen.getByDisplayValue('admin')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/Current Password/), {target: {value: 'old-pw'}});
    fireEvent.change(screen.getByLabelText(/^New Password/), {target: {value: 'new-pw'}});
    fireEvent.change(screen.getByLabelText(/Confirm Password/), {target: {value: 'wrong'}});

    expect(screen.getByText('Passwords do not match.')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Change'})).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Confirm Password/), {target: {value: 'new-pw'}});
    const saveBtn = screen.getByRole('button', {name: 'Change'});
    expect(saveBtn).toBeEnabled();
    fireEvent.click(saveBtn);

    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith(true, {
        user: 'admin',
        password: 'old-pw',
        newPassword: 'new-pw',
        confirmPassword: 'new-pw',
        csrf_token: 'tok-123',
      })
    );
  });

  it('NamedRestoreContent, RenameTabContent, ConfirmSaveContent, MasterPasswordContent, and ConfirmPromotionContent preserve action contracts', () => {
    const onOKRestore = jest.fn();
    const closeRestore = jest.fn();
    const {unmount: u1} = render(
      <NamedRestoreContent onOK={onOKRestore} closeModal={closeRestore} />
    );
    expect(screen.getByRole('button', {name: 'OK'})).toBeDisabled();
    fireEvent.change(
      screen.getByLabelText('Enter the name of the restore point to add'),
      {target: {value: 'rp_before_migration'}}
    );
    fireEvent.click(screen.getByRole('button', {name: 'OK'}));
    expect(onOKRestore.mock.calls[0][0].get('value')).toBe('rp_before_migration');
    u1();

    const setTitle = jest.fn();
    const setInternalAttrs = jest.fn();
    const closeRename = jest.fn();
    const docker = {
      find: () => ({internal: {title: 'Query 1*', isDirty: true}}),
      setTitle,
      setInternalAttrs,
    };
    const {unmount: u2} = render(
      <RenameTabContent panelId="p1" panelDocker={docker} closeModal={closeRename} />
    );
    fireEvent.change(screen.getByLabelText('New tab title'), {target: {value: 'Orders Audit'}});
    fireEvent.click(screen.getByRole('button', {name: 'OK'}));
    expect(setTitle).toHaveBeenCalledWith('p1', 'Orders Audit*');
    expect(setInternalAttrs).toHaveBeenCalledWith('p1', {orig_title: 'Query 1'});
    u2();

    const onSave = jest.fn();
    const {unmount: u3} = render(
      <ConfirmSaveContent text="Unsaved SQL" onSave={onSave} onDontSave={jest.fn()} closeModal={jest.fn()} />
    );
    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    expect(onSave).toHaveBeenCalledTimes(1);
    u3();

    const onMasterOK = jest.fn();
    const {unmount: u4} = render(
      <MasterPasswordContent
        isPWDPresent
        keyringName=""
        data={{errmsg: ''}}
        onOK={onMasterOK}
        closeModal={jest.fn()}
      />
    );
    fireEvent.change(screen.getByLabelText('Master password'), {target: {value: 'vault-secret'}});
    fireEvent.click(screen.getByRole('button', {name: 'OK'}));
    expect(onMasterOK.mock.calls[0][0].get('password')).toBe('vault-secret');
    u4();

    const onPromote = jest.fn();
    render(
      <ConfirmPromotionContent text="Promote to Query Tool?" onContinue={onPromote} closeModal={jest.fn()} />
    );
    fireEvent.click(screen.getByRole('checkbox', {name: 'Don\'t ask again'}));
    fireEvent.click(screen.getByRole('button', {name: 'Continue'}));
    expect(JSON.parse(onPromote.mock.calls[0][0].get('pref_data'))[0]).toMatchObject({
      name: 'view_edit_promotion_warning',
      value: false,
      module: 'sqleditor',
    });
  });

  it('FilterDialog and MacrosDialog render standardized RecordGrid with Grid/Hybrid/Mini/Form switcher', async () => {
    const api = {
      get: jest.fn(async (url) => {
        if (url.includes('get_filter_data')) {
          return {
            data: {
              data: {
                result: {
                  column_list: ['id', 'created_at'],
                  data_sorting: [{name: 'id', order: 'asc'}],
                  sql: 'id > 10',
                },
              },
            },
          };
        }
        if (url.includes('get_user_macros')) {
          return {data: [{id: 1, name: 'Count rows', sql: 'SELECT count(*) FROM t;'}]};
        }
        if (url.includes('get_macros')) {
          return {data: {macro: [{id: 1, key_label: 'Alt+1'}, {id: 2, key_label: 'Alt+2'}]}};
        }
        return {data: {}};
      }),
      put: jest.fn(async () => ({data: {data: {status: true}, filter: () => []}})),
    };

    const ctx = {api, params: {trans_id: 99}};
    const ThemedFilter = withTheme(() => (
      <QueryToolContext.Provider value={ctx}>
        <FilterDialog onClose={jest.fn()} onSave={jest.fn()} />
      </QueryToolContext.Provider>
    ));
    const {unmount} = render(<ThemedFilter />);

    await waitFor(() => expect(screen.getByText('Data Sorting')).toBeInTheDocument());
    expect(screen.getByRole('button', {name: 'Hybrid view'})).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Full-form view'})).toBeInTheDocument();
    unmount();

    const ThemedMacros = withTheme(() => (
      <QueryToolContext.Provider value={ctx}>
        <MacrosDialog onClose={jest.fn()} onSave={jest.fn()} />
      </QueryToolContext.Provider>
    ));
    render(<ThemedMacros />);
    await waitFor(() => expect(screen.getAllByDisplayValue('Count rows').length).toBeGreaterThanOrEqual(1));
    expect(screen.getByRole('button', {name: 'Hybrid view'})).toBeInTheDocument();
  });
});
