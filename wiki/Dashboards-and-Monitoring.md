# Dashboards and monitoring

Engine, endpoint/server and database dashboards are display-only. Their cards
show metrics the exact provider can observe, with native units, collection
scope and unavailable states. They must not invent a server CPU metric for an
embedded file database or treat a disabled collector as a healthy zero.

Use the selected endpoint/database context menu to configure collection.
Depending on the provider, choose registration credentials or a dedicated
monitoring account, a sampling interval, a bounded in-process retention window,
a lease and an optional heartbeat. A collector uses its own connection and
refreshes its own transaction; it does not use or commit an interactive SQL
editor session. A heartbeat is recorded only after a completed sample.

Opening or closing a dashboard does not start or stop a configured collector.
Use its monitoring policy controls for that. Gaps and unavailable values should
remain visible. Layout edits happen in the separately authorized DDN dashboard
editor and published definitions; the viewer itself has no layout editor.

Current in-process trends are volatile. Persistent monitoring history and its
ScratchBird storage backend are deferred. This does not defer persistent saved
dashboard definitions or SQL history. See the
[Firebird dashboard contract](https://github.com/scratchbird-software-inc/CDEadmin/blob/master/docs/en_US/firebird_dashboards.rst)
and each engine's functional contract for native metrics and collector rules.
