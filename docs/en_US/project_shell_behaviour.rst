.. _project_shell_behaviour:

***************************************************************
ScratchRobin Project Framework and Application Shell Behaviour
***************************************************************

Owner direction, 2026-11-12. Status: adopted behavioural specification.
Presentation themes and visual styling variations are layered on top of this
behavioural contract without altering the rules below.

Overview
========

ScratchRobin (the overall **project** frame) provides a single unified
multi-application workbench composed of:

1. **Unified ``t_actions`` Registry** — the single central control table for
   every menu item, internal tabbed-icon-bar control, side-menu launcher,
   toolbar button, and shortcut.
2. **Area 1 — Top Menu** — full-width project bar ordered by recursive
   unsigned-integer positional indices, hosting the System Icon (index ``0``),
   minimal project menus (``Applications`` ``60``, ``Window`` ``70``, ``Help``
   ``80``), dynamically merged/unmerged focused-application menus, and
   right-aligned Language and Tone controls.
3. **Area 2 — Side Menu** — vertical left-justified launcher strip below the
   Top Menu with a top Left Side Drawer toggle, ``data-navigator`` first,
   authorized user application launchers beneath it, and a bottom-aligned
   Settings Gear popup.
4. **Area 3 — Application Area** — workspace region below the Top Menu and
   right of the Side Menu supporting single-application full-bleed mode (no tab
   bar), multi-application tabbed mode, multi-instance execution, tear-off
   native floating windows for multi-monitor work, drop-back re-docking, and
   the special **User Dashboard** placeholder/tab lifecycle.


1. Internal Tabbed-Icon-Bar (``NotebookBar``)
=============================================

* Standard applications may expose an optional internal **Tabbed-Icon-Bar**
  (Microsoft Office / Collabora ribbon pattern), implemented by the standalone
  in-house ``web/pgadmin/static/js/scratch_notebookbar`` (``NotebookBar``)
  package.
* Visibility of the Tabbed-Icon-Bar is optional per application and controlled
  through **Settings** (and toggleable via ``Window > Toolbars``).
* The **User Dashboard** never displays a Tabbed-Icon-Bar.
* The Tabbed-Icon-Bar lives on the **Main Form** and reflects whichever
  application instance (docked or floating) currently has focus.
* **Standard Close Control**: Every active application Tabbed-Icon-Bar carries
  a standard small ``[x]`` close button at its trailing end (paired with a
  ``Close`` option on the Top Menu), present regardless of whether Area 3's tab
  strip is currently visible or hidden.
* Internal application bars disable ``Alt`` access-key interception
  (``accessKeyTrigger={null}``) so they never conflict with Area 1 Top Menu
  access keys.


2. Unified ``t_actions`` Central Action Registry
================================================

All callable actions across the project framework and every application are
registered in a single central ``t_actions`` registry. Menus, Tabbed-Icon-Bar
controls, Side Menu launchers, context menus, and buttons read their state from
``t_actions`` rather than maintaining separate enablement or label copies.

Each ``t_action`` entry contains five canonical attributes:

=================================== =======================================================================================
Attribute                           Behavioural Specification
=================================== =======================================================================================
**(a) Icon** (``icon``)             Semantic icon key resolved through ``cdeadmin_ui/icons/registry.js``.
**(b) Identifier** (``id``)         Stable namespaced identifier used in code and for i18n lookup of both the control's
                                    **caption/icon text** (``<id>.text``) and **hint/tooltip text** (``<id>.hint``).
**(c) Status** (``status``)         One of ``enabled``, ``disabled``, or ``invisible``. Bound controls update reactively:
                                    ``disabled`` greys out the control; ``invisible`` hides the control and collapses any
                                    group whose controls are all ``invisible``.
**(d) Application**                 Identifier of the owning application (e.g. ``project``, ``data-navigator``,
(``application``)                   ``sql-editor``, ``erd-designer``, ``cube-designer``, ``bi-designer``,
                                    ``screen-mesh-designer``, ``schema-compare``, ``settings``).
