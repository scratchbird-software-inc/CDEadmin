##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""A blueprint module implementing the Authentication."""

import config
import copy
import functools
from threading import Lock

from flask import current_app, flash, Response, request, url_for, \
    session, redirect, render_template
from flask_babel import gettext
from flask_security.views import _security, _ctx
from flask_security.utils import logout_user, config_value

from flask_login import current_user
from flask_socketio import disconnect, ConnectionRefusedError

from pgadmin.model import db, User
from pgadmin.utils.csrf import pgCSRFProtect
from pgadmin.utils.constants import KERBEROS, INTERNAL, OAUTH2, LDAP,\
    MessageType
import pgadmin.utils as pga_utils
from pgadmin.authenticate.registry import AuthSourceRegistry

MODULE_NAME = 'authenticate'
auth_obj = None

_URL_WITH_NEXT_PARAM = "{0}?next={1}"


class AuthLocker:
    """Implementing lock while authentication."""
    lock = Lock()

    def __enter__(self):
        self.lock.acquire()
        return self

    def __exit__(self, type, value, traceback):
        if self.lock.locked():
            self.lock.release()


def get_logout_url() -> str:
    """
    Returns the logout url based on the current authentication method.

    Returns:
        str: logout url
    """
    BROWSER_INDEX = 'browser.index'
    if config.SERVER_MODE and\
            session['auth_source_manager']['current_source'] == \
            KERBEROS:
        return _URL_WITH_NEXT_PARAM.format(url_for(
            'kerberos.logout'), url_for(BROWSER_INDEX))
    elif config.SERVER_MODE and\
            session['auth_source_manager']['current_source'] == \
            OAUTH2:
        return _URL_WITH_NEXT_PARAM.format(url_for(
            'oauth2.logout'), url_for(BROWSER_INDEX))

    return _URL_WITH_NEXT_PARAM.format(
        url_for('security.logout'), url_for(BROWSER_INDEX))


