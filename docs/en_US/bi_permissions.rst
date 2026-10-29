.. _bi_permissions:

**************************************
Sharing and permissions for BI content
**************************************

Stream C4 (permissions part). Collections, saved questions and dashboards were
strictly owner-only (:doc:`bi_saved_questions`, :doc:`bi_dashboards`). This page
describes how they are shared. The code is ``web/pgadmin/cdeadmin/bi/access.py``
(``BIAccess``); ``service.py``, ``dashboards.py`` and ``execution.py`` call it
for every decision. The UI is in :doc:`bi_query_builder_ui` and
:doc:`bi_dashboard_ui` (``cdeadmin_ui/modules/bi/ShareDialog.jsx``). Public
links and embedding are not part of this and do not exist.

The model
=========

A *grant* gives one principal one access level on one collection, saved
question or dashboard at one endpoint.

Principal
    A real pgAdmin ``User`` or ``Role`` row (``user.id`` / ``role.id``). Exactly
    one of ``user_id`` and ``role_id`` is set (check constraint); a user gets
    the grants of every role they hold. There is no separate identity system.
Access level
    ``view`` < ``edit`` < ``manage``.

    ``view``
        See the item and run it. Raw SQL text is redacted (below).
    ``edit``
        Change it, archive/restore, move, duplicate, read raw SQL, restore
        revisions. Each edit records the editor as the revision actor.
    ``manage``
        Everything above plus delete, change grants, change inheritance and
        transfer ownership.
Endpoint scope
    A grant applies only at the ``endpoint_id`` it was made at, like the
    content itself. The same question id at another endpoint is unaffected.

Tables (migration ``cde_bi_permissions_v1``, chained after
``cde_bi_dashboards_v1``; ``SCHEMA_VERSION`` is not bumped, as owner-confirmed):

``cde_bi_grant``
    ``grant_id``, ``endpoint_id``, ``resource_type``, ``resource_id``,
    ``user_id`` or ``role_id`` (foreign keys, ``ON DELETE CASCADE``), ``level``,
    ``created_by``, ``created_at``. Unique per resource and principal.
``cde_bi_access_override``
    One row per item that stops inheriting from its collection.
``cde_bi_audit``
    ``actor_user_id``, ``action``, ``resource_type``, ``resource_id``, target
    principal, detail and timestamp. The repository had no audit mechanism for
    BI, so this small table was added. Entries: ``grant.add``,
    ``grant.update``, ``grant.remove``, ``inherit.set`` and ``owner.transfer``.
``actor_user_id`` on both revision tables
    The user who made the revision. Revisions stay immutable.

Effective access
================

``effective access = max(owner -> manage, direct grants, inherited grants)``.

* The owner always has ``manage``.
* A grant on a collection flows down to its sub-collections, saved questions
  and dashboards filed in it.
* An item (or sub-collection) with an *override* (inheritance turned off) takes
  only its own direct grants and its owner; nothing from above reaches it.
  Turning inheritance back on removes the override.
* The owner of a collection counts as ``manage`` over items filed in it by
  others, unless an override cuts it.
* No grants means owner-only, exactly as before.

``BIAccess.require(user_id, kind, endpoint_id, resource_id, minimum, action)``
is the single authorization function. No view access, or a missing item, raises
the same ``<label> is unavailable`` error, so existence is not disclosed. View
access without the needed level raises ``BIPermissionDenied`` (a ``BIError``)
naming the level required. Every ``bi_*`` entry point goes through it; the
earlier ad-hoc ``user_id`` filters are gone. Deleting an item purges its
grants, overrides and audit rows.

Running shared content
======================

Sharing does not widen data access.

* A run executes with the **runner's** endpoint credentials and the runner's
  semantic row policies, never the owner's. ``security_context`` carries the
  runner's ``user_id``. The semantic model is resolved from the question's
  owner (the definition refers to it), but its policies are applied for the
  runner.