**(e) Code Link** (``target``)      Executable binding pointing to **client-side** handler code or a **server-side**
                                    endpoint/operation so callers invoke ``t_actions.execute(id, args)`` uniformly.
=================================== =======================================================================================


3. Startup, Authorization, Preferences vs. Settings, and Lock Screen
====================================================================

Startup and Authorization Sequence
----------------------------------

1. **Authentication**: On startup, the Login Screen is presented first.
2. **Authorization** *(configured in Settings)*: Once authenticated, an
   authorization step resolves:

   * Which **applications** are available to the signed-in user (populating
     Area 2 Side Menu and ``Applications > Application List``; unauthorized
     applications receive ``invisible`` status in ``t_actions``).
   * Which **parts and actions** within each permitted application are enabled,
     disabled, or invisible for the signed-in user.

3. **Initial Main Project Form**:

   * Opens with the **User Dashboard** displayed in Area 3 as a full-area
     placeholder (customizable with favoured reports, quick buttons, tasks, and
     branding).
   * Unlike legacy behaviour, **no SQL editor is preloaded on startup**.

User Preferences vs. Application and Global Settings
----------------------------------------------------

* **``Applications > Preferences`` (Personal User Preferences)**:
  Per-user personalization settings including colour palettes, fonts, UI scale
  and density, interface personalization, and user-owned API keys.
* **Area 2 Gear Icon — ``Application Settings`` & ``Global Settings``**:
  Application-wide and group/system configuration including authorization
  rules, shared templates, default SQL reference scripts, default drawer/bar
  options, and resetting persisted drawer dimensions to their defaults.
* **``Applications > Data Sources``**:
  Registration and management of database server and endpoint connections.

System Icon Session Dialog and Lock Screen
------------------------------------------

* Clicking the **System Icon** (Top Menu position ``0``) opens the **Session /
  Logout Dialog** with three choices:

  1. **Lock Screen**
  2. **Logout**
  3. **Cancel**

* **Lock Screen Behaviour**:

  * Designed so a user stepping away from their desk immediately hides all
    workspace information:

    * **Browser mode**: Hides the entire application (and blanks any open
      floating pop-out windows) so **only a single centered Unlock Dialog** is
      visible in the browser viewport.
    * **Desktop / non-browser mode**: Minimizes/hides application windows down
      to **a single floating Unlock Dialog**.

  * All open docked and floating application instances and unsaved work remain
    intact in memory and are restored once the user re-authenticates in the
    Unlock Dialog (with a Logout option also available from the lock dialog).


4. Project Framework Layout Areas
=================================

Area 1 — Top Menu (Base UI ``NavigationMenu`` & Internationalization)
---------------------------------------------------------------------

* Spans the top of the Main Form and separates **appearance** from
  **behaviour**:

  * **Appearance**: Rendered using **Base UI's ``NavigationMenu``**
    (``@base-ui/react/navigation-menu`` — ``NavigationMenu.Root``, ``List``,
    ``Item``, ``Trigger``, ``Icon``, ``Content``, ``Link``, ``Portal``,
    ``Positioner``, ``Popup``, ``Arrow``, and ``Viewport``) in
    ``cdeadmin_ui/shell/ProjectNavigationMenuBar.jsx`` and
    ``ProjectNavigationMenuStyles.js``:

    * High-contrast light and dark bar surfaces (``data-tone="light" | "dark"``)
      where the ScratchRobin System Icon, top-level pill triggers, rotating
      chevron icons, Language selector, and Light/Dark switcher remain clearly
      legible in every theme.
    * Smooth CSS-variable-driven popup sizing and positioning
      (``--positioner-width``, ``--positioner-height``, ``--popup-width``,
      ``--popup-height``, ``--transform-origin``) with a Base UI pointer arrow
      (``NavigationMenu.Arrow``) and rich item cards showing leading icons,
      localized titles, localized secondary descriptions/hints, checkmarks, and
      shortcuts.

  * **Internationalization (i18n)**: Every Main Menu trigger, item label, item
    description/hint, ``aria-label``, Language menu heading, and Light/Dark
    label resolves through structured i18n keys in
    ``cdeadmin_ui/shell/shellMenuI18n.js``, synchronized into ``t_actions``
    locale bundles and falling back to Flask-Babel ``sources/gettext`` so
    switching languages updates the entire Main Menu live without reloading.

