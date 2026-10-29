.. _bi_embedding:

*********************************
Signed embedding of BI content
*********************************

Stream C4 (embedding). A dashboard or a saved question can be shown inside
another web site, in an ``<iframe>``, to people who have no account here. The
embedding site's server decides who may see what by signing a short-lived
*token*; this server verifies the token and runs the content. This is the same
model as Metabase "signed embedding". There are no public links and no
anonymous access: every request carries a token that only the owner of the
embed and the embedding site's server can produce.

The feature is **off by default** (``CDEADMIN_BI_EMBED_ENABLED = False``) and
exists in server mode only. While it is off the unauthenticated blueprint is not
registered, no embed can be enabled, and the BI UI shows nothing. The code is
``web/pgadmin/cdeadmin/bi/`` (``embeds.py``, ``embed_tokens.py``,
``embed_models.py``, ``embed_store.py``, ``embed_scheduler.py``,
``embed_public.py``); the UI is ``cdeadmin_ui/modules/bi/EmbedDialog.jsx``.
Sharing between signed-in users is :doc:`bi_permissions`; unattended runs are
:doc:`bi_alerts`, whose delegation machinery this page reuses.

What an embed is
================

An embed is a stored definition:

* the resource (a dashboard or a question), pinned to a revision or following
  the latest one;
* its owner and endpoint; an enabled flag (new embeds are created *disabled*);
  an optional expiry;
* the *parameters* the token may carry, each ``locked`` (value comes only from
  the token, the viewer sees it but cannot change it), ``editable`` (the token
  gives a starting value and the viewer may change it) or ``hidden`` (like
  locked, and not shown). A dashboard parameter is a dashboard filter; a
  question parameter is a question parameter. Anything not declared is refused;
* the *claims* the token may carry, each optionally required. Claims feed the
  semantic model's ``security_context`` and so its tenant and role row policies
  (for example ``tenant_id``);
* the *allowed origins*: the exact web origins that may frame it. They become the
  ``frame-ancestors`` of the frame page and nothing else;
* the maximum token lifetime (30 seconds up to ``CDEADMIN_BI_EMBED_MAX_TOKEN_LIFETIME``),
  whether tokens must be one-time (``require_jti``), the page size and row caps,
  and display options (title, theme, border, download, which is off by default).

Run-as identity
===============

An embedded view has no signed-in user and the viewer's browser holds no
credential. It runs with the **embed owner's delegated credentials**, the same
mechanism alerts use: enabling an embed asks the owner's own session to
authorize a delegation (encrypted with the worker key ring, with an expiry,
default 30 days, bound to the endpoint generation). The credentials are never in
the token, never sent to the browser and never logged.

The run is attributed to a distinct principal, ``embed:<embed id>:<digest of the
claims>``, and the security context handed to the semantic compiler is
``{"claims": {...token claims..., "principal": "embedding", "embed_id": <id>}}``.
This has three effects:

* row and tenant policies see the *token's* claims (``tenant_id`` and so on) and
  never the owner's identity. The owner's own ``user_id`` claim is not offered;
  ``user_id``, ``principal``, ``embed_id``, ``embedding`` and ``roles_override``
  are reserved and a token carrying them is refused;
* the result cache key and result ownership include the principal and a digest
  of the security context, so two tenants never share a cached result or a result
  id, and an interactive user's results are invisible to an embed and the other
  way round;
* the embed stops working, and is disabled with a recorded reason, as soon as
  the owner no longer has ``manage`` on the resource, the resource is archived or
  deleted, or the delegation expires, is revoked or the endpoint changes.

Raw SQL questions
-----------------

Raw SQL bypasses semantic row policies, so it is refused in embeds unless the
server setting ``CDEADMIN_BI_EMBED_ALLOW_RAW_SQL`` is on **and** the owner passes
``assert_raw_sql_allowed`` (which refuses it while the endpoint has row policies).
It is never allowed together with declared claims. The check is made when the
embed is created, updated and enabled, and again on every run, so turning the
setting off, or adding a row policy later, stops it at once.

