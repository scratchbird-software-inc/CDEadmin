# Developer Ergonomics Audit — 2026-10-27

Audit of developer-facing tooling, build entry points and onboarding docs in
the CDEadmin repository. Findings are listed first, then the fixes applied in
this change, then deferred work.

## Findings

### (a) tools/ layout and wiring

- `tools/` holds 663 flat top-level Python scripts with no index.
- The `_gate` / `_qualification` / `_verify` suffixes encode the origin team,
  not behavior: Firebird-derived scripts use `_gate` (194 files), MySQL-derived
  scripts use `_qualification` (158), and small-engine scripts use `_verify`.
- Only ~23 of the 663 scripts are wired into the Makefile or CI.
- Two consistent CLI dialects exist: static checks use
  `--source/--policy/--output`; live checks use `--host/--port/--evidence`.
- `tools/reference_engine_demos/` is a 23,321-file tree inside `tools/`.

### (b) Makefile

- `make check` (line 45) chains ~30 targets, plus a hidden line-46 recipe
  running the full Jest suite and the pgAdmin regression suite. There is no
  per-engine granularity even though the underlying tools accept `--engine`.
- Bugs:
  - Line 84 (`check-js-coverage` recipe) uses space indentation, which breaks
    the target.
  - `clean-node` (line 431) removes `web/node-modules/` (hyphen) instead of
    `web/node_modules/`.
  - The `docker` target (line 447) runs `git checkout HEAD`, detaching HEAD as
    a build side effect.
  - The `.PHONY` declaration (lines 470–505) is incomplete.
- Nine identical `*-coverage` boilerplate targets are copy-pasted.
- There is no `make help`; ~40 `cdeadmin-*` targets are undocumented.

### (c) Onboarding documentation contradictions

| Topic | Statement A | Statement B | Truth |
| --- | --- | --- | --- |
| Node version | "Node.js 20 or later" (README.md:227) | dev guide says 22 LTS (22.22.x) | manage.py:60-62 enforces >= 22 |
| Node heap | "6 GiB standard" (README.md:29) | — | manage.py:123 sets 3 GiB |
| Python env | `venv` (README.md:241) | `.venv` (manage.py:114) | dev.sh uses `.venv` |
| Requirements | README installs regression reqs | dev.sh installs demo reqs | neither notes the gap |
| DB setup | `python3 web/setup.py` (README.md:272) | — | manage.py:134 runs `setup.py setup-db` |
| Launcher | code_overview.rst:24 calls pgAdmin4.py "the main file" | README: CDEadmin.py canonical | CDEadmin.py |
| WSL vs native | tools/development/README.md:24-26 vs NATIVE.md:3-4 | no decision rule | — |
| Go version | doctor requires Go 1.25.5+ | documented only in tools/development/README.md:72 | — |

### (d) DDN freshness protocol gap

AGENTS.md:46-60 mandates a 5-step DDN refresh before every build and every
commit-validating test, and admits the gate is not automated.
`tools/refresh_ddn.py` exists and IS wired into
`tools/development/native.py` (its `ddn(evidence)` runs before ~15 stages),
but `tools/development/manage.py` — the primary Linux `dev.sh` path — has no
`ddn` action, so the mandated protocol is silently skipped on Linux.

### (e) dev.sh doctor gaps

The `doctor` action does not check `vm.max_map_count`, the embedded SQLite
3.53.0 build, disk space, CMake, or DDN freshness.

## Fixes applied (2026-10-27)

1. **DDN refresh wired into the Linux dev path.** `manage.py` gained a `ddn`
   action that runs `tools/refresh_ddn.py` (equivalent to native.py's
   `ddn(evidence)`), and the `frontend` action now runs the DDN refresh first,
   mirroring native.py's ddn-before-build behavior. `dev.sh ddn` works.
   AGENTS.md, tools/development/README.md and
   wiki/Development-and-Qualification.md updated to match: the gate is now
   automated on both dev paths; direct webpack/pytest/Jest invocations still
   require running `bash tools/development/dev.sh ddn` (or
   `tools/refresh_ddn.py`) first.
2. **Onboarding docs reconciled.** README.md now states Node 22 LTS (tested
   22.22.x) via Corepack, the 3 GiB heap used by dev.sh frontend builds, and
   `setup.py setup-db`; the manual venv/build/startup sections defer to
   tools/development/README.md as the canonical Linux path. A host decision
   rule was added to tools/development/README.md and a reciprocal pointer to
   NATIVE.md. docs/en_US/code_overview.rst is marked as inherited upstream
   reference material with the launcher corrected to CDEadmin.py.
3. **Makefile bugs fixed.** Tab indentation in `check-js-coverage`;
   `clean-node` removes `web/node_modules/`; the `docker` target no longer
   runs `git checkout HEAD`; `.PHONY` now declares every target in the file.
4. **Makefile ergonomics.** Added a self-documenting `make help`; added
   `check-gates` (the cdeadmin gates/tests without install/bundle/lint and
   without the heavy Jest + regression suites; `check` now chains it);
   parameterized `cdeadmin-semantic-live` with `ENGINE ?= duckdb` and kept
   `cdeadmin-semantic-live-duckdb` / `-sqlite` as thin aliases; collapsed the
   nine `*-coverage` targets onto one shared coverage recipe.

## Deferred items

- Extend `dev.sh doctor` with checks for `vm.max_map_count`, embedded SQLite
  3.53.0, disk space, CMake, and DDN freshness.
- Regroup `tools/` into `gates/`, `qualify/<engine>/`, `build/`, `ui/` and
  move `reference_engine_demos/` out of `tools/`; add a tools index.
