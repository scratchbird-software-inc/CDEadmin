# Reviewed consumer patch: `cube.dimensional@1` profile

Date: 2026-11-10

## Scope and reason

Following owner direction (2026-11-07, 2026-11-09 and 2026-11-10),
ScratchRobin extends its own isolated DDN capture to support a dedicated
dimensional cube profile (`cube.dimensional@1`) without modifying the
upstream public `Diagram-Design-Notation` repository.

`ddn_cube_dimensional.py` registers `cube.dimensional@1` in the isolated build
snapshot before `project/ddn/packages/profiles/tools/generate.py` compiles the
codex and shard packs:

- Primary palette: `cube`, `semantic_model`, `fact`, `dimension`, `bridge`,
  `metric`, `aggregate`, `materialized_view`, `field`, `binding`.
- Relation vocabulary: `aggregates`, `assoc`, `bindfield`, `binds`, `derives`,
  `filters`, `joins`, `lookup`, `owns`, `part`, `ref`, `uses`.
- Presentation: graph projection in the `graphs-erd` shard with inline
  `data` compartment rows and explicit crow's-foot cardinality markers so
  measure groups, dimension entities, role-playing dimensions, filtered
  measures and aggregation rules render cleanly in the shared viewer alongside
  `matrix.relations@1` (usage matrix) and `table.records@1` (aggregation grid).

Every changed input hash and the patch/review hashes are recorded in
`web/pgadmin/static/vendor/ddn/current/resource-manifest.json` under
`consumer_patches.cube_dimensional`.
