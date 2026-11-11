.. _menu_bar:

*****************
Command menus
*****************

CDEadmin's top-level menus contain project-wide commands. Engine-specific
administration is supplied by the selected Object Explorer node and is not
hard-coded into the global menu structure.

File
====

The *File* menu manages CDEadmin projects, workspace files, imports/exports,
recent work, preferences and application exit where appropriate to the host.

Connectors
==========

The *Connectors* menu lists the connector types included in the current build.
Each item is a per-user checked preference. Checked connectors are visible in
the Object Explorer; unchecked connectors are hidden. The menu does not create
arbitrary connector implementations at runtime.

Object
======

The *Object* menu is populated from commands valid for the selected engine,
endpoint, database or native object. It can include Properties, Refresh,
Connect, Query, Open Data, Create, Alter or Drop only when the exact provider
admits them. The same commands appear in the node's context menu.

Tools
=====

The *Tools* menu opens project-owned facilities such as Data Studio, query
workspaces, ERD/whiteboard/dataflow diagrams, model conversion, semantic-model
design, dashboards, reports, data pump, scheduler, comparison and diagnostics.
Tools that require a connection ask for or inherit a typed provider target.

Owner direction, 2026-11-08: the *Tools* menu lists only commands that can
start from it, such as *New Schema Comparison*, *New Diagram…* and
*Diagrams*. Actions on an open comparison, pipeline, CDC definition,
replication topology, migration project, AI session or other work in
progress (for example *Apply Change Plan*, *Execute Failover Plan* or
*Run Pipeline*) are run from inside that tool, where the work they act on
is known; the same applies to the DDN view and designer actions.

Owner direction, 2026-11-08 (later): *Open in DDN Viewer* and *Open in DDN
Designer* are no longer offered on the menus. The DDN viewer and designer
they open are a proof of concept; the task-specific designers (diagrams,
and the planned cube, data model, BI and screen designers) are used
instead. Diagrams still open from the Diagrams tool and the Project
Explorer, which hand the asset to the viewer or designer themselves.

Added 2026-11-10: the task-specific Data Model (ERD) designer registers only
its launcher commands (*New Data Model (ERD)…* and *Data Models (ERD)*) on the
*Tools* menu. Open-model actions (*Save ERD Checkpoint*, *Convert ERD Engine*,
*Preview ERD Alter Plan*, *Accept ERD Version* and *Open in ERD Designer*) stay
on the open designer toolbar. The cross-engine comparison module uses the label
*Schema Comparison* on its activity and *Tools* entry while legacy PostgreSQL
*Schema Diff* remains for inherited registrations until PostgreSQL M7. The
task-specific Cube Designer likewise registers only *New Cube…* and *Cubes* on
the *Tools* menu while keeping *Save Cube Checkpoint*, *Preview Materialized
Aggregate Plan*, *Accept & Apply Cube* and *Open in Cube Designer* on the open
designer toolbar. The task-specific BI Questions & Dashboards Designer
similarly registers only *New BI Question or Dashboard…* and *BI Questions &
Dashboards* on the *Tools* menu while keeping *Open in BI Designer*, *Save BI
Checkpoint*, *Open SQL Bridge*, *Review Outward Effects* and *Accept BI
Version* on the open designer toolbar. The task-specific Screen Mesh Designer
registers only *New Screen Mesh…* and *Screen Meshes* on the *Tools* menu while
keeping *Open in Screen Mesh Designer*, *Save Screen Mesh Checkpoint*, *Redact
Screenshot Regions* and *Accept Screen Mesh Version* on the open designer
toolbar.

Window
======

The *Window* menu controls docking, grouping, tear-off windows, monitor
placement, workspace restoration and layout reset. A torn-off workspace retains
its command, security and provider context and can be docked again.

Help
====

The *Help* menu opens local documentation, command search, keyboard help,
diagnostics, provider/driver version information, project status and *About
ScratchRobin CDE Admin*. The About view states that CDEadmin is an independent
hard fork based on pgAdmin 4 9.17 and retains the upstream copyright and
PostgreSQL Licence attribution.

Command contract
================

Every menu entry is a command-registry projection with a stable command ID,
icon, label, security permission, visibility predicate, enablement predicate,
shortcut/macro binding and audit behavior. Menus can be redesigned without
changing command authority.