* **Unsigned-Integer Positional Index Model**:

  * Every top-level entry and every nested submenu item carries an **unsigned
    integer positional ``index``** (``>= 0``) and renders in ascending order.
  * Unoccupied indices collapse with zero visual gap (when ``1..59`` are empty,
    ``Applications`` at ``60`` sits immediately beside the System Icon at
    ``0``).
  * **Dynamic Application Menu Insertion & Merging**: When an application gains
    focus, it inserts its menu entries by ``index``. If an application targets
    an existing top-level index (such as ``60``, ``70``, or ``80``), its child
    items **merge into** that menu ordered by their own child ``index`` values
    and cleanly unmerge when focus leaves.

* **Baseline Project Top Menu Indices**:

  * ``0`` — **System Icon** (ScratchRobin icon -> Lock Screen / Logout /
    Cancel dialog)
  * ``1..59`` — Open indices before ``Applications``
  * ``60`` — **Applications**:

    1. ``Data Sources``
    2. ``Preferences``
    3. *Separator*
    4. *Authorized Application List*

  * ``61..69`` — Open indices between ``Applications`` and ``Window``
  * ``70`` — **Window**:

    1. *Toolbar List*
    2. *Separator*
    3. *Open Application List* (plus ``User Dashboard`` and ``Close`` active
       application)

  * ``71..79`` — Open indices between ``Window`` and ``Help``
  * ``80`` — **Help**:

    1. ``SQL Reference``
    2. ``Database Engine Reference``
    3. ``Glossary of Terms``
    4. ``Help``
    5. ``About``

  * ``81+`` — Open indices after ``Help``

* **Right-Aligned Framework Controls**:

  1. **Language Icon** — switches active UI language and refreshes ``t_actions``
     localized labels and hints.
  2. **Tone Switcher** — toggles UI tone (light / dark).

Area 2 — Side Menu (Clean-Room Vertical Rightward-Expanding Dock)
-----------------------------------------------------------------

* Positioned below Area 1 (Top Menu) and left-justified on the Main Form.
* **Dynamic Vertical Dock Appearance** (``ProjectVerticalDock.jsx`` /
  ``ProjectVerticalDockStyles.js``):

  * Clean-room PostgreSQL-licensed proximity-magnifying vertical dock inspired
    by ``reactbits.dev/components/dock``, transposed to a vertical left rail
    that **expands rightward**:

    * Keeps a fixed rail layout footprint (``52px``) so hovering icons never
      shifts or resizes the Left Side Drawer or Area 3.
    * Tracks pointer ``clientY`` with a cosine-bell proximity radius and GPU
      compositor spring transitions so **every** item in Area 2 — including the
      isolated top Left Drawer Toggle, the middle application launcher stack,
      and the bottom-aligned Settings Gear — smoothly grows rightward on hover
      (with neighboring icons swelling proportionally) and shrinks immediately
      back to its default ``36px`` size upon selection/click or pointer leave.
    * Displays floating localized tooltip pills to the right of the hovered
      tile.

* **Stateless Launcher Role**: Area 2 is strictly a **stateless application
  launcher** — it opens new application instances and **does not track**
  whether an application is still open (no active tints, running pips, or
  instance count badges). Selecting among already-open instances is performed
  via Area 3 tabs, floating windows, or ``Window > Open Application List``.
