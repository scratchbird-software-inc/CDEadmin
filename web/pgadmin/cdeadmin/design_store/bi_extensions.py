"""BI Phase 1 & Phase 2 extensions: device token fleet & remote kiosk viewer.

Provides:
- ``manage_bi_device_tokens``: list, mint and revoke display-only remote
  dashboard-server device tokens persisted as SHA-256 hashes in ``designs.db``.
- ``render_bi_kiosk_html_response`` (``SR-F-030034``): standalone chromeless
  display-only HTML viewer supporting header, query or ``#token=`` URL-fragment
  authentication, narrowing-only filter enforcement, auto-refresh countdown and
  accessible per-card HTML data tables with zero edit/admin/write-back chrome.
"""

from __future__ import annotations

import html
import json
from typing import Any, Mapping

from .bi_ddn import (
    BIDesignSync,
    _preview_columns_and_rows,
    ddn_to_dashboard,
    ddn_to_question,
)
from .service import (
    DesignStore,
    DesignStoreError,
    DesignStoreForbidden,
    DesignStoreNotFound,
)
from .shared_ddn import StoreDDNProcess

BI_KIOSK_FORM_KEY = 'bi-designer-kiosk'
BI_KIOSK_FORM_REF = 'SR-F-030034'


def _resolve_token_secret(app: Any = None) -> str:
    if app is not None and hasattr(app, 'config'):
        return str(
            app.config.get('CDEADMIN_BI_DEVICE_SECRET')
            or app.config.get('SECRET_KEY')
            or 'scratchrobin-bi-device-secret'
        )
    return 'scratchrobin-bi-device-secret'


def manage_bi_device_tokens(
    store: DesignStore,
    proc: StoreDDNProcess | None,
    *,
    design_id: str,
    actor_id: int,
    method: str,
    payload: Mapping[str, Any] | None,
    authorized: bool,
    app: Any = None,
) -> dict[str, Any]:
    """List, mint or revoke remote kiosk device tokens for a BI dashboard."""
    design = store.get_design(design_id)
    sync = BIDesignSync(
        store,
        proc,
        token_secret=_resolve_token_secret(app),
    )
    body = dict(payload or {})
    verb = str(method or 'GET').upper()
    action = str(
        body.get('action') or ('list' if verb == 'GET' else '')
    ).strip().lower()

    enabled_pubs = [
        eff for eff in sync.list_outward_effects(design_id, only_enabled=True)
        if eff.get('effect_kind') == 'dashboard_server'
    ]
    active_pub_id = enabled_pubs[0]['id'] if enabled_pubs else None

    if verb == 'GET' or action == 'list':
        return {
            'design_id': design_id,
            'active_publication_id': active_pub_id,
            'tokens': sync.list_device_tokens(design_id),
        }

    if action == 'mint':
        if not authorized:
            raise DesignStoreForbidden(
                'Caller is not authorized to mint remote kiosk device tokens'
            )
        sync._require_human(
            str(body.get('actor_kind') or 'human'),
            'mint remote kiosk device tokens',
        )
        if design['kind'] != 'dashboard':
            raise DesignStoreError(
                'Device tokens can only be minted for dashboard designs'
            )
        pub_id = str(body.get('publication_id') or active_pub_id or '').strip()
        if not pub_id:
            raise DesignStoreNotFound(
                'Dashboard does not have an enabled dashboard_server '
                'publication'
            )
        if not any(eff['id'] == pub_id for eff in enabled_pubs):
            raise DesignStoreNotFound(
                f'Active dashboard-server publication {pub_id!r} was not '
                f'found for design {design_id!r}'
            )
        raw_locked = body.get('locked_filters')
        if raw_locked is not None and not isinstance(raw_locked, Mapping):
            raise DesignStoreError('locked_filters must be an object')
        raw_exp = body.get('expires_at')
        expires_at = (
            str(raw_exp).strip()
            if raw_exp not in (None, '')
            else None
        )
        device_label = (
            str(body.get('device_label') or 'kiosk').strip() or 'kiosk'
        )
        device_token = sync.mint_device_token(
            pub_id,
            device_label=device_label,
            locked_filters=raw_locked,
            expires_at=expires_at,
            created_by=int(actor_id),
        )
        claims = sync.verify_device_token(device_token)
        tokens = sync.list_device_tokens(design_id)
        token_record = next(
            (t for t in tokens if t['token_id'] == claims.get('tid')),
            tokens[0] if tokens else None,
        )
        return {
            'design_id': design_id,
            'publication_id': pub_id,
            'device_token': device_token,
            'token_record': token_record,
            'kiosk_url': f'/cdeadmin/designs/kiosk/{pub_id}#token={device_token}',
            'tokens': tokens,
        }

    if action == 'revoke':
        if not authorized:
            raise DesignStoreForbidden(
                'Caller is not authorized to revoke remote kiosk device tokens'
            )
        sync._require_human(
            str(body.get('actor_kind') or 'human'),
            'revoke remote kiosk device tokens',
        )
        token_id = str(body.get('token_id') or '').strip()
        if not token_id:
            raise DesignStoreError('token_id is required to revoke a token')
        revoked = sync.revoke_device_token(design_id, token_id)
        return {
            'design_id': design_id,
            'revoked': revoked,
            'tokens': sync.list_device_tokens(design_id),
        }

    raise DesignStoreError(f'Unsupported BI device token action: {action!r}')