Tokens
======

A token is ``header.payload.signature``, three canonical unpadded base64url
strings, like a JWT.

Header
    Exactly ``{"alg": "HS256", "kid": "<key id>"}`` and optionally ``"typ":
    "JWT"``. The algorithm is pinned: there is no negotiation, ``none`` and every
    other value are refused, and so is any other header member (``jku``, ``jwk``,
    ``x5u``, ``crit``, ``zip``...), so algorithm confusion has nothing to work
    with.
Signature
    HMAC-SHA256 over ``header.payload`` with the embed's secret. It is compared
    with ``hmac.compare_digest``. If the embed or the ``kid`` is unknown the same
    comparison is made against a dummy key, so the work done does not tell the
    two cases apart.
Payload members
    ``aud`` (must equal the embed id), ``exp`` (mandatory), ``nbf``, ``iat``,
    ``jti``, ``params``, ``claims``, ``iss``, ``sub`` and ``prv`` (set only by the
    server for previews). Any other member is refused.
Lifetime
    The remaining lifetime, ``exp - now``, may not exceed the embed's maximum;
    when ``iat`` is present ``exp - iat`` may not either. ``nbf`` and ``iat`` get
    15 seconds of leeway (``CDEADMIN_BI_EMBED_CLOCK_SKEW``); ``exp`` gets none.
Parameters and claims
    ``params`` and ``claims`` are objects of scalars or lists of scalars (claims:
    strings, integers, booleans or lists of them; no floats, no null, no
    nesting). Names must be declared by the embed. A missing required claim, an
    undeclared name or a reserved name refuses the token.
One-time tokens
    With ``require_jti`` (or for a preview) the token needs a ``jti``. The frame
    page needs it unused; the first ``/data`` call consumes it (a unique row in
    ``cde_bi_embed_jti``, so it is exact across worker processes); later calls of
    the same view (cards, paging, drills, exports) need it to have been opened.
    A replay of the page load is refused.

Strict parsing: the token is limited to 4096 bytes; base64url must be canonical
(no padding, no alternative encodings of the same bytes); the JSON must be one
object with no duplicate members and no NaN or Infinity.

Signing keys and rotation
-------------------------

Each embed has its own secret (43 URL-safe characters, 256 bits). It is shown
**once**, when the embed is created or the key is rotated, and is stored only as
an AES-GCM envelope of the worker key ring, bound to the embed id and the ``kid``
(so a ciphertext moved to another embed does not decrypt). If the key ring is not
configured, no embed can be created and no token verifies.

An embed holds at most two keys: ``current`` and ``previous``. *Rotate* makes a
new key current, demotes the current one to previous and drops the old previous,
so after a rotation both the old and the new key verify (the overlap in which the
embedding site switches over). A second rotation retires the first key. *Retire
previous key* drops it explicitly. *Revoke* drops all keys, revokes the
delegation and is permanent. ``flask cde-bi-embed-rotate-keys`` re-encrypts the
stored secrets and delegations under the key ring's active key.

Request flow
============

The public routes are under ``/cdeadmin/embed/<embed id>/``:

``frame`` (GET, ``?token=``)
    The iframe page. It is a small HTML shell with one inline script (CSP nonce)
    that reads the token from the address, removes it from the address bar and
    then calls the API with ``Authorization: Bearer``. The token therefore is not
    kept in history or sent in a ``Referer``.
``data`` (GET)
    The dashboard document or question view the page needs: names, layout,
    parameter descriptors, offered drill-throughs, display options. No question
    ids, SQL, plans or cache information.
``cards/<card id>/run`` (POST), ``run`` (POST, questions), ``page`` (POST),
``drill`` (POST), ``export`` (POST)
    Results, paging, drill-through and, if allowed, download.