* **Top-to-Bottom Elements**:

  1. **Top Icon Button — Left Side Drawer Toggle**:
     Greyed out (``disabled``) unless the currently focused application
     supports a Left Side Drawer; toggles that instance's Left Side Drawer when
     enabled.
  2. **First Application Button — ``data-navigator``**:
     The standard application. Its Left Side Drawer presents the multi-engine
     database object tree (engines -> servers/databases -> schemas/tables/views
     and sibling collections), while its Main Work Area inspects and operates
     on selected objects and launches editors/designers.
  3. **Authorized Application Buttons**:
     Listed beneath ``data-navigator`` according to the current user's
     authorization profile.
  4. **Bottom-Aligned Gear Icon (``settings``)**:
     Opens a compact popup menu offering:

     * **Application Settings** *(uses the active application's registered
       settings target; disabled when no application settings target is
       active)*
     * **Global Settings** *(opens project-wide settings)*

Area 3 — Rounded-Island Layout (``3a``–``3e``), ``3b1``–``3b4``, Spacing & Zoom
-------------------------------------------------------------------------------

* **Shared Rounded-Corner Islands on Backdrop Colour ``a``**:

  * Everything below Area 1 (Top Menu) sits on recessed **Background Colour
    ``a``** (``--sr-backdrop-a``).
  * **Area 2** (Vertical Dock), every User Dashboard card/tile, and each
    distinct sub-surface of **Area 3** (``3a``, ``3b``, ``3c``, ``3d``, ``3e``)
    is enclosed by an identical ``1px`` border with matching rounded corners
    (``--sr-island-radius: 12px``), separated by user-configurable spacing
    (``panel_gap``, default ``6px``).

* **Area 3 Spatial Sub-Parts** (``ProjectShell.jsx`` /
  ``ProjectShellStyles.js``):

  * **``3b`` — Tabbed-Notebook-Bar Island**: Spans the **full width of Area 3**
    at the top (above ``3a``, ``3e``, and ``3c``) when the focused application
    displays its command bar:

    * **``3b1``**: Quick-access strip on the far left (``New``, ``Save``,
      ``Undo``, ``Redo`` icon buttons) on **Background Colour ``b``**
      (``--sr-strip-b``).
    * **``3b2``**: Tab strip track expanding across to ``3b4`` on **Background
      Colour ``b``**, with inactive tabs slightly darker than ``3b3``.
    * **``3b3``**: Active folder tab with a lighter surface matching the ``3b``
      body and its bottom border opened seamlessly into ``3b``.
    * **``3b4``**: Right-aligned ``[x]`` close button for the active
      application.
    * **``3b`` Body**: Command icon surface below ``3b1``–``3b4``.

  * **``3a`` — Optional Left Side Drawer Island**: Sits below ``3b`` on the
    left and extends **all the way to the bottom** of the window (aligned with
    the bottom of Area 2 and ``3d``), with a **single short vertical line
    resize handle inset just inside its right (workspace-facing) edge**.
  * **``3e`` — Main Application Work Area Island**: Sits to the right of ``3a``
    and above ``3d``.
  * **``3c`` — Optional Right Side Drawer Island**: Sits to the right of ``3e``
    and above ``3d``, with a **single short vertical line resize handle inset
    just inside its left (workspace-facing) edge**.
  * **``3d`` — Optional Status Bar Island**: Spans along the bottom
    **underneath both ``3e`` and ``3c``** (from the left edge of ``3e`` to the
    right edge of ``3c``).

* **Configurable Spacing & Per-Area Icon/Font Zoom**:

  * Both **Global Settings** and per-application **Application Settings** expose
    user-configurable ``panel_gap`` (``0–24px``) and per-area zoom percentages
    (``70%–160%``, scaling both icon size and font size across ``area_1``,
    ``area_2``, ``area_3a``, ``area_3b``, ``area_3c``, ``area_3d``, and
    ``area_3e``).

* **Single vs. Multiple Docked Applications**:

  * **1 docked item**: Fills **100% of Area 3** with **no tab strip** (closed
    via the standard ``[x]`` on the Tabbed-Icon-Bar or ``Close`` in the menu).
  * **2+ docked items**: Area 3 shrinks vertically to show a **tab strip** with
    one tab per open docked item; the **active tab** carries a small ``[x]``
    close button.

