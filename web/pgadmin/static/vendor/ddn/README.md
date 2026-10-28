# DDN distribution consumed by ScratchRobin

`current/` contains the standalone open DDN `ddn-next-1` (utility API 1.0) public
runtime, declarations, stylesheet and self-contained unified editing tool from the
owner-designated sister project (`tools/ddn_intake.py` `CONTRACT`, recorded as
`version` in `current/resource-manifest.json`). It is distributed under
**GPL-2.0-or-later**, with the original LICENSE and NOTICE.md. This is a new
distribution; the earlier 0.8.0 distribution, the previous MIT-labelled 0.5 viewer
and 0.1 Designer are retired, not relabelled.

Run `python3 tools/refresh_ddn.py` from the repository root before builds and
commit-validation tests. Direct webpack builds run this gate automatically.
Set `SCRATCHROBIN_DDN_SOURCE` and `SCRATCHROBIN_DDN_WORK` for other workstations;
`PYTHON` selects the interpreter used by webpack. The source must have its pinned
build dependencies installed. Intake fails instead of falling back to old code.

Intake captures current tracked and nonignored source files, verifies the capture
against the unchanged source inventory, and builds runtime and tool in an
isolated temporary snapshot. It never runs build tools in the sister checkout.
`resource-manifest.json` records source revision, dirty status, source hashes,
intake script hash, artifact hashes and license. `sdk-build.json` records the
upstream builder's distribution evidence. Matching source and artifact hashes
permit reuse of that exact previously built snapshot.

Product adapters use DDNLive's documented workspace/render/editor APIs and the
unified tool's setSource/getSource/onSourceChange/snapshot bridge. The read-only
surface renders SVG in an image document, without editing event handlers.
Versioned project-asset persistence and native database authorization remain
ScratchRobin responsibilities. DDN diagrams do not execute database changes.

Consumer checks include the Jest DDN suites and
`TMPDIR=<artifact-directory> node tools/tests/check_ddn_browser.cjs` (set
`DDN_BROWSER` when Chromium is not in the Playwright cache). These checks qualify
the adapter boundary, not native metadata round trips or database dashboards.