Order of checks for every request: the per-IP budget; token syntax; the embed
lookup; one constant-time signature comparison; embed status and expiry; the
claims and lifetime; the declared parameters and claims; the per-embed budget
(charged only for tokens that *verified*, so an attacker without the secret
cannot exhaust a real embed's budget); the one-time id; and finally the owner's
live rights (``manage`` on the resource, the resource active). Only then does
anything run.

Every refusal before the run is the **same** ``404`` with the body
``{"success":0,"errormsg":"Not found"}``: bad token, wrong or unknown embed,
disabled, revoked, expired, owner lost access. The reason is never in the
response. (The owner can ask why with the ``bi_embed_check_token`` action.)
Parameter violations are ``400`` with a short code (``parameter_not_editable``,
``invalid_filters``, ``row_limit``...), rate limiting is ``429`` with
``Retry-After``, and an unexpected failure is ``500`` ``{"error": "failed"}``.
Failures while running a question return ``{"status": "error", "code":
"failed"}`` and never a driver message.

Parameter rules
---------------

* Locked and hidden values come **only** from the token. A viewer value for them
  is a ``400``.
* Editable values come from the viewer on top of the token's starting value.
* The viewer can send only declared editable parameters; anything else is a
  ``400``.
* Every value goes through the same typed binder as a normal dashboard run
  (``resolve_filters``): type, ``allowed_values``, ``multiple`` and so on. The
  binder runs before anything executes.
* Drill-through is offered, and accepted, only when the target is a question that
  is itself a card of the same dashboard. Locked and hidden filters win over the
  values taken from the clicked row. Cross-filtering is not offered.

Limits
------

Page size, the rows an embed may show in total (``max_rows``) and the paging
budget per result are capped by the embed and by ``CDEADMIN_BI_EMBED_MAX_PAGE_SIZE``
and ``CDEADMIN_BI_EMBED_MAX_ROWS``. Request bodies are limited to 64 KiB.
Downloads are off unless **all three** allow them: the server setting
``CDEADMIN_BI_EMBED_ALLOW_DOWNLOADS``, the embed's ``download`` option, and the
question's export policy.

Hardening of the public surface
===============================

* No CORS: no ``Access-Control-*`` header is ever sent, and ``OPTIONS`` is not
  answered. The embedding page uses an iframe, not cross-origin ``fetch``.
* ``frame-ancestors`` is exactly the embed's allowed origins (or ``'none'`` when
  there are none) and the frame page's CSP is ``default-src 'none'`` with a
  nonce'd script and style and ``connect-src 'self'``; ``X-Frame-Options`` is not
  sent on these routes (it cannot express an origin list). JSON responses carry
  ``frame-ancestors 'none'``. Wildcards, paths, ``http`` (except localhost) and
  credentials in an origin are refused when the embed is saved.
  The application's own headers middleware leaves these responses alone through
  a response marker; the rest of pgAdmin keeps its ``frame-ancestors 'self'``.
* No cookie is read or set: a WSGI layer (``EmbedIsolation``) removes the
  ``Cookie`` request header before the application sees it and any
  ``Set-Cookie`` from the response, and ``SESSION_SKIP_PATHS`` keeps the session
  machinery away. CSRF protection does not apply: the blueprint is exempt because
  the only credential is a bearer token that a browser never attaches by itself.
* ``Cache-Control: no-store``, ``Referrer-Policy: no-referrer``,
  ``X-Content-Type-Options: nosniff``, ``X-Robots-Tag: noindex``.
* Rate limits: a token bucket per client address (``CDEADMIN_BI_EMBED_IP_RATE``,
  default burst 120, 2/s), spent before anything is looked up, and one per embed
  (``CDEADMIN_BI_EMBED_RATE``, default burst 300, 10/s) charged after the
  signature verifies. The buckets are in process and bounded (least recently
  used keys are forgotten). See residual risks.
* Responses are whitelisted: rows and what a table needs. No SQL text, plan,
  reproducibility manifest, cache fingerprint, endpoint, user or question id.
