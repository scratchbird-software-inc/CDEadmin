.. _bi_alerts:

****************************************
Alerts and subscriptions for BI content
****************************************

Stream C4 (threshold alerts). A saved question can raise an *alert* when a
measured value crosses a threshold, and a saved question or dashboard can be
sent on a schedule as a *subscription* (a snapshot in CSV, XLSX, PDF or SVG).
Both run unattended, with the owner's own access, on the existing report
scheduler. The code is ``web/pgadmin/cdeadmin/bi/`` (``alerts.py``,
``alert_models.py``, ``alert_scheduler.py``, ``alert_delivery.py``,
``alert_store.py``, ``webhook.py``); the UI is
``cdeadmin_ui/modules/bi/AlertsPanel.jsx`` and ``AlertDialog.jsx``. Sharing is
described in :doc:`bi_permissions`.

What it does
============

Alert
    Defined on a saved question (builder or semantic; raw SQL only when the
    owner passes ``assert_raw_sql_allowed``). On each scheduled run the question
    is executed and a *condition* is evaluated:

    * ``row_count`` or a column aggregate (``first``, ``sum``, ``avg``, ``min``,
      ``max``) compared with ``> >= < <= == != between`` against a constant, or
      against the previous evaluation as an absolute or percent change;
    * results ``exist`` or are ``empty``.

    By default an alert is *edge triggered*: it notifies when the condition
    first becomes true and again only after it has recovered and breached anew.
    ``fire_on: every_evaluation`` notifies on every run while it is in breach.
    An evaluation that cannot decide (no value, a null first value) leaves the
    state alone.
Subscription
    A scheduled snapshot of a question or dashboard in one export format. It is
    subject to the result policy's export rules, like a manual export.
Mute
    A mute always has an expiry (one minute to ninety days). A check that
    breaches while muted is recorded as suppressed (``muted``) and remembered:
    if the alert is still in breach when the mute ends, it notifies once.
Re-arm
    Forgets the breach state, so the next breach notifies again.
Parameters and filters
    A question alert may fix parameter values; a dashboard subscription may fix
    filter values. Blank values are left to the question defaults.

Channels
========

In-app (``in_app``)
    A row in ``cde_bi_notification`` per recipient. The ``bi_notification_list``
    and ``bi_notification_read`` actions list and mark them; a badge in the shell
    is not built yet.
Email (``email``)
    The ``report_delivery`` SMTP adapter and profile (``profile_id``). The
    profile's own ``allowed_domains`` still apply.
Object storage (``s3``)
    The ``report_delivery`` S3 adapter and profile; the object name is relative
    to the profile's fixed prefix.