* Raw-SQL questions stay subject to ``assert_raw_sql_allowed`` for the runner
  (the owner's models are scanned as well, so a model the owner can use cannot
  be used to smuggle past the runner's policy).
* The result cache key includes the principal. Cache entries are never shared
  between users, and an edit by anyone invalidates the question's entries for
  all users. Paging and export re-check access.

Redacted SQL
------------

A viewer (``view`` only) can run a raw-SQL question but not read it:
``definition.query.sql`` is empty and ``sql_redacted`` is true on get;
``bi_question_execute`` returns ``sql: null`` and ``sql_redacted``; compile
returns no source; execution errors are generic; clone is refused (it would
copy the text); a revision fetch is redacted the same way. Builder questions are not redacted, since
the definition is structured. ``edit`` and above see everything.

Dashboards
----------

Viewing a dashboard needs ``view`` on the dashboard. Each card runs only if
the runner also has ``view`` on the underlying question; otherwise the card
answers ``{"no_access": true}``, with no question name, SQL or error text. Cards
pin the owner's question revisions as before; pinning a question needs ``view``
on it for the person saving the dashboard. A question in use by a dashboard
the caller cannot see is reported without that dashboard's name.

Ownership transfer
==================

Needs ``manage`` and the exact name of the resource typed as confirmation. The
new owner must be a user the caller can see. The previous owner keeps ``edit``
through a new direct grant. The transfer is audited.

Principal visibility
====================

``bi_principal_search`` returns only principals the caller may see: their own
roles and the active users who share a role with them. An administrator sees
all. Email addresses are never returned. Granting to a principal the caller
cannot see fails with the uniform unavailable error.

Actions
=======

All are workspace actions (``/browser/server/cde_workspace/...``). Items carry
``access`` (the caller's level) and ``is_owner``.

``bi_access_get``
    ``{resource_type, resource_id}`` -> effective level and its sources.
``bi_grant_list``
    -> ``{owner, inherit, direct[], inherited[]}`` (needs ``manage``).
``bi_grant_add``
    ``{..., principal_type, principal_id, level}``.
``bi_grant_update`` / ``bi_grant_remove``
    ``{..., grant_id[, level]}``.
``bi_access_inherit``
    ``{..., inherit}``.
``bi_transfer_owner``
    ``{..., new_owner_id, confirm}``.
``bi_shared_with_me``
    -> ``{collections (tree), questions, dashboards}`` shared with the caller at
    this endpoint.
``bi_principal_search``
    ``{text, kinds?, limit?}`` -> ``{items: [{type, id, name}]}``.
``bi_audit_list``
    ``{resource_type, resource_id}`` (needs ``manage``).

``resource_type`` is ``collection``, ``question`` or ``dashboard``. List
actions (``bi_question_list``, ``bi_dashboard_list``, history) return what the
caller can see; ``bi_collection_list`` stays the caller's own tree and the
shared tree is under ``bi_shared_with_me``.

UI
==

The BI module shows a *Shared with me* root in the collection browser, a Share
dialog (principal search, level select, direct and inherited grants with
removal of direct ones, inheritance switch, ownership transfer with typed
confirmation), a read-only banner, controls hidden or disabled by effective
access, a redacted-SQL notice and a "No access" card in dashboards. All of this
only reflects what the server will do; the server enforces every rule.
``sharing.js`` holds the pure reducer; the Jest tests use responses generated
from the real backend by
``tools/tests/fixtures/cdeadmin_bi/generate_sharing_ui_fixtures.py``.

What is deliberately not shared
===============================

* Endpoint credentials, connection settings and the runner's database
  permissions. A viewer runs with their own.
* Semantic models. A shared question refers to the owner's model; the model
  itself is not listed or editable through the grant. Share it separately.
* Result cache entries, result ids and exports of other users.
* Public or unauthenticated links and embedding (separate task).
* Folder membership: filing a question in someone else's collection needs
  ``edit`` on the destination collection (and on the item).

Residual risks
==============

* **Endpoint-id keyed grants.** Endpoints are per server registration. Two
  users who each registered the same server have different endpoint ids, so a
  grant made by one does not reach the other. Sharing works for users of the
  same registration (shared servers). Matching registrations by connection
  identity is not done and needs an owner decision.
* **Collection inheritance reaches items filed by others.** Someone who files
  an item into a collection shared with a team exposes it to that team (and
  the collection owner). The item's owner can turn inheritance off.
* **The raw-SQL guard is lexical.** ``assert_raw_sql_allowed`` rejects the SQL
  by scanning for protected tables; it is the same guard as before and is not a
  database permission. The runner's own database permissions remain the real
  boundary.
* **Error messages from the database** can quote parts of a statement. Errors
  for redacted questions are replaced by a generic message, but a database
  error returned for an ``edit`` user is shown as is.
* **The shared default ``User`` role.** Everyone holds it, so a grant to it
  reaches every user, and every user is visible to everyone through it in
  principal search.
* **Performance.** Access is evaluated from one in-memory snapshot of the
  caller's grants and the collection tree at an endpoint per call. That is
  fine for hundreds of items; thousands of grants would want indexes or
  caching.
* **Deleted principals.** Removing a user or role cascades their grants. Items
  owned by a deleted user remain with no owner able to manage them; an
  administrator would have to take them over.

Tests
=====

``tools/tests/test_cdeadmin_bi_permissions.py`` (with
``tools/tests/bi_permissions_harness.py``): owner / viewer / editor / manager /
no-grant / role-member across inheritance and overrides, dashboards with
unshared cards, run-as-runner (a recording stub captures the
``security_context`` and the policy, on real SQLite/DuckDB), redaction,
revision actor, ownership transfer, non-leak of existence, cache key with the
principal, the migration, and an integration test against the real tables.
