.. _appearance_settings:

********************************
Appearance and accessibility
********************************

*View > Appearance and Accessibility…* sets the fonts, colours and area sizes
of the interface and keeps them as named presets. It replaces the
*Appearance* page of the Interface Designer and the accessibility pages of
*File > Preferences* (2026-11-05).

Changes show immediately as a preview. *Apply* saves them to your account;
*Reset* or closing the dialog returns to what was saved. ``Ctrl+Shift+0``
still switches the emergency safe mode (high contrast, large sizes, reduced
motion), and safe mode overrides both a preview and saved settings.

Sections
========

Profile and presets
   The starting profile (for example *Low vision* or *Compact expert*) and
   your saved presets.

Text and fonts
   Interface and editor fonts, interface scale, line height and letter
   spacing. A font is a comma-separated list such as
   ``"Atkinson Hyperlegible", sans-serif``; the first installed font is used.

Colours
   The theme and eleven interface colours. Text, focus and border colours
   below their minimum contrast are repaired automatically.

Menu and activity bar
   The command bar (the menu bar or the tabbed bar, below), menu text size
   and height, the width and icon size of the activity bar, and how selected
   and inactive activities are emphasised.

Areas and controls
   Toolbar, tab and status bar heights, control and click-target sizes,
   spacing, scrollbars, resize handles and corner radius.

Explorer and grids
   Tree row height, indent, expander and line width; grid row, header and
   cell padding.

Density and motion
   Information density, animation, and the keyboard focus indicator.

A blank number or colour uses the profile's value, which the field shows.
Each number has a supported range; values outside it are brought into range.

Presets
=======

*Save current settings as…* stores every setting in the dialog under a name.
*Use preset* shows a preset as the preview; *Apply* makes it your appearance.
Using a preset changes only the settings it holds, so a preset imported from
elsewhere that sets only text size leaves your colours alone.

*Export presets…* writes all your presets to
``cdeadmin-appearance-presets.json`` for another account or a colleague;
*Import presets…* adds the presets in such a file, replacing any with the same
name. A profile exported by the former Interface Designer
(``cdeadmin.interface-profile.v1``) imports as one preset of its appearance.

An account keeps up to 40 presets. The server checks every value in a preset
by the same rule as the setting itself.

Tabbed command bar
==================

*Command bar: Tabbed bar* replaces the menu bar with a tabbed bar: one tab
per menu, its commands in groups, with the same commands, shortcuts and
availability as the menus. When the window is narrow, groups fold into a
*More* menu. Double-click a tab, or press ``Ctrl+F1`` in the bar, to shrink
it to its tabs; a tab click then opens its commands until you use one.

Press and release ``Alt`` to show a key on each tab; type it to open the tab
and show keys on its commands, and type a command's key to run it.
``Escape`` goes back a step. The arrow keys move between tabs and commands.

*View > Customize Tabbed Bar…* reorders, hides and renames tabs and groups,
adds your own tabs and groups of commands, and sets the quick-access
commands at the left of the bar. Customization is saved to your account and
can only arrange commands the menus offer.

Deployment defaults
===================

The settings are ``misc`` preferences named ``accessibility_*`` (colours
``accessibility_color_*``) plus ``theme``; presets are
``misc:accessibility:appearance_presets``; the command bar is
``misc:accessibility:accessibility_command_bar`` (``menu`` or ``notebook``)
and its customization ``browser:interface_customization:command_bar_customization``. An administrator can set them for
accounts with ``setup.py set-prefs``. The same validation applies.
