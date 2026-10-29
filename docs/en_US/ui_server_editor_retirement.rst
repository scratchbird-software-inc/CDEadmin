.. _ui_server_editor_retirement:

Server editor: legacy registration retirement
=============================================

Decision (owner, 2026-10-28): retire the legacy registration dialog for MariaDB,
Firebird, DuckDB and SQLite **without a prior real-browser test**, accepting the
risk, with the old paths commented out and fully documented so that a person or a
locally hosted AI can trace and correct failures.

Status: **UNVERIFIED IN A BROWSER.** Verified only by Jest
(``web/regression/javascript/families/ServerRegistrationHost.spec.jsx``), the Python
round trips (``tools/tests/test_ui_descriptor_server_forms.py``) and descriptor
validation. Nothing has been run in a live pgAdmin shell.

What changed
------------

* ``web/pgadmin/browser/static/js/ProviderObjectEditor.jsx``: ``tryOpenServerForm``
  opens ``ServerRegistrationHost``; ``LEGACY_REGISTRATION_RETIRED`` (the engine set)
  and ``reportServerEditorFailure``.
* ``web/pgadmin/browser/server_groups/servers/static/js/server.js``
  ``register_engine_server`` and ``web/pgadmin/browser/static/js/ProviderContextMenu.js``
  ``edit_endpoint``: for retired engines a failure shows an error notification instead
  of opening the legacy dialog. The old fallback expression is kept as a
  ``LEGACY-FALLBACK`` comment.
* ``server.ui.js`` is untouched apart from a header comment: PostgreSQL, MySQL and
  the ``create_database`` / ``register_existing`` intents still use it.

Data flow
---------

#. Tree action -> ``tryOpenServerForm`` fetches ``/cdeadmin/api/ui/descriptors/<engine>``
   and requires ``forms.server.status == 'complete'``.
#. ``ServerRegistrationHost`` (``web/pgadmin/static/js/cdeadmin_ui/objects/``) builds the
   record: create from ``initialData`` (``register_engine_server``), edit from
   ``GET /browser/server/obj/<gid>/<sid>``; ``recordFromBackend`` (``descriptors.js``)
   re-keys ``backend_field_id`` to ``field_id`` and decodes JSON text for grid/keyvalue.
#. ``ObjectEditor`` in ``directApply`` mode (no plan, no Preview SQL) collects the draft;
   ``toBackendDraft`` maps to servers-API keys (``cde_route_<id>``, ``cde_secret_<id>``,
   ``db``, ``username`` ...); ``registrationPayload`` adds ``cde_profile_id``,
   ``cde_registration_intent``, ``cde_verify_now`` (a ``profile`` select, Firebird only,
   becomes ``cde_profile_id``).
#. POST (create) / PUT (edit) to the URL from ``generateNodeUrl``; the response ``node``
   feeds ``pgadmin:browser:tree:add`` / ``tree:update``, as ``node.js show_obj_properties``
   does.
#. Backend: ``web/pgadmin/browser/server_groups/servers/__init__.py`` create/update/properties.

Edit sends only changed fields (the alter rule), so an untouched password or secret is
never resent; the server keeps the stored value.

Likely failure points to check first
------------------------------------

* ``verified_runtime_version`` is unknown before first verification; the bundle is then
  fetched without ``?version=``. Check the descriptor service resolves that.
* Edit pre-fill depends on the properties response carrying ``cde_route_*`` values
  (``servers/__init__.py`` around line 1868). A missing field shows empty and, if saved
  unchanged, is simply not sent.
* ``clear_cache`` and the ``tree:update`` success callback were copied from ``node.js``;
  confirm the node label and icon refresh after editing name or colours.
* ``connect_now`` / ``cde_verify_now``: legacy defaulted ``connect_now`` to false for
  provider endpoints; the form default is ``true``. Confirm the server tree does not
  attempt a PostgreSQL connection.
* Multi-profile engines (Firebird native/embedded): the ``profile`` select value must
  become ``cde_profile_id``; changing it on edit changes the profile of a saved server.
* DuckDB / SQLite ``attached_databases`` and ``config``: grid and keyvalue values are sent
  as JSON values; the legacy dialog sent JSON text. ``provider_route_options`` accepts both
  (Python twin: ``registration_data`` in ``tools/ui_descriptor_roundtrip.py``).

Smoke test that closes the risk
-------------------------------

For each of SQLite, MariaDB and Firebird: register a server, confirm the tree node
appears with the right icon and engine, verify it, edit the name and one route field,
confirm the change persists after reload, and confirm an unchanged password survives.
Record the result below; only then may the provider_endpoint branches of ``server.ui.js``
be reduced to the engines that still need them.

Restoring the legacy dialog
---------------------------

#. Remove the engine from ``LEGACY_REGISTRATION_RETIRED`` (``ProviderObjectEditor.jsx``).
   The fallback then applies to it again, in both ``server.js`` and
   ``ProviderContextMenu.js``.
#. Optionally uncomment the ``LEGACY-FALLBACK`` lines for the original one-line form.
#. To disable the new editor for an engine, set that engine's ``forms/server.form.json``
   ``status`` to ``draft``; ``tryOpenServerForm`` then returns false (and, once the
   engine is out of the retired set, the legacy dialog opens).

Smoke test log
--------------

(empty: not yet run)
