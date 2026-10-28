DDN native geometry consumer patch (2026-10-28)
==============================================

The replacement DDN geographically bounded profiles omit the Cartesian,
LineString, MultiLineString and GeometryCollection inspection already shipped
by ScratchRobin. Full migration must preserve that native functionality.

`ddn_next_native_geometry.py` changes only the isolated open DDN capture. It
extends the existing geography method enum with `cartesian` in the adopted
codex/schema, records the extension in profile rules, and regenerates compiled
contracts with DDN's generator before building. No grammar, ABI, default,
commercial Weaver dependency or active sister-project file changes. The intake
manifest records patch, source-contract and generated-artifact hashes. This
consumer patch may be published with the authorized standalone integration and
is reviewable for upstream adoption. Unpatched upstream does not thereby gain
Cartesian inspection.

Geographic methods retain range checks, antimeridian polygon splitting and
bounded coordinate counts. Cartesian coordinates are finite native x/y, with
no wrapping, longitude/latitude assertion, routing or geocoding. Line outlines
and bounded collections retain source feature provenance. Polygon holes use
the existing even-odd fill. Collection depth is bounded at 32 and the existing
100,000-coordinate bound remains in effect. Source coordinates are retained;
projection supplies display geometry only. Qualify both the extension and the
unchanged geographic modes with native inspector and browser capture tests.

The capture adapter also removes a redundant non-namespaced `xmlns` attribute
from an already namespaced SVG root. XMLSerializer supplies the declaration;
the duplicate made exported SVG invalid in conforming XML readers. Cartesian
display coordinates are scaled before extents to avoid finite-value overflow
near Number.MAX_VALUE, while the source and exact native values remain intact.

SVG realization retains the presentation ABI's `fill-rule` paint attribute.
Ignoring its even-odd value filled native polygon holes in exported SVG.
This does not broaden CSS execution or remote asset admission.

The isolated build driver selects native node.exe on Windows and normalizes
package/test discovery paths. Compiler dependency-boundary checking is retained.
The consumer provisions exact-version native Node/TypeScript in its work area
when the source's local toolchain is absent, checks archive SHA-512 and tool
versions, and records compiler hashes. This does not claim Windows/macOS
qualification; platform teams still own their native evidence.
