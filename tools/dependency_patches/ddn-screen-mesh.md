# DDN consumer patch: `wireframe.ui@1` screen mesh expansion (`ddn_screen_mesh.py`)

## Scope and ownership

Under the 2026-11-07, 2026-11-08, 2026-11-09, and 2026-11-10 owner directions,
ScratchRobin's Screen Mesh designer builds low-fidelity screen wireframes and
annotated screenshots linked to underlying catalog tables, columns, BI
questions/dashboards, and cubes, while keeping working form builders and
executable client scripts strictly out of scope.

The baseline `wireframe.ui@1` profile in the public `Diagram-Design-Notation`
repository admits only a seven-control stencil (`ui.frame`, `ui.button`,
`ui.checkbox`, `ui.image`, `ui.input`, `ui.label`, `ui.list`) with `assoc`
links. `ddn_screen_mesh.py` expands ScratchRobin's isolated DDN capture in
place (`consumer_patches.screen_mesh` in `resource-manifest.json`):

1. **Expanded `wireframe.ui@1` UI roles (`F1`)**: registers `ui.grid` (with
   named column descriptors), `ui.dropdown`, `ui.radio`, `ui.tabs`, and
   first-class rectangular image hotspot regions (`ui.region`) on core `EL16`,
   alongside crisp vector glyphs in `presentation/src/graph-glyphs.ts`.
2. **Data and resource bindings**: admits context roles (`table`, `field`,
   `record`, `saved_view`, `dashboard`, `binding`) and binding relations
   (`binds`, `bindfield`) inside `wireframe.ui@1` without triggering false
   `DDN-UI-FRAME` warnings on non-`ui.*` context nodes.
3. **Bounded screen-to-screen navigation (`F2`)**: registers the directed
   `navigation` relation (`RL25`) from any `ui.*` control or `ui.region` to a
   target `ui.frame` screen with bounded non-executable `x_ui` metadata
   (`trigger` in `click | hover | delay`, `action` in
   `navigate | back | overlay | url`), enabling both per-screen wireframe views
   and derived `screen_flow` views in `wireframe.ui@1`.
4. **Isolated distribution budget**: raises the standalone `native/ddn-viewer`
   HTML gzip gate in the isolated capture from 250 KiB to 264 KiB to
   accommodate the cumulative role/schema codex entries from ScratchRobin's
   reviewed consumer dialect patches.

Nothing is pushed back to the public `Diagram-Design-Notation` repository.
