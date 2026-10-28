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

Native MariaDB 12.2.2 macOS builds apply one guarded source correction in
`native_servers.patch_mariadb_darwin_linker`: ColumnStore's GNU ld
`--as-needed` flag is conditional on a non-Apple toolchain. On Intel macOS its
unconditional use makes CMake header/function probes fail and contaminates
Mroonga's shared feature cache. Storage engines retain their upstream build
selection. `mariadb-source-patch.json` records the archive, before/after source
hashes and patch runner hash; a separate CMake build directory avoids old probe
cache values. The read-only reference source remains untouched.