* **Multi-Instance Execution**:
  Applications may be opened multiple times concurrently (for example, several
  SQL editors across Firebird, MySQL, or the same database), each maintaining
  isolated state.
* **Drag-Off Floating Windows (Multi-Monitor Support) & Re-Docking**:

  * Any application tab may be **dragged off** Area 3 to open a **native
    browser pop-out window** (in browser mode) or **floating desktop sub-form**
    (in desktop mode) for multi-monitor use.
  * To maximize screen real estate without wasteful repetition, a floating
    window contains **only that instance's Main Work Area and its bottom Status
    Area** — no top tab bar, no repeated Top Menu, no repeated Tabbed-Icon-Bar,
    and no repeated Left/Right Drawers. It is freely resizable and managed by
    the floating window's native ``Minimize`` / ``Maximize`` / ``Close``
    controls.
  * **Unified Focus**: Focusing a floating window triggers the exact same
    activation handshake on the Main Form as focusing a docked tab — updating
    the Main Form's Top Menu, Side Menu Left-Drawer toggle, Settings Gear
    context, Tabbed-Icon-Bar, and Left/Right Drawers for that focused floating
    instance.
  * **Drop-Back Re-Docking**: A floating sub-form may be dragged/dropped back
    onto Area 3 to close the pop-out window and become a docked tab again.

* **User Dashboard Lifecycle**:

  * Displays as a tabless placeholder when ``0`` docked applications are open.
  * Automatically disappears when an application is opened in Area 3, unless
    explicitly opened via ``Window > User Dashboard``, in which case it behaves
    as a closable tab.
  * If ``User Dashboard`` is open as a tab and all other docked application
    tabs are closed or detached, its tab automatically disappears and it
    reverts to normal placeholder mode.


5. Standard Application Anatomy, Drawers, and Teardown-Before-Activate
======================================================================

Standard Application Regions
----------------------------

1. **Optional Tabbed-Icon-Bar** *(on Main Form; controlled via Settings;
   includes standard trailing ``[x]`` close button)*.
2. **Left Side Drawer** *(on Main Form; optional; user-resizable; width
   persisted between uses and resettable in Application Settings; toggled from
   Area 2's top button)*.
3. **Main Work Area** *(docked in Area 3 or detached into a floating window)*.
4. **Right Side Drawer** *(on Main Form; user-resizable; width persisted
   between uses and resettable in Application Settings; toggled — including
   which inspector/view it displays — via the Tabbed-Icon-Bar or Top Menu)*.
5. **Optional Status Area** *(travels with the Main Work Area — bottom of Area
   3 when docked, bottom of the floating window when detached)*.

Per-Instance Drawer and Status Isolation
----------------------------------------

Every open application instance maintains its own Left Drawer open/closed
state, Right Drawer open/closed state and selected view, Status Area readouts,
and live drawer contents reflecting the work in *that* specific instance.

Deterministic Teardown-Before-Activate Sequence
-----------------------------------------------

Whenever focus switches away from an application instance or an application
closes (including when the last open application stops):

1. **Menu & ``t_actions`` Cleanup**: Remove/unmerge all Top Menu items
   contributed by the outgoing instance and reset its scoped ``t_actions`` to
   ``invisible``.
2. **Left Drawer Reset**: Set the Left Side Drawer to **closed** and set Area
   2's Left Side Drawer toggle to **disabled** (greyed out).
3. **Settings Context Clear**: Clear the active application-specific settings
   target on Area 2's Gear icon (``null``).
4. **Incoming Activation** *(only if another instance is receiving focus)*:
   Populate/merge the incoming instance's Top Menu items by positional
   ``index``, restore its per-instance Left and Right Drawer states and
   contents, set Area 2's Left Side Drawer toggle status, and register its
   application-specific settings target on the Gear icon.