def _extract_kiosk_token(
    query_args: Mapping[str, Any] | None,
    headers: Mapping[str, Any] | None,
) -> str:
    hdrs = headers or {}
    auth_hdr = str(hdrs.get('Authorization') or '').strip()
    if auth_hdr.lower().startswith('bearer '):
        candidate = auth_hdr[7:].strip()
        if candidate:
            return candidate
    header_tok = str(hdrs.get('X-ScratchRobin-Device-Token') or '').strip()
    if header_tok:
        return header_tok
    qargs = query_args or {}
    query_tok = str(qargs.get('token') or '').strip()
    return query_tok


def _extract_requested_filters(
    query_args: Mapping[str, Any] | None,
) -> dict[str, Any]:
    qargs = query_args or {}
    requested: dict[str, Any] = {}
    raw_json = qargs.get('filters')
    if raw_json not in (None, ''):
        try:
            parsed = json.loads(str(raw_json))
        except ValueError as exc:
            raise DesignStoreError('Invalid filters JSON query value') from exc
        if not isinstance(parsed, Mapping):
            raise DesignStoreError('filters query parameter must be an object')
        for k, v in parsed.items():
            requested[str(k)] = v
    for key, val in qargs.items():
        key_str = str(key)
        if key_str.startswith('filter_') and len(key_str) > 7:
            requested[key_str[7:]] = val
    return requested


def _format_kiosk_cell(value: Any, fmt: Mapping[str, Any] | None) -> str:
    if value is None:
        return ''
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        f = fmt or {}
        nfmt = str(f.get('number_format') or 'standard')
        dec = int(f.get('decimals', 2))
        curr = str(f.get('currency_code') or 'USD')
        symbols = {'USD': '$', 'EUR': '€', 'GBP': '£', 'CAD': 'CA$'}
        if nfmt == 'currency':
            return f"{symbols.get(curr, curr + ' ')}{value:,.{dec}f}"
        if nfmt == 'percent':
            return f'{value * 100:,.{dec}f}%'
        if nfmt == 'compact':
            abs_v = abs(float(value))
            if abs_v >= 1_000_000:
                return f'{value / 1_000_000:.{min(dec, 2)}f}M'
            if abs_v >= 1_000:
                return f'{value / 1_000:.{min(dec, 2)}f}K'
            return f'{value:,.{dec}f}'
        if isinstance(value, int) and dec == 0:
            return f'{value:,}'
        return f'{value:,.{dec}f}' if isinstance(value, float) else f'{value:,}'
    return str(value)