def socket_login_required(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            disconnect()
            raise ConnectionRefusedError("Unauthorised !")
        else:
            return f(*args, **kwargs)
    return wrapped


def socket_permissions_required(*fsperms):
    """Socket.IO equivalent of flask_security's permissions_required.

    Refuses the event unless the current user is authenticated and holds
    all of the named pgAdmin permissions (via their roles). This mirrors
    the HTTP @permissions_required decorator so that Socket.IO handlers
    enforce the same tool-level RBAC as the routes: an authenticated user
    must not be able to reach a sensitive handler (e.g. the schema diff
    comparison or the PSQL pseudo-terminal) for a tool whose permission
    they have been denied.

    has_permission() is used in preference to flask_principal's
    Permission().can() because it reads the user's roles directly and
    does not depend on the principal identity having been loaded onto the
    socket request context; it also honours pgAdmin's Administrator
    bypass (see CustomUserMixin).
    """
    def wrapper(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                disconnect()
                raise ConnectionRefusedError("Unauthorised !")

            for fsperm in fsperms:
                if not current_user.has_permission(fsperm):
                    disconnect()
                    raise ConnectionRefusedError("Forbidden !")

            return f(*args, **kwargs)
        return wrapped
    return wrapper


class AuthenticateModule(pga_utils.PgAdminModule):
    def get_exposed_url_endpoints(self):
        return [
            'authenticate.login',
            'authenticate.vault_status',
        ]


blueprint = AuthenticateModule(MODULE_NAME, __name__, static_url_path='')


@blueprint.route('/vault_status', endpoint='vault_status', methods=['GET'])
@pgCSRFProtect.exempt
def vault_status():
    """Report whether the Firebird Embedded UserConfigurationDatabase is initialized."""
    from pgadmin.cdeadmin.user_config_db import get_user_config_db
    from pgadmin.utils.ajax import make_json_response

    ucfg = get_user_config_db()
    return make_json_response(
        data={
            'vault_initialized': ucfg.is_vault_initialized(),
            'vault_unlocked': ucfg.is_unlocked(),
            'engine': ucfg.engine_name,
            'multi_user_ready': True,
        }
    )


@blueprint.route('/desktop_unlock', endpoint='desktop_unlock', methods=['POST'])
@pgCSRFProtect.exempt
def desktop_unlock():
    """Unlock UserConfigurationDatabase from the Electron splash screen login prompt."""
    from flask_security.utils import login_user
    from pgadmin.cdeadmin.user_config_db import (
        UserConfigAuthError,
        UserConfigKeyError,
        ensure_flask_security_user_for_vault_user,
        get_user_config_db,
         sync_runtime_orm_to_user_config_db,
    )
    from pgadmin.cdeadmin.user_config_db.service import mint_desktop_handoff_ticket
    from pgadmin.utils.ajax import make_json_response

    if config.SERVER_MODE:
        return make_json_response(
            status=403,
            success=0,
            errormsg=gettext('Desktop vault unlock is only available in desktop runtime.'),
        )

    payload = request.get_json(silent=True) or request.form or {}
    username = str(payload.get('username') or payload.get('email') or '').strip()
    password = str(payload.get('password') or '')
    database_key = str(payload.get('database_key') or payload.get('databaseKey') or '')

    with AuthLocker():
        ucfg = get_user_config_db()
        try:
            vault_user = ucfg.unlock_and_authenticate(
                username,
                password,
                database_key,
                legacy_data_dir=getattr(config, 'DATA_DIR', None),
            )
        except (UserConfigKeyError, UserConfigAuthError) as exc:
            return make_json_response(status=401, success=0, errormsg=str(exc))

        user = ensure_flask_security_user_for_vault_user(vault_user)
        current_app.keyManager.set(ucfg.derived_session_crypt_key())
        login_user(user)
        sync_runtime_orm_to_user_config_db(int(user.id))
        ticket = mint_desktop_handoff_ticket(int(user.id), str(user.username))
        return make_json_response(
            data={
                'ticket': ticket,
                'username': str(user.username),
                'vault_created': bool(vault_user.get('vault_created')),
                'engine': ucfg.engine_name,
            }
        )


@blueprint.route('/desktop_handoff', endpoint='desktop_handoff', methods=['GET'])
@pgCSRFProtect.exempt
def desktop_handoff():
    """Consume single-use Electron splash ticket to establish authenticated BrowserWindow session."""
    from flask_security.utils import login_user
    from pgadmin.cdeadmin.user_config_db import get_user_config_db
    from pgadmin.cdeadmin.user_config_db.service import consume_desktop_handoff_ticket

    if config.SERVER_MODE:
        return redirect(url_for('security.login'))

    ticket = str(request.args.get('ticket') or '').strip()
    entry = consume_desktop_handoff_ticket(ticket)
    ucfg = get_user_config_db()
    if not entry or not ucfg.is_unlocked():
        return redirect(url_for('security.login'))

    user = db.session.get(User, int(entry['user_id']))
    if user is None or not user.is_active:
        return redirect(url_for('security.login'))

    current_app.keyManager.set(ucfg.derived_session_crypt_key())
    login_user(user)
    session['auth_source_manager'] = {
        'source_friendly_name': INTERNAL,
        'auth_sources': [INTERNAL],
        'current_source': INTERNAL,
    }
    return redirect(url_for('browser.index'))


@blueprint.route('/login', endpoint='login', methods=['GET', 'POST'])
def login():
    """
    Entry point for all the authentication sources.
    The user input will be validated and authenticated.
    """
    with AuthLocker():
        return _login()


def _render_login_with_error(err_msg: str):
    flash(err_msg, MessageType.ERROR)
    form_class = _security.forms.get('login_form').cls
    form = form_class()
    return _security.render_template(
        config_value('LOGIN_USER_TEMPLATE'),
        login_user_form=form,
        **_ctx('login'),
    )


def _login():
    """
    Internal authentication process locked by a mutex.
    """
    import os as _os

    require_ucfg = current_app.config.get(
        'USER_CONFIG_LOGIN_REQUIRED',
        _os.environ.get('PGADMIN_TESTING_MODE') != '1',
    )
    if (
        request.method == 'POST'
        and 'oauth2_button' not in request.form
        and (require_ucfg or 'database_key' in request.form)
    ):
        from flask_security.utils import login_user
        from pgadmin.cdeadmin.user_config_db import (
            UserConfigAuthError,
            UserConfigKeyError,
            ensure_flask_security_user_for_vault_user,
            get_user_config_db,
            sync_runtime_orm_to_user_config_db,
        )

        username = str(
            request.form.get('email') or request.form.get('username') or ''
        ).strip()
        password = str(request.form.get('password') or '')
        database_key = str(request.form.get('database_key') or '')

        ucfg = get_user_config_db()
        try:
            vault_user = ucfg.unlock_and_authenticate(
                username,
                password,
                database_key,
                legacy_data_dir=getattr(config, 'DATA_DIR', None),
            )
        except (UserConfigKeyError, UserConfigAuthError) as exc:
            return _render_login_with_error(str(exc))

        user = ensure_flask_security_user_for_vault_user(vault_user)
        if not login_user(user):
            return _render_login_with_error(gettext('Login failed'))

        current_app.keyManager.set(ucfg.derived_session_crypt_key())
        sync_runtime_orm_to_user_config_db(int(user.id))
        session['auth_source_manager'] = {
            'source_friendly_name': INTERNAL,
            'auth_sources': copy.deepcopy(config.AUTHENTICATION_SOURCES),
            'current_source': INTERNAL,
        }
        user.login_attempts = 0
        db.session.commit()
        session.pop('oauth2_current_client', None)
        return redirect(pga_utils.get_safe_post_login_redirect())
    form = _security.forms.get('login_form').cls(request.form)
    if OAUTH2 in config.AUTHENTICATION_SOURCES \
            and 'oauth2_button' in request.form:
        # Sending empty form as oauth2 does not require form attribute
        auth_obj = AuthSourceManager({}, copy.deepcopy(
            config.AUTHENTICATION_SOURCES))
        # Persist only the OAuth2 provider selection across the redirect.
        # The auth-source instance lives on current_app's registry so we
        # re-look-up rather than persist a live class instance in session.
        session['oauth2_current_client'] = request.form.get('oauth2_button')
    else:
        auth_obj = AuthSourceManager(form, copy.deepcopy(
            config.AUTHENTICATION_SOURCES))

    session['auth_source_manager'] = None

    username = form.data['email']
    user = User.query.filter_by(username=username,
                                auth_source=INTERNAL).first()

    if user:
        if user.login_attempts >= config.MAX_LOGIN_ATTEMPTS > 0:
            user.locked = True
        else:
            user.locked = False
        db.session.commit()

        if user.login_attempts >= config.MAX_LOGIN_ATTEMPTS > 0:
            flash(gettext('Your account is locked. Please contact the '
                          'Administrator.'),
                  MessageType.WARNING)
            logout_user()
            return redirect(pga_utils.get_safe_post_logout_redirect())

    # Validate the user
    if not auth_obj.validate():
        for field in form.errors:
            flash_login_attempt_error = None
            if user and field in config.LOGIN_ATTEMPT_FIELDS:
                if config.MAX_LOGIN_ATTEMPTS > 0:
                    user.login_attempts += 1
                    left_attempts = \
                        config.MAX_LOGIN_ATTEMPTS - user.login_attempts
                    if left_attempts > 1:
                        flash_login_attempt_error = \
                            gettext('{0} more attempts remaining.'.
                                    format(left_attempts))
                    else:
                        flash_login_attempt_error = \
                            gettext('{0} more attempt remaining.'.
                                    format(left_attempts))
                db.session.commit()
            for error in form.errors[field]:
                if flash_login_attempt_error:
                    error = error + flash_login_attempt_error
                    flash_login_attempt_error = None
                flash(error, MessageType.WARNING)

        return redirect(pga_utils.get_safe_post_logout_redirect())

    # Authenticate the user
    status, msg = auth_obj.authenticate()
    if status:
        # Login the user
        status, msg = auth_obj.login()
        current_auth_obj = auth_obj.as_dict()

        if not status:
            if current_auth_obj['current_source'] == \
                    KERBEROS:
                return redirect('{0}?next={1}'.format(url_for(
                    'authenticate.kerberos_login'), url_for('browser.index')))

            flash(msg, MessageType.ERROR)
            return redirect(pga_utils.get_safe_post_logout_redirect())

        session['auth_source_manager'] = current_auth_obj

        if user:
            user.login_attempts = 0
        db.session.commit()

        session.pop('oauth2_current_client', None)
        return redirect(pga_utils.get_safe_post_login_redirect())

    elif isinstance(msg, Response):
        return msg
    elif 'oauth2_button' in request.form and not isinstance(msg, str):
        return msg
    session.pop('oauth2_current_client', None)
    flash(msg, MessageType.ERROR)
    form_class = _security.forms.get('login_form').cls
    form = form_class()

    return _security.render_template(
        config_value('LOGIN_USER_TEMPLATE'),
        login_user_form=form, **_ctx('login'))


class AuthSourceManager:
    """This class will manage all the authentication sources.
     """

    def __init__(self, form, sources):
        self.form = form
        self.auth_sources = sources
        self.source = None
        self.source_friendly_name = INTERNAL
        self.current_source = INTERNAL
        self.update_auth_sources()

    def as_dict(self):
        """
        Returns the dictionary object representing this object.
        """

        res = dict()
        res['source_friendly_name'] = self.source_friendly_name
        res['auth_sources'] = self.auth_sources
        res['current_source'] = self.current_source

        return res

    def update_auth_sources(self):
        # Only mutate the ordered list of auth sources when a user explicitly
        # selected an auth method on the login form.
        #
        # Without this guard, a plain internal login POST (email/password) can
        # incorrectly drop INTERNAL/LDAP and try OAUTH2 first, which then fails
        # because no oauth2 provider button was provided.
        if request.method != 'POST':
            return

        if 'internal_button' in request.form:
            for auth_src in [KERBEROS, OAUTH2]:
                if auth_src in self.auth_sources:
                    self.auth_sources.remove(auth_src)
            return

        if 'oauth2_button' in request.form:
            if INTERNAL in self.auth_sources:
                self.auth_sources.remove(INTERNAL)
            if LDAP in self.auth_sources:
                self.auth_sources.remove(LDAP)
            return

    def set_current_source(self, source):
        self.current_source = source

    @property
    def get_current_source(self):
        return self.current_source

    def set_source(self, source):
        self.source = source

    @property
    def get_source(self):
        return self.source

    def set_source_friendly_name(self, name):
        self.source_friendly_name = name

    @property
    def get_source_friendly_name(self):
        return self.source_friendly_name

    def validate(self):
        """Validate through all the sources."""
        err_msg = None
        for src in self.auth_sources:
            source = get_auth_sources(src)
            status, err_msg = source.validate(self.form)
            if status:
                return True
        if err_msg:
            flash(err_msg, MessageType.WARNING)
        return False

    def authenticate(self):
        """Authenticate through all the sources."""
        status = False
        msg = None
        for src in self.auth_sources:
            source = get_auth_sources(src)
            self.set_source(source)
            current_app.logger.debug(
                "Authentication initiated via source: %s" %
                source.get_source_name())

            status, msg = source.authenticate(self.form)

            if status:
                self.set_current_source(source.get_source_name())
                if msg is not None and 'username' in msg:
                    self.form._fields['email'].data = msg['username']
                return status, msg
            else:
                current_app.logger.debug(
                    "Authentication initiated via source: %s is failed." %
                    source.get_source_name())
        return status, msg

    def login(self):
        status, msg = self.source.login(self.form)
        if status:
            self.set_source_friendly_name(self.source.get_friendly_name())
            current_app.logger.debug(
                "Authentication and Login successfully done via source : %s" %
                self.source.get_source_name())

            # Set the login, logout view as per source  if available
            current_app.login_manager.login_view = getattr(
                self.source, 'LOGIN_VIEW', 'security.login')
            current_app.login_manager.logout_view = getattr(
                self.source, 'LOGOUT_VIEW', 'security.logout')

        return status, msg


def get_auth_sources(type):
    """Get the authenticated source object from the registry"""

    auth_sources = getattr(current_app, '_pgadmin_auth_sources', None)

    if auth_sources is None or not isinstance(auth_sources, dict):
        auth_sources = dict()

    if type in auth_sources:
        return auth_sources[type]

    auth_source = AuthSourceRegistry.get(type)

    if auth_source is not None:
        auth_sources[type] = auth_source
        setattr(current_app, '_pgadmin_auth_sources', auth_sources)

    return auth_source


def init_app(app):
    auth_sources = dict()

    setattr(app, '_pgadmin_auth_sources', auth_sources)
    AuthSourceRegistry.load_modules(app)

    return auth_sources
