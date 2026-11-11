# Dependency build adjustments

The adopted DDN source is the standalone open tree in ScratchWeaver. The
reviewed consumer changes and their scope are described in
[ddn-next-native-geometry.md](ddn-next-native-geometry.md). The intake applies
`ddn_next_native_geometry.py` only to its isolated source capture, regenerates
contracts from that capture, and records every changed input and artifact hash.
It preserves native Cartesian/line/collection inspection and polygon holes,
repairs SVG XML serialization, and makes the build driver use native host paths.
It changes neither the public ABI nor the grammar or defaults. The active
sister checkout and commercial Weaver source remain untouched.

The old 0.8 runtime, editor and intake patches are retired. A refresh failure
preserves the last admitted distribution and fails the build; it cannot select
an older dialect as a fallback. The owner authorized publication of the
standalone DDN integration on 2026-10-28; commercial Weaver remains excluded.

Updated 2026-11-03 (owner direction): DDN now comes only from the public
`Diagram-Design-Notation` repository; ScratchWeaver's copy is diverging on
purpose and is no longer a source. The geometry patch now edits the
public contract layout (`standard/codex`).

Updated 2026-11-07 (owner direction): DDN is a proof of concept. ScratchRobin
may rewrite or extend its own DDN capture without pushing changes back to the
DDN repository. The projects that use it are open source, so the changes stay
available there. The intake now also applies `ddn_registry_pack_cache.py`
([ddn-registry-pack-cache.md](ddn-registry-pack-cache.md)). It keeps one frozen
copy of each deep-frozen profile pack source and memoizes profile descriptors,
so every DDN runtime after the first reuses them. The manifest records it under
`consumer_patches.registry_pack_cache`.

Updated 2026-11-10 (owner decision): The intake also applies
`ddn_cube_dimensional.py` ([ddn-cube-dimensional.md](ddn-cube-dimensional.md))
to register the `cube.dimensional@1` dimensional cube profile in ScratchRobin's
isolated DDN capture alongside `matrix.relations@1` and `table.records@1`,
recorded under `consumer_patches.cube_dimensional`.

Native MariaDB 12.2.2 macOS builds apply one guarded source correction in
`native_servers.patch_mariadb_darwin_linker`: ColumnStore's GNU ld
`--as-needed` flag is conditional on a non-Apple toolchain. On Intel macOS its
unconditional use makes CMake header/function probes fail and contaminates
Mroonga's shared feature cache. Storage engines retain their upstream build
selection. `mariadb-source-patch.json` records the archive, before/after source
hashes and patch runner hash; a separate CMake build directory avoids old probe
cache values. The read-only reference source remains untouched.