def _extract_card_table_data(
    store: DesignStore,
    card: Mapping[str, Any],
) -> tuple[list[str], list[list[str]], str]:
    ctype = str(card.get('type') or 'question')
    if ctype == 'text':
        md = str((card.get('text') or {}).get('markdown') or '')
        return ['Note'], [[md]], 'text'
    if ctype == 'metric_panel':
        mp = card.get('metric_panel') or {}
        cols = [
            str(c.get('label') or c.get('id') or 'Metric')
            for c in (mp.get('columns') or [])
        ] or ['Metric', 'Value']
        rows = [
            [str(cell) for cell in r]
            for r in (mp.get('rows') or [])
            if isinstance(r, list)
        ]
        return cols, rows, 'metric_panel'

    q_ref = card.get('question') or {}
    q_did = str(q_ref.get('question_design_id') or '')
    vis_type = str(
        (card.get('visualization') or {}).get('type') or 'bar'
    )
    if q_did:
        try:
            q_head = store.get_design(q_did)
            target_ver = (
                q_head.get('active_version')
                if q_ref.get('follow_latest_accepted')
                else (
                    q_ref.get('pinned_version')
                    or q_head.get('active_version')
                    or q_head.get('head_version')
                )
            )
            q_doc = store.get_design(q_did, version=target_ver)
            q_parsed = ddn_to_question(q_doc['version']['ddn_text'])
            question = q_parsed['question']
            vis_fmt = question.get('visualization_format') or {}
            cols_meta, raw_rows = _preview_columns_and_rows(question)
            headers = [c['id'] for c in cols_meta if c['id'] != 'row_id']
            rows_out = [
                [
                    _format_kiosk_cell(cell, vis_fmt)
                    for cell in r[1:len(headers) + 1]
                ]
                for r in raw_rows
            ]
            return headers, rows_out, vis_type
        except Exception:
            pass
    return ['Series', 'Value'], [['Sample', '0']], vis_type


_KIOSK_CSS = """
:root {
  color-scheme: dark;
  --bg: #0f172a;
  --panel: #1e293b;
  --border: #334155;
  --text: #f8fafc;
  --muted: #94a3b8;
  --accent: #38bdf8;
  --chip: #0ea5e926;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
}
.kiosk-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 20px;
  background: var(--panel);
  border-bottom: 1px solid var(--border);
}
.kiosk-title-group { display: flex; align-items: center; gap: 10px; }
.kiosk-title { margin: 0; font-size: 18px; font-weight: 600; }
.kiosk-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--chip);
  border: 1px solid var(--border);
  color: var(--accent);
}
.kiosk-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 20px;
  border-bottom: 1px solid var(--border);
  background: #0b1220;
}
.kiosk-chip {
  font-size: 12px;
  padding: 3px 9px;
  border-radius: 6px;
  background: var(--panel);
  border: 1px solid var(--border);
}
.kiosk-controls { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--muted); }
.kiosk-select, .kiosk-btn {
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 12px;
}
.kiosk-btn { cursor: pointer; }
.kiosk-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: 14px;
  padding: 16px 20px;
}
.kiosk-card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.kiosk-card-hdr {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.kiosk-card-title { margin: 0; font-size: 14px; font-weight: 600; }
.kiosk-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.kiosk-table th, .kiosk-table td {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
}
.kiosk-table th { color: var(--muted); font-weight: 600; }
.kiosk-error {
  max-width: 560px;
  margin: 64px auto;
  padding: 24px;
  background: var(--panel);
  border: 1px solid #ef4444;
  border-radius: 8px;
}
"""


def _render_error_html(status_code: int, message: str) -> str:
    esc_msg = html.escape(message)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ScratchRobin Kiosk — {status_code}</title>
  <style>{_KIOSK_CSS}</style>
</head>
<body data-form-key="{BI_KIOSK_FORM_KEY}" data-form-reference="{BI_KIOSK_FORM_REF}" data-kiosk-display-only="true">
  <main class="kiosk-error" role="alert">
    <div class="kiosk-title-group">
      <h1 class="kiosk-title">Display-Only Kiosk Access Denied ({status_code})</h1>
      <span class="kiosk-badge">{BI_KIOSK_FORM_REF}</span>
    </div>
    <p>{esc_msg}</p>
  </main>
