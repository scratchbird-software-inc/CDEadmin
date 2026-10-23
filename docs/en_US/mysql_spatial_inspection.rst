MySQL spatial data inspection
==============================

Open **Diagnostics and verification → MySQL spatial data inspection** on a
native MySQL server or registered database. Discover or enter an authorized
persistent base table, observe its columns, select a geometry or binary column,
and explicitly allow private inspection. This workflow targets the admitted
MySQL 9.7.0 profile. Native SELECT privileges and workspace data-read/execute
admission apply. A registered database cannot inspect another database.

Coordinates and original values
--------------------------------

* Native geometry columns contain the exact four-byte little-endian SRID plus
  WKB. The inspector interprets the native storage order as X/Y, using the native
  constructor's longitude/latitude option for geographic coordinates.
* For binary columns select MySQL internal encoding or WKB explicitly. WKB
  requires an explicit SRID and longitude/latitude, latitude/longitude or native
  SRS-defined input order. No byte-order or SRID guesses are applied.
* **Native X/Y** plots the original native Cartesian values without assigning a
  different SRS. **WGS84** invokes native ST_Transform to SRID 4326 and plots
  longitude/latitude. Native refusal, including an unknown or unsupported source
  SRS, preserves the original values and diagnostics without a substituted map.
* Row inspection shows native WKT in both SRS-defined and X/Y order, native
  GeoJSON, validity, original bytes and the native SRS definition. Latitude-first
  WKT and longitude/latitude GeoJSON can legitimately differ. Binary download
  contains the exact original bytes, including the native SRID prefix when
  present, rather than reserialized geometry.

Points, multipoints, lines, multilines, polygons with holes, multipolygons and
nested geometry collections are supported. Native invalidity, empty geometry,
NULL, malformed binary and unsupported transformations remain distinct.
Oversized values report their original length without returning partial bytes.
The map is an approximate view; native text and original binary remain the
inspection authority.

Privacy, bounds and consistency
--------------------------------

No geometry is persisted in an application report/history store. Clearing the
inspection or replacing the target removes its private UI values and ignores
late replies. The inspector and DDN map make no external tile or map requests;
external access is disabled. No source writes or repairs are dispatched.

Each page uses an independent read-only native connection, leaving interactive
transactions, savepoints and warning areas intact. InnoDB pages have a native
repeatable-read snapshot; other engines explicitly lack a cross-row snapshot
guarantee. Pages are separate snapshots, not one retained table image. A visible
accessible native unique key determines ordering; otherwise the sample is
explicitly unordered. Source structure and SRID definitions are checked again
before returning the page. A fingerprint is observed metadata, not an immutable
native object identifier.

Limits are 1–100 rows per page, offset up to 1,000,000, 1–30 seconds of inspection
budget, 64 KiB per original value, 4 MiB per response, 10,000 map positions,
500 primitive map features, 32 collection levels and four concurrent reads per
application process. Native query deadlines apply; elapsed-budget checks run
between rows. Coverage explains any omitted whole value or map geometry. No
geometry or original byte string is truncated into a different value. Catalog
and selected-column pages are bounded separately.

DDN integration and qualification
----------------------------------

The optional DDN geographic module is loaded with the same-version current
runtime and tool. The consumed-source patch
``tools/dependency_patches/ddn-spatial-inspection.patch`` adds bounded lines,
collections, Cartesian fitting, polygon-hole filling and optional-module
loading against the all-in-one runtime. Intake applies it only to an isolated
dependency snapshot, records exact patch and adjusted-source hashes, then
rebuilds distributions together. The sister project's checkout stays untouched.
The original DDN license and notices ship with the consumed modules.

``tools/cdeadmin_mysql_spatial_qualification.py`` qualifies actual MySQL geometry
and privileges through the authenticated workspace on both native connector
interfaces, checks source bytes independently, and optionally exercises the
built desktop and exact download with Chromium. Store evidence outside the
repository. Linux native and desktop acceptance closes CMP-MY-09; Windows/macOS
qualification remains with the platform teams. ScratchBird history testing
remains owner-deferred.
