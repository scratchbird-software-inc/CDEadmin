Adopted standalone DDN integration
*********************************

Source and release boundary
===========================

Owner direction, 2026-10-28: generation, dashboards and DDN-to-native-metadata
exchange use the standalone open DDN foundation, published as the public repository
``scratchbird-software-inc/Diagram-Design-Notation``. The adopted language is
``ddn-next-1`` and the public utility API is 1.0. Its package version 0.0.0 is
not the old DDN 0.8 release. The old grammar, runtime and editor are incompatible.
The owner authorized publication of this standalone DDN integration on
2026-10-28. Commercial Weaver is a separate product and is not an integration
dependency. Source acquisition still requires an explicitly configured, reviewed
location for the matching new foundation.

``tools/refresh_ddn.py`` captures only standalone sources, maintained DDN tests,
public contract inputs and required build tools. It builds an isolated capture,
checks the compiler's resolved dependency boundary, and ships the viewer,
designer, verifier, declarations, worker/profile modules, fonts, licences and
notices together. ``resource-manifest.json`` records the source revision and
working state, compiler hashes, reviewed consumer patches and every artifact
hash. The modular loader checks its release hash against the host bundle.
A failed refresh fails the build and preserves the last admitted distribution.

Run the refresh before every build and qualification run. It uses the source's
pinned local tools when available, or provisions exact native Node/TypeScript
versions in consumer-owned work. Downloads use checked SHA-512 archives;
explicit ``SCRATCHROBIN_DDN_NODE`` and ``SCRATCHROBIN_DDN_TYPESCRIPT`` paths are
also supported and their versions are checked. No build writes into the active
sister checkout. Windows/macOS qualification remains with the platform teams;
portable intake code is not a substitute for their native receipts.

Consumer contracts
==================

A ScratchRobin source workspace has exactly ``format``, ``entry``, ``view`` and
``files``. Its format is ``ddn-source-workspace@1``; ``files`` maps relative DDN
paths to UTF-8 source text. It is distinct from DDN's native ``ModelSnapshot``
and ``SourceSet`` APIs. Generated source begins with ``version ddn-next-1``.
Quoted strings double embedded quotation marks; backslashes are literal.
Parsing, semantic verification and source patches use DDN's public APIs.

Generated multi-file catalogs and data exports explicitly link their files with
``include``. Every generated view remains reachable after selecting another
page and reopening the saved workspace. Supplied but unreferenced source is
still checked before native interpretation. Includes resolve only the supplied
file set, never arbitrary host files or remote URLs.

Catalog records use DDN record definitions with namespaced
``metadata.x_record`` facts. Exact native JSON, resource identities and paths
remain the native adapter contract. ``name_json`` retains the original name
independently of diagram labels. Exceptional control-containing strings retain
checked exact-text mappings; display escaping and shortened labels do not
change native names. Data records retain exact typed JSON and, where supplied,
the native Arrow payload. Duplicate result labels remain positional.

Native relational tables, fields and references use real DDN definitions.
Companion record definitions retain the native facts and UIDs that restricted
field/reference roles cannot carry themselves. Type, nullability and comment
edits enter the existing native review path. New PostgreSQL fields receive
stable parent-scoped draft identities and native creation validation. Graphical
MySQL/MariaDB additions
receive stable design identities and still require explicit new-column
admission and native type validation. Foreign keys require explicit native
intent. Missing or hidden objects never imply deletion. Three-way refresh
preserves authored source or reports conflicts; it does not discard edits.

Viewer, editor and monitoring
=============================

The shared viewer uses the public runtime, navigation and capture APIs. The
standalone designer owns its palette, inspector, layout and command history.
ScratchRobin owns asset permissions and versioned persistence. Source capture
awaits ``Designer.save()`` to flush pending forms and obtain coherent artifacts
before native handoff or host persistence. Newer edits during a save remain
dirty; asset-version conflicts retain the source. Unchanged BOM/CRLF source is
retained. Local model editing/verification does not grant lifecycle acceptance
or database execution authority. Native design storage retains its baseline
as a checked storage attachment; it is removed before opening the source
workspace in DDN.

Dashboards declare one trusted host source and a keyed observations dataset.
Publication validates engine/scope binding identities and removes sampled
telemetry. Live values enter through ``Runtime.ingest`` as provider data;
authored labels, layout and source are retained. Missing, stale or unauthorized
observations are not represented as a current successful value. Viewing does
not start collectors, create query sessions or enable editing.

The reviewed isolated consumer patch is documented in
``tools/dependency_patches/ddn-next-native-geometry.md``. It preserves native
Cartesian, line and collection inspection, geographic boundaries and polygon
holes, repairs SVG namespace serialization, and normalizes build-host paths.
Contracts are regenerated from the patched canonical inputs and provenance
records the distinction from unpatched upstream. It adds no commercial code,
remote geography, routing or geocoding.

Legacy source and evidence
==========================

Old ``ddn-workspace@1``, live snapshots and transient appearance/layout state are
not relabeled. Imports report that an explicit conversion is required and
retain the original source. No legacy parser is bundled as a compatibility
mode. The local review application had no saved DDN project assets or revisions
when inventoried for this migration. External legacy files need a separately
reviewed, loss-reported conversion before native use.

Headless native checks prove source/metadata admission and exact round trips.
``tools/ddn_render.mjs`` uses the public viewer/capture API with a DOM test host
and fallback text measurements. ``tools/tests/check_ddn_browser.cjs`` separately
qualifies actual Chromium loading, workers, fonts, SVG XML, source saves and
undo/redo; supplied fixtures can assert that all generated views are reachable.
Keep logs and native/browser receipts outside the repository. ScratchBird
persistent-history qualification remains owner-deferred.