</body>
</html>
"""


def _render_fragment_shell_html(publication_id: str) -> str:
    esc_pub = html.escape(publication_id)
    pub_json = json.dumps(publication_id)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ScratchRobin Display-Only Kiosk</title>
  <style>{_KIOSK_CSS}</style>
</head>
<body data-form-key="{BI_KIOSK_FORM_KEY}" data-form-reference="{BI_KIOSK_FORM_REF}" data-kiosk-display-only="true" data-publication-id="{esc_pub}">
  <header class="kiosk-header">
    <div class="kiosk-title-group">
      <h1 class="kiosk-title" id="kiosk-title">Remote Dashboard Kiosk</h1>
      <span class="kiosk-badge">Display-Only</span>
      <span class="kiosk-badge" id="kiosk-device-badge">Awaiting Device Token</span>
      <span class="kiosk-badge">{BI_KIOSK_FORM_REF}</span>
    </div>
    <div class="kiosk-controls">
      <label for="kiosk-refresh-select">Auto-refresh</label>
      <select id="kiosk-refresh-select" class="kiosk-select" aria-label="Auto-refresh interval">
        <option value="0">Off</option>
        <option value="30">30s</option>
        <option value="60" selected>60s</option>
        <option value="300">5m</option>
      </select>
      <span id="kiosk-countdown" aria-live="polite">60s</span>
    </div>
  </header>
  <section class="kiosk-filters" id="kiosk-filters" aria-label="Locked kiosk filters"></section>
  <main id="kiosk-main" class="kiosk-grid" aria-live="polite"></main>
  <script>
  (function () {{
    var pubId = {pub_json};
    var timerId = null;
    var remaining = 60;
    function readHashToken() {{
      var raw = (window.location.hash || '').replace(/^#/, '');
      var params = new URLSearchParams(raw);
      return params.get('token') || '';
    }}
    function clearNode(el) {{
      while (el.firstChild) el.removeChild(el.firstChild);
    }}
    function renderDenied(msg) {{
      var main = document.getElementById('kiosk-main');
      clearNode(main);
      var box = document.createElement('div');
      box.className = 'kiosk-error';
      box.setAttribute('role', 'alert');
      box.textContent = msg;
      main.appendChild(box);
    }}
    function loadDashboard() {{
      var tok = readHashToken();
      if (!tok) {{
        renderDenied('403: Display-only device token (#token=...) is required.');
        return;
      }}
      var url = '/cdeadmin/api/bi-server/dashboards/' + encodeURIComponent(pubId) + window.location.search;
      fetch(url, {{ headers: {{ 'Authorization': 'Bearer ' + tok }} }})
        .then(function (res) {{
          return res.json().then(function (body) {{ return {{ status: res.status, body: body }}; }});
        }})
        .then(function (out) {{
          if (out.status !== 200) {{
            renderDenied((out.body && out.body.error) || 'Access denied');
            return;
          }}
          var data = out.body;
          var sess = data.session || {{}};
          var design = sess.design || {{}};
          document.getElementById('kiosk-title').textContent = design.title || 'Published Dashboard';
          document.getElementById('kiosk-device-badge').textContent = 'Device: ' + (data.device_label || 'kiosk');
          var fltWrap = document.getElementById('kiosk-filters');
          clearNode(fltWrap);
          var flts = data.effective_filters || {{}};
          var keys = Object.keys(flts);
          if (!keys.length) {{
            var noneChip = document.createElement('span');
            noneChip.className = 'kiosk-chip';
            noneChip.textContent = 'No locked filters';
            fltWrap.appendChild(noneChip);
          }} else {{
            keys.forEach(function (k) {{
              var chip = document.createElement('span');
              chip.className = 'kiosk-chip';
              chip.textContent = k + ': ' + JSON.stringify(flts[k]);
              fltWrap.appendChild(chip);
            }});
          }}
          var main = document.getElementById('kiosk-main');
          clearNode(main);
          var views = sess.views || [{{ id: 'dashboard_composed', title: design.title || 'Overview' }}];
          views.forEach(function (v, idx) {{
            var card = document.createElement('article');
            card.className = 'kiosk-card';
            var hdr = document.createElement('div');
            hdr.className = 'kiosk-card-hdr';
            var h2 = document.createElement('h2');
            h2.className = 'kiosk-card-title';
            h2.textContent = v.title || v.id || ('Panel ' + (idx + 1));
            var toggle = document.createElement('button');
            toggle.type = 'button';
            toggle.className = 'kiosk-btn';
            toggle.textContent = 'Accessible Data Table';
            var tbl = document.createElement('table');
            tbl.className = 'kiosk-table';
            tbl.hidden = true;
            var tr = document.createElement('tr');
            var th = document.createElement('th');
            th.textContent = 'View';
            var td = document.createElement('td');
            td.textContent = (v.title || v.id || 'Panel');
            tr.appendChild(th);
            tr.appendChild(td);
            tbl.appendChild(tr);
            toggle.addEventListener('click', function () {{
              tbl.hidden = !tbl.hidden;
              toggle.setAttribute('aria-expanded', String(!tbl.hidden));
            }});
            hdr.appendChild(h2);
            hdr.appendChild(toggle);
            card.appendChild(hdr);
            card.appendChild(tbl);
            main.appendChild(card);
          }});
        }})
        .catch(function () {{
          renderDenied('Unable to reach ScratchRobin dashboard server.');
        }});
    }}
    var sel = document.getElementById('kiosk-refresh-select');
    var cd = document.getElementById('kiosk-countdown');
    function resetTimer() {{
      if (timerId) clearInterval(timerId);
      var sec = parseInt(sel.value, 10) || 0;
      if (sec <= 0) {{
        cd.textContent = 'Paused';
        return;
      }}
      remaining = sec;
      cd.textContent = remaining + 's';
      timerId = setInterval(function () {{
        remaining -= 1;
        if (remaining <= 0) {{
          remaining = sec;
          loadDashboard();
        }}
        cd.textContent = remaining + 's';
      }}, 1000);
    }}
    sel.addEventListener('change', resetTimer);
    window.addEventListener('hashchange', loadDashboard);
    resetTimer();
    loadDashboard();
  }})();
  </script>
</body>
</html>
"""


