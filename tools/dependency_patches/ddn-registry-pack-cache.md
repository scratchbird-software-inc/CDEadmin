DDN registry pack cache consumer patch (2026-11-07)
==================================================

Owner direction, 2026-11-07: the DDN software is a proof of concept.
ScratchRobin may rewrite or extend its own DDN capture without pushing changes
back to the DDN repository. This is the first change made under that direction.
Like the native geometry patch, it is applied only to the isolated source
capture, never to the DDN checkout, and the intake manifest records it under
`consumer_patches.registry_pack_cache`.

Why
---

Every DDN runtime installed the same profile packs by deep-cloning and freezing
about 480 KB of profile data (`registry.install`). The runtime's verifier cloned
and froze the same data again (`createVerifier`). The pack factories rebuilt all
153 profile descriptors each time runtime options were made.

ScratchRobin creates a runtime for every DDN surface: catalogs, diagrams and
dashboards for every engine. Measured under load, that was about 1 s of setup
per runtime.

A jest test that renders each of the 26 Firebird activity categories spent 56%
of its CPU there and hit its 18 s timeout under the owner's reference load. Any
test or screen that opens several DDN surfaces pays the same cost, whatever the
engine.

What changes
------------

- `execution/src/index.ts` gains `frozenCopy(value)`:
  - It returns `freeze(clone(value))` as before.
  - When `value` is deep-frozen, it keeps that copy and returns it for later
    calls with the same source object.
  - A deep-frozen object cannot change, so the shared copy always equals a new
    one.
  - The first copy still runs DDN's plain-JSON validation; accessors, symbols,
    cycles and non-finite numbers are rejected as before.
  - Objects that are not deep-frozen, or that hold accessors or typed arrays,
    are copied anew every time.
- `execution/src/index.ts` `freeze(value)` skips objects recorded as
  deep-frozen:
  - Recorded objects are every copy `frozenCopy` makes (plain JSON, frozen
    throughout) and every source it proved deep-frozen.
  - Such an object and everything reachable from it is already frozen and
    cannot change, so `freeze` has nothing to do there. Its result is the same
    as before: the value and everything reachable through data properties is
    frozen.
  - Without this, the registry, its merged view and the verifier each froze a
    new wrapper around the shared copies and walked all of them again; that
    walk was most of the cost left after sharing the copies.
- `runtime/src/registry.ts`:
  - `install()` uses `frozenCopy` for the manifest, each profile and the
    schemas.
  - Rules, commands and projections keep their per-install shallow copies,
    because they carry trusted callbacks.
- `verifier/src/index.ts`:
  - `createVerifier()` uses `frozenCopy` for each pack manifest and each
    profile.
  - Rules are copied as before.
- `profiles/src/core.ts`:
  - `profileDescriptor(id)` is memoized per id.
  - A descriptor is built only from the frozen codex and the id, and is
    deep-frozen, so every pack shares one descriptor object per profile.
  - Unknown ids are not cached.

Grammar, API, defaults, verification results and diagnostics are unchanged. No
module-level DDN cache is keyed by profile or pack objects; the keys are
runtimes, verifiers, snapshots and DOM nodes. Sharing immutable copies across
runtimes therefore carries no state from one runtime to another.

Qualification
-------------

Measured 2026-11-08 on a Core Ultra 7 165U (14 logical CPUs). "Reference load"
means 14 busy processes plus a writer fsyncing 1 MiB blocks (about 65 per
second). "Before" is the previous vendored build (release `e7022d75`), "after"
is this one (release `89579323`), both built from DDN `a0a26c621`. Ranges are
over three alternating runs of each build.

1. **DDN's own suite** on isolated captures of `a0a26c621`:

   | Capture | Passed |
   |---|---|
   | Unpatched | 1151 of 1151 |
   | Geometry patch only | 1150 of 1151 |
   | Geometry and cache patches | 1150 of 1151 |

   The failure in both patched captures is DDN's AI-reference check. It is
   stale because the geometry patch changes profile data.
2. **Same results.** Each of DDN's 150 website examples gives an identical
   verification report with both builds (69 valid, 19 invalid, 62 incomplete).
   That holds with a new verifier per document and with one verifier reused
   for all of them.
3. **Sharing.**
   - Two calls to a runtime-options factory return the same 153 profile
     descriptors, and their frozen copies are shared. This holds for the
     modules and for the `complete/` entry points, which re-export the modules.
   - In Chromium, through the modular loader the workbench uses, the loaded
     native pack's profiles are shared (4 of 4). A second runtime opens the
     same document identically.
   - `tools/tests/check_ddn_browser.cjs` passes.
   - The commands pack's schemas are not shared. They are about 5 KB, built
     anew and not frozen on each call, so they are copied every time, as
     before.