* Audit: management events (create, update, enable, disable, rotate, retire,
  revoke, delete, mint) go to the resource's audit trail, without secrets or
  tokens. Views are only *counted* per embed per day (views, card runs, errors);
  there is no per-viewer record, no IP and no claim value stored.

Management actions
==================

Authenticated, through the BI action endpoint, and all require ``manage`` on the
resource. Secrets, key listing, rotation, enabling and minting are limited to the
embed's **owner**; any manager may list, read (without keys), disable, revoke and
read the counts.

``bi_embed_catalog``
    Server limits and whether the feature is available.
``bi_embed_list``, ``bi_embed_get``
    Embeds of a resource, with keys (``kid`` and slot only) for the owner.
``bi_embed_create``, ``bi_embed_update``
    Validate the definition against the resource (declared parameters must exist,
    required ones must be declared, raw SQL and downloads policy). ``create``
    returns the secret **once**. ``update`` is optimistic (``expected_revision``).
``bi_embed_enable``, ``bi_embed_disable``, ``bi_embed_revoke``, ``bi_embed_delete``
    Lifecycle. Enabling needs the owner's own session to authorize the
    delegation; deleting needs a disabled embed.
``bi_embed_rotate``, ``bi_embed_retire_key``
    Keys.
``bi_embed_mint``
    A token for testing, signed with the current key, which is refused if the
    runtime would refuse it (undeclared parameter, too long, reserved claim...).
    It exists so the owner can try an embed; production tokens are signed by the
    embedding site.
``bi_embed_preview``
    A server-minted token valid for ``preview_seconds`` (default 120), one-time,
    marked ``prv`` so that the frame page also allows ``'self'`` as an ancestor.
    The BI UI uses it for its live preview and it is worthless elsewhere.
``bi_embed_check_token``
    Why a token is, or is not, accepted. Does not consume a one-time id.
``bi_embed_stats``
    Daily counts.

Configuration
=============

``CDEADMIN_BI_EMBED_ENABLED``
    Master switch, default ``False``. Server mode only.
``CDEADMIN_BI_EMBED_ALLOW_RAW_SQL``
    Default ``False``. See above.
``CDEADMIN_BI_EMBED_ALLOW_DOWNLOADS``
    Default ``False``.
``CDEADMIN_BI_EMBED_MAX_TOKEN_LIFETIME``
    Seconds, default 3600.
``CDEADMIN_BI_EMBED_IP_RATE`` / ``CDEADMIN_BI_EMBED_RATE``
    ``(burst, tokens per second)``.
``CDEADMIN_BI_EMBED_MAX_PAGE_SIZE`` / ``CDEADMIN_BI_EMBED_MAX_ROWS``
    Defaults 200 and 5000.

The worker key ring (``CDEADMIN_REPORT_WORKER_KEYS`` and
``CDEADMIN_REPORT_WORKER_ACTIVE_KEY_ID``, :doc:`report_delivery`) must be
configured. Behind a reverse proxy, configure it to pass the client address the
way the rest of pgAdmin expects (``X_FORWARDED_*``), or the per-IP bucket sees
the proxy.

Embedding site example (pseudo-code)
====================================

Sign on **your server**; never put the secret in a browser or a mobile app::

    token = HS256_sign(
        header  = {"alg": "HS256", "typ": "JWT", "kid": <kid>},
        payload = {"aud": <embed id>, "iat": now, "exp": now + 300,
                   "params": {"region": "east"},
                   "claims": {"tenant_id": 42}},
        secret  = <the secret shown at creation>)
    iframe src = https://<this server>/cdeadmin/embed/<embed id>/frame?token=<token>

Mint a token per page view, with the shortest lifetime that works, and put in it
only what that viewer may see.

Threat model
============

Assets: the data the owner can read; the owner's delegated credentials; the
signing secrets; the availability of the database behind the embed.

Attackers and what stops them:

* *Anyone on the internet without a token.* Every route needs a verified token;
  all failures look the same; per-IP limiting; no information about whether an
  embed exists.
