/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import Theme from '../../../pgadmin/static/js/Theme';
import LoginPage from '../../../pgadmin/static/js/SecurityPages/LoginPage';
import { releaseLabel } from '../../../pgadmin/static/js/SecurityPages/BasePage';

describe('LoginPage', ()=>{

  beforeEach(() => window.localStorage.clear());
  afterEach(() => window.localStorage.clear());

  let ctrlMount = (props)=>{
    return render(<Theme>
      <LoginPage {...props}/>
    </Theme>);
  };

  it('renders user name, user password, and database key prompt', ()=>{
    const ctrl = ctrlMount({
      userLanguage: 'en',
      langOptions: [{
        label: 'English',
        value: 'en',
      }],
      forgotPassUrl: '/forgot/url',
      csrfToken: 'some-token',
      loginUrl: '/login/url',
      authSources: ['internal'],
      authSourcesEnum: {
        OAUTH2: 'oauth2',
        KERBEROS: 'kerberos'
      },
      oauth2Config: [],
      loginBanner: 'login banner',
      productVersion: '0.325-alpha',
      vaultInitialized: false,
      vaultEngine: 'firebird-embedded',
    });
    expect(ctrl.container.querySelector('form').getAttribute('action')).toBe('/login/url');
    expect(screen.getByLabelText('User name')).toHaveAttribute('name', 'email');
    expect(screen.getByLabelText('User password')).toHaveAttribute('name', 'password');
    expect(screen.getByLabelText('Database key')).toHaveAttribute('name', 'database_key');
    expect(screen.getByText(/Encrypted UserConfigurationDatabase \(FirebirdSQL Embedded\)/i))
      .toBeInTheDocument();
    expect(screen.getByText(/First-run setup:/i)).toBeInTheDocument();
    expect(screen.getByText('Welcome to ScratchRobin')).toBeInTheDocument();
    const brand = screen.getByRole('complementary', {name: 'About ScratchRobin'});
    expect(brand).toHaveAttribute('data-cdeadmin-qa-key',
      'security.login.product-identity');
    expect(brand).toHaveTextContent('Open-source project · Alpha 0.325');
    expect(brand).toHaveTextContent(
      'Only a few of its supported platforms, and part of its functionality, are ready for review.');
    expect(brand).toHaveTextContent('ScratchBird Software Inc.');
    expect(screen.getByRole('button', {name: 'Sign in'}))
      .toHaveAttribute('name', 'internal_button');
    expect(screen.queryByLabelText('Enable QA visual element IDs'))
      .not.toBeInTheDocument();
    expect(screen.queryByText(/QA mode — show visual element IDs on hover/i))
      .not.toBeInTheDocument();
  });

  it('does not expose developer QA mode toggle on the production login form', ()=>{
    ctrlMount({userLanguage: 'en', langOptions: [{label: 'English',
      value: 'en'}], forgotPassUrl: '/forgot/url', csrfToken: 'some-token',
    loginUrl: '/login/url', authSources: ['internal'], authSourcesEnum: {
      OAUTH2: 'oauth2', KERBEROS: 'kerberos'}, oauth2Config: [], loginBanner: ''});
    expect(screen.queryByLabelText('Enable QA visual element IDs')).toBeNull();
  });

  it('reveals and hides browser-autofilled credentials and database key without losing their values', async ()=>{
    const ctrl = ctrlMount({userLanguage: 'en', langOptions: [],
      authSources: ['internal'], authSourcesEnum: {OAUTH2: 'oauth2'}, oauth2Config: []});
    const email = ctrl.container.querySelector('input[name="email"]');
    const password = ctrl.container.querySelector('input[name="password"]');
    const dbKey = ctrl.container.querySelector('input[name="database_key"]');
    expect(email).toHaveAttribute('autocomplete', 'username');
    expect(password).toHaveAttribute('autocomplete', 'current-password');
    expect(password).toHaveAttribute('type', 'password');
    expect(dbKey).toHaveAttribute('type', 'password');
    expect(password).toBeRequired();
    expect(dbKey).toBeRequired();
    // Model autofill that does not dispatch React's change event.
    email.value = 'dcalford';
    password.value = 'autofilled-test-value';
    dbKey.value = 'autofilled-db-key';
    expect(screen.getByRole('button', {name: 'Sign in'})).toBeEnabled();
    fireEvent.click(screen.getByLabelText('Show password'));
    await waitFor(() => expect(password).toHaveAttribute('type', 'text'));
    expect(dbKey).toHaveAttribute('type', 'text');
    expect(password).toHaveValue('autofilled-test-value');
    expect(dbKey).toHaveValue('autofilled-db-key');
    expect(email).toHaveValue('dcalford');
    fireEvent.click(screen.getByLabelText('Show password'));
    expect(password).toHaveAttribute('type', 'password');
    expect(dbKey).toHaveAttribute('type', 'password');
    expect(password).toHaveValue('autofilled-test-value');
    expect(dbKey).toHaveValue('autofilled-db-key');
    ctrl.unmount();
    ctrlMount({authSources: ['internal'], authSourcesEnum: {OAUTH2: 'oauth2'}, oauth2Config: []});
    expect(screen.getByLabelText('Show password')).not.toBeChecked();
  });

  it('hides internal authentication inputs and omits QA toggle when only OAuth2 is enabled', ()=>{
    const ctrl = ctrlMount({userLanguage: 'en', langOptions: [],
      forgotPassUrl: '/forgot/url', csrfToken: 'some-token',
      loginUrl: '/login/url', authSources: ['oauth2'], authSourcesEnum: {
        OAUTH2: 'oauth2', KERBEROS: 'kerberos'}, oauth2Config: [{
        OAUTH2_NAME: 'github', OAUTH2_BUTTON_COLOR: '#fff',
        OAUTH2_ICON: 'fa-github', OAUTH2_DISPLAY_NAME: 'Github'}],
      loginBanner: ''});
    expect(ctrl.container.querySelector('input[name="email"]')).toBeNull();
    expect(screen.queryByLabelText('Enable QA visual element IDs')).toBeNull();
  });

  it('oauth2', ()=>{
    const ctrl = ctrlMount({
      userLanguage: 'en',
      langOptions: [{
        label: 'English',
        value: 'en',
      }],
      forgotPassUrl: '/forgot/url',
      csrfToken: 'some-token',
      loginUrl: '/login/url',
      authSources: ['internal', 'oauth2'],
      authSourcesEnum: {
        OAUTH2: 'oauth2',
        KERBEROS: 'kerberos'
      },
      oauth2Config: [{
        OAUTH2_NAME: 'github',
        OAUTH2_BUTTON_COLOR: '#fff',
        OAUTH2_ICON: 'fa-github',
        OAUTH2_DISPLAY_NAME: 'Github'
      }],
      loginBanner: ''
    });
    expect(ctrl.container.querySelector('form').getAttribute('action')).toBe('/login/url');
    expect(ctrl.container.querySelector('input[name="email"]')).not.toBeNull();
    expect(ctrl.container.querySelector('input[name="password"]')).not.toBeNull();
    expect(ctrl.container.querySelector('input[name="database_key"]')).not.toBeNull();
    expect(ctrl.container.querySelector('button[name="oauth2_button"]')).toHaveValue('github');
  });

  it('reads the release from the product version', ()=>{
    expect(releaseLabel('0.325-alpha')).toBe('Alpha 0.325');
    expect(releaseLabel('1.0')).toBe('1.0');
    expect(releaseLabel(undefined)).toBeNull();
  });
});