Webhook (``webhook``)
    A signed ``POST`` of a JSON body. Headers: ``X-CDEadmin-Timestamp``,
    ``X-CDEadmin-Signature`` (``v1=`` plus hex HMAC-SHA256 over
    ``timestamp.body`` with the host's secret), ``X-CDEadmin-Key-Id`` and
    ``X-CDEadmin-Delivery`` (stable per occurrence, for de-duplication by the
    receiver). The receiver should reject a timestamp outside its tolerance.

Recipients are authorized again at send time, not only when the alert is saved:

* a pgAdmin user needs an active account and ``view`` on the resource;
* an external email address needs the server allow-list
  (``CDEADMIN_BI_EXTERNAL_RECIPIENTS``) and the alert owner needs ``manage`` on
  the resource;
* object storage and webhooks leave the application, so they also need the
  owner to hold ``manage``;
* content whose semantic model declares row or tenant filters was computed with
  the owner's row policy and is delivered to the owner only.

An alert message never carries more than a small number of rows
(``CDEADMIN_BI_ALERT_MESSAGE_ROWS``, default 5, never more than 25), with bounded
columns and cell length. Redacted columns and the export policy apply.

Credentials, state and failure
==============================

An alert runs with the credentials its owner delegated for a limited time
(default 30 days, at most a year), encrypted with the worker key ring under a
BI-specific resolver id and AAD schema, so a report credential cannot be used
for an alert or the other way round. Creating, editing or resuming an alert
authorizes a new delegation; nothing else can.

Before each run the owner's access is checked with ``BIAccess``. If the owner
lost ``view`` on the question (or dashboard), the alert is *paused* with the
reason ``resource_unavailable``, the delegated credentials are destroyed, and
nothing is executed. Other reasons to pause: ``delegation_expired``,
``endpoint_changed``, ``credential_unavailable``, ``repeated_failures`` (five
consecutive failures) and ``user_paused``. Resuming asks the owner to authorize
again.

Delivery is at most once. The new state is stored before delivery, and a
delivery whose result is not known is recorded as ``outcome_unknown`` and is not
retried. A missed run beyond the scheduler's ``max_lateness`` is recorded as a
misfire, not run late.

Actions
=======

All are ``bi_*`` workspace actions (``BIAlertService.ACTIONS``).

``bi_alert_catalog``
    Channels the server offers, profiles, allowed webhook hosts, limits and
    whether scheduling is available.
``bi_alert_schedule_preview``
    Next instants and shortest interval of a schedule.
``bi_alert_list``
    Alerts and subscriptions of one resource that the caller owns or manages.
``bi_alert_get``
    One alert with its definition and next runs.
``bi_alert_create`` and ``bi_alert_update``
    Create and authorize; update takes ``expected_revision``.
``bi_alert_delete``
    Delete and revoke the delegation.
``bi_alert_test``
    Dry run by id or of an unsaved definition, with the caller's own session.
    Nothing is sent, stored or changed.
``bi_alert_run_now``
    One real evaluation now, through the lease path (owner only, at most one
    every 15 seconds).
``bi_alert_mute`` and ``bi_alert_unmute``
    ``duration_minutes`` or ``until`` for a mute.
``bi_alert_rearm``, ``bi_alert_pause`` and ``bi_alert_resume``
    Forget the breach state; stop running; authorize again and run again.
``bi_alert_history``
    Recent checks (200 are kept).
``bi_notification_list`` and ``bi_notification_read``
    The caller's in-app notifications; mark some or all as read.

Who may do what: the owner can do everything. A user with ``manage`` on the
resource can list, read the history of, mute, unmute, pause and delete someone
else's alert, but cannot edit, test, run or resume it, because those use the
owner's delegated access. Everyone else gets the uniform "unavailable" answer.

Tables
======

Migration ``cde_bi_alerts_v1``, chained after ``cde_bi_permissions_v1``;
``SCHEMA_VERSION`` is not bumped. ``cde_bi_alert``,
``cde_bi_alert_delegation``, ``cde_bi_alert_credential``,
``cde_bi_alert_occurrence`` (unique per delegation and scheduled instant),
``cde_bi_alert_event`` and ``cde_bi_notification``. The delegation, credential
and occurrence tables mirror the report scheduler's, and the scheduler, lease,
heartbeat, stale-recovery and worker code is shared, not copied: the BI worker is
registered as a companion of the report worker.

Configuration
=============

``CDEADMIN_BI_ALERT_MESSAGE_ROWS``
    Rows in a message (default 5, at most 25).
``CDEADMIN_BI_ALERT_MIN_INTERVAL_SECONDS``
    Shortest allowed schedule gap (default 300).
``CDEADMIN_BI_ALERT_MAX_PER_USER``
    Alerts and subscriptions per user (default 50).
``CDEADMIN_BI_EXTERNAL_RECIPIENTS``
    ``{"domains": [...], "addresses": [...]}`` allowed for external email. Empty
    means none.
``CDEADMIN_BI_WEBHOOK_HOSTS``
    ``{host: {secret, port, key_id}}``. Empty means no webhooks.
``CDEADMIN_BI_WEBHOOK_TIMEOUT``
    Seconds (default 5, at most 15).

User interface
==============

*Alerts...* on a saved question and *Subscriptions...* on a saved dashboard open
a section with the list, per-row actions, a history table and the create/edit
dialog: a condition builder, a schedule picker (hourly, daily, weekdays, weekly
or a custom cron expression, in an IANA time zone) with the next runs from the
server, and a channel and recipient picker with user search. *Test evaluate*
shows the verdict, the message and the deliveries that would happen, and sends
nothing. The model is pure (``alerts.js``) and tested with fixtures generated
from the real backend (``generate_alert_ui_fixtures.py``).

Security model
==============

* Alerts never lend access. They run as the owner, with the owner's current
  access checked at every run; viewers of a shared question create their own
  alerts under their own access.
* Webhooks are the main outbound risk. A host must be in the server allow-list;
  the name is resolved once, every address must be public (loopback, private,
  link-local, multicast, unspecified, IPv4-mapped, 6to4 and Teredo forms of
  those are refused), and the connection is made to the checked address with
  the original name for TLS and ``Host``, so a second lookup cannot rebind it.
  Redirects are not followed, the timeout is short and the response body is not
  read beyond a small bound. Secrets are server configuration, never stored in
  an alert.
* History and API answers use a fixed text catalogue for failures. SQL, driver
  messages, paths and addresses never appear. Only people who can edit the
  content see a short technical detail line, and webhook URLs are shown only to
  the owner and managers.
* Recipients and the row cap are enforced when sending, so a permission change
  after saving takes effect on the next run.

Residual risks
==============

* A user with ``manage`` on a question can deliver its (capped) rows to external
  recipients on the allow-list through their own alert. The allow-list is the
  control.
* A message that has left the application cannot be recalled. Revoking access
  stops later messages only.
* Delivery is at most once: a crash between the stored state and the send loses
  one notification instead of repeating it.
* A webhook receiver that does not check the timestamp can be replayed by
  anyone who captured a request. Signing does not hide the body; use HTTPS.
* Clock skew moves the signed timestamp; the receiver's tolerance must allow it.
* Running now moves the schedule base, so the next scheduled run follows the
  manual one.
* The shell notification badge is not built; people see in-app notifications
  only through the list action until it is.
