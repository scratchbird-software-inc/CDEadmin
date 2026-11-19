Data Navigator outstanding work
===============================

This checklist covers the Data Viewer and SQL Editor. Native execution,
editable-row cancellation and the transaction controls have focused
verification evidence in :doc:`data_navigator_surfaces`.

* Finish localization. The November 18, 2026 inventory checked 664 literal
  translation keys in these surfaces and their shared components against the
  bundled catalogs and non-fuzzy server messages. Of those, 414 lack a
  translation in at least one locale. Audit hard-coded interface text
  separately. Verify language changes with both surfaces already open.
* Decide whether Prepare Statement must show parameter types when using
  MariaDB or the MySQL C connector. The patched connectors return native
  result-column metadata and parameter slots. Their C libraries leave
  parameter types unavailable. Any additional metadata path must keep the
  active connection's SQL mode and temporary objects and must avoid executing
  the selected statement.
* Complete hands-on Linux desktop acceptance for both surfaces across the six
  engines, including Firebird network and embedded. Check placement at narrow
  and wide sizes, focus help, colour and typography, language changes, and the
  transaction, cancellation and staged-edit controls. The current Linux build
  includes both patched native connectors and the SQLite configuration bridge.
  It passed desktop startup, 551 backend tests, 83 frontend tests and live
  surface API checks on all six engines.
* Record Windows and macOS qualification when the platform teams provide
  their results.
* Commit and push the reviewed source changes after verification and owner
  authorization.

Information reports when a grid adjustment cannot be generated as native
SQL. Host-side numeric sorting of text is one such case. Keep that distinction
visible when saving queries from grid settings.