def render_bi_kiosk_html_response(
    store: DesignStore,
    proc: StoreDDNProcess | None,
    *,
    publication_id: str,
    query_args: Mapping[str, Any] | None,
    headers: Mapping[str, Any] | None,
    app: Any = None,
) -> tuple[str, int, str]:
    """Render chromeless display-only remote kiosk HTML (``SR-F-030034``)."""
    content_type = 'text/html; charset=utf-8'
    token = _extract_kiosk_token(query_args, headers)
    if not token:
        return (
            _render_fragment_shell_html(publication_id),
            200,
            content_type,
        )

    sync = BIDesignSync(
        store,
        proc,
        token_secret=_resolve_token_secret(app),
    )
    try:
        requested_filters = _extract_requested_filters(query_args)
        rendered = sync.render_dashboard_server_view(
            publication_id,
            device_token=token,
            requested_filters=requested_filters,
        )
    except (DesignStoreForbidden, DesignStoreNotFound) as exc:
        return _render_error_html(403, str(exc)), 403, content_type
    except DesignStoreError as exc:
        return _render_error_html(400, str(exc)), 400, content_type

    session = rendered.get('session') or {}
    design_meta = session.get('design') or {}
    ddn_text = str(
        session.get('ddn_text')
        or (session.get('version') or {}).get('ddn_text')
        or ''
    )
    if not ddn_text and design_meta.get('id'):
        doc = store.get_design(
            design_meta['id'],
            version=design_meta.get('active_version'),
        )
        ddn_text = str((doc.get('version') or {}).get('ddn_text') or '')
    parsed_dash = ddn_to_dashboard(ddn_text)
    dashboard = parsed_dash['dashboard']

    title_esc = html.escape(
        str(dashboard.get('name') or design_meta.get('title') or 'Dashboard')
    )
    dev_esc = html.escape(str(rendered.get('device_label') or 'kiosk'))
    pub_esc = html.escape(publication_id)

    eff_filters = dict(rendered.get('effective_filters') or {})
    if eff_filters:
        chips_html = '\n'.join(
            f'<span class="kiosk-chip" data-locked-filter="{html.escape(str(k))}">'
            f'Locked · {html.escape(str(k))}: '
            f'{html.escape(json.dumps(v) if isinstance(v, (list, dict)) else str(v))}'
            f'</span>'
            for k, v in sorted(eff_filters.items())
        )
    else:
        chips_html = '<span class="kiosk-chip">No locked filters</span>'

    card_blocks: list[str] = []
    for idx, card in enumerate(dashboard.get('cards') or []):
        cid = html.escape(str(card.get('id') or f'card_{idx + 1}'))
        ctitle = html.escape(str(card.get('title') or f'Card {idx + 1}'))
        col_headers, rows, vis_label = _extract_card_table_data(store, card)
        vis_esc = html.escape(vis_label)
        thead_cells = ''.join(
            f'<th scope="col">{html.escape(h)}</th>' for h in col_headers
        )
        tbody_rows = ''.join(
            '<tr>'
            + ''.join(f'<td>{html.escape(cell)}</td>' for cell in row)
            + '</tr>'
            for row in rows
        ) or (
            f'<tr><td colspan="{max(len(col_headers), 1)}">No rows</td></tr>'
        )
        summary_text = (
            f'{len(rows)} row(s) · {vis_esc} profile'
            if vis_label != 'text'
            else (html.escape(rows[0][0]) if rows and rows[0] else '')
        )
        card_blocks.append(f"""
    <article class="kiosk-card" data-kiosk-card="{cid}">
      <div class="kiosk-card-hdr">
        <div>
          <h2 class="kiosk-card-title">{ctitle}</h2>
          <span class="kiosk-badge">{vis_esc}</span>
        </div>
        <button type="button" class="kiosk-btn" data-toggle-table="tbl-{cid}" aria-expanded="false" aria-controls="tbl-{cid}">
          Accessible Data Table
        </button>
      </div>
      <div class="kiosk-card-visual" data-card-summary="{cid}">{summary_text}</div>
      <table id="tbl-{cid}" class="kiosk-table" role="table" aria-label="{ctitle} data table" hidden>
        <thead><tr>{thead_cells}</tr></thead>
        <tbody>{tbody_rows}</tbody>
      </table>
    </article>""")

    cards_joined = '\n'.join(card_blocks) or (
        '<p class="kiosk-chip">This published dashboard has no cards.</p>'
    )

    body_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title_esc} — ScratchRobin Kiosk</title>
  <style>{_KIOSK_CSS}</style>