* *A viewer of an embedded page* (they hold a valid token for their own view):
  cannot change locked or hidden parameters or claims (inside the signature, and
  viewer input for them is refused), cannot add parameters, cannot reach another
  tenant's results (principal in the cache key and result ownership), cannot
  page past the row cap, cannot reach resources outside the embed (drill targets
  must be cards of the same dashboard), cannot download unless the embed, the
  server and the export policy allow it, cannot learn SQL or credentials.
* *A forger without the secret.* Pinned algorithm, strict parsing, constant-time
  compare with a dummy key for unknown ids, no pre-verification enumeration, and
  failed attempts cannot drain the embed's budget.
* *Someone holding an old or leaked token.* Mandatory short ``exp`` capped by the
  embed; optional one-time ids; revoking or disabling the embed, or rotating the
  key twice, ends it at once.
* *A malicious embedding page* trying to read responses: there is no CORS and the
  responses are only for the frame; ``frame-ancestors`` limits who can frame the
  page. A page that is *allowed* to frame the embed sees what the iframe shows
  to its viewer, which is the point.
* *Another site framing the embed* (clickjacking): ``frame-ancestors`` from the
  allowed origins only.
* *A malicious or careless owner*: an embed can only expose what the owner can
  already manage, runs with the owner's credentials only while the owner keeps
  ``manage``, and the owner is accountable in the audit trail.
* *Database theft:* the secrets and the delegated credentials are encrypted with
  the worker key ring, bound to their embed.
* *CSRF / session fixation:* no cookies, no session, bearer token only.

Residual risks
==============

* **HS256 secrets are shared.** Anyone who holds the secret can mint tokens for
  the embed until it is rotated and the previous key retired. An asymmetric
  scheme (Ed25519) would let the embedding site keep the private key; it is not
  implemented, to keep the first version to one audited algorithm.
* **Run-as is the owner.** The data an embed can reach is everything the owner's
  database account can reach through the embedded resource. Semantic row
  policies and the owner's account are the only fine-grained control; use a
  restricted database account and semantic models with tenant filters for
  multi-tenant embedding. Raw SQL cannot be filtered by claims, hence refused.
* **Rate limits are per process.** With several worker processes the effective
  limit is multiplied by the number of processes; a shared limiter belongs in
  the reverse proxy. One-time ids are exact across processes (database).
* **A token is visible to the viewer's browser.** It sits in the iframe address
  until the page script removes it, and the embedding site's own page. Keep
  lifetimes short and use one-time ids for sensitive content.
* **Claims are trusted.** A buggy embedding site that signs the wrong
  ``tenant_id`` shows the wrong tenant's data. The server cannot know better.
* **Counters are approximate** (a failed counter write never breaks a view).
* **Cache keys include claims**, so a high-cardinality claim (a per-user id)
  multiplies cache entries; the cache is bounded as for other runs.

Decisions to confirm
====================

#. HS256 only; Ed25519 later.
#. ``manage`` on the resource is required of the owner at run time (stricter than
   ``view``), and losing it disables the embed rather than pausing it.
#. ``jti`` semantics: opened by the first data call, so the frame page alone does
   not consume it.
#. The in-process rate limiter.
#. Cross-filtering is not offered in embeds; drill-through only within the
   dashboard.
#. Server mode only.
#. The migration ``cde_bi_embeds_v1`` follows ``cde_bi_alerts_v1`` and does not
   bump ``SCHEMA_VERSION``.

Tests
=====

``tools/tests/test_cdeadmin_bi_embedding.py``, with ``bi_embed_harness.py``:
token rules in isolation; the forging matrix over the real blueprint; locked,
editable and hidden parameters; a claim-driven tenant policy on live SQLite and
DuckDB; cache and result separation; rate limiting; headers, cookies and CORS;
raw SQL; owner access loss; secret hygiene; the management actions; and the real
tables and migration.
