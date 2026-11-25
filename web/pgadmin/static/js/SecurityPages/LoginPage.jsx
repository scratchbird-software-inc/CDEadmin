/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import { useRef, useState } from 'react';
import { InputSelectNonSearch, InputText, MESSAGE_TYPE, NotifierMessage } from '../components/FormComponents';
import BasePage, { SecurityButton } from './BasePage';
import gettext from 'sources/gettext';
import PropTypes from 'prop-types';

export default function LoginPage({
  userLanguage,
  langOptions,
  forgotPassUrl,
  csrfToken,
  loginUrl,
  authSources,
  authSourcesEnum,
  oauth2Config,
  loginBanner,
  vaultInitialized = true,
  vaultEngine = 'firebird-embedded',
  ...props
}) {
  const [form, setForm] = useState({
    email: '',
    password: '',
    database_key: '',
    language: userLanguage,
  });
  const [showPassword, setShowPassword] = useState(false);
  const formRef = useRef(null);

  // Hide login form if auth source is only oauth2 and/or kerberos. #5386
  const showLoginForm = !(
    ((authSources?.includes('oauth2') || authSources?.includes('kerberos')) &&
      authSources?.length == 1) ||
    (authSources?.includes('oauth2') &&
      authSources?.includes('kerberos') &&
      authSources?.length == 2)
  );

  const onTextChange = (n, val) => {
    setForm((prev) => ({...prev, [n]: val}));
  };

  const engineBadge =
    vaultEngine === 'firebird-server'
      ? gettext('Central Configuration Database (FirebirdSQL)')
      : gettext('Encrypted UserConfigurationDatabase (FirebirdSQL Embedded)');

  return (
    <>
      {loginBanner && (
        <NotifierMessage
          showIcon={false}
          closable={false}
          type={MESSAGE_TYPE.ERROR}
          message={loginBanner}
          style={{
            position: 'absolute',
            width: '80%',
            top: '30px',
            left: 0,
            right: 0,
            marginRight: 'auto',
            marginLeft: 'auto',
          }}
          textCenter
        />
      )}
      <BasePage
        title={gettext('Welcome to ScratchRobin')}
        subtitle={
          vaultInitialized === false
            ? gettext(
              'Initialize your user account and encrypt your UserConfigurationDatabase.'
            )
            : gettext(
              'Sign in and unlock your encrypted UserConfigurationDatabase.'
            )
        }
        brandQaKey="security.login.product-identity"
        {...props}
      >
        <form
          ref={formRef}
          data-cdeadmin-qa-key="security.login.form"
          style={{display: 'flex', gap: '14px', flexDirection: 'column'}}
          action={loginUrl}
          method="POST"
        >
          {showLoginForm && (
            <>
              <input name="csrf_token" defaultValue={csrfToken} hidden />
              <div
                data-cdeadmin-qa-key="security.login.vault-status"
                style={{
                  fontSize: '0.75rem',
                  lineHeight: 1.4,
                  padding: '8px 10px',
                  borderRadius: '6px',
                  background:
                    vaultInitialized === false
                      ? 'rgba(2, 132, 199, 0.10)'
                      : 'rgba(51, 102, 214, 0.08)',
                  border: '1px solid rgba(51, 102, 214, 0.24)',
                }}
              >
                <div style={{fontWeight: 600}}>{engineBadge}</div>
                {vaultInitialized === false && (
                  <div style={{marginTop: '3px', opacity: 0.88}}>
                    {gettext(
                      'First-run setup: choose your initial User name, User password, and Database key.'
                    )}
                  </div>
                )}
              </div>

              <div>
                <label
                  className="BasePage-label"
                  htmlFor="security-login-email"
                >
                  {gettext('User name')}
                </label>
                <InputText
                  cid="security-login-email"
                  name="email"
                  value={form.email}
                  onChange={(v) => onTextChange('email', v)}
                  autoFocus
                  required
                  controlProps={{autoComplete: 'username'}}
                />
              </div>

              <div>
                <label
                  className="BasePage-label"
                  htmlFor="security-login-password"
                >
                  {gettext('User password')}
                </label>
                <InputText
                  cid="security-login-password"
                  name="password"
                  value={form.password}
                  onChange={(v) => onTextChange('password', v)}
                  type={showPassword ? 'text' : 'password'}
                  required
                  controlProps={{autoComplete: 'current-password'}}
                />
              </div>

              <div>
                <label
                  className="BasePage-label"
                  htmlFor="security-login-database-key"
                >
                  {gettext('Database key')}
                </label>
                <InputText
                  cid="security-login-database-key"
                  name="database_key"
                  value={form.database_key}
                  onChange={(v) => onTextChange('database_key', v)}
                  type={showPassword ? 'text' : 'password'}
                  required
                  controlProps={{
                    autoComplete: 'off',
                    placeholder: gettext('Decryption key for UserConfigurationDatabase'),
                  }}
                />
              </div>

              <label
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '8px',
                  fontSize: '0.84rem',
                  cursor: 'pointer',
                  userSelect: 'none',
                }}
              >
                <input
                  type="checkbox"
                  checked={showPassword}
                  onChange={(event) => {
                    // Autofill may update native inputs without a React change event.
                    // Preserve those values before changing the password input type.
                    const inputs = formRef.current?.elements;
                    if (inputs) {
                      setForm((previous) => ({
                        ...previous,
                        email: inputs.namedItem('email')?.value ?? previous.email,
                        password:
                          inputs.namedItem('password')?.value ?? previous.password,
                        database_key:
                          inputs.namedItem('database_key')?.value ??
                          previous.database_key,
                      }));
                    }
                    setShowPassword(event.target.checked);
                  }}
                />
                <span>{gettext('Show password')}</span>
              </label>

              {forgotPassUrl && (
                <div style={{textAlign: 'right', marginTop: '-8px', fontSize: '0.82rem'}}>
                  <a style={{color: 'inherit'}} href={forgotPassUrl}>
                    {gettext('Forgotten your password?')}
                  </a>
                </div>
              )}

              <InputSelectNonSearch
                name="language"
                options={langOptions}
                value={form.language}
                onChange={(v) => onTextChange('language', v.target.value)}
              />
            </>
          )}
          {showLoginForm && (
            <SecurityButton name="internal_button" value="Login">
              {gettext('Sign in')}
            </SecurityButton>
          )}
          {authSources?.includes?.(authSourcesEnum.OAUTH2) &&
            oauth2Config.map((oauth) => {
              const iconStyles = [
                'fab',
                'fas',
                'far',
                'fal',
                'fat',
                'fad',
                'fa-brands',
                'fa-solid',
                'fa-regular',
                'fa-light',
                'fa-thin',
                'fa-duotone',
              ];
              const hasStyle = oauth.OAUTH2_ICON?.split(/\s+/).some((c) =>
                iconStyles.includes(c)
              );
              const iconClassName = hasStyle
                ? oauth.OAUTH2_ICON
                : 'fab ' + oauth.OAUTH2_ICON;
              return (
                <SecurityButton
                  key={oauth.OAUTH2_NAME}
                  name="oauth2_button"
                  value={oauth.OAUTH2_NAME}
                  style={{backgroundColor: oauth.OAUTH2_BUTTON_COLOR}}
                >
                  <span
                    className={iconClassName}
                    style={{fontSize: '1.3em', marginRight: '8px'}}
                    aria-hidden="true"
                  />
                  {gettext('Login with %s', oauth.OAUTH2_DISPLAY_NAME)}
                </SecurityButton>
              );
            })}
        </form>
      </BasePage>
    </>
  );
}

LoginPage.propTypes = {
  userLanguage: PropTypes.string,
  langOptions: PropTypes.arrayOf(PropTypes.object),
  forgotPassUrl: PropTypes.string,
  csrfToken: PropTypes.string,
  loginUrl: PropTypes.string,
  authSources: PropTypes.arrayOf(PropTypes.string),
  authSourcesEnum: PropTypes.object,
  oauth2Config: PropTypes.arrayOf(PropTypes.object),
  loginBanner: PropTypes.string,
  vaultInitialized: PropTypes.bool,
  vaultEngine: PropTypes.string,
};