</head>
<body data-form-key="{BI_KIOSK_FORM_KEY}" data-form-reference="{BI_KIOSK_FORM_REF}" data-kiosk-display-only="true" data-publication-id="{pub_esc}">
  <header class="kiosk-header">
    <div class="kiosk-title-group">
      <h1 class="kiosk-title">{title_esc}</h1>
      <span class="kiosk-badge">Display-Only</span>
      <span class="kiosk-badge">Device: {dev_esc}</span>
      <span class="kiosk-badge">{BI_KIOSK_FORM_REF}</span>
    </div>
    <div class="kiosk-controls">
      <label for="kiosk-refresh-select">Auto-refresh</label>
      <select id="kiosk-refresh-select" class="kiosk-select" aria-label="Auto-refresh interval">
        <option value="0">Off</option>
        <option value="30">30s</option>
        <option value="60" selected>60s</option>
        <option value="300">5m</option>
      </select>
      <span id="kiosk-countdown" aria-live="polite">60s</span>
    </div>
  </header>
  <section class="kiosk-filters" aria-label="Locked kiosk filters">
    {chips_html}
  </section>
  <main class="kiosk-grid">
    {cards_joined}
  </main>
  <script>
  (function () {{
    document.querySelectorAll('[data-toggle-table]').forEach(function (btn) {{
      btn.addEventListener('click', function () {{
        var id = btn.getAttribute('data-toggle-table');
        var tbl = document.getElementById(id);
        if (!tbl) return;
        tbl.hidden = !tbl.hidden;
        btn.setAttribute('aria-expanded', String(!tbl.hidden));
      }});
    }});
    var sel = document.getElementById('kiosk-refresh-select');
    var cd = document.getElementById('kiosk-countdown');
    var timerId = null;
    function resetTimer() {{
      if (timerId) clearInterval(timerId);
      var sec = parseInt(sel.value, 10) || 0;
      if (sec <= 0) {{
        cd.textContent = 'Paused';
        return;
      }}
      var rem = sec;
      cd.textContent = rem + 's';
      timerId = setInterval(function () {{
        rem -= 1;
        if (rem <= 0) window.location.reload();
        else cd.textContent = rem + 's';
      }}, 1000);
    }}
    if (sel && cd) {{
      sel.addEventListener('change', resetTimer);
      resetTimer();
    }}
  }})();
  </script>
</body>
</html>
"""
    return body_html, 200, content_type
