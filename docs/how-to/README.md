# ScratchRobin How-To Guides & Feature Manuals

Practical step-by-step manuals with live screenshots for ScratchRobin's multi-engine database design, query authoring, custom datatypes/domains, and administration workflows.

---

## Visual Query Authoring

- [Building CTE, Recursive CTE, and Window Queries in the Visual Builders](visual-builder-cte-and-window-queries.md) — Step-by-step walkthrough with screenshots covering **Show system objects** (off by default), staged `WITH` and `WITH RECURSIVE` Common Table Expressions (Anchor + `[↻ SELF]` recursive join + termination guards), `OVER (...)` window analytics, `ROWS` / `RANGE` / `GROUPS` frame bounds, reusable `WINDOW` clauses, and 1-click post-window outer filtering.

---

## Custom Datatypes, Domains & Constraint Variations (Core Six Engines)

- [Core Six Custom Datatypes, Domains & Constraint Overview](custom-datatypes-and-domains-overview.md) — Engine capability matrix (`PostgreSQL 18.3`, `Firebird 5.0.4`, `DuckDB 1.5.2`, `MySQL 9.7`, `MariaDB 12.2`, `SQLite 3.53`), `SR-F` form mapping, Create / Alter / Drop lifecycle summary, and constraint equivalence patterns.
- [PostgreSQL Domains & Custom Types (`ENUM`, `COMPOSITE`, `RANGE`)](postgresql-domains-and-custom-types.md) — Step-by-step manual with screenshots for `SR-F-020068` covering collated domains, multiple named `CHECK` constraints, deferred `NOT VALID` + online `VALIDATE CONSTRAINT` & `RENAME CONSTRAINT` (`Edit...`), array domains, `ENUM`, `COMPOSITE`, and `RANGE`/`MULTIRANGE` types, and safe `Drop...` (`OperationDialog` with `CASCADE` + typed confirmation).
- [Firebird 5 Domains & Constraint Variations](firebird-domains-and-constraints.md) — Step-by-step manual with screenshots for `SR-F-020036` covering scalar, `UTF8` / `UNICODE_CI_AI` collated, multi-dimensional array (`[1:4, 1:2]`), and `BLOB SUB_TYPE TEXT` domains, `VALUE` check expressions, null-aware `CHECK` rules, atomic `ALTER DOMAIN` updates (`Edit...`), and safe `Drop...` (`OperationDialog`).
- [DuckDB Custom Types (`ENUM`, `STRUCT`, `UNION`, `ALIAS` / `ARRAY`) & Constraints](duckdb-custom-types-and-constraints.md) — Step-by-step manual with screenshots for `SR-F-020026` covering dictionary `ENUM`s, composite `STRUCT`s, tagged `UNION`s, fixed-length `DOUBLE[4]` arrays, `COMMENT ON TYPE`, read-only `Inspect...`, `CREATE OR REPLACE TYPE`, safe `Drop...` (`OperationDialog`), and nested struct-member `CHECK` constraints.
