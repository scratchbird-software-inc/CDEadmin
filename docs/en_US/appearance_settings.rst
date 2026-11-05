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
   Menu text size and height, the width and icon size of the activity bar,
   and how selected and inactive activities are emphasised.

Areas and controls
   Toolbar, tab and status bar heights, control and click-target sizes,
   spacing, scrollbars, resize handles and corner radius.

Object explorer and grids
   Tree row height, indent, expander and line width; grid row, header and
   cell padding.

Density, motion and focus
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

Deployment defaults
===================

The settings are ``misc`` preferences named ``accessibility_*`` (colours
``accessibility_color_*``) plus ``theme``; presets are
``misc:accessibility:appearance_presets``. An administrator can set them for
accounts with ``setup.py set-prefs``. The same validation applies.