4. **Set-up cost**, before → after:

   | Measure | Before | After |
   |---|---|---|
   | Runtime options (node) | 6.4–6.9 ms | 1.7–2.0 ms |
   | `createRuntime` (node) | 33–34 ms | 6–7 ms |
   | `createRuntime`, `complete/` entry points (node) | 206–228 ms | 4–7 ms |
   | `createVerifier` (node) | 17 ms | 2.2 ms |
   | `createVerifier`, `complete/` entry points (node) | 138 ms | 2.7 ms |
   | Runtime, Chromium | 21.5 ms | 3 ms |
   | Heap, 26 runtimes and verifiers alive | 67 MB | 5.3 MB |

   Neither build keeps memory once its runtimes are destroyed.
5. **First version.** A first version shared the copies, but `freeze()` still
   walked them.
   - It halved set-up, but under the reference load the FirebirdActivity jest
     test still hit its 18 s timeout in 3 of 3 runs.
   - The registry, its merged view and the verifier walked the shared copies
     again when freezing their wrappers.
   - The `freeze()` change removed that walk.
6. **jest, DDN specs.** The 25 spec files that load the vendored DDN (Firebird
   10, MySQL 4, MariaDB 2, PostgreSQL 3, DuckDB 1, SQLite 1, shared 4):
   - **Single process:**
     - no failures with either build;
     - summed file time 40.1 → 32.5 s;
     - CPU 54–67 → 44–53 s;
     - FirebirdActivity 3.6–4.6 → 1.5–1.9 s.
   - **Four workers under the reference load:**
     - FirebirdActivity "renders each native category" timed out in 3 of 3
       runs before, and passed in 3 of 3 runs after, at 11.8–16.1 s.
     - Summed test time is unchanged within the noise: 181–193 s before,
       186–203 s after.
   - **Not changed by this patch:**
     - PostgresqlDashboard "retains every server observation" takes 13–22 s
       under the reference load with both builds; it has its own 45 s timeout.
     - The MySQL and MariaDB dashboard-editor "seeds the paired designer"
       tests fail under that load with both builds.
7. **Full jest suite** (half the CPUs as workers; load average 17–18 from
   other work on the machine):
   - 5365 of 5373 passed.
   - The 2 failures are in `SQLiteCatalog.spec.jsx`, which mocks the DDN
     surface and does not load DDN. Rerun, it passes 14 of 14 with either
     build.
   - An earlier full run at ambient load 9–16 failed 5 tests, FirebirdActivity
     among them; all 5 pass.
8. **Full Python suite** (58 minutes; load average 18 falling to 10):
   - 20,097 passed.
   - 19 failures plus the mysql-native subtest, all on the recorded baseline
     of `81b92ed91`. No new failure.

Results by engine. Every DDN surface goes through the patched modules. The
Python column counts the tests in files named for the engine, which include
its DDN catalog, review and round-trip runners.

The engine-specific DDN screens belong to the six engines in the table. They
are selected by those engines' native profiles, so related providers do not
open them; this covers Dolt, TiDB and Vitess (MySQL family) and CockroachDB
and YugabyteDB (PostgreSQL family). Any provider can still reach DDN two ways:
- Its tabular results can be exported as a static DDN workspace. That export
  is written in Python, without the DDN runtime.
- Such a workspace opens in the shared DDN surfaces, which are covered by the
  Shared row.

| Engine | jest DDN spec files (tests), failed | Python tests, failed (all on baseline) |
|---|---|---|
| Firebird | 10 (40), 0 | 11153, 2 |
| MySQL | 4 (16), 0 | 2635, 3 |
| MariaDB | 2 (5), 0 | 262, 0 |
| PostgreSQL | 3 (28), 0 | 1232, 9 |
| SQLite | 1 (2), 0 | 892, 0 |
| DuckDB | 1 (2), 0 | 925, 0 |
| Shared (DDN surfaces, BI dashboards) | 4 (30), 0 | 481, 0 |

`tools/tests/test_ddn_registry_pack_cache.py` checks four things in the
shipped distribution:
- the manifest record;
- sharing in the modules and in each `complete/` entry point;
- the copy and `freeze()` rules;
- that the patch refuses a changed DDN source.

It fails on the previous build.
