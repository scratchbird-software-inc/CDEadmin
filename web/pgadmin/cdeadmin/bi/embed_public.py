##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""The unauthenticated surface of signed embedding.

Deliberately the only unauthenticated BI code, and deliberately small.  See
``docs/en_US/bi_embedding.rst`` ("Threat model").

* Nothing here reads or sets a cookie: a WSGI layer removes the ``Cookie``
  request header and any ``Set-Cookie`` response header for these paths, so
  no ambient credential can be used and none is created.  There is no
  session and CSRF protection is not applicable (state is only changed by
  a bearer token the caller must present; the JavaScript sends it in an
  ``Authorization`` header, never in a cookie).
* There is no CORS: no ``Access-Control-*`` header is ever sent, and
  ``OPTIONS`` is not answered.
* The page is framable only by the embed's declared origins
  (``frame-ancestors``), and ``X-Frame-Options`` is not sent.
* Every refusal (bad, expired, replayed or mis-addressed token, unknown,
  disabled, revoked or expired embed, owner without rights) is the same
  response, so nothing can be enumerated.  The only distinguishable
  answers are 429 (after the caller proved a valid token) and 400 for a
  request outside the embed's declared parameters.
* Responses never contain SQL, plans, secrets, cache internals or error
  detail beyond a generic code.
"""

from __future__ import annotations

import json
import secrets

from .embeds import EmbedDenied, EmbedInvalid, EmbedRateLimited

BLUEPRINT_NAME = 'cdeadmin_bi_embed'
PREFIX = '/cdeadmin/embed/'
MAX_BODY = 64 * 1024
NOT_FOUND = '{"success":0,"errormsg":"Not found"}'
JSON_CSP = "default-src 'none'; frame-ancestors 'none'"


class EmbedIsolation:
    """WSGI layer: embed paths neither read nor set cookies."""

    def __init__(self, application, prefix=PREFIX):
        self.application, self.prefix = application, prefix

    def __call__(self, environ, start_response):
        if not environ.get('PATH_INFO', '').startswith(self.prefix):
            return self.application(environ, start_response)
        environ.pop('HTTP_COOKIE', None)

        def respond(status, headers, exc_info=None):
            kept = [(k, v) for k, v in headers
                    if k.lower() != 'set-cookie']
            return start_response(status, kept, exc_info)

        return self.application(environ, respond)


def _bearer(request):
    value = request.headers.get('Authorization', '')
    scheme, _space, token = value.partition(' ')
    return token if scheme == 'Bearer' and token and ' ' not in token else ''


SHELL_CSS = '''
:root{color-scheme:light dark;--bg:#fff;--fg:#1c2330;--muted:#5b6678;--line:#d5dae3;--head:#f1f4f9;--accent:#1b5fb4}
body[data-theme=dark]{--bg:#161b24;--fg:#e8ecf3;--muted:#9aa5b8;--line:#2e3646;--head:#1f2632;--accent:#78a9f0;color-scheme:dark}
body[data-theme=light]{color-scheme:light}
@media (prefers-color-scheme:dark){body[data-theme=auto]{--bg:#161b24;--fg:#e8ecf3;--muted:#9aa5b8;--line:#2e3646;--head:#1f2632;--accent:#78a9f0}}
*{box-sizing:border-box}
body{margin:0;padding:12px 16px;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}
body[data-border=yes]{border:1px solid var(--line)}
h1{font-size:18px;margin:0 0 8px}h2{font-size:14px;margin:0 0 6px}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:flex-end;margin:0 0 12px}
.bar label{display:grid;gap:2px;font-size:12px;color:var(--muted)}
.bar input,.bar select{font:inherit;padding:4px 6px;border:1px solid var(--line);border-radius:4px;background:var(--bg);color:var(--fg)}
.tag{padding:2px 8px;border:1px solid var(--line);border-radius:10px;font-size:12px;color:var(--muted)}
button{font:inherit;padding:4px 10px;border:1px solid var(--accent);border-radius:4px;background:transparent;color:var(--accent);cursor:pointer}
button:disabled{opacity:.5;cursor:default}
.tabs{display:flex;gap:6px;margin:0 0 10px}
.card{border:1px solid var(--line);border-radius:6px;margin:0 0 12px;padding:10px;overflow:auto}
table{border-collapse:collapse;width:100%}
th,td{border-bottom:1px solid var(--line);padding:4px 8px;text-align:left;white-space:nowrap}
th{background:var(--head);font-weight:600}
.note{color:var(--muted);font-size:12px;margin:6px 0 0}
.err{color:#b3261e}
'''

SHELL_JS = r'''
(function () {
  'use strict';
  var body = document.body;
  var token = new URLSearchParams(location.search).get('token') || '';
  try { history.replaceState(null, '', location.pathname); } catch (e) { /* ignore */ }
  var base = location.pathname.replace(/\/frame$/, '');
  var root = document.getElementById('root');
  var model = null;
  var values = {};
  var tab = null;

  function el(tag, text, className) {
    var node = document.createElement(tag);
    if (text !== undefined && text !== null) { node.textContent = String(text); }
    if (className) { node.className = className; }
    return node;
  }
  function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }
  function api(path, payload) {
    var init = {method: payload === undefined ? 'GET' : 'POST', credentials: 'omit', cache: 'no-store',
      referrerPolicy: 'no-referrer', headers: {Authorization: 'Bearer ' + token, Accept: 'application/json'}};
    if (payload !== undefined) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(payload);
    }
    return fetch(base + path, init).then(function (response) {
      return response.json().then(function (json) {
        if (!response.ok || !json.success) { throw new Error('unavailable'); }
        return json.data;
      });
    });
  }
  function fail(node) { clear(node); node.appendChild(el('p', 'This content is not available.', 'err')); }

  function table(result, drill) {
    var wrap = el('div');
    var grid = el('table');
    var head = el('tr');
    result.columns.forEach(function (name) { head.appendChild(el('th', name)); });
    if (drill) { head.appendChild(el('th', '')); }
    grid.appendChild(head);
    var append = function (rows) {
      rows.forEach(function (row) {
        var line = el('tr');
        result.columns.forEach(function (name) {
          var value = row[name];
          line.appendChild(el('td', value === null || value === undefined ? '' : (typeof value === 'object' ? JSON.stringify(value) : value)));
        });
        if (drill) {
          var cell = el('td');
          var open = el('button', 'Details');
          open.addEventListener('click', function () { drill(row); });
          cell.appendChild(open);
          line.appendChild(cell);
        }
        grid.appendChild(line);
      });
    };
    append(result.rows);
    wrap.appendChild(grid);
    if (!result.rows.length) { wrap.appendChild(el('p', 'No rows.', 'note')); }
    var more = el('button', 'Load more');
    var cursor = result.next_cursor;
    more.hidden = !cursor;
    more.addEventListener('click', function () {
      more.disabled = true;
      api('/page', {result_id: result.result_id, cursor: cursor}).then(function (page) {
        append(page.rows);
        cursor = page.next_cursor;
        more.hidden = !cursor;
        more.disabled = false;
      }, function () { more.hidden = true; wrap.appendChild(el('p', 'No more rows are available.', 'note')); });
    });
    wrap.appendChild(more);
    if (result.download) {
      result.download.formats.forEach(function (format) {
        var save = el('button', 'Download ' + format);
        save.addEventListener('click', function () {
          fetch(base + '/export', {method: 'POST', credentials: 'omit', cache: 'no-store', referrerPolicy: 'no-referrer',
            headers: {Authorization: 'Bearer ' + token, 'Content-Type': 'application/json'},
            body: JSON.stringify({result_id: result.result_id, format: format})})
            .then(function (response) { if (!response.ok) { throw new Error('x'); } return response.blob(); })
            .then(function (blob) {
              var link = document.createElement('a');
              link.href = URL.createObjectURL(blob);
              link.download = 'export.' + format;
              link.click();
              setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
            }, function () { wrap.appendChild(el('p', 'The download is not available.', 'note')); });
        });
        wrap.appendChild(save);
      });
    }
    return wrap;
  }

  function show(node, promise, drill) {
    clear(node);
    node.appendChild(el('p', 'Loading...', 'note'));
    promise.then(function (result) {
      clear(node);
      if (result.title) { node.appendChild(el('h2', result.title)); }
      if (result.status !== 'ok') { node.appendChild(el('p', 'This content is not available.', 'note')); return; }
      node.appendChild(table(result, drill));
    }, function () { fail(node); });
  }

  function filterValue(param, input) {
    if (param.type === 'boolean') { return input.checked; }
    var text = input.value.trim();
    if (text === '') { return null; }
    var convert = function (item) {
      item = item.trim();
      return (param.type === 'number' || param.type === 'integer') && item !== '' && !isNaN(Number(item)) ? Number(item) : item;
    };
    return param.multiple ? text.split(',').map(convert) : convert(text);
  }

  function filters(bar, reload) {
    var inputs = [];
    model.parameters.forEach(function (param) {
      if (param.mode !== 'editable') {
        bar.appendChild(el('span', param.name + ': ' + (param.value === undefined ? '' : String(param.value)), 'tag'));
        return;
      }
      var label = el('label', param.name);
      var input;
      if (param.allowed_values.length && !param.multiple) {
        input = el('select');
        input.appendChild(el('option', ''));
        param.allowed_values.forEach(function (item) { var option = el('option', item); option.value = String(item); input.appendChild(option); });
      } else {
        input = el('input');
        input.type = param.type === 'boolean' ? 'checkbox' : 'text';
      }
      if (param.value !== undefined || param.default !== undefined) {
        var start = param.value !== undefined ? param.value : param.default;
        if (param.type === 'boolean') { input.checked = !!start; } else { input.value = Array.isArray(start) ? start.join(',') : String(start); }
      }
      label.appendChild(input);
      bar.appendChild(label);
      inputs.push([param, input]);
    });
    if (inputs.length) {
      var apply = el('button', 'Apply');
      apply.addEventListener('click', function () {
        values = {};
        inputs.forEach(function (pair) {
          var value = filterValue(pair[0], pair[1]);
          if (value !== null) { values[pair[0].id] = value; }
        });
        reload();
      });
      bar.appendChild(apply);
    }
    return function () {
      values = {};
      inputs.forEach(function (pair) {
        var value = filterValue(pair[0], pair[1]);
        if (value !== null) { values[pair[0].id] = value; }
      });
    };
  }

  function render() {
    clear(root);
    if (model.display.title) { root.appendChild(el('h1', model.name)); }
    var bar = el('div', null, 'bar');
    root.appendChild(bar);
    var cards = el('div');
    var collect;
    var reload = function () {
      clear(cards);
      if (model.kind === 'question') {
        var holder = el('section', null, 'card');
        cards.appendChild(holder);
        show(holder, api('/run', {parameters: values, page_size: model.page_size}));
        return;
      }
      var tabs = model.tabs;
      if (tabs.length > 1) {
        var row = el('div', null, 'tabs');
        tabs.forEach(function (item) {
          var button = el('button', item.name);
          button.disabled = item.id === tab;
          button.addEventListener('click', function () { tab = item.id; reload(); });
          row.appendChild(button);
        });
        cards.appendChild(row);
      }
      model.cards.filter(function (card) { return tabs.length < 2 || card.tab_id === tab; })
        .sort(function (a, b) { return a.layout.y - b.layout.y || a.layout.x - b.layout.x; })
        .forEach(function (card) {
          var holder = el('section', null, 'card');
          cards.appendChild(holder);
          if (card.type === 'text') { holder.appendChild(el('p', card.text)); return; }
          if (card.type !== 'question') { holder.appendChild(el('p', 'Not available here.', 'note')); return; }
          var drills = model.drills.filter(function (item) { return item.source_card_id === card.id; });
          var drill = drills.length ? function (row) {
            var panel = el('section', null, 'card');
            holder.appendChild(panel);
            show(panel, api('/drill', {drill_id: drills[0].id, row: row, filters: values}));
          } : null;
          var promise = api('/cards/' + encodeURIComponent(card.id) + '/run', {filters: values, page_size: model.page_size});
          show(holder, promise.then(function (result) { result.title = card.title; return result; }), drill);
        });
    };
    collect = filters(bar, reload);
    root.appendChild(cards);
    collect();
    reload();
  }

  api('/data').then(function (data) {
    model = data;
    tab = data.tabs && data.tabs.length ? data.tabs[0].id : null;
    document.title = data.display.title ? data.name : 'Embedded content';
    render();
  }, function () { fail(root); });
}());
'''


def shell_page(session, nonce):
    display = session.definition['display']
    from html import escape
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="referrer" content="no-referrer">'
        '<title>Embedded content</title>'
        '<style nonce="%(n)s">%(css)s</style></head>'
        '<body data-theme="%(theme)s" data-border="%(border)s">'
        '<div id="root" role="main" aria-live="polite">Loading...</div>'
        '<noscript>JavaScript is required to show this content.</noscript>'
        '<script nonce="%(n)s">%(js)s</script></body></html>'
    ) % {'n': nonce, 'css': SHELL_CSS, 'js': SHELL_JS,
         'theme': escape(display['theme']),
         'border': 'yes' if display['border'] else 'no'}


def register(app, service):
    """Register the blueprint and the cookie isolation layer (idempotent)."""
    from flask import Blueprint, Response, request

    if BLUEPRINT_NAME in app.blueprints:
        return app.blueprints[BLUEPRINT_NAME]
    api = Blueprint(BLUEPRINT_NAME, __name__, url_prefix=PREFIX.rstrip('/'))

    def finish(response, csp=None):
        headers = response.headers
        headers['Cache-Control'] = 'no-store'
        headers['Pragma'] = 'no-cache'
        headers['X-Content-Type-Options'] = 'nosniff'
        headers['Referrer-Policy'] = 'no-referrer'
        headers['Cross-Origin-Resource-Policy'] = 'same-origin'
        headers['X-Robots-Tag'] = 'noindex, nofollow'
        headers['Content-Security-Policy'] = csp or JSON_CSP
        headers.pop('X-Frame-Options', None)
        for name in [h for h in headers.keys()
                     if h.lower().startswith('access-control-')]:
            del headers[name]
        # tells SecurityHeaders (pgadmin/utils/security_headers.py) not to
        # replace the CSP above or add X-Frame-Options
        response.cdeadmin_own_security_headers = True
        return response

    def body(payload, status=200):
        return finish(Response(
            json.dumps({'success': 1, 'data': payload}, default=str),
            status=status, mimetype='application/json'))

    def refuse(status=404, **extra):
        text = NOT_FOUND if status == 404 else json.dumps(
            {'success': 0, **extra})
        response = finish(Response(text, status=status,
                                   mimetype='application/json'))
        return response

    def payload():
        request.max_content_length = MAX_BODY
        try:
            value = request.get_json(silent=True)
        except Exception:
            raise EmbedInvalid('invalid_request') from None
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise EmbedInvalid('invalid_request')
        return value

    def guard(embed_id, handler, *, use='continue', shell=False):
        try:
            service.admit_ip(request.remote_addr)
            token = (request.args.get('token', '') if shell
                     else _bearer(request))
            session = service.authenticate(token, embed_id, use=use)
            return handler(session)
        except EmbedRateLimited as exc:
            response = refuse(429, error='rate_limited')
            response.headers['Retry-After'] = str(exc.retry_after)
            return response
        except EmbedInvalid as exc:
            return refuse(400, error=exc.code)
        except EmbedDenied:
            return refuse(404)
        except Exception as exc:  # never an error page with detail
            app.logger.error('embedded request failed (%s)',
                             type(exc).__name__)
            return refuse(500, error='failed')

    @api.route('/<embed_id>/frame', methods=['GET'],
               provide_automatic_options=False)
    def frame(embed_id):
        def handler(session):
            nonce = secrets.token_urlsafe(16)
            csp = ("default-src 'none'; script-src 'nonce-%(n)s'; "
                   "style-src 'nonce-%(n)s'; connect-src 'self'; "
                   "base-uri 'none'; form-action 'none'; "
                   "frame-ancestors %(a)s") % {
                'n': nonce, 'a': session.frame_ancestors}
            return finish(Response(shell_page(session, nonce),
                                   mimetype='text/html'), csp)
        return guard(embed_id, handler, shell=True, use='open')

    @api.route('/<embed_id>/data', methods=['GET'],
               provide_automatic_options=False)
    def data(embed_id):
        return guard(embed_id, lambda s: body(service.view(s)),
                     use='consume')

    @api.route('/<embed_id>/cards/<card_id>/run', methods=['POST'],
               provide_automatic_options=False)
    def card_run(embed_id, card_id):
        def handler(session):
            value = payload()
            return body(service.run_card(
                session, card_id, value.get('filters'),
                value.get('page_size')))
        return guard(embed_id, handler)

    @api.route('/<embed_id>/run', methods=['POST'],
               provide_automatic_options=False)
    def question_run(embed_id):
        def handler(session):
            value = payload()
            return body(service.run_question(
                session, value.get('parameters'), value.get('page_size')))
        return guard(embed_id, handler)

    @api.route('/<embed_id>/page', methods=['POST'],
               provide_automatic_options=False)
    def page(embed_id):
        def handler(session):
            value = payload()
            result_id, cursor = value.get('result_id'), value.get('cursor')
            if not isinstance(result_id, str) or not isinstance(
                    cursor, (str, int, dict)) or isinstance(cursor, bool):
                raise EmbedInvalid('invalid_request')
            return body(service.page(session, result_id, cursor,
                                     value.get('page_size')))
        return guard(embed_id, handler)

    @api.route('/<embed_id>/drill', methods=['POST'],
               provide_automatic_options=False)
    def drill(embed_id):
        def handler(session):
            value = payload()
            if not isinstance(value.get('drill_id'), str) or not isinstance(
                    value.get('row'), dict):
                raise EmbedInvalid('invalid_request')
            return body(service.drill(
                session, value['drill_id'], value['row'],
                value.get('filters')))
        return guard(embed_id, handler)

    @api.route('/<embed_id>/export', methods=['POST'],
               provide_automatic_options=False)
    def export(embed_id):
        def handler(session):
            value = payload()
            fmt = value.get('format')
            if not isinstance(value.get('result_id'), str) or not isinstance(
                    fmt, str):
                raise EmbedInvalid('invalid_request')
            content, media_type = service.export(
                session, value['result_id'], fmt)
            response = finish(Response(content, mimetype=media_type))
            response.headers['Content-Disposition'] = (
                'attachment; filename="export.%s"' % (
                    fmt if fmt.isalnum() else 'dat'))
            return response
        return guard(embed_id, handler)

    app.register_blueprint(api)
    _exempt_csrf(api)
    if not getattr(app.wsgi_app, '_cdeadmin_embed_isolation', False):
        app.wsgi_app = EmbedIsolation(app.wsgi_app)
        app.wsgi_app._cdeadmin_embed_isolation = True
    return api


def _exempt_csrf(blueprint):
    """The whole blueprint is outside CSRF protection (bearer token only)."""
    try:
        from pgadmin.utils.csrf import pgCSRFProtect
    except Exception:  # pragma: no cover - not running inside pgAdmin
        return
    pgCSRFProtect.exempt(blueprint)


__all__ = ('BLUEPRINT_NAME', 'EmbedIsolation', 'register', 'shell_page')
